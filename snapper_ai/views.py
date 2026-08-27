"""Human-facing Snapper report and instrument views.

Experiment-agnostic: scopes, component card builders, curve families,
reference resolution, preferences, and configuration all arrive
through the host-registered providers and hooks (see registry.py).
The host includes ``snapper_ai.urls`` and provides a ``base.html``.
"""

import json
import logging
from hashlib import sha256

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from . import registry
from .models import CaptureCursor, CurrentComponent, SystemSnap
from .presentation import cut_chip, cut_delta, et_naive


RECENT_SNAP_LIMIT = 100


def _focus_curve_filter(all_groups, wanted):
    """The curve predicate for a focus-sized product: curves of the
    wanted families only."""
    cache_groups = [group for group in all_groups
                    if group.get('name') in wanted]

    def _filter(curve_id):
        return any(registry.group_matches(group, curve_id)
                   for group in cache_groups)

    return _filter


def _focus_cache_key(scope, focus_param, wanted, cache_span):
    """The focus product key; the families set is its identity."""
    identity = '\n'.join(sorted(wanted)) or 'empty'
    token = sha256(identity.encode()).hexdigest()[:16]
    return (f'snapper_series:v18:{scope}:focus:'
            f'{focus_param}:{token}:{cache_span}')


def prewarm_focus_series(scope, window_keys=()):
    """Rebuild a scope's cache-opted focus products so pages land warm.

    For each focus view declaring ``cache_series`` and each of its
    options, rebuilds the product at the option's own span (the
    default landing) and at each named window in ``window_keys``,
    honoring the option's window floor. The host calls this after the
    focused record changes — e.g. a nightly rebuild of the underlying
    record — through a ``series_cache`` hook accepting
    ``refresh=True``; a hook without the parameter still fills any
    missing product.

    Returns the product keys rebuilt.
    """
    from datetime import timedelta

    from django.utils import timezone

    from .series import WINDOW_HOURS, observatory_series

    series_cache = registry.hook('series_cache')
    provider = registry.get(scope)
    if series_cache is None or provider is None:
        return []
    now = timezone.now()
    all_groups = list(registry.resolve_curve_groups(provider))
    warmed = []
    for focus_def in registry.resolve_focus_views(provider):
        if (not focus_def.get('cache_series')
                or focus_def.get('prewarm_series') is False):
            continue
        focus_param = focus_def.get('param') or 'focus'
        components = tuple(focus_def.get('components') or ()) or None
        selector_defs = list(focus_def.get('selectors') or ())
        if not selector_defs and focus_def.get('quantity'):
            selector_defs = [focus_def['quantity']]
        families_key = '|'.join(
            str(sel.get('default') or '') for sel in selector_defs)
        for option in (focus_def.get('options') or ()):
            by_key = option.get('families_by')
            families = ((by_key.get(families_key) if by_key
                         else option.get('families')) or ())
            wanted = set(families)
            curve_filter = _focus_curve_filter(all_groups, wanted)
            floor = option.get('start')
            spans = []
            if floor:
                spans.append((f'span:{floor.date().isoformat()}', floor))
            for window_key in window_keys:
                hours = WINDOW_HOURS.get(window_key)
                if not hours:
                    continue
                start = now - timedelta(hours=hours)
                if floor:
                    start = max(start, floor)
                spans.append((window_key, start))
            for cache_span, start in spans:
                key = _focus_cache_key(
                    scope, focus_param, wanted, cache_span)

                def builder(start=start, curve_filter=curve_filter,
                            components=components):
                    return observatory_series(
                        scope, start, now,
                        curve_filter=curve_filter,
                        snap_components=components)

                try:
                    series_cache(key, builder, refresh=True)
                except TypeError:
                    series_cache(key, builder)
                warmed.append(key)
    return warmed


def _view_default_off_ids(member_ids, rendered_groups, curves):
    """The default-off vocabulary the URL stamper serializes against:
    provider member-level ids plus every rendered curve whose rendered
    group carries the group-level ``default_off`` mark. Both channels
    must be in one set — a curve unticked by its group's default is a
    default, not a viewer exclusion, and must never be stamped into
    ``off=`` (URL state carries only deliberate selections)."""
    out = set(member_ids)
    for group in (rendered_groups or ()):
        if not group.get('default_off'):
            continue
        out.update(
            curve_id for curve_id in curves
            if registry.group_matches(group, curve_id))
    return sorted(out)


def _validated_scope(scope):
    if registry.get(scope) is None:
        raise Http404(f'Unknown Snapper scope {scope!r}')
    return scope


def _scope_label(scope):
    provider = registry.get(scope)
    return provider.label if provider else scope


def _health_url():
    hook = registry.hook('health_url')
    return hook() if hook else None


def _scope_options(scope, active_query='', active_focus_label=None):
    """Scope switcher entries: each scope, followed by its provider's
    preset tabs (report-page links with a fixed query string). A preset
    is active when the current querystring carries its families value.
    Each focus view links to its own selection-free page and is active
    when it is the engaged one (by page or by parameter)."""
    from urllib.parse import parse_qs

    active_params = parse_qs(active_query)
    active_families = (active_params.get('families') or [''])[0]
    options = []
    for name in registry.scopes():
        plain_index = len(options)
        options.append({
            'name': name,
            'label': _scope_label(name),
            'active': name == scope and not active_families,
        })
        provider = registry.get(name)
        presets = provider.preset_links if provider else ()
        if callable(presets):
            try:
                presets = presets()
            except Exception:                                # noqa: BLE001
                presets = ()
        for preset in presets or ():
            preset_families = (parse_qs(preset.get('query') or '')
                               .get('families') or [''])[0]
            options.append({
                'name': name,
                'label': preset.get('label') or 'preset',
                'query': preset.get('query') or '',
                'active': (name == scope and bool(active_families)
                           and preset_families == active_families),
            })
        for focus in registry.resolve_focus_views(provider):
            param = focus.get('param') or 'focus'
            label = focus.get('label') or 'Focus'
            focus_active = (name == scope
                            and (active_focus_label == label
                                 or (active_focus_label is None
                                     and bool(active_params.get(param)))))
            options.append({
                'name': name,
                'label': label,
                'focus_slug': label.lower(),
                'active': focus_active,
            })
            if focus_active:
                options[plain_index]['active'] = False
    return options


