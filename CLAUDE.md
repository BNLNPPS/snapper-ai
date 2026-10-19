# snapper-ai

Start from the SWF workspace guide, `../swf-testbed/CLAUDE.md`
(<https://github.com/BNLNPPS/swf-testbed/blob/main/CLAUDE.md>): the
system, the workspace, how to work, production and collaboration. This
file adds what is particular to snapper-ai, the agnostic core that
aggregates subsystem state into coherent, durable history (`README.md`).

- The core is agnostic: SWF's providers and pages live in swf-monitor,
  registered with the core (README, Boundary). A change that names an
  SWF subsystem belongs there, not here.
- Documents in `docs/`: DESIGN, IMPLEMENTATION, INTEGRATION, and
  DEVELOPMENT for the branch workflow across this repository and the SWF
  core.
- Developed on `main`; its SWF integration commits go to the core
  repositories' current `infra/baseline-vNN` branch (docs/DEVELOPMENT.md).
  It reaches production with the swf-monitor full deploy.
