"""OpenStreetMap Overpass finder. Free, but small-business data is patchy: treat results as candidates to verify."""
from __future__ import annotations

import json
import logging
import sqlite3

import httpx

from agency.config import Settings, get_settings
from agency.db import insert_lead, phone_in_leads
from agency.phone import to_e164

log = logging.getLogger(__name__)

# category label -> (OSM key, regex of values)
CATEGORIES = {
    "restaurant": ("amenity", "restaurant|cafe|fast_food"),
    "pharmacy": ("amenity", "pharmacy"),
    "plumber": ("craft", "plumber"),
    "electrician": ("craft", "electrician"),
    "hairdresser": ("shop", "hairdresser|barber"),
    "hardware": ("shop", "hardware|doityourself"),
}

ALIASES = {
    "restaurant": ("restaurant", "restaurants", "cafe", "food", "diner", "bistro", "bakery"),
    "pharmacy": ("pharmacy", "pharmacies", "drugstore"),
    "plumber": ("plumber", "plumbers", "plumbing"),
    "electrician": ("electrician", "electricians", "electrical"),
    "hairdresser": ("hairdresser", "hairdressers", "barber", "barbers", "salon"),
    "hardware": ("hardware", "diy"),
}


def build_query(category: str, area_name: str) -> str:
    cat = category.lower().strip()
    if cat not in CATEGORIES:
        for k, aliases in ALIASES.items():
            if cat in aliases or any(a in cat for a in aliases):
                cat = k
                break
    if cat not in CATEGORIES:
        available = ", ".join(sorted(CATEGORIES.keys()))
        raise ValueError(f"Unknown OSM category '{category}'. Available: {available}")
    key, values = CATEGORIES[cat]
    return f"""
[out:json][timeout:90];
area["name"="{area_name}"]["boundary"="administrative"]->.a;
(
  nwr["{key}"~"^({values})$"]["phone"][!"website"][!"contact:website"](area.a);
);
out center tags;
""".strip()


def search(
    category: str,
    area_name: str,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> list[dict]:
    s = settings or get_settings()
    q = build_query(category, area_name)
    if client is not None:
        resp = client.post(s.overpass_url, data={"data": q}, timeout=120)
    else:
        resp = httpx.post(s.overpass_url, data={"data": q}, timeout=120)
    resp.raise_for_status()
    return resp.json().get("elements", [])


def save(conn: sqlite3.Connection, elements: list[dict], category: str, state: str | None = None) -> int:
    n = 0
    for el in elements:
        tags = el.get("tags", {})
        phone_raw = tags.get("phone") or tags.get("contact:phone")
        if not phone_raw:
            continue
        # Dedupe by phone across all sources
        if phone_in_leads(conn, phone_raw):
            log.debug("Skipping duplicate phone: %s (%s)", phone_raw, tags.get("name"))
            continue
        phone_norm = to_e164(phone_raw)
        center = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        new_id = insert_lead(
            conn,
            source="osm",
            source_id=f"{el['type']}/{el['id']}",
            name=tags.get("name", "Unknown"),
            category=category,
            phone_e164=phone_norm or phone_raw,
            address=" ".join(filter(None, [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:city")])),
            city=tags.get("addr:city"),
            state=tags.get("addr:state") or state,
            lat=center.get("lat"),
            lng=center.get("lon"),
            website_uri=None,
            hours_json=json.dumps([tags["opening_hours"]] if "opening_hours" in tags else []),
            raw_json=json.dumps(el),
        )
        n += 1 if new_id else 0
    return n
