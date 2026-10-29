# Code style

- Type hints everywhere, `from __future__ import annotations`, small functions, docstrings only where behavior is non-obvious.
- No network calls at import time. Pass dependencies (DB connection, settings, clock) as arguments so tests can inject fakes.
- Use `httpx` with explicit timeouts. Handle and log API errors; never crash a batch for one bad lead.
- Tests live in `tests/`, named `test_<module>.py`. Mock network and LiveKit.
- Prefer boring and readable over clever.
