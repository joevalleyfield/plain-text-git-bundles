Filed as: 260923-bdd-phase2-acceptance
FKA:
AKA: phase 2 bdd; delta and bridge acceptance scenarios
Legacy index:

keywords: bdd, acceptance, closed, correctness, contract

Parent:
Depends on: `260923-delta-pack-unpack-integration`, `260923-git-bundle-bridge`
Blocks:
Blocked by: `260923-delta-pack-unpack-integration`, `260923-git-bundle-bridge`
Related:

# BDD Acceptance Scenarios for Phase 2 (Deltas & Bundle Bridge)

Implement end-to-end BDD acceptance scenarios verifying bidirectional Git bundle conversion and multi-commit plain-text delta compression (blobs and trees) against real Git histories.

## Current Reality

- `tests/test_bdd_scenarios.py` tests Phase 1 workflows:
  - Clean delta pack and unpack roundtrip.
  - Extension whitelisting and spoofing rejection.
  - Quarantine side-channel reconciliation.
  - Multi-commit linear history.
- Phase 2 scenarios implemented in `tests/features/phase2_interop_deltas.feature` and `tests/test_bdd_scenarios.py`.

## Desired Reality

1. **Delta Compression Acceptance Scenario**:
   - Create a realistic repository history with multiple commits iteratively modifying wide directory trees and text files.
   - Run `ptbundle pack` and verify:
     - Iterative text changes are saved as `.delta.txt` in `blobs/`.
     - Repeated tree modifications are saved as `.delta.txt` in `trees/`.
     - `manifest.txt` records `trees_delta` and `blobs_delta`.
   - Run `ptbundle unpack` into a target clone and verify:
     - All commits, trees, and blobs reconstitute bit-exactly.
     - Working tree and `git log` match source repository byte-for-byte.
2. **Git Bundle Bridge Roundtrip Scenario**:
   - Create a source Git repo and generate a canonical Git bundle using `git bundle create`.
   - Run `ptbundle from-bundle` to produce a plain-text bundle directory.
   - Run `ptbundle to-bundle` to synthesize a new `.bundle` file.
   - Run `git bundle verify` on the synthesized file.
   - Clone from the synthesized `.bundle` using canonical `git clone` and verify repository integrity.

## Gap Analysis

- Closed. All BDD scenarios implemented and verified.

## Transformations

1. Add scenarios to `tests/test_bdd_scenarios.py` and `tests/features/phase2_interop_deltas.feature`.
2. Run full test suite with coverage enforcement.

## Evidence

- Added BDD acceptance scenarios in `tests/features/phase2_interop_deltas.feature` and step definitions in `tests/test_bdd_scenarios.py`:
  1. Multi-commit text and tree plain-text delta compression with unpack and verification.
  2. Bidirectional conversion between canonical Git `.bundle` files and plain-text `ptbundle` directories with `git bundle verify` and `git clone`.
- `uv run pytest`: 85 passed with 100% statement and branch coverage across all 10 modules in `src/ptbundle`.
- `uv run ruff check .`: clean.
- `uv run ruff format --check .`: 38 files verified cleanly.
- `uv run mypy src tests`: clean (21 source files, 0 issues).

## Decisions

- **Full Ecosystem Interop**: The BDD test invokes both `git` and `ptbundle` CLI binaries to verify real-world interoperability.

## Open Fronts

- None.

## Next Actions

- None; task completed.
