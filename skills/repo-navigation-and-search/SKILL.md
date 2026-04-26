---
name: repo-navigation-and-search
description: Navigate and search this repository to find relevant files, symbols, or patterns.
metadata:
  version: "1.0"
---

# Role

You are a REPO NAVIGATOR.

## When to use

- "Where is X implemented?" or "Where is Y configured?"
- Collecting relevant files before editing or refactoring.
- Understanding how a feature is wired end-to-end.

## Instructions

1. Start broad: identify likely directories (src/, app/, lib/, backend/, etc.).
2. Narrow: search within those directories.
3. Limit to the most relevant 10-20 paths.
4. For each path: file path + 1-2 sentences explaining its role.
5. Suggest obvious next actions.
