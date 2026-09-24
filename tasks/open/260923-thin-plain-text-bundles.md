Filed as: 260923-thin-plain-text-bundles
FKA:
AKA: thin bundles; external basis deltas; relax delta self-containment
Legacy index:

keywords: pack, unpack, delta, thin, active, correctness, contract

Parent:
Depends on: `260923-delta-pack-unpack-integration`, `260923-bdd-phase2-acceptance`
Blocks:
Blocked by:
Related: `260923-delta-pack-unpack-integration`

# Thin Plain-Text Bundles & External Basis Deltas

Relax the bundle self-containment constraint on plain-text deltas by adopting the canonical Git `--thin` / `--no-thin` model, allowing deltas to reference external basis objects present in the repository history (e.g. reachable from prerequisite boundary commits).

## Current Reality

- `ptbundle pack` only generates deltas if a prior version of the tree or blob was encountered within the revision delta itself (`delta.objects`).
- Single-commit feature branches (`base..head`) can never use delta compression; modified files and trees are emitted in full (`.txt`).
- `ptbundle unpack` only resolves deltas whose `base_oid` exists in `resolved_trees` or `resolved_blobs` inside the bundle.
- There is no `--thin` or `--no-thin` flag on `ptbundle pack`.

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

- `README.md` needs contract updates.
- `src/ptbundle/repo.py` needs methods to read raw objects by OID and inspect objects at specific revisions/paths.
- `src/ptbundle/pack.py` needs thin basis resolution against `delta.prerequisites` and `thin` parameter.
- `src/ptbundle/unpack.py` needs fallback resolution of base objects against `repo`.
- `src/ptbundle/cli.py` needs `--thin` / `--no-thin` CLI flags.
- Tests in `tests/test_pack.py`, `tests/test_unpack.py`, `tests/test_cli.py`, `tests/test_bdd_scenarios.py`, and `tests/features/phase2_interop_deltas.feature`.

## Transformations

1. Update `README.md` (RDD).
2. Implement repo, pack, unpack, and cli changes.
3. Add unit and BDD tests.
4. Verify with full test suite, lint, format, typecheck.
5. Close task and update workboard.

## Evidence

- Pending implementation and test runs.

## Decisions

- **Git Convention**: Use `--thin` (default) and `--no-thin` (opt-out). No secondary aliases.

## Open Fronts

- None.

## Next Actions

- Commit task opening.
- Update `README.md`.
