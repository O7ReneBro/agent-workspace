"""
shell_tools.py — Run safe shell commands in the workspace.

Security model:
- ALLOWED_COMMANDS: exact base-command allowlist (no prefix matching).
- DESTRUCTIVE_COMMANDS: require confirm=True.
- Shell metacharacters are blocked to prevent injection.
- Command length and argument count are bounded.
- subprocess is called with a list (no shell=True) to prevent shell expansion.
"""

import re
import subprocess
import shlex
from pathlib import Path
from tools.file_tools import REPO_ROOT

# Maximum safe limits
_MAX_CMD_LEN = 512
_MAX_ARGS = 32

# Shell metacharacters that enable injection.
# These are never valid in our controlled tool interface.
_SHELL_INJECT_RE = re.compile(r'[;|&`$(){}!\n\r]')

# Exact base commands allowed without confirmation.
# Key = first token of the command (lowercased).
ALLOWED_COMMANDS: frozenset[str] = frozenset({
    "python", "python3",
    "pytest",
    "ruff",
    "black",
    "isort",
    "mypy",
    "ls", "cat", "echo", "find", "head", "tail", "wc",
})

# Git sub-commands allowed without confirmation.
ALLOWED_GIT_SUBCOMMANDS: frozenset[str] = frozenset({
    "status", "diff", "log", "show", "branch", "remote",
})

# Exact base commands that require confirm=True.
DESTRUCTIVE_COMMANDS: frozenset[str] = frozenset({
    "rm", "rmdir",
})

# Git sub-commands that require confirm=True.
DESTRUCTIVE_GIT_SUBCOMMANDS: frozenset[str] = frozenset({
    "push", "commit", "reset", "rebase", "merge",
    "checkout", "switch", "add",
})

# npm/npx sub-commands allowed without confirmation.
ALLOWED_NPM_SUBCOMMANDS: frozenset[str] = frozenset({
    "test", "run",
})
ALLOWED_NPX_SUBCOMMANDS: frozenset[str] = frozenset({
    "eslint", "prettier", "jest", "vitest", "mocha",
})


def _validate_command(command: str, confirm: bool) -> str | None:
    """
    Validate a command string.
    Returns an error message string if blocked, or None if allowed.
    """
    if len(command) > _MAX_CMD_LEN:
        return f"Blocked: command exceeds maximum length ({_MAX_CMD_LEN} chars)."

    if _SHELL_INJECT_RE.search(command):
        return f"Blocked: shell metacharacters detected in command: {command!r}"

    try:
        tokens = shlex.split(command)
    except ValueError as e:
        return f"Blocked: could not parse command: {e}"

    if not tokens:
        return "Blocked: empty command."

    if len(tokens) > _MAX_ARGS:
        return f"Blocked: too many arguments ({len(tokens)} > {_MAX_ARGS})."

    base = tokens[0].lower()

    # git sub-command routing
    if base == "git":
        if len(tokens) < 2:
            return "Blocked: bare 'git' with no subcommand."
        sub = tokens[1].lower()
        if sub in ALLOWED_GIT_SUBCOMMANDS:
            return None  # safe
        if sub in DESTRUCTIVE_GIT_SUBCOMMANDS:
            if not confirm:
                return f"Blocked: 'git {sub}' is destructive. Pass confirm=True."
            return None  # destructive but confirmed
        return f"Blocked: 'git {sub}' is not in the allowed git subcommand list."

    # npm sub-command routing
    if base == "npm":
        if len(tokens) < 2 or tokens[1].lower() not in ALLOWED_NPM_SUBCOMMANDS:
            sub = tokens[1].lower() if len(tokens) > 1 else "<none>"
            return f"Blocked: 'npm {sub}' is not allowed."
        return None

    # npx sub-command routing
    if base == "npx":
        if len(tokens) < 2 or tokens[1].lower() not in ALLOWED_NPX_SUBCOMMANDS:
            sub = tokens[1].lower() if len(tokens) > 1 else "<none>"
            return f"Blocked: 'npx {sub}' is not allowed."
        return None

    # Destructive base commands
    if base in DESTRUCTIVE_COMMANDS:
        if not confirm:
            return f"Blocked: '{base}' is destructive. Pass confirm=True."
        return None

    # Allowed base commands
    if base in ALLOWED_COMMANDS:
        return None

    # Not in any list
    if not confirm:
        return (
            f"Blocked: '{base}' is not in the allowed command list. "
            "Pass confirm=True to override (use with caution)."
        )
    return None


def run_command(
    command: str,
    cwd: str | None = None,
    timeout: int = 60,
    confirm: bool = False,
) -> dict:
    """
    Run a shell command safely.
    Returns {stdout, stderr, returncode}.
    """
    error = _validate_command(command, confirm)
    if error:
        return {"stdout": "", "stderr": error, "returncode": -1}

    work_dir = Path(cwd).resolve() if cwd else REPO_ROOT

    try:
        tokens = shlex.split(command)
        result = subprocess.run(
            tokens,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            # shell=False is the default and MUST remain so.
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Timeout after {timeout}s", "returncode": -1}
    except FileNotFoundError:
        tokens = shlex.split(command)
        return {"stdout": "", "stderr": f"Command not found: {tokens[0]!r}", "returncode": 127}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1}


def run_tests(
    framework: str = "auto",
    path: str = ".",
    extra_args: str = "",
) -> dict:
    """
    Run the test suite. Auto-detects pytest or jest.
    extra_args must not contain shell metacharacters.
    """
    if _SHELL_INJECT_RE.search(extra_args):
        return {
            "stdout": "",
            "stderr": "Blocked: shell metacharacters in extra_args.",
            "returncode": -1,
        }

    if framework == "auto":
        if (REPO_ROOT / "pytest.ini").exists() or (REPO_ROOT / "pyproject.toml").exists():
            framework = "pytest"
        elif (REPO_ROOT / "package.json").exists():
            framework = "jest"
        else:
            framework = "pytest"

    if framework not in ("pytest", "jest"):
        return {
            "stdout": "",
            "stderr": f"Unknown test framework: {framework!r}. Use 'pytest', 'jest', or 'auto'.",
            "returncode": -1,
        }

    # Build command from validated parts only
    safe_path = path.replace(";", "").replace("|", "").replace("&", "")
    safe_extra = extra_args.strip()

    if framework == "pytest":
        cmd = f"pytest {safe_path} {safe_extra} -v".strip()
    else:
        cmd = f"npx jest {safe_path} {safe_extra} --verbose".strip()

    return run_command(cmd)
