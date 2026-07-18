# SWF and epicprod integration

This document is the integration contract between the generic snapper-ai
service and its first deployments: the streaming workflow testbed and epicprod.
It names the decisions and ownership required before bootstrap. The generic
capture and query contract remains in [DESIGN.md](DESIGN.md).

## Integration boundary

snapper-ai owns component registration, canonical publication, the current
component registry, coherent capture, immutable history, and temporal retrieval.

The initial integration installs `snapper_ai` as a Django application in the
SWF monitor runtime, in the same pattern as the installable `pcs` application
from `swf-epicprod`. Its models use the monitor's default PostgreSQL connection
and therefore create `snapper_*` tables in `swfdb`. There is no second database,
standalone web server, or independent authentication stack. SWF owns route
mounting, REST and MCP authentication, AppLog integration, environment
configuration, release deployment, and migration execution.

SWF and epicprod own:

- the processes that maintain each component projection;
- projection content, resolution, assessment, and freshness policy;
- publisher identities and credentials;
- adapters from authoritative state to component publication;
- mappings from registered event resolvers to existing APIs or MCP tools;
- scheduler deployment and supervision;
- System status and alarm integration; and
- database migration, retention, and operational configuration.

## Publisher trust and authentication

Every component has one registered publisher identity. The publication path
authenticates that identity and verifies its authority over `(scope,
component)` before accepting registration or data.

The initial integrations support two paths:

1. **Direct database publication.** A maintainer already using the monitor
   database calls the shared publication helper in the same transaction as its
   authoritative local update where practical. Its database or service identity
   maps to an allowlist of component names.
2. **Authenticated message ingress.** A process without database access sends a
   complete registration and component projection through an authenticated
   transport. A thin generic ingress validates the transport identity and calls
   the same publication helper.

Both paths expose `report_component_unchanged(...)`. A maintainer can assess its
source every cycle and affirm the current curated projection without resending
its payload. This updates assessment, source, and liveness metadata while
preserving the component revision.

The integration must define credential issuance, rotation, revocation, and the
identity-to-component mapping before the first external publisher is enabled.
Component registration changes require the same ownership check as data
publication.

## Initial component catalog

The component owner chooses a bounded projection whose canonical changes are
worth recording. The resolution column is part of the integration contract;
snapper-ai applies canonical comparison after this curation.

| Scope | Component | Initial maintainer | Projection and resolution |
|---|---|---|---|
| both | `health` | System status maintainer | assessed health transitions and bounded status summaries |
| testbed | `datataking` | datataking state owner | per-namespace operational state transitions, run identity, transition time |
| testbed | `workflows` | workflow-state maintainer | bounded active-work summaries and outcome aggregates |
| testbed | `agents` | agent-status maintainer | bounded instance map with operational and assessed health state |
| testbed | `data` | data-state maintainer | bounded queues, file and slice state, rounded recent throughput |
| epicprod | `panda` | PanDA activity maintainer | curated job, core, site, and task summaries at declared count/rate resolution |
| epicprod | `production` | campaign-state maintainer | campaign progress, outputs, bytes, placement, and data arrival summaries |
| epicprod | `ops` | epicprod ops maintainer | agent state, actions, alarms, and assessment execution |

Before enabling a component, its owner must complete its quantity registration,
publication trigger, curation resolution, freshness and assessment policy,
maximum serialized size, visibility, and related event sources.

The PanDA projection requires an explicit commissioning choice. Publishing raw
`jobs_by_state` counts makes every canonical count change meaningful and can
drive epicprod snaps at every opportunity. Bucketed counts, rounded rates, or
another curated representation reduce that rate when they preserve the history
users and AIs need. This is a PanDA maintainer decision recorded in its component
contract. The maintainer may report no change after any assessment that leaves
the curated projection unchanged.

### `health` v1 contract

The first real component is `health` in exactly two scopes: `testbed` and
`epicprod`. Its authenticated publisher identity is
`swf-monitor:system-status`; the SWF adapter derives that identity server-side
and never accepts it from a request payload.

