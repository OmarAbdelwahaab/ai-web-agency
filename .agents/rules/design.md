# Design rules for the site template

- Read `PRODUCT.md` and `DESIGN.md` before changing anything in `src/agency/sitegen/templates/` or `render.py`.
- Keep the template one page, no JS framework, no stock photos, no external scripts. Fonts via Google Fonts with fallbacks only.
- Never copy another brand's design system or imitate a recognizable brand.
- Facts on a generated page must come from the lead record or call notes. The LLM fills text fields only; templates produce all HTML.
- After any template change: run `agency demo-site` for all four themes, run `agency qa-site`, fix findings, run `pytest -q`.
- Use one design skill at a time (Impeccable or taste-skill, not both) and keep `.agents/rules/compliance.md` higher priority than any skill.
