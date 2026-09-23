Filed as: 260922-bundle-manifest-engine
FKA:
AKA: bundle manifest; manifest.txt parser and serializer; prerequisite and ref tracking
Legacy index:

keywords: manifest, implementation, active, contract, correctness

Parent:
Depends on: `260922-git-object-model`
Blocks:
Blocked by:
Related:

# Implement Bundle Manifest Specification and Engine

Define the text specification and implement a zero-dependency parser and serializer for `manifest.txt`, tracking delta prerequisites, target ref tips, hash algorithms, and object auditing metrics for `ptbundle`.

## Current Reality

Milestone 1 (`260922-git-object-model`) implemented the core Git object models, hashing, and serializers in `src/ptbundle/objects.py`. However, there is no mechanism to record or validate the overall bundle transfer contract:
- No data structures or functions exist to parse or generate `manifest.txt`.
- The CLI stubs (`pack` and `unpack`) do not inspect or write prerequisites, target branches, or object counts.

## Desired Reality

A dedicated module `src/ptbundle/manifest.py` implementing:
1. **Manifest Text Specification (`manifest.txt`)**:
   - Header identifying the format version: `# ptbundle v1`.
   - Hash algorithm declaration (defaulting to `sha1`, supporting `sha256`).
   - Prerequisites list: commits that the recipient repository must possess for the delta to apply (format: `prerequisite <oid> [comment]`).
   - Target references list: heads and tags being transferred or updated (format: `ref <refname> <oid>`).
   - Audit summary metrics: counts of commits, trees, text blobs, whitelisted binaries, and quarantined objects.
2. **Dataclasses & Engine**:
   - `ManifestPrerequisite(oid: str, comment: str = "")`
   - `ManifestRef(name: str, oid: str)`
   - `ManifestMetrics(commits: int, trees: int, blobs_text: int, blobs_binary: int, blobs_quarantined: int)`
   - `Manifest`: Container with methods `to_text() -> str`, `from_text(text: str) -> Manifest`, and validation logic.
3. **Strict Validation**:
   - Validates format header and supported version.
   - Validates hex OID format and length matching declared `hash_algo` (40 chars for SHA-1, 64 chars for SHA-256).
   - Validates Git reference name format (`refs/heads/...`, `refs/tags/...`).
   - Enforces non-negative metric counts and reports malformed syntax with clear, actionable error messages.
4. **Complete Test Suite**:
   - 100% statement and branch test coverage in `tests/test_manifest.py`.
   - Comprehensive tests for round-trip serialization, parsing edge cases, blank lines, comments, and invalid inputs.
5. **Zero External Dependencies**:
   - Python standard library only (`dataclasses`, `re`, `typing`).

## Gap Analysis

- Need to formalize the line-based syntax of `manifest.txt` to ensure compatibility with plain-text audit policies while remaining trivial to parse in shell or Python.
- Need `src/ptbundle/manifest.py` with full typing and docstrings.
- Need `tests/test_manifest.py` verifying all valid and invalid cases to maintain 100% test coverage.

## Known Facts / Assumptions / Unknowns

### Known Facts
- Standard `git bundle` headers use `-<oid> <comment>` for prerequisites and `<oid> <refname>` for references.
- In `ptbundle`, explicit keyword-prefixed lines (`prerequisite <oid> [comment]` and `ref <refname> <oid>`) provide clearer self-documentation for human security auditors.
- `manifest.txt` must be pure ASCII/UTF-8 with no binary or null bytes.

### Working Assumptions
- Lines beginning with `#` (except the format header) are treated as comments.
- Blank lines and extra whitespace around fields are ignored during parsing.
- Metrics are informative for human auditors and sanity checking, but do not replace cryptographic object verification.

### Unknowns
- None.

## Investigations

- Verify syntax readability when rendered in terminal pagers or text editors during audit.
- Check edge cases where a bundle has no prerequisites (a full / non-delta bundle). The manifest must cleanly support 0 prerequisites.

## Models / Forecasts / Risks

- **Reference name injection**: Ref names must be validated to ensure they conform to valid Git ref paths (e.g. preventing path traversal attempts like `refs/heads/../../foo`).

## Transformations

1. Create `src/ptbundle/manifest.py` implementing `Manifest`, `ManifestPrerequisite`, `ManifestRef`, `ManifestMetrics`.
2. Create `tests/test_manifest.py` covering all features, edge cases, and error states.
3. Run test suite to verify 100% statement and branch coverage.
4. Update `tasks/open/260922-bundle-manifest-engine.md` with progress stitching.

## Evidence

- `uv run pytest`: 100% statement and branch coverage on `src/ptbundle/manifest.py`.
- `uv run ruff check .` and `uv run ruff format --check .`: Clean.
- `uv run mypy src tests`: Clean type check.

## Decisions

- **Keyword-prefixed syntax**: Use explicit `prerequisite <oid> [comment]` and `ref <refname> <oid>` rather than positional symbols to maximize audit readability.
- **Support full and delta bundles**: `prerequisites` list can be empty, allowing `ptbundle` to serialize complete repositories as well as deltas.

## Open Fronts

- None.

## Next Actions

1. Review task with thread peer.
2. Implement TDD cycle: write unit tests in `tests/test_manifest.py` and implement `src/ptbundle/manifest.py`.
