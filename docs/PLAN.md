# snapper-ai plan

This is the authoritative execution plan and progress record for snapper-ai.
The technical contract lives in [DESIGN.md](DESIGN.md), and durable
implementation decisions live in [IMPLEMENTATION.md](IMPLEMENTATION.md).

Update this file in the same commit as any material change in scope, order, or
completion status. Keep completed steps in place so the path of the project
remains visible.

Status markers:

- [x] means complete for the stated item;
- [~] means current bounded work; and
- [ ] means not started.

## Current position

As of 2026-07-25, Phase 5 is complete and the package carries its own
UI. The report page opens as the Time history — state lanes and
measured-parameter curves on one Eastern-time axis with a click-driven
vertical cut, stacked per-family curve panels, window-step arrows
through the recorded history, and all view state in the URL. The four
base queries plus `context_around` are served through read-open SWF
REST and five MCP tools with the typed evidence envelopes intact, and
the three event resolvers map to authoritative services.

On 2026-07-25 the entire UI — views, series assembly, templates —
moved from the host into this package behind a provider registry
(`snapper_ai.registry`): hosts register scopes, curve vocabularies,
component cards, and service hooks, and the core stays
experiment-agnostic. The host integration guide is
[INTEGRATION.md](INTEGRATION.md); the display design is
[TIME_HISTORY_UI.md](TIME_HISTORY_UI.md).

The initial state-evolution components are live:

- **System health** for the testbed and epicprod scopes (component name:
  health);
- **Datataking state** for testbed (component name: datataking), with
  independent automatically discovered namespace
  lanes; and
- **PanDA activity** for epicprod (component name: panda), with current job and
  task states and target-site discrimination.

On 2026-07-29 the provider surface grew in place: curve families may
be supplied by a callable resolved per render, a provider may declare
several focus views (each with its own tab and clean page), curves may
carry provider-declared colors, and a family may declare its member
display order. The epicprod host used these for a Site focus view over
per-site job lifecycle curves.

The next work is section 8 — terminal-outcome counters and window
integrals — ahead of the remaining Phase 6 catalog items (operator
decision 2026-07-29).

## Ordered plan

### 1. Core registry, publication, and capture

- [x] Define component registration and owner-authorized publication.
- [x] Store bounded current component state with canonical hashes and revisions.
- [x] Capture coherent immutable full snaps at aligned opportunities.
- [x] Maintain per-scope capture cursors, heartbeat, baseline, failure, and
  coverage-gap state.
- [x] Deploy supervised testbed and epicprod capture at the initial
  30-second opportunity and five-minute maximum quiet interval.

### 2. Initial real state components

- [x] Publish assessed System health for both scopes.
- [x] Publish namespaced testbed datataking state evolution.
- [x] Register the datataking exact-transition source and its stable resolver
  identifier; concrete resolver mapping remains in Phase 5.
- [x] Publish epicprod PanDA job activity, including every current in-flight
  job state, running jobs and cores, and target-site maps.
- [x] Publish current nonterminal JEDI task states globally and by target site,
  plus trailing 24-hour task outcomes and processing types.
- [x] Keep users and individual job and task records outside Snapper history.

### 3. Bounded commissioning

- [x] Observe one representative active window, initially 24 hours and closed
  with a five-day production read.
- [x] Measure snap and no-change behavior by scope. Snap rates and recent reason
  distributions are recorded below; exact quiet and duplicate outcomes need not
  enter immutable snap history.
- [x] Measure each component's initial contribution to snap creation.
- [x] Measure canonical row size and capture/assembly behavior. Initial
  measurements and current state sizes are below. Lock wait remains bounded but
  is not separately retained; commissioning did not justify adding that
  instrumentation.
- [x] Confirm scheduler heartbeat and coverage-gap behavior throughout the
  window. Current cursors are healthy, immutable gap boundaries are deployed,
  and observed recoveries closed honestly.
