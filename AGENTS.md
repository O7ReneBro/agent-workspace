---
name: agent-workspace
description: Root repo instructions for all AI coding assistants. Every agent must read this file first.
metadata:
  version: "1.0"
---

# Agent Workspace

You are operating in a modular AI agent workspace.

## Operating rules

1. Work ONLY inside this repo directory.
2. Prefer local, file-based solutions.
3. Before any major change, write a short plan and wait for user confirmation.
4. After every change, update README.md and docs/ accordingly.
5. Keep all modules small, focused, and documented.

## Key directories

- /skills   — SKILL.md definitions (modular agent capabilities)
- /agents   — AGENT.md and agent configs
- /memory   — Local memory modules (notes, tasks, context, episodes)
- /tools    — Callable Python tools
- /scripts  — CLI entrypoints
- /config   — Global settings
- /docs     — Architecture, guides, HOWTOs

## Where to start

- Architecture/design questions → agents/architecture-advisor/AGENT.md
- Coding tasks → skills/code-generation-and-refactoring/SKILL.md
- Repo navigation → skills/repo-navigation-and-search/SKILL.md
- Memory notes → skills/memory-notes/SKILL.md

See docs/ARCHITECTURE.md for the full system overview.
