# ptbundle Workboard

> **Status:** Active Development
> **Last Sync:** 2026-09-23

## 0. Focus Queue

<!-- WORKBOARD:NOW:START -->
- **[`260923-bdd-phase2-acceptance`]** **Delta Compression Acceptance Scenario**: Create a realistic repository history with multiple commits iteratively modifying wide directory trees and ...
- **[`260923-git-bundle-bridge`]** **`from-bundle` Subcommand**: `ptbundle from-bundle <bundle_file> -o <ptbundle_dir> [--whitelist-ext ...]` Unpacks the bundle into an isolated tempora...
<!-- WORKBOARD:NOW:END -->

## 1. Relationship Tree

<!-- WORKBOARD:RELATIONSHIP_ROOTS:START -->
`260923-plain-text-delta-engine`
`260923-git-bundle-bridge`
<!-- WORKBOARD:RELATIONSHIP_ROOTS:END -->

<!-- WORKBOARD:RELATIONSHIP_TREE:START -->
- Warning: root `260923-plain-text-delta-engine` not rendered (closed task).
- `260923-git-bundle-bridge`: **`from-bundle` Subcommand**: `ptbundle from-bundle <bundle_file> -o <ptbundle_dir> [--whitelist-ext ...]` Unpacks the bundle into an isolated tempora... (depends on `260922-git-repo-io`; blocks `260923-bdd-phase2-acceptance`; related `260923-delta-pack-unpack-integration`)
<!-- WORKBOARD:RELATIONSHIP_TREE:END -->

## 2. Inbox

<!-- WORKBOARD:INBOX:START -->
- _Inbox is empty._
<!-- WORKBOARD:INBOX:END -->

## 3. Recent Closures

<!-- WORKBOARD:CLOSED:START -->
- **[`260923-plain-text-delta-engine`]** - `uv run pytest tests/test_delta.py --cov=ptbundle.delta` passes 11/11 tests with 100% statement and branch coverage (2
- **[`260923-delta-pack-unpack-integration`]** - `uv run pytest` passes 77/77 tests with 100.00% statement and branch coverage (1213 statements, 468 branches, 0 missin
- **[`260922-scaffold-project-disciplines`]** - `uv run pytest`: 5 passed in 0.04s with 100% line and branch coverage (`--cov-fail-under=100`).
- **[`260922-pack-unpack-orchestrators`]** - `uv run pytest`: 55 passed in 1.46s with 100% line and branch coverage (`--cov-fail-under=100`).
- **[`260922-inspection-quarantine-policy`]** - `uv run pytest`: 44 passed in 0.22s with 100% line and branch coverage (`--cov-fail-under=100`).
- **[`260922-git-repo-io`]** - `uv run pytest`: 49 passed in 0.60s with 100% line and branch coverage (`--cov-fail-under=100`).
- **[`260922-git-object-model`]** - `uv run pytest`: 27 passed in 0.18s with 100% line and branch coverage (`--cov-fail-under=100`).
- **[`260922-bundle-manifest-engine`]** - `uv run pytest`: 36 passed in 0.20s with 100% line and branch coverage (`--cov-fail-under=100`).
- **[`260922-bdd-acceptance-suite`]** - `uv run pytest`: 62 passed in 2.28s, 100% statement and branch coverage (890 statements, 302 branches).
<!-- WORKBOARD:CLOSED:END -->
