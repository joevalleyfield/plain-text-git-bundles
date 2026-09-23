Filed as: 260922-git-repo-io
FKA:
AKA: git repo io; git repository interface; loose object injection; delta traversal
Legacy index:

keywords: repo, implementation, active, contract, correctness

Parent:
Depends on: `260922-git-object-model`, `260922-bundle-manifest-engine`, `260922-inspection-quarantine-policy`
Blocks:
Blocked by:
Related:

# Implement Git Repository Interface and Object I/O Engine

Implement Git repository discovery, revision delta traversal (`git rev-list`), loose object reading and atomic injection, prerequisite validation, and reference updates for `ptbundle`.

## Current Reality

The foundational models for Git objects (`objects.py`), transfer manifests (`manifest.py`), and quarantine policies (`policy.py`) are fully implemented and tested. However, `ptbundle` currently has no interface to communicate with live Git repositories:
- Cannot discover repository roots or `.git` paths.
- Cannot query Git for delta object sets (`git rev-list --objects`, `git rev-list --boundary`).
- Cannot extract objects from repository object databases or inject reconstituted loose objects into `.git/objects`.
- Cannot validate prerequisite commits or update destination branch references.

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

- Need `GitRepo` helper encapsulating Git command execution and `.git` path resolution.
- Need robust parser for `git rev-list --objects` and `git rev-list --boundary`.
- Need high-performance, atomic loose object injector that directly writes `.git/objects/xx/<38-chars>` with zlib compression.
- Need tests exercising delta discovery, prerequisite checks, object injection, and ref updates against real Git repositories.

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

- Verify behavior when revision range has no boundary (e.g. initial branch commit or full repository export). The prerequisites list should be empty.
- Verify behavior when writing an object that already exists in `.git/objects`. It should be skipped safely without error.

## Models / Forecasts / Risks

- **Corrupted Loose Object Writes**: Writing directly to the destination path could leave partial files on disk if interrupted. Writing to a temporary file in the same filesystem (`.git/objects/tmp_...`) followed by `os.replace` guarantees atomicity.

## Transformations

1. Create `src/ptbundle/repo.py` implementing `GitRepo`, `DeltaSpec`, `discover_delta`, `read_git_objects`, `inject_loose_object`, `verify_prerequisites`, and `update_reference`.
2. Create unit and integration tests in `tests/test_repo.py` with 100% statement and branch test coverage.
3. Update `tasks/open/260922-git-repo-io.md` with progress stitching.

## Evidence

- `uv run pytest`: 100% statement and branch coverage on `src/ptbundle/repo.py`.
- `uv run ruff check .` and `uv run ruff format --check .`: Clean.
- `uv run mypy src tests`: Clean type check.

## Decisions

- **Direct zlib loose object writes**: Use Python `zlib` to write directly to `.git/objects/xx/` rather than shelling out to `git hash-object -w` per object. This is significantly faster and uses zero runtime dependencies.
- **Porcelain ref updates**: Use `git update-ref` for updating branches and tags to ensure reflog updates and lockfile safety are respected.

## Open Fronts

- None.

## Next Actions

1. Review task with thread peer.
2. Begin TDD cycle: write tests in `tests/test_repo.py` and implement `src/ptbundle/repo.py`.
