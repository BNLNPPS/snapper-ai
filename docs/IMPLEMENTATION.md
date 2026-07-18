# snapper-ai implementation record

This document records durable implementation choices, their consequences, and
where they are realized. It complements the normative
[technical design](DESIGN.md) and the live [execution plan](PLAN.md).

Add or amend a decision in the same commit that changes the corresponding code
or integration contract. Do not erase superseded decisions: mark them
superseded and link the replacement so historical snaps remain interpretable.
Each decision records when it was accepted and the concrete code, contract, and
commits that implement or specify it.

## Current implementation map

### Generic package: snapper-ai

- `snapper_ai/models.py` owns the current component registry, immutable system
  snaps, and bounded capture cursor.
- `snapper_ai/services.py` owns registration, validation, canonicalization,
  publication, unchanged assessment, ownership checks, and revision semantics.
- `snapper_ai/capture.py` owns aligned capture decisions, scope serialization,
  coherent registry cuts, full-snap persistence, baseline behavior, and
  coverage-gap bookkeeping.
- `snapper_ai/queries.py` owns deterministic temporal retrieval and its typed
  evidence results. It currently implements `latest(scope)` and
  `state_at(scope, time)`, and
  `component_history(scope, component, start, end)`, and
  `changes_between(scope, start, end)`.
- `snapper_ai/migrations/0002_systemsnap_recovery_gap.py` makes recovered gap
  boundaries immutable and marks pre-existing recovery starts unknown.
- `DESIGN.md` is the generic semantic contract.

### Initial host: swf-monitor

- The package is installed as a Django application in the existing monitor
  runtime and uses its default swfdb PostgreSQL database.
- `monitor_app.snapper_health` publishes the bounded System-health component
  for both scopes.
- `monitor_app.snapper_datataking` publishes testbed datataking state by
  namespace from authoritative `RunState` and `WorkflowExecution` records.
- `monitor_app.snapper_panda` publishes the curated epicprod PanDA-activity
  component from the existing monitor query layer and lightweight aggregate
  database queries.
- The supervised schedulers capture testbed and epicprod; the full System
  status refresh maintains health and PanDA current state before capture.
- `SWF_EPICPROD_INTEGRATION.md` is the host-specific contract.

## Decisions

### D-001 — Generic Django application in the existing runtime

**Status:** accepted

**Date:** 2026-07-17

**Implemented in:** snapper-ai commit 1242e75, principally
`snapper_ai/models.py` and `snapper_ai/services.py`.

Snapper is a reusable Django application, not a separate service deployment.
The host supplies settings, authentication, routing, logging, migrations,
PostgreSQL, and process supervision. The generic package imports no SWF,
testbed, epicprod, or PanDA domain models.

**Consequence:** domain adapters stay in swf-monitor; the reusable package
contains only registry, capture, history, and temporal retrieval mechanics.

### D-002 — Owners curate and maintain current component state

**Status:** accepted

**Date:** 2026-07-16

**Implemented in:** snapper-ai commits 873c058 and 1242e75, principally
`docs/DESIGN.md` and `snapper_ai/services.py`.

Subsystem owners perform remote access, joins, aggregation, assessment, and
freshness evaluation before publication. Snapper copies bounded maintained
state and never probes domain systems during capture or a web request.

Every canonical change in the published projection is meaningful by owner
choice and advances the component revision. Identical publications refresh
provenance without advancing content history.

**Consequence:** component contracts must state the historical question,
resolution, bounds, owner, freshness, and publication trigger before coding.

### D-003 — Full coherent snaps first

**Status:** accepted for commissioning

**Date:** 2026-07-17

**Implemented in:** snapper-ai commits d23738e and 42c4ad6, principally
`snapper_ai/capture.py`.

Capture compares a small component revision vector at fixed aligned
opportunities. A component change, periodic baseline, manual request, or
coverage recovery produces a complete logical snap. Quiet opportunities stop
before JSON assembly.

The initial operating cadence is a 30-second opportunity with a five-minute
maximum quiet interval in both scopes. Storage remains full-only until measured
row size and change density justify delta reconstruction.

**Consequence:** retention, cadence changes, and delta encoding remain empirical
production decisions rather than prerequisites.

### D-004 — Health is an explicit assessed projection

**Status:** accepted and deployed; component schema v1

**Date:** 2026-07-17

**Implemented in:** swf-monitor commits 4e18901 and a3f9051, principally
`monitor_app/snapper_health.py`; contract in
`SWF_EPICPROD_INTEGRATION.md`.

The System-health component (internal name: health) is published for both
scopes from the bounded maintained System status registry after assessment.
Scope membership is explicit rather than inferred
from every status row, and the informational bot-usage check does not enter health
history. Included stale assessments are projected according to the declared
health policy rather than being re-evaluated during capture.

