"""
memory_tools.py — Read and write local memory stores.

Supports: notes, tasks, context bundles, episode logs.
All writes are local and file-based. No cloud sync.

Security:
- Slug generation strips all non-alphanumeric characters except dash.
- Tags are validated to prevent YAML injection.
- Episode fields are capped to prevent log bloat.
- All file writes route through file_tools._safe_path.
"""

import json
import re
import datetime
from pathlib import Path
from tools.file_tools import REPO_ROOT, read_file, write_file, list_files, search_files

NOTES_DIR = "memory/notes"
TASKS_DIR = "memory/tasks"
CONTEXT_DIR = "memory/context"
EPISODES_DIR = "memory/episodes"

# Slug: only lowercase alphanumeric and dashes, max 80 chars.
_SLUG_CLEAN_RE = re.compile(r'[^a-z0-9-]+')

# Tag: only alphanumeric, dash, underscore, colon.
_TAG_RE = re.compile(r'^[a-zA-Z0-9_:-]{1,64}$')

# Max field lengths for episode entries (prevent log bloat / injection).
_MAX_AGENT_LEN = 64
_MAX_ACTION_LEN = 256
_MAX_RESULT_LEN = 2048


def _make_slug(title: str) -> str:
    """
    Convert a title to a safe filename slug.
    Replaces spaces with dashes, strips all non-alphanumeric chars, collapses dashes.
    """
    slug = title.lower().replace(" ", "-")
    slug = _SLUG_CLEAN_RE.sub("-", slug)
    slug = re.sub(r'-{2,}', '-', slug).strip("-")
    return slug[:80] or "note"


def _validate_tags(tags: list[str]) -> list[str]:
    """
    Validate and sanitize tags. Rejects tags containing YAML-unsafe characters.
    Returns only valid tags.
    """
    valid = []
    for tag in tags:
        if _TAG_RE.match(tag):
            valid.append(tag)
    return valid


# ── Notes ──────────────────────────────────────────────────────────────────

def write_note(title: str, body: str, tags: list[str] | None = None) -> str:
    """
    Write a Markdown note to /memory/notes/<slug>.md.
    Returns the file path.
    """
    slug = _make_slug(title)
    safe_tags = _validate_tags(tags or [])
    tags_str = ", ".join(safe_tags)
    # Escape title for YAML: wrap in quotes, escape inner quotes.
    safe_title = title.replace('"', "'")
    created = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    content = f'---\ntitle: "{safe_title}"\ntags: [{tags_str}]\ncreated: {created}\n---\n\n{body}\n'
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
    slug = _make_slug(name)
    lines = [f"# {name}\n"]
    for t in tasks:
        # Strip leading/trailing whitespace; block newlines in task text.
        safe_t = t.strip().replace("\n", " ").replace("\r", " ")
        lines.append(f"- [ ] {safe_t}")
    content = "\n".join(lines) + "\n"
    path = f"{TASKS_DIR}/{slug}.md"
    write_file(path, content)
    return path


def read_task_list(name: str) -> str:
    """Read a task list by name or path."""
    if not name.endswith(".md"):
        name = f"{TASKS_DIR}/{_make_slug(name)}.md"
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
    safe_slug = _make_slug(task_slug)
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
    path = f"{CONTEXT_DIR}/{safe_slug}.md"
    write_file(path, content)
    return path


# ── Episodes ───────────────────────────────────────────────────────────────

def log_episode(agent: str, action: str, result: str, metadata: dict | None = None) -> str:
    """
    Append a JSONL episode entry to /memory/episodes/episodes.jsonl.
    Fields are capped to prevent log bloat.
    """
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "agent": str(agent)[:_MAX_AGENT_LEN],
        "action": str(action)[:_MAX_ACTION_LEN],
        "result": str(result)[:_MAX_RESULT_LEN],
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
    if not isinstance(n, int) or n < 1 or n > 10000:
        return []
    path = REPO_ROOT / EPISODES_DIR / "episodes.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines[-n:]]
