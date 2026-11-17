"""High-level orchestration service for lead enrichment and owner notes."""
from __future__ import annotations

import json
import logging
import sqlite3

import httpx

from agency.config import Settings, get_settings
from agency.db import add_owner_note, get_enrichment, get_lead, save_enrichment
from agency.enrichment.images import LocalAssetSource
from agency.enrichment.models import LeadEnrichment, PhotoReference, ReviewSnippet
from agency.enrichment.places_details import fetch_place_details
from agency.enrichment.score import compute_data_richness

log = logging.getLogger(__name__)


def enrich_lead(
    conn: sqlite3.Connection,
    lead_id: int,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> LeadEnrichment:
    """Enrich a lead with verified Google Places details, reviews, photos, and local assets."""
    s = settings or get_settings()
    lead = get_lead(conn, lead_id)
    if lead is None:
        raise ValueError(f"Lead #{lead_id} not found in database")

    existing_row = get_enrichment(conn, lead_id)
    existing_notes = existing_row["owner_notes"] if existing_row else None
    existing_raw = json.loads(existing_row["raw_json"]) if (existing_row and existing_row["raw_json"]) else None

    details: dict = {}
    if s.places_api_key:
        place_id = None
        if lead["source"] == "places" and lead["source_id"]:
            place_id = lead["source_id"]
        else:
            # Try to resolve place_id via text search
            from agency.leads import places

            query = f"{lead['name']} {lead['city'] or ''} {lead['state'] or ''}".strip()
            try:
                candidates = places.search(query, limit=1, settings=s, client=client)
                if candidates:
                    place_id = candidates[0].get("id")
            except Exception as e:
                log.warning("Could not resolve place ID for lead #%d via search: %s", lead_id, e)

        if place_id:
            try:
                details = fetch_place_details(place_id, settings=s, client=client)
            except Exception as e:
                log.error("Failed to fetch details for place %s: %s", place_id, e)

    # Blend details with existing lead data
    rating = details.get("rating") if details.get("rating") is not None else lead["rating"]
    review_count = details.get("review_count") if details.get("review_count") is not None else lead["rating_count"]
    top_reviews: list[ReviewSnippet] = details.get("reviews") or []
    if not top_reviews and existing_row and existing_row["top_reviews_json"]:
        try:
            top_reviews = [ReviewSnippet(**r) for r in json.loads(existing_row["top_reviews_json"])]
        except Exception:
            pass

    categories: list[str] = details.get("categories") or []
    if not categories and existing_row and existing_row["categories_json"]:
        try:
            categories = json.loads(existing_row["categories_json"])
        except Exception:
            pass
    if not categories and lead["category"]:
        categories = [lead["category"]]

    photo_refs: list[PhotoReference] = details.get("photos") or []
    if not photo_refs and existing_row and existing_row["photo_refs_json"]:
        try:
            photo_refs = [PhotoReference(**p) for p in json.loads(existing_row["photo_refs_json"])]
        except Exception:
            pass

    website_confirmed_none = details.get("website_confirmed_none")
    if website_confirmed_none is None:
        website_confirmed_none = not bool(lead["website_uri"])

    owner_notes = existing_notes if existing_notes is not None else (lead["notes"] or None)
    raw_payload = details.get("raw_json") or existing_raw

    # Local owner photos
    local_images = LocalAssetSource(s.assets_dir).get_images(lead_id)

    enrichment = LeadEnrichment(
        lead_id=lead_id,
        rating=rating,
        review_count=review_count,
        top_reviews=top_reviews,
        categories=categories,
        photo_refs=photo_refs,
        website_confirmed_none=website_confirmed_none,
        owner_notes=owner_notes,
        raw_json=raw_payload,
    )

    # Compute data richness score
    richness = compute_data_richness(enrichment, lead, local_image_count=len(local_images))
    enrichment.data_richness = richness

    # Persist to database
    save_enrichment(
        conn,
        lead_id=lead_id,
        rating=rating,
        review_count=review_count,
        top_reviews_json=json.dumps([r.model_dump() for r in top_reviews]),
        categories_json=json.dumps(categories),
        photo_refs_json=json.dumps([p.model_dump() for p in photo_refs]),
        website_confirmed_none=website_confirmed_none,
        owner_notes=owner_notes,
        data_richness=richness,
        raw_json=json.dumps(raw_payload) if raw_payload else None,
    )

    return enrichment


def record_owner_note(
    conn: sqlite3.Connection,
    lead_id: int,
    notes: str,
    *,
    settings: Settings | None = None,
) -> LeadEnrichment:
    """Record call notes from the owner and recalculate data richness."""
    add_owner_note(conn, lead_id, notes)

    lead = get_lead(conn, lead_id)
    if lead is None:
        raise ValueError(f"Lead #{lead_id} not found in database")

    s = settings or get_settings()
    row = get_enrichment(conn, lead_id)
    local_images = LocalAssetSource(s.assets_dir).get_images(lead_id)

    top_reviews: list[ReviewSnippet] = []
    if row and row["top_reviews_json"]:
        try:
            top_reviews = [ReviewSnippet(**r) for r in json.loads(row["top_reviews_json"])]
        except Exception:
            pass

    categories: list[str] = []
    if row and row["categories_json"]:
        try:
            categories = json.loads(row["categories_json"])
        except Exception:
            pass

    photo_refs: list[PhotoReference] = []
    if row and row["photo_refs_json"]:
        try:
            photo_refs = [PhotoReference(**p) for p in json.loads(row["photo_refs_json"])]
        except Exception:
            pass

    owner_notes = row["owner_notes"] if row else notes

    enrichment = LeadEnrichment(
        lead_id=lead_id,
        rating=row["rating"] if row else lead["rating"],
        review_count=row["review_count"] if row else lead["rating_count"],
        top_reviews=top_reviews,
        categories=categories,
        photo_refs=photo_refs,
        website_confirmed_none=bool(row["website_confirmed_none"]) if row else not bool(lead["website_uri"]),
        owner_notes=owner_notes,
    )

    richness = compute_data_richness(enrichment, lead, local_image_count=len(local_images))
    enrichment.data_richness = richness

    conn.execute(
        "UPDATE lead_enrichment SET data_richness = ?, updated_at = datetime('now') WHERE lead_id = ?",
        (richness, lead_id),
    )
    conn.commit()

    return enrichment
