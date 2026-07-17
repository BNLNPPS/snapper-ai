# snapper-ai technical design

This document is the technical contract for snapper-ai. The
[README](../README.md) provides the short product description. The
[superseded early design](archive/SNAP_EARLY_DESIGN_SUPERSEDED.md) preserves the
longer path by which the current design was reached.

snapper-ai is a generic service that aggregates subsystem-maintained current
state into efficient, coherent, durable, AI-readable history. Capture is
deterministic and AI-free. AI is the primary consumer layer.

## Design invariants

1. Each subsystem owns and maintains its bounded present-state projection.
2. A component publication is a complete atomic replacement under one owner.
3. Registration supplies the structure and interpretation metadata needed to
   understand every published quantity.
4. Snapper copies maintained state; component-specific probing, joining,
   aggregation, and assessment stay with the owner.
5. Fixed, aligned opportunities and the decision to persist a snap are separate
   concerns.
6. Registration begins with a concrete historical retrieval need and a declared
   useful representation and temporal resolution.
7. Any canonical change in an owner-curated component projection makes a snap
   due; periodic baselines bound quiet intervals.
8. Every logical snap represents complete state across the registered scope.
9. Event streams carry exact transitions; snaps carry coherent sampled state.
10. Historical interpretation uses recorded timestamps, versions, policy epochs,
   provenance, and database ordering.
11. Component schemas and capture practice can evolve while old history remains
    directly interpretable.

## Terms and roles

| Term | Meaning |
|---|---|
| scope | A system whose state is recorded, initially `testbed` or `epicprod` |
| component | One subsystem-owned bounded state projection and atomic update unit |
| now | A component's latest accepted complete state and provenance |
| registration | Serializable metadata defining a component and its quantities |
| publication | Atomic replacement of a component's registered current state |
| snap opportunity | A fixed clock-aligned boundary at which capture is evaluated |
| system snap | One immutable logical state across the registered scope |
| coherent cut | One transactionally consistent read of the component registry |
| event stream | Exact transition history retained by the owning system |

```text
component maintainers  -->  current component registry
                                      |
aligned scheduler  -------------------+-->  system snap history
                                                   |
                                  APIs, pages, MCP, AIs, analysis
```

## Registration

A subsystem registers a component using an ordinary serializable declaration.
The declaration travels with the publisher and can be reconciled idempotently
during deployment or maintainer startup. Snapper remains component-agnostic and
executes no component callbacks.

Every proposed component and quantity starts with the historical question it
will answer and the representation and temporal resolution at which that answer
is useful. These consumer requirements determine the curated projection before
its schema is registered.

A component is the ownership, consistency, revision, and replacement unit. A
quantity is a typed subtree inside the component's `data`. Quantities provide
discovery, validation, documentation, and generic presentation.

Each quantity definition includes, as applicable:

- a stable key and path relative to component `data`;
- scope, component, owning subsystem, and publisher identity;
- a title and precise semantic description;
- JSON value shape, nullability, and numeric bounds;
- kind, such as gauge, cumulative counter, state, assessment, timestamp,
  bounded map, or window statistic;
- unit and window definition;
- dimension definitions and whether their value sets are open;
- publication resolution, aggregation, or bucketing semantics when relevant;
- required, optional, unavailable, and unknown-value semantics;
- maximum cardinality or serialized size for bounded collections;
- visibility classification; and
- freshness, assessment, algorithm, and provenance policy identifiers.

A component may also register related event sources. Each source declaration
gives exact-event context a stable identity and resolver while the events remain
in their authoritative system. The event-reference contract is defined below.

Open bounded maps represent domains such as `jobs_by_state`. The map is one
registered quantity; individual jobs, tasks, sites, or states stay outside the
registration catalog. Registered paths inside a component have unambiguous
ownership and shape.

Registration carries a monotonically increasing version and canonical hash.
Metadata or quantity membership changes create a new registration version and
make a full snap due. Stored history retains the applicable registration so an
external mutable catalog is unnecessary for interpretation.

## Publication and maintained now

The owning subsystem publishes a complete replacement whenever its curated,
snap-visible state changes. Whole-component publication gives every component
one assessment time, one source time, one revision, and one atomic consistency
boundary. Independent publishers use separate component names.