- [x] Confirm that raw five-minute PanDA counts provide useful temporal
  resolution without unacceptable snap growth.
- [x] Record the initial findings here and make only evidence-driven
  corrections.

Commissioning is deliberately bounded. It is not a dashboard project and must
not delay temporal retrieval unless it uncovers a correctness problem.

#### Initial read — 2026-07-18 13:49 UTC

This read covers the first roughly 15 hours 46 minutes of operation, from
2026-07-17 21:59 UTC. It is an early baseline, not a substitute for closing the
representative 24-hour window.

| Scope | Snaps | Snaps/hour | State bytes mean / p95 / max | Assembly ms mean / p95 | Observation delay ms mean / p95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| epicprod | 251 | 15.9 | 1,878 / 3,210 / 3,720 | 0.028 / 0.041 | 7,107 / 11,458 |
| testbed | 247 | 15.7 | 1,560 / 2,202 / 2,208 | 0.033 / 0.048 | 7,014 / 11,391 |

The full snapper_system_snap relation, including its indexes, occupied
1,400,832 bytes. Change-bearing snaps attributed 48 changes to epicprod System
health, 8 to epicprod PanDA activity, 10 to testbed System health, and 2 to
testbed datataking state. Baselines dominated snap reasons: 206 for epicprod and
209 for testbed. The five-minute PanDA maintainer therefore contributes
bounded production detail without driving every aligned opportunity into a
snap in this initial window.

Both scope cursors were current, reporting a quiet latest opportunity, zero
consecutive failures, and no active coverage gap. Each scope nevertheless had
28 recovery-marked snaps. Those legacy snaps retain the recovery reason but
not the gap's start boundary. Migration 0002 marks their start explicitly
unknown rather than inventing continuity; new recovery snaps retain the exact
start. Exact no-change and lock-wait rates are also unavailable from retained
history; instrumentation should be added only if the completed commissioning
window shows that those measures are worth their operational cost.

#### Five-day read — 2026-07-22

This read covers approximately five days from the first snaps at
2026-07-17 21:59 UTC. epicprod had 1,532 snaps and testbed had 1,517, or
approximately 12.7 and 12.6 snaps per hour. The rate is close to the intended
five-minute continuity baseline because most five-minute PanDA changes coincide
with a baseline rather than creating additional snaps.

The latest complete canonical state documents were approximately 9.2 KiB for
epicprod and 4.2 KiB for testbed, well inside the registered 64 KiB per-component
bounds. In the latest 100 snaps, epicprod had 96 change-bearing snaps, while
testbed had 17 datataking changes. The raw five-minute PanDA projection therefore
provides useful temporal resolution without causing a snap-growth problem.

The durable action stream contained 2,741 successful material capture actions
and four errors. Three errors were bootstrap, policy-transition, or deployment
artifacts. One ordinary runtime capture timed out after 30 seconds on
2026-07-20; both scopes recovered successfully on the next poll. Four recent
recovery snaps per scope represented exact one-opportunity gaps and coincided
with supervised-worker process changes. No gap remained open.

The significant commissioning issue is outside snap persistence. The
supervised worker launched approximately 41,900 full Django capture subprocesses
and generated approximately 174,000 matching AppLog rows in five days. The
10-second poll invokes capture three times per configured 30-second opportunity,
so most executions are duplicates or quiet checks. Phase 5 must replace this
with one invocation at each aligned boundary and material-only durable logging.

### 4. Generic temporal query service

- [x] Implement `latest(scope)`.
- [x] Implement `state_at(scope, time)` with actual snap time and explicit
  observer-coverage status.
- [x] Implement `component_history(scope, component, start, end)`, beginning
  with state at the interval boundary and optionally suppressing unchanged
  baselines.
- [x] Implement `changes_between(scope, start, end)`.
- [x] Return component assessment/source times, schema and policy versions,
  provenance, hashes, and coverage state consistently.
