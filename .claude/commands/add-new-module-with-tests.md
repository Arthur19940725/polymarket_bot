---
name: add-new-module-with-tests
description: Workflow command scaffold for add-new-module-with-tests in polymarket_bot.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /add-new-module-with-tests

Use this workflow when working on **add-new-module-with-tests** in `polymarket_bot`.

## Goal

Adds a new functional module (e.g., clock, storage, api client, ranker, watcher, risk, executor, backtest) along with its corresponding test file.

## Common Files

- `polymarket/polymarket-copy-bot/{module}.py`
- `polymarket/polymarket-copy-bot/tests/test_{module}.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Create or update a main implementation file in polymarket/polymarket-copy-bot/{module}.py
- Create or update a corresponding test file in polymarket/polymarket-copy-bot/tests/test_{module}.py

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.