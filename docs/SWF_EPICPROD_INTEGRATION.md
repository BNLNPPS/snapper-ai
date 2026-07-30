# SWF and epicprod integration

This document is the integration contract between the generic snapper-ai
service and its first deployments: the streaming workflow testbed and epicprod.
It names the integration decisions and ownership required for bootstrap. The
generic capture and query contract remains in [DESIGN.md](DESIGN.md); current
execution order and progress live only in [PLAN.md](PLAN.md).

Integration development and deployment must follow the repository/branch
boundary in [DEVELOPMENT.md](DEVELOPMENT.md): the generic snapper-ai package is
developed on its main branch, while changes in swf-testbed, swf-monitor, and
swf-common-lib go to the current coordinated infra/baseline-vNN branch and are
deployed from that branch until the baseline delivery boundary.

## Integration boundary

snapper-ai owns component registration, canonical publication, the current
component registry, coherent capture, immutable history, and temporal retrieval.

The initial integration installs snapper_ai as a Django application in the SWF
monitor runtime, in the same pattern as the installable pcs application from
swf-epicprod. Its models use the monitor's default PostgreSQL connection and
therefore create snapper-prefixed tables in swfdb. There is no second database,
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
| both | System health (health) | System status maintainer | assessed health transitions and bounded status summaries |
| testbed | Datataking state (datataking) | datataking state owner | per-namespace operational state transitions, run identity, transition time |
| testbed | Workflow activity (workflows) | workflow-state maintainer | bounded active-work summaries and outcome aggregates |
| testbed | Agent status (agents) | agent-status maintainer | bounded instance map with operational and assessed health state |
| testbed | Data activity (data) | data-state maintainer | bounded queues, file and slice state, rounded recent throughput |
| epicprod | PanDA activity (panda) | PanDA activity maintainer | curated job, core, site, and task summaries at declared count/rate resolution |
| epicprod | Production activity (production) | campaign-state maintainer | campaign progress, outputs, bytes, placement, and data arrival summaries |
| epicprod | Operations activity (ops) | epicprod ops maintainer | agent state, actions, alarms, and assessment execution |

Before enabling a component, its owner must complete its quantity registration,
publication trigger, curation resolution, freshness and assessment policy,
maximum serialized size, visibility, and related event sources.

The PanDA projection requires an explicit commissioning choice. Publishing raw
job counts grouped by state makes every canonical count change meaningful and can
drive epicprod snaps at every opportunity. Bucketed counts, rounded rates, or
another curated representation reduce that rate when they preserve the history
users and AIs need. This is a PanDA maintainer decision recorded in its component
contract. The maintainer may report no change after any assessment that leaves
the curated projection unchanged.

### System-health component (health), version 1

The first real component represents assessed System health. Its internal name
is health, and it exists in exactly two scopes: testbed and epicprod. Its
authenticated publisher identity is swf-monitor:system-status; the SWF adapter derives that identity server-side
and never accepts it from a request payload.

The authoritative source is the current SystemStatus registry after a
completed refresh. The initial scope membership is explicit:

| Scope | Included System status checks |
|---|---|
| testbed | swf-monitor-mcp-asgi, httpd, github-actions |
| epicprod | the three shared checks plus epicprod-ops-agent, swf-panda-bot, campaign-assessments, epic-devcloud-prod, and epic-devcloud-doc |

The bot-usage check is informational and does not enter health history. New checks do
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
advancing check timestamps stay in SystemStatus and its history rather than
forcing Snapper revisions. The assessment time is when the scoped projection is
evaluated; the source time is the oldest non-null check time among its included
checks. Any included row older than the existing 15-minute System status
threshold is projected as an error. The overall status and reason are then
computed deterministically from the scoped rows. These timestamps update on an
identical publication without advancing the component revision.

The historical question is: *what health did SWF assess for this scope, which
checks determined it, and when was the oldest source check made?* Visibility is
public, the assessment policy is swf-system-status-v1, and the stable event
resolver identifier swf-system-status-history is registered for exact check
transitions. Its concrete System status history API or MCP mapping remains part
of the event-resolver tranche.

### Datataking-state component (datataking), version 2

