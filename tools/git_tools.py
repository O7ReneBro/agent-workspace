"""
git_tools.py — Git operations for the workspace.

Destructive operations (commit, push) require confirm=True.
"""

from tools.shell_tools import run_command


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
    flags = "--oneline" if oneline else ""
    result = run_command(f"git log -n {n} {flags}")
    return result["stdout"] or result["stderr"]


def git_add(path: str = ".") -> dict:
    """Stage files for commit."""
    return run_command(f"git add {path}", confirm=True)


def git_commit(message: str, confirm: bool = False) -> dict:
    """
    Commit staged changes.
    Requires confirm=True as a safety gate.
    """
    if not confirm:
        return {"stdout": "", "stderr": "Blocked: pass confirm=True to commit.", "returncode": -1}
    return run_command(f'git commit -m "{message}"', confirm=True)


def git_push(remote: str = "origin", branch: str = "main", confirm: bool = False) -> dict:
    """
    Push to remote.
    Requires confirm=True as a safety gate.
    """
    if not confirm:
        return {"stdout": "", "stderr": "Blocked: pass confirm=True to push.", "returncode": -1}
    return run_command(f"git push {remote} {branch}", confirm=True)


def git_branches() -> str:
    """List all branches."""
    result = run_command("git branch -a")
    return result["stdout"] or result["stderr"]


def git_create_branch(name: str, confirm: bool = False) -> dict:
    """Create and switch to a new branch. Requires confirm=True."""
    if not confirm:
        return {"stdout": "", "stderr": "Blocked: pass confirm=True to create branch.", "returncode": -1}
    return run_command(f"git checkout -b {name}", confirm=True)
