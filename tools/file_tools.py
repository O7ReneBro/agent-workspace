"""
file_tools.py — Read, write, list, and search files in the workspace.

All paths are relative to the repo root.
Never write outside the repo root.
"""

import os
import fnmatch
from pathlib import Path
from typing import Union

REPO_ROOT = Path(os.environ.get("AGENT_WORKSPACE_ROOT", Path(__file__).parent.parent))


def _safe_path(path: str) -> Path:
    """Resolve path and ensure it stays inside REPO_ROOT."""
    resolved = (REPO_ROOT / path).resolve()
    if not str(resolved).startswith(str(REPO_ROOT.resolve())):
        raise PermissionError(f"Path escape attempt blocked: {path}")
    return resolved


def read_file(path: str) -> str:
    """Read and return the full text content of a file."""
    return _safe_path(path).read_text(encoding="utf-8")


def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories as needed."""
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"Written: {path}"


def append_file(path: str, content: str) -> str:
    """Append content to a file."""
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(content)
    return f"Appended to: {path}"


def list_files(
    directory: str = ".",
    pattern: str = "*",
    recursive: bool = True,
    max_results: int = 200,
) -> list[str]:
    """
    List files in a directory, optionally filtered by glob pattern.
    Returns paths relative to REPO_ROOT.
    """
    base = _safe_path(directory)
    results = []
    glob_fn = base.rglob if recursive else base.glob
    for p in glob_fn(pattern):
        if p.is_file():
            results.append(str(p.relative_to(REPO_ROOT)))
        if len(results) >= max_results:
            break
    return sorted(results)


def search_files(
    query: str,
    directory: str = ".",
    file_pattern: str = "*",
    max_results: int = 50,
) -> list[dict]:
    """
    Search for a substring in files matching file_pattern under directory.
    Returns list of {path, line_number, line} dicts.
    """
    base = _safe_path(directory)
    results = []
    for p in base.rglob(file_pattern):
        if not p.is_file():
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, start=1):
            if query.lower() in line.lower():
                results.append(
                    {
                        "path": str(p.relative_to(REPO_ROOT)),
                        "line_number": i,
                        "line": line.strip(),
                    }
                )
                if len(results) >= max_results:
                    return results
    return results


def file_exists(path: str) -> bool:
    """Check if a file exists."""
    try:
        return _safe_path(path).is_file()
    except PermissionError:
        return False


def delete_file(path: str, confirm: bool = False) -> str:
    """Delete a file. Requires confirm=True as a safety gate."""
    if not confirm:
        return "Aborted: pass confirm=True to delete."
    p = _safe_path(path)
    p.unlink()
    return f"Deleted: {path}"
