"""
search_tools.py — Text and symbol search across the workspace.

Provides grep-style search and simple symbol (def/class) lookup.
"""

import re
from pathlib import Path
from tools.file_tools import REPO_ROOT, _safe_path


def grep(
    pattern: str,
    directory: str = ".",
    file_glob: str = "*",
    case_sensitive: bool = False,
    max_results: int = 100,
) -> list[dict]:
    """
    Regex grep across files.
    Returns list of {path, line_number, line} dicts.
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    compiled = re.compile(pattern, flags)
    base = _safe_path(directory)
    results = []
    for p in base.rglob(file_glob):
        if not p.is_file():
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, start=1):
            if compiled.search(line):
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


def find_symbol(
    symbol: str,
    directory: str = ".",
    language: str = "python",
) -> list[dict]:
    """
    Find function or class definitions for a symbol name.
    Supports: python, javascript/typescript.
    Returns list of {path, line_number, line} dicts.
    """
    patterns = {
        "python": rf"^\s*(def|class)\s+{re.escape(symbol)}\b",
        "javascript": rf"(function\s+{re.escape(symbol)}|const\s+{re.escape(symbol)}\s*=|class\s+{re.escape(symbol)})",
        "typescript": rf"(function\s+{re.escape(symbol)}|const\s+{re.escape(symbol)}\s*=|class\s+{re.escape(symbol)})",
    }
    file_globs = {
        "python": "*.py",
        "javascript": "*.{js,jsx,mjs}",
        "typescript": "*.{ts,tsx}",
    }
    lang = language.lower()
    pat = patterns.get(lang, patterns["python"])
    glob = file_globs.get(lang, "*.py")
    return grep(pat, directory=directory, file_glob=glob, case_sensitive=True)


def find_todos(
    directory: str = ".",
    tags: list[str] | None = None,
    max_results: int = 100,
) -> list[dict]:
    """
    Find TODO/FIXME/HACK/NOTE comments in the codebase.
    """
    if tags is None:
        tags = ["TODO", "FIXME", "HACK", "NOTE", "XXX"]
    pattern = "|".join(tags)
    return grep(pattern, directory=directory, case_sensitive=False, max_results=max_results)
