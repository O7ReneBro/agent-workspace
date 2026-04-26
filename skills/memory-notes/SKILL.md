---
name: memory-notes
description: Read and write local knowledge-base notes in /memory/notes/. Use for storing decisions, discoveries, preferences, and reusable context.
metadata:
  version: "1.0"
---

# Role

You are a MEMORY NOTE KEEPER.

## When to use

- The user wants to save a decision, finding, or preference.
- You need to retrieve a previously stored note.
- Another skill needs persistent context across sessions.

## Note format

Each note is a Markdown file at /memory/notes/<slug>.md with:
- YAML frontmatter: title, tags, created date.
- Body: free-form Markdown.

## Instructions

Write:
1. Generate a slug from the title (lowercase, hyphenated).
2. Write YAML frontmatter: title, tags, created.
3. Write body as clean Markdown.
4. Save to /memory/notes/<slug>.md.
5. Confirm path to user.

Read:
1. Search /memory/notes/ for matching filenames or keywords.
2. Return full content or summary.
3. Suggest related notes if found.
