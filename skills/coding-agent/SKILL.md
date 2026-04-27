---
name: coding-agent
description: Delegate coding tasks to Codex, Claude Code, or Pi agents via background process. Use when: (1) building/creating new features or apps, (2) reviewing PRs (spawn in temp dir), (3) refactoring large codebases, (4) iterative coding that needs file exploration. NOT for: simple one-liner fixes (just edit), reading code (use read tool), thread-bound ACP harness requests in chat, or any work in ~/clawd workspace.
source: openclaw/openclaw
version: 20260304
---

# Coding Agent (bash-first)

Use **bash** (with optional background mode) for all coding agent work.

## ⚠️ PTY Mode: Codex/Pi/OpenCode yes, Claude Code no

For **Codex, Pi, and OpenCode**, PTY is required:
```bash
# ✅ Codex/Pi/OpenCode
bash pty:true command:"codex exec 'Your prompt'"

# ✅ Claude Code (no PTY)
cd /path/to/project && claude --permission-mode bypassPermissions --print 'Your task'
```

### Bash Tool Parameters

| Parameter   | Type    | Description                                              |
|-------------|---------|----------------------------------------------------------|
| `command`   | string  | Shell command to run                                     |
| `pty`       | boolean | Allocates pseudo-terminal (required for Codex/Pi)        |
| `workdir`   | string  | Working directory (agent sees only this folder)          |
| `background`| boolean | Run in background, returns sessionId                     |
| `timeout`   | number  | Timeout in seconds                                       |
| `elevated`  | boolean | Run on host instead of sandbox                          |

### Process Tool Actions

| Action       | Description                              |
|--------------|------------------------------------------|
| `list`       | List all running/recent sessions         |
| `poll`       | Check if session is still running        |
| `log`        | Get session output                       |
| `write`      | Send raw data to stdin                   |
| `submit`     | Send data + newline (Enter)              |
| `send-keys`  | Send key tokens or hex bytes             |
| `paste`      | Paste text                               |
| `kill`       | Terminate the session                    |

## Quick Start: One-Shot Tasks

```bash
# Quick chat (Codex needs a git repo)
SCRATCH=$(mktemp -d) && cd $SCRATCH && git init && codex exec "Your prompt"

# In a real project
bash pty:true workdir:~/Projects/myproject command:"codex exec 'Add error handling'"
```

## The Pattern: workdir + background + pty

```bash
# 1. Start agent in background
bash pty:true workdir:~/project background:true command:"codex exec --full-auto 'Build feature X'"
# Returns sessionId

# 2. Monitor
process action:log sessionId:XXX
process action:poll sessionId:XXX

# 3. Send input if needed
process action:submit sessionId:XXX data:"yes"

# 4. Kill if needed
process action:kill sessionId:XXX
```

## Codex CLI Flags

| Flag           | Effect                                         |
|----------------|------------------------------------------------|
| `exec`         | One-shot execution, exits when done            |
| `--full-auto`  | Auto-approves in workspace                     |
| `--yolo`       | No sandbox, no approvals (fastest, dangerous)  |

## Claude Code

```bash
# Foreground
bash workdir:~/project command:"claude --permission-mode bypassPermissions --print 'Your task'"

# Background
bash workdir:~/project background:true command:"claude --permission-mode bypassPermissions --print 'Your task'"
```

## OpenCode

```bash
bash pty:true workdir:~/project command:"opencode run 'Your task'"
```

## Pi Coding Agent

```bash
# Install
npm install -g @mariozechner/pi-coding-agent

bash pty:true workdir:~/project command:"pi 'Your task'"
bash pty:true command:"pi -p 'Summarize src/'"
bash pty:true command:"pi --provider openai --model gpt-4o-mini -p 'Your task'"
```

## Parallel Issue Fixing (git worktrees)

```bash
# 1. Create worktrees
git worktree add -b fix/issue-78 /tmp/issue-78 main
git worktree add -b fix/issue-99 /tmp/issue-99 main

# 2. Launch agents in parallel
bash pty:true workdir:/tmp/issue-78 background:true command:"codex --yolo 'Fix issue #78. Commit after.'"
bash pty:true workdir:/tmp/issue-99 background:true command:"codex --yolo 'Fix issue #99. Commit after.'"

# 3. Monitor
process action:list

# 4. Create PRs
cd /tmp/issue-78 && git push -u origin fix/issue-78
gh pr create --head fix/issue-78 --title "fix: issue 78"

# 5. Cleanup
git worktree remove /tmp/issue-78
```

## PR Review Pattern

```bash
# Clone to temp — NEVER review in live project folder
REVIEW_DIR=$(mktemp -d)
git clone https://github.com/user/repo.git $REVIEW_DIR
cd $REVIEW_DIR && gh pr checkout 130
bash pty:true workdir:$REVIEW_DIR command:"codex review --base origin/main"
```

## Auto-Notify on Completion

Append a wake trigger so you get pinged immediately when a long job finishes:

```bash
bash pty:true workdir:~/project background:true command:"codex --yolo exec 'Build REST API for todos.

When finished: openclaw system event --text \"Done: Built todos API\" --mode now'"
```

## ⚠️ Rules

1. **PTY per agent**: Codex/Pi/OpenCode = `pty:true` | Claude Code = `--print --permission-mode bypassPermissions`
2. **Respect tool choice** — if user asks Codex, use Codex. Don’t hand-code patches in orchestrator mode.
3. **Be patient** — don’t kill sessions for being slow
4. **Monitor with `process:log`** — check progress without interfering
5. **`--full-auto` for building**, vanilla for reviewing
6. **Parallel is OK** — many Codex processes at once for batch work
7. **NEVER start Codex in `~/.openclaw/`**
8. **NEVER checkout branches in live project folders**

---

## 🚦 Trading System Integration

> Project-specific patterns for `agent-workspace/agents/trading-system/`

### Backtester — delegate to Codex

```bash
bash pty:true workdir:~/agent-workspace background:true \
  command:"codex exec --full-auto 'Implement a vectorized backtester in agents/trading-system/backtest.py.
  Use pandas OHLCV data from ccxt, replay BOS+EMA+RSI signals, compute: win rate, Sharpe, max DD, expectancy.
  Write results to logs/backtest_results.json.
  When done: openclaw system event --text \"Done: backtester built\" --mode now'"
```

### New indicator / strategy module

```bash
bash pty:true workdir:~/agent-workspace background:true \
  command:"codex exec --full-auto 'Add VWAP + volume cluster indicator to agents/trading-system/market_scanner.py.
  Follow existing compute_rsi / compute_atr pattern. Add unit tests in tests/test_scanner.py.'"
```

### PR review for trading-system changes

```bash
REVIEW_DIR=$(mktemp -d)
git clone https://github.com/O7ReneBro/agent-workspace.git $REVIEW_DIR
cd $REVIEW_DIR && gh pr checkout <PR_NUMBER>
bash pty:true workdir:$REVIEW_DIR \
  command:"codex review --base origin/main"
```

### Parallel issue fixing (multi-module)

```bash
git worktree add -b fix/scanner-vwap /tmp/scanner-fix main
git worktree add -b fix/risk-dd-guard /tmp/risk-fix main

bash pty:true workdir:/tmp/scanner-fix background:true \
  command:"codex --yolo 'Add VWAP to market_scanner.py. Tests + commit.'"
bash pty:true workdir:/tmp/risk-fix background:true \
  command:"codex --yolo 'Improve daily drawdown guard in live_trade.py. Tests + commit.'"

process action:list
```
