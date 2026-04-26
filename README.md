# agent-workspace

Modular AI agent workspace for Claude Code, OpenCode, and other coding assistants.

## What this is

A ready-to-clone repository with:
- 13 modular SKILL.md definitions
- 2 AGENT.md personas (primary-assistant + architecture-advisor)
- Local memory system (notes, tasks, context, episodes)
- Tool module stubs (Python)
- CLI script stubs
- Full architecture documentation

## Quick start

1. Clone the repo into your project or as a standalone workspace.
2. Open with Claude Code or another coding assistant that supports AGENTS.md / SKILL.md.
3. Ask: "Where do I start?" — the `repo-help` skill will orient you.
4. Ask: "Design the agent stack for my project." — routes to `architecture-advisor`.

## Directory structure

```
agent-workspace/
├── AGENTS.md          ← Root instructions for all coding assistants
├── README.md
├── config/
│   └── settings.yaml  ← Global config (model, memory paths, safety)
├── agents/            ← Agent personas
├── skills/            ← Modular SKILL.md definitions
├── memory/            ← Local memory stores
├── tools/             ← Python tool modules (implement these)
├── scripts/           ← CLI entrypoints (implement these)
└── docs/              ← Architecture and agent guides
```

## Skills included

| Skill | Purpose |
|---|---|
| agent-foundations-and-design | AI agent concepts and design advice |
| pattern-picker | Select reasoning patterns (ReAct, planner-worker, etc.) |
| framework-comparator | Compare orchestration stacks |
| repo-help | Repo orientation |
| repo-navigation-and-search | Find files and symbols |
| run-tests | Run test suite |
| run-lint-and-format | Lint and format |
| code-generation-and-refactoring | Implement features and refactors |
| file-summarization | Summarize files and modules |
| task-planning-and-tracking | Break goals into tasks |
| memory-notes | Read/write local knowledge base |
| context-builder | Build context bundles for tasks |
| git-workflow-helper | Git operations and commit messages |

## Safety defaults

- No destructive commands without confirmation.
- No external API calls unless configured in config/settings.yaml.
- Human approval required before git push or PR creation.

## Next steps

Implement the Python tool modules in /tools/ and the CLI scripts in /scripts/.
See docs/ARCHITECTURE.md for the full roadmap.
