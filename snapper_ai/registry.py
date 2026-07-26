"""Scope provider registry — the seam that keeps the Snapper core
experiment-agnostic.

The core (models, capture, queries, series assembly, views, templates)
never imports a host application's models or knows an experiment's
vocabulary. A host registers each scope it serves as a ScopeProvider:
how snap state maps to numeric curves, how curve ids read as labels and
group into families, how components render as cards, how episodic
activity lanes are built, and how event references resolve to host
pages. Host-wide services (user preferences, configuration values,
scheduler status) are registered once as hooks.

Everything is optional: an unregistered hook or provider field falls
back to generic behavior — unknown components render as quantity
tables, curve ids label themselves, preferences are not remembered.
A deployment outside the original host needs only: a ``base.html``
template, one ``register(ScopeProvider(...))`` call per scope, and a
data feed into ``snapper_ai.capture``.
"""

from dataclasses import dataclass, field


@dataclass
class ScopeProvider:
    """One scope's host-supplied presentation and extraction hooks.

    scope            URL identity of the scope (e.g. 'epicprod').
    label            Human label shown in the scope switcher.
    curve_values     (state_dict) -> {curve_id: number} for one snap.
    lane_entries     (state_dict) -> {lane_id: entry} extra continuous
                     lanes beyond the core health lanes.
    curve_label      (curve_id) -> label, or None to fall through to
                     the id itself.
    curve_groups     Tuple of {'name', 'prefixes', 'ids'} dicts: the
                     curve family rows of the observatory legend.
    episodic_lanes   (start, end, dangle_seconds) -> {lane_name:
                     [segment, ...]} discrete activity lanes.
    activity_at      (instant) -> per-lane activity truth at an
                     instant, for card builders that must agree with
                     the lanes.
    activity_card    (key) -> card dict for one keyed episodic
                     activity (the Time history's numbered-bar detail
                     panel), or None when the key resolves to nothing.
    component_cards  {component_name: builder(data, previous_data,
                     ctx)} -> card dict including 'kind'. ctx carries
                     'scope' and 'requested_at' (None outside a cut).
    card_template    Host template rendering this scope's provider
                     cards; the core stamps it on each built card.
    annotate_references  (references) -> annotated references with
                     host page links.
    """

    scope: str
    label: str
    curve_values: object = None
    lane_entries: object = None
    curve_label: object = None
    curve_groups: tuple = ()
    episodic_lanes: object = None
    activity_at: object = None
    activity_card: object = None
    component_cards: dict = field(default_factory=dict)
    card_template: str = ''
    annotate_references: object = None


_REGISTRY = {}
_HOOKS = {
    # prefs_get(username, scope) -> dict; prefs_set(username, scope, dict)
    'prefs_get': None,
    'prefs_set': None,
    # config_get(key, default) -> value (host configuration store)
    'config_get': None,
    # scheduler_status(scope) -> object rendered on the system tab
    'scheduler_status': None,
    # health_url() -> URL of the host's health/system page, linked from
    # health check rows; None leaves them unlinked
    'health_url': None,
}


def register(provider):
    """Register a scope provider (host AppConfig.ready() territory)."""
    _REGISTRY[provider.scope] = provider


def register_hooks(**hooks):
    """Register host-wide service hooks; unknown names are an error."""
    for name, value in hooks.items():
        if name not in _HOOKS:
            raise ValueError(f'unknown snapper hook {name!r}')
        _HOOKS[name] = value


def get(scope):
    return _REGISTRY.get(scope)


def scopes():
    """Registered scope names in registration order."""
    return list(_REGISTRY)


def hook(name):
    return _HOOKS.get(name)


def config_get(key, default=None):
    getter = _HOOKS.get('config_get')
    return getter(key, default) if getter else default
