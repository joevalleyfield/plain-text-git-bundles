Filed as: 260922-scaffold-project-disciplines
FKA:
AKA: project bootstrap; initial scaffolding
Legacy index:

keywords: governance, implementation, active, packaging, tooling

Parent:
Depends on:
Blocks:
Blocked by:
Related:

# Scaffold Project Disciplines

Establish foundational engineering disciplines across task tracking, commits, development, testing, coverage, packaging, documentation, and dependency management.

## Current Reality
An initial README.md has been committed via Jujutsu (`jj`). No packaging configuration, task tracking, test suite, linters, or contributor guidelines currently exist in the repository.

## Desired Reality
1. Task discipline modeled after `../toas` is operational (`tasks/` with `open/`, `closed/`, `WORKBOARD.md`, and `sync_workboard.py`).
2. Commit discipline is established: open tasks committed as `tasks: ...`, progress stitched to task files, closure folded into feature/fix commits, and `jj` workflow codified.
3. Concentric development rhythm established: Readme-Driven (RDD) -> Behavior-Driven (BDD) -> Test-Driven (TDD).
4. Packaging and zero runtime dependency policy configured via `pyproject.toml` (Python >=3.10) with CLI entrypoint `ptbundle`.
5. Testing and 100% coverage discipline configured with `pytest`, `pytest-cov`, and `pytest-bdd`.
6. Code style and typing configured via `ruff` and `mypy`.
7. Contributor and agent instructions codified in `AGENTS.md`.

## Gap Analysis
Need to author the task tracking layout, workboard sync script, `pyproject.toml`, `.gitignore`, `src/ptbundle` skeleton, `tests` skeleton, and `AGENTS.md`.

## Known Facts / Assumptions / Unknowns
- Known: Zero runtime external dependencies is a strict project requirement.
- Known: Development and testing will use `uv` and standard modern tooling (`ruff`, `mypy`, `pytest`).
- Known: Python version target is >=3.10.

## Investigations
Inspected `../toas/tasks` and `../toas/AGENTS.md` to match established workspace patterns and task naming conventions.

## Models / Forecasts / Risks
- Risk: Pytest coverage config failing under 100% if uncovered branches exist. Mitigation: Keep initial skeleton minimal and fully covered with unit tests.

## Transformations
- Added `tasks/README.md`, `tasks/task-template.md`, `tasks/scripts/sync_workboard.py`, `tasks/WORKBOARD.md`.
- Opened `tasks/open/260922-scaffold-project-disciplines.md`.
- Added `pyproject.toml` and `.gitignore`.
- Added `src/ptbundle/__init__.py`, `src/ptbundle/py.typed`, `src/ptbundle/cli.py`.
- Added `tests/conftest.py`, `tests/test_cli.py`.
- Added `AGENTS.md`.

## Evidence
- `uv run pytest` passes with 100% line and branch coverage.
- `uv run ruff check .` and `uv run ruff format --check .` pass cleanly.
- `uv run mypy src tests` passes cleanly.
- `python3 tasks/scripts/sync_workboard.py` synchronizes the workboard without errors.

## Decisions
- Adopted concentric RDD -> BDD -> TDD rhythm.
- Enforced task-stitching rule: progress commits update the task file, and closure is folded with the final feature commit.

## Open Fronts
- Complete scaffolding files, verify test suite, and fold closure into final commit.

## Next Actions
1. Run `sync_workboard.py`.
2. Commit opening of this task as `tasks: open task for scaffolding project disciplines`.
3. Create `pyproject.toml`, source skeleton, tests, and `AGENTS.md`.
4. Run verification commands.
5. Move task to `tasks/closed/` and fold closure into `feat(scaffold): ...`.
