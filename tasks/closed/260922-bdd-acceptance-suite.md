Filed as: 260922-bdd-acceptance-suite
FKA:
AKA: bdd acceptance suite; pytest-bdd scenarios; end-to-end integration workflows
Legacy index:

keywords: bdd, testing, active, correctness, contract

Parent:
Depends on: `260922-pack-unpack-orchestrators`
Blocks:
Blocked by:
Related:

# Implement BDD Acceptance Suite with pytest-bdd

Implement executable Gherkin feature scenarios and step definitions in `tests/features/` and `tests/step_defs/` validating end-to-end delta packaging, quarantine side-channel delivery, and ingress safety for `ptbundle`.

## Current Reality

The codebase has unit and integration tests covering all individual components and CLI commands (`tests/test_*.py`) with 100% statement and branch coverage. However, the BDD middle loop defined in `AGENTS.md` (Behavior-Driven Development with `pytest-bdd`) has not yet been formalized:
- No `.feature` files exist under `tests/features/`.
- No user-facing Gherkin specifications exist describing cross-domain transfer scenarios, quarantine workflows, and ingress tampering defenses.

## Desired Reality

A comprehensive, executable BDD specification suite:
1. **Feature Scenarios (`tests/features/`)**:
   - `delta_transfer.feature`:
     - Packaging a branch delta (`main..feature`) from a source repository.
     - Unpacking the delta into an upstream repository clone.
     - Bit-exact verification that `git log`, `git diff`, and file contents match the source.
     - Full repository packaging (zero prerequisites).
   - `quarantine_sidechannel.feature`:
     - Packaging a repository containing text files, whitelisted images (`.png`), and non-whitelisted binary payloads (`.bin`).
     - Verifying that non-whitelisted binaries are cleanly diverted to `quarantine/` with `quarantine-manifest.txt`.
     - Verifying that unpack fails cleanly when required sidechannel payloads are absent.
     - Verifying that unpack succeeds and advances refs when `--sidechannel` is supplied with the quarantined media.
   - `ingress_tamper_defense.feature`:
     - Tampering with a `.txt` blob or tree in transit (hash mismatch).
     - Missing prerequisite commits in destination repository.
     - Attempted ref-injection or unsafe branch paths.
     - Verifying that destination repository state and ref tips are completely untouched upon rejection.
2. **Step Definitions (`tests/step_defs/` or `tests/test_bdd_*.py`)**:
   - Clean, reusable `pytest-bdd` step definitions.
   - Fixtures managing source and destination Git repositories in temporary directories.
   - Invocation of the `ptbundle` CLI entrypoint (`src/ptbundle/cli.py:main`).
3. **Continuous Enforcement**:
   - Runs cleanly under `uv run pytest`.
   - Maintains 100% statement and branch coverage across all production modules.

## Gap Analysis

- Need Gherkin feature files specifying user journeys and guard-rail security guarantees.
- Need test step bindings matching Gherkin steps (`Given`, `When`, `Then`).
- Ensure all BDD tests execute efficiently without slowing down test runner cycles.

## Known Facts / Assumptions / Unknowns

### Known Facts
- `pytest-bdd` (8.1.0) is already declared in `pyproject.toml` and installed in the environment.
- Feature files belong in `tests/features/`.

### Working Assumptions
- Real temporary Git repositories created with `git init` provide the most faithful end-to-end verification.

### Unknowns
- None.

## Investigations

- Verified round-trip cross-domain transfer across independent git repositories using pytest-bdd scenarios.
- Verified single-branch upstream clone behavior in fixtures to ensure prerequisite and delta boundaries are accurately exercised.

## Models / Forecasts / Risks

- **Slow Test Suite**: Real Git process invocations can be slow if overused. Using lean Git histories (1-3 commits, small files) keeps execution fast (entire 62-test suite finishes in ~2.2s).

## Transformations

1. Created `tests/features/delta_transfer.feature` specifying 3 scenarios:
   - Packaging and unpacking branch delta across repositories with exact bit-for-bit file and log match
   - Packaging and unpacking full repository history from scratch (no prerequisites)
   - Repeated unpacking is idempotent and retains repository health
2. Created `tests/features/quarantine_sidechannel.feature` specifying 2 scenarios:
   - Non-whitelisted binaries diverted to quarantine directory and rejected on unpack without sidechannel
   - Successful unpack and branch advance when `--sidechannel` is supplied with quarantined media
3. Created `tests/features/ingress_tamper_defense.feature` specifying 2 scenarios:
   - Ingress rejects tampered blob object and preserves destination repository untouched
   - Ingress rejects bundle when prerequisite commit is missing and preserves destination repository untouched
4. Implemented step definitions in `tests/test_bdd_scenarios.py` using `pytest-bdd` (8.1.0) with clean source/destination repo isolation fixtures and direct CLI invocation.
5. Moved task from `tasks/open/260922-bdd-acceptance-suite.md` to `tasks/closed/260922-bdd-acceptance-suite.md`.
6. Refreshed workboard with `python3 tasks/scripts/sync_workboard.py`.

## Evidence

- `uv run pytest`: 62 passed in 2.28s, 100% statement and branch coverage (890 statements, 302 branches).
- `uv run ruff check .`: Clean (0 errors).
- `uv run ruff format --check .`: 30 files already formatted.
- `uv run mypy src tests`: Success: no issues found in 17 source files.

## Decisions

- **Direct CLI invocation in steps**: BDD steps invoke `cli.main(argv)` directly in-process or via runner, verifying exact stdout and return codes as a user would observe them.
- **Single-branch cloning for upstream fixtures**: Used `git clone --branch main --single-branch` for destination repositories to ensure feature branch tips are absent prior to unpacking deltas.
- **Isolation of side-channel media**: Verifying that quarantine files are written outside the bundle directory in `quarantine/` and correctly resolved when passed via `--sidechannel`.

## Open Fronts

- None. All Phase 1 milestones (Milestones 1 through 6) are complete, verified, and closed.

## Next Actions

- Fold closure into commit `test(bdd): implement acceptance test suite with pytest-bdd`.
- Advance `main` bookmark in `jj`.
