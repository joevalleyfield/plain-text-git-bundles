Filed as: 260923-bdd-phase2-acceptance
FKA:
AKA: phase 2 bdd; delta and bridge acceptance scenarios
Legacy index:

keywords: bdd, acceptance, active, correctness, contract

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
- No acceptance scenarios exist for `.delta.txt` compression or `from-bundle` / `to-bundle`.

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

- New BDD scenario tests need to be added to `tests/test_bdd_scenarios.py`.

## Transformations

1. Add scenarios to `tests/test_bdd_scenarios.py`.
2. Run full test suite with coverage enforcement.

## Evidence

- `uv run pytest` passes 100% of tests with 100% statement and branch coverage.

## Decisions

- **Full Ecosystem Interop**: The BDD test must invoke both `git` and `ptbundle` CLI binaries to verify real-world interoperability.

## Open Fronts

- None once implemented.

## Next Actions

- Implement BDD acceptance scenarios.
