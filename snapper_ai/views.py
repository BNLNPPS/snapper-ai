"""Human-facing Snapper report and instrument views.

Experiment-agnostic: scopes, component card builders, curve families,
reference resolution, preferences, and configuration all arrive
through the host-registered providers and hooks (see registry.py).
The host includes ``snapper_ai.urls`` and provides a ``base.html``.
"""

import json

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from . import registry
from .models import CaptureCursor, CurrentComponent, SystemSnap
from .presentation import cut_chip, cut_delta


RECENT_SNAP_LIMIT = 100


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


def _scope_options(scope):
    return [
        {
            'name': name,
            'label': _scope_label(name),
            'active': name == scope,
        }
        for name in registry.scopes()
    ]


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
        card = builder(data, {}, {'scope': scope,
                                  'requested_at': reference_time})
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
               for key in ('curves_off', 'window', 'lanes_open')
               if key in payload}
    prefs_set(request.user.username, scope, allowed)
    return JsonResponse({'saved': True})


def snapper_report(request, scope, snap_id=None):
    from django.utils import timezone

    from .series import (DEFAULT_WINDOW, WINDOW_HOURS,
                         observatory_series, parse_window)

    scope = _validated_scope(scope)
    snaps = SystemSnap.objects.filter(scope=scope).order_by('-snap_time')
    latest_snap = snaps.first()

    user_prefs = _snapper_prefs(request, scope)
    now = timezone.now()
    window_start, window_end, window_key = parse_window(
        request, now,
        default_window=str(user_prefs.get('window') or DEFAULT_WINDOW))
    observatory = observatory_series(scope, window_start, window_end)

    # Window stepping: the arrows shift the whole window through the
    # recorded history, loading older or newer data server-side. No
    # arrow only at an edge — 'now' on the right, the earliest snap on
    # the left. The named window key rides along in the URL so stepping
    # forward to the present restores the rolling named window.
    from urllib.parse import urlencode as _urlencode
    from zoneinfo import ZoneInfo as _ZoneInfo
    earliest_snap = snaps.last()
    span = window_end - window_start
    named_key = request.GET.get('window') or ''
    if named_key not in WINDOW_HOURS:
        named_key = window_key if window_key in WINDOW_HOURS else DEFAULT_WINDOW

    def _range_url(start, end):
        return '?' + _urlencode({'start': start.isoformat(),
                                 'end': end.isoformat(),
                                 'window': named_key})

    observatory_prev_url = None
    observatory_next_url = None
    if earliest_snap and window_start > earliest_snap.snap_time:
        prev_start = max(window_start - span, earliest_snap.snap_time)
        observatory_prev_url = _range_url(prev_start, prev_start + span)
    if window_key == 'custom':
        if window_end + span >= now:
            observatory_next_url = f'?window={named_key}'
        else:
            observatory_next_url = _range_url(window_end, window_end + span)

    _et = _ZoneInfo('America/New_York')
    observatory_range_label = (
        f"{window_start.astimezone(_et).strftime('%m-%d %H:%M')}"
        f" – {window_end.astimezone(_et).strftime('%m-%d %H:%M')} ET")
    if snap_id is None:
        selected_snap = latest_snap
    else:
        selected_snap = get_object_or_404(snaps, id=snap_id)

    components = []
    observation_delay = None
    if selected_snap is not None:
        state = _dict(selected_snap.state)
        # Health is deliberately absent here: its detail pops up under
        # the Time history on a health-lane click, so an always-on
        # health card below would restate it.
        components = [
            _present_snap_component(name, payload, scope=scope,
                                    reference_time=selected_snap.snap_time)
            for name, payload in sorted(
                _dict(state.get('components')).items())
            if name != 'health'
        ]
        observation_delay = (
            selected_snap.observed_at - selected_snap.snap_time
        ).total_seconds()

    from django.core.paginator import Paginator

    paginator = Paginator(snaps, RECENT_SNAP_LIMIT)
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
        'active_tab': 'report',
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
        'observatory': observatory,
        'observatory_window': window_key,
        'observatory_windows': list(WINDOW_HOURS),
        'observatory_default_window': DEFAULT_WINDOW,
        'observatory_cut': (request.GET.get('cut') or '').strip(),
        'observatory_prefs': user_prefs,
        'observatory_prev_url': observatory_prev_url,
        'observatory_next_url': observatory_next_url,
        'observatory_range_label': observatory_range_label,
        'observatory_groups': list(
            (registry.get(scope).curve_groups or ())
            if registry.get(scope) else ()),
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

def _cut_components(snap, previous_snap, scope, requested_at=None):
    state = _dict(snap.state)
    previous_state = _dict(previous_snap.state) if previous_snap else {}
    provider = registry.get(scope)
    cards = []
    for name, payload in sorted(_dict(state.get('components')).items()):
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
                card.update(builder(data, previous_data,
                                    {'scope': scope,
                                     'requested_at': requested_at}))
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
    card = None
    error = ''
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
    previous_snap = (SystemSnap.objects
                     .filter(scope=scope, snap_time__lt=snap.snap_time)
                     .order_by('-snap_time').first()) if snap else None

    references = []
    try:
        from .queries import context_around
        context = context_around(scope, requested, 3600).as_dict()
        references = context['references']
        if provider and provider.annotate_references is not None:
            references = provider.annotate_references(references)
    except Exception:                                        # noqa: BLE001
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

    cards = (_cut_components(snap, previous_snap, scope,
                             requested_at=result.requested_at)
             if snap else [])
    # ?component= narrows the cut to one component's card — the health
    # lane's pop-up detail uses this compact form.
    component_filter = (request.GET.get('component') or '').strip()
    if component_filter:
        cards = [c for c in cards if c.get('name') == component_filter]
        references = []
    for card in cards:
        assessed = parse_datetime(str(card.get('assessed_at') or ''))
        card['assessed_age_text'] = (
            _age_text((result.requested_at - assessed).total_seconds())
            if assessed and assessed.tzinfo else None)

    return render(request, 'snapper_ai/_snapper_cut.html', {
        'scope': scope,
        'requested_at': result.requested_at,
        'actual_snap_time': result.snap_time,
        'snap_age_text': _age_text(
            (result.requested_at - result.snap_time).total_seconds()),
        'coverage': coverage,
        'coverage_notice': coverage_notice,
        'previous_age_text': (
            _age_text((snap.snap_time
                       - previous_snap.snap_time).total_seconds())
            if snap and previous_snap else None),
        'cards': cards,
        'references': references,
        'health_url': _health_url(),
    })
