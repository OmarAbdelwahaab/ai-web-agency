from __future__ import annotations

import json
import re
import sqlite3
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from agency.phone import pretty_us

Theme = Literal["food", "health", "trades", "retail"]


class HoursRow(BaseModel):
    day: str = Field(max_length=20)
    text: str = Field(max_length=40)


class Service(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=200)
    price: str | None = Field(default=None, max_length=30)


class SiteConfig(BaseModel):
    """Everything the template needs. The LLM never writes HTML; it only fills allowed text fields."""

    slug: str
    business_name: str = Field(min_length=2, max_length=80)
    theme: Theme = "retail"
    tagline: str = Field(max_length=120)
    about: str | None = Field(default=None, max_length=900)
    phone: str
    phone_e164: str
    email: str | None = None
    address: str | None = None
    maps_query: str | None = None
    hours: list[HoursRow] = Field(default_factory=list, max_length=7)
    services: list[Service] = Field(default_factory=list, max_length=12)
    cta_label: str = "Call now"
    credit: str | None = None
    used_fallback: bool = False

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,59}", v):
            raise ValueError("slug must be 3-60 chars of a-z, 0-9, dashes")
        return v


class AIText(BaseModel):
    """The only fields the LLM is allowed to produce."""

    tagline: str = Field(max_length=120)
    about: str | None = Field(default=None, max_length=900)
    services: list[Service] = Field(default_factory=list, max_length=12)


def slugify(name: str, suffix: str | int = "") -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:45] or "site"
    return f"{base}-{suffix}" if suffix != "" else base


_FOOD = ("restaurant", "cafe", "coffee", "bakery", "food", "pizza", "diner", "bistro")
_HEALTH = ("pharmacy", "clinic", "dental", "dentist", "health", "chiropract", "optic", "vet")
_TRADES = ("plumb", "electric", "hvac", "roof", "contractor", "repair", "locksmith", "landscap", "clean", "pest", "garage")


def theme_for_category(category: str | None) -> Theme:
    c = (category or "").lower()
    words = set(re.findall(r"[a-z]+", c))
    if words.intersection({"bar", "bars", "pub", "pubs"}) or any(any(w.startswith(k) for w in words) for k in _FOOD):
        return "food"
    if any(any(w.startswith(k) for w in words) for k in _HEALTH):
        return "health"
    if any(any(w.startswith(k) for w in words) for k in _TRADES):
        return "trades"
    return "retail"


DAY_MAP = {
    "mo": "Mon", "tu": "Tue", "we": "Wed", "th": "Thu", "fr": "Fri", "sa": "Sat", "su": "Sun",
    "mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun",
    "monday": "Monday", "tuesday": "Tuesday", "wednesday": "Wednesday", "thursday": "Thursday",
    "friday": "Friday", "saturday": "Saturday", "sunday": "Sunday",
    "ph": "Public Holidays",
}


def _fmt_day_token(d: str) -> str:
    return DAY_MAP.get(d.strip().lower(), d.strip().capitalize())


def _format_day_expression(d_raw: str) -> str | None:
    d = d_raw.strip()
    if not d:
        return None
    if d.lower() == "ph":
        return "Public Holidays"
    if "-" in d or "–" in d:
        sep = "-" if "-" in d else "–"
        parts = [p.strip() for p in d.split(sep, 1)]
        if len(parts) == 2 and all(p.lower() in DAY_MAP for p in parts if p):
            return f"{_fmt_day_token(parts[0])}–{_fmt_day_token(parts[1])}"
    if "," in d:
        parts = [p.strip() for p in d.split(",")]
        if parts and all(p.lower() in DAY_MAP for p in parts if p):
            return ", ".join(_fmt_day_token(p) for p in parts)
    if d.lower() in DAY_MAP:
        return _fmt_day_token(d)
    return None


def _format_time_expression(t_raw: str) -> str | None:
    t = t_raw.strip()
    if not t:
        return None
    low = t.lower()
    if low in ("off", "closed"):
        return "Closed"
    if low in ("open", "24h", "24 hours", "open 24 hours"):
        return "Open 24 hours"
    if t == "24/7":
        return "Open 24/7"
    # HH:MM-HH:MM or H:MM-H:MM (24h)
    m = re.match(r"^(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})$", t)
    if m:
        h1, m1, h2, m2 = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
        if 0 <= h1 <= 24 and 0 <= h2 <= 24:
            def to_12h(h: int, mm: str) -> str:
                period = "AM" if (h < 12 or h == 24) else "PM"
                h12 = h % 12
                if h12 == 0:
                    h12 = 12
                return f"{h12}:{mm} {period}"
            return f"{to_12h(h1, m1)} – {to_12h(h2, m2)}"
    # H-H (e.g. 8-5 or 9-5)
    m_simple = re.match(r"^(\d{1,2})\s*[-–]\s*(\d{1,2})$", t)
    if m_simple:
        h1, h2 = int(m_simple.group(1)), int(m_simple.group(2))
        def to_12h_simple(h: int) -> str:
            period = "PM" if (h <= 7 or (12 <= h < 24)) else "AM"
            h12 = h % 12
            if h12 == 0:
                h12 = 12
            return f"{h12}:00 {period}"
        return f"{to_12h_simple(h1)} – {to_12h_simple(h2)}"
    # Already formatted with AM/PM (e.g. '9:00 AM – 5:00 PM' or '9:00 AM - 5:00 PM')
    if re.search(r"\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)", t, re.IGNORECASE):
        norm = re.sub(r"\s*[-–]\s*", " – ", t)
        return norm
    return None


