"""View products as queries (PLAN.md section 9).

The report page derives two products above the record: the series
(curve extraction per snap, whole-series transforms, window-relative
re-basing) and the summary at a cut (each plotted metric's value at
the instant, its delta, and its statistics over the window). AI
clients get the same products here, as data in the evidence envelope,
built by the same assembly and cache the page uses so the two never
disagree.

``series_product`` resolves a focus view exactly as the page does —
its declaration, the chosen option(s), the selector defaults — and
returns the focus-sized product for a named window. ``cut_summary``
resolves the focus component's state at an instant and asks the
host's registered summary builder for the rows.
"""
import logging
from datetime import timedelta

from django.utils import timezone

from . import registry
from .models import SystemSnap
from .queries import InvalidQuery, SnapNotFound, state_at
from .series import WINDOW_HOURS, observatory_series

logger = logging.getLogger(__name__)

_FAMILY_KEYS = ('name', 'title', 'prefixes', 'ids', 'order', 'stacked',
                'window_relative', 'cumulative_stack', 'end_stamped',
                'event_flow', 'event_flow_bin_scale', 'cumulative_panel',
                'measure_param',
                'units_by_measure', 'title_by_measure', 'default_off',
                'default_off_ids', 'units', 'fills')


def _iso(value):
    return value.isoformat() if value is not None else None


def resolve_focus(scope, focus, selection=None, selectors=None):
    """The focus view named by ``focus`` (its page label, case-
    insensitive) resolved as the page resolves it: the chosen options
    (``selection``: comma-separated option values, else the declared
    default), the selector axes (``selectors``: {param: value}, else
    each axis's default), and from them the families, the cut
    component, and the window floor."""
    provider = registry.get(scope)
    if provider is None:
        raise SnapNotFound(f'unknown scope {scope!r}')
    focus_defs = registry.resolve_focus_views(provider)
    focus_def = None
    for candidate in focus_defs:
        if str(focus or '').lower() == (candidate.get('label') or 'focus').lower():
            focus_def = candidate
            break
    if focus_def is None:
        known = ', '.join(sorted((d.get('label') or 'focus')
                                 for d in focus_defs)) or 'none'
        raise InvalidQuery(
            f'unknown focus view {focus!r} for scope {scope!r}; '
            f'known: {known}')
    options = list(focus_def.get('options') or ())
    by_value = {o.get('value'): o for o in options}
    open_groups = []
    chosen_values = []
    raw = (selection or '').strip()
    if raw.lower() == 'all':
        chosen_values = [o.get('value') for o in options if o.get('value')]
    elif raw.lower() == 'none':
        chosen_values = []
    elif raw:
        open_option = focus_def.get('open_option')
        for value in (s.strip() for s in raw.split(',')):
            if value in by_value:
                chosen_values.append(value)
            elif value and open_option is not None:
                synthesized = open_option(value)
                if synthesized:
                    by_value[value] = synthesized.get('option') or {}
                    open_groups.extend(synthesized.get('groups') or ())
                    chosen_values.append(value)
            elif value:
                raise InvalidQuery(
                    f'unknown selection {value!r} for focus {focus!r}; '
                    f"known: {', '.join(sorted(k for k in by_value if k))}")
    if not chosen_values and options and raw.lower() != 'none':
        default = by_value.get(focus_def.get('default'))
        chosen_values = [(default or options[0]).get('value')]
    chosen = [by_value[v] for v in chosen_values]

    selector_defs = list(focus_def.get('selectors') or ())
    if not selector_defs and focus_def.get('quantity'):
        selector_defs = [focus_def['quantity']]
    selected_values = []
    for sel in selector_defs:
        values = [c.get('value') for c in (sel.get('choices') or ())]
        value = str((selectors or {}).get(sel.get('param') or 'quantity')
                    or '').strip()
        if value and value not in values:
            raise InvalidQuery(
                f"unknown {sel.get('param') or 'quantity'} value {value!r}; "
                f"known: {', '.join(v for v in values if v)}")
        selected_values.append(value or sel.get('default') or '')
    from .views import _families_key
    families_key = _families_key(selector_defs, selected_values)

    def _families(option):
        by_key = option.get('families_by')
        if by_key:
            return by_key.get(families_key) or ()
        return option.get('families') or ()

    starts = [o.get('start') for o in chosen if o.get('start')]
    lead = chosen[0] if chosen else (options[0] if options else {})
    return {
        'provider': provider,
        'def': focus_def,
        'label': focus_def.get('label') or 'focus',
        'param': focus_def.get('param') or 'focus',
        'values': chosen_values,
        'selector_values': dict(zip(
            [sel.get('param') or 'quantity' for sel in selector_defs],
            selected_values)),
        'families': [f for o in chosen for f in _families(o)],
        'component': lead.get('component') or '',
        'start': min(starts) if starts else None,
        'open_groups': open_groups,
    }


