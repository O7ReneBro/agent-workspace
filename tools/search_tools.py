"""
search_tools.py — Text and symbol search across the workspace.

Provides grep-style search and simple symbol (def/class) lookup.

Security:
- re.compile wrapped in try/except to surface bad regex safely.
- Language parameter validated against explicit allowlist.
- find_todos tag whitelist enforced.
"""

import re
from tools.file_tools import REPO_ROOT, _safe_path

# Supported languages for find_symbol.
_SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"python", "javascript", "typescript"})

# Allowed TODO-style tags (prevent arbitrary regex injection via tag list).
_ALLOWED_TODO_TAGS: frozenset[str] = frozenset({
    "TODO", "FIXME", "HACK", "NOTE", "XXX", "BUG", "OPTIMIZE", "REVIEW",
})


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
    Returns an error dict if the pattern is invalid regex.
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        compiled = re.compile(pattern, flags)
    except re.error as e:
        return [{"error": f"Invalid regex pattern: {e}", "path": "", "line_number": 0, "line": ""}]

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
    Supported languages: python, javascript, typescript.
    Returns an error dict for unsupported languages.
    """
    lang = language.lower()
    if lang not in _SUPPORTED_LANGUAGES:
        return [{
            "error": (
                f"Unsupported language: {language!r}. "
                f"Supported: {sorted(_SUPPORTED_LANGUAGES)}"
            ),
            "path": "", "line_number": 0, "line": "",
        }]

    patterns = {
        "python": rf"^\s*(def|class)\s+{re.escape(symbol)}\b",
        "javascript": (
            rf"(function\s+{re.escape(symbol)}"
            rf"|const\s+{re.escape(symbol)}\s*="
            rf"|class\s+{re.escape(symbol)})"
        ),
        "typescript": (
            rf"(function\s+{re.escape(symbol)}"
            rf"|const\s+{re.escape(symbol)}\s*="
            rf"|class\s+{re.escape(symbol)})"
        ),
    }
    file_globs = {
        "python": "*.py",
        "javascript": "*.js",
        "typescript": "*.ts",
    }
    return grep(
        patterns[lang],
        directory=directory,
        file_glob=file_globs[lang],
        case_sensitive=True,
    )


def find_todos(
    directory: str = ".",
    tags: list[str] | None = None,
    max_results: int = 100,
) -> list[dict]:
    """
    Find TODO/FIXME/HACK/NOTE comments in the codebase.
    Tags are validated against an allowlist to prevent regex injection.
    """
    requested = set(tags or _ALLOWED_TODO_TAGS)
    safe_tags = [t for t in requested if t.upper() in _ALLOWED_TODO_TAGS]
    if not safe_tags:
        return [{
            "error": (
                f"No valid tags provided. "
                f"Allowed: {sorted(_ALLOWED_TODO_TAGS)}"
            ),
            "path": "", "line_number": 0, "line": "",
        }]
    pattern = "|".join(re.escape(t) for t in safe_tags)
    return grep(pattern, directory=directory, case_sensitive=False, max_results=max_results)
