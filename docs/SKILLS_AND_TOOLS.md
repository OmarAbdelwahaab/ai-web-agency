# Skills and tools: what we use, what we skip, and why

Nine repos were reviewed against this project (an AI voice caller plus an instant site builder for small local businesses). Their files are NOT copied into this ZIP: they update often, and installing from the source keeps you on the current version. `scripts/setup_skills.sh` installs the ones worth having.

## Verdicts

| Repo | Verdict | Why |
|---|---|---|
| microsoft/playwright-cli | Use | Screenshots and checks of generated sites in a real browser, at phone size. Token-efficient CLI. Wired into `agency qa-site` and the post-sale pipeline. |
| pbakaus/impeccable | Use | Its detector runs 62 deterministic design checks with no LLM and no API key, so it works as a cheap quality gate on every generated site. Its commands (`audit`, `polish`, `critique`) help while building the template. |
| Leonxlnx/taste-skill | Use once | Good for making the template itself look distinctive. Too heavy for per-client builds (its own README says 30-45 minutes and a few hundred thousand tokens per build). Do not run it at the same time as Impeccable. |
| msitarzewski/agency-agents | Small subset | Persona prompts. A few help here (UI finish-gate review, accessibility audit, reality check, evidence collection, discovery-call coaching). Most of the 150+ agents are irrelevant, and installing everything bloats context. |
| VoltAgent/awesome-design-md | Idea only | A collection of DESIGN.md files extracted from big brands' design systems. We should not clone big-brand looks onto small businesses' sites. We adopted the DESIGN.md convention with our own file. |
| dickwu/apple-design-skill | Skip | Apple Human Interface Guidelines review for native and cross-platform apps (iOS, macOS, Flutter, Tauri). Wrong target for one-page local business sites. |
| myshell-ai/OpenVoice | Skip | Instant voice cloning. Our agent must sound like what it is (an AI, disclosed in the first sentence), and cloned voices would work against that. It is also not built as a low-latency phone TTS. Use a streaming TTS provider through LiveKit. |
| ever-co/ever-gauzy | Skip for now | A full ERP/CRM/HRM/project-management platform. Far heavier than needed. SQLite plus the Telegram bot covers one owner. Revisit if you hire staff or run many clients. |
| Mahanaicoach/google-maps-scraper-kit | Not included | It scrapes Google Maps directly, and its own FAQ says that is against Google's Terms of Service and warns about IP rate limits and personal data rules. It also works against the Places API route this project uses. Use the official Places API, OpenStreetMap, or any list you have the right to use via `agency import-csv`. |

## What was added to the project because of this review
- `src/agency/sitegen/qa.py`, `agency qa-site`, and an optional QA step in the post-sale flow (`QA_ENABLED=true`): design detector result plus a phone-size screenshot sent to your Telegram with the preview.
- `agency import-csv`: neutral CSV importer with flexible column names.
- `PRODUCT.md` and `DESIGN.md`: durable context for the design tools, written for this project.
- `.agents/rules/design.md` and the `/check-site` workflow.
- `scripts/setup_skills.sh`.

## Order of use
1. `bash scripts/setup_skills.sh --core`, then `/impeccable init` in Antigravity (it will read `PRODUCT.md`).
2. Roadmap phase 2: build and test the template; run `agency qa-site` and `/impeccable audit` until clean.
3. Optional, once: `bash scripts/setup_skills.sh --taste` and ask it to elevate the template. Review the diff, then uninstall or stop using it for per-client work.
4. Optional: `bash scripts/setup_skills.sh --agents`.

## Cautions
- Impeccable sends anonymous design-roll requests to impeccable.style when a new design starts. The setup script turns that off (`npx impeccable telemetry off`). Its hooks download an engine binary on first use, so review hooks before unattended runs. Do not use its live mode on production sites.
- taste-skill pulls open-license photos and credits them on the page. Our per-client sites use no stock photos (no real photos of the business means no photos).
- Run only one design skill at a time. Two sets of design opinions in one context produce muddled output.
- Third-party skills are instructions your agent will follow. Read a skill before installing it, and keep the compliance rules in `.agents/rules/compliance.md` higher priority than any skill.