The owner chooses both content and resolution before publication. It may publish
bucketed counts, rounded rates, stable categories, or another bounded projection
whose changes are worth recording. snapper-ai applies one mechanical rule after
publication: a canonical content change advances the component revision. It has
no component or quantity significance engine. A publisher that exposes a raw
fast-changing gauge has intentionally chosen that gauge's change rate as a
possible system snap rate.

The component API supports two owner assessments:

- `publish_component(...)` submits a complete curated projection; and
- `report_component_unchanged(...)` affirms that the owner assessed its source
  and the currently registered projection remains current at its declared
  resolution.

A no-change report updates assessment time, optional source time, latest report
time, and maintainer liveness. It preserves component data, content hash, and
revision, so it creates no new change reason. An earlier unrecorded revision
remains due. Assessment and source times are provenance outside the
revision-driving canonical content; the next periodic baseline records their
newest values.

The no-change operation authenticates the same component owner and requires an
active registered projection. A transport that can reorder messages also sends
the revision it is affirming, allowing Snapper to reject a stale affirmation.
An identical complete publication remains valid and has the same revision
semantics; the explicit operation avoids constructing and validating a possibly
large unchanged payload.

Publication performs these generic operations:

1. authenticate the publisher and verify component ownership;
2. reconcile and validate the registration;
3. validate all required and optional content;
4. canonicalize the complete component JSON;
5. compute registration and content hashes;
6. compare with the current accepted state; and
7. atomically store the new now and return its acceptance result.

An identical reading is valid. It refreshes acceptance and observation metadata
while preserving the component revision. A semantic content or registration
change advances the revision and leaves the scope due for capture. Frequent or
simple publishers can send every reading while canonical comparison keeps
history compact.

The mutable component registry stores one current record per `(scope,
component)`. It contains:

| Field group | Contents |
|---|---|
| identity | scope, component name, publisher identity, active or retired state |
| registration | definition, schema version, registration version and hash |
| current state | bounded JSON data and canonical content hash |
| generation | monotonically increasing component revision |
| provenance | assessed time, optional source time, assessment-policy version |
| publication | latest acceptance time and latest semantic-change time |

This registry is mutable staging state. Immutable system snaps provide history.
The current record also provides the natural component-level interlock used
during publication and capture.

Component retirement is explicit and versioned. A tombstone enters snap history;
publisher silence leaves the component registered and allows its maintained
health or freshness state to describe the failure.

## Maintained assessments

Owners perform remote access, joins, aggregation, health evaluation, staleness
evaluation, and window calculations before publication. Operationally useful
health, age, rate, and rolling-window values enter the maintained projection
together with their assessment time and policy version.

A cached view of a remote system also carries `source_as_of`. A failed refresh
preserves the last source time and publishes the owner's assessed stale,
unavailable, or unknown state. Time-driven transitions, such as crossing a
staleness threshold, are semantic state changes and produce a new publication.

Historical readers receive the assessment exactly as recorded. Alternative
analysis can use supporting facts and an explicitly identified policy; it stays
distinct from the assessment the system knew at the time.

## Coherence and time

A coherent snap is a transactionally consistent read of the current component
registry. It guarantees that every included component was a complete accepted
publication and that the registry did not change midway through composition.

Coherence does not imply simultaneous source observation. Component owners run
independently, and one snap may contain assessments made seconds or minutes
apart. Every component therefore retains `assessed_at`, optional `source_as_of`,
and its assessment-policy version. The snap envelope separately records the
aligned `snap_time` and actual registry `observed_at`.

APIs and AI context present these times with the state. The precise historical
claim is: *these were the latest accepted component projections in one stable
registry cut*. Consumers can apply freshness requirements to that evidence; they
must not describe the components as simultaneously observed.

## Capture practice

Snap opportunities occur at a fixed, aligned cadence. Every opportunity makes a
bounded decision:

```text
do_snap = revisions_changed or baseline_due or manual_due or recovery_due
```

The component revision vector is the durable change latch. A separate dirty
flag adds no information. Registration changes advance a component revision and
force a full snap.

At a boundary, the capture transaction proceeds as follows:

1. serialize capture for the scope and stabilize active membership;
2. read and lock active component records in stable component-name order;
3. compare their revision vector with the last successfully observed vector;
4. evaluate baseline, manual, and recovery reasons;
5. end a quiet opportunity after updating the bounded scheduler cursor;
6. when due, copy the stable component records, canonicalize them, and compute
   per-component and composed-state hashes;
7. persist the snap and advance the observed vector to the captured generation;
   and
