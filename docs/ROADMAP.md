# Roadmap (one phase at a time; tick boxes as you finish)

Each phase has a paste-ready prompt for Antigravity. Always say: "Follow AGENTS.md and the rules in .agents/rules."

## Phase 0: Environment
- [x] venv created, `pip install -e ".[voice,dev]"` works, `pytest -q` passes
- [x] `.env` created from `.env.example`
Prompt: "Set up the dev environment, pin working dependency versions in pyproject.toml, and make sure pytest passes. Do not write feature code yet."

## Phase 1: Core (config, DB, compliance gates)
- [x] `config.py`, `db.py`, `compliance/gates.py` reviewed and fully tested
- [x] `agency init-db` creates all tables
Prompt: "Review src/agency/config.py, db.py and compliance/gates.py. Add edge-case tests for time zones around midnight and DST, DNC matching with different phone formats, and attempt limits."

## Phase 2: Site generator (can be finished with no phone or API at all)
- [x] Template renders for all four themes, responsive, accessible, readable on mobile
- [x] `agency demo-site` works; JSON-LD and meta tags present
- [x] `sitegen/ai_fill.py` fills SiteConfig from a lead record using the LLM, validated, with deterministic fallback
- [x] Deploy to Cloudflare Pages behind `DEPLOY_ENABLED`
- [x] `bash scripts/setup_skills.sh --core` run; `agency qa-site` works for all four themes (detector clean, phone screenshot reviewed)
- [x] Optional, once: polish the template with ONE design skill (taste-skill or Impeccable commands), then stop using it for per-client builds
Prompt: "Polish the site template in src/agency/sitegen/templates. Keep it fast, no JS frameworks, no stock images. Test with five fake businesses (restaurant, pharmacy, plumber, barber, hardware store) and screenshot each on mobile width."

## Phase 3: Lead pipeline
- [x] `leads/places.py` works with a real key (Enterprise-tier fields; watch free caps)
- [x] `leads/osm.py` returns candidates; results deduped by phone
- [x] `agency import-csv` verified with a real CSV (flexible columns, default coordinates for the city)
- [x] `leads/verify.py` adds timezone, phone validation, social-only detection
- [x] Optional: web-presence check via a search API before marking "no website"
Prompt: "Finish the lead pipeline. Add pagination and cost logging to places.py, dedupe across sources, and implement the optional web-presence check behind SEARCH_API_KEY."

## Phase 4: Voice agent (terminal only)
- [x] `python -m agency.voice.agent console` works with free-tier providers
- [x] Opening discloses AI + agency + purpose; opt-out and voicemail paths work
- [x] Prices only via `get_price_list`
Prompt: "Read the current LiveKit Agents docs, fix voice/agent.py to match the installed version, and get console mode working. Then write transcript-based tests for opt-out, voicemail, and price questions."

## Phase 5: Telephony (still dry-run)
- [ ] LiveKit Cloud project + SIP outbound trunk configured (manual, see below)
- [ ] `agency dial --lead-id N` dry-run logs gate decision and the dispatch it would send
- [ ] Test call to the owner's own phone only
Manual steps: create a SIP provider account, buy/register a US number, create an outbound trunk in LiveKit, put `SIP_OUTBOUND_TRUNK_ID` in `.env`.

## Phase 6: Post-sale pipeline
- [ ] Telegram bot alerts, `/approve`, `/reject`, `/status`
- [ ] Payment provider chosen (manual by default); payment link flow
- [ ] Build preview, owner approval, deploy, send link
- [ ] With `QA_ENABLED=true`: detector line and phone screenshot arrive in Telegram with the preview
Prompt: "Wire pipeline/post_sale.py end to end with fakes, then with real Telegram. Add idempotency so a repeated deal event cannot create two clients."

## Phase 7: Hardening and deploy
- [ ] Structured logging, retries, rate limits, daily call cap
- [ ] Dockerfile + compose on a small VPS (worker + Telegram bot)
- [ ] Dashboard view or CSV export of leads, calls, outcomes
- [ ] Attorney sign-off recorded before `LEGAL_REVIEW_DONE=true`
