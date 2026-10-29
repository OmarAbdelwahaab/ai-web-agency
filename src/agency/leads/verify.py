"""Normalize and qualify leads. Sets status to 'verified' or 'disqualified'."""
from __future__ import annotations

import logging
import sqlite3
from functools import lru_cache
from urllib.parse import urlparse

import httpx

from agency.config import Settings, get_settings
from agency.phone import to_e164

log = logging.getLogger(__name__)

SOCIAL_HOSTS = ("facebook.com", "instagram.com", "linktr.ee", "yelp.com", "x.com", "twitter.com", "tiktok.com")

AGGREGATOR_HOSTS = (
    "yelp.com", "yellowpages.com", "bbb.org", "mapquest.com", "angi.com",
    "thumbtack.com", "superpages.com", "manta.com", "chamberofcommerce.com",
    "dexknows.com", "whitepages.com", "tripadvisor.com", "groupon.com",
    "nextdoor.com", "citysearch.com", "usps.com", "wikipedia.org",
)


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


def check_web_presence(
    name: str,
    city: str | None = None,
    state: str | None = None,
    *,
    api_key: str | None = None,
    engine_id: str | None = None,
    client: httpx.Client | None = None,
) -> str | None:
    """Check search API for business web presence.
    Returns the real website URL if found, None otherwise.
    """
    if not api_key:
        return None

    query = f"{name} {city or ''} {state or ''}".strip()
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": engine_id or "0",
        "q": query,
        "num": 5,
    }

    def _parse_items(items: list[dict]) -> str | None:
        for item in items:
            link = item.get("link") or item.get("url")
            if not link:
                continue
            if classify_website(link) == "real":
                host = (urlparse(link).hostname or "").lower()
                if not any(host == a or host.endswith("." + a) for a in AGGREGATOR_HOSTS):
                    return link
        return None

    if client is not None:
        try:
            resp = client.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                return _parse_items(resp.json().get("items", []))
        except Exception as e:
            log.warning("Web presence check failed: %s", e)
        return None

    with httpx.Client(timeout=10) as c:
        try:
            resp = c.get(url, params=params)
            if resp.status_code == 200:
                return _parse_items(resp.json().get("items", []))
        except Exception as e:
            log.warning("Web presence check failed: %s", e)
    return None


def verify_lead(
    conn: sqlite3.Connection,
    lead: sqlite3.Row,
    *,
    settings: Settings | None = None,
    search_client: httpx.Client | None = None,
) -> str:
    s = settings or get_settings()
    phone = to_e164(lead["phone_e164"])
    tz = timezone_for(lead["lat"], lead["lng"])
    site = classify_website(lead["website_uri"])
    website_checked = lead["website_checked"]

    if not phone:
        status, note = "disqualified", "invalid phone"
    elif not tz:
        status, note = "disqualified", "no timezone (missing coordinates)"
    elif site == "real":
        status, note = "disqualified", "has a real website"
        website_checked = 1
    else:
        found_site = None
        if s.search_api_key:
            found_site = check_web_presence(
                name=lead["name"],
                city=lead["city"],
                state=lead["state"],
                api_key=s.search_api_key,
                engine_id=s.search_engine_id,
                client=search_client,
            )
            website_checked = 1

        if found_site:
            status, note = "disqualified", f"found website via search: {found_site}"
        else:
            status, note = "verified", f"website={site}"

    conn.execute(
        "UPDATE leads SET phone_e164 = ?, timezone = ?, status = ?, notes = ?, website_checked = ? WHERE id = ?",
        (phone or lead["phone_e164"], tz, status, note, website_checked, lead["id"]),
    )
    conn.commit()
    return status


def verify_all(
    conn: sqlite3.Connection,
    limit: int = 500,
    *,
    settings: Settings | None = None,
    search_client: httpx.Client | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for lead in conn.execute("SELECT * FROM leads WHERE status = 'new' LIMIT ?", (limit,)).fetchall():
        st = verify_lead(conn, lead, settings=settings, search_client=search_client)
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
