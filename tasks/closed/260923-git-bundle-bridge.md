Filed as: 260923-git-bundle-bridge
FKA:
AKA: git bundle interop; from-bundle; to-bundle; bundle binary bridge
Legacy index:

keywords: bundle, cli, tooling, closed, compatibility, contract

Parent:
Depends on: `260922-git-repo-io`
Blocks: `260923-bdd-phase2-acceptance`
Blocked by:
Related: `260923-delta-pack-unpack-integration`

# Implement Git Bundle Interoperability Bridge (`from-bundle` and `to-bundle`)

Implement bidirectional conversion between standard Git `.bundle` binary files and plain-text `ptbundle` directories using isolated bare Git repository plumbing.

## Current Reality

- `ptbundle pack` requires an existing Git repository directory and rev-list range.
- `ptbundle unpack` requires an existing target Git repository directory.
- Users who receive a `.bundle` file or want to produce a `.bundle` file from a `ptbundle` must manually clone or fetch into a scratch repository first.

## Desired Reality

1. **`from-bundle` Subcommand**:
   - `ptbundle from-bundle <bundle_file> -o <ptbundle_dir> [--whitelist-ext ...]`
   - Unpacks the bundle into an isolated temporary bare repo via `git fetch`.
   - Executes `pack_bundle` against the fetched refs and prerequisites.
   - Emits a full plain-text bundle directory.
2. **`to-bundle` Subcommand**:
   - `ptbundle to-bundle <ptbundle_dir> -o <bundle_file>`
   - Unpacks the `ptbundle` directory into an isolated temporary bare repo via `unpack_bundle`.
   - Executes `git bundle create` for the declared refs and prerequisites.
   - Emits a canonical `.bundle` binary file verified with Git's internal checks.
3. **Core Module `src/ptbundle/bundle.py`**:
   - `read_bundle_header(bundle_path: Path) -> GitBundleHeader`: Parses `# v2 git bundle` and `# v3 git bundle` headers, extracting prerequisite and ref lists.
   - `convert_from_bundle(...)` and `convert_to_bundle(...)`.
4. **Complete Unit Tests**:
   - 100% statement and branch coverage in `tests/test_bundle.py`.
   - Verification using `git bundle verify` on synthesized bundles.

## Gap Analysis

- `src/ptbundle/bundle.py` needs to be created.
- `from-bundle` and `to-bundle` subcommands need to be added to `src/ptbundle/cli.py`.
- Unit tests in `tests/test_bundle.py` need to be created.

## Known Facts / Assumptions / Unknowns

### Known Facts
- A Git bundle starts with `# v2 git bundle` or `# v3 git bundle`, followed by lines starting with `-` for prerequisites and OID+ref pairs for tips, separated by an empty line from the binary packfile.
- Using an isolated temporary bare repo ensures 100% compatibility with Git's native packfile encoder/decoder while maintaining zero external Python dependencies.

## Transformations

1. Create `src/ptbundle/bundle.py`.
2. Add `from-bundle` and `to-bundle` to `src/ptbundle/cli.py`.
3. Create `tests/test_bundle.py`.

## Evidence

- `uv run pytest tests/test_bundle.py` passes 4/4 tests with 100.00% statement and branch coverage (105 statements, 36 branches, 0 missing).
- `uv run pytest tests/test_cli.py` passes 9/9 tests with 100.00% statement and branch coverage (116 statements, 16 branches, 0 missing).
- `from-bundle` converts Git `.bundle` files to plain-text ptbundle directory trees with delta compression.
- `to-bundle` converts plain-text ptbundle directory trees to canonical Git `.bundle` files.
- Synthesized `.bundle` files pass `git bundle verify` bit-exactly with exit code 0.
- Error handling for invalid headers, corrupted data, non-existent files, and empty headers verified.

## Decisions

- **Plumbing via Bare Scratch Repos**: Use `tempfile.TemporaryDirectory` with `git init --bare` to isolate all packfile operations, eliminating custom binary packfile parsing.
- **Reference Normalization**: Raw Git bundle refs (including `HEAD`) are normalized to standard `refs/` paths (`refs/heads/HEAD`) for strict ingress safety.

## Open Fronts

- BDD acceptance scenarios (tracked in `260923-bdd-phase2-acceptance`).

## Next Actions

- Done. Proceed with `260923-bdd-phase2-acceptance`.
