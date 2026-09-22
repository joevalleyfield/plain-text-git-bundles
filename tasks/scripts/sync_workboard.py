#!/usr/bin/env python3
"""
Syncs task inventory into tasks/WORKBOARD.md for ptbundle.

Managed sections:
- relationship tree
- open queue
- inbox
- recent closures
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
TASKS_DIR = PROJECT_ROOT
WORKBOARD_PATH = PROJECT_ROOT / "WORKBOARD.md"

STALE_THRESHOLD_DAYS = 30

NOW_START = "<!-- WORKBOARD:NOW:START -->"
NOW_END = "<!-- WORKBOARD:NOW:END -->"
INBOX_START = "<!-- WORKBOARD:INBOX:START -->"
INBOX_END = "<!-- WORKBOARD:INBOX:END -->"
CLOSED_START = "<!-- WORKBOARD:CLOSED:START -->"
CLOSED_END = "<!-- WORKBOARD:CLOSED:END -->"
REL_ROOTS_START = "<!-- WORKBOARD:RELATIONSHIP_ROOTS:START -->"
REL_ROOTS_END = "<!-- WORKBOARD:RELATIONSHIP_ROOTS:END -->"
REL_TREE_START = "<!-- WORKBOARD:RELATIONSHIP_TREE:START -->"
REL_TREE_END = "<!-- WORKBOARD:RELATIONSHIP_TREE:END -->"

RELATIONSHIP_PREFIXES = (
    "Parent:",
    "Depends on:",
    "Blocks:",
    "Blocked by:",
    "Related:",
)
METADATA_PREFIXES = (
    "Filed as:",
    "FKA:",
    "AKA:",
    "Legacy index:",
    "keywords:",
    *RELATIONSHIP_PREFIXES,
)
TASK_REF_RE = re.compile(r"`([^`]+)`")


@dataclass
class TaskRecord:
    id: str
    title: str
    objective: str
    path: Path
    parent: str | None = None
    depends_on: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)


def _sort_key(task_id: str) -> tuple[int, str]:
    match = re.match(r"^(\d+)", task_id)
    return (int(match.group(1)) if match else 0, task_id)


def _extract_refs(value: str) -> list[str]:
    refs = [match.strip() for match in TASK_REF_RE.findall(value)]
    if refs:
        return refs
    parts = [part.strip() for part in value.split(";")]
    return [part for part in parts if part]


def _extract_section(lines: list[str], content: str, headings: tuple[str, ...]) -> str:
    def _matches(line: str, heading: str) -> bool:
        stripped = line.strip()
        if not stripped.startswith("## "):
            return False
        return stripped[3:].strip().casefold() == heading.casefold()

    for heading in headings:
        start_line_idx = next(
            (idx for idx, line in enumerate(lines) if _matches(line, heading)),
            None,
        )
        if start_line_idx is None:
            continue
        section_lines: list[str] = []
        for line in lines[start_line_idx + 1 :]:
            if line.strip().startswith("## "):
                break
            section_lines.append(line)
        return "\n".join(section_lines).strip()
    return ""


def _human_title(lines: list[str], stem: str) -> str:
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            text = stripped[2:].strip()
            if text and text != stem:
                return text
    return ""


def _lead_paragraph(lines: list[str]) -> str:
    seen_title = False
    collected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not seen_title:
            if stripped.startswith("# ") and not stripped.startswith("## "):
                seen_title = True
            continue
        if stripped.startswith("## "):
            break
        if any(stripped.startswith(prefix) for prefix in METADATA_PREFIXES):
            continue
        if not stripped:
            if collected:
                break
            continue
        collected.append(stripped)
    return " ".join(collected).strip()


def parse_task(filepath: Path) -> TaskRecord | None:
    try:
        content = filepath.read_text(encoding="utf-8")
        lines = content.splitlines()
        title = filepath.stem
        objective = _extract_section(lines, content, ("Objective", "Goal", "Desired Reality"))
        if not objective:
            objective = _lead_paragraph(lines)
        if not objective:
            objective = _human_title(lines, title)

        relationships = {
            "parent": None,
            "depends_on": [],
            "blocks": [],
            "blocked_by": [],
            "related": [],
        }
        for raw_line in lines:
            line = raw_line.strip()
            if line.startswith("Parent:"):
                refs = _extract_refs(line.partition(":")[2].strip())
                relationships["parent"] = refs[0] if refs else None
            elif line.startswith("Depends on:"):
                relationships["depends_on"] = _extract_refs(line.partition(":")[2].strip())
            elif line.startswith("Blocks:"):
                relationships["blocks"] = _extract_refs(line.partition(":")[2].strip())
            elif line.startswith("Blocked by:"):
                relationships["blocked_by"] = _extract_refs(line.partition(":")[2].strip())
            elif line.startswith("Related:"):
                relationships["related"] = _extract_refs(line.partition(":")[2].strip())

        if objective:
            clean_lines = []
            for line in objective.split("\n"):
                clean_lines.append(re.sub(r"^(\s*[-*]\s|\s*\d+\.\s)", "", line))
            collapsed = " ".join(clean_lines).strip()
            objective = collapsed[:150] + ("..." if len(collapsed) > 150 else "")

        return TaskRecord(
            id=title,
            title=title,
            objective=objective,
            path=filepath,
            parent=relationships["parent"],
            depends_on=relationships["depends_on"],
            blocks=relationships["blocks"],
            blocked_by=relationships["blocked_by"],
            related=relationships["related"],
        )
    except Exception:
        return None


def get_tasks(directory: Path) -> list[TaskRecord]:
    if not directory.exists():
        return []
    tasks: list[TaskRecord] = []
    for path in directory.iterdir():
        if path.suffix != ".md":
            continue
        task = parse_task(path)
        if task:
            tasks.append(task)
    tasks.sort(key=lambda task: _sort_key(task.id))
    return tasks


def get_open_tasks() -> list[TaskRecord]:
    return get_tasks(TASKS_DIR / "open")


def get_closed_tasks(limit: int = 10) -> list[TaskRecord]:
    tasks = get_tasks(TASKS_DIR / "closed")
    tasks.sort(key=lambda task: _sort_key(task.id), reverse=True)
    return tasks[:limit]


def get_open_task_ids() -> set[str]:
    return {task.id for task in get_open_tasks()}


def check_stale_tasks(task_ids: set[str]) -> set[str]:
    stale_ids: set[str] = set()
    for task_id in task_ids:
        path = TASKS_DIR / "open" / f"{task_id}.md"
        if not path.exists():
            continue
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%ct", str(path)],
                capture_output=True,
                text=True,
                cwd=str(PROJECT_ROOT),
                check=False,
            )
        except Exception:
            continue
        if result.returncode != 0 or not result.stdout.strip():
            continue
        last_modified = int(result.stdout.strip())
        days_old = (datetime.now().timestamp() - last_modified) / 86400
        if days_old > STALE_THRESHOLD_DAYS:
            stale_ids.add(task_id)
    return stale_ids


def get_inbox_items() -> list[str]:
    inbox_dir = TASKS_DIR / "in"
    items: list[str] = []
    if inbox_dir.exists():
        for path in sorted(inbox_dir.iterdir()):
            if path.suffix == ".md":
                items.append(f"`{path.stem}`")
    inbox_path = TASKS_DIR / "open" / "inbox.md"
    if inbox_path.exists():
        try:
            content = inbox_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("- [ ]"):
                    item = stripped[5:].strip()
                    if item:
                        items.append(item)
        except Exception:
            pass
    return items


def generate_inbox_section(items: list[str]) -> str:
    if not items:
        return "- _Inbox is empty._"
    return "\n".join(f"- **[Inbox]** {item}" for item in items)


def generate_now_section(tasks: list[TaskRecord], stale_ids: set[str]) -> str:
    if not tasks:
        return "- _No open tasks._"
    lines: list[str] = []
    for task in tasks:
        stale_flag = " ⚠️ Stale" if task.id in stale_ids else ""
        lines.append(f"- **[`{task.id}`]** {task.objective}{stale_flag}")
    return "\n".join(lines)


def generate_closed_section(tasks: list[TaskRecord]) -> str:
    if not tasks:
        return "- _No closed tasks._"
    lines: list[str] = []
    for task in tasks:
        try:
            content = task.path.read_text(encoding="utf-8")
        except Exception:
            content = ""
        done_when = ""
        if "## Evidence" in content:
            match = re.search(r"## Evidence\n(.*?)(?=\n\n|\Z)", content, re.DOTALL)
            if match:
                done_when = match.group(1).strip().split("\n")[0][:120]
        if not done_when:
            done_when = task.objective
        lines.append(f"- **[`{task.id}`]** {done_when}")
    return "\n".join(lines)


def extract_relationship_roots(workboard_content: str) -> list[str]:
    start_idx = workboard_content.find(REL_ROOTS_START)
    end_idx = workboard_content.find(REL_ROOTS_END)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        return []
    block = workboard_content[start_idx + len(REL_ROOTS_START) : end_idx]
    roots: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--"):
            continue
        roots.extend(_extract_refs(stripped))
    return roots


def _format_task_label(task: TaskRecord) -> str:
    label = f"`{task.id}`: {task.objective}".strip()
    return label


def _format_edge_note(name: str, refs: list[str]) -> str:
    if not refs:
        return ""
    rendered = ", ".join(f"`{ref}`" for ref in refs)
    return f"{name} {rendered}"


def build_relationship_tree(roots: list[str], open_tasks: list[TaskRecord], closed_tasks: list[TaskRecord]) -> str:
    open_map = {task.id: task for task in open_tasks}
    known_map = {task.id: task for task in [*open_tasks, *closed_tasks]}
    children_by_parent: dict[str, list[str]] = {}
    for task in open_tasks:
        if task.parent:
            children_by_parent.setdefault(task.parent, []).append(task.id)
    for child_ids in children_by_parent.values():
        child_ids.sort(key=_sort_key)

    lines: list[str] = []
    seen: set[str] = set()

    def render_node(task_id: str, depth: int) -> None:
        task = open_map.get(task_id)
        indent = "  " * depth
        if task is None:
            known = known_map.get(task_id)
            status = "closed reference" if known else "missing task"
            lines.append(f"{indent}- `{task_id}` ({status})")
            return
        if task_id in seen:
            lines.append(f"{indent}- `@{task_id}`")
            return

        seen.add(task_id)
        blocked_by_set = set(task.blocked_by)
        resolved_dependencies = [
            ref for ref in task.depends_on if ref not in blocked_by_set
        ]
        annotations = [
            _format_edge_note("depends on", resolved_dependencies),
            _format_edge_note("blocked by", task.blocked_by),
            _format_edge_note("blocks", task.blocks),
            _format_edge_note("related", task.related),
        ]
        note_parts = [part for part in annotations if part]
        note = f" ({'; '.join(note_parts)})" if note_parts else ""
        lines.append(f"{indent}- {_format_task_label(task)}{note}")
        for child_id in children_by_parent.get(task_id, []):
            render_node(child_id, depth + 1)

    if not roots:
        return "- _No relationship roots configured._"

    for root_id in roots:
        if root_id not in open_map:
            known = known_map.get(root_id)
            status = "closed task" if known else "missing task"
            lines.append(f"- Warning: root `{root_id}` not rendered ({status}).")
            continue
        render_node(root_id, 0)

    return "\n".join(lines) if lines else "- _No relationship tree entries._"


def replace_marker_block(content: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        return content
    return (
        content[: start_idx + len(start_marker)]
        + "\n"
        + replacement
        + "\n"
        + content[end_idx:]
    )


def refresh_last_sync(content: str, sync_date: str) -> str:
    return re.sub(
        r"(^> \*\*Last Sync:\*\* ).*$",
        rf"\g<1>{sync_date}",
        content,
        count=1,
        flags=re.MULTILINE,
    )


def sync() -> None:
    if not WORKBOARD_PATH.exists():
        print(f"Error: {WORKBOARD_PATH} not found.")
        return

    content = WORKBOARD_PATH.read_text(encoding="utf-8")
    sync_date = datetime.now().date().isoformat()
    open_tasks = get_open_tasks()
    closed_tasks = get_closed_tasks(10)
    inbox_items = get_inbox_items()
    stale_ids = check_stale_tasks(get_open_task_ids())
    roots = extract_relationship_roots(content)

    relationship_tree = build_relationship_tree(roots, open_tasks, get_tasks(TASKS_DIR / "closed"))
    now_section = generate_now_section(open_tasks, stale_ids)
    inbox_section = generate_inbox_section(inbox_items)
    closed_section = generate_closed_section(closed_tasks)

    updated = replace_marker_block(content, REL_TREE_START, REL_TREE_END, relationship_tree)
    updated = replace_marker_block(updated, NOW_START, NOW_END, now_section)
    updated = replace_marker_block(updated, INBOX_START, INBOX_END, inbox_section)
    updated = replace_marker_block(updated, CLOSED_START, CLOSED_END, closed_section)
    updated = refresh_last_sync(updated, sync_date)

    WORKBOARD_PATH.write_text(updated, encoding="utf-8")
    print(
        f"Synced {len(open_tasks)} open, {len(inbox_items)} inbox, "
        f"{len(closed_tasks)} closed tasks, and {len(roots)} relationship roots."
    )
    if stale_ids:
        print(f"Stale tasks (>30 days no change): {', '.join(sorted(stale_ids, key=_sort_key))}")


if __name__ == "__main__":
    sync()
