# AI Web Agency

Finds US local businesses without a website, calls eligible leads with an AI voice agent, and builds each client's site from a ready-made template within minutes of a "yes". You review every site in Telegram before it goes out.

## How to use this with Antigravity
1. Open this folder as a workspace in Antigravity. It reads `AGENTS.md` and `.agents/rules/` automatically.
2. Run the `/next-phase` workflow (or paste the prompt for a phase from `docs/ROADMAP.md`).
3. Work one phase at a time. Review diffs before accepting.

## Quick start (no phone, no API keys needed)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
agency init-db
agency demo-site            # renders a sample site into output/demo-plumbing
python -m http.server 8080 --directory output/demo-plumbing
pytest -q
```

## Project layout
```
AGENTS.md                  instructions Antigravity reads on every task
PRODUCT.md / DESIGN.md     context for design tools and the site template
.agents/rules|workflows    always-on rules and slash workflows
docs/                      architecture, compliance, roadmap, call script, skills review
scripts/setup_skills.sh    optional installer: playwright-cli, Impeccable, taste-skill, agent personas
pricing.yaml               the ONLY source of prices the agent may quote
src/agency/
  config.py db.py cli.py
  leads/                   Places API + OpenStreetMap finders, verification
  compliance/gates.py      calling window, DNC, attempt limits, live-dial switch
  voice/                   prompts, tools, LiveKit agent, dispatcher
  notify/                  Telegram bot, optional email
  payments/                payment link providers
  sitegen/                 schema, AI fill, template, render, deploy
  pipeline/post_sale.py    yes -> payment -> alert -> build -> review -> deploy
tests/
```

## Safety switches
Real dialing stays off until BOTH `LIVE_DIALING_ENABLED=true` and `LEGAL_REVIEW_DONE=true`. Read `docs/COMPLIANCE.md` first.

## Optional skills and QA tools
```bash
bash scripts/setup_skills.sh --core      # playwright-cli + Impeccable (recommended)
agency qa-site --slug demo-trades        # design detector + phone screenshot
agency import-csv --file leads.csv --lat 30.27 --lng -97.74 --city Austin --state TX
```
`docs/SKILLS_AND_TOOLS.md` explains which third-party repos are used, which are not, and why.
