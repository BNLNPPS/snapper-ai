# snapper-ai plan

This is the authoritative execution plan and progress record for snapper-ai.
The technical contract lives in [DESIGN.md](DESIGN.md), and durable
implementation decisions live in [IMPLEMENTATION.md](IMPLEMENTATION.md).

Update this file in the same commit as any material change in scope, order, or
completion status. Keep completed steps in place so the path of the project
remains visible.

Status markers:

- `[x]` complete and operating;
- `[~]` current bounded work; and
- `[ ]` not started.

## Current position

As of 2026-07-18, coherent capture is operating for `testbed` and `epicprod`.
The initial state-evolution components are live:

- `testbed:health` and `epicprod:health`;
- `testbed:datataking`, with independent automatically discovered namespace
  lanes; and
- `epicprod:panda`, with current job and task states and target-site
  discrimination.

The first bounded commissioning read is recorded below, and `latest(scope)` is
implemented as the first generic temporal query. The next tranche is the
historical coverage correction required for honest `state_at(scope, time)`,
followed by that query itself. Do not expand the testbed or production component
catalog before the retrieval layer exists unless an operational need requires
it.

## Ordered plan

### 1. Core registry, publication, and capture

- [x] Define component registration and owner-authorized publication.
- [x] Store bounded current component state with canonical hashes and revisions.
- [x] Capture coherent immutable full snaps at aligned opportunities.
- [x] Maintain per-scope capture cursors, heartbeat, baseline, failure, and
  coverage-gap state.
- [x] Deploy supervised `testbed` and `epicprod` capture at the initial
  30-second opportunity and five-minute maximum quiet interval.

### 2. Initial real state components

- [x] Publish assessed `health` for both scopes.
- [x] Publish namespaced `testbed:datataking` state evolution.
- [x] Register the datataking exact-transition source and its stable resolver
  identifier; concrete resolver mapping remains in Phase 5.
- [x] Publish `epicprod:panda` job activity, including every current in-flight
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
  window. Current cursors are healthy; immutable gap boundaries need the
  correction identified below.
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
| `epicprod` | 251 | 15.9 | 1,878 / 3,210 / 3,720 | 0.028 / 0.041 | 7,107 / 11,458 |
| `testbed` | 247 | 15.7 | 1,560 / 2,202 / 2,208 | 0.033 / 0.048 | 7,014 / 11,391 |

The full `snapper_system_snap` relation, including its indexes, occupied
1,400,832 bytes. Change-bearing snaps attributed 48 changes to
`epicprod:health`, 8 to `epicprod:panda`, 10 to `testbed:health`, and 2 to
`testbed:datataking`. Baselines dominated snap reasons: 206 for `epicprod` and
209 for `testbed`. The five-minute PanDA maintainer therefore contributes
bounded production detail without driving every aligned opportunity into a
snap in this initial window.

Both scope cursors were current, reporting a quiet latest opportunity, zero
consecutive failures, and no active coverage gap. Each scope nevertheless had
28 recovery-marked snaps. A recovery snap retains the `recovery` reason, but the
immutable snap does not retain the gap's start boundary; the cursor clears that
boundary after recovery. This must be corrected before `state_at` can make
exact historical observer-coverage claims. Exact no-change and lock-wait rates
are also unavailable from retained history; instrumentation should be added
only if the completed commissioning window shows that those measures are worth
their operational cost.

### 4. Generic temporal query service

- [x] Implement `latest(scope)`.
- [ ] Implement `state_at(scope, time)` with actual snap time and explicit
  observer-coverage status.
- [ ] Implement `component_history(scope, component, start, end)`, beginning
  with state at the interval boundary and optionally suppressing unchanged
  baselines.
- [ ] Implement `changes_between(scope, start, end)`.
- [ ] Return component assessment/source times, schema and policy versions,
  provenance, hashes, and coverage state consistently.
- [ ] Test quiet intervals, exact boundaries, schema evolution, and known
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

- [ ] `testbed:workflows`.
- [ ] `testbed:agents`.
- [ ] `testbed:data`.
- [ ] `epicprod:production`.
- [ ] `epicprod:ops`.

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

- **2026-07-18:** Recorded the initial 15-hour-46-minute commissioning read and
  implemented generic `latest(scope)` retrieval with actual snap time and
  current observer coverage. The read identified one prerequisite for
  `state_at`: persist immutable recovery-gap boundaries before making
  historical coverage claims.
- **2026-07-18:** Completed the bounded initial component tranche.
  `testbed:datataking` is namespace-aware; `epicprod:panda` schema v3 records
  all current in-flight job states and all current nonterminal task states by
  target site. The deployed capture path recorded the v3 component. Began the
  bounded commissioning phase; temporal queries are next.