def _landing_cut(scope, component, window_start, window_end):
    """The load-time default cut of a focus view: half a recording
    interval back from the window's end, so the page opens on the
    latest recorded state rather than a mid-window instant. The
    interval is the focus component's own change cadence, read from
    the spacing of its most recent change-bearing snaps (full snaps
    carry every component, so presence alone says nothing about
    cadence). The cut never lands before the component's first
    change-bearing snap in the window — a record younger than the
    window would otherwise open on an instant with nothing to show."""
    spacing = None
    first = None
    if component:
        changed = (SystemSnap.objects
                   .filter(scope=scope, snap_time__gte=window_start,
                           snap_time__lte=window_end,
                           changed_components__contains=[component]))
        stamps = list(changed.order_by('-snap_time')
                      .values_list('snap_time', flat=True)[:4])
        diffs = sorted(a - b for a, b in zip(stamps, stamps[1:]) if a > b)
        if diffs:
            spacing = diffs[len(diffs) // 2]
        first = (changed.order_by('snap_time')
                 .values_list('snap_time', flat=True).first())
    if spacing is None:
        spacing = (window_end - window_start) / 48
    cut = window_end - spacing / 2
    if first and cut < first:
        cut = first
    return cut


def _focus_landing_cut(scope, focus_option, groups, observatory,
                       window_start, window_end):
    """The landing cut lands inside the latest display bin that has
    data, so the page opens on detail with something to show — a grid
    that materializes behind the clock (the campaign day bins build
    overnight, so today is empty) must not take the cut. Families whose
    columns stamp an interval's END (end-stamped quilts, event flows,
    cumulative day grids) take the cut half a grid step back from
    their last data stamp; instantaneous curves take their last stamp
    exactly, and the newer of the two readings wins. With nothing
    plotted at all, fall back to the component's change cadence."""
    from datetime import datetime
    from zoneinfo import ZoneInfo as _ZoneInfo
    et = _ZoneInfo('America/New_York')

    def _parse(stamp):
        try:
            when = datetime.fromisoformat(str(stamp).replace('Z', '+00:00'))
        except ValueError:
            return None
        if when.tzinfo is None:
            # Event-flow bins stamp naive Eastern grid edges.
            when = when.replace(tzinfo=et)
        return when

    primary = ([g for g in groups
                if g.get('stacked') or g.get('event_flow')] or groups)
    interval_groups = [g for g in primary
                       if g.get('end_stamped') or g.get('event_flow')
                       or g.get('cumulative_stack')]
    instant_groups = [g for g in primary if g not in interval_groups]

    def _stamps(for_groups):
        found = set()
        for curve_id, curve in (observatory.get('curves') or {}).items():
            if not any(registry.group_matches(g, curve_id)
                       for g in for_groups):
                continue
            for point in (curve.get('points') or ()):
                if point and len(point) > 1 and point[1] is not None:
                    when = _parse(point[0])
                    if when is not None:
                        found.add(when)
        return sorted(found)

    cut = None
    if interval_groups:
        stamps = _stamps(interval_groups)
        if stamps:
            diffs = (b - a for a, b in zip(stamps, stamps[1:]))
            step = min((d for d in diffs if d.total_seconds() > 0),
                       default=None)
            cut = stamps[-1] - step / 2 if step else stamps[-1]
    if instant_groups:
        stamps = _stamps(instant_groups)
        if stamps and (cut is None or stamps[-1] >= cut):
            cut = stamps[-1]
    if cut is None:
        return _landing_cut(scope, focus_option.get('component') or '',
                            window_start, window_end)
    return min(max(cut, window_start), window_end)


def _curve_colors(provider, curve_ids):
    """Provider-declared colors for the curves that have one (the
    host's semantic vocabulary, e.g. state colors); everything else
    takes the client's palette deal."""
    hook = provider.curve_color if provider else None
    if not hook:
        return {}
    colors = {}
    for curve_id in curve_ids:
        try:
            color = hook(curve_id)
        except Exception as e:                               # noqa: BLE001
            logger.error('snapper curve_color failed for %r: %s',
                         curve_id, e)
            return colors
        if color:
            colors[curve_id] = color
    return colors


def _dict(value):
    return value if isinstance(value, dict) else {}


def _json(value):
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def _value_at(data, path):
    value = data
    for part in str(path or '').split('.'):
        if not part or not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _quantity_values(registration, data):
    rows = []
    for name, definition in sorted(
            _dict(registration.get('quantities')).items()):
        definition = _dict(definition)
        value = _value_at(data, definition.get('path', name))
        is_complex = isinstance(value, (dict, list))
        if is_complex:
            display = json.dumps(value, indent=2, sort_keys=True)
        elif value is None:
            display = '—'
        else:
            display = str(value)
        rows.append({
            'name': name,
            'description': definition.get('description', ''),
            'value': display,
            'is_complex': is_complex,
        })
    return rows


def _age_text(delta_seconds):
    """Compact human age ('31s', '2m 31s', '3h 04m', '2d 5h'); None when
    under a second — the caller then falls back to the absolute time."""
    seconds = int(round(delta_seconds))
    if seconds < 1:
        return None
    if seconds < 60:
        return f'{seconds}s'
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f'{minutes}m {seconds:02d}s' if seconds else f'{minutes}m'
    hours, minutes = divmod(minutes, 60)
    if hours < 48:
        return f'{hours}h {minutes:02d}m' if minutes else f'{hours}h'
    days, hours = divmod(hours, 24)
    return f'{days}d {hours}h' if hours else f'{days}d'


def _present_snap_component(name, payload, scope=None,
                            reference_time=None):
    payload = _dict(payload)
    registration = _dict(payload.get('registration'))
    data = _dict(payload.get('data'))
    health = None
    if name == 'health':
        overall = _dict(data.get('overall'))
        checks = []
        for check_name, check in sorted(_dict(data.get('checks')).items()):
            check = _dict(check)
            checks.append({
                'name': check_name,
                'category': check.get('category', ''),
                'status': check.get('status', 'unknown'),
                'summary': check.get('summary', ''),
            })
        health = {
            'status': overall.get('status', 'unknown'),
            'reason': overall.get('reason', ''),
            'counts': _dict(overall.get('counts')),
            'checks': checks,
            'non_ok': [c for c in checks
                       if c['status'] not in ('ok', 'healthy')],
        }
    # Provider-registered components render as the same structured card
    # the cut uses (no deltas — there is no previous snap in this
    # presentation); a component without a registered rendering falls
    # back to the quantity table.
    card = {'kind': None}
    provider = registry.get(scope) if scope else None
    builder = (provider.component_cards.get(name)
               if provider and provider.component_cards else None)
    if builder is not None:
        # A builder may decline this presentation (the cut convention:
        # None omits the card); here the component still renders, as
        # the generic quantity table.
        built = builder(data, {}, {'scope': scope,
                                   'requested_at': reference_time})
        if built is not None:
            card = built
            if provider.card_template:
                card.setdefault('template', provider.card_template)
    return {
        'name': name,
        'title': registration.get('title') or name,
        'description': registration.get('description', ''),
        'revision': payload.get('revision'),
        'registration_version': payload.get('registration_version'),
        'assessed_at': payload.get('assessed_at'),
        'source_as_of': payload.get('source_as_of'),
        'accepted_at': payload.get('accepted_at'),
        'publisher_identity': payload.get('publisher_identity', ''),
        'health': health,
        'card': card,
        'quantities': _quantity_values(registration, data),
        'payload_json': _json(payload),
    }


def _snap_row(snap):
    return {
        'id': snap.id,
        'snap_time': snap.snap_time,
        'observed_at': snap.observed_at,
        'reasons': ', '.join(snap.reasons or []) or '—',
        'changed_components': (
            ', '.join(snap.changed_components or []) or '—'),
        'capture_policy': snap.capture_policy,
        'encoding': snap.encoding,
        'component_count': len(snap.component_revisions or {}),
    }


def snapper_root(request):
    names = registry.scopes()
    if not names:
        raise Http404('No Snapper scopes registered')
    return redirect('snapper_ai:snapper_report', scope=names[0])


def _snapper_prefs(request, scope):
    """The signed-in user's remembered UI state for one scope."""
    prefs_get = registry.hook('prefs_get')
    if prefs_get is None or not request.user.is_authenticated:
        return {}
    value = prefs_get(request.user.username, scope)
    return value if isinstance(value, dict) else {}


def snapper_prefs_save(request, scope):
    """POST endpoint remembering the observatory UI state per user."""
    import json as _json_module

    from django.http import JsonResponse

    scope = _validated_scope(scope)
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'saved': False, 'reason': 'not signed in'})
    prefs_set = registry.hook('prefs_set')
    if prefs_set is None:
        return JsonResponse({'saved': False, 'reason': 'no prefs backend'})
    try:
        payload = _json_module.loads(request.body or b'{}')
    except ValueError:
        return JsonResponse({'error': 'invalid JSON'}, status=400)
    allowed = {key: payload[key]
               for key in ('curves_off', 'curves_off2', 'curves_off3',
                           'curves_off4', 'curves_off5', 'curves_on5',
                           'curves_off6', 'curves_on6',
                           'window', 'lanes_open',
                           'pc_off', 'pc_off2', 'focus_last')
               if key in payload}
    prefs_set(request.user.username, scope, allowed)
    return JsonResponse({'saved': True})


