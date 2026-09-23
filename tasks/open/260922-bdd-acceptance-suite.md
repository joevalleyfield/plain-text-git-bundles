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

- Verify `pytest-bdd` step fixture scoping when handling multi-repo (source and destination) scenarios.

## Models / Forecasts / Risks

- **Slow Test Suite**: Real Git process invocations can be slow if overused. Using lean Git histories (1-3 commits, small files) keeps execution fast (< 2 seconds total).

## Transformations

1. Create `tests/features/delta_transfer.feature`.
2. Create `tests/features/quarantine_sidechannel.feature`.
3. Create `tests/features/ingress_tamper_defense.feature`.
4. Implement step definitions in `tests/test_bdd_scenarios.py` (or `tests/step_defs/`).
5. Run test suite to verify 100% coverage and passing scenarios.
6. Update `tasks/open/260922-bdd-acceptance-suite.md` with progress stitching.

## Evidence

- `uv run pytest`: All BDD scenarios and unit tests passing with 100% statement and branch coverage.
- `uv run ruff check .` and `uv run ruff format --check .`: Clean.
- `uv run mypy src tests`: Clean.

## Decisions

- **Direct CLI invocation in steps**: BDD steps invoke `cli.main(argv)` directly in-process or via runner, verifying exact stdout and return codes as a user would observe them.

## Open Fronts

- None.

## Next Actions

1. Review task with thread peer.
2. Implement feature files and step definitions.
