Filed as: 260922-git-object-model
FKA:
AKA: git object model; canonical git hashing; tree and commit serialization
Legacy index:

keywords: crypto, implementation, closed, correctness, compatibility

Parent:
Depends on: `260922-scaffold-project-disciplines`
Blocks:
Blocked by:
Related:

# Implement Git Object Model and Canonical Serializers

Implement zero-dependency Python representations for Git objects (`blob`, `tree`, `commit`, `tag`) supporting bit-exact canonical SHA-1/SHA-256 hashing and bidirectional plain-text serialization for `ptbundle`.

## Current Reality

The Git object models and canonical serializers are fully implemented and verified in `src/ptbundle/objects.py`:
- `compute_oid`, `format_git_object`, and `parse_git_object` implement canonical Git hashing (`<type> <size>\0<payload>`) for SHA-1 and SHA-256, verified bit-exact against `git hash-object`.
- `GitBlob` supports raw binary payloads, UTF-8 text detection (`is_binary`), and extension preservation.
- `GitTreeEntry` and `GitTree` support bidirectional parsing and serialization between binary Git trees and human-auditable `ls-tree` plain-text syntax (`<mode> <type> <oid>\t<path>\n`). Canonical Git directory sorting (treating trees as ending in `/`) is implemented via `tree_entry_sort_key` and verified against `git mktree --missing`.
- `GitCommit` parses and formats commit headers (`tree`, `parent`, `author`, `committer`, multiline extra headers like `gpgsig`) and commit bodies, verified against `git commit-tree`.
- `GitTag` parses and formats annotated tag headers (`object`, `type`, `tag`, optional `tagger`, extra headers) and tag messages, verified against `git mktag`.
- 100% statement and branch test coverage enforced via `pytest-cov`.
- Zero external runtime dependencies (Python standard library only).

## Desired Reality

A dedicated module `src/ptbundle/objects.py` (and supporting submodules if appropriate) providing:
1. **Canonical Git OID Hashing**:
   - Computes canonical Git hashes for objects using the Git standard: `<type> <size>\0<payload>`.
   - Supports SHA-1 (standard Git) and SHA-256 (Git objectFormat=sha256).
   - Produces bit-exact matches against native `git hash-object` for blobs, trees, commits, and tags.
2. **Blob Handling**:
   - Reconstitute loose Git blob objects from raw payloads.
   - Text/UTF-8 detection: distinguish valid UTF-8 text from binary files.
   - File extension preservation for whitelisted types.
3. **Tree Serialization & Deserialization**:
   - Parse native binary Git trees (series of `<octal_mode> <path>\0<raw_oid_bytes>`).
   - Emit text-safe, human-auditable `ls-tree` formatted listings (`<mode> <type> <hex_oid>\t<path>\n`).
   - Reconstruct canonical binary Git trees from text-safe listings, enforcing Git's canonical sorting rules (directories sorted as if suffixed with `/`).
4. **Commit & Tag Handling**:
   - Parse and serialize UTF-8 commit headers (`tree`, `parent`, `author`, `committer`) and commit messages.
   - Parse and serialize annotated tag objects (`object`, `type`, `tag`, `tagger`, message).
5. **Zero External Dependencies**:
   - Implemented strictly with Python 3.10+ standard library (`hashlib`, `pathlib`, `typing`, `enum`, etc.).
6. **Complete Test Suite**:
   - 100% branch and statement coverage.
   - Direct verification against Git CLI outputs (`git hash-object`, `git cat-file`, `git mktree`, `git commit-tree`, `git mktag`) across various edge cases (empty files, symlinks, subtrees, UTF-8 commit messages, multiple parents/merges, PGP signatures).

## Gap Analysis

All gaps closed:
- Implemented `src/ptbundle/objects.py` covering all 4 Git object types and hashing functions.
- Implemented `tests/test_objects.py` with 22 comprehensive unit tests exercising bit-exact parity against native Git CLI commands.
- Achieved 100.00% statement and branch coverage across the entire codebase.

