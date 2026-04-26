"""
shell_tools.py — Run safe shell commands in the workspace.

Only whitelisted commands are allowed.
Destructive commands require explicit confirmation.
"""

import subprocess
import shlex
from pathlib import Path
from tools.file_tools import REPO_ROOT

# Commands allowed without confirmation
SAFE_PREFIXES = (
    "python",
    "pytest",
    "ruff",
    "black",
    "isort",
    "mypy",
    "npm test",
    "npx eslint",
    "npx prettier",
    "git status",
    "git diff",
    "git log",
    "git show",
    "git branch",
    "ls",
    "cat",
    "echo",
    "find",
)

# Commands that require confirm=True
DESTRUCTIVE_PREFIXES = (
    "git push",
    "git commit",
    "rm ",
    "rmdir",
    "git reset",
    "git rebase",
    "git merge",
)


def run_command(
    command: str,
    cwd: str | None = None,
    timeout: int = 60,
    confirm: bool = False,
) -> dict:
    """
    Run a shell command.
    Returns {stdout, stderr, returncode}.
    """
    work_dir = Path(cwd) if cwd else REPO_ROOT

    # Safety checks
    cmd_lower = command.strip().lower()
    is_destructive = any(cmd_lower.startswith(p.lower()) for p in DESTRUCTIVE_PREFIXES)
    is_safe = any(cmd_lower.startswith(p.lower()) for p in SAFE_PREFIXES)

    if is_destructive and not confirm:
        return {
            "stdout": "",
            "stderr": f"Blocked: '{command}' is destructive. Pass confirm=True.",
            "returncode": -1,
        }

    if not is_safe and not is_destructive and not confirm:
        return {
            "stdout": "",
            "stderr": f"Blocked: '{command}' is not in the safe-command list. Pass confirm=True to override.",
            "returncode": -1,
        }

    try:
        result = subprocess.run(
            shlex.split(command),
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Timeout after {timeout}s", "returncode": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1}


def run_tests(framework: str = "auto", path: str = ".", extra_args: str = "") -> dict:
    """
    Run the test suite.
    Auto-detects pytest or jest.
    """
    if framework == "auto":
        if (REPO_ROOT / "pytest.ini").exists() or (REPO_ROOT / "pyproject.toml").exists():
            framework = "pytest"
        elif (REPO_ROOT / "package.json").exists():
            framework = "jest"
        else:
            framework = "pytest"  # fallback

    commands = {
        "pytest": f"pytest {path} {extra_args} -v",
        "jest": f"npx jest {path} {extra_args} --verbose",
    }
    cmd = commands.get(framework, f"pytest {path} {extra_args} -v")
    return run_command(cmd)