def series_product(scope, focus, window='24h', selection=None,
                   selectors=None):
    """The focus view's series product over a named window, as the
    page builds it: the same curve predicate, the same snap
    components, the same cached product when the focus declares one.
    Returns a plain dict — curves with their points (stamps in the
    series' timezone), the families that declare them, coverage gaps,
    the snap count, and the cache state."""
    from .views import _focus_cache_key, _focus_curve_filter

    resolved = resolve_focus(scope, focus, selection, selectors)
    hours = WINDOW_HOURS.get(str(window or '').strip())
    if not hours:
        raise InvalidQuery(
            f'unknown window {window!r}; known: '
            + ', '.join(WINDOW_HOURS))
    now = timezone.now()
    start = now - timedelta(hours=hours)
    if resolved['start'] and resolved['start'] > start:
        start = resolved['start']
    provider = resolved['provider']
    focus_def = resolved['def']
    all_groups = (list(registry.resolve_curve_groups(provider))
                  + list(resolved['open_groups']))
    wanted = set(resolved['families'])
    curve_filter = _focus_curve_filter(all_groups, wanted)
    components = tuple(focus_def.get('components') or ()) or None

    def build():
        return observatory_series(scope, start, now,
                                  curve_filter=curve_filter,
                                  snap_components=components)

    series_cache = registry.hook('series_cache')
    cache = None
    series = None
    if series_cache is not None and focus_def.get('cache_series'):
        key = _focus_cache_key(scope, resolved['param'], wanted, window)
        cached = series_cache(key, build)
        if isinstance(cached, dict) and set(cached).issubset(
                {'value', 'refreshing', 'built_at', 'age_seconds'}):
            series = cached.get('value')
            cache = {'key': key, 'built_at': _iso(cached.get('built_at')),
                     'age_seconds': cached.get('age_seconds'),
                     'refreshing': bool(cached.get('refreshing'))}
        else:
            series = cached
            cache = {'key': key}
    if series is None:
        # No cache, or another worker owns the first fill: build here.
        series = build()
        cache = cache or None
    families = [{k: g[k] for k in _FAMILY_KEYS if k in g}
                for g in all_groups if g.get('name') in wanted]
    return {
        'scope': scope,
        'focus': resolved['label'],
        'selection': resolved['values'],
        'selectors': resolved['selector_values'],
        'window': window,
        'requested_start': _iso(start),
        'requested_end': _iso(now),
        'series_start': series.get('start'),
        'series_end': series.get('end'),
        'timezone': series.get('timezone'),
        'snap_count': series.get('snap_count'),
        'families': families,
        'curves': series.get('curves') or {},
        'gaps': series.get('gaps') or [],
        'cache': cache,
    }


def cut_summary(scope, focus, time, since=None):
    """The summary at a cut as data: the focus component's state at
    the latest snap carrying it at or before ``time``, handed to the
    host's registered summary builder for that component
    (ScopeProvider.cut_summaries) with the previous carrying snap and
    the window basis ``since`` (default: 24 hours before the cut).
    The envelope carries the actual snap time, coverage at the
    requested instant, and the component's provenance."""
    resolved = resolve_focus(scope, focus)
    component = resolved['component']
    if not component:
        raise InvalidQuery(f'focus view {focus!r} names no cut component')
    provider = resolved['provider']
    builder = (getattr(provider, 'cut_summaries', None) or {}).get(component)
    if builder is None:
        raise InvalidQuery(
            f'no cut summary is registered for component {component!r} '
            f'in scope {scope!r}')
    result = state_at(scope, time)
    carrying = (SystemSnap.objects
                .filter(scope=scope, snap_time__lte=result.requested_at,
                        state__components__has_key=component)
                .order_by('-snap_time').first())
    if carrying is None:
        first = (SystemSnap.objects
                 .filter(scope=scope, state__components__has_key=component)
                 .order_by('snap_time').values('snap_time').first())
        raise SnapNotFound(
            f'no {component} record at or before {result.requested_at.isoformat()}'
            + (f"; the record begins at {first['snap_time'].isoformat()}"
               if first else ''))
    previous = (SystemSnap.objects
                .filter(scope=scope, snap_time__lt=carrying.snap_time,
                        state__components__has_key=component)
                .order_by('-snap_time').first())
    payload = ((carrying.state or {}).get('components') or {}).get(component) or {}
    previous_payload = (((previous.state or {}).get('components') or {})
                        .get(component) or {}) if previous else {}
    if since is None:
        since = result.requested_at - timedelta(hours=24)
    if since >= result.requested_at:
        raise InvalidQuery('since must precede time')
    summary = builder(scope, result.requested_at, since,
                      payload.get('data') or {},
                      previous_payload.get('data') or {})
    coverage = result.coverage.as_dict()
    return {
        'scope': scope,
        'focus': resolved['label'],
        'component': component,
        'requested_at': _iso(result.requested_at),
        'snap_time': _iso(carrying.snap_time),
        'previous_snap_time': _iso(previous.snap_time) if previous else None,
        'coverage': coverage,
        'since': _iso(since),
        'component_provenance': {
            key: payload.get(key)
            for key in ('v', 'registration_version', 'revision',
                        'assessed_at', 'source_as_of',
                        'assessment_policy', 'publisher_identity')
            if key in payload},
        'summary': summary,
    }
