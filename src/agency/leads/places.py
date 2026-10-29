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
from agency.db import insert_lead, phone_in_leads
from agency.phone import to_e164

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


def search(
    query: str,
    *,
    limit: int = 40,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Run a text search like 'plumber in Austin, TX' and return raw place dicts (max `limit`)."""
    s = settings or get_settings()
    if not s.places_api_key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not set")
    headers = {"X-Goog-Api-Key": s.places_api_key, "X-Goog-FieldMask": FIELDS, "Content-Type": "application/json"}
    results: list[dict] = []
    token: str | None = None
    req_count = 0

    def _paginate(c: httpx.Client):
        nonlocal token, req_count
        while len(results) < limit:
            page_size = min(20, limit - len(results))
            body: dict = {"textQuery": query, "pageSize": page_size}
            if token:
                body["pageToken"] = token
            req_count += 1
            resp = c.post(URL, headers=headers, json=body)
            if resp.status_code != 200:
                log.error("Places API error %s: %s", resp.status_code, resp.text[:300])
                break
            data = resp.json()
            places = data.get("places", [])
            results.extend(places)
            token = data.get("nextPageToken")
            if not token or not places:
                break

    if client is not None:
        _paginate(client)
    else:
        with httpx.Client(timeout=20) as c:
            _paginate(c)

    est_cost = req_count * 0.035
    log.info(
        "Places API search for '%s': %d request(s) made, %d places returned. Estimated cost: $%.4f (Enterprise SKU ~ $0.035/req)",
        query, req_count, len(results), est_cost,
    )
    return results[:limit]


def save(conn: sqlite3.Connection, places: list[dict], category: str | None = None) -> int:
    """Store places that look like candidates (operational, has phone, no websiteUri). Returns count inserted."""
    n = 0
    for p in places:
        if p.get("businessStatus") not in (None, "OPERATIONAL"):
            continue
        phone_raw = p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber")
        if not phone_raw:
            continue
        # Dedupe by phone across all sources
        if phone_in_leads(conn, phone_raw):
            log.debug("Skipping duplicate phone: %s (%s)", phone_raw, p.get("displayName", {}).get("text"))
            continue
        city, state = _state_city(p.get("addressComponents", []))
        loc = p.get("location", {})
        phone_norm = to_e164(phone_raw)
        new_id = insert_lead(
            conn,
            source="places",
            source_id=p["id"],
            name=p.get("displayName", {}).get("text", "Unknown"),
            category=category or p.get("primaryType"),
            phone_e164=phone_norm or phone_raw,
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
