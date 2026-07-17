# snapper-ai

> A small, efficient system that aggregates subsystem-owned **now** into
> coherent, durable, AI-readable history.

snapper-ai turns operational state into operational memory. It is a snapper of
histories: subsystems publish their present state, and snapper-ai records that
state as a sequence of coherent system-wide snaps.

The `-ai` names the primary consumer: an AI charged with reasoning and
inference across system histories. The deterministic, AI-free capture path
of snapper-ai provides operational memory that AIs can retrieve and reason over directly.
Pages, plots, reports, and incident reviews use the same history.

## Why

Operational systems usually know what is happening now and record some exact
events. They rarely preserve a direct answer to a simpler question: what did the
whole system look like at an earlier time?

Reconstructing that answer later can require expensive database queries,
correlation across unrelated records, or facts that were never recorded with
usable lifetimes. Recovering the PanDA jobs running at a past instant, for
example, requires counting jobs whose start time precedes it and whose end time
follows it. Many other kinds of state have no recoverable history at all.

snapper-ai records history while the present state is already known. It turns
historical state from an inference problem into a retrieval problem.

The application was conceived for the PanDA workload-management ecosystem,
initially the ePIC streaming workflow testbed and epicprod production system.
Production progress and distributed processing activity are important to the
collaboration, valuable in diagnosis, and rich input for AI reasoning and
reporting. Prior-art research found several adjacent open-source systems;
focused development still offered the shortest path to this particular need.
The design therefore broadened into an application-agnostic service, with
PanDA/ePIC as its first integration.

## How it works

```text
subsystem owns and maintains its now
                 |
                 | publish complete component state
                 v
        current component registry
                 |
                 | aligned capture decision
                 v
        immutable system snap history
                 |
                 v
     people, applications, and AI agents
```

Each subsystem owns a bounded JSON **component** describing its current state.
Its registration supplies the shape, meaning, ownership, units, freshness, and
provenance needed to interpret that state. The mutable component registry holds
the latest accepted value from every owner.

Registration begins with a concrete retrieval need: state that consumers want
back, in a representation and temporal granularity that will be useful when
returned.

A submitted component state must be curated so that every change within it is a
change worth recording. The owner chooses the projection and its resolution;
snapper-ai then treats every canonical change as meaningful. Publishing a raw,
fast-changing gauge is therefore an explicit choice to drive snaps at that rate.

After an assessment, the owner either publishes a new curated state or reports
that it has nothing new. A no-change report refreshes assessment and liveness
metadata while leaving component content and revision unchanged. A snap at every
opportunity is also valid when that is the history consumers want.

At fixed, clock-aligned opportunities, snapper-ai checks a small revision vector.
A canonical component change makes a snap due. A periodic baseline records the
system even through long quiet periods. Quiet opportunities end before JSON
assembly, keeping the system inexpensive when little is happening.

A **system snap** is one immutable, versioned JSON structure containing a stable
cut across the registered components in a scope. Event streams retain exact
transitions; snaps retain coherent sampled state.

Coherence means a consistent read of the component registry. Components may
have been assessed at different times, so every component carries its own
assessment time and, when applicable, source time.

## The narrow design

snapper-ai provides authoritative system state across time, giving people and
AIs direct knowledge of how complex systems evolve.

Five properties define the product:

1. **Owner-published state.** Every component comes from the subsystem that
   maintains it.
2. **Coherent capture.** Every snap is a stable system-wide cut across those
   independently maintained states.
3. **Efficient history.** Cheap aligned checks, change-driven snaps, and periodic
   baselines fit both active and quiet systems.
4. **Evolutionary robustness.** Component schemas and capture practice evolve
   under explicit versions and policy epochs; old history remains interpretable.
5. **AI-native retrieval.** AIs receive authoritative temporal context with
   timestamps, hashes, provenance, and coverage status.

Capture stays deliberately simple: generic JSON, explicit metadata, content
hashes, bounded component state, and straightforward database ordering.

## What AIs can ask

The core retrieval surface answers questions such as:

- What is the latest recorded system state?
- What was the state at this time?
- What changed between these moments?
- How did this component evolve over the last day?
- What was pending when an incident began?
- Is a component's current state different from the latest recorded state?

The corresponding operations are `latest`, `state_at`, `changes_between`,
`component_history`, and `context_around`. Results include actual snap and source
times, schema and policy versions, provenance, and observer-coverage status.
Exact transition sequences remain available from event streams joined around a
snap.

## Initial applications

The first registration set is intentionally small:

| Scope | Initial components |
|---|---|
| both | system health and assessment freshness |
| testbed | datataking state, workflow activity, agent state, data activity |
| epicprod | PanDA activity, production and campaign state, operational state |

The first high-value epicprod projection is current PanDA activity: jobs and
tasks by state, running jobs and cores, active task types, sites, and recent
outcomes. Recording that maintained now supplies concurrency history that is
otherwise expensive or impossible to recover later.

## Implementation

snapper-ai is packaged as a reusable Django application backed by PostgreSQL.
It contains no SWF, PanDA, testbed, or epicprod domain model. A hosting Django
project supplies runtime settings, database connection, routing,
authentication, logging, migrations, and process deployment.

The initial SWF application installs this generic package into the existing SWF
monitor runtime and uses its `swfdb` PostgreSQL database. That deployment is an
integration choice defined in
[SWF_EPICPROD_INTEGRATION.md](docs/SWF_EPICPROD_INTEGRATION.md), not part of the
generic Snapper product contract.

## Documentation

The [technical design](docs/DESIGN.md) defines registration, publication,
capture, snap representation, evolution, query semantics, AI evidence,
efficiency, and the implementation boundary.

The [SWF and epicprod integration](docs/SWF_EPICPROD_INTEGRATION.md) identifies
the deployment contracts that connect the generic service to its first users.

The original detailed exploration remains available as a
[superseded early design](docs/archive/SNAP_EARLY_DESIGN_SUPERSEDED.md).

## License

snapper-ai is licensed under the [Apache License 2.0](LICENSE).
