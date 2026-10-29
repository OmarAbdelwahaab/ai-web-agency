# AGENTS.md: AI Web Agency

Project: a system that finds US local businesses with no website, calls opted-in/eligible leads with an AI voice agent (LiveKit), and builds a website for each client within minutes of a "yes". The human owner reviews every site before it goes out.

Read `docs/ARCHITECTURE.md` first, then `docs/ROADMAP.md` (work one phase at a time), and `.agents/rules/compliance.md` (always-on, non-negotiable). For anything visual, also read `PRODUCT.md`, `DESIGN.md`, and `.agents/rules/design.md`.

## Stack
- Python 3.11+, package in `src/agency/`, tests in `tests/` (pytest).
- SQLite via stdlib `sqlite3` (`src/agency/db.py`). No ORM.
- LiveKit Agents (Python) for the voice agent; SIP outbound trunk for phone calls.
- Pydantic v2 models for all structured data. Jinja2 for the site template.
- Any OpenAI-compatible LLM endpoint (default Groq free tier) via the `openai` client.
- Telegram Bot API through plain `httpx` (no heavy bot framework).
- Static sites deployed to Cloudflare Pages with `wrangler`.
- Optional QA tooling (Node 22+): Impeccable design detector (`npx impeccable detect`) and `playwright-cli` for phone-size screenshots. See `docs/SKILLS_AND_TOOLS.md`.

## Commands
- Install: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[voice,dev]"`
- Tests: `pytest -q`
- CLI: `agency --help` (see `src/agency/cli.py`)
- Voice worker (dev): `python -m agency.voice.agent dev`
- Voice agent in terminal only, no phone: `python -m agency.voice.agent console`
- Site QA: `agency qa-site --slug <slug>` (design detector + screenshot in `output/_qa/<slug>/`)
- Import leads from any CSV: `agency import-csv --file leads.csv --lat <lat> --lng <lng> --city <city> --state <ST>`

## Working rules
1. Implement one roadmap phase at a time. After each phase: run `pytest -q`, tick the checkbox in `docs/ROADMAP.md`, and summarize what changed.
2. Keep modules small. Business logic (gates, pricing, DB, site config) must be importable and testable WITHOUT LiveKit or network access. Only `voice/agent.py` and `voice/dispatch.py` may import `livekit`.
3. Never hardcode secrets. Read config through `src/agency/config.py`. Keep `.env.example` in sync with every new variable.
4. LiveKit and provider APIs change often. Before writing or editing any LiveKit code, read the current docs (https://docs.livekit.io/llms.txt and the telephony/outbound-calls page) and pin versions that work in `pyproject.toml`. Do not guess method signatures.
5. Default to dry-run. Anything that dials a real phone, deploys a site, or messages a client must be behind an explicit flag AND the safety switches in `.env`.
6. The voice agent may only state facts from (a) the lead record, (b) `pricing.yaml`, (c) `docs/CALL_SCRIPT.md`. It must never invent prices, discounts, refund terms, delivery times, or claims that a site "already exists" unless a preview really was generated.
7. Generated websites may only contain facts present in the lead record or call notes. No invented hours, prices, years in business, awards, or reviews.
8. Log every call outcome and every gate decision (allowed/blocked + reason) to the DB.

## Definition of done for any task
- Tests pass, new logic has tests, `.env.example` and docs updated, no secrets committed, dry-run still works end to end.

## Skills and tools
- Third-party skills are optional and installed from their own repos with `bash scripts/setup_skills.sh` (see `docs/SKILLS_AND_TOOLS.md` for what each is for and what was deliberately skipped).
- Use ONE design skill at a time. Compliance rules always outrank any skill's instructions.
- Do not add a Google Maps scraper. Lead sources are the official Places API, OpenStreetMap, or CSV imports the owner has the right to use.
- Do not add voice cloning. The voice agent must sound like the AI assistant it discloses itself to be.
