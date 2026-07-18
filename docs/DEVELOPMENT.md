# snapper-ai development workflow

This repository and its SWF host integrations use different branch workflows.
Keeping that distinction explicit is necessary because a Snapper change often
touches both the reusable package and coordinated SWF core repositories.

The authoritative system-wide SWF workflow is the
[SWF Testbed Development Guide](https://github.com/BNLNPPS/swf-testbed/blob/main/docs/development.md).
This document states how that workflow applies to Snapper work.

## Repository and branch ownership

| Repository | Development branch |
| --- | --- |
| `snapper-ai` | `main` |
| `swf-testbed` | current coordinated `infra/baseline-vNN` |
| `swf-monitor` | current coordinated `infra/baseline-vNN` |
| `swf-common-lib` | current coordinated `infra/baseline-vNN` |

`snapper-ai` is a solo-development exception and is developed on `main`.
That exception does not extend to its host integration code.

All Snapper integration commits in the SWF core repositories must go to the
current coordinated `infra/baseline-vNN` branch, with the same baseline number
used across the core repositories. At the time this rule was recorded, the
working branch was `infra/baseline-v40`; always confirm the current baseline
before starting work rather than treating that number as permanent.

Do not push Snapper integration commits directly to a core repository's
`main`. Baselines reach `main` through coordinated pull requests at delivery
boundaries.

## Starting integration work

Before editing a core repository:

1. Read the current branch from the SWF development/release documentation and
   confirm the corresponding remote branch exists.
2. Inspect `git status -sb` and `git worktree list`.
3. Work on the current `infra/baseline-vNN`, preserving the matching branch
   across every affected core repository.
4. Commit and push each repository's integration change to that baseline
   branch.
5. Keep package changes in `snapper-ai` on `main` and integration changes in
   their owning SWF repositories; do not copy domain adapters into the generic
   package.

## Shared checkout safety

The core repositories on `pandaserver02` are shared working trees. Uncommitted
files may belong to another active development session.

- Never stash, reset, checkout, switch, merge, or overwrite a shared checkout
  that contains work you do not own.
- Use a temporary Git worktree when branch reconciliation or isolated work is
  required while the shared checkout is dirty.
- Stage only the files owned by the current task.
- Remove the temporary worktree after its branch is pushed and verify that the
  shared checkout's status is unchanged.

For example, to reconcile an accidental core-repository `main` commit into the
active baseline without touching the shared checkout:

```bash
git -C /path/to/core-repo worktree add /tmp/core-baseline-vNN infra/baseline-vNN
git -C /tmp/core-baseline-vNN fetch origin
git -C /tmp/core-baseline-vNN merge origin/main
git -C /tmp/core-baseline-vNN push origin infra/baseline-vNN
git -C /path/to/core-repo worktree remove /tmp/core-baseline-vNN
```

Use a uniquely allocated temporary path in real work. Inspect the merge before
pushing, and preserve a true merge when both sides have commits so the baseline
records both lines of development.

## Deployment rule

During an active coordinated baseline, deploy the SWF monitor from that
baseline, not from `main`:

```bash
./deploy-swf-monitor.sh branch infra/baseline-vNN
```

A deployment from core-repository `main` can omit work that exists only on the
active baseline. Deployment does not change the branch workflow: first put the
integration commit on the coordinated baseline, then deploy that branch when
the deployment is authorized. The baseline is merged to `main` only at the
coordinated delivery boundary.
