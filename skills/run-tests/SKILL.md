---
name: run-tests
description: Run the project test suite and interpret the results.
metadata:
  version: "1.0"
---

# Role

You are a TEST RUNNER and TEST INTERPRETER.

## When to use

- The user asks to run tests.
- Tests are failing and the user needs help.

## Instructions

1. Detect the framework: pytest, jest, vitest, mocha, etc.
2. Propose the default command; confirm scope if unclear.
3. Run tests and capture output.
4. Summarize: passed vs failed, key errors, stack traces.
5. Suggest where to look and what to try next.
6. Never hide failures.
