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

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ScopeProvider:
    """One scope's host-supplied presentation and extraction hooks.

    scope            URL identity of the scope (e.g. 'epicprod').
    label            Human label shown in the scope switcher.
    curve_values     (state_dict) -> {curve_id: number} for one snap.
    event_values     (state_dict) -> {curve_id: [events]} discrete
                     events recorded in one snap, each at its own event
                     time: an ISO stamp, a [stamp, qualifier] pair, or
                     a [stamp, qualifier, weight] triple. Families
                     declaring 'event_flow' bin these at render
                     (series.py): each bin carries the count with its
                     per-qualifier breakdown and, for weighted events,
                     the summed weight with its breakdown, so a family
                     plots either measure of the same events. Boundary
                     snaps contribute no events (their events precede
                     the window).
    series_transform (series_dict) -> series_dict after the one series
                     walk, for host-side folding derived from those curves.
    lane_entries     (state_dict) -> {lane_id: entry} extra continuous
                     lanes beyond the core health lanes.
    curve_label      (curve_id) -> label, or None to fall through to
                     the id itself.
    curve_color      (curve_id) -> CSS color, or None to take the
                     palette deal. For curves with semantic color —
                     state-bearing curves wear the host's state-color
                     vocabulary on every surface.
    curve_groups     Tuple of {'name', 'prefixes', 'ids'} dicts: the
                     curve family rows of the observatory legend. May
                     be a callable returning that tuple, resolved per
                     render so families can track live host state
                     (resolve with ``resolve_curve_groups``). A family
                     may declare 'order' (member display order),
                     'window_relative' (cumulative-counter curves
                     rendered relative to the window's left edge — the
                     displayed window is the integration range; True
                     for the whole family or a list of ids and
                     '_'-terminated prefixes within a mixed family),
                     'default_off_ids' (members that remain unticked
                     until the visitor explicitly enables them),
                     'tall' (double panel height), 'panel_px' (explicit
                     panel height), 'end_stamped' (stack values describe
                     the interval ending at their stamp),
                     'event_flow_bin_scale' (an event-flow family's
                     display bins are this many times the page's ladder
                     rung, so a sparse family draws as bars rather than
                     hairlines; the page takes the largest declared), and
                     'focus_closed' (section closed by default inside a
                     focus view).
    scope_curve_groups  Optional compact subset of curve_groups for the
                     unfocused scope report. When supplied, curves
                     outside these families stay on their dedicated
                     focus views instead of overloading the front door.
    scope_components Optional tuple of component names whose cards the
                     unfocused scope report's cut renders — the card
                     counterpart of scope_curve_groups. A component
                     with a dedicated focus view keeps its card there,
                     still reachable through a ?component= cut. Absent,
                     the cut renders every component in the snap.
    episodic_lanes   (start, end, dangle_seconds) -> {lane_name:
                     [segment, ...]} discrete activity lanes.
    activity_at      (instant) -> per-lane activity truth at an
                     instant, for card builders that must agree with
                     the lanes.
    activity_card    (key) -> card dict for one keyed episodic
                     activity (the Time history's numbered-bar detail
                     panel), or None when the key resolves to nothing.
    component_cards  {component_name: builder(data, previous_data,
                     ctx)} -> card dict including 'kind', or None to
                     omit the component from this cut. ctx carries
                     'scope' and 'requested_at' (None outside a cut).
    card_template    Host template rendering this scope's provider
                     cards; the core stamps it on each built card.
    cut_summaries    {component_name: builder(scope, requested_at,
                     since, data, previous_data)} -> the summary at a
                     cut as data (products.cut_summary): rows in panel
                     order with value, delta, window statistics, and
                     threshold marks, plus any basis text. The page's
                     card and the query share the builder.
    annotate_references  (references) -> annotated references with
                     host page links.
    """

    scope: str
    label: str
    curve_values: object = None
    event_values: object = None
    series_transform: object = None
    lane_entries: object = None
    curve_label: object = None
    curve_color: object = None
    curve_groups: tuple = ()
    scope_curve_groups: object = None
    scope_components: object = None
    episodic_lanes: object = None
    activity_at: object = None
    activity_card: object = None
    component_cards: dict = field(default_factory=dict)
    card_template: str = ''
    cut_summaries: dict = field(default_factory=dict)
    annotate_references: object = None
    # Preset tabs rendered after this scope in the scope switcher:
    # {'label', 'query'} dicts linking to the scope's report page with
    # the query string (e.g. a families= focused view). The host
    # supplies them; a callable is invoked at render time so presets
    # can track host state such as the producing campaigns.
    preset_links: object = ()
    # Focus views: scope-switcher tabs opening the report narrowed to
    # a host-defined selection. A declaration is a dict (or a callable
    # returning one): {'param', 'label', 'default', 'options':
    # [{'value', 'label', 'families': [...], 'component': name,
    # 'start': datetime|None}]}. 'default' names an option value or
    # 'all' (every option); the clean page restores the signed-in
    # user's last selection ahead of it. An option may declare an
    # 'activity' curve id (and the declaration an 'activity_label'):
    # with several options selected, presentation follows the peak of
    # that curve over the window, idle options last and closed, with a
    # jump list in the same order. This field accepts one declaration or
    # a tuple/list of them — each gets its own tab and its own clean
    # page at /<scope>/<label-lowercased>/. When the report request
    # carries ?<param>=<value>: only the option's families' curves and
    # control rows render, the window start clamps to the option's
    # start, the cut narrows to the option's component, and the
    # options render as a tab row. Optional keys: 'cache_series'
    # persists each option's families as a focus-sized product through
    # the series_cache hook; 'components' names the snap components the
    # focused record lives in, so the series build walks only those
    # snaps (valid because focus views keep no lanes or gap shading) —
    # see views.prewarm_focus_series for rebuilding these products when
    # the record changes.
    focus_view: object = None


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
    # series_cache(key, builder, refresh=False) -> {'value': series
    # dict or None, 'refreshing': bool}: the host serves its stored
    # copy immediately and rebuilds behind responses (its
    # cached-product mechanism); refresh=True rebuilds synchronously
    # (the prewarm path). A hook without the refresh parameter and a
    # legacy bare series dict are both accepted; None builds inline.
    'series_cache': None,
}