## Known Facts / Assumptions / Unknowns

### Known Facts
- Git object hash is `hash(f"{obj_type} {len(payload)}\0".encode() + payload)`.
- For SHA-1, OID length is 40 hex chars (20 bytes). For SHA-256, OID length is 64 hex chars (32 bytes).
- Native Git tree format: each entry is `<mode_without_leading_zeros_or_octal> <path_bytes>\0<binary_oid_bytes>`.
- In standard `ls-tree` / `cat-file -p`, entries are printed as:
  `<mode_6_digits> <type> <hex_oid>\t<path>`
  e.g. `100644 blob e69de29bb2d1d6434b8b29ae775ad8c2e48c5391\tREADME.md`.
- In strict text-whitelisting CDS environments, `.txt` files must avoid null bytes (`\0`). The `ls-tree` format contains tabs and newlines, perfectly avoiding null bytes.
- Git directory sorting collation sorts subtrees as if suffixed with `/`.

### Working Assumptions
- Default hash algorithm is SHA-1, with clean parameterization for SHA-256.
- Text blobs are stored in `<sha>.txt` with exact file contents as the payload.

### Unknowns
- Resolved: Git handles symlinks as mode `120000 blob <sha>`, where the blob payload is the target path string without trailing newline.

## Investigations

- Verified canonical Git tree sort order behavior with test fixtures containing files and directories with overlapping prefix names (`a.c`, `a`, `a-b`, `a_b`). Verified that `tree_entry_sort_key` matches `git mktree --missing` bit-for-bit.
- Verified binary Git tree round-trip against `git mktree` and `git cat-file -p`.
- Verified commit serialization and parity against `git commit-tree`.
- Verified tag serialization and parity against `git mktag`.

## Models / Forecasts / Risks

- **Tree sorting mismatch**: Resolved by implementing `tree_entry_sort_key` which appends `/` to the name when sorting subtrees (`040000`).
- **Line ending normalization**: Resolved by preserving exact binary bytes without universal newline transformation.

## Transformations

1. Created `src/ptbundle/objects.py` implementing `GitObjectType`, `GitObject`, `GitBlob`, `GitTree`, `GitTreeEntry`, `GitCommit`, `GitTag`, and hashing utilities.
2. Created unit tests in `tests/test_objects.py` with 100% test coverage and parity tests against Git CLI.
3. Formatted and linted code with `ruff check` and `ruff format`. Verified strict typing with `mypy src tests`.
4. Moved task from `tasks/open/260922-git-object-model.md` to `tasks/closed/260922-git-object-model.md`.
5. Refreshed workboard with `uv run python tasks/scripts/sync_workboard.py`.

## Evidence

- `uv run pytest`: 27 passed in 0.18s with 100% line and branch coverage (`--cov-fail-under=100`).
- `uv run ruff check .`: Clean (0 errors).
- `uv run ruff format --check .`: 14 files already formatted.
- `uv run mypy src tests`: Success: no issues found in 6 source files.
- Bit-exact OID parity verified against `git hash-object`, `git mktree --missing`, `git commit-tree`, and `git mktag`.

## Decisions

- **ls-tree plain-text format for trees**: Use standard 6-digit mode, type, hex SHA, tab, and path string. This eliminates all null bytes and renders tree objects directly human-readable and diffable.
- **Raw payload preservation**: Blob text payload is encoded/decoded preserving exact line endings (no universal newline mutation).
- **Subtree sort key**: Canonical Git collation sorts tree entries byte-by-byte by name, except directories are suffixed with `/` during comparison.

## Open Fronts

- None. Ready for Phase 1 Milestone 2 (Loose Object Store Reader & Ingress Safe Writer).

## Next Actions

- Fold closure into commit `feat(objects): implement git object models, canonical serializers, and OID hashing`.
- Advance `main` bookmark in `jj`.
