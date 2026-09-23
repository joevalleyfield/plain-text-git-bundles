Filed as: 260922-pack-unpack-orchestrators
FKA:
AKA: pack and unpack orchestrators; cli integration; end-to-end bundle creation and ingress
Legacy index:

keywords: pack, unpack, cli, implementation, active, usability, correctness

Parent:
Depends on: `260922-git-object-model`, `260922-bundle-manifest-engine`, `260922-inspection-quarantine-policy`, `260922-git-repo-io`
Blocks:
Blocked by:
Related:

# Implement Pack and Unpack CLI Orchestrators

Connect domain object models, manifest engine, inspection policies, and repository I/O into end-to-end `pack` and `unpack` orchestrators exposed through the `ptbundle` CLI.

## Current Reality

All foundational building blocks are implemented and individually verified:
- `objects.py`: Bit-exact Git object models and canonical plain-text serializers.
- `manifest.py`: `manifest.txt` parser, serializer, and validation.
- `policy.py`: Text vs. binary classification, extension/signature whitelisting, and quarantine management.
- `repo.py`: Git repository discovery, delta traversal, batch extraction, loose object injection, and reference updates.

However, `src/ptbundle/cli.py` still contains stub implementations that print placeholder messages, and there are no orchestrator modules tying these pieces together into cohesive `pack` and `unpack` workflows.

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

- Need `src/ptbundle/pack.py` orchestrating delta emission, directory partitioning, and manifest generation.
- Need `src/ptbundle/unpack.py` orchestrating prerequisite validation, cryptographic reconstruction, loose object injection, sidechannel reconciliation, and ref updates.
- Need to update `src/ptbundle/cli.py` to invoke the orchestrators and format terminal output.
- Need unit and integration tests in `tests/test_pack.py`, `tests/test_unpack.py`, and updated `tests/test_cli.py`.

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

- Verify behavior when packing a clean branch with 100% text files vs. mixed text and images.
- Verify unpack into a detached-HEAD or fresh repository clone.

## Models / Forecasts / Risks

- **Partial Ingress Corruption**: If an object fails cryptographic verification halfway through unpacking, loose objects written up to that point remain in `.git/objects` (unreferenced), but the target ref must NOT be updated. This ensures Git repository consistency is always preserved.

## Transformations

1. Create `src/ptbundle/pack.py` implementing `pack_bundle`.
2. Create `src/ptbundle/unpack.py` implementing `unpack_bundle` and `UnpackResult`.
3. Update `src/ptbundle/cli.py` to route `pack` and `unpack` commands to the orchestrators.
4. Create `tests/test_pack.py` and `tests/test_unpack.py`, and update `tests/test_cli.py`.
5. Update `tasks/open/260922-pack-unpack-orchestrators.md` with progress stitching.

## Evidence

- `uv run pytest`: 100% statement and branch coverage across all modules.
- `uv run ruff check .` and `uv run ruff format --check .`: Clean.
- `uv run mypy src tests`: Clean type check.
- Real Git repository round-trip: pack a commit range from repo A, unpack into repo B, and verify `git log` and `git diff` match byte-for-byte.

## Decisions

- **Two-phase unpack**: Verify all objects first, then write loose objects, then update refs.
- **Strict quarantine requirement**: Missing quarantined binaries without `--sidechannel` blocks ref updates, protecting the integrity of the commit graph.

## Open Fronts

- None.

## Next Actions

1. Review task with thread peer.
2. Begin TDD cycle: write tests and implement `pack.py`, `unpack.py`, and CLI integration.