8. commit and release the component interlocks.

A publisher that reaches a locked component waits briefly, installs its newer
now after commit, and remains due for the next boundary. Different components
can publish concurrently. Database row locks are a natural implementation;
other stores may provide an equivalent compare-and-swap or transactional
interlock.

The first capture pass reads only the small `(component, revision,
registration_version)` vector. Quiet opportunities stop before component JSON
assembly. Capture performs only local registry reads, envelope construction,
canonical ordering, hashing, and persistence.

Storage sparsity is an observed outcome rather than a correctness target. A
scope whose useful state changes at every opportunity produces a snap at every
opportunity. The configured cadence bounds that rate. The revision-vector path
still supplies durable change detection and cheap evaluation whenever the scope
is quiet.

Initial cadence values favor measurement:

| Period | Snap opportunity | Maximum quiet interval |
|---|---:|---:|
| commissioning | 10 seconds | 100 seconds |
| initial production target | 30 seconds | 5 minutes |

The baseline is initially ten opportunities. Configuration can change these
values at any time. Every snap records or references the effective capture
policy and epoch. Readers use actual timestamps and recorded provenance, so
period changes and their edges require no cadence-aware query behavior.

Initial startup, a maximum quiet interval, a manual request, and recovery after
an observer gap produce full snaps. Manual requests target the next aligned
boundary. Missed boundaries create explicit observer-coverage gaps; the next
successful boundary records recovery using current state at that time.

Scheduler health is maintained separately from snap age. A quiet healthy system
may have sparse snap history while the scheduler continues to evaluate every
boundary.

## Snap representation

Every logical snap represents complete system state and has one versioned JSON
structure. A relational store may keep searchable envelope fields in columns and
the component map in one JSON column while the external representation remains a
single document.

```json
{
  "v": 1,
  "scope": "epicprod",
  "snap_time": "2026-07-16T18:30:00Z",
  "observed_at": "2026-07-16T18:30:00.103Z",
  "capture_policy": "epicprod-v1",
  "encoding": "full",
  "reasons": ["change"],
  "changed_components": ["panda"],
  "components": {
    "panda": {
      "v": 1,
      "registration_version": 6,
      "revision": 4810,
      "assessed_at": "2026-07-16T18:29:48Z",
      "source_as_of": "2026-07-16T18:29:41Z",
      "data": {
        "jobs_by_state": {"running": 250, "activated": 40},
        "active_tasks": 9
      }
    }
  }
}
```

The snap envelope carries:

- scope, aligned snap time, observation time, and completion time;
- snap-schema and capture-policy versions;
- reasons for capture and changed component names;
- component revision, registration-version, and hash vectors;
- a composed state hash; and
- the named component map.

Each component carries its schema and registration versions, revision,
assessment time, optional source time, policy provenance, and bounded data. Its
data may contain state, aggregates, assessments, timestamps, and references.
High-cardinality source collections remain in their authoritative systems.

The first implementation stores full snaps and measures row size and change
density. Complete top-level component replacements can later provide delta
encoding when the measured savings justify reconstruction. A delta uses whole
components and explicit tombstones; field-level patch operations would weaken
component ownership. The semantic contract remains complete logical state for
every snap.

Historical sequence is discovered dynamically through `(scope, snap_time)`
database order. Previous and next rows require no stored chain pointer. A
historical insertion takes its chronological position automatically. Full-plus-
delta reconstruction selects the latest preceding full row and applies later
component replacements in database order, validating the composed state hash.

## Conceptual data model

The authoritative content model has two stores plus a bounded operational
cursor.

### Current component

One mutable record per `(scope, component)` contains registration, current data,
revision, hashes, timestamps, policy provenance, publisher identity, and
retirement state. Component publication and snap capture coordinate through
this record.

### System snap

Each immutable history record contains an identity, scope, aligned and observed
times, schema and policy versions, encoding, capture reasons, changed components,
revision and hash vectors, composed state hash, and state JSON.

An index beginning with `(scope, snap_time)` serves latest, point-in-time, and
range queries. JSON indexes should follow measured query patterns.

### Capture cursor

One mutable cursor per scope stores the latest successfully observed component
revision vector and hashes, latest check and snap information, baseline progress,
and scheduler result. It is bounded operational state and keeps per-opportunity
work constant.

## Evolution

snapper-ai history remains interpretable as both recorded state and capture
practice evolve.

