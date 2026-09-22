# ptbundle Agent Notes & Disciplines

## Portable and Local Runners

Use `uv` directly in shared scripts, task instructions, and commands so they work across local and CI environments.
The local `.codex-local/bin/uvt` or `.gemini-local/bin/uvt` wrapper is a developer convenience; if present, prefer it, otherwise use `uv`.

## Jujutsu (jj) Workflow

- Workspace VCS is `jj` colocated with Git (`.jj` exists in repository root).
- `jj commit` = `jj describe && jj new` — the working copy `@` is empty by default.
- Never do `jj abandon @` — if you want to undo or edit a prior commit, use `jj edit @-`.
- To inspect the last commit diff: `jj diff --git -r @-`.
- To inspect the last commit details: `jj show --git @-`.

## Concentric Development Rhythm (RDD -> BDD -> TDD)

Development follows three concentric feedback loops:

```text
       ┌──────────────────────────────────────────────────┐
       │ Outer Loop: Readme-Driven Development (RDD)      │
       │  • README is the user-facing contract and truth │
       │  • Specs, CLI UX, and wire format designed first │
       │  ┌────────────────────────────────────────────┐  │
       │  │ Middle Loop: Behavior-Driven Dev (BDD)     │  │
       │  │  • Scenarios & acceptance workflows        │  │
       │  │  • Interoperability with canonical git     │  │
       │  │  ┌──────────────────────────────────────┐  │  │
       │  │  │ Inner Loop: Test-Driven Dev (TDD)    │  │  │
       │  │  │  • Unit red/green/refactor cycle     │  │  │
       │  │  │  • 100% coverage on every component  │  │  │
       │  │  └──────────────────────────────────────┘  │  │
       │  └────────────────────────────────────────────┘  │
       └──────────────────────────────────────────────────┘
```

1. **Outer Loop: Readme-Driven Development (RDD)**
   - The user contract, command ergonomics, data format, and invariants are defined in [README.md](README.md) before code is written.
   - Any architectural or behavior change must begin by aligning the documentation.
2. **Middle Loop: Behavior-Driven Development (BDD)**
   - End-to-end user workflows and ingress/egress scenarios are defined via executable specifications (`pytest-bdd` / integration scenarios).
   - Validates that bundles generated from real Git histories unpack cleanly into target repositories with bit-exact integrity.
3. **Inner Loop: Test-Driven Development (TDD)**
   - Micro-level red/green/refactor cycle driving individual modules, parsers, serializers, and OID hashers.
   - 100% branch and statement test coverage enforced on all production code in `src/ptbundle`.

## Task & Commit Discipline

- **Task Naming**: `tasks/open/YYMMDD-short-intent.md` (see [tasks/README.md](tasks/README.md) for full taxonomy and template).
- **Task Metadata**: Always maintain continuity fields (`Filed as:`, `FKA:`, `AKA:`, `Legacy index:`), `keywords:`, and relationship links (`Parent:`, `Depends on:`, `Blocks:`, `Blocked by:`, `Related:`).
- **Opening Tasks**: Open tasks must be committed alone or in groups as `tasks: ...` commits (e.g. `tasks: open task for delta pack algorithm`).
- **Progress Stitching**: Commits making progress on a task must update the task file in the same commit to stitch task status/evidence directly to the code or docs change.
- **Closure Folding**: Task closure (moving from `tasks/open/` to `tasks/closed/` with full acceptance evidence) can be folded in with the final commit of a feature or fix (e.g. `feat(pack): implement delta pack generation`).
- **Conventional Commits**: Commit messages follow `type(scope): summary` or `type: summary` with types:
  - `feat`: new feature or functionality
  - `fix`: bug fix
  - `docs`: user, contributor, or architectural documentation
  - `tasks`: opening, retitling, or organizing task files and workboard
  - `test`: test additions and fixture improvements
  - `refactor`: structural changes without changing behavior
  - `chore` / `build`: build configuration, tooling, and dependencies
- **Workboard Sync**: Run `python3 tasks/scripts/sync_workboard.py` whenever tasks are created, updated, moved, or closed.

## Architectural Invariants

- **Zero Runtime Dependencies**: The core package `ptbundle` must rely exclusively on Python standard library modules (`hashlib`, `pathlib`, `argparse`, `sys`, `subprocess`, etc.).
- **Bit-Exact Git Object Hashes**: Git object IDs are cryptographically non-negotiable. Hashing reconstituted payloads (`<type> <size>\0<payload>`) must match canonical Git SHA-1 and SHA-256 byte-for-byte.
- **Strict Ingress Safety**: Unpacking must validate prerequisites and hashes before injecting loose objects into `.git/objects`. Binaries must follow strict extension whitelisting and quarantine routing.

## Verification Commands

- **Run test suite with 100% coverage enforcement**:
  ```bash
  uv run pytest
  ```
- **Linting**:
  ```bash
  uv run ruff check .
  ```
- **Formatting**:
  ```bash
  uv run ruff format --check .
  ```
- **Type Checking**:
  ```bash
  uv run mypy src tests
  ```
- **Sync Workboard**:
  ```bash
  python3 tasks/scripts/sync_workboard.py
  ```