def snapper_report(request, scope, snap_id=None, focus_slug=None):
    from django.utils import timezone

    from .series import (DEFAULT_WINDOW, WINDOW_HOURS,
                         observatory_series, parse_window)

    scope = _validated_scope(scope)
    snaps = SystemSnap.objects.filter(scope=scope).order_by('-snap_time')
    latest_snap = snaps.first()

    # Focus views (registry.focus_view): the report narrowed to one
    # host-defined selection — only its families, its component in the
    # cut, its start as the window floor. A provider may declare
    # several; the engaged one is named by the page slug or by the
    # first declaration whose parameter the request carries.
    provider = registry.get(scope)
    focus_defs = registry.resolve_focus_views(provider)
    focus_def = None
    focus_option = None
    # A focus view's own page (/scope/<label>/) engages that focus
    # with its defaults; the query parameter only narrows. A slug that
    # names no focus view is an unknown page.
    if focus_slug is not None:
        for candidate in focus_defs:
            if focus_slug.lower() == (candidate.get('label')
                                      or 'focus').lower():
                focus_def = candidate
                break
        if focus_def is None:
            raise Http404(f'Unknown Snapper page {focus_slug!r}')
    else:
        # A present parameter engages its focus even when empty:
        # ?site= with nothing ticked is the all-off state, not an
        # exit from the view.
        for candidate in focus_defs:
            if request.GET.get(
                    candidate.get('param') or 'focus') is not None:
                focus_def = candidate
                break
    focus_selected = []
    open_groups = []
    if focus_def:
        raw_value = request.GET.get(focus_def.get('param') or 'focus')
        raw = (raw_value or '').strip()
        if raw_value is not None or focus_slug is not None:
            options = focus_def.get('options') or []
            by_value = {o.get('value'): o for o in options}
            if raw.lower() == 'all':
                focus_selected = [o.get('value') for o in options
                                  if o.get('value')]
            else:
                # An off-list value may be served by the view's
                # open_option hook: (value) -> {'option': {...},
                # 'groups': (...)} or None. The synthesized option and
                # its family groups exist for this request only — the
                # open-parameter path for views whose value space is
                # unbounded (e.g. any task id reached by link).
                open_option = focus_def.get('open_option')
                focus_selected = []
                for value in (s.strip() for s in raw.split(',')):
                    if value in by_value:
                        focus_selected.append(value)
                    elif value and open_option is not None:
                        synthesized = open_option(value)
                        if synthesized:
                            by_value[value] = synthesized.get('option') or {}
                            open_groups.extend(
                                synthesized.get('groups') or ())
                            focus_selected.append(value)
            # Only the clean page (no parameter at all) lands on the
            # default. An explicitly empty parameter is all off — a
            # valid state, as in every Snapper tick row — and stays
            # off until the user ticks again.
            if (not focus_selected and options
                    and (raw_value is None or raw)):
                default = by_value.get(focus_def.get('default'))
                focus_selected = [(default or options[0]).get('value')]
            chosen = [by_value[v] for v in focus_selected]
            # A focus view may offer selector axes (e.g. a plotted
            # quantity, a grouping lens): each option carries families
            # per selector combination, and each axis's ?<param>=
            # choice picks which set plots. A single 'quantity' axis is
            # accepted as the one-axis form.
            selector_defs = list(focus_def.get('selectors') or ())
            if not selector_defs and focus_def.get('quantity'):
                selector_defs = [focus_def['quantity']]
            selected_values = []
            for sel in selector_defs:
                values = [c.get('value')
                          for c in (sel.get('choices') or ())]
                value = (request.GET.get(sel.get('param')
                                         or 'quantity') or '').strip()
                if value not in values:
                    value = sel.get('default') or ''
                selected_values.append(value)
            families_key = '|'.join(selected_values)

            def _families(option):
                by_key = option.get('families_by')
                if by_key:
                    return by_key.get(families_key) or ()
                return option.get('families') or ()

            # One or several options at once: families union, window
            # floored at the earliest start. All off is valid: no
            # families, the cut still narrowed to the view's component.
            starts = [o.get('start') for o in chosen if o.get('start')]
            lead = chosen[0] if chosen else (options[0] if options else {})
            focus_option = {
                'value': ','.join(focus_selected),
                'selector_values': selected_values,
                'families': [f for o in chosen for f in _families(o)],
                'component': lead.get('component') or '',
                'collapse_below': (chosen[0].get('collapse_below')
                                   if chosen else None),
                'start': min(starts) if starts else None,
            }

    user_prefs = _snapper_prefs(request, scope)
    now = timezone.now()
    window_start, window_end, window_key = parse_window(
        request, now,
        default_window=str(user_prefs.get('window') or DEFAULT_WINDOW))
    if focus_option is not None and focus_option.get('start'):
        explicit = any(request.GET.get(key)
                       for key in ('window', 'start', 'end', 'view'))
        if explicit:
            window_start = max(window_start, focus_option['start'])
            if window_start >= window_end:
                # A requested range wholly before the focus floor
                # squashes to nothing — fall back to the record's
                # natural span rather than rendering a zero-width page.
                window_start = focus_option['start']
                window_end = now
                window_key = 'custom'
        else:
            # A focus view's natural window is the focused record's own
            # span: its start through now. A remembered short window
            # (hours) holds no points of a daily record and lands on an
            # empty plot; explicit window choices are honored above.
            # The key becomes 'custom' so no named button claims the
            # span and the client never stamps a named window into the
            # URL (which would land the next load back on the
            # remembered short window).
            window_start = focus_option['start']
            window_end = now
            window_key = 'custom'
    # Resolve the groups before the series cache: a provider may opt a
    # focus into a focus-sized product, whose curve predicate comes
    # from the exact families selected for this request. Groups
    # synthesized by an open_option hook join for this request only.
    all_groups = list(registry.resolve_curve_groups(provider)) + open_groups

    # The series is a cached product where the host provides the
    # mechanism: named windows and the focus default span key stably
    # (their spans slide, their identity does not); explicit ranges
    # build inline. The top-level dict is copied before the focus
    # narrowing mutates it.
    series_cache = registry.hook('series_cache')
    cache_key = None
    series_curve_filter = None
    # A focus that declares its component set builds from that set's
    # snaps alone (observatory_series snap_components) — the focused
    # record is constant between its own snaps, and focus views keep
    # no lanes or gap shading, so the filtered walk renders
    # identically at a fraction of the cost on busy scopes.
    series_snap_components = None
    if focus_option is not None and focus_def.get('components'):
        series_snap_components = tuple(focus_def['components'])
    if (series_cache is not None
            and not (request.GET.get('start') or request.GET.get('end'))):
        cache_span = None
        if window_key in WINDOW_HOURS:
            cache_span = window_key
        elif focus_option is not None and focus_option.get('start'):
            cache_span = f'span:{window_start.date().isoformat()}'
        if cache_span:
            if (focus_option is not None
                    and focus_def.get('cache_series')):
                wanted = set(focus_option.get('families') or ())
                series_curve_filter = _focus_curve_filter(
                    all_groups, wanted)
                cache_key = _focus_cache_key(
                    scope, focus_def.get('param') or 'focus',
                    wanted, cache_span)
            else:
                cache_key = f'snapper_series:v18:{scope}:{cache_span}'
    if cache_key:
        cached = series_cache(
            cache_key,
            lambda: observatory_series(
                scope, window_start, window_end,
                curve_filter=series_curve_filter,
                snap_components=series_snap_components))
        cache_refreshing = False
        if (isinstance(cached, dict)
                and set(cached).issubset(
                    {'value', 'refreshing', 'built_at', 'age_seconds'})):
            cached_value = cached.get('value')
            cache_refreshing = bool(cached.get('refreshing'))
        else:
            # Backward compatibility for a host still returning the
            # former bare-series hook value.
            cached_value = cached
        if cached_value is None:
            # Another worker owns the first fill.  Return a truthful,
            # immediately renderable shell; the page's short follow-up
            # fetch will pick up the product when that build lands.
            observatory = {
                'scope': scope,
                'start': et_naive(window_start),
                'end': et_naive(window_end),
                'end_ms': int(window_end.timestamp() * 1000),
                'timezone': 'ET', 'snap_count': 0,
                'curves': {}, 'lanes': {}, 'gaps': [],
            }
            cache_refreshing = True
        else:
            observatory = dict(cached_value)
        observatory['cache_refreshing'] = cache_refreshing
    else:
        observatory = observatory_series(
            scope, window_start, window_end,
            curve_filter=series_curve_filter,
            snap_components=series_snap_components)
        observatory['cache_refreshing'] = False
    scope_groups = list(registry.resolve_scope_curve_groups(provider))
    default_off_ids = sorted({
        curve_id
        for group in all_groups
        for curve_id in (group.get('default_off_ids') or ())
    })
    if (focus_option is None and provider is not None
            and provider.scope_curve_groups is not None):
        # The front door is an explicit compact projection. Focus-only
        # Campaign/Site curves do not fall through into a giant Other
        # family after their control rows are removed.
        def _in_scope(curve_id):
            return any(registry.group_matches(group, curve_id)
                       for group in scope_groups)

        observatory['curves'] = {
            curve_id: curve
            for curve_id, curve in observatory['curves'].items()
            if _in_scope(curve_id)}
    observatory['colors'] = _curve_colors(provider, observatory['curves'])

    focus_context = None
    if focus_option is not None:
        # Only the focused families' curves and control rows render.
        wanted = set(focus_option.get('families') or ())
        groups = [dict(g)
                  for g in all_groups
                  if g.get('name') in wanted]
        # A chosen stacked family is the focus view's primary display:
        # a scope-view default_off marking does not apply to it. A
        # focus whose families include no stacked group has no other
        # primary display — every family it names is the view, so all
        # of them shed the scope-view marking. A family marked
        # focus_closed keeps a closed section by default (its curves
        # stay ticked) — secondary within the focus itself.
        has_stacked = any(group.get('stacked') for group in groups)
        for group in groups:
            if group.get('stacked') or not has_stacked:
                group.pop('default_off', None)
                if group.get('focus_closed'):
                    group['start_closed'] = True

        def _in_focus(curve_id):
            return any(registry.group_matches(g, curve_id)
                       for g in groups)

        observatory['curves'] = {
            curve_id: curve
            for curve_id, curve in observatory['curves'].items()
            if _in_focus(curve_id)}
        # The focused record carries its own provenance; the scope's
        # capture-coverage shading belongs to the scope view.
        observatory['gaps'] = []
        # So do the core health lanes: on a focus view the plot is the
        # focused record alone.
        observatory['lanes'] = {
            lane_id: lane
            for lane_id, lane in (observatory.get('lanes') or {}).items()
            if lane_id != 'health' and lane.get('parent') != 'health'}
        # Fold the long tail of a stacked family: members that never
        # reach the collapse fraction of ANY single interval's family
        # total merge into one 'other' band (id suffix zz_other, drawn
        # atop the stack). The test is per interval, not whole-window:
        # a new configuration dominating recent days must keep its
        # color even while its window sum is still small. Hundreds of
        # never-visible slivers otherwise cost real browsers dearly;
        # the fold is stated, never silent.
        collapse = float(focus_option.get('collapse_below') or 0)
        if collapse > 0:
            for group in groups:
                # Long-tail folding belongs only to the arrivals quilt,
                # identified by its PC grouping metadata. Additive
                # category stacks and exact-id per-category PC stacks
                # must retain every member; an exact-id family has no
                # prefix and must never fall through to matching every
                # curve with startswith('').
                if not group.get('stacked') or not group.get('pc_groups'):
                    continue
                prefix = (group.get('prefixes') or [''])[0]
                members = {
                    curve_id: dict(curve['points'])
                    for curve_id, curve in observatory['curves'].items()
                    if curve_id.startswith(prefix)}
                interval_totals = {}
                for points in members.values():
                    for x, y in points.items():
                        interval_totals[x] = interval_totals.get(x, 0) + y
                if not any(interval_totals.values()):
                    continue

                def _peak_share(points):
                    return max(
                        (y / interval_totals[x]
                         for x, y in points.items()
                         if interval_totals[x]), default=0)

                folded = [curve_id for curve_id, points in members.items()
                          if _peak_share(points) < collapse]
                if len(folded) < 2:
                    continue
                other_points = {}
                for curve_id in folded:
                    for x, y in observatory['curves'][curve_id]['points']:
                        other_points[x] = other_points.get(x, 0) + y
                    del observatory['curves'][curve_id]
                observatory['curves'][f'{prefix}zz_other'] = {
                    'label': (f'{len(folded)} configurations, each '
                              f'below {collapse:.0%} of every '
                              f'interval\'s total'),
                    'points': sorted(other_points.items()),
                }
        param = focus_def.get('param') or 'focus'
        default = focus_def.get('default') or ''

        def _focus_url(values, overrides=None):
            # Change only focus membership (and any explicitly changed
            # selector); keep the live window, cut, and zoom query.
            query = request.GET.copy()
            query[param] = (values if isinstance(values, str)
                            else ','.join(values))
            for i, sel in enumerate(selector_defs):
                value = selected_values[i]
                sel_param = sel.get('param') or 'quantity'
                if overrides and sel_param in overrides:
                    value = overrides[sel_param]
                if value and value != (sel.get('default') or ''):
                    query[sel_param] = value
                else:
                    query.pop(sel_param, None)
            return '?' + query.urlencode()

        def _toggle_url(value):
            # A tick toggles membership; all off is a valid state, as
            # in every Snapper tick row, and the explicitly empty
            # parameter says so.
            after = [v for v in focus_selected if v != value]
            if value not in focus_selected:
                after = focus_selected + [value]
            return _focus_url(after)

        selectors_context = []
        for i, sel in enumerate(selector_defs):
            sel_param = sel.get('param') or 'quantity'
            selectors_context.append({
                'label': sel.get('label') or 'Counting',
                'param': sel_param,
                'value': selected_values[i],
                'choices': [
                    {'value': c.get('value'), 'label': c.get('label'),
                     'active': c.get('value') == selected_values[i],
                     'url': _focus_url(
                         focus_selected, {sel_param: c.get('value')})}
                    for c in (sel.get('choices') or ())],
            })
        from urllib.parse import urlencode as _enc
        focus_context = {
            'label': focus_def.get('label') or 'Focus',
            'selector_label': (focus_def.get('selector_label')
                               or focus_def.get('label') or 'Focus'),
            'note': focus_def.get('note') or '',
            'param': param,
            'value': focus_option.get('value') or '',
            'component': focus_option.get('component') or '',
            'groups': groups,
            'all_on_url': _focus_url('all'),
            'all_off_url': _focus_url([]),
            'options': [
                {'value': o.get('value'), 'label': o.get('label'),
                 'active': o.get('value') in focus_selected,
                 'url': _toggle_url(o.get('value'))}
                for o in (focus_def.get('options') or ())],
            # A selection served by the open_option hook is not among
            # the listed options; the template shows it as a plain
            # label instead of a tick row.
            'open_label': ', '.join(
                str((by_value.get(v) or {}).get('label') or v)
                for v in focus_selected
                if not any(o.get('value') == v
                           for o in (focus_def.get('options') or ()))),
            'selectors': selectors_context,
            # The cut narrows by the EFFECTIVE selector values — the
            # clean page carries none in its URL, yet its cut must
            # know them all.
            'cut_query': _enc(
                [(sel.get('param') or 'quantity', selected_values[i])
                 for i, sel in enumerate(selector_defs)
                 if selected_values[i]]),
            # Parameter names the window strip carries through when
            # present in the page URL.
            'carry_params': ','.join(
                sel.get('param') or 'quantity'
                for sel in selector_defs),
        }

    # Window stepping: the arrows shift the whole window through the
    # recorded history, loading older or newer data server-side. No
    # arrow only at an edge — 'now' on the right, the earliest snap on
    # the left. The named window key rides along in the URL so stepping
    # forward to the present restores the rolling named window.
    from urllib.parse import urlencode as _urlencode
    from zoneinfo import ZoneInfo as _ZoneInfo
    earliest_snap = snaps.last()
    span = window_end - window_start
    # Named-window provenance: a named key is restored on return to the
    # present only when the view actually descends from a named window
    # (the current page is one, or the key rode in with a step URL). A
    # computed span with no such ancestry — the campaign page default —
    # keeps its duration instead of falling back to the default window.
    named_in_url = request.GET.get('window') or ''
    has_named_provenance = (named_in_url in WINDOW_HOURS
                            or window_key in WINDOW_HOURS)
    named_key = (named_in_url if named_in_url in WINDOW_HOURS
                 else window_key if window_key in WINDOW_HOURS
                 else DEFAULT_WINDOW)

    def _range_url(start, end):
        params = {'start': start.isoformat(), 'end': end.isoformat()}
        if has_named_provenance:
            params['window'] = named_key
        return '?' + _urlencode(params)

    observatory_prev_url = None
    observatory_next_url = None
    # Stepping floor: the earliest snap, raised to the focused record's
    # start on a focus page — the arrows never offer territory the page
    # cannot show.
    step_floor = earliest_snap.snap_time if earliest_snap else None
    if focus_option is not None and focus_option.get('start'):
        step_floor = (max(step_floor, focus_option['start'])
                      if step_floor else focus_option['start'])
    if step_floor and window_start > step_floor:
        prev_start = max(window_start - span, step_floor)
        observatory_prev_url = _range_url(prev_start, prev_start + span)
    # A custom range whose right edge is already current has nowhere to
    # step.  In particular, Now stamps ``cut=now``; offering another
    # server-computed range ending at the next request's ``now`` makes
    # that URL navigate forever.  The client uses the same one-minute
    # live-edge tolerance for track-now.
    if (window_key == 'custom'
            and (now - window_end).total_seconds() > 60):
        if window_end + span >= now:
            # Forward-to-present: restore the rolling named window when
            # one is in the ancestry; otherwise the same duration ending
            # now — Now never changes the span the user was reading.
            observatory_next_url = (f'?window={named_key}'
                                    if has_named_provenance
                                    else _range_url(now - span, now))
        else:
            observatory_next_url = _range_url(window_end, window_end + span)

    _et = _ZoneInfo('America/New_York')
    observatory_range_label = (
        f"{window_start.astimezone(_et).strftime('%m-%d %H:%M')}"
        f" – {window_end.astimezone(_et).strftime('%m-%d %H:%M')} ET")
    return render(request, 'snapper_ai/snapper.html', {
        'active_tab': 'report',
        'scope': scope,
        'scope_label': _scope_label(scope),
        'scope_options': _scope_options(
            scope, request.META.get('QUERY_STRING', ''),
            active_focus_label=(
                (focus_def.get('label') or 'Focus')
                if focus_option is not None else None)),
        'observatory': observatory,
        'observatory_window': window_key,
        'observatory_windows': list(WINDOW_HOURS),
        'observatory_default_window': DEFAULT_WINDOW,
        # A focus page lands with the slice already taken — half a
        # recording interval back from the window's end, on the latest
        # recorded state — so the click-for-details gesture is shown,
        # not discovered. An explicit ?cut= wins as ever; the literal
        # value 'now' means the live edge (the client enters track-now).
        'observatory_cut': (
            window_end.isoformat()
            if (request.GET.get('cut') or '').strip() == 'now'
            else (request.GET.get('cut') or '').strip()
            or (_focus_landing_cut(
                    scope, focus_option, focus_context['groups'],
                    observatory, window_start, window_end).isoformat()
                if focus_option is not None else '')),
        'observatory_prefs': user_prefs,
        'observatory_prev_url': observatory_prev_url,
        'observatory_next_url': observatory_next_url,
        'observatory_range_label': observatory_range_label,
        'observatory_groups': (
            focus_context['groups'] if focus_context else scope_groups),
        'observatory_default_off_ids': _view_default_off_ids(
            default_off_ids,
            focus_context['groups'] if focus_context else scope_groups,
            observatory.get('curves') or {}),
        'observatory_focus': focus_context,
        'health_url': _health_url(),
    })


