Filed as: 260922-inspection-quarantine-policy
FKA:
AKA: quarantine policy; binary whitelist; side-channel quarantine manifest
Legacy index:

keywords: quarantine, policy, implementation, closed, contract, correctness

Parent:
Depends on: `260922-git-object-model`, `260922-bundle-manifest-engine`
Blocks:
Blocked by:
Related:

# Implement Inspection and Quarantine Policy Engine

Implement blob classification (text vs. binary), extension/signature whitelisting, and quarantine staging with `quarantine-manifest.txt` for side-channel out-of-band delivery in `ptbundle`.

## Current Reality

The inspection and quarantine policy engine is fully implemented and verified in `src/ptbundle/policy.py`:
- `BlobClassification` categorizes payloads into `TEXT`, `BINARY_WHITELISTED`, and `QUARANTINED`.
- `extract_extension` parses extensions case-insensitively and safely handles edge cases (dotfiles, trailing dots, extensionless binaries).
- `WhitelistPolicy` supports case-insensitive extension matching and magic-byte anti-spoofing verification for common media types (PNG, JPEG, GIF, PDF).
- `BlobClassifier` classifies payloads based on UTF-8 validity (zero null bytes), path extensions, and signature verification.
- `QuarantineRecord` and `QuarantineManifest` provide bidirectional serialization for `quarantine-manifest.txt` with audit reasons.
- `load_sidechannel_objects` recursively scans out-of-band media (ignoring hidden files and manifests), computes Git blob OIDs, and reconciles them against expected quarantine manifests.
- 100% statement and branch test coverage enforced via `pytest-cov`.
- Zero external runtime dependencies (Python standard library only).

## Desired Reality

A dedicated module `src/ptbundle/policy.py` implementing:
1. **Blob Classification (`BlobClassification`)**:
   - `TEXT`: Valid UTF-8, no null bytes (`\0`). Targeted for `blobs/xx/<sha>.txt`.
   - `BINARY_WHITELISTED`: Non-text payload whose path extension is explicitly allowed on the whitelist and passes signature validation. Targeted for `blobs/xx/<sha>.<ext>`.
   - `QUARANTINED`: Non-text payload not on the whitelist (or failing signature check). Diverted to `quarantine/<sha>.<ext>`.
2. **Whitelist Policy (`WhitelistPolicy`)**:
   - Configurable set of allowed extensions (e.g. `png`, `jpg`, `pdf`, `svg`, `csv`), case-insensitive, normalized without leading dots.
   - Built-in sanity checks for common binary signatures (PNG magic bytes `\x89PNG\r\n\x1a\n`, JPEG `\xff\xd8\xff`, GIF `GIF87a`/`GIF89a`, PDF `%PDF-`, etc.) to prevent disguised binaries from evading inspection.
3. **Quarantine Record & Manifest (`QuarantineManifest`)**:
   - Formats and parses `quarantine-manifest.txt` for side-channel delivery (CD-R / courier):
     ```text
     # ptbundle quarantine manifest v1
     quarantine <oid> <path_in_tree> <size_bytes> <reason>
     ```
   - Records each quarantined object's OID, repository path, byte size, and quarantine reason.
4. **Side-Channel Reconciliation (`load_sidechannel_objects`)**:
   - Scans a side-channel directory (e.g. mounted optical drive) for missing objects.
   - Reconstructs and verifies Git OIDs matching the quarantine manifest.
5. **Complete Test Suite**:
   - 100% statement and branch coverage in `tests/test_policy.py`.
   - Unit tests for UTF-8 detection, whitelisted extensions, signature verification, spoofed extension detection, quarantine manifest parsing/formatting, and side-channel payload loading.
6. **Zero External Dependencies**:
   - Strictly Python standard library (`pathlib`, `typing`, `dataclasses`, `enum`).

## Gap Analysis

All gaps closed:
- `src/ptbundle/policy.py` implemented with complete typing and docstrings.
- `tests/test_policy.py` implemented with 8 unit tests covering all edge cases, spoofing attempts, manifest formatting, and side-channel reconciliation.
- 100.00% statement and branch coverage maintained across `src/ptbundle`.

## Known Facts / Assumptions / Unknowns

### Known Facts
- Text files in `ptbundle` must not contain null bytes (`\0`) to ensure compatibility with strict text-only CDS guards.
- Trees provide the relative file path for each blob OID, enabling extension extraction.
- In cross-domain transfer, quarantined binaries are segregated from the primary text bundle and transferred out-of-band via physical media.

### Working Assumptions
- The default whitelist is empty unless specified by `--whitelist-ext`.
- An empty whitelist means all non-text binaries are routed to quarantine.
- Paths without extensions or with unknown extensions are classified as quarantined if they are not UTF-8 text.

### Unknowns
- Resolved: Empty files (`b""`) are treated as valid UTF-8 text in Git.

## Investigations

- Verified magic-byte detection rejects executable binaries disguised as `.png` files.
- Verified recursive scanning in `load_sidechannel_objects` allows nested media hierarchies while verifying OIDs.

## Models / Forecasts / Risks

- **Disguised Executables**: Prevented by magic-byte verification in `WhitelistPolicy.verify_signature` for known image and document formats.

## Transformations

1. Created `src/ptbundle/policy.py` implementing `BlobClassification`, `BlobClassifier`, `WhitelistPolicy`, `QuarantineRecord`, `QuarantineManifest`, and `load_sidechannel_objects`.
2. Created unit tests in `tests/test_policy.py` covering all features and error states.
3. Formatted and linted code with `ruff check` and `ruff format`. Verified strict typing with `mypy src tests`.
4. Moved task from `tasks/open/260922-inspection-quarantine-policy.md` to `tasks/closed/260922-inspection-quarantine-policy.md`.
5. Refreshed workboard with `uv run python tasks/scripts/sync_workboard.py`.

## Evidence

- `uv run pytest`: 44 passed in 0.22s with 100% line and branch coverage (`--cov-fail-under=100`).
- `uv run ruff check .`: Clean (0 errors).
- `uv run ruff format --check .`: 20 files already formatted.
- `uv run mypy src tests`: Success: no issues found in 10 source files.

## Decisions

- **Extension case-insensitivity**: Whitelist matches extensions case-insensitively (`.PNG` matches `png`).
- **Explicit quarantine reasons**: `quarantine-manifest.txt` records human-auditable reasons (e.g. `extension_not_whitelisted:exe`, `signature_mismatch:png`, `missing_extension`) to guide security reviewers.
- **Media-agnostic recursive traversal**: `load_sidechannel_objects` indexes discovered files by their Git blob OID (`compute_oid(GitObjectType.BLOB, payload)`), allowing flat or hierarchical side-channel storage.
- **Empty payload handling**: Zero-byte blobs (`b""`) decode cleanly as UTF-8 text without null bytes.

## Open Fronts

- None. Ready for Milestone 4 (Git Repo I/O).

## Next Actions

- Fold closure into commit `feat(policy): implement inspection and quarantine policy engine`.
- Advance `main` bookmark in `jj`.
