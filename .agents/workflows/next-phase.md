---
description: Implement the next unchecked phase from docs/ROADMAP.md
---

1. Read `AGENTS.md`, `.agents/rules/compliance.md`, and `docs/ARCHITECTURE.md`.
2. Open `docs/ROADMAP.md` and find the first phase with unchecked boxes.
3. Write a short plan for that phase only. Wait for approval if the plan touches dialing, payments, or deployment.
4. Implement the phase. Look up current docs for any third-party API before using it.
5. Add or update tests, run `pytest -q`, and fix failures.
6. Tick the finished boxes in `docs/ROADMAP.md` and update `.env.example` and `README.md` if anything changed.
7. Summarize what was done, what was skipped, and what the owner must do manually (API keys, accounts, trunk setup).
