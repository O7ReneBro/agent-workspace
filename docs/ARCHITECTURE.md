# Architecture Overview

## Purpose

This repository is a modular AI agent workspace for local assistants
(Claude Code, OpenCode, and compatible coding assistants).
It combines skills, tools, agents, memory, and scripts into a layered system
driven from any compatible coding assistant.

---

## Layer map

```
┌────────────────────────────────────────────┐
│           USER                             │
│   chat / CLI / IDE / coding assistant      │
└─────────────────┬──────────────────────────┘
                  │ instruction
┌─────────────────▼──────────────────────────┐
│             AI AGENT                       │
│  /agents/primary-assistant  (core loop)    │
│  /agents/architecture-advisor (design)     │
│                                            │
│  reasoning: ReAct / planner-worker         │
└───────┬────────────────────────┬───────────┘
        │ activates              │ reads/writes
┌───────▼──────────┐  ┌──────────▼───────────┐
│    SKILLS        │  │       MEMORY          │
│  /skills/...     │  │  /memory/notes        │
│  SKILL.md each   │  │  /memory/tasks        │
│                  │  │  /memory/context      │
│  modular         │  │  /memory/episodes     │
│  workflows       │  │  /memory/.chroma      │
└───────┬──────────┘  └───────────────────────┘
        │ calls
┌───────▼────────────────────────────────────┐
│              TOOLS                         │
│  /tools/ (Python modules)                  │
│  file I/O, search, git, shell, memory      │
└───────┬────────────────────────────────────┘
        │ uses
┌───────▼────────────────────────────────────┐
│           APIs / SYSTEM                    │
│  local filesystem, shell, external APIs    │
│  (only when explicitly configured)         │
└────────────────────────────────────────────┘
```

---

## Components

### Agents

| Agent | Path | Role |
|---|---|---|
| primary-assistant | /agents/primary-assistant/ | Main coding + research assistant |
| architecture-advisor | /agents/architecture-advisor/ | Architecture, design, pattern selection |

### Skills

| Skill | Path | Purpose |
|---|---|---|
| agent-foundations-and-design | /skills/agent-foundations/ | AI agent concepts, design advice |
| pattern-picker | /skills/pattern-picker/ | Selects reasoning/control patterns |
| framework-comparator | /skills/framework-comparator/ | Compares orchestration stacks |
| repo-help | /skills/repo-help/ | Repo orientation |
| repo-navigation-and-search | /skills/repo-navigation-and-search/ | Find files and symbols |
| run-tests | /skills/run-tests/ | Run test suite, interpret results |
| run-lint-and-format | /skills/run-lint-and-format/ | Lint and format the codebase |
| code-generation-and-refactoring | /skills/code-generation-and-refactoring/ | Implement features, refactors |
| file-summarization | /skills/file-summarization/ | Summarize files and modules |
| task-planning-and-tracking | /skills/task-planning-and-tracking/ | Break goals into tasks |
| memory-notes | /skills/memory-notes/ | Write/read local knowledge base |
| context-builder | /skills/context-builder/ | Build context bundles for tasks |
| git-workflow-helper | /skills/git-workflow-helper/ | Git status, diffs, commit messages |

### Tools

| Module | Path | Purpose |
|---|---|---|
| file_tools | /tools/file_tools.py | read/write/search/list files |
| search_tools | /tools/search_tools.py | grep, symbol search, TODO finder |
| shell_tools | /tools/shell_tools.py | safe shell command runner |
| git_tools | /tools/git_tools.py | git status/diff/log/commit/push |
| memory_tools | /tools/memory_tools.py | notes/tasks/context/episodes |

### Memory stores

| Store | Path | Type |
|---|---|---|
| Notes | /memory/notes/ | Markdown knowledge files |
| Tasks | /memory/tasks/ | Markdown task checklists |
| Context | /memory/context/ | Context bundles per task |
| Episodes | /memory/episodes/ | JSONL logs of past runs |
| Vector index | /memory/.chroma/ | Chroma local vector DB |

---

## Reasoning patterns

- Primary assistant: ReAct — alternates thoughts and tool calls.
- Architecture advisor: Planner-style — reads, selects skills, synthesizes.
- Coding tasks: ReAct + Reflexion — implements, runs tests, reflects on failures.

---

## Safety rules

- No destructive commands without explicit confirmation.
- No external API calls unless configured in /config/settings.yaml.
- Human approval required before git push, PR creation, or deployment.
- All memory writes are local and file-based; no cloud sync by default.

---

## Setup

```bash
# Clone
git clone https://github.com/O7ReneBro/agent-workspace.git
cd agent-workspace

# Install Python dependencies (optional, for tools and scripts)
pip install anthropic chromadb sentence-transformers

# Run a skill
python scripts/run_skill.py --list
python scripts/run_skill.py memory-notes

# Run an agent (requires ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=your_key
python scripts/run_agent.py --agent primary-assistant

# Index memory notes into Chroma vector DB
python scripts/index_memory.py

# Semantic search over notes
python scripts/index_memory.py --query "agent memory design"
```

---

## Roadmap

- [x] AGENTS.md + 2 AGENT.md personas
- [x] 13 SKILL.md definitions
- [x] 5 Python tool modules
- [x] run_agent.py CLI
- [x] run_skill.py CLI
- [x] index_memory.py with Chroma vector index
- [ ] Unit tests for tool modules
- [ ] Eval benchmarks for skills
- [ ] MCP server wrapper for tool modules
- [ ] LangGraph / multi-agent orchestration example