def snapper_episode(request, scope, episode_id):
    """One episode's Time history: the observatory in activity mode,
    lanes from the episode's participants in birth order, the slice
    listing who was active at the cut (docs/EPISODES.md). Task
    participants parent their job lanes, collapsed by default."""
    from django.utils import timezone

    from .episodes import EpisodeNotFound, InvalidEpisode, episode_record
    from .series import DEFAULT_WINDOW

    scope = _validated_scope(scope)
    try:
        record = episode_record(scope, episode_id)
    except (EpisodeNotFound, InvalidEpisode):
        from django.http import Http404
        raise Http404(f'no episode {episode_id} in scope {scope}')

    now = timezone.now()
    started = record['started_at']
    ended = record['ended_at'] or now
    # The axis runs to the last participant death: the workload tail
    # beyond the run window is the fanout's story.
    deaths = [p['died_at'] for p in record['participants']
              if p.get('died_at')]
    axis_end = max([ended] + deaths)

    # Task lanes wear their site as the plain label, and worker lanes
    # wear their task's hue — color is meaning. Every participant —
    # agents, tasks, workers — holds a main-plot lane: the fanout is
    # the point of the view.
    task_site = {}
    job_task = {}
    for event in record['events']:
        payload = event.get('payload') or {}
        if event['kind'] == 'task_created' and payload.get('site'):
            task_site[event['participant']] = payload['site']
        if event['kind'] == 'job_created' and payload.get('jeditaskid'):
            job_task[event['participant']] = f"task-{payload['jeditaskid']}"

    def _value(participant):
        detail_status = ''
        for event in reversed(record['events']):
            if (event['participant'] == participant['id']
                    and (event.get('payload') or {}).get('status')):
                detail_status = str(event['payload']['status']).lower()
                break
        if detail_status in ('failed', 'error', 'terminated', 'warning'):
            return detail_status
        if detail_status in ('finished', 'done', 'completed'):
            return 'completed'
        return 'running'

    def _iso(value):
        return value.isoformat() if hasattr(value, 'isoformat') else value

    lanes = {}
    # The category axis stacks insertion order bottom-up; reversed
    # birth order puts the first participant at the top, the stack
    # building downward as lanes come into existence.
    ordered = sorted(
        record['participants'],
        key=lambda p: _iso(p.get('born_at')) or _iso(started),
        reverse=True)
    for participant in ordered:
        lane_id = f"p:{participant['id']}"
        born = participant.get('born_at') or started
        died = participant.get('died_at')
        label = participant.get('label') or participant['id']
        kind = participant.get('kind') or ''
        if kind == 'panda_task':
            site = task_site.get(participant['id'])
            label = f'{site} PanDA task' if site else 'PanDA task'
        elif kind == 'panda_job':
            label = label.replace('job ', 'worker ')
        elif kind:
            label = kind.replace('_', ' ') + ' agent'
        lane = {
            'label': label,
            'segments': [{
                't0': _iso(born),
                't1': _iso(died or axis_end),
                'value': _value(participant),
                'open_end': died is None,
                'key': participant['id'],
                'summary': kind,
                'hover': f"{label} · {kind}" if kind else label,
            }],
        }
        if participant['id'] in job_task:
            lane['hue_with'] = f"p:{job_task[participant['id']]}"
        lanes[lane_id] = lane

    observatory = {
        'lanes': lanes,
        'curves': {},
        'gaps': [],
        'start': _iso(started),
        'end': _iso(axis_end),
        'end_ms': int(axis_end.timestamp() * 1000),
        'snap_count': record['event_count'],
    }

    from zoneinfo import ZoneInfo as _ZoneInfo
    _et = _ZoneInfo('America/New_York')
    range_label = (
        f"{started.astimezone(_et).strftime('%m-%d %H:%M')}"
        f" – {axis_end.astimezone(_et).strftime('%m-%d %H:%M')} ET")

    midpoint = started + (axis_end - started) / 2
    return render(request, 'snapper_ai/snapper.html', {
        'active_tab': 'report',
        'scope': scope,
        'scope_label': _scope_label(scope),
        'scope_options': _scope_options(
            scope, request.META.get('QUERY_STRING', '')),
        'observatory': observatory,
        'observatory_window': 'custom',
        'observatory_windows': [],
        'observatory_default_window': DEFAULT_WINDOW,
        'observatory_cut': (
            axis_end.isoformat()
            if (request.GET.get('cut') or '').strip() == 'now'
            else (request.GET.get('cut') or '').strip()
            or midpoint.isoformat()),
        'observatory_prefs': {},
        'observatory_prev_url': None,
        'observatory_next_url': None,
        'observatory_range_label': range_label,
        'observatory_groups': [],
        'observatory_default_off_ids': [],
        'observatory_focus': None,
        'observatory_episode': True,
        'observatory_count_label': 'events',
        'observatory_activity_extra': f'&episode={record["episode_id"]}',
        'observatory_episode_title': (
            f"{record['label'] or record['episode_id']}"
            f" · {record['kind'] or 'episode'}"),
        'health_url': _health_url(),
    })


