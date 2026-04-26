"""
memory_tools.py — Read and write local memory stores.

Supports: notes, tasks, context bundles, episode logs.
All writes are local and file-based. No cloud sync.
"""

import json
import datetime
from pathlib import Path
from tools.file_tools import REPO_ROOT, read_file, write_file, list_files, search_files

NOTES_DIR = "memory/notes"
TASKS_DIR = "memory/tasks"
CONTEXT_DIR = "memory/context"
EPISODES_DIR = "memory/episodes"


# ── Notes ──────────────────────────────────────────────────────────────────

def write_note(title: str, body: str, tags: list[str] | None = None) -> str:
    """
    Write a Markdown note to /memory/notes/<slug>.md.
    Returns the file path.
    """
    slug = title.lower().replace(" ", "-").replace("/", "-")[:80]
    tags_str = ", ".join(tags or [])
    created = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    content = f"""---
title: {title}
tags: [{tags_str}]
created: {created}
---

{body}
"""
    path = f"{NOTES_DIR}/{slug}.md"
    write_file(path, content)
    return path


def read_note(slug_or_path: str) -> str:
    """Read a note by slug or full relative path."""
    if not slug_or_path.endswith(".md"):
        slug_or_path = f"{NOTES_DIR}/{slug_or_path}.md"
    return read_file(slug_or_path)


def search_notes(query: str) -> list[dict]:
    """Search notes by substring. Returns list of {path, line_number, line}."""
    return search_files(query, directory=NOTES_DIR, file_pattern="*.md")


def list_notes() -> list[str]:
    """List all note file paths."""
    return list_files(NOTES_DIR, pattern="*.md", recursive=False)


# ── Tasks ──────────────────────────────────────────────────────────────────

def write_task_list(name: str, tasks: list[str]) -> str:
    """
    Write a task list to /memory/tasks/<name>.md.
    Tasks are written as checkboxes.
    """
    lines = [f"# {name}\n"]
    for t in tasks:
        lines.append(f"- [ ] {t}")
    content = "\n".join(lines) + "\n"
    path = f"{TASKS_DIR}/{name.lower().replace(' ', '-')}.md"
    write_file(path, content)
    return path


def read_task_list(name: str) -> str:
    """Read a task list by name or path."""
    if not name.endswith(".md"):
        name = f"{TASKS_DIR}/{name.lower().replace(' ', '-')}.md"
    return read_file(name)


# ── Context bundles ────────────────────────────────────────────────────────

def write_context_bundle(
    task_slug: str,
    description: str,
    file_paths: list[str],
    notes: list[str] | None = None,
    constraints: str = "",
) -> str:
    """
    Write a context bundle to /memory/context/<task-slug>.md.
    """
    lines = [f"# Context: {task_slug}\n", f"{description}\n"]
    lines.append("## Relevant files\n")
    for fp in file_paths:
        lines.append(f"- `{fp}`")
    if notes:
        lines.append("\n## Related notes\n")
        for n in notes:
            lines.append(f"- {n}")
    if constraints:
        lines.append(f"\n## Constraints\n\n{constraints}")
    content = "\n".join(lines) + "\n"
    path = f"{CONTEXT_DIR}/{task_slug}.md"
    write_file(path, content)
    return path


# ── Episodes ───────────────────────────────────────────────────────────────

def log_episode(agent: str, action: str, result: str, metadata: dict | None = None) -> str:
    """
    Append a JSONL episode entry to /memory/episodes/episodes.jsonl.
    """
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "agent": agent,
        "action": action,
        "result": result,
        "metadata": metadata or {},
    }
    path = f"{EPISODES_DIR}/episodes.jsonl"
    full_path = REPO_ROOT / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with full_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return path


def read_episodes(n: int = 50) -> list[dict]:
    """Read the last n episode entries."""
    path = REPO_ROOT / EPISODES_DIR / "episodes.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(l) for l in lines[-n:]]
