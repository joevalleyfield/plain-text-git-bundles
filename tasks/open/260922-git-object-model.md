Filed as: 260922-git-object-model
FKA:
AKA: git object model; canonical git hashing; tree and commit serialization
Legacy index:

keywords: crypto, implementation, active, correctness, compatibility

Parent:
Depends on: `260922-scaffold-project-disciplines`
Blocks:
Blocked by:
Related:

# Implement Git Object Model and Canonical Serializers

Implement zero-dependency Python representations for Git objects (`blob`, `tree`, `commit`, `tag`) supporting bit-exact canonical SHA-1/SHA-256 hashing and bidirectional plain-text serialization for `ptbundle`.

## Current Reality

The project has established development disciplines, packaging, linting, typechecking, and a CLI skeleton with 100% test coverage. However, no domain logic exists for Git objects:
- `src/ptbundle/cli.py` has stub handlers for `pack` and `unpack` that merely print messages.
- There are no functions or classes to calculate canonical Git OIDs, parse/serialize Git tree structures, or convert between raw Git object payloads and `ptbundle`'s `.txt` wire format.

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
   - Direct verification against Git CLI outputs (`git hash-object`, `git cat-file`, `git mktree`) across various edge cases (empty files, symlinks, subtrees, UTF-8 commit messages, multiple parents/merges).

## Gap Analysis

- Need data structures representing the 4 Git object types (`GitBlob`, `GitTree`, `GitCommit`, `GitTag`).
- Need binary tree encoder/decoder that handles Git's binary pack/loose format and produces the plain-text `<sha>.txt` format.
- Need canonical Git tree sorting algorithm: Git sorts tree entries byte-by-byte by name, except directories are treated as ending with `/` for collation.
- Need comprehensive unit test suite in `tests/test_objects.py` verifying hash parity against real Git repositories and CLI commands.

## Known Facts / Assumptions / Unknowns

### Known Facts
- Git object hash is `hash(f"{obj_type} {len(payload)}\0".encode() + payload)`.
- For SHA-1, OID length is 40 hex chars (20 bytes). For SHA-256, OID length is 64 hex chars (32 bytes).
- Native Git tree format: each entry is `<mode_without_leading_zeros_or_octal> <path_bytes>\0<binary_oid_bytes>`.
- In standard `ls-tree` / `cat-file -p`, entries are printed as:
  `<mode_6_digits> <type> <hex_oid>\t<path>`
  e.g. `100644 blob e69de29bb2d1d6434b8b29ae775ad8c2e48c5391\tREADME.md`.
- In strict text-whitelisting CDS environments, `.txt` files must avoid null bytes (`\0`). The `ls-tree` format contains tabs and newlines, perfectly avoiding null bytes.

### Working Assumptions
- Default hash algorithm is SHA-1, with clean parameterization for SHA-256.
- Text blobs are stored in `<sha>.txt` with exact file contents as the payload.

### Unknowns
- How symlinks should be formatted in text trees (Git stores symlinks as mode `120000 blob <sha>`, where the blob payload is the target path string). Should be verified to match canonical Git behavior.

## Investigations

- Verify canonical Git tree sort order behavior with test fixture containing files and directories with overlapping prefix names (e.g. `foo`, `foo.txt`, `foo/bar`).
- Verify binary Git tree round-trip against `git mktree` and `git cat-file -p`.

## Models / Forecasts / Risks

- **Tree sorting mismatch**: If entries in a tree are reconstructed in lexicographical order by filename without Git's trailing slash rule for trees, the reconstructed binary tree will have entries in the wrong order, causing the calculated tree SHA to diverge from Git's canonical SHA.
- **Line ending normalization**: We must treat all blob payloads as raw binary bytes underneath so CRLF / LF line endings are preserved bit-for-bit without Python text translation corrupting hashes.

## Transformations

1. Create `src/ptbundle/objects.py` implementing `GitObjectType`, `GitObject`, `GitBlob`, `GitTree`, `GitTreeEntry`, `GitCommit`, `GitTag`, and hashing utilities.
2. Create unit tests in `tests/test_objects.py` with 100% test coverage and parity tests against Git.
3. Update `tasks/open/260922-git-object-model.md` with progress stitching.

## Evidence

- `uv run pytest`: 100% statement and branch coverage on `src/ptbundle/objects.py`.
- `uv run ruff check .` and `uv run ruff format --check .`: Clean.
- `uv run mypy src tests`: Clean type check.
- Verification that hashes computed by `src/ptbundle/objects.py` match `git hash-object` on sample inputs.

## Decisions

- **ls-tree plain-text format for trees**: Use standard 6-digit mode, type, hex SHA, tab, and path string. This eliminates all null bytes and renders tree objects directly human-readable and diffable.
- **Raw payload preservation**: Blob text payload is encoded/decoded preserving exact line endings (no universal newline mutation).

## Open Fronts

- None.

## Next Actions

1. Review task with thread peer.
2. Begin TDD cycle: write failing tests in `tests/test_objects.py` testing OID computation and tree serialization against Git.