def snapper_snaps(request, scope, snap_id=None):
    """The snap record: recorded state of one snap (latest by default,
    any snap by id) with its components and audit documents, and the
    paginated snap history. The archival surface — the Time history is
    the operational one and links here from its header."""
    scope = _validated_scope(scope)
    snaps = SystemSnap.objects.filter(scope=scope).order_by('-snap_time')
    latest_snap = snaps.first()
    if snap_id is None:
        selected_snap = latest_snap
    else:
        selected_snap = get_object_or_404(snaps, id=snap_id)

    components = []
    observation_delay = None
    if selected_snap is not None:
        state = _dict(selected_snap.state)
        components = [
            _present_snap_component(name, payload, scope=scope,
                                    reference_time=selected_snap.snap_time)
            for name, payload in sorted(
                _dict(state.get('components')).items())
        ]
        observation_delay = (
            selected_snap.observed_at - selected_snap.snap_time
        ).total_seconds()

    from django.core.paginator import Paginator

    # The history table needs each snap's metadata, never its state:
    # a page of full state documents is tens of megabytes of JSONB for
    # a table of timestamps.
    paginator = Paginator(snaps.defer('state'), RECENT_SNAP_LIMIT)
    try:
        snap_page_number = max(int(request.GET.get('snap_page') or 1), 1)
    except ValueError:
        snap_page_number = 1
    snap_page = paginator.get_page(snap_page_number)
    recent = list(snap_page.object_list)
    pager_params = request.GET.copy()
    pager_params.pop('snap_page', None)
    pager_query = pager_params.urlencode()
    return render(request, 'snapper_ai/snapper.html', {
        'snap_page': snap_page,
        'snap_pager_query': f'{pager_query}&' if pager_query else '',
        'active_tab': 'snaps',
        'scope': scope,
        'scope_label': _scope_label(scope),
        'scope_options': _scope_options(scope),
        'selected_snap': selected_snap,
        'latest_snap': latest_snap,
        'observation_delay': observation_delay,
        'components': components,
        'selected_snap_json': (
            _json(selected_snap.state) if selected_snap is not None else ''),
        'snap_rows': [_snap_row(snap) for snap in recent],
        'snap_count': snaps.count(),
        'recent_snap_limit': RECENT_SNAP_LIMIT,
        'health_url': _health_url(),
    })


