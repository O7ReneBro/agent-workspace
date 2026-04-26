"""
git_tools.py — Git operations for the workspace.

Security:
- Destructive operations (commit, push, add, checkout) require confirm=True.
- Branch names are validated against an injection-safe pattern.
- All commands route through shell_tools.run_command (never shell=True).
"""

import re
from tools.shell_tools import run_command

# Valid branch/tag name: alphanumeric, dash, underscore, dot, slash only.
_BRANCH_RE = re.compile(r'^[a-zA-Z0-9_./-]{1,100}$')


def _validate_branch(name: str) -> str | None:
    """Return error string if branch name is invalid, else None."""
    if not _BRANCH_RE.match(name):
        return f"Invalid branch name: {name!r}. Use only [a-zA-Z0-9_./-]."
    return None


def git_status() -> str:
    """Return the current git status."""
    result = run_command("git status")
    return result["stdout"] or result["stderr"]


def git_diff(staged: bool = False, path: str = "") -> str:
    """Return git diff. Pass staged=True for --cached."""
    flags = "--cached" if staged else ""
    cmd = f"git diff {flags} {path}".strip()
    result = run_command(cmd)
    return result["stdout"] or result["stderr"]


def git_log(n: int = 10, oneline: bool = True) -> str:
    """Return recent git log."""
    if not isinstance(n, int) or n < 1 or n > 500:
        return "Error: n must be an integer between 1 and 500."
    flags = "--oneline" if oneline else ""
    result = run_command(f"git log -n {n} {flags}".strip())
    return result["stdout"] or result["stderr"]


def git_add(path: str = ".", confirm: bool = False) -> dict:
    """
    Stage files for commit.
    Requires confirm=True — staging is a precursor to a destructive commit.
    """
    if not confirm:
        return {"stdout": "", "stderr": "Blocked: pass confirm=True to stage files.", "returncode": -1}
    return run_command(f"git add {path}", confirm=True)


def git_commit(message: str, confirm: bool = False) -> dict:
    """
    Commit staged changes.
    Requires confirm=True.
    Message is quoted safely by shlex inside run_command.
    """
    if not confirm:
        return {"stdout": "", "stderr": "Blocked: pass confirm=True to commit.", "returncode": -1}
    if len(message) > 500:
        return {"stdout": "", "stderr": "Blocked: commit message too long (max 500 chars).", "returncode": -1}
    # Embed message safely — shlex.split will tokenize the quoted string correctly.
    return run_command(f'git commit -m "{message}"', confirm=True)


def git_push(remote: str = "origin", branch: str = "main", confirm: bool = False) -> dict:
    """
    Push to remote.
    Requires confirm=True.
    Remote and branch names are validated.
    """
    if not confirm:
        return {"stdout": "", "stderr": "Blocked: pass confirm=True to push.", "returncode": -1}
    err = _validate_branch(branch)
    if err:
        return {"stdout": "", "stderr": err, "returncode": -1}
    err = _validate_branch(remote)
    if err:
        return {"stdout": "", "stderr": f"Invalid remote name: {remote!r}", "returncode": -1}
    return run_command(f"git push {remote} {branch}", confirm=True)


def git_branches() -> str:
    """List all branches."""
    result = run_command("git branch -a")
    return result["stdout"] or result["stderr"]


def git_create_branch(name: str, confirm: bool = False) -> dict:
    """Create and switch to a new branch. Requires confirm=True."""
    if not confirm:
        return {"stdout": "", "stderr": "Blocked: pass confirm=True to create branch.", "returncode": -1}
    err = _validate_branch(name)
    if err:
        return {"stdout": "", "stderr": err, "returncode": -1}
    return run_command(f"git checkout -b {name}", confirm=True)
