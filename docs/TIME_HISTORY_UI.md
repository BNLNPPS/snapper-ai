# Time history — display design

The design of the Snapper report page's temporal display, set 2026-07-23
after operator review of the first build. The quality bar is explicit:
a display that would not embarrass us in the HL-LHC or ePIC control
room. Prior art: Perfetto's track-plus-selection-panel model, Grafana's
state-timeline and shared-crosshair discipline, control-room strip
tools' single state-color vocabulary.

The delivered display in both scopes, served publicly:
[epicprod](https://epic-devcloud.org/prod/snapper/epicprod/report/?window=24h) ·
[testbed](https://epic-devcloud.org/prod/snapper/testbed/report/?window=7d).

[![The epicprod report page](snapper-epicprod.png)](https://epic-devcloud.org/prod/snapper/epicprod/report/?window=24h)

*epicprod: the health lane and stacked curve panels — in-flight jobs and
tasks by state — with per-curve selection controls, over a 24-hour window.*

[![The testbed report page](snapper-testbed.png)](https://epic-devcloud.org/prod/snapper/testbed/report/?window=7d)

*testbed: full-height namespace activity bands carrying workflow datataking
and processing tiles, the health lane, and the time cut's per-run component
cards below the tracks, over a seven-day window.*

## Three zones, one time axis

1. **Tracks** — set 2026-07-24 after operator review at wide windows:
   namespace lanes are full-height bands carrying true workflow
   activity periods. A continuous grey track says the namespace exists
   and is idle; discrete tiles interrupt it where workflows actually
   ran — a solid tile for the datataking window opening into a lighter
   tile for the processing tail, assembled from the state-event record
   where it exists and the universal run record otherwise, workflow
   identity joined through the execution record. A run with no
   recorded end renders hatched. Tiles keep a zoom-aware minimum
   visual width so short runs read as blocks at any scale, with true
   proportions returning on zoom; the plot enhances the truth into
   legibility (set 2026-07-26) — the minimum is a legible block, never
   a sliver. The goal is twofold and the layout serves it directly
   (set 2026-07-26): fast drill into what's happening at a time, and
   fast big-picture overview. Three stacked surfaces, one job each,
   inside the one unchanged click model — a click IS a vertical time
   slice, the red line lands at the clicked instant and the URL
   carries it (?cut=). First the plot: lanes and the cut, no markers.
   Second a thin notice slot directly under the plot: the health card
   when the slice is taken on the health lane (a component-narrowed
   cut, ?component=, that builds only that card), the empty-slice
   notice otherwise when the slice crosses nothing — never silent —
   and the classic state cards on scopes without activity lanes
   (epicprod) — the scope's own components when the provider declares
   them (`scope_components`), so a component with a dedicated focus
   view keeps its card, and its build cost, on that view. A
   component-narrowed cut at an instant with no record
   of that component at or before it renders a "no record" card
   naming where the record begins, with a link that cuts there. A
   focus view lands with its default cut half a recording interval
   back from the window's end — the component's change cadence, read
   from its recent change-bearing snaps — so the page opens on the
   latest recorded state; the cut never lands before the component's
   first recorded snap, so a record younger than the window does not
   open on an empty instant. Third the overview table, in its own scroll pane
   sized to the full table height: the at-a-glance inventory of the
   window, newest first, time leftmost with elapsed length, and the
   detail home. The whole table is visible on the page — page
   scrolling browses it and never clips it — and nothing pins except
   the slim Time history strip (window controls and Now), which
   stays in reach anywhere down the table. A slice highlights and
   expands the crossed events' story subentries and scrolls the pane
   — never the page — so that section lands flush at the pane top,
   immediately below the plot, the position a pop-in would occupy;
   in-pane bottom fill makes this hold down to the very last row. A
   row click is event-scoped: it toggles that one story subentry. Color cues:
   greens belong to health; events are blue — the datataking tile,
   its lighter processing tail, and the table's highlight share the
   blue family. A horizontal lane tick row above the plot, carrying
   its own All on/off, defines the shown truth everywhere (default
   all on, URL ?hide=): an unticked lane disappears from the PLOT, the table, and
   the slice alike — reviewing one operator's activity must not be
   polluted by another's — and the plot reclaims its vertical room.
   Namespaces will multiply (subdetectors, calibrations and their
   kin; eventually a hierarchy): be efficient in what is shown,
   flexible in deciding what is not. A Now button in the card header
   slices at the window's end, homes a zoomed view to it, and stays
   in track-now — re-homing and re-slicing as the page updates —
   until toggled off (the slice then stays fixed) or the user clicks
   or pans elsewhere. The report page
   is the Time history alone: the snap record (recorded state,
   component and snap audit documents, paginated history) lives on
   its own Snap history tab — one home per story. State values in
   story tables render with the application's standard state fills.
   There are no numbers: the table's pop-in position removed their
   job (bridging plot clicks to table rows), and with it the
   numbered/unnumbered asymmetry. Continuous state lanes (health, its
   expandable per-check sub-lanes) keep edge-to-edge bands. Recovery
   gaps are grey spans painted beneath, never over. No pips: a tile's
   leading edge is the run start.
2. **Stacked curve panels** — one compact panel per family (in-flight
   jobs, tasks, job types, type-by-state; later sites and health
   counts), each with its own y-scale and legend row, sharing the
   x-axis, crosshair, and slider.
3. **Selection panel** — never raw JSON first. Two gestures feed it:
   - **Cut (click)**: server-rendered component cards
     (`/snapper/<scope>/cut/?time=`). Consistency is by construction:
     the datataking card derives from the same run-record arcs the
     lanes draw — datataking / processing / idle per namespace with
     run and workflow — so what the bands show at the cut line is what
     the cards say. A click on a tile's inflated minimum-width extent
     snaps the cut into the activity itself; clicked green is green
     below, at any zoom. Health shows chips with non-ok check rows;
     panda shows headline stats with deltas against the previous snap.
     Every entity reference is a link; raw documents sit behind
     explicitly labeled audit foldouts; exact-event links land on
     human pages.
   - **Selection (drag a range)**: the interval story —
     changes-between summarized as field-level previous → current
     rows, plus per-curve min/mean/max over the selection.

## Cross-cutting contracts

One state-color vocabulary shared by bands, chips, and cells; stable
curve colors per curve id; Eastern time on every surface; all view
state in the URL; per-user remembered preferences; evidence honesty
throughout (actual snap times, coverage never inferred).

## Delivery landings

1. **Done (2026-07-23):** the cut as structured component cards with
   deltas and resolver links.
2. **Done (2026-07-24):** stacked per-family panels with own
   y-scales, crosshair across panels, expandable lane headers, and the
   activity-band tracks with the consistent click-snapped cut.
3. Dropped (operator decision 2026-07-24): drag stays zoom; no
   selection gesture swap.
4. **Done (2026-07-25):** window step-arrows through the recorded
   history — an arrow is absent only at a true edge, 'now' or the
   earliest snap; stepping loads the adjacent range server-side and
   the custom badge names the range. Same day the display moved into
   the snapper_ai package behind the provider registry; curve families
   and labels are provider data ([INTEGRATION.md](INTEGRATION.md)).
5. **Done (2026-07-27):** embeddable curves-only panels for host
   pages — matching colors, a click opening this display; first host
   is the SWF monitor's PanDA activity page ([INTEGRATION.md
   §4](INTEGRATION.md), README).
6. **Done (2026-07-29):** terminal outcomes as window-relative
   cumulative counters. A terminal transition is a point event — the
   job leaves the in-flight population at its end time — so finished
   and failed render as staircases rising from zero at the window's
   left edge: the displayed window is the integration range, zooming
   or panning re-bases the staircases at the view's left edge, and
   the value at the view's right edge is the interval total. Drag
   remains zoom. The cut reports outcomes on the same basis (the cut
   request carries the view's left edge) and its detail is a table,
   one row per curve in panel order with the row's swatch in the
   curve's color. A focus view tells its story in one plot; secondary
   families (failure classes, tasks) sit behind rotators, closed by
   default, and every family section carries the rotator. When
   several panels stack, the top panel draws its own date labels so
   it stands alone in a screenshot. First user: the epicprod Site
   focus (per-site job lifecycle). Remembered curve selections are
   versioned with the curve vocabulary, as the series cache is —
   selections recorded against an old vocabulary are stale wholesale.

## Grafana position

Decided 2026-07-23: the monitor's own display is the product face —
the cut is its heart and cannot live in a dashboard tool. Grafana (the
SDCC-supported service) is a future satellite: snapper series shipped
to collaboration-visible dashboards (the MONIT pattern), provisioned
as code, consuming the same REST/SQL truth with zero coupling — a
Phase-7-adjacent add-on, not the primary display.
