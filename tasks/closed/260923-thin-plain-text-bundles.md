Filed as: 260923-thin-plain-text-bundles
FKA:
AKA: thin bundles; external basis deltas; relax delta self-containment
Legacy index:

keywords: pack, unpack, delta, thin, closed, correctness, contract

Parent:
Depends on: `260923-delta-pack-unpack-integration`, `260923-bdd-phase2-acceptance`
Blocks:
Blocked by:
Related: `260923-delta-pack-unpack-integration`

# Thin Plain-Text Bundles & External Basis Deltas

Relax the bundle self-containment constraint on plain-text deltas by adopting the canonical Git `--thin` / `--no-thin` model, allowing deltas to reference external basis objects present in the repository history (e.g. reachable from prerequisite boundary commits).

## Current Reality

- `ptbundle pack` now supports `--thin` (default) and `--no-thin` (opt-out).
- When packing revision ranges with boundary prerequisites (e.g. `base..head`), modified text blobs and trees are delta-compressed against basis objects in the source repository without bundling those basis objects.
- `ptbundle unpack` resolves external base objects directly from the target repository's object database (`repo.read_raw_object`).
- Single-commit feature branches generate compact thin deltas.
- `--no-thin` forces full self-contained objects (`.txt`) for offline/standalone package verification.

## Desired Reality

1. **RDD Contract**:
   - `README.md` documents thin plain-text bundles.
   - Default is `--thin` for revision ranges with boundary prerequisites (`base..head`).
   - `--no-thin` disables thin deltas and forces full self-contained objects.
2. **Pack Orchestration**:
   - `pack_bundle(..., thin=True)` queries boundary prerequisite commits (`delta.prerequisites`) when a path is encountered for the first time.
   - If a base object exists in the prerequisite and yields a smaller delta than full payload, emits `<oid>.delta.txt` referencing `base: <base_oid>`.
3. **Unpack Orchestration**:
   - `unpack_bundle` checks the target repository (`repo.read_raw_object`) when `delta.base_oid` is not bundled in the package.
   - Reconstitutes the object, validates `target_oid`, and injects loose object.
   - If base is missing from both bundle and target repo, raises an informative audit error.
4. **CLI Ergonomics**:
   - `ptbundle pack` supports `--thin` (default: True) and `--no-thin` (`action="store_false"`).
5. **BDD & TDD Verification**:
   - Executable BDD scenarios and unit tests verifying thin bundle generation, unpack integrity, and `--no-thin` self-containment.
   - 100% statement and branch coverage enforced.

## Gap Analysis

- Closed. All requirements implemented and verified.

## Transformations

1. Update `README.md` (RDD) with `--thin` and `--no-thin` specification.
2. Implement `GitRepo.read_raw_object` and `GitRepo.get_object_at_revision` in `src/ptbundle/repo.py`.
3. Implement thin delta generation against boundary prerequisites in `src/ptbundle/pack.py`.
4. Implement external base resolution from target repo in `src/ptbundle/unpack.py`.
5. Add `--thin` / `--no-thin` options to CLI in `src/ptbundle/cli.py`.
6. Add unit tests in `tests/test_pack.py`, `tests/test_unpack.py`, `tests/test_repo.py`, and `tests/test_cli.py`.
7. Add BDD acceptance scenarios in `tests/features/phase2_interop_deltas.feature` and `tests/test_bdd_scenarios.py`.
8. Verify 100% coverage, linting, formatting, and typing.

## Evidence

- `uv run pytest`: 90 passed in 5.10s with 100.00% statement and branch coverage across all 10 modules in `src/ptbundle`.
- `uv run ruff check .`: clean (0 errors).
- `uv run ruff format --check .`: 39 files clean.
- `uv run mypy src tests`: clean (0 issues across 21 source files).
- Executable BDD scenarios passing:
  - `Single-commit PR incremental pack with thin deltas against base commit`
  - `Single-commit PR pack with no-thin enforces complete self-containment`

## Decisions

- **Git Convention**: Use `--thin` (default) and `--no-thin` (opt-out). No secondary aliases.

## Open Fronts

- None.

## Next Actions

- Fold closure into feature commit and update workboard.
