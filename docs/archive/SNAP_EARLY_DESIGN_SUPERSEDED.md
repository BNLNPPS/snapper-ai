# Snapper: System Snaps

A system snap is the recorded global state of a scoped system, such as the
streaming workflow testbed or the epicprod production system, at an aligned
timestamp. A fixed clock boundary triggers a check for whether a snap is due.
The check does not assemble or persist state when no snap is due.

**Snapper** aggregates the subsystems' maintained nows into system snapshots
and records their history. The name describes its operation and follows the
animal-oriented service naming used by PanDA and Canary.

```text
subsystems maintain their nows
            ↓
Snapper aggregates the nows
            ↓
snap history
```

Each subsystem continuously owns and maintains its present **now**. When that
now changes in a way the subsystem considers snap-significant, the subsystem
publishes its complete replacement component projection. That publication is
the change trigger for Snapper; Snapper never asks the subsystem to reconstruct
its now at a snap boundary.

The snap series complements the event streams the platform already records
(messages, the action stream, and status history). Events carry exact
transition times; snaps carry aligned system-wide state. Any two snaps can
be compared to determine what changed, and every subsystem joins at a
common timestamp. This realizes the sampled history of the global state
defined in the
[E0-E1 state machine](https://github.com/BNLNPPS/swf-testbed/blob/infra/baseline-v39/docs/e0-e1-state-machine.md):
a recorded vertical cut through the system's concurrent components.

Snaps sample asynchronous services. State changes between snaps are
carried by the event streams, and a snap is the maintained current state
composed at its aligned boundary. The design follows the System status boundary
rule ([SYSTEM_STATUS.md](SYSTEM_STATUS.md)): an agent-driven writer produces
rows, the web tier and every other consumer read rows, and nothing probes
services in a request path. Snapper also performs no probes or expensive
derivation; subsystem maintainers do that work ahead of time.

## Design basis

System snaps combine established ideas from time-series monitoring, process
historians, and event-sourced systems. None of those systems is the complete
model, but each establishes a useful constraint.

- [RRDtool](https://www.rrdtool.org/rrdtool/doc/rrdcreate.en.html) separates
  the fixed `step` used for aligned primary data points from sample arrival
  times. Its `heartbeat` places a limit on how long values remain known when
  samples stop. System snaps use the same separation: clock boundaries define
  aligned opportunities, snap persistence can be sparse, and state must not
  be carried across a known observer gap.
- [Prometheus](https://prometheus.io/docs/prometheus/latest/configuration/configuration/)
  uses fixed scrape intervals while
  [query evaluation](https://prometheus.io/docs/prometheus/latest/querying/basics/)
  selects the newest eligible sample for each requested timestamp. Its
  staleness rules prevent indefinite last-value carry-forward. System snaps
  likewise provide an aligned query view over stored observations and require
  explicit assessed liveness and unknown-state semantics.
- [FactoryTalk Historian compression](https://www.rockwellautomation.com/en-hu/docs/factorytalk-historian-machine-edition/7-102/fthme-help-series-c-ie-ditamap/collect-and-store-data/filter-data/compression-filtering.html)
  evaluates observations before archival, preserves significant changes, and
  uses a maximum archive interval so an unchanged point is still recorded
  periodically. It also treats every change to a digital value as significant.
  This is the closest storage model for snaps: state changes produce snaps,
  unchanged intervals are represented sparsely, and periodic full snaps bound
  the quiet interval.
- The
  [Event Sourcing pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing)
  treats event streams as the exact history and snapshots as serialized state
  at selected positions in that history. Existing SWF event streams retain
  transition timing and intent; system snaps provide the query-optimized
  system-wide state. Snaps supplement those event streams rather than replace
  them.

These precedents lead to the following design rules:

1. Clock alignment and archival frequency are separate concerns.
2. Every canonical component-content change published by its owner makes a snap
   due.
3. A maximum quiet interval produces periodic full snaps.
4. Last-snap carry-forward is valid only while scheduler coverage is known.
5. Retention preserves complete full-plus-delta sequences; long-term reduction
   uses separate rollups.
6. Each subsystem continuously maintains its own bounded present-state
   projection. Snapper copies those projections; it does not derive component
   state.
7. Every snap quantity is registered with a stable key, value contract, owner,
   and interpretation metadata before it can be published.
8. Assessed health, staleness, ages, rates, and rolling-window values belong in
   the maintained projection when they are operationally useful. They carry
   assessment time and policy provenance and are not recomputed by historical
   readers.
9. Consumers use actual record timestamps and database ordering. They do not
   infer or depend on the cadence that produced the records.

## The snap record

The external representation is one versioned JSON document. Relational
columns hold the snap envelope; the `state` JSONB column holds the
`components` map. The API combines them into this representation:

For readability, the examples show each component's registration version but
omit its repeated `registration` definition body. Stored full components carry
that complete registration metadata.

```json
{
  "v": 1,
  "scope": "testbed",
  "snap_time": "2026-07-16T18:30:00Z",
  "observed_at": "2026-07-16T18:30:00.084Z",
  "encoding": "full",
  "reasons": ["change"],
  "changed_components": ["datataking", "data"],
  "components": {
    "datataking": {
      "v": 1,
      "registration_version": 2,
      "revision": 1842,
      "assessed_at": "2026-07-16T18:29:59.920Z",
      "data": {"state": "run", "substate": "physics", "run_number": 100123}
    },
    "workflows": {
      "v": 1,
      "registration_version": 4,
      "revision": 927,
      "assessed_at": "2026-07-16T18:29:59.760Z",
      "data": {
        "active_by_status": {"running": 2},
        "completed_total": 18430,
        "failed_total": 42
      }
    },
    "agents": {
      "v": 1,
      "registration_version": 3,
      "revision": 3315,
      "assessed_at": "2026-07-16T18:29:59.510Z",
      "data": {
        "instances": {
          "daqsim-default": {
            "type": "daqsim",
            "status": "ok",
            "operational_state": "ready",
            "heartbeat_age_seconds": 1.3,
            "last_heartbeat_at": "2026-07-16T18:29:58.210Z"
          },
          "data-default": {
            "type": "data",
            "status": "ok",
            "operational_state": "processing",
            "heartbeat_age_seconds": 1.7,
            "last_heartbeat_at": "2026-07-16T18:29:57.804Z"
          }
        }
      }
    },
    "data": {
      "v": 1,
      "registration_version": 5,
      "revision": 22418,
      "assessed_at": "2026-07-16T18:29:59.880Z",
      "data": {
        "stf_files": 15234,
        "tf_slices": 88210,
        "slices_by_status": {"queued": 40, "processing": 12, "completed": 88158}
      }
    },
    "messages": {
      "v": 1,
      "registration_version": 1,
      "revision": 41902,
      "assessed_at": "2026-07-16T18:29:59.920Z",
      "data": {"sent_total": 41902, "last_sent_at": "2026-07-16T18:29:59.401Z"}
    }
  }
}
```

```json
{
  "v": 1,
  "scope": "epicprod",
  "snap_time": "2026-07-16T18:30:00Z",
  "observed_at": "2026-07-16T18:30:00.103Z",
  "encoding": "full",
  "reasons": ["change"],
  "changed_components": ["campaigns", "panda"],
  "components": {
    "campaigns": {
      "v": 1,
      "registration_version": 3,
      "revision": 612,
      "assessed_at": "2026-07-16T18:29:59.840Z",
      "data": {
        "current": ["26.06"],
        "tasks_by_status": {"draft": 3, "ready": 1, "submitted": 4, "completed": 121, "failed": 1}
      }
    },
    "panda": {
      "v": 1,
      "registration_version": 6,
      "revision": 4810,
      "assessed_at": "2026-07-16T18:29:48Z",
      "source_as_of": "2026-07-16T18:29:41Z",
      "data": {
        "jobs_by_state": {"running": 250, "activated": 40, "finished": 3100, "failed": 45},
        "tasks_active": 9
      }
    },
    "alarms": {
      "v": 1,
      "registration_version": 1,
      "revision": 18,
      "assessed_at": "2026-07-16T18:29:58Z",
      "data": {"active": 0}
    },
    "health": {
      "v": 1,
      "registration_version": 2,
      "revision": 944,
      "assessed_at": "2026-07-16T18:29:55Z",
      "assessment_policy": "system-status-v1",
      "data": {
        "overall_status": "ok",
        "checks_by_status": {"ok": 9, "warning": 0, "error": 0, "unknown": 0},
        "oldest_check_age_seconds": 42
      }
    },
    "assessments": {
      "v": 1,
      "registration_version": 4,
      "revision": 208,
      "assessed_at": "2026-07-16T18:29:55Z",
      "assessment_policy": "campaign-freshness-v1",
      "data": {
        "daily": {
          "status": "ok",
          "age_hours": 6.2,
          "last_completed_at": "2026-07-16T12:18:00Z"
        },
        "weekly": {
          "status": "ok",
          "age_hours": 60.5,
          "last_completed_at": "2026-07-14T06:00:00Z"
        }
      }
    },
    "ops": {
      "v": 1,
      "registration_version": 3,
      "revision": 8402,
      "assessed_at": "2026-07-16T18:29:55Z",
      "data": {
        "agent_status": "ok",
        "agent_heartbeat_age_seconds": 2,
        "agent_last_heartbeat_at": "2026-07-16T18:29:53Z",
        "actions_total": 8402,
        "last_action_at": "2026-07-16T18:27:14Z"
      }
    }
  }
}
```

Each component contains its registration version, component revision,
`assessed_at`, optional remote-source time, optional assessment-policy version,
and data. Its complete registration metadata is copied from the component row
into stored full snaps and whenever the registration changes. The top-level
`observed_at` says when Snapper read the maintained projections; it is not the
assessment time of every component. The component map is open, but each
component is a bounded state vector. It can contain explicit assessments,
active identities, aggregate counts, timestamps, and references to
authoritative records. It does not contain complete task, job, file, message,
or log collections.

Each snap has exactly one JSONB state payload. State is not split across
normalized component-content tables.

### Full and delta encodings

Every logical snap represents the complete system state. The JSON payload has
one of two physical encodings:

- `full` contains the complete component map.
- `component_delta` contains complete replacements for the changed top-level
  components.

A delta never contains JSON Patch operations or field-level edits. Replacing a
whole component preserves component ownership and versioning. Removing a
component uses an explicit component tombstone.

Periodic, initial, manual, and recovery snaps use full encoding. Change snaps
between them can use component-delta encoding. With a full snap every ten
checks, reconstruction requires at most one full payload and nine intervening
deltas.

Reconstruction dynamically selects the latest `full` snap at or before the
target and applies later `component_delta` rows in `(scope, snap_time)` order
through the target. The unique `(scope, snap_time)` constraint makes the order
deterministic. No chain membership or sequence linkage is stored. A historical
insertion takes its chronological position automatically.

The composed state hash is stored on both encodings. A delta's component keys
must equal `changed_components`, and applying the full snap plus its ordered
deltas must reproduce that hash. Full-only writing remains a valid operating
mode while row size and change density are measured.

A component hash covers its registration, assessment-policy version, tombstone
state, and canonical `data`. It excludes revision, `assessed_at`,
`source_as_of`, and publication metadata. The composed state hash covers the
top-level schema version and the ordered component hashes.

### Evolution rules

- `components` is an open map. Adding a component or registered quantity is the
  normal way the snap grows. It creates a new registration version and forces a
  full snap. Consumers must ignore unknown keys.
- Within a schema version (`v`), keys are never renamed or removed and
  meanings never change. A breaking change bumps `v`; during a transition
  a writer may emit both versions' fields. A top-level or component schema
  change makes a full snap due.
- Every count-by-category is an open map keyed by the domain value
  (`by_status`, `by_state`, `by_type`), so new statuses appear in the
  record without any schema change.
- Counters are cumulative where the source is cumulative. A component may also
  carry rates and windowed counts maintained by its owner; their window and
  assessment time are part of that component's contract.
- Health, liveness, staleness, and age assessments are stored when maintained
  by the component owner. Supporting timestamps and counters are retained when
  useful for audit, but readers do not have to recreate the assessment.
- A component whose data has independent freshness (a cached view of a
  remote system, such as PanDA) carries its own `source_as_of`.
- One component = one state owner = one key. The owner defines and maintains
  its section's internal structure.

## Quantity registration

Components and quantities have different roles:

- A **component** is the ownership, consistency, revision, and delta unit. One
  subsystem publishes the complete component projection atomically.
- A **quantity** is a registered, typed subtree within the component's `data`.
  It is the unit of discovery, validation, documentation, and later generic
  presentation.

The top-level `components` object is therefore a map of registered component
names. A component owner publishes the complete `data` subtree beneath its own
name and cannot write beneath another component. The shared helper constructs
the surrounding envelope, including registration version, content revision,
assessment metadata, and hash. The registered quantity definitions determine
the allowed shape of that subtree, including explicitly open bounded maps.

A subsystem declares its quantities in code and reconciles those declarations
through a shared registry during deployment or maintainer startup. Publication
of an unregistered quantity, or of a value that fails its registered contract,
is rejected. Registration does not install a calculation in Snapper; the owning
subsystem remains responsible for producing the value.

Each quantity definition contains at least:

- a stable key and JSON Pointer relative to the component's `data`;
- scope, component, owning subsystem, and maintainer identity;
- title and precise semantic description;
- JSON value schema, including nullability and numeric bounds where known;
- semantic kind such as gauge, cumulative counter, state, assessment,
  timestamp, bounded map, or window statistic;
- unit and, for a window statistic, the window definition;
- dimension definitions, including whether their value set is open;
- required or optional status and unavailable-value semantics;
- maximum cardinality or serialized size for bounded collections;
- visibility classification for public, operator, or internal consumers; and
- assessment, freshness, or provenance policy identifiers where applicable.

A map such as `jobs_by_state` is one bounded registered quantity whose keys are
the open PanDA-state dimension. Individual state values, sites, agents, jobs,
and tasks are not separately registered. This avoids high-cardinality
registration growth while still documenting the map's keys and values.

Registered paths within one component do not overlap. Structural JSON objects
may contain registered children, but a subtree cannot be registered both as a
quantity and as a collection of separately registered descendants. Required
quantities must be present in every publication; optional quantities use their
registered absent or null semantics.

Definitions are stored with the component's current row as a registration JSON
document and monotonically increasing `registration_version`. A metadata or
membership change replaces that registration, advances the component revision,
and forces a full snap. Every full snap copies the complete registration with
the component data; a changed component in a delta also carries its complete
registration. Historical snaps are therefore self-contained without a separate
catalog table.

Registration is an ordinary serializable declaration, not a Python plug-in.
For example:

```python
PANDA_SNAP_COMPONENT = {
    "scope": "epicprod",
    "component": "panda",
    "owner": "panda-activity",
    "quantities": {
        "jobs_by_state": {
            "path": "/jobs_by_state",
            "semantic_kind": "gauge_map",
            "unit": "jobs",
            "value_schema": {
                "type": "object",
                "additionalProperties": {"type": "integer", "minimum": 0},
            },
            "dimensions": {
                "key": {"name": "panda_job_state", "open": True},
            },
            "required": True,
            "max_items": 64,
            "visibility": "public",
        },
    },
}

publish_snap_component(
    definition=PANDA_SNAP_COMPONENT,
    content={"jobs_by_state": jobs_by_state},
    assessed_at=assessment_time,
    source_as_of=panda_source_time,
)
```

The declaration is a plain dictionary and publication is one explicit function
call in the subsystem's existing mutation or refresh path. The helper hashes
and reconciles the declaration, so unchanged metadata reuses the existing
registration version. There are no decorators, metaclasses, import-time side
effects, entry points, dynamic imports, or callbacks executed by Snapper.

## Publication and sweep mechanics

The integration is push-based. Snapper does not import subsystem modules,
discover callbacks, or call providers while making a snap.

```text
subsystem declaration ──> SnapComponent registration
subsystem maintainer  ──> SnapComponent current data
aligned clock         ──> Snapper ──> one SystemSnap
```

The shared publication library exposes one normal operation,
`publish_snap_component(...)`. It reconciles the supplied component
declaration, validates the complete content, and publishes the current
projection atomically. Registration is idempotent and travels with the
publisher rather than being configured in Snapper.

No Snapper code, configuration edit, process restart, or component-specific
hook is required when a subsystem registers another component or quantity. A
component becomes snap-visible with its first valid publication.

Publication is whole-component and single-owner. Independent publishers use
separate component keys, even when their quantities are displayed together.
This gives every component one assessment time, one source time, one
registration, one revision, and one atomic consistency boundary. A maintainer
can update several quantities in one publication without exposing an
intermediate mixture of old and new values.

For a subsystem already writing the monitor database, the publication helper
runs in the same database transaction as the authoritative state mutation when
possible. Its plain dictionary payload can also be carried by one generic
message for a process without database access; a thin ingress consumer invokes
the same helper and contains no component-specific logic. The first
implementation uses the direct database helper wherever it is already
available and adds the transport wrapper only for publishers that need it.

The shared helper locks the component row, checks publisher
ownership, validates all required and optional quantities, canonicalizes the
data, and computes its content hash. It advances the component revision only
when canonical content or the registration changes. Metadata-only refreshes
update the component row without making a change snap due.

The `SnapComponent` row is the component's interlock. A publisher uses
`SELECT ... FOR UPDATE` on its own row before comparing and replacing content.
Different components can therefore publish concurrently. Snapper prevents
component registration or retirement during a sweep with a lightweight
scope-membership advisory lock, then locks all active component rows in stable
name order. A publisher attempting to replace one of those rows waits until the
snap transaction commits. A queued message may arrive during that interval,
but the ingress cannot install it as the new now until the row unlocks.

`SnapComponent` is consequently a central current-content registry, not a
history table. It contains one mutable row per component and always represents
the latest successfully published coherent content. Repeated changes before a
snap overwrite that row and advance its revision, so publication frequency
does not create unbounded storage. "Current" means current as published, not an
assertion that a remote system was observed at the same instant; `assessed_at`,
`source_as_of`, and maintained health make that distinction explicit.

The subsystem decides what is significant enough to publish. The shared helper
does not second-guess that policy; its content hash only prevents an identical
retry from advancing the revision. A time-driven change such as crossing a
staleness threshold is a new now and must be published by the subsystem that
owns that assessment.

At an aligned boundary, Snapper first selects only the small
`(component, revision, registration_version)` vector for the scope. A new component
row or changed revision makes assembly due. Snapper then reads every active
locked component row and copies the rows into the component map. Its only
component-independent transformations are envelope construction, canonical
ordering, hashing, and full/delta encoding.

Component retirement is explicit. The owner publishes a registered tombstone;
Snapper records the removal, and older snaps retain the registration that
defined it. A component is never removed merely because its publisher stopped.
Publisher failure and staleness are represented by maintained health state.

## Maintained state contract

Every snap component has a subsystem owner that maintains a cheap, bounded
projection of its present state in the local database. This projection is the
interface between operational code and the snap system. The owner performs any
remote access, joins, aggregation, health evaluation, staleness evaluation, or
window calculation needed to produce it. Snapper only reads and composes these
projections.

A maintained projection includes:

- the component schema version and monotonically increasing revision;
- the current component data, including derived assessments useful to
  operators and historical consumers;
- `assessed_at`, meaning when that data was evaluated;
- `source_as_of` when the projection is based on an independently refreshed
  remote or cached source;
- an assessment-policy or algorithm version when interpretation depends on
  thresholds or calculation rules; and
- a canonical content hash.

Existing current-state stores remain authoritative. Their maintainers publish
the bounded snap-visible projection to `SnapComponent` in the same
transaction as the authoritative local update when possible. For example, the
System status refresher already evaluates service health and assessment
freshness; it publishes that evaluated current state rather than leaving the
Snapper or a historical reader to calculate it again.

Time-dependent transitions are also the owner's responsibility. If an agent
becomes stale solely because a threshold is crossed, the relevant maintainer
must publish the new assessed state and advance its revision. A refresh that
finds the same semantic projection may update observation metadata without
advancing the revision. This permits cheap periodic reassessment without
forcing a change snap, while the periodic full snap still captures current
provenance.

Unavailable and unknown are explicit component states, not absent data. A
maintainer that cannot refresh a remote source preserves the last known source
time and publishes the resulting stale, unavailable, or unknown assessment
according to its policy.

## Mutation contract

Every semantic mutation that changes a maintained projection advances that
component's revision in the same database transaction. This includes a new
derived assessment, rate, age, or window value when that value is part of the
component contract. Routine `updated_at` writes and successful reassessments
whose snap-visible projection is unchanged do not advance a revision. The
shared publication helper accepts a scope and component name, canonicalizes the
projection, and advances the revision only when its content hash changes.

Remote systems participate at their local ingestion boundary. A PanDA or
Rucio state maintainer advances a component revision when its local projection
changes. A successful identical refresh can update `assessed_at`,
`source_as_of`, and maintainer health without making a change snap due. The next
periodic full snap records that newer provenance.

Per-component revisions avoid a single global revision hot spot and identify
the components responsible for a snap. Periodic full snaps provide bounded
reconciliation for missed instrumentation. Revisions are wake-up generations;
component hashes, rather than revision numbers, identify projection content.

## Snap protocol

At each aligned boundary, Snapper performs the following operations in one
database transaction:

1. Acquire a scope run lock so only one Snapper process evaluates the scope,
   then acquire the scope membership lock in shared mode and select all active
   `SnapComponent` rows `FOR UPDATE` in component-name order. Registration and
   retirement take the membership lock in exclusive mode. Existing component
   publishers lock only their own rows.
2. Compare the locked component revision vector with the cursor's observed
   revision vector. Also check periodic-full, manual, and recovery requests.
   This combined decision is `do_snap`:

   ```text
   do_snap = revisions_changed or full_due or manual_due or recovery_due
   full_due = registration_changed or periodic_full_due
   ```

   The revision mismatch is the durable change latch; no separate Boolean flag
   is required. A registration change also advances the component revision but
   forces full rather than delta encoding.
3. If nothing is due, update the bounded scheduler cursor and stop. No
   component payloads are assembled and no snap row is written.
4. If assembly is due, capture the locked rows, their registration versions,
   and their revision vector. No publisher can replace a component now until
   the transaction commits.
5. Canonicalize the maintained component projections and compute per-component
   hashes and the composed state hash. `changed_components` is determined by
   component-hash comparison, not by the pending-revision list.
6. Persist a snap if the hash changed, or if a periodic, manual, or recovery
   reason requires a record. Use full encoding for a required full snap;
   otherwise use full or component-delta encoding according to configuration.
   A mutation that returns to the previous state is assembled but does not
   require a duplicate change snap.
7. Advance the cursor's observed revisions only to the captured vector and
   commit, releasing the row and membership locks. A waiting publication then
   installs its new now and remains due for the next boundary.

The cursor increments `checks_since_full` at every evaluated boundary and
resets it after a full snap. A full snap is due when the counter reaches the
current `full_every_checks` setting. Cadence changes apply at the next check;
stored rows remain self-describing and require no cadence-aware read behavior.

If a periodic full assembly finds a changed component hash without a pending
revision, the snap is stored and a `snap_revision_miss` warning is recorded in
the application log and System status. The periodic pass provides recovery,
but an incorrectly published projection remains an operational defect.

Initial startup, maximum quiet interval, manual request, and recovery after an
observer gap force a full snap even when the state hash is unchanged. Manual
requests mark the next aligned boundary; they do not create off-grid snaps.

Every boundary is evaluated. A snap is stored only when composed state changes
or a full snap is required. Scheduler liveness is monitored separately, so the
absence of a new snap can be distinguished from a stopped Snapper process.

## Consistency and failure semantics

Snapper reads the locked `SnapComponent` rows only. The transaction provides a
stable local cut across every component projection. Maintainers may have
evaluated remote sources at different times, so each remote-derived component
carries `source_as_of`.

A stored logical snap reconstructs to complete state. If a required current
projection is missing, invalid, or changes inconsistently during assembly, the
transaction writes no snap and does not advance observed revisions. The
failure is recorded in the application log and System status, and the next
boundary retries. Missing projections are never converted to empty component
data.

Remote or expensive work never occurs in this failure path. A state-maintainer
failure is represented in maintained state as stale, unavailable, or unknown;
a local database or projection-contract failure aborts snap assembly.

Snapper never backfills a missed boundary with present state. A missed
boundary creates an observer coverage gap. The next successful boundary forces
a recovery snap, and System status history records the stale and recovered
transitions. Queries do not carry state across such a gap.

## Data model

The authoritative content model has two tables. `SnapComponent` is mutable and
holds each registered component's latest now; `SystemSnap` is immutable and
holds the complete recorded system history. The small cursor described below is
operational scheduler state, not another content or history representation.

### `SystemSnap`

Immutable table `swf_system_snap` (`monitor_app.SystemSnap`):

| Field | Type | Notes |
|---|---|---|
| `id` | big integer primary key | snap identity |
| `scope` | char, indexed | `testbed`, `epicprod`; unique with `snap_time` |
| `snap_time` | timestamptz, indexed | aligned clock time of the scheduler boundary |
| `observed_at` | timestamptz | start time of the database observation |
| `completed_at` | timestamptz | end time of snap assembly |
| `schema_version` | small integer | top-level record version |
| `encoding` | char | `full` or `component_delta` |
| `reasons` | JSONB array | `change`, `periodic`, `manual`, `recovery` |
| `changed_components` | JSONB array | components whose canonical data hashes changed |
| `component_revisions` | JSONB object | revision vector captured by the database snapshot |
| `component_registration_versions` | JSONB object | registration version captured for each component |
| `component_hashes` | JSONB object | hashes of canonical maintained component content |
| `state_hash` | char(64) | SHA-256 of the complete composed component content |
| `state` | JSONB | complete map for `full`; changed-component map for `component_delta` |
| `created_at` | timestamptz auto | database insertion time |

Index `(scope, snap_time)` descending serves "latest" and range scans.
JSONB GIN indexing is deferred until a query pattern needs it.

### `SnapComponent`

Mutable table `swf_snap_component` (`monitor_app.SnapComponent`),
with one row per `(scope, component)`:

| Field | Type | Notes |
|---|---|---|
| `id` | big integer primary key | row identity |
| `scope` | char | `testbed` or `epicprod` |
| `component` | char | registered state key; unique with `scope` |
| `registration_version` | bigint | advances when quantity definitions change |
| `registration` | JSONB | owner and complete registered quantity definitions |
| `registration_hash` | char(64) | canonical registration hash |
| `revision` | bigint | advances when canonical component content changes |
| `assessed_at` | timestamptz | when the owner evaluated this projection |
| `source_as_of` | timestamptz, nullable | independent source or cache time |
| `assessment_policy` | char, nullable | versioned policy or algorithm identifier |
| `publisher_id` | char | registered component owner identity |
| `tombstone` | boolean | explicit component retirement state |
| `data` | JSONB | bounded present-state projection |
| `content_hash` | char(64) | registration, policy, tombstone, and canonical data hash |
| `last_accepted_at` | timestamptz | latest valid publication, including identical content |
| `changed_at` | timestamptz | latest canonical-content change |
| `updated_at` | timestamptz auto | latest publication, including metadata-only refresh |

Subsystem maintainers publish these rows. The shared helper locks the row,
validates `data` against `registration`, computes the hashes, advances
`revision` only when content changes, and updates assessment and source metadata
on every successful publication. A registration change advances both
`registration_version` and the component revision and forces a full snap.
Snapper locks and reads these rows but never treats them as history.

### `SystemSnapCursor`

Mutable table with one row per scope:

| Field | Type | Notes |
|---|---|---|
| `scope` | char primary key | `testbed`, `epicprod` |
| `observed_revisions` | JSONB object | latest component vector successfully assembled |
| `observed_registration_versions` | JSONB object | latest registration vector successfully assembled |
| `last_component_hashes` | JSONB object | latest assembled component hashes |
| `last_state_hash` | char(64) | latest assembled component-content hash |
| `checks_since_full` | positive integer | evaluated boundaries since the latest full snap |
| `last_check_time` | timestamptz | latest aligned boundary evaluated |
| `last_check_observed_at` | timestamptz | actual scheduler observation time |
| `last_check_result` | char | `quiet`, `unchanged`, `snapped`, or `failed` |
| `last_snap_id` | foreign key, nullable | latest stored snap |
| `last_full_snap_at` | timestamptz, nullable | latest stored full snap |
| `updated_at` | timestamptz auto | cursor write time |

The cursor is the small fixed-cost write at every check. It is bounded current
state rather than content history. System status history records scheduler
health transitions.

## State maintainers and Snapper

State maintainers are registered by scope and component name. They can be part
of an existing mutation path, such as datataking state changes, or periodic
refreshers, such as System status and PanDA activity. They publish through the
shared `SnapComponent` helper after doing their component-specific work.
The helper is the instrumentation point that makes a snap due.

Snapper has no component plug-ins and no knowledge of component internals. It
selects all registered current-state rows for a scope, wraps each row as a
versioned component envelope, and records their consistent composition.

Snapper is a standalone doer beside the status refresher:

```bash
scripts/run-snapper.py --scope all --source ops_agent_periodic
```

The epicprod ops agent runs it on a periodic loop and handles
`msg_type=record_system_snap` for manual triggers, as it does for
`refresh_system_status`. Both scopes read the same database, so one doer
covers both.

## Component-facing services

The registry and snap history provide generic services back to every registered
component. These services require no component-specific code in Snapper.

`publish_snap_component(...)` returns:

- `accepted_at`: when the valid publication entered the current registry;
- `registration_version` and `component_revision`;
- `content_changed`: whether canonical content differed from the preceding
  current content and therefore advanced the revision;
- `different_from_last_snap`: whether the accepted content hash differs from
  the component hash in the latest recorded logical snap; and
- `do_snap`: whether the scope remains due after the publication.

An identical status reading is therefore accepted and refreshes observation
metadata while returning `content_changed=false`. If an earlier change is still
waiting for the next boundary, `different_from_last_snap` remains true.

`get_snap_component(scope, component)` returns the registered definition,
current content, `assessed_at`, `source_as_of`, last acceptance and content
change times, latest recorded snap time, and the same pending comparison. The
comparison is a content-hash comparison between `SnapComponent` and the
cursor's latest component hash; it does not re-evaluate the component's data.

`get_snap_component_history(scope, component, since, until=None)` returns that
component reconstructed from the recorded snap series, with actual snap,
assessment, and source times and the registration version applicable to each
value. The default compact form returns the state at the start of the interval
followed by content changes. An option can include unchanged periodic
observations.

This history is snap history, not a log of every publication. Several component
changes between aligned boundaries can collapse into the one now captured at
the boundary, and identical readings are not append-only records. A component
that requires every intermediate reading or transition retains its own event or
measurement history and can join it with snaps by time.

## Initial registration set

The first release should be deliberately small, but each component should be
useful immediately and establish a reusable state-maintenance path.

| Scope | Component | Initial registered quantities |
|---|---|---|
| both | `health` | `overall_status`, `checks_by_status`, `checks`, `oldest_check_age_seconds`, `assessment_freshness` |
| testbed | `datataking` | `state`, `substate`, `run_number`, `last_transition_at` |
| testbed | `workflows` | `active_by_status`, `active_by_type`, `completed_total`, `failed_total`, `recent_outcomes` |
| testbed | `agents` | `instances`, a bounded map containing each agent's operational and assessed health state |
| testbed | `data` | `stf_files`, `tf_slices`, `slices_by_status`, `queue_depth`, `recent_throughput` |
| epicprod | `panda` | `jobs_by_state`, `jobs_by_site`, `running_jobs`, `running_cores`, `active_tasks_by_state`, `active_tasks_by_type`, `recent_outcomes` |
| epicprod | `production` | `campaigns`, `pcs_tasks_by_state`, `outputs_total`, `bytes_total`, `placement_by_state`, `last_rucio_arrival_at` |
| epicprod | `ops` | `agent_state`, `actions_total`, `recent_actions`, `alarms`, `assessment_execution` |

The PanDA component is the first high-value epicprod activity projection. A
periodic PanDA maintainer performs the raw queries or consumes maintained
rollups, publishes the compact result locally, and marks the component due only
when that result changes. Snapper never queries PanDA job or task tables
itself. This directly records historical concurrency without repeatedly
counting jobs whose start and end times bracket each later query.

## Cadence, retention, configuration

Proposed SysConfig keys and their seeded values:

| Key | Production target | Commissioning | Meaning |
|---|---:|---:|---|
| `snap_check_seconds_testbed` | 30 | 10 | testbed aligned evaluation cadence |
| `snap_check_seconds_epicprod` | 30 | 10 | epicprod aligned evaluation cadence |
| `snap_full_every_checks_testbed` | 10 | 10 | maximum checks between full testbed snaps |
| `snap_full_every_checks_epicprod` | 10 | 10 | maximum checks between full epicprod snaps |
| `snap_retention_days_testbed` | 365 | 365 | testbed immutable retention horizon |
| `snap_retention_days_epicprod` | 365 | 365 | epicprod immutable retention horizon |
| `snap_delta_enabled_testbed` | true | false | allow testbed component-delta snaps |
| `snap_delta_enabled_epicprod` | true | false | allow epicprod component-delta snaps |

The production target therefore checks every 30 seconds and forces a full snap
every 5 minutes. Commissioning checks every 10 seconds and forces a full snap
every 100 seconds. Commissioning begins at the higher frequency so observed
snap rate, component change density, assembly time, and JSONB size can guide
later settings. It begins in full-only mode to establish full payload size,
then enables deltas to exercise reconstruction and measure savings.

These settings may change at any time. The scheduler reads the current values
from SysConfig and realigns its next check accordingly. Stored snaps do not
need configuration history: their timestamps and encodings are sufficient
for reconstruction, comparison, and presentation.

Two scopes checked every 30 seconds have fewer than 6,000 snap opportunities
per day. Only due opportunities produce rows, so storage follows system
activity. Capacity planning uses measured snap rate and p95 JSONB row size.

All snaps are retained intact within the retention horizon. A full snap and
the following deltas up to the next full snap form one retention segment and
are deleted together. Keeping every Nth snap is not valid because it can break
reconstruction or remove the only record of a short-lived state. Longer-term
reduction uses separate component-specific rollups.

A System status check watches the Snapper heartbeat per scope and turns the
System indicator red if Snapper stops. Snap age alone is not a liveness signal
because an unchanged system may produce no snap.

## Query semantics

`snap_time` is the timestamp assigned to the snap; `observed_at` is when the
database snapshot was taken. Their difference exposes scheduler and assembly
lag.

For a requested time with no exact stored row, the query layer returns the
latest earlier snap and its actual timestamp when scheduler coverage is known
to be continuous. It does not relabel or synthesize a record at the requested
time. A known observer gap returns unknown coverage rather than an old state
presented as current. Regular resampling and other explicit carry-forward are
subject to the same coverage rule.

Full and component-delta payloads are reconstructed from the rows present at
query time in chronological database order. The state hash stored on each row
validates the composed result. Consumers receive one complete logical snap.
Charts plot actual snap times. Any regular series is an explicit resampling
operation with a declared resolution and carry-forward policy.

A logical `SystemSnapComponentHistory` view exposes
`(snap_time, scope, component, registration_version, component_data)` without
creating another authoritative history table. For one component and time
range, it selects the latest preceding full snap plus full rows and deltas that
contain that component, extracts only the named JSON subtree, and suppresses
unchanged hashes in compact mode. Plotting code therefore filters by component
name and iterates that component's JSON rather than decoding unrelated
components. If measured query volume later warrants it, this view can be
materialized as a derived cache without changing the two-table content model.

Component assessments are returned exactly as maintained and recorded, together
with their `assessed_at`, `source_as_of`, and policy provenance. Historical
assessment age, health, liveness, staleness, and windowed rates are not
recomputed using the query clock or current thresholds. A consumer can perform
an explicitly labeled alternative analysis from supporting facts, but it does
not replace the recorded assessment.

## Consumers

- **Pages**: read rows only. A snap history view with a time slider over the
  record becomes possible once the series exists.
- **MCP**: `swf_get_system_snap(scope, at=None)` returning the snap at or
  before a time (latest by default), and snap-range retrieval for
  trending. Tool additions follow the standard MCP checklist.
- **AI**: assessments and daily reports compare snaps instead of re-deriving
  the global state; anomaly detection combines snaps with event and rollup
  series.
- **Incident review**: the snap at the incident time is the system-wide
  context, joined with the event streams for exact sequences.

## Deferred

- Per-namespace snap scopes (the scope field admits them when wanted).
- Component-specific long-term rollups.
- Event-snap correlation views.
