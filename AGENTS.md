# Agents Guide: Grinder

## Essential Commands
- **Tests**: Run suites separately to avoid `tests.conftest` conflicts:
  - `.venv/bin/pytest digestor/tests/ -v`
  - `.venv/bin/pytest notifier/tests/ -v`
- **Smoke Test**: Verify mail delivery path: `SMTP_RECIPIENT=smoketest@mail-receiver.test ./smoke_test.sh`
- **Environment**: Python 3.12+; virtual environment at `.venv/`.

## Architecture & Data Flow
- **Components**: `mail-receiver` (Postfix) $\rightarrow$ `digestor` (Python) $\rightarrow$ `notifier` (Python Matrix bot).
- **Shared State**: 
  - SQLite DB (`/data/digestor.db`): Shared between `digestor` (writer) and `notifier` (reader/writer).
  - Maildir (`/data/maildir`): Shared between `mail-receiver` (writer) and `digestor` (reader).
- **AI Pipeline**: Local Ollama (`gemma3:4b`) for first-pass triage $\rightarrow$ Anthropic Claude API for final classification, digests, and web tracking summaries.
- **Configs**: Located in `config/`. `context.md` is re-read on every processing cycle without requiring restart.

## Conventions & Constraints
- **Code Style**: Prefer plain functions over classes; keep AI wrappers thin.
- **Testing**: Use `unittest.mock.patch` for all external I/O (AI APIs, HTTP). Watcher tests must use real inotify events.
- **Deployment**: Rootless Podman / podman-compose. Secrets are managed via `.env`.
- **Commits**: Imperative subject lines with scope prefixes: `feat(digestor): ...` or `fix(notifier): ...`.
