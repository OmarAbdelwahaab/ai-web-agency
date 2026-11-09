"""Data richness score calculation and qualification gating."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from agency.config import get_settings
from agency.enrichment.models import LeadEnrichment
from agency.sitegen.schema import parse_hours


def compute_data_richness(
    enrichment: LeadEnrichment,
    lead: sqlite3.Row | dict[str, Any] | None = None,
    local_image_count: int = 0,
) -> float:
    """Calculate data richness score from 0.0 to 1.0 based on real business content.
    
    Components:
    - Photos (local owner assets or photo references): max 0.25
    - Reviews (verified snippets or rating & count): max 0.25
    - Real opening hours (parsable day/time intervals): max 0.20
    - Categories & specialties: max 0.15
    - Owner notes (call notes, history, specialties): max 0.15
    """
    score = 0.0

    # 1. Photos (max 0.25)
    if local_image_count >= 2:
        score += 0.25
    elif local_image_count == 1:
        score += 0.15
    elif len(enrichment.photo_refs) >= 2:
        score += 0.20
    elif len(enrichment.photo_refs) == 1:
        score += 0.10

    # 2. Reviews (max 0.25)
    if len(enrichment.top_reviews) >= 2:
        score += 0.25
    elif len(enrichment.top_reviews) == 1:
        score += 0.20
    elif enrichment.rating is not None and (enrichment.review_count or 0) >= 5:
        score += 0.15
    elif enrichment.rating is not None:
        score += 0.10

    # 3. Opening hours (max 0.20)
    has_hours = False
    if lead:
        hours_raw = lead["hours_json"] if isinstance(lead, sqlite3.Row) else lead.get("hours_json")
        if hours_raw:
            try:
                parsed_json = json.loads(hours_raw) if isinstance(hours_raw, str) else hours_raw
                parsed_rows = parse_hours(parsed_json)
                if parsed_rows:
                    has_hours = True
            except Exception:
                pass
    if has_hours:
        score += 0.20

    # 4. Categories & specialties (max 0.15)
    cat_val = None
    if lead:
        cat_val = lead["category"] if isinstance(lead, sqlite3.Row) else lead.get("category")
    if enrichment.categories:
        score += 0.15
    elif cat_val and cat_val.strip().lower() not in {"", "local business", "unknown"}:
        score += 0.15

    # 5. Owner notes (max 0.15)
    notes_val = enrichment.owner_notes or ""
    if not notes_val and lead:
        notes_raw = lead["notes"] if isinstance(lead, sqlite3.Row) else lead.get("notes")
        notes_val = notes_raw or ""
    if notes_val.strip():
        score += 0.15

    return round(min(1.0, score), 2)


def is_rich_lead(score: float, threshold: float | None = None) -> bool:
    """Return True if lead qualifies for custom agent-built path."""
    t = threshold if threshold is not None else get_settings().richness_threshold
    return score >= t
