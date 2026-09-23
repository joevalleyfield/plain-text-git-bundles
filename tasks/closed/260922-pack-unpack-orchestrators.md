Filed as: 260922-pack-unpack-orchestrators
FKA:
AKA: pack and unpack orchestrators; cli integration; end-to-end bundle creation and ingress
Legacy index:

keywords: pack, unpack, cli, implementation, closed, usability, correctness

Parent:
Depends on: `260922-git-object-model`, `260922-bundle-manifest-engine`, `260922-inspection-quarantine-policy`, `260922-git-repo-io`
Blocks:
Blocked by:
Related:

# Implement Pack and Unpack CLI Orchestrators

Connect domain object models, manifest engine, inspection policies, and repository I/O into end-to-end `pack` and `unpack` orchestrators exposed through the `ptbundle` CLI.

## Current Reality

The `pack` and `unpack` orchestrators and CLI workflows are fully implemented and verified:
- `pack_bundle` (`src/ptbundle/pack.py`) discovers delta objects and boundary prerequisites, partitions objects into `commits/`, `trees/`, and `blobs/`, routes non-whitelisted binaries to `quarantine/` with `quarantine-manifest.txt`, and generates `manifest.txt`.
- `unpack_bundle` (`src/ptbundle/unpack.py`) executes a two-phase ingress pipeline: verifies prerequisites, cryptographically validates all commits, trees, and blobs against their expected OIDs, reconciles quarantined objects via `--sidechannel`, injects loose objects into `.git/objects/xx/xxxx`, and atomically updates target references.
- `src/ptbundle/cli.py` routes `pack` and `unpack` subcommands to the orchestrators, formats human-auditable terminal output, and handles errors with exit codes.
- 100% statement and branch test coverage enforced via `pytest-cov`.
- Zero external runtime dependencies (Python standard library only).

## Desired Reality

Dedicated orchestrators in `src/ptbundle/pack.py` and `src/ptbundle/unpack.py`, fully wired into `src/ptbundle/cli.py`:

1. **Pack Orchestrator (`src/ptbundle/pack.py`)**:
   - `pack_bundle(repo: GitRepo, rev_range: str, output_dir: Path | str, whitelist_policy: WhitelistPolicy | None = None, ref_name: str | None = None) -> Manifest`:
     - Discovers delta objects and boundary prerequisites via `discover_delta`.
     - Establishes destination directory layout (`commits/xx/`, `trees/xx/`, `blobs/xx/`).
     - Serializes commits to `commits/xx/<sha>.txt`.
     - Converts binary trees to human-auditable text format (`ls-tree`) in `trees/xx/<sha>.txt` (zero null bytes).
     - Classifies blobs via `BlobClassifier`:
       - Text blobs → `blobs/xx/<sha>.txt`.
       - Whitelisted binary blobs → `blobs/xx/<sha>.<ext>`.
       - Non-whitelisted or signature-failing binaries → diverted to `quarantine/<sha>.<ext>` and recorded in `quarantine-manifest.txt`.
     - Generates and writes canonical `manifest.txt` with prerequisites, target ref pointers, and summary metrics.
2. **Unpack Orchestrator (`src/ptbundle/unpack.py`)**:
   - `unpack_bundle(repo: GitRepo, bundle_dir: Path | str, sidechannel_dir: Path | str | None = None) -> UnpackResult`:
     - Parses and validates `manifest.txt`.
     - Verifies that target repository contains all required prerequisite commits (`verify_prerequisites`).
     - Scans bundle directory for `commits/`, `trees/`, and `blobs/`.
     - If quarantined objects exist in manifest:
       - Requires `sidechannel_dir` and loads missing payloads via `load_sidechannel_objects`.
       - Rejects unpack with clear error if required quarantined objects are absent.
     - Cryptographically verifies every object against its expected OID:
       - Blobs: `compute_oid(BLOB, payload) == oid`.
       - Trees: `GitTree.from_text(text).oid == oid`.
       - Commits: `GitCommit.from_payload(payload).oid == oid`.
     - Injects verified loose objects directly into `.git/objects/xx/xxxx`.
     - Atomically updates target references (`update_reference`).
