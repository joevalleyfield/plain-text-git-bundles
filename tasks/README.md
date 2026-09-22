# Tasks

This directory holds active, closed, and recurring task files for `ptbundle`.

## Filename Naming Scheme

Use `YYMMDD-short-intent.md` for all new task files.

```text
tasks/open/260922-scaffold-project-disciplines.md
tasks/closed/260922-initial-readme.md
```

Rules:
- `YYMMDD` = year (2-digit) + month + day of creation. Easy to mint, gives chronology.
- `short-intent` = kebab-case slug describing the task. Keep it under ~40 chars.
- Same-day same-slug collision is rare; when it happens, disambiguate the slug or merge/split the tasks.
- Do not use random ids or artificial prefixes by default.

## Continuity Fields

Include these near the top of every task file:

```markdown
Filed as: 260922-scaffold-project-disciplines
FKA:
AKA: project bootstrap; initial scaffolding
Legacy index:
```

- `Filed as:` records the original handle at creation. Never change this line.
- `FKA:` lists previous handles after renames, separated by semicolons.
- `AKA:` lists search-friendly aliases and alternate phrasings, separated by semicolons.
- `Legacy index:` holds old numerical task ids for backward search continuity.

## Relationship Fields

Tasks should preserve graph structure when dependencies or hierarchies exist.

Use lightweight relationship lines in prose near the top of the file:

```markdown
Parent: `260922-parent-task`
Depends on: `260922-prerequisite-task`
Blocks: `260922-dependent-task`
Blocked by: `260922-prerequisite-task`
Related: `260922-adjacent-task`
```

Guidelines:
- `Parent:` means the task is a child of an umbrella or coordination task.
- `Depends on:` means this task has a real prerequisite or causal dependency.
- `Blocked by:` means the unresolved subset of `Depends on:`.
- `Blocks:` means other tasks are actively gated on this task.
- `Related:` means adjacency matters, but execution order does not.

## Keyword Convention

Use a single `keywords:` line near the top of each task file.

```markdown
keywords: runtime, implementation, active, packaging, cli
```

Controlled vocabulary:
- `domain`: `pack`, `unpack`, `manifest`, `crypto`, `quarantine`, `cli`, `tooling`, `docs`
- `mode`: `implementation`, `hardening`, `decomp`, `governance`, `investigation`, `explore`
- `lifecycle`: `active`, `inception`, `parked`, `blocked`, `follow-on`, `historical`
- `objective`: `correctness`, `maintainability`, `contract`, `usability`, `performance`, `compatibility`

## Commit & Task Lifecycle Disciplines

1. **Opening Tasks**: Open tasks should be committed alone or in groups as `tasks: ...` commits (e.g. `tasks: open task for delta pack algorithm`).
2. **Progress Stitching**: Any commit that materially achieves ends called for by a task must update that task file in the same commit to stitch task status/progress directly to the code or docs change.
3. **Closure Folding**: Task closure (moving the task from `tasks/open/` to `tasks/closed/` with verified acceptance evidence) can be folded into the final commit of a feature or fix (e.g. `feat(pack): implement delta pack generation`).

## Operational Workboard

- Run `python3 tasks/scripts/sync_workboard.py` whenever tasks are added, updated, moved, or closed.
- Keep `tasks/WORKBOARD.md` as the active operational dashboard.
