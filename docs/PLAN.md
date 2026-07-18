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

As of 2026-07-18, coherent capture is operating for testbed and epicprod.
The initial state-evolution components are live:

- **System health** for the testbed and epicprod scopes (component name:
  health);
- **Datataking state** for testbed (component name: datataking), with
  independent automatically discovered namespace
  lanes; and
- **PanDA activity** for epicprod (component name: panda), with current job and
  task states and target-site discrimination.

The first bounded commissioning read is recorded below. The four generic base
queries—latest, state at, component history, and changes between—are
implemented with actual times, provenance, schema/policy evolution, and honest
observer coverage. Deployment of the new migration and Phase 5 SWF adapters is
deferred until coordinated SWF work resumes. The remaining package-only work is
to close the bounded commissioning read; do not expand the component catalog
unless an operational need requires it.

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

- [~] Observe one representative active window, initially 24 hours.
- [~] Measure snap and no-change rates by scope. Initial snap rates are below;
  exact historical no-change outcomes are not currently retained.
- [x] Measure each component's initial contribution to snap creation.
- [~] Measure canonical row size, capture/assembly time, and lock time. Initial
  size and assembly measurements are below; lock wait is bounded but is not
  separately timed or retained.
- [~] Confirm scheduler heartbeat and coverage-gap behavior throughout the
  window. Current cursors are healthy; immutable gap boundaries are implemented
  in the package and await the next coordinated deployment.
- [ ] Inspect whether raw five-minute PanDA counts provide useful temporal
  resolution without unacceptable growth.
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

### 5. SWF REST, MCP, and event context

- [ ] Expose the generic query service through thin authenticated SWF REST
  adapters.
- [ ] Expose the same semantics through thin MCP tools.
- [ ] Map the stable health, datataking, and PanDA event resolver identifiers to
  authoritative services.
- [ ] Implement `context_around` after the base queries and resolver mappings
  work end to end.
- [ ] Ensure AI-facing results preserve actual times, coverage, provenance, and
  event availability rather than presenting inferred continuity as fact.

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
  unchecked future times. Coordinated deployment remains pending.
- **2026-07-18:** Recorded the initial 15-hour-46-minute commissioning read and
  implemented generic `latest(scope)` retrieval with actual snap time and
  current observer coverage. The read identified one prerequisite for
  `state_at`: persist immutable recovery-gap boundaries before making
  historical coverage claims.
- **2026-07-18:** Completed the bounded initial component tranche.
  testbed datataking is namespace-aware; epicprod PanDA schema v3 records
  all current in-flight job states and all current nonterminal task states by
  target site. The deployed capture path recorded the v3 component. Began the
  bounded commissioning phase; temporal queries are next.
