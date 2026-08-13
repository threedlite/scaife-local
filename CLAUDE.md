# Working in this repo

## Git: never run mutating git commands

**Do not run any git command that changes repository state, the index, the
working tree, or a remote — under any circumstances, including when the
user's request seems to imply it.** The user manages all commits themselves.

Forbidden (non-exhaustive):

`git commit` · `git add` / `git rm` / `git mv` / `git restore` / `git stash`
· `git checkout` / `git switch` / `git reset` / `git revert` /
`git cherry-pick` · `git merge` / `git rebase` / `git pull` ·
`git push` / `git fetch` / `git remote …` · `git branch -d/-D/-m` /
`git tag` · `git clean` · `git gc` / `git prune` / `git reflog expire` ·
`git config` (writing) · `git submodule update` · any `gh` command that
creates or modifies a PR, branch, release, or issue.

Read-only git is fine and encouraged: `git status`, `git log`, `git diff`,
`git show`, `git blame`, `git check-attr`, `git ls-files`, `git config --get`.

Leave finished work as **uncommitted changes in the working tree** and say
so plainly in your summary. If committing seems useful, offer it and let
the user decide — do not commit and then mention it afterwards. This
applies even to a "safe" commit on a scratch branch: creating the branch is
itself a mutation.

If a task genuinely cannot proceed without a mutating git operation, stop
and explain what is needed rather than running it.

## What this project is

A local, fully offline Scaife Viewer (Ancient Greek + Latin reading) run
via Docker Compose. `README.md` is the authoritative documentation — read
it before changing anything, and keep it accurate when behaviour changes.

- `bootstrap.sh` — one-command bring-up (preflights, fetches data, builds,
  `docker compose up --build`). Safe to re-run; it is idempotent.
- `scaife/scaife-viewer-2026-08-10-001/` — the patched Django + Vue app.
- `deploy/entrypoint.sh` (inside the app) — one-time data work on first
  boot, each step gated by a sentinel in `sv-data/atlas/sentinels/`. Delete a
  sentinel to force that step to re-run.
- `deps/`, `data-sources/`, `sv-data/` — gitignored, fetched or generated.

## Tests

`bash scripts/run-tests.sh` — 79 unit tests in
`scaife/scaife-viewer-2026-08-10-001/sv_pdl/tests/`. Run them after any
change to `sv_pdl/`, settings, URLs or dependencies. The stack must be up.

- `--integration` adds checks needing live services and has **one expected
  failure** (elasticsearch-py 7.10.1 against an 8.x server) — a deliberate
  marker, documented in `UPGRADE-IMPACT.md`. Do not "fix" it by weakening
  the assertion.
- Lint is **not** part of the image build (it used to be, and a stray unused
  import would fail the whole build). Run it directly with
  `bash scripts/lint.sh`; `--fix` applies isort ordering. Keep the tree lint
  clean anyway — `docker build --build-arg RUN_LINT=1` restores the gate.
- Before touching dependencies, read `SBOM-2026-08-13.md` and
  `UPGRADE-IMPACT.md`. `scaife-viewer-core` hard-pins `Django<3.0`; there is
  no incremental upgrade path without forking upstream.

## Conventions

- Verify claims before writing them into the README. Several of its
  original figures (image versions, disk, timings, corpus sizes) turned out
  to be wrong when measured; prefer a measured number, and say what it was
  measured on. Mark anything untested as untested.
- Run management commands as the app user: `docker exec -u scaife
  scaife-viewer python manage.py …`. Plain `docker exec` lands as root,
  because the container starts as UID 0 to install firewall rules before
  dropping privileges.
- Long jobs: run them detached inside the container and log to `/sv-data/`
  (the writable bind mount) so the host can watch progress.
