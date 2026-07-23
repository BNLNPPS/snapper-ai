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

As of 2026-07-23, Phase 5 is complete. Capture runs once per aligned
boundary with material-only logging; the four base queries plus
`context_around` are served through read-open SWF REST and five MCP
tools with the typed evidence envelopes intact; the three event
resolvers map to authoritative services; and the report page opens as
the Time history — state lanes and measured-parameter curves on one
Eastern-time axis with a click-driven vertical cut. The display design and its remaining
landings are [TIME_HISTORY_UI.md](TIME_HISTORY_UI.md). The next work is
Phase 6: expanding the component catalog one contracted component at a
time (epicprod components keyed by campaign family).

The initial state-evolution components are live:

- **System health** for the testbed and epicprod scopes (component name:
  health);
- **Datataking state** for testbed (component name: datataking), with
  independent automatically discovered namespace
  lanes; and
- **PanDA activity** for epicprod (component name: panda), with current job and
  task states and target-site discrimination.

The initial and five-day commissioning reads are recorded below. The four
generic base queries—latest, state at, component history, and changes
between—are implemented with actual times, provenance, schema/policy evolution,
and honest observer coverage. The package through snapper-ai commit 385aeee and
migration 0002 are installed in the initial SWF host. The generic queries are
not yet exposed through SWF REST or MCP adapters.

Phase 5 is the current implementation tranche. First, the supervised worker
must invoke capture once at each configured aligned 30-second boundary instead
of launching a Django subprocess every 10 seconds, and routine start, result,
completion, duplicate, quiet, and child-bootstrap messages must stop entering
AppLog. Material captures, recoveries, failures, and manual requests remain
durable; a bounded periodic summary may be added if it proves useful. Then the
existing temporal query service must be exposed through a usable history UI,
REST, and MCP. This work crosses into swf-monitor and must be coordinated with
other work in the shared core repositories. Do not expand the component catalog
until this retrieval tranche is complete.

### Next-session bootstrap

As observed through the production products on 2026-07-22:

- epicprod had 1,532 snaps and testbed had 1,517, both beginning at
  2026-07-17 21:59:20 UTC;
- both capture cursors had fresh heartbeats, zero consecutive failures, and no
  open coverage gap;
- the latest complete state documents were approximately 9.2 KiB for epicprod
  and 4.2 KiB for testbed;
- the latest 100 epicprod snaps contained 96 change-bearing snaps, primarily
  the five-minute PanDA projection, while the latest 100 testbed snaps contained
  17 datataking changes;
- four recent one-opportunity recovery gaps in each scope were exact, closed,
  and coincident with supervised-worker process changes; and
- the production UI still exposes only the latest 100 snaps, and the installed
  generic temporal queries have no SWF REST or MCP transport adapters.

Before doing new work, verify these facts because branches and runtime state
can move. snapper-ai work stays on main. Any Phase 5 integration work belongs on
the current coordinated infra/baseline-vNN branch in swf-monitor, after checking
the shared checkout for another session's work. Use
[DEVELOPMENT.md](DEVELOPMENT.md) for the branch and deployment procedure.

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

## Progress log

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
