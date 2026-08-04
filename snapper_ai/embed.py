"""Embeddable curves-only Time history plot for host pages.

A host page embeds a compact, read-only rendering of one scope's
numeric curve families over a time window: build the context with
``embed_context`` and render it with the ``_snapper_embed.html``
partial. The embed carries no lanes, no controls, and no preferences;
a click anywhere on the plot opens the scope's full Time history with
the matching window. Colors are assigned over the scope's full curve
list, so a curve wears the same color here and on the report page.
"""

import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

# Bounded read: the series assembly loads every snap in the window, so
# embeds never reach past the observatory's own largest named window.
MAX_EMBED_DAYS = 30

# The embed has no zoom, so a curve needs no more points than the plot
# has pixels; beyond this cap the payload and render cost buy nothing.
MAX_POINTS_PER_CURVE = 500


def _downsample(points, cap=MAX_POINTS_PER_CURVE):
    """Bucketed min-max downsampling to at most ~cap points. Each
    bucket keeps its extreme-value points in time order, so the visual
    envelope — every spike — survives at any rendering width."""
    if len(points) <= cap:
        return points
    buckets = max(cap // 2 - 1, 1)
    size = len(points) / buckets
    out = [points[0]]
    for index in range(buckets):
        lo = int(index * size)
        hi = max(int((index + 1) * size), lo + 1)
        chunk = points[lo:hi]
        if not chunk:
            continue
        low = min(chunk, key=lambda p: p[1])
        high = max(chunk, key=lambda p: p[1])
        keep = [low] if low is high else sorted(
            [low, high], key=lambda p: p[0])
        for point in keep:
            if point is not out[-1]:
                out.append(point)
    if points[-1] is not out[-1]:
        out.append(points[-1])
    return out


def _family_matcher(group):
    prefixes = tuple(group.get('prefixes') or ())
    ids = set(group.get('ids') or ())

    def match(curve_id):
        return curve_id in ids or curve_id.startswith(prefixes)

    return match


def _report_query(start, end, now):
    """Query string for the report-page link: the named rolling window
    when the span matches one exactly and the window ends at now, the
    explicit range otherwise. Only the QUERY is stored: the path is
    resolved by the partial at render time ({% url %}), because a
    context built outside request context (cached-product background
    rebuilds) has no script prefix and reverse() there bakes a dead
    path."""
    from urllib.parse import urlencode

    from .series import WINDOW_HOURS

    span_hours = (end - start).total_seconds() / 3600.0
    named = next((key for key, hours in WINDOW_HOURS.items()
                  if abs(hours - span_hours) < 0.01), None)
    if named and abs((now - end).total_seconds()) < 300:
        return urlencode({'window': named})
    return urlencode({'start': start.isoformat(), 'end': end.isoformat()})


def embed_context(scope, start, end, families=(), lanes=False,
                  include_default_off=False):
    """Context for ``_snapper_embed.html``: the scope's curves filtered
    to the named ``families`` (provider ``curve_groups`` names, plotted
    as one panel each in the order given) over [start, end], clamped to
    the most recent MAX_EMBED_DAYS days. A curve joins the first listed
    family that matches it. ``lanes=True`` additionally includes the
    scope's episodic activity lanes (namespace bands), rendered above
    any curve panels. Members declared in a family's
    ``default_off_ids`` are omitted unless ``include_default_off`` is
    true. Errors return a context whose ``error`` the partial renders
    visibly."""
    from django.utils import timezone

    from . import registry
    from .series import observatory_series

    provider = registry.get(scope)
    if provider is None:
        return {'scope': scope,
                'error': f'unknown Snapper scope {scope!r}'}

    clamp_note = ''
    if end - start > timedelta(days=MAX_EMBED_DAYS):
        start = end - timedelta(days=MAX_EMBED_DAYS)
        clamp_note = (f'Showing the most recent {MAX_EMBED_DAYS} days '
                      'of recorded state.')

    series = observatory_series(scope, start, end)
    all_curve_ids = sorted(series['curves'])

    groups = {group.get('name'): group
              for group in registry.resolve_curve_groups(provider)}
    panels = []
    assigned = set()
    for name in families:
        group = groups.get(name)
        if group is None:
            return {'scope': scope,
                    'error': (f'scope {scope!r} has no curve family '
                              f'{name!r}')}
        match = _family_matcher(group)
        ids = [curve_id for curve_id in all_curve_ids
               if curve_id not in assigned and match(curve_id)]
        if not include_default_off:
            default_off_ids = set(group.get('default_off_ids') or ())
            ids = [curve_id for curve_id in ids
                   if curve_id not in default_off_ids]
        order = list(group.get('order') or ())
        if order:
            rank = {curve_id: i for i, curve_id in enumerate(order)}
            ids.sort(key=lambda cid: (rank.get(cid, len(order)), cid))
        assigned.update(ids)
        panels.append({'name': name, 'ids': ids})

    curves = {}
    for panel in panels:
        for curve_id in panel['ids']:
            curve = series['curves'][curve_id]
            curves[curve_id] = {'label': curve['label'],
                                'points': _downsample(curve['points'])}
    # Episodic lanes only (namespace bands): a lane with no activity in
    # the window earns no row, as on the report page.
    embed_lanes = {}
    if lanes:
        embed_lanes = {
            lane_id: lane for lane_id, lane in series['lanes'].items()
            if lane.get('segments')
        }
    colors = {}
    if provider.curve_color is not None:
        for curve_id in curves:
            try:
                color = provider.curve_color(curve_id)
            except Exception as e:                           # noqa: BLE001
                logger.error('snapper curve_color failed for %r: %s',
                             curve_id, e)
                break
            if color:
                colors[curve_id] = color
    return {
        'scope': scope,
        'label': provider.label or scope,
        'dom_id': f'snapper-embed-{scope}',
        'data_dom_id': f'snapper-embed-data-{scope}',
        'data': {
            'start': series['start'],
            'end': series['end'],
            'curves': curves,
            'all_curve_ids': all_curve_ids,
            'panels': panels,
            'lanes': embed_lanes,
            'gaps': series['gaps'],
            'colors': colors,
        },
        'report_query': _report_query(start, end, timezone.now()),
        'clamp_note': clamp_note,
        'has_points': (any(curve['points'] for curve in curves.values())
                       or bool(embed_lanes)),
        'error': '',
    }
