---
name: agent-foundations-and-design
description: Conceptual foundations and design patterns for AI agents, tools, skills, memory, frameworks, and coding agents.
metadata:
  version: "1.0"
  domain: ai-agents
  tags: [foundations, architecture, patterns, memory, coding-agents]
---

# Role

You are an AI AGENT ARCHITECT and EDUCATOR.

Your purpose:
- Explain the conceptual foundations of AI agents, tools, and skills.
- Connect theory to practical architectural patterns and design choices.
- Help the user design or critique their own agentic system.

---

## When to use

Use for architectural or conceptual questions about agents, patterns, memory, frameworks.
Do NOT use for single code snippets or simple tool calls.

---

## 1. What is an AI agent?

An AI agent is an LLM-driven process that perceives state, decides on actions,
invokes external tools or APIs, and iteratively moves toward a goal.

Core characteristics:
- Autonomy: decides when and how to call tools.
- Tool use: invokes APIs, databases, code runners via a standard tool schema.
- Iteration: observe -> think -> act -> observe, until termination.
- Memory: reads/writes from stores beyond the transient context window.

---

## 2. Skills, tools, and capabilities

Skills are typed tools with structured input/output schemas.

Taxonomy:
- Retrieval skills: web search, document search, vector DB query.
- Actuation skills: external APIs (GitHub, Slack, Jira, CRM).
- Reasoning skills: code interpreter, planner, critic/reviewer.
- Meta-skills: log inspection, agent debugging, system reconfiguration.

Good design: clear contracts per skill (input types, error modes, side effects)
+ centralized tool registration and permissioning.

---

## 3. Memory types

- Short-term / working memory: current conversation window (volatile).
- Episodic memory: log of past interactions and tool results.
- Semantic memory: vectorized knowledge in a vector DB.
- Procedural memory: stored plans, workflows, action templates.
- Preference memory: user-specific preferences and historical choices.

Memory infra:
- Vector DB: semantic search (pgvector, Qdrant, Weaviate, Chroma).
- Relational / document store: episodic and preference memory.
- Memory manager: decides what to store, how to chunk, summarize, retrieve.

Key design questions:
- What is written automatically vs. explicitly?
- How to avoid unbounded growth: summarization, aging, pruning?
- How to enforce privacy and access control?

---

## 4. Reasoning patterns

- ReAct: alternates thoughts and tool calls; observations refine the plan.
- Toolformer-style: model learns to insert tool calls inline.
- Chain-of-Thought / Tree-of-Thought: linear or branching reasoning steps.
- Planner-executor: planner decomposes; workers execute sub-tasks.
- Reflexion: agent critiques its own past outputs and iterates.

Patterns can be combined: planner using ReAct internally,
workers on simpler loops.

---

## 5. Frameworks and orchestration families

- Graph/workflow-based: nodes = tools/LLM calls; edges = control flow.
  Good for deterministic, auditable pipelines.
- Agent-centric runtimes: agents as long-lived entities with mailboxes and skill sets.
  Good for multi-agent collaboration.
- Serverless function-style: each step is stateless; all state in external stores.
  Easier scaling; harder long-horizon planning.

Design considerations: observability, safety, testability.

---

## 6. Coding agents

Architecture loop:
1. Ingest context: repo files, issue description.
2. Plan: identify files, design changes, implement, test, refine.
3. Edit: apply diffs via a patching tool.
4. Validate: run tests, linters, compilation.
5. Iterate: refine based on failures or human review.

Typical tools:
- read_file, list_files, search_codebase
- apply_patch, create_file
- run_tests, run_command
- git_commit, open_pr (with human approval)

Key challenges: context limits on large repos, hallucinations,
tool reliability, security.

---

## 7. Design recommendations

Clear separation of layers:
- Policy layer: system prompts, reasoning patterns.
- Tool layer: well-typed skills with permissions and tests.
- Memory layer: vector DB + relational store + summarization jobs.
- Orchestration layer: event loop, logging, eval hooks.

Start simple:
- Single core assistant + small high-quality tool set.
- Add specialized agents only when concrete workflows emerge.
- Include memory forgetting/summarization from the start.
- Require human approval for PR creation and deployments.
- Build a small benchmark; log failures for iteration.

---

## Summary behavior

When activated:
1. Clarify what the user really wants.
2. Select the relevant sections from this skill.
3. Answer layered: 2-3 paragraph high-level first, then detail.
4. Tie everything back to the user's concrete project.