The authoritative source is the current `SystemStatus` registry after a
completed refresh. The initial scope membership is explicit:

| Scope | Included System status checks |
|---|---|
| `testbed` | `swf-monitor-mcp-asgi`, `httpd`, `github-actions` |
| `epicprod` | the three shared checks plus `epicprod-ops-agent`, `swf-panda-bot`, `campaign-assessments`, `epic-devcloud-prod`, and `epic-devcloud-doc` |

`bot-usage` is informational and does not enter health history. New checks do
not enter a scope implicitly; the adapter mapping changes under review.

The complete revision-driving projection is:

```json
{
  "overall": {
    "status": "ok | warning | error | unknown",
    "reason": "bounded deterministic summary",
    "counts": {"ok": 0, "warning": 0, "error": 0, "unknown": 0}
  },
  "checks": {
    "stable-check-name": {
      "category": "stable category",
      "status": "ok | warning | error | unknown",
      "summary": "bounded operator-facing summary"
    }
  }
}
```

The map is limited to 128 checks, each summary to 500 characters, and the
canonical component JSON to 64 KiB. Raw collector data and continuously
advancing check timestamps stay in `SystemStatus` and its history rather than
forcing Snapper revisions. `assessed_at` is when the scoped projection is
evaluated; `source_as_of` is the oldest non-null `checked_at` among its included
checks. Any included row older than the existing 15-minute System status
threshold is projected as `error`. The overall status and reason are then
computed deterministically from the scoped rows. These timestamps update on an
identical publication without advancing the component revision.

The historical question is: *what health did SWF assess for this scope, which
checks determined it, and when was the oldest source check made?* Visibility is
public, the assessment policy is `swf-system-status-v1`, and the stable event
resolver `swf-system-status-history` points to the existing System status
history API or MCP adapter for exact check transitions.

### `datataking` v2 contract