**Consequence:** health history records what the maintained assessment said at
the time, with policy and assessment provenance, while capture remains generic.

### D-005 — Testbed state is namespaced state evolution

**Status:** accepted and deployed; component schema v2

**Date:** 2026-07-18

**Implemented in:** swf-monitor commit 4db63c1, principally
`monitor_app/snapper_datataking.py`; snapper-ai commit ff8e174, principally
`README.md` and `SWF_EPICPROD_INTEGRATION.md`.

The testbed is a shared platform. Its datataking component therefore publishes
a bounded map of independently evolving namespace lanes, not a singleton latest
run. Namespaces are automatically discovered from linked
`WorkflowExecution.namespace` values; there is no configured name list.

Each lane carries the latest linked run identity, phase, state, substate, and
transition time. Genuine state transitions change the projection. Slice-counter
churn does not. Exact intermediate transitions remain in the authoritative
`SystemStateEvent` stream.

The component registration declares that event source and its stable resolver
identifier. Concrete REST/MCP resolver mapping is still pending.

**Consequence:** Snapper history supplies the sampled vertical cut through the
state model for every active namespace without replacing the exact event log.

### D-006 — PanDA history is aggregate operational state

**Status:** accepted and deployed; component schema v3

**Date:** 2026-07-18

**Implemented in:** swf-monitor commit df3ae18, principally
`monitor_app/snapper_panda.py`; snapper-ai commit 5092ad5, principally
`SWF_EPICPROD_INTEGRATION.md`.

The epicprod PanDA-activity component (internal name: panda) is maintained every
five minutes. It records:

- trailing 24-hour job counts by status and bounded target-site outcomes;
- every current in-flight job state, globally and by target site;
- current running jobs and allocated cores;
- trailing 24-hour task counts by status and processing type; and
- every current nonterminal JEDI task state, globally and by target site.

Terminal task states excluded from the current gauge are done, finished,
failed, broken, aborted, exhausted, and passed.

The site dimension means the job or task target site. Current production tasks
may be explicitly assigned at submission; the field must not be described as a
site chosen by brokerage without evidence.

Users, individual job and task identities, and other high-cardinality records
remain in PanDA and are available only through drill-down/event resolvers.
Counts are raw integers sampled at the five-minute maintainer resolution.

**Consequence:** the component exposes production backlog and evolution directly
while keeping Snapper bounded and leaving PanDA authoritative for records.

### D-007 — Schema evolution preserves honest old history

**Status:** accepted

**Date:** 2026-07-18

**Implemented in:** generic version and validation semantics in snapper-ai
commit 1242e75 (`snapper_ai/services.py`); compatible live upgrade ordering in
swf-monitor commit df3ae18 (`monitor_app/snapper_panda.py`).

Registration and component schema versions are explicit. Old snaps retain the
shape and policy that were true when captured. An additive contract upgrade may
publish an expanded payload under the previous compatible registration before
making new quantities required, all within one transaction.

**Consequence:** upgrades do not rewrite old snaps or create a moment in which
the current payload violates its authoritative registration.

### D-008 — Actual time and coverage are part of every temporal answer

**Status:** accepted; latest and state-at queries implemented

**Date:** 2026-07-16

**Specified in:** snapper-ai commit 3035970, principally `docs/DESIGN.md`.
`latest(scope)` and `state_at(scope, time)` are implemented in
`snapper_ai/queries.py`; range queries remain in Phase 4 of `PLAN.md`.

The state-at query returns the latest eligible logical state together with its actual
snap time. It does not pretend the state was observed at the requested time.
Known observer gaps produce explicit gap coverage rather than silently
carrying state across the gap. Incomplete historical evidence produces
unknown coverage.

Component history begins with state at the interval boundary and then recorded
changes. Exact transitions that collapse between aligned captures remain the
responsibility of registered authoritative event streams.

**Consequence:** REST, MCP, plots, and AI context must share these semantics and
surface assessment time, source time, schema/policy versions, and provenance.

### D-009 — AI consumes deterministic evidence; it does not enter capture

**Status:** accepted

**Date:** 2026-07-16

**Specified in:** snapper-ai commit 3035970, principally `README.md` and
`docs/DESIGN.md`; deterministic capture is implemented in `snapper_ai/capture.py`.

Capture and temporal retrieval are deterministic and AI-free. AI is a primary
consumer through the same query contract used by applications and people.
The context-around query may combine coherent state, nearby changes, and resolvable
event references, but it must preserve evidence times and availability.

**Consequence:** semantic interpretation, anomaly hypotheses, and narrative
generation sit above Snapper rather than altering recorded operational facts.

### D-010 — Temporal retrieval returns a typed evidence result

**Status:** accepted; generic base queries implemented

