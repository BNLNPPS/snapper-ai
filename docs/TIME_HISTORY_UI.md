# Time history — display design

The design of the Snapper report page's temporal display, set 2026-07-23
after operator review of the first build. The quality bar is explicit:
a display that would not embarrass us in the HL-LHC or ePIC control
room. Prior art: Perfetto's track-plus-selection-panel model, Grafana's
state-timeline and shared-crosshair discipline, control-room strip
tools' single state-color vocabulary.

## Three zones, one time axis

1. **Tracks** — state lanes as horizontal bars (solid when active,
   pastel when not), run-start pips, recovery gaps as grey spans never
   painted over, an always-visible range slider as the horizontal
   scroll. Lane headers expand to detail sub-lanes (health to its
   non-ok checks).
2. **Stacked curve panels** — one compact panel per family (in-flight
   jobs, tasks, job types, type-by-state; later sites and health
   counts), each with its own y-scale and legend row, sharing the
   x-axis, crosshair, and slider.
3. **Selection panel** — never raw JSON first. Two gestures feed it:
   - **Cut (click)**: server-rendered component cards
     (`/snapper/<scope>/cut/?time=`). A yellow health period shows a
     yellow chip with its reason and non-ok check rows; datataking
     shows namespace/run/state chips; panda shows headline stats with
     deltas against the previous snap. Raw documents sit one click
     behind; exact-event resolver links sit below.
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
2. Stacked per-family panels, shared crosshair with unified readout,
   expandable lane headers.
3. Range-selection aggregation and the gesture swap (drag selects;
   shift-drag zooms; slider scrolls).

## Grafana position

Decided 2026-07-23: the monitor's own display is the product face —
the cut is its heart and cannot live in a dashboard tool. Grafana (the
SDCC-supported service) is a future satellite: snapper series shipped
to collaboration-visible dashboards (the MONIT pattern), provisioned
as code, consuming the same REST/SQL truth with zero coupling — a
Phase-7-adjacent add-on, not the primary display.
