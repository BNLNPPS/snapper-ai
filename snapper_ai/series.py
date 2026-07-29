"""Observatory series assembly for the Snapper report page.

Experiment-agnostic extraction of plot series from recorded snaps:
numeric curves and categorical state lanes, plus recovery-gap spans.
Scope-specific extraction — which state fields become curves, how
curve ids read as labels, episodic activity lanes — is delegated to
the host-registered ScopeProvider (see registry.py). The core keeps
the generic evidence semantics: every point is a real snap at its
actual snap time, and known gaps are returned for display rather than
painted over. Health lanes are core: any scope's health component
follows the shared overall/checks shape.
"""

from django.utils.dateparse import parse_datetime

from . import registry
from .models import SystemSnap
from .presentation import component_data, et_naive

# The observatory plot draws every snap point; windows are bounded so
# assembly stays a bounded read (12-13 snaps/hour at current cadence).
WINDOW_HOURS = {'6h': 6, '24h': 24, '48h': 48, '7d': 168, '30d': 720}
DEFAULT_WINDOW = '24h'


def _iso(value):
    return value.isoformat().replace('+00:00', 'Z') if value else None


def _lane_entries(scope, state):
    """Continuous lane entries for one snap (health and its checks),
    keyed by lane id: the band value (drives color), hover text, and a
    dedup ``key``. Datataking namespaces are episodic, not continuous —
    they are assembled into discrete run periods by the series builder.
    """
    entries = {}
    health = component_data(state, 'health')
    overall = health.get('overall') or {}
    if overall:
        status = str(overall.get('status') or 'unknown')
        reason = str(overall.get('reason') or '').strip()
        counts = overall.get('counts') or {}
        hover = status if not reason else f'{status} — {reason}'
        count_bits = ', '.join(
            f'{k} {v}' for k, v in sorted(counts.items())
            if isinstance(v, int) and v and k != 'total')
        if count_bits:
            hover += f' ({count_bits})'
        entries['health'] = {'value': status, 'hover': hover,
                            'active': True, 'key': f'{status}|{reason}'}
    # Per-check sub-lanes behind the health lane's expandable header.
    # Every check is emitted here; the assembler drops the always-ok
    # ones so the expansion shows only checks with a story in the window.
    for check_name, check in sorted(
            (health.get('checks') or {}).items()):
        check = check if isinstance(check, dict) else {}
        status = str(check.get('status') or 'unknown')
        summary = str(check.get('summary') or '').strip()
        entries[f'check:{check_name}'] = {
            'value': status,
            'hover': f'{status} — {summary}' if summary else status,
            'active': True, 'key': f'{status}|{summary}',
            'parent': 'health'}
    return entries


def _curve_label(provider, curve_id):
    if provider is not None and provider.curve_label is not None:
        label = provider.curve_label(curve_id)
        if label:
            return label
    return curve_id


