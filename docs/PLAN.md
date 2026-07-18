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

The immediate path is a bounded commissioning read, followed directly by the
generic temporal query service. Do not expand the testbed or production
component catalog before that retrieval layer exists unless an operational need
requires it.

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
- [ ] Measure snap and no-change rates by scope.
- [ ] Measure each component's contribution to snap creation.
- [ ] Measure canonical row size, capture/assembly time, and lock time.
- [ ] Confirm scheduler heartbeat and coverage-gap behavior throughout the
  window.
- [ ] Inspect whether raw five-minute PanDA counts provide useful temporal
  resolution without unacceptable growth.
- [ ] Record the findings here and make only evidence-driven corrections.

Commissioning is deliberately bounded. It is not a dashboard project and must
not delay temporal retrieval unless it uncovers a correctness problem.

### 4. Generic temporal query service

- [ ] Implement `latest(scope)`.
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

- **2026-07-18:** Completed the bounded initial component tranche.
  `testbed:datataking` is namespace-aware; `epicprod:panda` schema v3 records
  all current in-flight job states and all current nonterminal task states by
  target site. The deployed capture path recorded the v3 component. Began the
  bounded commissioning phase; temporal queries are next.
