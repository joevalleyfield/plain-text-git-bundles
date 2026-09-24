Filed as: 260923-plain-text-delta-engine
FKA:
AKA: text delta engine; unified diff compression; blob and tree deltas
Legacy index:

keywords: crypto, implementation, closed, correctness, pack, unpack

Parent:
Depends on: `260922-git-object-model`
Blocks: `260923-delta-pack-unpack-integration`
Blocked by:
Related: `260923-git-bundle-bridge`

# Implement Plain-Text Delta Engine for Blobs and Trees

Implement CVS/RCS-style plain-text delta compression using Python standard library (`difflib`) to generate and apply deterministic unified diffs (`.delta.txt`) for text blobs and `ls-tree` formatted trees with bit-exact Git OID verification.

## Current Reality

- `ptbundle` stores all revisions of Git objects as full loose text files (`commits/`, `trees/`, `blobs/`).
- Iterative edits to large text files or wide directory trees across multiple commits duplicate near-identical lines in every commit revision.
- Git object reconstitution and OID calculation are implemented in `src/ptbundle/objects.py`.
- No delta compression engine exists yet.

## Desired Reality

A new module `src/ptbundle/delta.py` providing:
1. **`TextDelta` Data Class**:
   - Fields: `object_type: GitObjectType`, `path: str`, `base_oid: str`, `target_oid: str`, `diff_text: str`.
   - Serialization `to_text()`:
     ```text
     # ptbundle delta v1
     type: blob
     path: src/main.py
     base: e69de29bb2d1...
     target: 4f8a1b2c3d4e...

     @@ -1,3 +1,4 @@
     ...
     ```
   - Parsing `from_text()` with strict format validation.
2. **`create_text_delta`**:
   - Generates unified diffs between base and target payloads using `difflib.unified_diff`.
   - Detects whether target is smaller as a delta than as full text.
   - Accurately tracks and preserves trailing newline (`\ No newline at end of file`) state for bit-exact reproducibility.
3. **`apply_text_delta`**:
   - Applies the unified diff onto base bytes deterministically.
   - Verifies reconstructed bytes hash bit-exactly to `target_oid` (`compute_oid(...)`).
   - For trees, parses into `GitTree` and verifies OID against Git's canonical binary tree hashing.
4. **Complete Unit Test Suite**:
   - 100% statement and branch coverage in `tests/test_delta.py`.
   - Tests for additions, deletions, modifications, EOF newline edge cases, corrupted deltas, and tree modifications.

## Gap Analysis

- `src/ptbundle/delta.py` needs to be created.
- `tests/test_delta.py` needs to be created.
- 100% statement and branch coverage must be maintained.

## Known Facts / Assumptions / Unknowns

### Known Facts
- Git OIDs are cryptographically sensitive down to individual bytes and line endings (`\n` vs `\r\n`, trailing newline presence).
- Both text blobs and `ls-tree` trees serialize cleanly to UTF-8 text lines.
- Python standard library `difflib` provides diffing facilities but requires careful handling of line endings to prevent EOF hash mismatches.

### Working Assumptions
- Deltas are self-contained within the bundle (referencing base objects present in the bundle).
- If a delta is larger than the raw target payload, the system falls back to storing the full text object.

## Investigations

- Test `difflib.unified_diff` behavior on strings without trailing newlines to establish exact patch logic.

## Models / Forecasts / Risks

- **EOF newline mismatch**: If a file does not have a trailing newline and the patch adds one, Git OID calculation will mismatch. Mitigated by explicit EOF markers and tests.

## Transformations

1. Create `src/ptbundle/delta.py`.
2. Create `tests/test_delta.py`.
3. Verify with `uv run pytest`, `uv run ruff`, `uv run mypy`.

## Evidence

- `uv run pytest tests/test_delta.py --cov=ptbundle.delta` passes 11/11 tests with 100% statement and branch coverage (229 statements, 116 branches, 0 missing).
- `uv run ruff check` and `uv run ruff format --check` clean.
- `uv run mypy src/ptbundle/delta.py tests/test_delta.py` clean with no issues.
- All edge cases (empty payloads, missing EOF newline, CRLF, multi-hunk diffs, binary and text tree diffs) verified.

## Decisions

- **Informational Header**: Include `type:` and `path:` in the delta header for human reviewer ergonomics without affecting the cryptographic payload.
- **Strict OID verification**: `apply_text_delta` must compute and verify the target OID before returning the reconstituted payload.

## Open Fronts

- Integrating into `pack.py` and `unpack.py` (tracked in `260923-delta-pack-unpack-integration`).

## Next Actions

- Done. Proceed with `260923-delta-pack-unpack-integration`.
