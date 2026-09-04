# Integrating snapper-ai into a host application

snapper-ai is a self-contained Django application: models, capture,
temporal queries, and the full UI (report, system, and cut surfaces).
A host supplies four things — a database, a URL mount, a data feed, and
its presentation specifics by registration. This document is the
generic integration guide; the swf platform integration is the worked
example throughout (its contract is
[SWF_EPICPROD_INTEGRATION.md](SWF_EPICPROD_INTEGRATION.md), its
provider module `monitor_app/snapper_providers.py` in swf-monitor).

## 1. Install

```python
INSTALLED_APPS = [
    ...,
    'snapper_ai',
]
```

Run migrations. The package creates its snapper-prefixed tables on the
default connection; there is no second database or standalone service.

```python
# project urls.py
path('snapper/', include('snapper_ai.urls')),
```

Mount at the project level (route names live in the `snapper_ai`
namespace). The templates extend a `base.html` the host must provide —
any block-structured base with a `content` block works.

## 2. Feed it

Subsystem owners publish bounded current-state projections through
`snapper_ai.services` (`publish_component`,
`report_component_unchanged`), and a supervised scheduler invokes
`snapper_ai.capture` once per aligned boundary per scope. The semantic
contract — registration, curation, coherence, coverage — is
[DESIGN.md](DESIGN.md). In the swf host, the component maintainers are
`monitor_app.snapper_health`, `snapper_datataking`, and
`snapper_panda`, publishing after their authoritative refreshes.

With nothing else, the UI already works: scopes appear when registered
(step 3), curves are absent until a provider extracts them, and every
component renders as a generic quantity table with its audit document.

## 3. Register providers

Presentation specifics arrive through `snapper_ai.registry`, called
from the host's `AppConfig.ready()`:

```python
from snapper_ai.presentation import component_data, cut_chip, cut_delta
from snapper_ai.registry import ScopeProvider, register, register_hooks


def _curve_values(state):
    """Snap state -> {curve_id: number} for the observatory curves."""
    jobs = component_data(state, 'myjobs')
    return {'jobs_total': int(jobs.get('total') or 0)}


def _jobs_card(data, previous_data, ctx):
    """Component card: pure data; the core stamps card_template."""
    return {'kind': 'myjobs',
            'headline': [{'label': 'jobs', 'value': data.get('total'),
                          'delta': cut_delta(data.get('total'),
                                             previous_data.get('total'))}]}


def register_snapper_providers():
    register(ScopeProvider(
        scope='mysystem',
        label='My System',
        curve_values=_curve_values,
        curve_label=lambda cid: {'jobs_total': 'jobs total'}.get(cid),
        curve_groups=({'name': 'Jobs', 'prefixes': ['job_'],
                       'ids': ['jobs_total']},),
        component_cards={'myjobs': _jobs_card},
        card_template='myhost/_snapper_cards.html',
    ))
    register_hooks(
        prefs_get=...,        # (username, scope) -> dict
        prefs_set=...,        # (username, scope, dict)
        config_get=...,       # (key, default) -> value
        scheduler_status=...,  # (scope) -> row for the system tab
        health_url=...,        # () -> host health page URL
    )
```

Everything is optional. The fallbacks: an unregistered hook disables
its feature quietly (no remembered preferences, unlinked health rows,
default configuration values); a component without a card builder
renders as a quantity table; a curve id without a label labels itself.

Report URLs encode curve selection in two lists: `off=` names
default-on curves that are hidden, while `on=` names provider-declared
default-off curves that are explicitly included. Both lists override
remembered preferences and travel with window navigation.

The provider surface, in full (`snapper_ai/registry.py` is the
authority):