def register(provider):
    """Register a scope provider (host AppConfig.ready() territory)."""
    _REGISTRY[provider.scope] = provider


def resolve_curve_groups(provider):
    """A provider's curve families, resolving the callable form. A
    failing callable yields no families and logs — the page renders
    without them rather than erroring."""
    groups = provider.curve_groups if provider else ()
    if callable(groups):
        try:
            groups = groups()
        except Exception as e:                               # noqa: BLE001
            logger.error('snapper curve_groups callable failed for '
                         'scope %r: %s', provider.scope, e)
            groups = ()
    return groups or ()


def resolve_scope_curve_groups(provider):
    """The compact family projection for an unfocused scope report.
    Absent an explicit projection, the full curve registry remains the
    report vocabulary for backwards compatibility."""
    if provider is None or provider.scope_curve_groups is None:
        return resolve_curve_groups(provider)
    groups = provider.scope_curve_groups
    if callable(groups):
        try:
            groups = groups()
        except Exception as e:                               # noqa: BLE001
            logger.error('snapper scope_curve_groups callable failed for '
                         'scope %r: %s', provider.scope, e)
            groups = ()
    return groups or ()


def resolve_focus_views(provider):
    """A provider's focus views as a list. The field accepts one
    declaration or a tuple/list; each entry is a dict or a callable
    returning one. A failing or empty entry drops out and logs."""
    raw = provider.focus_view if provider else None
    if raw is None:
        return []
    entries = list(raw) if isinstance(raw, (list, tuple)) else [raw]
    views = []
    for entry in entries:
        try:
            entry = entry() if callable(entry) else entry
        except Exception as e:                               # noqa: BLE001
            logger.error('snapper focus view failed for scope %r: %s',
                         provider.scope, e)
            entry = None
        if entry:
            views.append(entry)
    return views


def group_matches(group, curve_id):
    """True when the curve belongs to this family: an exact id, or a
    declared prefix hit not claimed away by an exclude prefix. Exclude
    prefixes exist for prefix-colliding sibling families — one entity
    name extending another (SITE vs SITE_test) — where a bare prefix
    would swallow the longer sibling's curves."""
    cid = str(curve_id)
    if cid in (group.get('ids') or ()):
        return True
    prefixes = tuple(group.get('prefixes') or ())
    if not (prefixes and cid.startswith(prefixes)):
        return False
    excludes = tuple(group.get('exclude_prefixes') or ())
    return not (excludes and cid.startswith(excludes))


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
