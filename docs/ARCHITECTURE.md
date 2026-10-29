# Architecture

```
Before calling        find leads -> verify -> scrub lists -> lead record (per-lead context)
During the call       scheduler (local hours) -> LiveKit agent (STT/LLM/TTS) -> SIP trunk -> outcome
After a yes           payment link -> Telegram alert -> build site (template + JSON) -> owner review -> deploy -> send link
```

## Data flow
1. `leads.places` (Google Places API New, text search) and `leads.osm` (Overpass) insert rows into `leads` with `status='new'`.
2. `leads.verify` normalizes the phone to E.164, derives the IANA timezone from lat/lng, classifies social-only "websites", and sets `status='verified'` or `'disqualified'`.
3. `compliance.gates.can_dial()` is the single gate before any call. Result and reason are logged.
4. `voice.dispatch.dispatch_call()` creates a LiveKit agent dispatch whose JSON metadata carries the lead record (this is the per-lead context). Nothing is searched live during the call.
5. `voice.agent` (LiveKit worker) dials via `create_sip_participant`, waits for answer, runs the conversation with function tools: `record_outcome`, `mark_do_not_call`, `schedule_callback`, `get_price_list`, `create_deal`, `end_call`.
6. `create_deal` calls `pipeline.post_sale.handle_deal`: creates a `clients` row, creates a payment link, builds a preview site, and alerts the owner in Telegram.
6b. If `QA_ENABLED=true`, `sitegen/qa.py` runs the Impeccable detector and a phone-size screenshot (playwright-cli); both go to the owner with the preview. QA output lives in `output/_qa/`, never inside a site folder.
7. Owner replies `/approve <client_id>` in Telegram. `finalize_client` deploys the site and sends the URL (Telegram to the owner, optional SMTP email to the client).

## Key design decisions
- Site builds are deterministic: the LLM fills a validated `SiteConfig` JSON, a fixed Jinja2 template renders it. The model never writes HTML.
- All prices and terms come from `pricing.yaml`; the model calls a tool to read them.
- Business logic is free of LiveKit imports so it can be tested offline.
- Dry-run is the default everywhere.

## Tables (SQLite)
`leads`, `calls`, `dnc`, `clients`. See `src/agency/db.py`.

## External services
Google Places API (New), Overpass API, LiveKit Cloud (free tier) + a SIP trunk provider (Twilio/Telnyx), an OpenAI-compatible LLM (Groq free tier), Deepgram (STT), Cartesia or similar (TTS), Telegram Bot API, Cloudflare Pages.