def _positive_int(config, key, default, minimum):
    raw = config.get(key, default)
    try:
        value = int(raw)
        if value < minimum:
            raise ValueError
    except (TypeError, ValueError):
        return raw, None
    return raw, value


def _duration(seconds):
    if seconds is None:
        return 'unavailable'
    minutes, remainder = divmod(seconds, 60)
    if minutes and remainder:
        return f'{minutes}m {remainder}s'
    if minutes:
        return f'{minutes}m'
    return f'{remainder}s'


def _component_registration(component):
    registration = _dict(component.registration)
    quantities = []
    for name, definition in sorted(
            _dict(registration.get('quantities')).items()):
        definition = _dict(definition)
        limits = []
        for key, label in (
                ('max_items', 'max items'),
                ('max_length', 'max length'),
                ('minimum', 'minimum'),
                ('maximum', 'maximum')):
            if key in definition:
                limits.append(f'{label}: {definition[key]}')
        if definition.get('enum'):
            limits.append('values: ' + ', '.join(
                str(value) for value in definition['enum']))
        quantities.append({
            'name': name,
            'path': definition.get('path', name),
            'kind': definition.get('kind', ''),
            'type': definition.get('type', ''),
            'required': bool(definition.get('required')),
            'limits': '; '.join(limits) or '—',
            'description': definition.get('description', ''),
        })
    event_sources = []
    for source in registration.get('event_sources') or []:
        source = _dict(source)
        event_sources.append({
            'name': source.get('name', ''),
            'kind': source.get('event_kind', ''),
            'resolver': source.get('resolver', ''),
            'owner': source.get('owner', ''),
            'visibility': source.get('visibility', ''),
        })
    return {
        'record': component,
        'title': registration.get('title') or component.name,
        'description': registration.get('description', ''),
        'owning_subsystem': registration.get('owning_subsystem', ''),
        'visibility': registration.get('visibility', ''),
        'assessment_policy': registration.get('assessment_policy', ''),
        'max_serialized_bytes': registration.get('max_serialized_bytes'),
        'quantities': quantities,
        'event_sources': event_sources,
        'registration_json': _json(registration),
    }


