"""OpenStreetMap Overpass finder. Free, but small-business data is patchy: treat results as candidates to verify."""
from __future__ import annotations

import json
import logging
import sqlite3

import httpx

from agency.config import Settings, get_settings
from agency.db import insert_lead

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


def build_query(category: str, area_name: str) -> str:
    key, values = CATEGORIES[category]
    return f"""
[out:json][timeout:90];
area["name"="{area_name}"]["boundary"="administrative"]->.a;
(
  nwr["{key}"~"^({values})$"]["phone"][!"website"][!"contact:website"](area.a);
);
out center tags;
""".strip()


def search(category: str, area_name: str, *, settings: Settings | None = None) -> list[dict]:
    s = settings or get_settings()
    q = build_query(category, area_name)
    resp = httpx.post(s.overpass_url, data={"data": q}, timeout=120)
    resp.raise_for_status()
    return resp.json().get("elements", [])


def save(conn: sqlite3.Connection, elements: list[dict], category: str, state: str | None = None) -> int:
    n = 0
    for el in elements:
        tags = el.get("tags", {})
        center = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        new_id = insert_lead(
            conn,
            source="osm",
            source_id=f"{el['type']}/{el['id']}",
            name=tags.get("name", "Unknown"),
            category=category,
            phone_e164=tags.get("phone") or tags.get("contact:phone"),  # normalized in verify
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
