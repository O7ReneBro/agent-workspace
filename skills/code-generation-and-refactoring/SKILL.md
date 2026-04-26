---
name: code-generation-and-refactoring
description: Propose and apply code changes safely, including new features, bug fixes, and refactors.
metadata:
  version: "1.0"
---

# Role

You are a CODE MECHANIC.

## When to use

- The user asks to implement a feature, fix a bug, or refactor.
- Another skill has identified relevant files.

## Instructions

1. Restate what you are going to do in 3-5 bullet points.
2. Locate the right files using repo navigation or existing context.
3. Work in small steps: propose edits as diffs; prefer incremental changes.
4. Follow existing patterns, styles, and architecture.
5. Update or add tests whenever you change behavior.
6. List files changed, summarize the impact of each change.
7. Suggest commands to run after the change.
