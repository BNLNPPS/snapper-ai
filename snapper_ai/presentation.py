"""Public presentation vocabulary shared by the Snapper core and host
provider modules.

Host providers import from here — never underscore names from series
or views: times render as Eastern wall time for plotting, snap state
unwraps through component_data, and the cut's chip/delta vocabulary is
one set shared by core cards and provider cards.
"""

from zoneinfo import ZoneInfo

# All plotted time strings are Eastern wall time: Plotly renders date
# strings literally, and the surfaces present time in ET everywhere.
ET_ZONE = ZoneInfo('America/New_York')

# One state-color vocabulary, mirrored by the Time history plot
# (_snapper_observatory.html STATE_COLORS). Keep the two in step.
CUT_STATE_COLORS = {
    # Color cues: greens belong to health; events are blue.
    'ok': '#2e7d32', 'healthy': '#2e7d32', 'running': '#1565c0',
    'warning': '#f9a825', 'error': '#c62828', 'ended': '#78909c',
    'unknown': '#9e9e9e',
    # Datataking activity phases, matching the lane tile colors.
    'datataking': '#1565c0', 'processing': '#8ab6e8', 'idle': '#90a4ae',
}
CUT_FALLBACK_COLOR = '#1565c0'


def et_naive(value):
    """Eastern time string for plotting, WITH offset suffix: a naive
    string is parsed in the browser's local zone by Date.parse, shifting
    the strip by hours for any non-Eastern viewer (CT, UTC) and clipping
    the newest data off the axis."""
    if not value:
        return None
    return value.astimezone(ET_ZONE).isoformat(timespec='seconds')


def component_data(state, name):
    """One component's data dict out of a snap state document."""
    components = state.get('components') if isinstance(state, dict) else None
    payload = components.get(name) if isinstance(components, dict) else None
    data = payload.get('data') if isinstance(payload, dict) else None
    return data if isinstance(data, dict) else {}


def span_text(seconds):
    """Compact human duration for lane hovers."""
    if seconds >= 5400:
        return f'{seconds / 3600:.1f} h'
    if seconds >= 90:
        return f'{seconds / 60:.0f} min'
    return f'{seconds:.0f} s'


def cut_chip(value):
    """State chip: the value with its color from the shared vocabulary."""
    base = str(value or 'unknown').split('/')[0].lower()
    return {'value': str(value or 'unknown'),
            'color': CUT_STATE_COLORS.get(base, CUT_FALLBACK_COLOR)}


def cut_delta(current, previous):
    """Signed change string between two counts; None when absent/zero."""
    if current is None or previous is None:
        return None
    difference = int(current) - int(previous)
    if difference == 0:
        return None
    return f'+{difference}' if difference > 0 else str(difference)