The first state component is `datataking` in the shared `testbed` scope. It is
the initial concrete realization of the vertical cut through the
[ePIC E0-E1 global-state model](https://github.com/BNLNPPS/swf-testbed/blob/main/docs/images/e0-e1-global-state-v1.svg):
the latest component state marks the independent datataking lane for every
namespaced testbed at the present instant, while recorded snaps show how those
lanes evolve with the rest of the shared platform.

The brief v1 singleton projection is superseded. Version 2 represents the
platform as it is operated: multiple independently namespaced testbeds sharing
common infrastructure.

Its server-derived publisher identity is `swf-monitor:run-state`. The
authoritative source is the highest-numbered `RunState` row in each namespace.
The adapter resolves `RunState.metadata.execution_id` through the corresponding
`WorkflowExecution.namespace`; legacy executions without a namespace do not
enter this projection. Namespace membership is discovered from those records,
not configured in Snapper, so a namespace enters automatically with its first
RunState. Creation of a run and a semantic change to `phase`, `state`, or
`substate` publish the complete namespace map immediately in the same database
transaction. Slice counters and other run bookkeeping do not enter the
projection and do not advance its revision.

The complete revision-driving projection is:

```json
{
  "namespaces": {
    "test-zy": {
      "run_number": 101,
      "phase": "physics",
      "state": "running",
      "substate": "physics",
      "last_transition_at": "2026-07-18T12:00:00Z"
    }
  }
}
```

The map is limited to 128 namespaces and the canonical component JSON to 64
KiB. Within each namespace, `substate` is omitted when the state model does not
define one, and `last_transition_at` carries the authoritative
`state_changed_at` value. `assessed_at` is the adapter evaluation time.
`source_as_of` is unset because no single source timestamp represents the
independently evolving namespace states. Visibility is public and the
assessment policy is `swf-datataking-state-v1`.

The historical question is: *where did the recorded vertical cut intersect the
datataking lane for each namespace, for which run, and when did each state
begin?* Snap history provides coherent sampled evolution. The stable resolver
`swf-testbed-system-state-events` links the component to the authoritative
`SystemStateEvent` stream, using namespace-to-run selector translation, when an
exact intermediate transition sequence is required.

### `panda` v3 contract

The first epicprod state component is `panda`. Its server-derived publisher
identity is `swf-monitor:panda-activity`, and its authoritative source is the
existing SWF PanDA monitor query layer over the ePIC PanDA database.

The brief v1 projection recorded current `running` jobs and cores but did not
distinguish the rest of the in-flight population from the trailing activity
window. Version 2 records every current in-flight job state explicitly.
Version 3 adds the corresponding current nonterminal JEDI task states and
target-site counts.

The supervised ops agent publishes the component after each full five-minute
System status refresh. Snapper does not query PanDA during capture. Each
publication reads the existing trailing 24-hour aggregate, a lightweight
current in-flight query over `jobsactive4`, and a nonterminal task aggregate
over `jedi_tasks`, then removes users and individual job and task records before
publication.

The revision-driving projection is:

```json
{
  "window_hours": 24,
  "jobs": {
    "total_24h": 12720,
    "by_status_24h": {"running": 331, "finished": 3805},
    "in_flight_now": {
      "total": 161167,
      "by_status": {"activated": 160805, "starting": 100, "running": 262},
      "running_jobs": 262,
      "running_cores": 391
    },
    "sites": {
      "NERSC_Perlmutter_epic": {
        "jobs_24h": 1795,
        "finished_24h": 1532,
        "failed_24h": 3,
        "in_flight_jobs_now": 52771,
        "by_status_now": {"activated": 52514, "running": 257},
        "running_jobs_now": 257,
        "running_cores_now": 386
      }
    }
  },
  "tasks": {
    "total_24h": 19,
    "by_status_24h": {"running": 9, "done": 5},
    "by_type_24h": {"epicproduction": 9},
    "in_flight_now": {
      "total": 38,
      "by_status": {"running": 27, "ready": 10, "assigning": 1}
    },
    "sites": {
      "UM_GREX_PanDA_1": {
        "in_flight_tasks_now": 18,
        "by_status_now": {"running": 18}
      },
      "NERSC_Perlmutter_epic": {
        "in_flight_tasks_now": 9,
        "by_status_now": {"running": 9}
      }
    }
  }
}
```

Job and task status maps are limited to 32 entries, each site map to 32 sites,
the task-type map to 32 types, and canonical component JSON to 64 KiB. Job
sites with current in-flight work rank ahead of inactive sites, followed by
trailing job volume; task sites rank by current nonterminal task count. Current
in-flight job states are `defined`, `waiting`, `assigned`,
`activated`, `sent`, `starting`, `running`, `holding`, `transferring`, and
`merging`. Current tasks are all JEDI states except `done`, `finished`,
`failed`, `broken`, `aborted`, `exhausted`, and `passed`. The component records
raw integer counts at five-minute observation resolution: a count change
between maintainer runs is meaningful, while changes inside that interval
intentionally collapse into the next maintained state.

`assessed_at` and `source_as_of` are the completed-query time. Visibility is
public and the assessment policy is `swf-panda-activity-24h-v2`. The historical
question is: *how much PanDA work was active, what states were its jobs and
tasks in at each target site, and how did recent outcomes evolve?* The stable
resolver
`swf-panda-activity-history` supplies exact PanDA task and job context when a
sampled aggregate requires drill-down.

## Adapter and transaction wiring

Existing current-state stores remain authoritative. Their maintainers publish
the bounded snap-visible projection after completing source-specific work such
as remote access, joins, aggregation, and health assessment.

For local mutations, publication should share the authoritative database
transaction so current application state and the component registry advance
together. Periodic remote maintainers publish after a completed refresh and
carry both `assessed_at` and `source_as_of`.

The generic helper returns acceptance time, registration and component
revisions, whether canonical content changed, and whether current content
differs from the latest recorded snap. Integration code logs rejected
publications and exposes repeated validation or ownership failures through
System status.

## Scheduler and process wiring

Capture has one active writer per scope. A scope run lock enforces that rule;
multiple deployed contenders may provide failover while preserving single-
writer semantics.

The initial deployment must identify:

- the supervising process and service account;
- which process evaluates each scope;
- scheduler heartbeat storage and refresh interval;
- manual capture ingress and authorization;
- startup and shutdown behavior;
- database lock timeout and retry behavior; and
- the deployment path for independent failover when required.

Commissioning starts in full-only mode with 10-second opportunities and a
baseline every ten opportunities. The initial production target is a 30-second
opportunity and a five-minute maximum quiet interval. SysConfig owns these
values independently for testbed and epicprod.

## Liveness, failures, and alarms

System status tracks a scheduler heartbeat for each scope. Alarm thresholds are
derived from the configured opportunity interval so a cadence change also
changes the expected heartbeat window.

The operational integration reports at least:

- scheduler heartbeat age and latest evaluated boundary;
- latest check result and latest successful snap;
- consecutive capture failures;
- observer-coverage gap and recovery state;
- component publication rejection counts; and
- component publication, no-change, and revision rates;
- registered components whose maintained assessment is stale or unavailable.

A quiet scope remains healthy while boundaries continue to be evaluated. Snap
age alone is therefore an activity signal, while scheduler heartbeat is the
liveness signal. A missed boundary creates an explicit coverage gap. The next
successful boundary records a recovery snap and clears the alarm according to
the existing alarm recovery policy.

## Event resolver mapping

Each component registration declares related event sources using the generic
event-reference contract. This integration maps stable resolver identifiers to
concrete local services.

The initial mapping should cover:

| Component | Event context | Resolver target |
|---|---|---|
| `health` | assessed health transitions | System status history API or MCP tool |
| `datataking` | state transitions | testbed action or status stream |
| `workflows` | workflow transitions | SWF action stream |
| `panda` | task and job activity | PanDA activity or action-history adapter |
| `production` | campaign and placement activity | epicprod and Rucio action adapters |
| `ops` | operator and agent actions | epicprod action stream |

Each mapping defines authorization, selector translation, event-time field,
retention semantics, and availability reporting. Stable resolver identifiers
remain constant when deployment URLs change.

## Query and visibility wiring

The integration assigns every registered quantity and event source a public,
operator, or internal visibility. API, page, MCP, and AI callers receive the
same logical snap under their authorized projection.

`state_at` and `context_around` must surface component assessment and source
times so users and AIs can distinguish registry coherence from simultaneous
source observation. Event-reference resolution applies the caller's normal
authorization to the authoritative event source.

## Bootstrap sequence

1. Install the current-component, system-snap, and capture-cursor schema.
2. Deploy the shared registration and publication helper with publisher
   authentication.
3. Register and publish `health` for both scopes.
4. Start one supervised scheduler and verify heartbeat, quiet checks, manual
   capture, failure, and recovery behavior.
5. Add one testbed state component and the curated epicprod `panda` component.
6. Run full-only commissioning at the higher cadence and measure change rate,
   per-component snap contribution, no-change rate, row size, assembly time,
   lock time, and query behavior.
7. Validate `latest`, `state_at`, component history, change queries, coverage
   gaps, and event-reference resolution through API and MCP.
8. Add remaining components individually, with owner and alarm review for each.
9. Set production cadence and retention from measurements; evaluate delta
   encoding only after full-snap evidence justifies it.

## Production acceptance

The integration is ready for production when:

- every enabled component has an identified owner and authenticated publisher;
- curation resolution, freshness, schema, provenance, and size bounds are
  registered;
- scheduler liveness and capture failures reach the existing alarm system;
- coverage gaps and recovery are visible to queries;
- AI results surface component assessment and source times;
- each returned event reference resolves or reports a specific availability
  state;
- full-snap capacity measurements support the configured cadence and retention;
  and
- operational ownership and recovery procedures are documented.
