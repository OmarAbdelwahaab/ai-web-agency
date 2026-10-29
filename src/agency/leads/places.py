"""Google Places API (New) text search. Official API only; do not scrape Google Maps.

Cost note: requesting phone/website fields puts calls in the Enterprise SKU, which has a small
free monthly cap. Check current pricing at https://developers.google.com/maps/billing-and-pricing/pricing
"""
from __future__ import annotations

import json
import logging
import sqlite3

import httpx

from agency.config import Settings, get_settings
from agency.db import insert_lead

log = logging.getLogger(__name__)

URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join(
    f"places.{f}"
    for f in (
        "id", "displayName", "formattedAddress", "nationalPhoneNumber", "internationalPhoneNumber",
        "websiteUri", "rating", "userRatingCount", "businessStatus", "regularOpeningHours",
        "location", "types", "primaryType", "addressComponents",
    )
) + ",nextPageToken"


def _state_city(components: list[dict]) -> tuple[str | None, str | None]:
    city = state = None
    for c in components or []:
        types = c.get("types", [])
        if "locality" in types:
            city = c.get("longText")
        if "administrative_area_level_1" in types:
            state = c.get("shortText")
    return city, state


def search(query: str, *, limit: int = 40, settings: Settings | None = None) -> list[dict]:
    """Run a text search like 'plumber in Austin, TX' and return raw place dicts (max `limit`)."""
    s = settings or get_settings()
    if not s.places_api_key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not set")
    headers = {"X-Goog-Api-Key": s.places_api_key, "X-Goog-FieldMask": FIELDS, "Content-Type": "application/json"}
    results: list[dict] = []
    token: str | None = None
    with httpx.Client(timeout=20) as client:
        while len(results) < limit:
            body: dict = {"textQuery": query, "pageSize": 20}
            if token:
                body["pageToken"] = token
            resp = client.post(URL, headers=headers, json=body)
            if resp.status_code != 200:
                log.error("Places API error %s: %s", resp.status_code, resp.text[:300])
                break
            data = resp.json()
            results.extend(data.get("places", []))
            token = data.get("nextPageToken")
            if not token:
                break
    return results[:limit]


def save(conn: sqlite3.Connection, places: list[dict], category: str | None = None) -> int:
    """Store places that look like candidates (operational, has phone, no websiteUri). Returns count inserted."""
    n = 0
    for p in places:
        if p.get("businessStatus") not in (None, "OPERATIONAL"):
            continue
        if not p.get("nationalPhoneNumber"):
            continue
        city, state = _state_city(p.get("addressComponents", []))
        loc = p.get("location", {})
        new_id = insert_lead(
            conn,
            source="places",
            source_id=p["id"],
            name=p.get("displayName", {}).get("text", "Unknown"),
            category=category or p.get("primaryType"),
            phone_e164=p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber"),  # normalized in verify
            address=p.get("formattedAddress"),
            city=city,
            state=state,
            lat=loc.get("latitude"),
            lng=loc.get("longitude"),
            website_uri=p.get("websiteUri"),
            rating=p.get("rating"),
            rating_count=p.get("userRatingCount"),
            business_status=p.get("businessStatus"),
            hours_json=json.dumps(p.get("regularOpeningHours", {}).get("weekdayDescriptions", [])),
            raw_json=json.dumps(p),
        )
        n += 1 if new_id else 0
    return n
