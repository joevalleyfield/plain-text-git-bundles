Filed as: 260922-inspection-quarantine-policy
FKA:
AKA: quarantine policy; binary whitelist; side-channel quarantine manifest
Legacy index:

keywords: quarantine, policy, implementation, active, contract, correctness

Parent:
Depends on: `260922-git-object-model`, `260922-bundle-manifest-engine`
Blocks:
Blocked by:
Related:

# Implement Inspection and Quarantine Policy Engine

Implement blob classification (text vs. binary), extension/signature whitelisting, and quarantine staging with `quarantine-manifest.txt` for side-channel out-of-band delivery in `ptbundle`.

## Current Reality

Milestones 1 & 2 established the core Git object models and the bundle manifest specification. However, the policy layer that evaluates blob safety and handles non-text files does not yet exist:
- No policy engine exists to classify blobs based on UTF-8 validity, file extensions from tree paths, or magic byte signatures.
- No mechanism exists to route non-whitelisted binaries to a `quarantine/` directory or emit a `quarantine-manifest.txt`.
- The CLI `--whitelist-ext` argument in `src/ptbundle/cli.py` is parsed but unused.

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

- Need classification engine linking `GitBlob` payloads with their path and mode from `GitTreeEntry`.
- Need policy evaluator supporting extension parsing and magic byte verification.
- Need serialization and parsing for `quarantine-manifest.txt`.
- Need loader to verify and reconcile side-channel payloads on ingress.

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
- None.

## Investigations

- Verify edge cases with zero-byte files (empty blobs are valid UTF-8 text in Git: SHA-1 `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391`).
- Verify path extraction when a blob appears at multiple paths with different extensions (e.g., hardlinked or duplicate content). The most restrictive policy should govern, or the classification should be per-path.

## Models / Forecasts / Risks

- **Disguised Executables**: A file named `image.png` that actually contains executable machine code or a shell script. Basic magic-byte validation prevents obvious spoofing for common media types.

## Transformations

1. Create `src/ptbundle/policy.py` implementing `BlobClassification`, `BlobClassifier`, `WhitelistPolicy`, `QuarantineRecord`, `QuarantineManifest`, and `load_sidechannel_objects`.
2. Create unit tests in `tests/test_policy.py` with 100% statement and branch test coverage.
3. Update `tasks/open/260922-inspection-quarantine-policy.md` with progress stitching.

## Evidence

- `uv run pytest`: 100% statement and branch coverage on `src/ptbundle/policy.py`.
- `uv run ruff check .` and `uv run ruff format --check .`: Clean.
- `uv run mypy src tests`: Clean type check.

## Decisions

- **Extension case-insensitivity**: Whitelist matches extensions case-insensitively (`.PNG` matches `png`).
- **Explicit quarantine reasons**: `quarantine-manifest.txt` records human-auditable reasons (e.g. `extension_not_whitelisted`, `signature_mismatch`) to guide security reviewers.

## Open Fronts

- None.

## Next Actions

1. Review task with thread peer.
2. Begin TDD cycle: write unit tests in `tests/test_policy.py` and implement `src/ptbundle/policy.py`.
