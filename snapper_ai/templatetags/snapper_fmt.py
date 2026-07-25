"""Display filters for the Snapper core templates.

Self-contained so the core renders in any host: times format as
Eastern wall time (the presentation timezone of the Snapper surfaces),
and state values map to ``<state>_fill`` CSS class names — colored by
the host's state stylesheet where one exists, harmlessly unstyled
where none does.
"""
from datetime import datetime, date
from zoneinfo import ZoneInfo

from django import template

register = template.Library()

_EASTERN = ZoneInfo('America/New_York')


@register.filter(name='fmt_dt')
def fmt_dt(value):
    """Format a datetime / ISO string as ``YYYYMMDD HH:MM:SS`` Eastern.

    Returns '' for falsy input and the original string when parsing
    fails (don't hide bad data).
    """
    if not value:
        return ''
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=_EASTERN)
        return value.astimezone(_EASTERN).strftime('%Y%m%d %H:%M:%S')
    if isinstance(value, date):
        return value.strftime('%Y%m%d')
    return str(value)


@register.filter(name='state_class')
def state_class(value):
    """Return the ``<state>_fill`` CSS class name for a state value."""
    if not value:
        return ''
    return f'{str(value).lower()}_fill'


@register.filter(name='state_label')
def state_label(value):
    """Render a state value as a human-friendly cell label.

    Underscores become spaces with title-casing; common acronyms keep
    their capitals (``csv_import`` renders as ``CSV Import``).
    """
    if not value:
        return ''
    upper_words = {'csv': 'CSV', 'mc': 'MC', 'id': 'ID', 'url': 'URL',
                   'api': 'API'}
    parts = str(value).replace('_', ' ').split()
    return ' '.join(upper_words.get(p.lower(), p.capitalize())
                    for p in parts)