- [x] Test quiet intervals, exact boundaries, schema evolution, and known
  coverage gaps.

### 5. Lean capture scheduling, retrieval, and event context

- [x] Invoke scheduled capture once at each configured aligned boundary; do not
  launch duplicate polling subprocesses inside the same opportunity.
  Deployed 2026-07-22 (swf-monitor dac9109): the worker sleeps to one
  second past each wall-clock opportunity multiple and invokes once.
- [x] Keep routine scheduled start, result, completion, duplicate, quiet, and
  child-bootstrap messages out of AppLog. Retain material captures, recoveries,
  failures, and manual requests. Deployed 2026-07-22 (swf-monitor
  dac9109); the optional periodic summary was not needed — the System
  page scheduler rows carry liveness.
- [x] Extend the UI beyond the latest 100 rows with temporal views. The
  report page opens as the Time history (2026-07-23, iterated under
  operator review): state lanes as horizontal bars with full-extent
  hover and run-start pips over stepped curves, remembered per-user
  curve and window state, double-click zoom, Eastern time throughout, a
  click-driven vertical cut rendering state_at with actual time and
  coverage plus a context link, and a paginated snap history table.
- [x] Expose the generic query service through thin SWF REST adapters with the
  same typed evidence envelopes. Deployed 2026-07-23 (swf-monitor 03b5fa6):
  `/api/snapper/<scope>/{latest,state-at,history,changes}/`, read-open per
  the monitor's read-surface convention rather than authenticated — the
  monitor gates writes and sensitive surfaces only.
- [x] Expose the same semantics through thin MCP tools. Deployed 2026-07-23
  (swf-monitor 03b5fa6): `snapper_latest`, `snapper_state_at`,
  `snapper_component_history`, `snapper_changes_between`, with docstrings
  that teach the evidence envelope and coverage honesty.
- [x] Map the stable health, datataking, and PanDA event resolver identifiers to
  authoritative services. 2026-07-23: `monitor_app.snapper_resolvers`
  maps swf-system-status-history to the new
  `/api/system-status/history/` read surface,
  swf-testbed-system-state-events to the system-state-events REST, and
  swf-panda-activity-history to the PanDA REST and MCP tools; an
  unmapped resolver stays unknown, never claimed available.
- [x] Implement `context_around` after the base queries and resolver mappings
  work end to end. 2026-07-23: generic `context_around(scope, time,
  window_seconds)` returns state at the instant, derived changes in the
  centered window, and event references from the registered
  declarations; the SWF REST and MCP transports attach resolver
  transports. Package query tests cover it.
- [x] Ensure AI-facing results preserve actual times, coverage, provenance, and
  event availability rather than presenting inferred continuity as fact.
  The typed envelopes flow unchanged through REST and MCP; tool
  docstrings instruct consumers on actual-time and gap honesty; context
  references carry availability from the resolver mapping.

### 6. Expand the component catalog individually

- [ ] Testbed workflow activity.
- [ ] Testbed agent status.
- [ ] Testbed data activity.
- [ ] Epicprod production activity.
- [ ] Epicprod operations activity.

Each component requires a historical question, owner, bounded projection,
resolution, freshness policy, size limit, visibility, publication trigger,
alarm behavior, and event resolver before implementation.

### 7. Production policy from evidence

- [ ] Set long-term cadence and retention from measured use and growth.
- [ ] Evaluate component-delta encoding only if full-snap measurements justify
  its reconstruction complexity.
- [ ] Define any long-term rollups separately from primary snap retention.
- [ ] Complete operating and recovery procedures and production acceptance.

### 8. Terminal-outcome counters and window integrals

