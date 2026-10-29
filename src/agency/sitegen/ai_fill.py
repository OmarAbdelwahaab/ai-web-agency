"""Use an LLM to write tagline/about/services from the lead record and call notes, with strict validation."""
from __future__ import annotations

import json
import logging
import sqlite3

from pydantic import ValidationError

from agency.config import Settings, get_settings
from agency.sitegen.schema import AIText, SiteConfig, config_from_lead

log = logging.getLogger(__name__)

SYSTEM = """You write short website copy for a local business.
Rules:
- Use ONLY facts in the provided JSON (business name, category, city, rating, call notes).
- Never invent hours, prices, years in business, awards, reviews, owner names, or services.
- "services" may only list services explicitly mentioned in call_notes. If none, return an empty list.
- Plain, friendly, specific language. No hype, no superlatives like "best" or "#1".
- tagline <= 12 words. about <= 80 words, or null if there are not enough facts.
Return a single JSON object: {"tagline": str, "about": str|null, "services": [{"name": str, "description": str|null, "price": str|null}]}"""


def fill_config(
    lead: sqlite3.Row,
    call_notes: str = "",
    *,
    credit: str | None = None,
    settings: Settings | None = None,
    client=None,
) -> SiteConfig:
    """Return a SiteConfig. Falls back to the deterministic config if the LLM is unavailable or invalid."""
    s = settings or get_settings()
    base = config_from_lead(lead, credit=credit)
    if client is None:
        if not s.llm_api_key:
            return base
        from openai import OpenAI

        client = OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key, timeout=30)

    facts = {
        "business_name": lead["name"],
        "category": lead["category"],
        "city": lead["city"],
        "rating": lead["rating"],
        "rating_count": lead["rating_count"],
        "call_notes": call_notes,
    }
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(facts)}]
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=s.llm_model, messages=messages, temperature=0.3, response_format={"type": "json_object"}
            )
            text = AIText.model_validate_json(resp.choices[0].message.content)
            return base.model_copy(update={"tagline": text.tagline, "about": text.about, "services": text.services})
        except (ValidationError, json.JSONDecodeError) as e:
            log.warning("LLM output invalid (attempt %s): %s", attempt + 1, e)
            messages.append({"role": "user", "content": f"Invalid output: {e}. Return valid JSON only."})
        except Exception as e:  # network/provider errors
            log.error("LLM call failed: %s", e)
            break
    return base
