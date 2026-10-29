"""Import leads from any CSV (your own list, an export from a lead source you are licensed to use, etc.).

Column names are matched flexibly. If the file has no coordinates, pass default lat/lng for the city so a
timezone can be derived (city-level accuracy is enough for calling-window checks).
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from agency.db import insert_lead

ALIASES = {
    "name": ("name", "title", "business_name", "business"),
    "phone": ("phone", "phone_number", "telephone", "tel"),
    "website": ("website", "website_uri", "url", "site"),
    "address": ("address", "full_address", "formatted_address", "complete_address"),
    "category": ("category", "type", "categories", "main_category"),
    "rating": ("rating", "review_rating", "stars"),
    "rating_count": ("review_count", "rating_count", "reviews", "user_ratings_total"),
    "lat": ("lat", "latitude"),
    "lng": ("lng", "lon", "longitude"),
    "city": ("city", "locality"),
    "state": ("state", "region", "state_code"),
}


def _pick(row: dict, key: str):
    lowered = {k.strip().lower(): v for k, v in row.items() if k}
    for alias in ALIASES[key]:
        v = lowered.get(alias)
        if v not in (None, ""):
            return v.strip() if isinstance(v, str) else v
    return None


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def import_csv(
    conn: sqlite3.Connection,
    path: str | Path,
    *,
    default_lat: float | None = None,
    default_lng: float | None = None,
    default_city: str | None = None,
    default_state: str | None = None,
    source: str = "csv",
) -> dict[str, int]:
    counts = {"inserted": 0, "duplicates": 0, "skipped_no_name_or_phone": 0, "no_coordinates": 0}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name, phone = _pick(row, "name"), _pick(row, "phone")
            if not name or not phone:
                counts["skipped_no_name_or_phone"] += 1
                continue
            lat = _float(_pick(row, "lat")) if _pick(row, "lat") else default_lat
            lng = _float(_pick(row, "lng")) if _pick(row, "lng") else default_lng
            if lat is None or lng is None:
                counts["no_coordinates"] += 1  # inserted anyway; verify will disqualify it
            digits = re.sub(r"\D", "", phone)
            source_id = digits or hashlib.sha1(f"{name}{_pick(row, 'address')}".encode()).hexdigest()[:16]
            new_id = insert_lead(
                conn,
                source=source,
                source_id=source_id,
                name=name,
                category=_pick(row, "category"),
                phone_e164=phone,  # normalized in verify
                address=_pick(row, "address"),
                city=_pick(row, "city") or default_city,
                state=_pick(row, "state") or default_state,
                lat=lat,
                lng=lng,
                website_uri=_pick(row, "website"),
                rating=_float(_pick(row, "rating")),
                rating_count=_int(_pick(row, "rating_count")),
                raw_json=json.dumps(row),
            )
            counts["inserted" if new_id else "duplicates"] += 1
    return counts