The component map is open. Adding a component or quantity creates a registration
version. Additive fields are normal, and consumers ignore unfamiliar keys.
Breaking shape or meaning changes create a component schema version. Historical
records retain the registration and policy provenance applicable when they were
captured; old payloads remain valid historical facts.

Capture cadence, baseline frequency, triggering rules, assessment policies, and
physical encoding evolve under explicit versions or policy epochs. Query logic
depends on actual record time, coverage, and provenance. Schemas and capture
policies are themselves temporal state.

## Query semantics

The core retrieval operations are:

- `latest(scope)` returns the latest logical system state;
- `state_at(scope, time)` returns the latest eligible state and its actual snap
  time, together with observer-coverage status;
- `changes_between(scope, start, end)` returns changed components and values;
- `component_history(scope, component, start, end)` returns the component's
  recorded evolution with applicable registration and provenance; and
- `context_around(scope, time, window)` returns system state, nearby changes,
  and resolvable references to registered exact event streams.

Point-in-time results preserve their actual snap timestamp. Known observer gaps
produce unknown coverage rather than silently carrying old state across the
gap. Charts plot actual snap times. Regular series are explicit resampling
operations with a declared resolution and carry-forward policy.

A component-history view extracts one named component from logical snaps and
can suppress unchanged baseline values. It begins with the state at the start of
the interval, followed by recorded changes. Several publications between aligned
boundaries may collapse into the one now captured at the boundary; components
that need every intermediate transition retain an event or measurement stream.

Component-facing operations also expose the current registration and state,
latest acceptance time, current revision, whether accepted content changed, and
whether current content differs from the latest recorded snap.

## Event-reference contract

snapper-ai links coherent state to exact transitions without copying event
streams into snap history. A component registration can declare zero or more
event sources. Each declaration contains:

- a stable source key unique within the component;
- the authoritative owner and event kind;
- event-time semantics and the field that carries event time;
- a stable resolver identifier, such as an API route, MCP tool, or adapter name;
- the JSON shape of any source-specific selector;
- optional event-ID, cursor, and watermark semantics;
- visibility and authorization classification; and
- retention or availability semantics when known.

`context_around` returns references using a common envelope:

```json
{
  "component": "panda",
  "source": "actions",
  "resolver": "panda-action-stream",
  "scope": "epicprod",
  "from": "2026-07-16T18:25:00Z",
  "until": "2026-07-16T18:35:00Z",
  "selector": {"campaign": "26.06"},
  "watermark": "opaque-source-watermark",
  "availability": "available"
}
```

`component`, `source`, and `resolver` identify the registered declaration.
`from` and `until` bound event time. `selector`, `watermark`, and explicit event
IDs are optional source-defined fields whose shapes come from that declaration.
`availability` reports `available`, `expired`, `unauthorized`, or `unknown` at
query time.

A resolver must produce the referenced events or a specific availability
result. The SWF integration maps resolver identifiers to concrete APIs and MCP
tools. Stable registered identifiers keep stored or returned references
independent of deployment URLs.

## AI evidence contract

snapper-ai makes system state directly knowable across time. It moves the first
step of AI reasoning from timeline reconstruction to deterministic retrieval.

An AI-facing result includes:

- requested scope and time;
- actual snap, assessment, and source times;
- observer-coverage status;
- complete logical component state;
- schema, registration, assessment-policy, and capture-policy versions;
- content hashes and source provenance;
- changes within the requested context window; and
- resolvable event references and authoritative source records.

This contract supports incident analysis, anomaly detection, automated
reporting, planning, evaluation, and reliable agent decisions. MCP and agent
interfaces use the same query semantics as pages and ordinary APIs. Semantic
memory systems can add documents, incidents, people, hypotheses, and inferred
relationships above snapper-ai's deterministic operational evidence.

## Efficiency discipline

Efficiency shapes the architecture from the beginning:

- publishers overwrite one bounded current component record;
- canonical hashes collapse identical semantic publications;
- each opportunity first compares a small revision vector;
- quiet opportunities stop before JSON assembly and persistence;
- assembly uses maintained local state and generic transformations;
- component-level interlocks allow independent publication;
- change-driven snaps make storage follow system activity;
- periodic baselines bound quiet intervals and aid reconciliation;
- bounded projections leave high-cardinality collections at their source; and
- full-only storage establishes the measurement baseline for any later delta
  optimization.

