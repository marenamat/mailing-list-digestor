# Contributing

## Minor changes

Bug fixes, documentation improvements, and small self-contained features are welcome as pull requests without prior discussion. "Minor" means the change is easy to review in isolation and does not affect the overall architecture.

To submit a pull request:

1. Fork the repository and create a branch from `main`
2. Make your change with tests if relevant
3. Verify the test suites pass: `.venv/bin/pytest digestor/tests/ notifier/tests/ -v` (run separately — the two suites share a `tests.conftest` name that conflicts when run together from the root)
4. Open a pull request with a clear description of what changed and why

## Major changes

Before starting significant work — new services, architectural changes, changes to the SQLite schema or Matrix protocol handling, anything that touches multiple modules — open an issue or start a discussion first. This avoids wasted effort if the direction doesn't fit.

"Major" is intentionally loose. When in doubt, ask first.

## Code style

- Python: no formatter enforced, but follow the existing style (plain functions over classes where possible, thin wrappers around AI calls, all external I/O mockable in tests)
- Commits: imperative subject line, scope prefix where applicable (`feat(digestor):`, `fix(notifier):`, etc.)
- No generated files committed (no `__pycache__`, no `.pyc`)

## Tests

Every feature should have a unit test. AI calls (ollama, Claude) and HTTP calls (archive fetcher) are tested with `unittest.mock.patch` — no live credentials needed to run the suite. The watcher tests use real inotify events, not mocks.

## Environment

The project runs on Python 3.12+ with a venv at `.venv/`. Podman (rootless) and podman-compose are required for integration testing. See [README.md](README.md) for setup.