3. **CLI Integration (`src/ptbundle/cli.py`)**:
   - `pack` command: accepts revision range, `--output` directory, and `--whitelist-ext` options. Prints human-readable audit summary.
   - `unpack` command: accepts bundle directory and optional `--sidechannel` directory. Prints verified object counts and updated ref pointers.
   - Error handling: catches validation errors and exits with clear error messages and non-zero exit codes.
4. **Complete Test Suite**:
   - 100% statement and branch coverage across `src/ptbundle/pack.py`, `src/ptbundle/unpack.py`, and `src/ptbundle/cli.py`.
   - Integration tests executing real pack and unpack cycles on temporary Git repositories.

## Gap Analysis

All gaps closed:
- `src/ptbundle/pack.py` and `src/ptbundle/unpack.py` authored with complete typing and docstrings.
- `src/ptbundle/cli.py` wired to invoke orchestrators and report progress.
- `tests/test_pack.py`, `tests/test_unpack.py`, and `tests/test_cli.py` authored with 11 comprehensive tests.
- 100.00% statement and branch coverage maintained across `src/ptbundle`.

## Known Facts / Assumptions / Unknowns

### Known Facts
- Target repository must not be modified if prerequisite validation or cryptographic verification fails.
- Reference updates must occur only after all objects are successfully written to `.git/objects`.
- Unpack must be completely idempotent: unpacking the same bundle twice must succeed without error.

### Working Assumptions
- Default whitelist is empty (all binary files quarantined) unless `--whitelist-ext` is provided.
- If `--sidechannel` is omitted and the bundle contains quarantined objects, unpack fails with an informative error stating which objects are missing.

### Unknowns
- None.

## Investigations

- Verified round-trip delta export from Repo A and import into Repo B with mixed text, whitelisted PNG, and quarantined binary payload. Verified that git checkout and diff match bit-for-bit.
- Verified that corrupted commits, trees, or blobs are detected and rejected prior to ref update.

## Models / Forecasts / Risks

- **Partial Ingress Corruption**: Resolved by two-phase verification: every object is validated before injection, and target refs are updated only after all objects are safely written.

## Transformations

1. Created `src/ptbundle/pack.py` implementing `pack_bundle`.
2. Created `src/ptbundle/unpack.py` implementing `unpack_bundle` and `UnpackResult`.
3. Updated `src/ptbundle/cli.py` to route `pack` and `unpack` commands to the orchestrators.
4. Created `tests/test_pack.py` and `tests/test_unpack.py`, and updated `tests/test_cli.py`.
5. Moved task from `tasks/open/260922-pack-unpack-orchestrators.md` to `tasks/closed/260922-pack-unpack-orchestrators.md`.
6. Refreshed workboard with `uv run python tasks/scripts/sync_workboard.py`.

## Evidence

- `uv run pytest`: 55 passed in 1.46s with 100% line and branch coverage (`--cov-fail-under=100`).
- `uv run ruff check .`: Clean (0 errors).
- `uv run ruff format --check .`: 28 files already formatted.
- `uv run mypy src tests`: Success: no issues found in 16 source files.
- Full Git roundtrip verified: `main..feature` packed from Repo A and unpacked into Repo B with matching files, checkout, and clean `git fsck`.

## Decisions

- **Two-phase unpack**: Verify all objects first, then write loose objects, then update refs.
- **Strict quarantine requirement**: Missing quarantined binaries without `--sidechannel` blocks ref updates, protecting the integrity of the commit graph.
- **Tree formatting**: Trees are written in human-readable `ls-tree` plain text without null bytes.

## Open Fronts

- None. Ready for Milestone 6 (BDD Acceptance Suite).

## Next Actions

- Fold closure into commit `feat(cli): implement pack and unpack orchestrators`.
- Advance `main` bookmark in `jj`.