At a 30-second opportunity interval, two scopes present fewer than 6,000 daily
opportunities. Only due opportunities create immutable history rows. Capacity
planning uses measured snap rate, change density, assembly time, and p95 row
size.

Retention preserves reconstructable history. With delta encoding, a full snap
and its following deltas form a retention segment and age out together. Long-
term reduction uses separate component-specific rollups, preserving the primary
snap history within its configured horizon.

## Initial registration set

| Scope | Component | Initial state |
|---|---|---|
| both | `health` | overall status, checks, assessment freshness |
| testbed | `datataking` | state, substate, run number, last transition |
| testbed | `workflows` | active work, outcomes, cumulative totals |
| testbed | `agents` | bounded instance map with operational and health state |
| testbed | `data` | files, slices, queues, recent throughput |
| epicprod | `panda` | jobs, cores, sites, tasks, and outcomes by state or type |
| epicprod | `production` | campaigns, outputs, bytes, placement, data arrival |
| epicprod | `ops` | agent state, actions, alarms, assessment execution |

The PanDA maintainer performs raw queries or consumes maintained rollups and
publishes a compact local projection at a deliberately chosen resolution. Raw
job and task changes affect snap rate only through that curated projection. Snap
capture remains independent of PanDA job and task tables.

## Prior art and distinction

snapper-ai borrows proven mechanisms while retaining its narrow scope:

- [ETSI NGSI-LD](https://cim.etsi.org/NGSI-LD/official/introduction.html) and
  [Orion-LD](https://github.com/FIWARE/context.Orion-LD) provide registered
  current and temporal context, centered on entity/property history, JSON-LD
  semantics, and federation. snapper-ai centers on lightweight recurring
  coherent system state.
- [Eclipse Ditto](https://eclipse.dev/ditto/) maintains generic digital-twin
  current state and revision history per entity. snapper-ai aligns state across
  multiple components.
- [AWS IoT Device Shadows](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-document.html)
  demonstrate publisher-owned current JSON, versions, accepted updates, and
  change detection. snapper-ai adds coherent durable history.
- [Home Assistant](https://www.home-assistant.io/docs/configuration/state_object/)
  and its [Recorder](https://www.home-assistant.io/integrations/recorder) show the
  practical value of integration-owned current state plus generic recording;
  snapper-ai records system cuts across independently maintained components.
- [Kubernetes API machinery](https://kubernetes.io/docs/reference/using-api/api-concepts/)
  demonstrates generic resources, revisions, consistent collection reads, and
  reliable change observation. snapper-ai applies related mechanics to durable
  operational memory.
- [Graphiti/Zep](https://github.com/getzep/graphiti) provides temporal context
  for AI agents by extracting and reconciling semantic facts. It can complement
  snapper-ai's authoritative producer-owned evidence.
- [Palantir Foundry and AIP](https://www.palantir.com/docs/foundry/agents/overview)
  validate the value of a shared operational world for humans and AI at broad
  enterprise scale. snapper-ai provides a small, focused general service.

The pieces exist many times over. The distinct product is their conjunction:
authoritative subsystem-maintained now, efficient coherent history,
self-description across evolution, and direct temporal retrieval for people,
applications, and AIs.

## Implementation boundary

snapper-ai is a generic, factorized service in its own repository. Its core
knows scopes, components, registrations, JSON state, versions, hashes, capture
policy, and temporal retrieval. Domain knowledge for SWF, PanDA, testbed state
machines, epicprod campaigns, and monitor pages stays in adapters.

SWF and epicprod provide the initial integration and deployment. Their component
definitions, database adapters, publisher authentication, SysConfig keys,
process wiring, event resolvers, liveness alarms, and bootstrap plan are defined
in [SWF_EPICPROD_INTEGRATION.md](SWF_EPICPROD_INTEGRATION.md).

Capture has one active writer per scope, enforced by the scope interlock. A
deployment may run multiple contenders for failover. Deployment count,
scheduler heartbeat, and alarm behavior belong to the integration contract.

## Decisions intentionally left empirical

- full-only storage versus component-delta optimization;
- measured production cadence and retention;
- exact registration-schema vocabulary and validation subset;
- database-specific locking and notification mechanics; and
- long-term rollups or derived caches justified by query volume.

Observed use should justify added machinery. The core remains centered on
registered current state, coherent capture, durable history, and temporal
retrieval.
