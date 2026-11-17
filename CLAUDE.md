# CLAUDE.md - AI Web Agency Guidelines

## Commands
- Run tests: `.venv\Scripts\pytest.exe -q`
- CLI: `.venv\Scripts\agency.exe <cmd>`
- Update Knowledge Graph: `.venv\Scripts\graphify.exe update .` (or run `scripts\watch_graphify.bat` in background)

## Knowledge Graph (graphify)
This project uses graphify for architecture and dependency mapping (`graphify-out/`).
- For codebase or architecture questions, first run `.venv\Scripts\graphify.exe query "<question>"`.
- After modifying code files, run `.venv\Scripts\graphify.exe update .` to keep `graphify-out/` current (AST-only, no LLM cost).

## Coding Standards & Compliance
- Python 3.11+ in `src/agency/`, tests in `tests/` (pytest).
- SQLite via stdlib `sqlite3` (`src/agency/db.py`). No ORM.
- Keep business logic isolated and testable without LiveKit or network.
- Never hardcode secrets. Read config through `src/agency/config.py`.
- Generated websites may only contain verified facts from the lead record. No invented claims.
