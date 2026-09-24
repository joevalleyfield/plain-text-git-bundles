Filed as: 260923-delta-pack-unpack-integration
FKA:
AKA: delta pack and unpack; delta wire format; manifest delta metrics
Legacy index:

keywords: pack, unpack, integration, active, contract, usability

Parent:
Depends on: `260923-plain-text-delta-engine`
Blocks: `260923-bdd-phase2-acceptance`
Blocked by:
Related: `260923-git-bundle-bridge`

# Integrate Plain-Text Delta Engine into Pack and Unpack Orchestrators

Integrate the plain-text delta engine into `pack_bundle` and `unpack_bundle`, update the manifest engine to record delta metrics, and add CLI ergonomics (`--no-delta`).

## Current Reality

- `pack_bundle` currently writes all text blobs as full files under `blobs/xx/<sha>.txt` and all trees under `trees/xx/<sha>.txt`.
- `unpack_bundle` expects all objects in `blobs/` to be full payloads.
- Manifest metrics track `trees`, `blobs_text`, `blobs_binary`, and `blobs_quarantined`.

## Desired Reality

1. **Pack Integration (`src/ptbundle/pack.py`)**:
   - Track commit parent/child relationships in the rev-list to identify path-level ancestor blobs and trees.
   - For text blobs sharing a path across commits, generate a candidate delta against the predecessor blob.
   - For trees across commits, generate candidate deltas against predecessor root/subtrees.
   - If the candidate delta is smaller than the full text payload, write `blobs/xx/<target_sha>.delta.txt` or `trees/xx/<target_sha>.delta.txt`.
   - Provide a `--no-delta` CLI flag to bypass delta compression if desired.
2. **Manifest Updates (`src/ptbundle/manifest.py`)**:
   - Support `trees_full`, `trees_delta`, `blobs_text`, `blobs_delta` in manifest metrics while preserving backwards compatibility with v1 manifests.
3. **Unpack Integration (`src/ptbundle/unpack.py`)**:
   - Topological resolution:
     - Load all full trees and blobs first.
     - Discover and resolve `.delta.txt` tree objects against their base trees, validating OIDs.
     - Discover and resolve `.delta.txt` blob objects against their base blobs, validating OIDs.
     - Inject loose objects into target `.git/objects`.
4. **Complete Unit Tests**:
   - 100% statement and branch coverage across updated modules.

## Gap Analysis

- `src/ptbundle/pack.py` needs delta selection logic and `--no-delta` support.
- `src/ptbundle/manifest.py` needs updated metrics parsing/formatting.
- `src/ptbundle/unpack.py` needs topological delta resolution.
- Unit tests in `tests/test_pack.py`, `tests/test_unpack.py`, and `tests/test_manifest.py` need updating.

## Known Facts / Assumptions / Unknowns

### Known Facts
- Topological resolution must resolve full base objects before delta objects.
- In multi-commit deltas, a tree or blob delta may depend on another delta (delta chains). A loop or topological sort easily resolves this in $O(N)$ passes.

## Transformations

1. Update `src/ptbundle/manifest.py`.
2. Update `src/ptbundle/pack.py`.
3. Update `src/ptbundle/unpack.py`.
4. Update `src/ptbundle/cli.py`.
5. Update unit tests in `tests/`.

## Evidence

- `uv run pytest` passes with 100% statement and branch coverage.

## Decisions

- **Topological resolution strategy**: Resolve full objects into a cache first, then iteratively resolve delta objects whose base is present in the cache until all deltas are resolved.

## Open Fronts

- BDD scenario testing (tracked in `260923-bdd-phase2-acceptance`).

## Next Actions

- Implement manifest metric updates.
- Wire delta candidate selection into `pack.py`.
- Wire topological delta resolution into `unpack.py`.
