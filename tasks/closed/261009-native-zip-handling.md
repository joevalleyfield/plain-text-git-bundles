Filed as: 261009-native-zip-handling
FKA:
AKA: native zip archive support; zip bundle packaging and unpacking
Legacy index:

keywords: pack, unpack, zip, archive, closed, contract, usability

Parent:
Depends on: `260923-thin-plain-text-bundles`
Blocks:
Blocked by:
Related: `260923-git-bundle-bridge`

# Native .zip Handling in ptbundle

Add native `.zip` archive handling to `ptbundle.pack` and `ptbundle.unpack` to allow bundling and ingesting plain-text Git bundles directly as single `.zip` files using Python's stdlib `zipfile.ZipFile`.

## Current Reality

- `ptbundle pack` outputs directly to a `.zip` archive when `--output` ends with `.zip` using stdlib `zipfile.ZipFile` directly without intermediate disk staging.
- `ptbundle unpack` accepts `.zip` archives directly as input, performing safe extraction into an isolated temporary scratch directory with strict path-traversal prevention.
- `ptbundle from-bundle` and `to-bundle` support `.zip` archives interchangeably with directory-based bundles.
- `README.md` documents native `.zip` packaging and unpacking workflows.

## Desired Reality

1. **RDD Contract**:
   - `README.md` documents native `.zip` packaging and unpacking ergonomics.
   - `ptbundle pack` outputs directly to a `.zip` archive when `--output` ends with `.zip`.
   - `ptbundle unpack` accepts `.zip` archives directly as input.
   - `ptbundle to-bundle` and `ptbundle from-bundle` accept and emit `.zip` archives.
2. **Pack Orchestration**:
   - `pack_bundle(..., output_dir)` detects if `output_dir` ends with `.zip`.
   - When `.zip` is requested, serializes objects and `manifest.txt` directly into `zipfile.ZipFile` without temporary disk files.
   - Supports compressed (`zipfile.ZIP_DEFLATED`) or uncompressed storage.
3. **Unpack Orchestration**:
   - `unpack_bundle(..., bundle_dir)` detects if `bundle_dir` is a `.zip` file.
   - Securely extracts into an isolated temporary directory (with path-traversal prevention) before validating and injecting objects.
   - Reports clear errors if archive is corrupt or missing `manifest.txt`.
4. **Bridge Interoperability**:
   - `convert_to_bundle` supports reading from `.zip` bundle files.
   - `convert_from_bundle` supports writing directly to `.zip` bundle files.
5. **BDD & TDD Verification**:
   - Unit tests covering pack to `.zip`, unpack from `.zip`, quarantine handling in `.zip`, path traversal protection, and error cases.
   - BDD acceptance scenarios for `.zip` workflows.
   - 100% statement and branch coverage enforced across `src/ptbundle`.

## Gap Analysis

- Closed. All requirements implemented, documented, and verified.

## Transformations

1. Create task file and sync workboard (`tasks: open task for native zip handling`).
2. Update `README.md` (RDD contract).
3. Implement native zip serialization in `src/ptbundle/pack.py`.
4. Implement native zip extraction and verification in `src/ptbundle/unpack.py`.
5. Update `src/ptbundle/bundle.py` to support `.zip` in `convert_to_bundle`.
6. Update CLI help strings in `src/ptbundle/cli.py`.
7. Add unit tests and BDD scenario tests.
8. Verify 100% test coverage, linting, formatting, typing, and workboard sync.
9. Fold closure into feature commit.

## Evidence

- `uv run pytest`: 98 passed in 5.90s with 100.00% statement and branch coverage across all 10 modules in `src/ptbundle`.
- `uv run ruff check .`: clean (0 errors).
- `uv run ruff format --check .`: 40 files already formatted.
- `uv run mypy src tests`: clean (0 issues across 21 source files).
- Executable BDD scenarios passing:
  - `Pack a delta directly to a .zip archive and unpack into target repo`
  - `Convert canonical Git bundle to a .zip archive and back`

## Decisions

- **Direct Serialization**: `pack_bundle` writes directly into `zipfile.ZipFile` avoiding unnecessary temporary directory churn.
- **Safe Scratch Extraction**: `unpack_bundle` safely extracts `.zip` into a scratch temp directory with path traversal guards (`_safe_extract_zip`), reusing existing directory validation and injection machinery.

## Open Fronts

- None.

## Next Actions

- Fold closure into feature commit and update workboard.
