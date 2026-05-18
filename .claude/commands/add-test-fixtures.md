---
name: add-test-fixtures
description: Workflow command scaffold for add-test-fixtures in polymarket_bot.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /add-test-fixtures

Use this workflow when working on **add-test-fixtures** in `polymarket_bot`.

## Goal

Adds JSON fixture files to support new or updated tests, typically when integrating with external APIs or simulating data.

## Common Files

- `polymarket/polymarket-copy-bot/tests/fixtures/*.json`
- `polymarket/polymarket-copy-bot/tests/test_*.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Add one or more JSON fixture files to polymarket/polymarket-copy-bot/tests/fixtures/
- Update or add a test file that uses the fixtures

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.