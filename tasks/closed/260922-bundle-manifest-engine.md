Filed as: 260922-bundle-manifest-engine
FKA:
AKA: bundle manifest; manifest.txt parser and serializer; prerequisite and ref tracking
Legacy index:

keywords: manifest, implementation, closed, contract, correctness

Parent:
Depends on: `260922-git-object-model`
Blocks:
Blocked by:
Related:

# Implement Bundle Manifest Specification and Engine

Define the text specification and implement a zero-dependency parser and serializer for `manifest.txt`, tracking delta prerequisites, target ref tips, hash algorithms, and object auditing metrics for `ptbundle`.

## Current Reality

The bundle manifest specification and engine are fully implemented and verified in `src/ptbundle/manifest.py`:
- `ManifestPrerequisite(oid, comment)` represents required commits with canonical serialization `prerequisite <oid> [comment]` and parsing support for git bundle alias `-<oid> [comment]`.
- `ManifestRef(name, oid)` represents target heads/tags with strict Git ref validation (requires `refs/`, rejects directory traversal `..`, reflog `@{`, illegal characters, and component dot rules).
- `ManifestMetrics` tracks object counts (`commits`, `trees`, `blobs_text`, `blobs_binary`, `blobs_quarantined`) with non-negative validation.
- `Manifest` coordinates versioning, hash algorithm selection (`sha1`, `sha256`), bidirectional serialization (`to_text()`, `from_text()`), and security validation.
- 100% statement and branch test coverage enforced via `pytest-cov`.
- Zero external runtime dependencies (Python standard library only).

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

All gaps closed:
- `src/ptbundle/manifest.py` authored with complete typing, docstrings, and validations.
- `tests/test_manifest.py` authored with 9 comprehensive unit tests covering all valid round-trips, aliases, and edge-case errors.
- 100.00% statement and branch coverage maintained across `src/ptbundle`.

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

- Verified syntax readability when rendered in terminal pagers or text editors during audit.
- Verified that full bundles (0 prerequisites) serialize and parse cleanly.
- Verified alias parsing of git bundle `-<oid> [comment]` format alongside canonical `prerequisite` lines.

## Models / Forecasts / Risks

- **Reference name injection**: Resolved by `validate_ref_name` which strictly enforces `refs/` prefix and rejects directory traversal (`..`), reflog selectors (`@{`), illegal characters, and component dot rules.

## Transformations

1. Created `src/ptbundle/manifest.py` implementing `Manifest`, `ManifestPrerequisite`, `ManifestRef`, `ManifestMetrics`, `validate_ref_name`, `validate_oid`.
2. Created `tests/test_manifest.py` covering all features, edge cases, and error states.
3. Formatted and linted code with `ruff check` and `ruff format`. Verified strict typing with `mypy src tests`.
4. Moved task from `tasks/open/260922-bundle-manifest-engine.md` to `tasks/closed/260922-bundle-manifest-engine.md`.
5. Refreshed workboard with `uv run python tasks/scripts/sync_workboard.py`.

## Evidence

- `uv run pytest`: 36 passed in 0.20s with 100% line and branch coverage (`--cov-fail-under=100`).
- `uv run ruff check .`: Clean (0 errors).
- `uv run ruff format --check .`: 17 files already formatted.
- `uv run mypy src tests`: Success: no issues found in 8 source files.

## Decisions

- **Keyword-prefixed syntax with git bundle alias**: Canonical format uses `prerequisite <oid> [comment]`, but `-<oid> [comment]` is accepted on parse for interoperability.
- **Explicit hash-algo declaration**: Always emit `hash-algo sha1` (or `hash-algo sha256`) explicitly below `# ptbundle v1` to eliminate ambiguity.
- **Clean metric format**: Format metrics as `commits: 3`, `trees: 7`, etc., supporting both `key: val` and `metric key val` on parse.
- **Strict ref path validation**: Enforce `refs/` prefix and reject all invalid characters, traversals, and reflog selectors.
- **Support full and delta bundles**: `prerequisites` list can be empty, allowing `ptbundle` to serialize complete repositories as well as deltas.

## Open Fronts

- None. Ready for Milestone 3 (Inspection & Quarantine Policy) or Milestone 4 (Git Repo I/O).

## Next Actions

- Fold closure into commit `feat(manifest): implement bundle manifest specification and engine`.
- Advance `main` bookmark in `jj`.