Terminal job transitions are point events: a job leaves the in-flight
population at its end time, so terminal states have no instantaneous
population to record, and the trailing-24-hour outcome fields cannot be
composed into arbitrary-interval counts. This tranche records terminal
outcomes as monotonic cumulative counters and renders them relative to
the displayed window: the counters rise from zero at the window's left
edge, the zoom range is the integration range, the vertical cut reports
outcomes accumulated since the window start, and the same counters
answer numeric queries through the existing REST and MCP transports.
Drag remains zoom; no separate selection gesture is needed.

- [x] epicprod panda component version 5 (swf-monitor
  `snapper_panda.py`): cumulative terminal counters, scope-level and
  per-site, for finished, failed, cancelled, and closed jobs, plus a
  bounded per-site failed-by-class map (at most 16 classes from the
  monitor's error-component classification; the smallest classes roll
  into 'other'). Each publication counts completed jobs with end times
  after the previous publication's source time (active and archived
  tables, deduplicated) and adds them to the counters read from the
  component's current state. The counters are monotonic across
  restarts by construction, and the absolute origin is arbitrary
  because every consumer differences them. Update the registration and
  catch SWF_EPICPROD_INTEGRATION.md up to the deployed version 4
  contract before recording version 5.
- [x] Generic window-relative rendering: a curve family may declare
  `window_relative`; the series assembly rebases matched curves at the
  window's left boundary — each point becomes the sum of non-negative
  increments since the boundary snap, so a counter re-base never
  renders as a negative step. Labels carry the basis ("in window").
  Embedded panels inherit the transform. On a client zoom,
  window-relative curves subtract their value at the view's left edge,
  so the value at the view's right edge is the interval total.
- [x] Site families rework (swf-monitor provider): window-relative
  finished and failed curves replace the rolling 24-hour curves in the
  site jobs family, and a per-site failures family renders the
  failed-by-class counters as per-class curves so a failure burst is
  attributable by class on the timeline. Series cache version bump.
