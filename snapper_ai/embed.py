"""Embeddable curves-only Time history plot for host pages.

A host page embeds a compact, read-only rendering of one scope's
numeric curve families over a time window: build the context with
``embed_context`` and render it with the ``_snapper_embed.html``
partial. The embed carries no lanes, no controls, and no preferences;
a click anywhere on the plot opens the scope's full Time history with
the matching window. Colors are assigned over the scope's full curve
list, so a curve wears the same color here and on the report page.
"""

from datetime import timedelta

# Bounded read: the series assembly loads every snap in the window, so
# embeds never reach past the observatory's own largest named window.
MAX_EMBED_DAYS = 30


def _family_matcher(group):
    prefixes = tuple(group.get('prefixes') or ())
    ids = set(group.get('ids') or ())

    def match(curve_id):
        return curve_id in ids or curve_id.startswith(prefixes)

    return match


def _report_url(scope, start, end, now):
    """The report-page target: the named rolling window when the span
    matches one exactly and the window ends at now, the explicit range
    otherwise."""
    from urllib.parse import urlencode

    from django.urls import reverse

    from .series import WINDOW_HOURS

    url = reverse('snapper_ai:snapper_report', kwargs={'scope': scope})
    span_hours = (end - start).total_seconds() / 3600.0
    named = next((key for key, hours in WINDOW_HOURS.items()
                  if abs(hours - span_hours) < 0.01), None)
    if named and abs((now - end).total_seconds()) < 300:
        return f'{url}?{urlencode({"window": named})}'
    return f'{url}?{urlencode({"start": start.isoformat(), "end": end.isoformat()})}'


def embed_context(scope, start, end, families):
    """Context for ``_snapper_embed.html``: the scope's curves filtered
    to the named ``families`` (provider ``curve_groups`` names, plotted
    as one panel each in the order given) over [start, end], clamped to
    the most recent MAX_EMBED_DAYS days. A curve joins the first listed
    family that matches it. Errors return a context whose ``error`` the
    partial renders visibly."""
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
              for group in (provider.curve_groups or ())}
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
        assigned.update(ids)
        panels.append({'name': name, 'ids': ids})

    curves = {curve_id: series['curves'][curve_id]
              for panel in panels for curve_id in panel['ids']}
    report_url = _report_url(scope, start, end, timezone.now())
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
            'gaps': series['gaps'],
            'report_url': report_url,
        },
        'report_url': report_url,
        'clamp_note': clamp_note,
        'has_points': any(curve['points'] for curve in curves.values()),
        'error': '',
    }