def snapper_system(request, scope):
    scope = _validated_scope(scope)
    opportunity_key = f'snapper_opportunity_seconds_{scope}'
    baseline_key = f'snapper_baseline_every_{scope}'
    policy_key = f'snapper_capture_policy_{scope}'
    config = {key: registry.config_get(key, default)
              for key, default in (
                  (opportunity_key, 10), (baseline_key, 10),
                  (policy_key, f'{scope}-v1'),
                  ('snapper_lock_timeout_ms', 5000))}
    opportunity_raw, opportunity = _positive_int(
        config, opportunity_key, 10, 10)
    baseline_raw, baseline = _positive_int(config, baseline_key, 10, 1)
    lock_raw, lock_timeout = _positive_int(
        config, 'snapper_lock_timeout_ms', 5000, 1)
    max_quiet = (
        opportunity * baseline
        if opportunity is not None and baseline is not None else None)

    cursor = (
        CaptureCursor.objects.select_related('latest_snap')
        .filter(scope=scope).first()
    )
    status_hook = registry.hook('scheduler_status')
    scheduler_status = status_hook(scope) if status_hook else None
    components = [
        _component_registration(component)
        for component in CurrentComponent.objects.filter(scope=scope)
        .order_by('-active', 'name')
    ]
    policy_rows = [
        {
            'setting': 'Snap opportunity',
            'value': f'{opportunity}s' if opportunity is not None else opportunity_raw,
            'key': opportunity_key,
            'valid': opportunity is not None,
        },
        {
            'setting': 'Periodic baseline',
            'value': (
                f'every {baseline} opportunities'
                if baseline is not None else baseline_raw),
            'key': baseline_key,
            'valid': baseline is not None,
        },
        {
            'setting': 'Maximum quiet interval',
            'value': _duration(max_quiet),
            'key': 'derived from opportunity × baseline',
            'valid': max_quiet is not None,
        },
        {
            'setting': 'Capture policy',
            'value': config.get(policy_key, f'{scope}-v1'),
            'key': policy_key,
            'valid': bool(config.get(policy_key, f'{scope}-v1')),
        },
        {
            'setting': 'Database lock timeout',
            'value': (
                f'{lock_timeout} ms' if lock_timeout is not None else lock_raw),
            'key': 'snapper_lock_timeout_ms',
            'valid': lock_timeout is not None,
        },
    ]
    return render(request, 'snapper_ai/snapper.html', {
        'active_tab': 'system',
        'scope': scope,
        'scope_label': _scope_label(scope),
        'scope_options': _scope_options(scope),
        'cursor': cursor,
        'scheduler_status': scheduler_status,
        'policy_rows': policy_rows,
        'components': components,
        'baseline_every': baseline,
        'health_url': _health_url(),
    })


# ── The cut: structured state at an instant ──────────────────────────────

def _cut_components(snap, previous_snap, scope, requested_at=None,
                    only=None, params=None, since_snap=None,
                    since=None):
    state = _dict(snap.state)
    previous_state = _dict(previous_snap.state) if previous_snap else {}
    provider = registry.get(scope)
    cards = []
    for name, payload in sorted(_dict(state.get('components')).items()):
        if only and name != only:
            continue
        payload = _dict(payload)
        data = _dict(payload.get('data'))
        previous_payload = _dict(
            _dict(previous_state.get('components')).get(name))
        previous_data = _dict(previous_payload.get('data'))
        card = {
            'name': name,
            'assessed_at': payload.get('assessed_at'),
            'changed': (payload.get('revision')
                        != previous_payload.get('revision')),
            'payload_json': _json(payload),
        }
        if name == 'health':
            overall = _dict(data.get('overall'))
            card['kind'] = 'health'
            card['chip'] = cut_chip(overall.get('status'))
            card['reason'] = overall.get('reason', '')
            card['counts'] = _dict(overall.get('counts'))
            card['non_ok_checks'] = [
                {'name': check_name, 'chip': cut_chip(check.get('status')),
                 'summary': check.get('summary', ''),
                 'category': check.get('category', '')}
                for check_name, check in sorted(
                    _dict(data.get('checks')).items())
                if str(check.get('status')) not in ('ok', 'healthy')
                for check in [_dict(check)]
            ]
        else:
            builder = (provider.component_cards.get(name)
                       if provider and provider.component_cards else None)
            if builder is not None:
                # The integration basis: the same component's data at
                # the ?since= instant, for cards reporting
                # window-relative counter differences.
                since_data = _dict(_dict(_dict(_dict(
                    (since_snap.state if since_snap else {})
                    or {}).get('components')).get(name)).get('data'))
                built = builder(data, previous_data,
                                {'scope': scope,
                                 'requested_at': requested_at,
                                 'params': params or {},
                                 'since': since,
                                 'since_data': since_data})
                if built is None:
                    continue
                card.update(built)
                if provider.card_template:
                    card.setdefault('template', provider.card_template)
            else:
                card['kind'] = 'generic'
        cards.append(card)
    return cards