| Field | Role |
|---|---|
| `curve_values` | snap state → numeric curves for the Time history |
| `lane_entries` | extra continuous lanes beyond the core health lanes |
| `curve_label` | curve id → display label |
| `curve_color` | curve id → CSS color for curves with semantic color (state-bearing curves take the host's state vocabulary); the palette deal otherwise |
| `curve_groups` | curve family rows of the observatory legend; a callable is resolved per render so families track live host state. A family entry may declare `order` (member display order), `window_relative` (cumulative counters rendered relative to the window's left edge — `True` for the whole family, or a list of ids and `_`-terminated prefixes within a mixed family), `default_off` (the whole family starts unticked), `default_off_ids` (individual members stay unticked until explicitly enabled), `tall` (double panel height), `focus_closed` (section closed by default inside a focus view), and `fills` (a map of member id → hatch: `pattern`, `fgcolor`, `bgcolor`, `size`, `solidity` — a hatched area from zero to that member's curve, marking a member that is a subset of a sibling; the hatch distinguishes it from a stacked band, and filled members draw beneath their siblings' lines) |
| `scope_curve_groups` | compact subset of `curve_groups` for the unfocused scope report; curves outside these families stay on their focus views |
| `scope_components` | component names whose cards the unfocused scope report's cut renders, the card counterpart of `scope_curve_groups`; a component with a focus view keeps its card there, still reachable through a `?component=` cut. Absent, every component in the snap renders |
| `episodic_lanes` | discrete activity lanes from the host's own records |
| `activity_at` | instant → activity truth, for cards that must agree with the lanes |
| `activity_card` | keyed episodic activity → detail card |
| `component_cards` | component name → card builder (data, previous, ctx; ctx carries the page params and, when the cut names a basis, `since`/`since_data` for window-difference reporting) |
| `card_template` | host template rendering this scope's cards |
| `cut_summaries` | component name → summary builder (scope, requested_at, since, data, previous_data) returning the summary at a cut as data: rows in panel order with value, delta, window statistics, threshold marks. The page's card and the `products.cut_summary` query share it |
| `annotate_references` | event references → references with host links |
| `preset_links` | report-page tabs with fixed query strings |
| `focus_view` | one declaration or a tuple: scope-switcher tabs, each with its own clean page, options, selector axes, and an optional one-line `note` explaining the display. `label` names the page; optional `selector_label` names the selectable entities when those concepts differ. The focus parameter accepts `all` as a durable selection of every currently registered option, and a declaration may name `all` as its `default`. The clean page restores the signed-in user's last selection for the focus ahead of the default; the client does the same from local storage for a visitor not signed in. An option may declare an `activity` curve id (and the declaration an `activity_label`): with several options selected, presentation follows activity — options ordered by the peak of that curve over the shown window, idle options last in alphabetical order with their sections closed — and a jump list under the selector, in the same order with each peak in brackets, scrolls to an option's first section. An optional `member_restrict` hook — called with the request query, returning `None` or `{'note', 'keep', 'params', 'group_ids', 'group_titles'}` — narrows the plotted members per request (the cached series stays whole): curves failing the `keep` predicate drop, the `note` renders as the page's visible statement of the restriction, the `params` ride the cut fetch and window stepping so the restriction survives navigation, and `group_ids`/`group_titles` remap a family's exact-id membership and title for the request (an aggregate-based family substituting per-member curves under restriction — such a family declares the substitutes' prefixes as `extra_cache_prefixes`, captured in the cached focus series without joining the family's display). A family may also declare `empty_note`, rendered centered in its panel when its members hold points but no nonzero value in the window. |

Card builders return pure data with a `kind`; the host card template
renders the kinds it knows and carries whatever host page links belong
there. The shared chip, delta, and time vocabulary comes from
`snapper_ai.presentation` — host modules import only public names from
`presentation` and `registry`.

## 4. Embed curve panels on host pages

Any host page can carry a compact, read-only rendering of a scope's
curve families — the Time history's stacked panels without lanes,
controls, or preferences. Build the context in the host view and
render it with the shipped partial:

```python
from snapper_ai.embed import embed_context

context['snapper_embed'] = embed_context(
    'mysystem', start, end, families=('Jobs',))
```

```django
{% include 'snapper_ai/_snapper_embed.html' with embed=snapper_embed %}
```

`families` names entries of the provider's `curve_groups`, one panel
each in the order given. An entry may instead be an inline panel spec
— a dict carrying `title`, `prefixes` and/or `ids`, and optionally
`stacked` and `units` — a host-defined panel over the scope's curves
that adds nothing to the scope's declared family list; `lanes=True` additionally renders the scope's
episodic activity lanes (namespace bands with the report page's
hue-per-namespace, lightness-per-phase vocabulary) above any panels. The window is clamped to the most recent 30
days (`embed.MAX_EMBED_DAYS`) with a visible note, and each curve is
downsampled to at most `embed.MAX_POINTS_PER_CURVE` points by bucketed
min-max, which preserves the visual envelope in a display without
zoom. Members listed in `default_off_ids` are omitted; a host that
deliberately needs them in a read-only embed passes
`include_default_off=True`. A family declaring `stacked` renders as a
running-sum stack (the campaign-quilt form) and its key line states
the member count rather than a chip per member.
`hide_key=True` drops the static curve key above the plot, for a host
page that leaves curve identification to the hover readout.
`snap_components=('name', ...)` restricts the series walk to the
named components' snaps — a large cost reduction on busy scopes,
valid only when every listed family's curves live in those components
and `lanes` is off; the caller asserts that. Coverage gaps paint
as the same grey spans as the report page, and curve colors match the
report page (assigned over the scope's full curve list). A click
anywhere on the plot opens the scope's report page with the matching
window — the named rolling window when the span matches one exactly,
the explicit range otherwise. Errors, including an unknown scope or
family, render visibly in the partial. The swf host embeds the
epicprod jobs and tasks families on its PanDA activity page.

## 5. Own the transports you want

REST and MCP transports for the temporal queries are host territory by
design: the generic queries return typed evidence envelopes
(`snapper_ai.queries`), and the host wraps them under its own
authentication and URL conventions. The swf host serves them read-open
at `/api/snapper/<scope>/...` and as five MCP tools, preserving the
envelopes unchanged. The view products are queries too
(`snapper_ai.products`): `series_product(scope, focus, window,
selection, selectors)` returns a focus view's series exactly as the
page builds and caches it, and `cut_summary(scope, focus, time,
since)` returns the summary at a cut from the provider's registered
builder; the swf host serves them as `/series/` and `/cut-summary/`
and as two more MCP tools.

## Checklist

- [ ] `INSTALLED_APPS` + migrations
- [ ] `path('snapper/', include('snapper_ai.urls'))` and a `base.html`
- [ ] One or more component publishers and a supervised capture
      scheduler per scope
- [ ] One `ScopeProvider` registration per scope, hooks as wanted
- [ ] A host card template for any registered card kinds
- [ ] Optional REST/MCP wrappers over `snapper_ai.queries`