def _parse_single_hours_rule(rule: str) -> tuple[str, str] | None:
    rule = rule.strip()
    if not rule:
        return None
    if rule == "24/7":
        return ("Mon–Sun", "Open 24/7")
    # If colon-separated (Google-style, e.g. "Monday: 9:00 AM – 5:00 PM" or "Mon: 8-5")
    if ":" in rule:
        idx = rule.find(":")
        prefix = rule[:idx].strip()
        if not re.search(r"\d", prefix):
            day_str = _format_day_expression(prefix)
            time_str = _format_time_expression(rule[idx + 1:])
            if day_str and time_str:
                return (day_str, time_str)
    # OSM-style: day tokens followed by space and time/keyword
    m = re.match(r"^([A-Za-z,\-–]+)\s+(.*)$", rule)
    if m:
        day_str = _format_day_expression(m.group(1))
        time_str = _format_time_expression(m.group(2))
        if day_str and time_str:
            return (day_str, time_str)
    return None


def parse_hours(hours_raw: str | list[str] | None) -> list[HoursRow]:
    """Parse raw hours strings (OSM or Google format) into structured, readable HoursRows.
    Expands semicolon-separated rules, formats times to 12-hour AM/PM, and drops invalid garbage.
    """
    if not hours_raw:
        return []
    if isinstance(hours_raw, str):
        try:
            items = json.loads(hours_raw)
            if not isinstance(items, list):
                items = [hours_raw]
        except json.JSONDecodeError:
            items = [hours_raw]
    elif isinstance(hours_raw, list):
        items = hours_raw
    else:
        return []

    rows: list[HoursRow] = []
    for item in items:
        if not isinstance(item, str):
            continue
        sub_rules = [r.strip() for r in item.split(";") if r.strip()]
        for sub in sub_rules:
            parsed = _parse_single_hours_rule(sub)
            if parsed:
                day, text = parsed
                rows.append(HoursRow(day=day[:20], text=text[:40]))
    return rows[:7]


_hours_rows = parse_hours  # backward compatibility


def clean_address(addr: str | None, business_name: str | None = None) -> str | None:
    """Clean address string: remove country suffix, strip leading duplicate business name, format cleanly."""
    if not addr:
        return None
    s = addr.strip()
    if business_name:
        b_clean = business_name.strip()
        if s.lower().startswith(b_clean.lower() + ","):
            s = s[len(b_clean) + 1:].strip()
        elif s.lower().startswith(b_clean.lower()):
            s = s[len(b_clean):].lstrip(",").strip()

    # Remove country suffix at the end (e.g. ', United States of America', ', United States', ', USA', ', US')
    s = re.sub(r",?\s*(?:United States of America|United States|USA|US)\.?\s*$", "", s, flags=re.IGNORECASE)
    s = s.rstrip(",").strip()
    return s or None


def config_from_lead(lead: sqlite3.Row, *, credit: str | None = None) -> SiteConfig:
    """Deterministic base config using ONLY facts stored on the lead. No LLM needed."""
    city = lead["city"]
    name = lead["name"]
    category = (lead["category"] or "").lower()
    theme = theme_for_category(lead["category"])

    tagline = f"Serving {city}" if city else "Welcome"

    # Honest, category-specific fallback about text
    if theme == "food":
        about = f"{name} is a local {category or 'restaurant'} serving {city or 'the community'} with fresh food and drinks."
    elif theme == "health":
        about = f"{name} provides professional {category or 'healthcare'} services to patients in {city or 'the community'}."
    elif theme == "trades":
        about = f"{name} offers dependable {category or 'service'} solutions across {city or 'the local area'}."
    else:
        about = f"{name} is a local business dedicated to serving {city or 'the community'}."

    addr_clean = clean_address(lead["address"], name)

    return SiteConfig(
        slug=slugify(name, lead["id"]),
        business_name=name,
        theme=theme,
        tagline=tagline,
        about=about,
        phone=pretty_us(lead["phone_e164"]),
        phone_e164=lead["phone_e164"],
        address=addr_clean,
        maps_query=f'{name} {addr_clean or ""}'.strip(),
        hours=parse_hours(lead["hours_json"]),
        credit=credit,
        used_fallback=True,
    )
