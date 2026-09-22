Filed as: 260922-scaffold-project-disciplines
FKA:
AKA: project bootstrap; initial scaffolding
Legacy index:

keywords: governance, implementation, closed, packaging, tooling

Parent:
Depends on:
Blocks:
Blocked by:
Related:

# Scaffold Project Disciplines

Establish foundational engineering disciplines across task tracking, commits, development, testing, coverage, packaging, documentation, and dependency management.

## Current Reality
Disciplines and foundations are established and verified:
- Task tracking system matching `../toas` is operational under `tasks/` with `sync_workboard.py`.
- Task/commit discipline is established: open tasks committed as `tasks: ...`, progress stitched to task files, closure folded into feature/fix commits.
- Concentric development rhythm established: Readme-Driven (RDD) -> Behavior-Driven (BDD) -> Test-Driven (TDD).
- Packaging and zero runtime external dependencies configured in `pyproject.toml` (Python >=3.10) with CLI entrypoint `ptbundle`.
- Test suite with 100% line and branch coverage configured via `pytest`, `pytest-cov`, and `pytest-bdd`.
- Formatting, linting, and strict type checking configured via `ruff` and `mypy`.
- Decluttered local environment configured with `dev.local` integration (`.gemini-local/bin/uvt`).
- Contributor and agent instructions codified in `AGENTS.md`.

## Desired Reality
1. Task discipline modeled after `../toas` is operational (`tasks/` with `open/`, `closed/`, `WORKBOARD.md`, and `sync_workboard.py`).
2. Commit discipline is established: open tasks committed as `tasks: ...`, progress stitched to task files, closure folded into feature/fix commits, and `jj` workflow codified.
3. Concentric development rhythm established: Readme-Driven (RDD) -> Behavior-Driven (BDD) -> Test-Driven (TDD).
4. Packaging and zero runtime dependency policy configured via `pyproject.toml` (Python >=3.10) with CLI entrypoint `ptbundle`.
5. Testing and 100% coverage discipline configured with `pytest`, `pytest-cov`, and `pytest-bdd`.
6. Code style and typing configured via `ruff` and `mypy`.
7. Contributor and agent instructions codified in `AGENTS.md`.

## Gap Analysis
All gaps closed: scaffolding files, source tree, tests, dev tools, and governance docs are in place and verified.

## Known Facts / Assumptions / Unknowns
- Fact: Zero runtime external dependencies is strictly enforced in `pyproject.toml`.
- Fact: Testing and linting run through `uv` / `.gemini-local/bin/uvt` with 100% coverage requirement.

## Investigations
Inspected `../toas/tasks`, `../toas/AGENTS.md`, and `../declutter-dev-local` to align project structure with user preferences and machine conventions.

## Models / Forecasts / Risks
- Resolved: 100% coverage is strictly met on `src/ptbundle`.

## Transformations
- Created `tasks/README.md`, `tasks/task-template.md`, `tasks/scripts/sync_workboard.py`, `tasks/WORKBOARD.md`.
- Opened task `tasks/open/260922-scaffold-project-disciplines.md` and committed under `tasks:`.
- Configured packaging in `pyproject.toml` and `.gitignore`.
- Created source structure: `src/ptbundle/__init__.py`, `src/ptbundle/py.typed`, `src/ptbundle/cli.py`.
- Created test suite: `tests/conftest.py`, `tests/test_cli.py`.
- Author `AGENTS.md` covering concentric RDD -> BDD -> TDD rhythm, task/commit lifecycle rules, and invariants.
- Configured declutter environment with `.declutter/workspace.env`, `.envrc`, and `.gemini-local/bin/uvt`.
- Verified test suite, formatting, linting, and typing.
- Moved task to `tasks/closed/260922-scaffold-project-disciplines.md` and re-synced `tasks/WORKBOARD.md`.

## Evidence
- `uv run pytest`: 5 passed in 0.04s with 100% line and branch coverage (`--cov-fail-under=100`).
- `uv run ruff check .`: All checks passed.
- `uv run ruff format --check .`: 11 files already formatted.
- `uv run mypy src tests`: Success: no issues found in 4 source files.
- `uv run ptbundle --version` prints `ptbundle 0.1.0`.
- `python3 tasks/scripts/sync_workboard.py`: Synced 0 open, 0 inbox, 1 closed tasks.

## Decisions
- Adopted concentric RDD -> BDD -> TDD rhythm in `AGENTS.md`.
- Established task and commit discipline: open tasks committed as `tasks: ...`, progress stitched, closure folded into feature/fix commits.
- Maintained zero runtime external dependencies for `ptbundle`.
- Integrated with `declutter-dev-local` to keep caches and virtual environments in `~/Library/Caches/dev.local`.

## Open Fronts
- None for bootstrap. Next step will be Phase 1 Milestone 1 (core OID calculations and Git object types).

## Next Actions
- Fold closure into `feat(scaffold): establish development, testing, packaging, and governance disciplines`.
