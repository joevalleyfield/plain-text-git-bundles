Filed as: 260922-git-repo-io
FKA:
AKA: git repo io; git repository interface; loose object injection; delta traversal
Legacy index:

keywords: repo, implementation, closed, contract, correctness

Parent:
Depends on: `260922-git-object-model`, `260922-bundle-manifest-engine`, `260922-inspection-quarantine-policy`
Blocks:
Blocked by:
Related:

# Implement Git Repository Interface and Object I/O Engine

Implement Git repository discovery, revision delta traversal (`git rev-list`), loose object reading and atomic injection, prerequisite validation, and reference updates for `ptbundle`.

## Current Reality

The Git repository interface and object I/O engine are fully implemented and verified in `src/ptbundle/repo.py`:
- `GitRepo` provides upward repository discovery supporting standard `.git` directories and worktree/submodule `gitdir:` pointer files.
- `discover_delta` extracts revision deltas, resolves target tips and references, discovers boundary prerequisite commits via `git rev-list --boundary`, and streams object metadata and raw payloads in a single pass via `git cat-file --batch`.
- `verify_prerequisites` verifies base commit existence before ingress operations.
- `inject_loose_object` injects reconstituted Git objects directly into `.git/objects/xx/xxxx` using zero-dependency `zlib.compress`, written atomically via temporary files (`os.replace`) and skipped idempotently if already present.
- `update_reference` updates or creates repository references safely using porcelain `git update-ref`.
- 100% statement and branch test coverage enforced via `pytest-cov`.
- Zero external runtime dependencies (Python standard library only).

## Desired Reality

A dedicated module `src/ptbundle/repo.py` implementing:
1. **Repository Discovery (`GitRepo`)**:
   - Find Git repository root from any working directory path, supporting both standard `.git` directories and `.git` worktree pointer files (`gitdir: ...`).
2. **Delta Discovery (`DeltaSpec`, `discover_delta`)**:
   - Given a revision range (e.g. `origin/main..feature` or `HEAD~2..HEAD`) or single ref tip:
     - Execute `git rev-list --boundary <range>` to discover boundary/prerequisite commits (lines starting with `-<oid>`).
     - Execute `git rev-list --objects <range>` to discover all commits, trees, and blobs in the delta with their associated paths.
     - Resolve target reference names and tip OIDs via `git rev-parse`.
3. **Object Extraction (Egress / Pack)**:
   - Extract raw object payloads and types using `git cat-file --batch` or direct loose object reads.
   - Pair each blob OID with its repository file path from the tree traversal so extension and policy checks can be applied.
4. **Ingress Validation & Loose Object Injection (Ingress / Unpack)**:
   - **Prerequisite Verification**: Check that all prerequisite commits exist in the target repository before applying any changes (`git cat-file -e <oid>^{commit}`).
   - **Loose Object Writer**: Inject reconstituted objects into `.git/objects/xx/xxxx` using zero-dependency Python `zlib.compress(format_git_object(type, payload))`.
   - **Atomic Safety**: Write to a temporary file in `.git/objects/` and atomically rename to `.git/objects/xx/xxxx`. Check if object already exists to avoid redundant writes.
   - **Atomic Ref Update**: Update target branch references via `git update-ref <refname> <oid>`.
5. **Complete Test Suite**:
   - 100% statement and branch test coverage in `tests/test_repo.py`.
   - End-to-end integration with temporary Git repositories created with `git init`.
6. **Zero External Dependencies**:
   - Standard library only (`subprocess`, `pathlib`, `zlib`, `os`, `shutil`).

## Gap Analysis

All gaps closed:
- `src/ptbundle/repo.py` implemented with complete typing and docstrings.
- `tests/test_repo.py` implemented with 5 integration and unit tests covering repo discovery, worktrees, deltas, cat-file batch streaming, loose object injection, fsck validation, and reference updates.
- 100.00% statement and branch coverage maintained across `src/ptbundle`.

## Known Facts / Assumptions / Unknowns

### Known Facts
- Loose objects are stored in `.git/objects/<2-char-prefix>/<38-char-hash>` compressed with standard zlib deflate.
- `git rev-list --objects <range>` outputs lines formatted as `<oid>` for commits/trees and `<oid> <path>` for blobs and subtrees.
- `git rev-list --boundary <range>` outputs boundary commits prefixed with `-`.
- `git update-ref <ref> <oid>` is the canonical porcelain-safe way to update Git references atomically.

### Working Assumptions
- The system has `git` installed and available on `PATH` for repo discovery and rev-list operations.
- Direct loose object injection avoids spawning subprocesses for thousands of objects, making unpack fast and zero-overhead.

### Unknowns
- None.

## Investigations

- Verified that `git cat-file --batch` streams objects with exact `<size>` byte payloads and trailing newline delimiters without subprocess spawning per object.
- Verified that `git fsck` confirms repository integrity after loose object injection.

## Models / Forecasts / Risks

- **Corrupted Loose Object Writes**: Prevented by atomic temporary file creation in `.git/objects/` followed by `os.replace`.

## Transformations

1. Created `src/ptbundle/repo.py` implementing `GitRepo`, `DeltaSpec`, `DeltaObject`, `discover_delta`, `verify_prerequisites`, `inject_loose_object`, and `update_reference`.
2. Created integration tests in `tests/test_repo.py` covering all features and error states.
3. Formatted and linted code with `ruff check` and `ruff format`. Verified strict typing with `mypy src tests`.
4. Moved task from `tasks/open/260922-git-repo-io.md` to `tasks/closed/260922-git-repo-io.md`.
5. Refreshed workboard with `uv run python tasks/scripts/sync_workboard.py`.

## Evidence

- `uv run pytest`: 49 passed in 0.60s with 100% line and branch coverage (`--cov-fail-under=100`).
- `uv run ruff check .`: Clean (0 errors).
- `uv run ruff format --check .`: 23 files already formatted.
- `uv run mypy src tests`: Success: no issues found in 12 source files.

## Decisions

- **Single-pass batch extraction**: Used `git cat-file --batch` to stream all delta object payloads in one pipeline, avoiding subprocess spawning per object.
- **Direct zlib loose object writes**: Used Python `zlib` to write directly to `.git/objects/xx/` via temporary files and `os.replace` rather than shelling out to `git hash-object -w`.
- **Porcelain ref updates**: Used `git update-ref` for updating branches and tags to ensure reflog updates and lockfile safety are respected.

## Open Fronts

- None. Ready for Milestone 5 (CLI Orchestrators).

## Next Actions

- Fold closure into commit `feat(repo): implement git repository interface and object io engine`.
- Advance `main` bookmark in `jj`.