The first state component represents datataking state in the shared testbed
scope. Its internal name is datataking. It is
the initial concrete realization of the vertical cut through the
[ePIC E0-E1 global-state model](https://github.com/BNLNPPS/swf-testbed/blob/main/docs/images/e0-e1-global-state-v1.svg):
the latest component state marks the independent datataking lane for every
namespaced testbed at the present instant, while recorded snaps show how those
lanes evolve with the rest of the shared platform.

The brief v1 singleton projection is superseded. Version 2 represents the
platform as it is operated: multiple independently namespaced testbeds sharing
common infrastructure.

Its server-derived publisher identity is swf-monitor:run-state. The authoritative
source is the highest-numbered RunState row in each namespace. The adapter
resolves the execution ID in RunState metadata through the corresponding
WorkflowExecution namespace; legacy executions without a namespace do not
enter this projection. Namespace membership is discovered from those records,
not configured in Snapper, so a namespace enters automatically with its first
RunState. Creation of a run and a semantic change to phase, state, or substate
publish the complete namespace map immediately in the same database
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
KiB. Within each namespace, substate is omitted when the state model does not
define one, and the last-transition time carries the authoritative state-change
time. The assessment time is the adapter evaluation time. The source time is
unset because no single source timestamp represents the
independently evolving namespace states. Visibility is public and the
assessment policy is swf-datataking-state-v1.

The historical question is: *where did the recorded vertical cut intersect the
datataking lane for each namespace, for which run, and when did each state
begin?* Snap history provides coherent sampled evolution. The stable resolver
identifier swf-testbed-system-state-events is registered for the authoritative
SystemStateEvent stream. Concrete resolution, including namespace-to-run
selector translation, remains part of the event-resolver tranche.

### PanDA-activity component (panda), version 3

This epicprod state component represents PanDA job, task, core, and site
activity. Its internal name is panda. Its server-derived publisher identity is
swf-monitor:panda-activity, and its authoritative source is the existing SWF
PanDA monitor query layer over the ePIC PanDA database.

The brief v1 projection recorded current running jobs and cores but did not
distinguish the rest of the in-flight population from the trailing activity
window. Version 2 records every current in-flight job state explicitly.
Version 3 adds the corresponding current nonterminal JEDI task states and
target-site counts.

The supervised ops agent publishes the component after each full five-minute
System status refresh. Snapper does not query PanDA during capture. Each
publication reads the existing trailing 24-hour aggregate, a lightweight
current in-flight query over jobsactive4, and a nonterminal task aggregate over
jedi_tasks, then removes users and individual job and task records before
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
the task-type map to 32 types, and canonical component JSON to 64 KiB. Both site
maps retain every non-test queue in the Canary catalog, including explicit zero
state for inactive queues. Remaining job-site slots rank by current in-flight
work and then trailing job volume; remaining task-site slots rank by current
nonterminal task count. Current in-flight job states are defined, waiting,
assigned, activated, sent, starting, running, holding, transferring, and
merging. Current tasks are all JEDI states except done, finished, failed,
broken, aborted, exhausted, and passed. The component records raw integer
counts at five-minute observation resolution: a count change between
maintainer runs is meaningful, while changes inside that interval intentionally
collapse into the next maintained state.

Version 4 adds current in-flight job counts by processing type and by type
and status, bounded to 16 types with the smallest rolled into 'other'.

Version 5 records terminal outcomes as monotonic cumulative counters:
`jobs.cum` by status (finished, failed, cancelled, closed) and, per site,
`cum` plus `cum_failed_by_class` over the monitor's error-component classes.
Each publication counts completed jobs with end times after the previous
publication's source time (active and archived tables, deduplicated) and adds
them to the counters read from the component's current state; a current state
without counters seeds from the full recorded job history, so the absolute
origin is the database epoch and every consumer differences two instants.
When a Canary catalog queue first enters the current component, its per-site
counters are initialized from full PanDA history through the previous
publication mark before the current delta is applied. Catalog queues are not
evicted. An activity-derived site outside the catalog can be evicted from the
bounded map and loses its per-site counters when that happens; the scope-level
counters are unaffected. The swf-monitor script
`scripts/backfill-panda-counters.py` reconstructs the counters at an hourly
grid of historical instants as `backfill-panda-v1` snaps sharing the same
absolute origin, covering activity recorded before the version-5 publisher
deployment.

The assessment and source times are the completed-query time. Visibility is
public and the assessment policy is swf-panda-activity-24h-v3. The historical
question is: *how much PanDA work was active, what states were its jobs and
tasks in at each target site, and how did recent outcomes evolve?* The stable
resolver identifier swf-panda-activity-history is registered for exact PanDA
task and job context. Its concrete activity or action-history mapping remains
part of the event-resolver tranche.

## Adapter and transaction wiring

Existing current-state stores remain authoritative. Their maintainers publish
the bounded snap-visible projection after completing source-specific work such
as remote access, joins, aggregation, and health assessment.

For local mutations, publication should share the authoritative database
transaction so current application state and the component registry advance
together. Periodic remote maintainers publish after a completed refresh and
carry both assessment and source times.

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

The deployed mapping (2026-07-23) lives in
`monitor_app.snapper_resolvers.RESOLVER_MAP`; the context REST endpoint
(`/api/snapper/<scope>/context/`) and the `snapper_context_around` MCP
tool attach each reference's concrete transport, and an unmapped
resolver stays unknown rather than being claimed available:

| Resolver identifier | Component | Target |
|---|---|---|
| `swf-system-status-history` | health (both scopes) | `/api/system-status/history/` (name, start, end) |
| `swf-testbed-system-state-events` | datataking | `/api/system-state-events/` (run_number, event_type, state) |
| `swf-panda-activity-history` | panda | `/api/panda/tasks/` plus the `panda_*` MCP tools |

Future components (workflow, production, and operations activity) add
their declarations and rows here as they are contracted in Phase 6.
Each mapping defines selector translation, event-time field, and
availability reporting. Stable resolver identifiers remain constant
when deployment URLs change.

## Presentation integration

Since 2026-07-25 the Snapper UI ships in the package and the swf host
supplies its presentation specifics by registration
([INTEGRATION.md](INTEGRATION.md) is the generic guide):

- `swf_monitor_project/urls.py` mounts `snapper_ai.urls` at `snapper/`,
  a project-level peer of the other installed applications.
- `monitor_app/snapper_providers.py` registers the epicprod and testbed
  ScopeProviders — curve extraction from the panda and workflow
  components, curve labels and families, the panda / workflow /
  datataking card builders, and the testbed run-arc activity lanes —
  and the host hooks: UserPreference-backed preferences, SysConfig
  values, scheduler status rows, and the System page URL. Registration
  runs in `MonitorAppConfig.ready()`.
- `monitor_app/templates/monitor_app/_snapper_cards.html` renders the
  provider card kinds with their links into monitor surfaces; the
  provider declares it as its card template.
- `monitor_app/snapper_resolvers.py` remains the event-reference
  resolver mapping and is registered per scope as the reference
  annotator.

## Query and visibility wiring

The integration assigns every registered quantity and event source a public,
operator, or internal visibility. API, page, MCP, and AI callers receive the
same logical snap under their authorized projection.

State-at and context-around queries must surface component assessment and source
times so users and AIs can distinguish registry coherence from simultaneous
source observation. Event-reference resolution applies the caller's normal
authorization to the authoritative event source.

## Bootstrap sequence

This is the integration acceptance sequence, not a second progress tracker.
See [PLAN.md](PLAN.md) for completed, current, and pending work.

1. Install the current-component, system-snap, and capture-cursor schema.
2. Deploy the shared registration and publication helper with publisher
   authentication.
3. Register and publish System health for both scopes.
4. Start one supervised scheduler and verify heartbeat, quiet checks, manual
   capture, failure, and recovery behavior.
5. Add one testbed state component and the curated epicprod PanDA-activity component.
6. Run full-only commissioning at the higher cadence and measure change rate,
   per-component snap contribution, no-change rate, row size, assembly time,
   lock time, and query behavior.
7. Validate latest and state-at queries, component history, change queries, coverage
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
