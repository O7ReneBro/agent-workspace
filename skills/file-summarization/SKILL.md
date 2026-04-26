---
name: file-summarization
description: Summarize files or directories so the user can quickly understand their purpose.
metadata:
  version: "1.0"
---

# Role

You are a FILE AND MODULE SUMMARIZER.

## When to use

- "What does this file do?" or "What's inside this folder?"
- You need a quick mental model before editing.

## Instructions

1. Read the file(s).
2. Identify: purpose, key exports/functions/classes, dependencies, patterns.
3. Note side effects, external dependencies, or security implications if relevant.
4. Keep concise: 3-6 bullets per file unless the user asks for more.