def snapper_activity(request, scope):
    """One keyed episodic activity's detail card — the Time history's
    numbered-bar selection panel. The provider resolves the key to a
    card; the host card template renders the story."""
    import logging

    scope = _validated_scope(scope)
    provider = registry.get(scope)
    key = (request.GET.get('key') or '').strip()
    episode_id = (request.GET.get('episode') or '').strip()
    card = None
    error = ''
    if key and episode_id:
        # Episode participant cards are generic: the episode record is
        # self-describing, so no provider is involved.
        from .episodes import (EpisodeNotFound, InvalidEpisode,
                               episode_record)
        try:
            record = episode_record(scope, episode_id)
        except (EpisodeNotFound, InvalidEpisode) as e:
            record = None
            error = str(e)
        if record is not None:
            participant = next(
                (p for p in record['participants'] if p['id'] == key),
                None)
            if participant is None:
                error = 'no participant matches this key'
            else:
                events = [e for e in record['events']
                          if e['participant'] == key]
                card = {
                    'kind': 'episode_participant',
                    'template': 'snapper_ai/_snapper_episode_card.html',
                    'participant': participant,
                    'events': events[-40:],
                    'event_count': len(events),
                    'episode_id': record['episode_id'],
                }
        return render(request, 'snapper_ai/_snapper_activity.html',
                      {'card': card, 'error': error})
    if not key:
        error = 'key is required'
    elif provider is None or provider.activity_card is None:
        error = 'this scope has no activity detail provider'
    else:
        try:
            card = provider.activity_card(key)
        except Exception as e:                              # noqa: BLE001
            logging.getLogger(__name__).error(
                'activity card failed for %s %r: %s', scope, key, e)
            error = f'activity lookup failed: {e}'
        if card is None and not error:
            error = 'no recorded activity matches this key'
        if card is not None and provider.card_template:
            card.setdefault('template', provider.card_template)
    return render(request, 'snapper_ai/_snapper_activity.html',
                  {'card': card, 'error': error})


def snapper_cut(request, scope):
    """Server-rendered state cut: structured component cards at an
    instant, with deltas against the previous snap, exact-event context
    links, and the raw document one click behind (the Time history's
    selection panel; also the deep-link target for external dashboards)."""
    from django.utils.dateparse import parse_datetime

    from .queries import SnapNotFound, state_at

    scope = _validated_scope(scope)
    provider = registry.get(scope)
    requested = parse_datetime((request.GET.get('time') or '').strip())
    if requested is None or requested.tzinfo is None:
        return render(request, 'snapper_ai/_snapper_cut.html',
                      {'error': 'time must be ISO 8601 with timezone'})
    try:
        result = state_at(scope, requested)
    except SnapNotFound as e:
        return render(request, 'snapper_ai/_snapper_cut.html',
                      {'error': str(e)})
    snap = SystemSnap.objects.filter(id=result.snap_id).first()

    # ?component= narrows the cut to one component's card — the health
    # lane's pop-up detail uses this compact form. The narrowing gates
    # the WORK, not just the output: no reference scan, no other
    # component's card build. A component cut also resolves to the
    # latest snap CARRYING that component (e.g. a daily record's snap),
    # not merely the latest snap; the previous snap for deltas is the
    # previous one carrying it.
    component_filter = (request.GET.get('component') or '').strip()
    record_notice = None
    if component_filter and snap is not None and component_filter not in (
            (snap.state or {}).get('components') or {}):
        carrying = (SystemSnap.objects
                    .filter(scope=scope, snap_time__lte=result.requested_at,
                            state__components__has_key=component_filter)
                    .order_by('-snap_time').first())
        if carrying is not None:
            snap = carrying
        else:
            # No record of the component at or before this instant: the
            # cut says so and names where the record begins, instead of
            # an empty card slot that reads as "no detail exists".
            first = (SystemSnap.objects
                     .filter(scope=scope,
                             state__components__has_key=component_filter)
                     .order_by('snap_time').values('snap_time').first())
            record_notice = {
                'chip': cut_chip('unknown'),
                'component': component_filter,
                'first': first['snap_time'] if first else None,
                'first_iso': (first['snap_time'].isoformat()
                              if first else ''),
            }
            snap = None
    if component_filter and snap is not None:
        previous_snap = (
            SystemSnap.objects
            .filter(scope=scope, snap_time__lt=snap.snap_time,
                    state__components__has_key=component_filter)
            .order_by('-snap_time').first())
    else:
        previous_snap = (SystemSnap.objects
                         .filter(scope=scope,
                                 snap_time__lt=snap.snap_time)
                         .order_by('-snap_time').first()) if snap else None

    references = []
    if not component_filter:
        try:
            from .queries import context_around
            context = context_around(scope, requested, 3600).as_dict()
            references = context['references']
            if provider and provider.annotate_references is not None:
                references = provider.annotate_references(references)
        except Exception:                                    # noqa: BLE001
            pass  # references are enrichment; the cut renders without them

    # Attention economy: one absolute time, everything else relative to
    # it; coverage is mentioned only when it is NOT clean, in plain words.
    coverage = result.coverage.as_dict()
    coverage_notice = None
    if coverage.get('status') == 'gap':
        coverage_notice = {
            'chip': cut_chip('error'), 'label': 'recording gap',
            'detail': 'Capture was down at this instant — showing the last '
                      'state recorded before the outage; the state may have '
                      'changed unseen.'}
    elif coverage.get('status') != 'covered':
        coverage_notice = {
            'chip': cut_chip('warning'), 'label': 'coverage unknown',
            'detail': 'Whether capture was observing at this instant cannot '
                      'be established — showing the last recorded state.'}

    # The page's query travels to the card builders: a provider whose
    # card spans several records (e.g. campaigns) narrows to the
    # page's selection. ?since= names the integration basis — the
    # displayed window's left edge — and resolves to the latest snap
    # at or before it carrying the narrowed component.
    since = parse_datetime((request.GET.get('since') or '').strip())
    since_snap = None
    if since is not None and since.tzinfo is not None:
        basis_query = SystemSnap.objects.filter(
            scope=scope, snap_time__lte=since)
        if component_filter:
            basis_query = basis_query.filter(
                state__components__has_key=component_filter)
        since_snap = basis_query.order_by('-snap_time').first()
    cards = (_cut_components(snap, previous_snap, scope,
                             requested_at=result.requested_at,
                             only=component_filter or None,
                             params=request.GET,
                             since_snap=since_snap, since=since)
             if snap else [])
    for card in cards:
        assessed = parse_datetime(str(card.get('assessed_at') or ''))
        card['assessed_age_text'] = (
            _age_text((result.requested_at - assessed).total_seconds())
            if assessed and assessed.tzinfo else None)

    actual_snap_time = snap.snap_time if snap is not None else result.snap_time
    return render(request, 'snapper_ai/_snapper_cut.html', {
        'scope': scope,
        'requested_at': result.requested_at,
        'actual_snap_time': actual_snap_time,
        'snap_age_text': _age_text(
            (result.requested_at - actual_snap_time).total_seconds()),
        'coverage': coverage,
        'coverage_notice': coverage_notice,
        'record_notice': record_notice,
        'previous_age_text': (
            _age_text((snap.snap_time
                       - previous_snap.snap_time).total_seconds())
            if snap and previous_snap else None),
        'cards': cards,
        'references': references,
        'health_url': _health_url(),
        # Compact: a focus-narrowed card carries its own identity; the
        # instant/component chrome is dropped around it.
        'compact': (request.GET.get('compact') or '') == '1',
    })
