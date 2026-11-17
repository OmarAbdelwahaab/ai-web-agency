"""Geoapify Places API finder. Fast, structured commercial POI search with a generous free tier (3,000 req/day)."""
from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any

import httpx

from agency.config import Settings, get_settings
from agency.db import insert_lead, phone_in_leads
from agency.phone import to_e164

log = logging.getLogger(__name__)

PLACES_URL = "https://api.geoapify.com/v2/places"
GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"

# Map common shorthand categories to Geoapify category taxonomies
CATEGORIES: dict[str, str] = {
    "restaurant": "catering.restaurant,catering.cafe,catering.fast_food",
    "cafe": "catering.cafe",
    "food": "catering.restaurant,catering.cafe,catering.fast_food",
    "pharmacy": "healthcare.pharmacy",
    "plumber": "service",
    "electrician": "service",
    "hairdresser": "service.beauty",
    "barber": "service.beauty",
    "beauty": "service.beauty",
    "hardware": "commercial.houseware_and_hardware",
    "dentist": "healthcare.dentist",
    "auto": "service.vehicle",
    "car_repair": "service.vehicle",
    "locksmith": "service",
}


def geocode_city(city: str, api_key: str, client: httpx.Client | None = None) -> tuple[float, float, str | None]:
    """Resolve city text into (lat, lon, state_code) coordinates."""
    params = {"text": city, "format": "json", "apiKey": api_key}
    c = client or httpx
    resp = c.get(GEOCODE_URL, params=params, timeout=15)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        raise ValueError(f"Could not geocode city '{city}' with Geoapify")
    first = results[0]
    lat = float(first["lat"])
    lon = float(first["lon"])
    state = first.get("state_code") or first.get("state")
    return lat, lon, state


def search(
    query: str,
    city: str,
    *,
    radius_m: int = 10000,
    limit: int = 40,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """Search for places matching a category or query in a city."""
    s = settings or get_settings()
    if not s.geoapify_api_key:
        raise RuntimeError("GEOAPIFY_API_KEY is not set")

    lat, lon, _ = geocode_city(city, s.geoapify_api_key, client=client)

    cat_key = query.lower().strip()
    geoapify_cat = CATEGORIES.get(cat_key)

    params: dict[str, Any] = {
        "filter": f"circle:{lon},{lat},{radius_m}",
        "bias": f"proximity:{lon},{lat}",
        "limit": min(limit, 100),
        "apiKey": s.geoapify_api_key,
    }

    if geoapify_cat:
        params["categories"] = geoapify_cat
        if geoapify_cat == "service" and cat_key not in ("service",):
            params["name"] = query
    else:
        # Fallback to general commercial/service with name search
        params["categories"] = "commercial,service,catering"
        params["name"] = query

    c = client or httpx
    resp = c.get(PLACES_URL, params=params, timeout=30)
    if resp.status_code != 200:
        log.error("Geoapify Places API error %s: %s", resp.status_code, resp.text[:300])
        resp.raise_for_status()

    features = resp.json().get("features", [])
    return [f.get("properties", {}) for f in features]


def save(conn: sqlite3.Connection, places: list[dict[str, Any]], category: str | None = None, state: str | None = None) -> int:
    """Store operational places with phone and without website. Deduplicated by phone."""
    n = 0
    for p in places:
        # Check contact info
        contact = p.get("contact") or {}
        phone_raw = contact.get("phone") or p.get("phone") or contact.get("phone_international")
        if not phone_raw:
            continue

        # Target businesses WITHOUT a website
        website = p.get("website") or contact.get("website")
        if website:
            continue

        # Dedupe by phone across all sources
        if phone_in_leads(conn, phone_raw):
            log.debug("Skipping duplicate phone: %s (%s)", phone_raw, p.get("name"))
            continue

        phone_norm = to_e164(phone_raw)
        place_id = p.get("place_id") or f"{p.get('lat')}_{p.get('lon')}"
        name = p.get("name") or p.get("formatted", "Unknown Business")

        hours_str = p.get("opening_hours")
        hours_json = json.dumps([hours_str] if hours_str else [])

        insert_lead(
            conn,
            source="geoapify",
            source_id=place_id,
            name=name,
            category=category or "local business",
            phone_e164=phone_norm or phone_raw,
            address=p.get("formatted") or p.get("address_line1"),
            city=p.get("city"),
            state=p.get("state_code") or p.get("state") or state,
            lat=p.get("lat"),
            lng=p.get("lon"),
            website_uri=None,
            hours_json=hours_json,
            status="new",
        )
        n += 1

    conn.commit()
    return n
