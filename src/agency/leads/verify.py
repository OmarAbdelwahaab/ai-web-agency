"""Normalize and qualify leads. Sets status to 'verified' or 'disqualified'."""
from __future__ import annotations

import logging
import sqlite3
from functools import lru_cache
from urllib.parse import urlparse

from agency.phone import to_e164

log = logging.getLogger(__name__)

SOCIAL_HOSTS = ("facebook.com", "instagram.com", "linktr.ee", "yelp.com", "x.com", "twitter.com", "tiktok.com")


@lru_cache(maxsize=1)
def _tf():
    from timezonefinder import TimezoneFinder

    return TimezoneFinder()


def timezone_for(lat: float | None, lng: float | None) -> str | None:
    if lat is None or lng is None:
        return None
    return _tf().timezone_at(lat=lat, lng=lng)


def classify_website(uri: str | None) -> str:
    """'none' | 'social' | 'real'. Social-only listings still count as website-less leads."""
    if not uri:
        return "none"
    host = (urlparse(uri).hostname or "").lower()
    return "social" if any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS) else "real"


def verify_lead(conn: sqlite3.Connection, lead: sqlite3.Row) -> str:
    phone = to_e164(lead["phone_e164"])
    tz = timezone_for(lead["lat"], lead["lng"])
    site = classify_website(lead["website_uri"])
    if not phone:
        status, note = "disqualified", "invalid phone"
    elif not tz:
        status, note = "disqualified", "no timezone (missing coordinates)"
    elif site == "real":
        status, note = "disqualified", "has a real website"
    else:
        status, note = "verified", f"website={site}"
    # TODO(phase 3): web-presence check via a search API; set website_checked=1 when done.
    conn.execute(
        "UPDATE leads SET phone_e164 = ?, timezone = ?, status = ?, notes = ? WHERE id = ?",
        (phone or lead["phone_e164"], tz, status, note, lead["id"]),
    )
    conn.commit()
    return status


def verify_all(conn: sqlite3.Connection, limit: int = 500) -> dict[str, int]:
    counts: dict[str, int] = {}
    for lead in conn.execute("SELECT * FROM leads WHERE status = 'new' LIMIT ?", (limit,)).fetchall():
        st = verify_lead(conn, lead)
        counts[st] = counts.get(st, 0) + 1
    return counts


def scrub_all(conn: sqlite3.Connection) -> dict[str, int]:
    """Mark verified leads 'ready' unless their number is on the internal DNC list."""
    from agency.compliance.gates import is_dnc

    counts = {"ready": 0, "dnc": 0}
    for lead in conn.execute("SELECT * FROM leads WHERE status = 'verified'").fetchall():
        if is_dnc(conn, lead["phone_e164"]):
            conn.execute("UPDATE leads SET status = 'dnc' WHERE id = ?", (lead["id"],))
            counts["dnc"] += 1
        else:
            conn.execute("UPDATE leads SET status = 'ready' WHERE id = ?", (lead["id"],))
            counts["ready"] += 1
    conn.commit()
    return counts
