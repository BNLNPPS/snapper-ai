# Episodes: event-fed bounded records

Snapper scopes record ongoing systems: components are captured at
aligned boundaries, and the snap sequence is the record. Episodes
extend the model to bounded activities — a workflow execution, from
launch to teardown — where the record is the event sequence itself,
at its native (sub-second) resolution, and boundary-aligned capture
plays no role.

The first host application is the swf-testbed agentic workflow view
(swf-testbed `docs/agentic-workflow-view.md`): one workflow execution
rendered as dynamic lanes for agents and workers with message marks
between them, live while the execution runs and replayable afterward.
The mechanism is generic and carries no host vocabulary.

## Model

- **Episode** — a bounded record keyed by scope and a host-supplied
  episode id, with start time, end time (null while live), a label,
  and the host's summary document. Episodes belong to a scope; the
  scope's provider declares how they are discovered.
- **Episode events** — the record. Each event carries a timestamp, a
  type, a participant id, an optional counterpart participant id
  (for events that connect two lanes, such as recorded message
  consumption), and a bounded payload document. Events are written
  by an episode builder in the host, not by Snapper.
- **Participants** — the lane identities: id, label, kind
  (host-defined), birth and death times. Participants arrive with
  the events that introduce them; the lane roster is derived, not
  pre-declared.

Episodes are durable records. The builder assembles them from the
host's operational sources (message logs, registries, workload
records); once captured, replay does not depend on those sources'
retention.

## Capture

The host runs the episode builder. Two modes, both supported by the
same record shape:

- **Prompt capture** — the builder runs at execution end and writes
  the complete episode.
- **Live capture** — the builder appends events while the execution
  runs; the episode's end time is set at teardown. The view follows
  by polling or by the host's push channel; either way the episode
  record is the single source.

## Rendering

The episode view reuses the Time history vocabulary: horizontal lanes
over a time axis, activity tiles, the cut as a time slice, the
in-house floater, step arrows. Episode-specific behavior:

- **Dynamic lanes.** A lane begins at its participant's birth event
  and ends at its death event. A dead participant's lane keeps its
  vertical slot for the remainder of the episode, rendered dimmed,
  so the plot's shape is stable over the whole replay.
- **Connectors.** Events with a counterpart participant render as
  marks on the source lane with a connector to the counterpart lane.
  Events without a counterpart render as marks on their own lane.
- **Detail cards.** A click on any element opens its detail card
  through the established card machinery; the provider supplies card
  builders per event kind, as component and activity cards work
  today.
- **Stepping.** The step arrows step the time window within the
  episode. An episode-stepping mode — arrows move to the previous or
  next episode of the same scope — is a candidate addition to the
  same control.
- **Live follow.** For an open episode the view tracks the growing
  end, in the manner of the report page's track-now mode.

## Provider surface

An `EpisodeProvider` registration parallel to `ScopeProvider`:

| Field | Role |
|---|---|
| `list_episodes` | scope → recent episodes for the picker |
| `episode` | episode id → episode record with events |
| `participant_label` / `participant_kind` | lane identity and grouping |
| `event_cards` | event kind → detail card builder |
| `episode_card` | the episode's own summary card |

Hosts register providers from `AppConfig.ready()` as today. The
generic package defines the episode and event storage, the queries,
and the view; the host defines the builder and the presentation
specifics.

## Relation to scopes

Episodes do not replace scope capture. A scope may have both: the
tick-and-change snap record for the ongoing system, and episodes for
its bounded activities. The testbed scope keeps its report page; its
executions gain episode records. Cross-navigation is expected in both
directions: an activity tile on the report page links to its episode;
an episode links back to its position in the scope history.
