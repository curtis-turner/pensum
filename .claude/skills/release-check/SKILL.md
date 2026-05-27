---
name: release-check
description: Run the full quality gate before a release. Use when the user wants to prepare a release, check if the project is ready to tag, or verify everything passes.
---

Run these checks in order and report the results:

1. `uv run ruff check .` (lint)
2. `uv run ruff format --check .` (format verification)
3. `uv run pytest` (tests)
4. Read the `version` field from `pyproject.toml` and confirm it matches the intended release version.

If any check fails, fix the issue and rerun that check before continuing. Report a summary: which checks passed, which failed, and the current version.