- [x] Site cut card legibility: on a site-focused cut the site section
  leads and the scope headline is dropped from the compact form.
  Reading order: outcomes since the window start (finished and failed
  totals, failure classes beneath the failed row, each row carrying
  its curve's swatch color), then in-flight counts in lifecycle order,
  then tasks. The card states the accumulation basis once. The cut
  request carries the window start so the card differences the
  counters server-side.
- [x] Transports: no new endpoints — `state_at` and `changes_between`
  already return the component, and differencing the version-5
  counters between two instants yields terminal counts per site and
  per failure class. Name the counters in the MCP tool docstrings so
  agent consumers find them.
- [x] Attribution beyond site (which task or processing type produced
  the outcomes) stays with the PanDA-database chart on the jobs page
  and the existing panda query tools; the component counters remain
  bounded to site, status, and failure class.
- [x] Document the display rule in TIME_HISTORY_UI.md and the
  2026-07-29 provider-surface additions (callable curve groups,
  multiple focus views, curve colors, member order, window-relative
  families) in INTEGRATION.md.
- [x] Live verification: the window-relative curves must agree with
  the jobs page's PanDA-database chart over the same window within the
  five-minute observation resolution; zoom rebase, cut basis, and
  embed behavior verified on the deployed pages.

### 9. Series and cut-summary products for AI clients

Views are for eyes; AI clients read the data. Today the two diverge one
step above the record: the page computes series products (curve
extraction, event binning, whole-series transforms such as rolling
ratios, window-relative re-basing) and the summary at a cut (each
plotted metric's value at the instant, its delta, and its minimum,
mean, and maximum over the window), while the five queries return the
component states beneath them. An AI asking how two metrics moved
together over a window has to walk component history and recompute
what the page already holds. This tranche exposes the page's products
as queries, in the same evidence envelope.

- [x] Generic `series_product(scope, focus, window, selection,
  selectors)` (`snapper_ai/products.py`, 2026-08-25): the focus view's
  series product as data — curves with their points and labels, the
  family declarations, coverage gaps, the window basis — resolved and
  built exactly as the page does, through the same cache, so the two
  never disagree.
- [x] Generic `cut_summary(scope, focus, time, since)`: the summary at
  a cut as data — one row per plotted metric in panel order with raw
  and formatted value, delta against the previous snap, window
  statistics, threshold marks — from a provider-registered builder
  (`ScopeProvider.cut_summaries`; the platform card's summary is the
  first), with the cut's actual snap time, coverage, and the
  component's provenance.
- [x] Transports in the swf host: REST `/api/snapper/<scope>/series/`
  and `/cut-summary/`, MCP `snapper_series` and `snapper_cut_summary`,
  with docstrings stating the window basis and the cache state.
- [ ] Correlation as a query, once the series product is a query:
  pairwise coefficients with lag over a window, declared per focus
  view (SNAPPER_PLATFORM.md, the summary at the cut), served to the
  page and to AI clients alike.

## Progress log

- **2026-09-06:** An event-flow family may declare
  `event_flow_bin_scale`, widening its display bins by that factor
  (5b21002); the epicprod host's Storage view strip uses it. Planned
  the weighted event form and the per-family bin measure selection
  (INTEGRATION.md: an event as [stamp, qualifier, weight], bins
  carrying count and weight, `measure_param` with `units_by_measure`
  and `title_by_measure`), the package side of the swf host's
  wasted-resources reading (swf-monitor SNAPPER_ERRORS.md, Wasted
  resources). No new curve ids: the count and weight of the same
  events ride one curve.
- **2026-07-29:** The provider surface grew in place (61ba2ad,
  60b74f3): `curve_groups` accepts a callable resolved per render, so
  families track live host state without an application restart;
  `focus_view` accepts several declarations, each with its own
  scope-switcher tab and clean page; `curve_color` gives state-bearing
  curves the host's state-color vocabulary on the report page and
  embeds alike; a family may declare its member display order; and a
  focus view whose families include no stacked group opens all of
  them. The epicprod host registered a Site focus view (per-site job
  lifecycle and task curves from the sites maps recorded in every
  snap) and embedded the site panels on its PanDA jobs page. Section 8
  was planned the same day and precedes the remaining Phase 6 items.
- **2026-07-25:** The UI moved into the package (snapper-ai c4868ed and
  the API polish that followed): views, series assembly, templates, URL
  routes, and self-contained template tags, behind the new
  `snapper_ai.registry` provider seam and `snapper_ai.presentation`
  public vocabulary. The swf host kept exactly the experiment-specific
  half (`monitor_app/snapper_providers.py`, host card template, service
  hooks). Same day, the report window gained step-arrows through the
  recorded history (arrows absent only at 'now' and the earliest snap)
  and the curve labels dropped redundant in-flight qualifiers.
- **2026-07-24:** Time history landing 2 under operator review
  (swf-monitor side): stacked per-family curve panels with independent
  y-scales and a shared crosshair; testbed namespace lanes as
  full-height idle tracks with discrete run-activity tiles derived from
  the run record; the drilldown contract (every entity reference a
  link, raw documents behind labeled audit foldouts); and repair of
  stale historical run/execution state uncovered by the display.
- **2026-07-23 (later):** Closed Phase 5. Generic `context_around` with
  event references and package tests; the SWF resolver mapping
  (`monitor_app.snapper_resolvers`) attaching concrete REST and MCP
  transports, with a new read surface for the health observation
  stream; a context REST endpoint, a fifth MCP tool, a context link on
  the Time history's vertical cut, and snap-table pagination. The Time
  history itself iterated through operator review to lanes-as-bars with
  run pips, remembered UI state, double-click zoom, and Eastern time on
  every surface.
- **2026-07-23:** Deployed the REST and MCP retrieval transports
  (swf-monitor 03b5fa6): four read-open REST endpoints and four MCP tools
  wrapping the generic queries, returning the typed evidence envelope
  unchanged and verified against live production snaps. REST follows the
  monitor's read-open convention for read surfaces. The same commit
  silenced the remaining routine log flood (the status-refresh stdout
  relay now logs only on failure). Remaining in Phase 5: the history UI
  (consultation pending), resolver mappings, and context_around.
- **2026-07-22 (later):** Deployed the lean scheduler and material-only
  logging (swf-monitor dac9109). The supervised worker invokes capture
  once, one second past each aligned opportunity boundary; routine
  invocation, quiet/duplicate result, success stderr, completion, and
  Django-bootstrap messages no longer enter AppLog. First minutes of
  operation recorded two durable rows, both material (a change-bearing
  capture and its completion relay), against roughly 340 in an equal
  window before the change; cursors heartbeat on the 30-second cadence
  with zero failures. Phase 5 continues with the retrieval tranche: UI,
  REST, MCP, resolver mappings, then context_around.
- **2026-07-22:** Closed bounded commissioning with a five-day production-product
  review. Both scopes were healthy with no open gap; full-snap growth and current
  document sizes remained modest; and five-minute PanDA observations provided
  useful change history without increasing the baseline snap rate materially.
  One non-bootstrap capture timeout recovered on the next poll. The review found
  approximately 41,900 capture subprocess launches and 174,000 matching AppLog
  rows, so Phase 5 now begins with aligned once-per-boundary scheduling and
  material-only logging, followed by UI, REST, and MCP retrieval. Component
  expansion remains blocked on completing that retrieval tranche.
- **2026-07-18:** Deployed the generic package through commit 385aeee and
  migration 0002 with the standard SWF deployment script from the coordinated
  swf-monitor v40 branch. The active host release is swf-monitor commit
  a9c0a7a. The production health check returned HTTP 200; both capture cursors
  were current with zero failures and no open gap at the 16:10 UTC audit. The
  deployed package exposes all four generic queries, but SWF REST, MCP, and
  exact-event resolver adapters remain Phase 5. The same release removed code
  styling from human-facing Snapper names and fields.
- **2026-07-18:** Implemented `changes_between(scope, start, end)`, completing
  the four generic base queries. It derives added, changed, and removed
  component values from adjacent complete snaps; omits value-identical
  baselines; and preserves recovery, snap-schema, and capture-policy
  transitions. Endpoint coverage bounds every interval. Twenty-two PostgreSQL
  tests now cover the Phase 4 query contract, including component registration
  and schema evolution. No SWF repository or deployment was touched.
- **2026-07-18:** Implemented
  `component_history(scope, component, start, end)` in the generic package.
  History begins with explicit boundary state, records absence and appearance,
  optionally suppresses semantically unchanged baselines, retains recovery
  evidence unconditionally, and returns coverage at both requested endpoints.
  The package suite now has 17 passing PostgreSQL tests. No SWF repository or
  deployment was touched.
- **2026-07-18:** Implemented immutable half-open recovery-gap intervals and
  `state_at(scope, time)` entirely in the generic package. Migration 0002
  marks existing recovery starts unknown and preserves exact starts for new
  snaps. Twelve package-level PostgreSQL tests cover capture, migration,
  latest, point-in-time selection, exact recovery boundaries, active gaps, and
  unchecked future times. Coordinated deployment was still pending at that
  point; the deployment is recorded in the latest entry above.
- **2026-07-18:** Recorded the initial 15-hour-46-minute commissioning read and
  implemented generic `latest(scope)` retrieval with actual snap time and
  current observer coverage. The read identified one prerequisite for
  `state_at`: persist immutable recovery-gap boundaries before making
  historical coverage claims.
- **2026-07-18:** Completed the bounded initial component tranche.
  testbed datataking is namespace-aware; epicprod PanDA schema v3 records
  all current in-flight job states and all current nonterminal task states by
  target site. The deployed capture path recorded the v3 component. Began the
  bounded commissioning phase; temporal queries were the next tranche and are
  recorded as complete in the later entries above.