**Date:** 2026-07-18

**Implemented in:** `snapper_ai/queries.py`, with package-level database tests
in `snapper_ai/tests/test_queries.py`.

The generic Python service returns a frozen `StateQueryResult` envelope, not a
bare state dictionary. Its serialization includes the scope, requested time,
actual snap time, observation and completion times, snap identity, schema and
capture policy, encoding, state hash, applicable observer coverage, and a
complete copied state document.

Coverage has explicit covered, gap, and unknown states. For the latest query, it
describes the current capture cursor. For the state-at query, it is derived from exact
snap boundaries, the next immutable recovery record, or the current cursor at
the open end of history. A missing scope or eligible snap raises
`SnapNotFound`, and an encoding that cannot yet be reconstructed raises
`UnsupportedEncoding` rather than returning partial or misleading state.

**Consequence:** callers can consume latest state, point-in-time state,
component history, and changes without guessing evidence times or capture
health. REST and MCP may wrap these results for transport, but must preserve
their semantics. Delta reconstruction and exact external envelopes remain
later decisions.

### D-011 — Recovery gaps are immutable half-open intervals

**Status:** accepted and implemented in the package; deployment pending

**Date:** 2026-07-18

**Implemented in:** `snapper_ai/models.py`, `snapper_ai/capture.py`, migration
`0002_systemsnap_recovery_gap.py`, and package-level capture, migration, and
query tests.

A recovery snap stores the time at which the recovered gap started. Together
with its own snap time, this defines a half-open gap ending at the snap time.
The recovery boundary is covered because capture assembled a complete state at
that boundary. Database constraints prevent a known start from being marked
unknown and require every known start to precede its recovery snap.

Recovery snaps written before this field existed cannot recover their exact
start from immutable data. Migration 0002 marks their start as unknown; it does
not estimate or backfill a timestamp. The state-at query conservatively returns
unknown coverage between the preceding snap and such
a legacy recovery. A null evidence flag is also treated as unknown so a writer
from the preceding code version cannot create false continuity during a
coordinated upgrade.

**Consequence:** point-in-time answers distinguish known gaps, genuinely
covered intervals, legacy uncertainty, and times beyond the current observer
boundary without projecting the mutable cursor backward through history.

### D-012 — Component history begins with boundary state

**Status:** accepted and implemented in the package

**Date:** 2026-07-18

**Implemented in:** `snapper_ai/queries.py` and package-level query tests in
`snapper_ai/tests/test_queries.py`.

`component_history(scope, component, start, end)` returns a frozen result whose
first entry is the latest eligible state at the requested start. The entry
retains its actual snap time and represents absence explicitly rather than
dropping a component that had not yet appeared or had been retired.

Subsequent entries are classified as component changes, unchanged baselines,
or recoveries. Component identity includes its content hash, revision,
registration and schema versions, assessment policy, and publisher identity.
Callers may include unchanged baselines; by default they are suppressed.
Recovery entries are never suppressed, even when the component value is
unchanged. The result returns observer coverage at both requested endpoints,
while recovery entries expose gap evidence within the interval.

**Consequence:** component timelines start from a knowable boundary value and
remain honest about component absence and observer gaps without requiring every
periodic full snap to appear as a value change.

### D-013 — System changes are derived from adjacent complete snaps

**Status:** accepted and implemented in the package

**Date:** 2026-07-18

**Implemented in:** `snapper_ai/queries.py` and package-level query tests in
`snapper_ai/tests/test_queries.py`.

`changes_between(scope, start, end)` uses the latest eligible snap at the start
time as its comparison boundary and scans complete snaps in the half-open
interval after the start through the end. It
derives component changes from the before and after documents and their
identity vectors rather than accepting the recorded changed-components field as
the result. The
recorded vector remains in the response as provenance.

Every component difference is classified as added, changed, or removed
and carries previous and current documents, hashes, registration versions, and
revisions. Value-identical baselines are omitted. Recovery-only snaps remain as
coverage evidence, and snap-schema or capture-policy transitions remain as
policy changes even when component values are identical. The result also
returns its comparison boundary and observer coverage at both requested
endpoints.

**Consequence:** consumers receive reproducible value changes, explicit
appearance and disappearance, and the policy and observer evidence needed to
interpret the interval without treating metadata hints as authoritative data.

## Open implementation decisions

These require evidence or the next implementation tranche and are intentionally
not settled here:

- long-term cadence and retention;
- whether full-snap growth warrants component-delta encoding;
- exact REST and MCP transport envelopes for temporal queries;
- authorization and visibility projections for REST, MCP, and event resolvers;
- resolver selector and availability details for the System-health, datataking,
  and PanDA-activity components;
- ordering and contracts for the remaining component catalog; and
- whether query volume justifies derived indexes, caches, or rollups.