def observatory_series(scope, start, end):
    """Curves, lanes, and gap spans for one scope and window."""
    provider = registry.get(scope)

    rows = list(
        SystemSnap.objects
        .filter(scope=scope, snap_time__gte=start, snap_time__lte=end)
        .order_by('snap_time')
        .values('snap_time', 'state', 'recovered_gap_started_at',
                'recovered_gap_start_unknown', 'reasons'))
    boundary = (
        SystemSnap.objects
        .filter(scope=scope, snap_time__lt=start)
        .order_by('-snap_time')
        .values('snap_time', 'state')
        .first())

    dangle_seconds = 3600.0 * float(
        registry.config_get('snapper_lane_dangle_hours', 12))
    curves = {}
    lanes = {}
    gaps = []

    def add_curve_point(curve_id, time_iso, value):
        curve = curves.setdefault(
            curve_id, {'label': _curve_label(provider, curve_id),
                       'points': []})
        curve['points'].append([time_iso, value])

    def add_lane_point(lane_id, time_iso, entry):
        label = lane_id[6:] if lane_id.startswith('check:') else lane_id
        lane = lanes.setdefault(lane_id, {'label': label, 'points': []})
        if entry.get('parent'):
            lane['parent'] = entry['parent']
        points = lane['points']
        if points and points[-1].get('key') == entry['key']:
            return
        points.append({'t': time_iso, 'value': entry['value'],
                       'hover': entry['hover'], 'active': entry['active'],
                       'key': entry['key']})

    def state_curves(state):
        if provider is not None and provider.curve_values is not None:
            return provider.curve_values(state) or {}
        return {}

    def state_lanes(state):
        entries = _lane_entries(scope, state)
        if provider is not None and provider.lane_entries is not None:
            entries.update(provider.lane_entries(state) or {})
        return entries

    if boundary:
        start_naive = et_naive(start)
        for curve_id, value in state_curves(boundary['state']).items():
            add_curve_point(curve_id, start_naive, value)
        for lane_id, entry in state_lanes(boundary['state']).items():
            add_lane_point(lane_id, start_naive, entry)

    for row in rows:
        time_naive = et_naive(row['snap_time'])
        for curve_id, value in state_curves(row['state']).items():
            add_curve_point(curve_id, time_naive, value)
        for lane_id, entry in state_lanes(row['state']).items():
            add_lane_point(lane_id, time_naive, entry)
        if row['recovered_gap_started_at'] is not None:
            gaps.append([et_naive(row['recovered_gap_started_at']),
                         time_naive, 'gap'])
        elif row['recovered_gap_start_unknown']:
            gaps.append([None, time_naive, 'unknown start'])

    # A check sub-lane earns its place only with a non-ok story in the
    # window; an always-ok check would add a row and say nothing.
    for lane_id in [key for key, lane in lanes.items()
                    if lane.get('parent')
                    and all(point['value'] in ('ok', 'healthy')
                            for point in lane['points'])]:
        del lanes[lane_id]

    # Window-relative rendering: curves of a family declaring
    # window_relative rebase at the window's left edge — each point
    # becomes the sum of non-negative increments since the curve's
    # first point in range (the boundary snap when it carries the
    # curve), so a cumulative counter rises from zero at the window's
    # edge and a counter re-base never renders as a negative step.
    matchers = []
    for group in registry.resolve_curve_groups(provider):
        if not group.get('window_relative'):
            continue
        prefixes = tuple(group.get('prefixes') or ())
        ids = set(group.get('ids') or ())
        matchers.append(
            lambda cid, p=prefixes, i=ids:
                cid in i or bool(p and cid.startswith(p)))
    if matchers:
        for curve_id, curve in curves.items():
            if not any(match(curve_id) for match in matchers):
                continue
            total = 0
            previous = None
            rebased = []
            for time_iso, value in curve['points']:
                if previous is not None and value > previous:
                    total += value - previous
                previous = value
                rebased.append([time_iso, total])
            curve['points'] = rebased

    # Episodic activity lanes from the host's canonical activity
    # record: discrete activity with identity, over a grey idle track.
    if provider is not None and provider.episodic_lanes is not None:
        # Category axes place the first-inserted lane at the BOTTOM;
        # reverse-alpha insertion reads alphabetical top-down on the
        # plot, with the earlier-inserted health lanes beneath.
        for name, segments in sorted(
                provider.episodic_lanes(start, end,
                                        dangle_seconds).items(),
                reverse=True):
            lanes[f'ns:{name}'] = {'label': name, 'segments': segments}

    return {
        'scope': scope,
        # Plotted strings are Eastern wall time; end_ms is the true-UTC
        # anchor for converting a clicked plot position to an instant.
        'start': et_naive(start),
        'end': et_naive(end),
        'end_ms': int(end.timestamp() * 1000),
        'timezone': 'ET',
        'snap_count': len(rows),
        'curves': curves,
        'lanes': lanes,
        'gaps': gaps,
    }


def parse_window(request, now, default_window=DEFAULT_WINDOW):
    """(start, end, window_key) from ?window= or ?start=&end=.

    ``default_window`` lets a signed-in user's remembered preference
    stand in when the URL carries no window.
    """
    from datetime import timedelta

    raw_start = request.GET.get('start')
    raw_end = request.GET.get('end')
    if raw_start and raw_end:
        start = parse_datetime(raw_start)
        end = parse_datetime(raw_end)
        if start and end and start.tzinfo and end.tzinfo and start < end:
            return start, end, 'custom'
    if default_window not in WINDOW_HOURS:
        default_window = DEFAULT_WINDOW
    window = request.GET.get('window') or default_window
    hours = WINDOW_HOURS.get(window)
    if hours is None:
        window, hours = default_window, WINDOW_HOURS[default_window]
    return now - timedelta(hours=hours), now, window
