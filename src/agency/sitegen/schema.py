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


def _hours_rows(hours_json: str | None) -> list[HoursRow]:
    rows: list[HoursRow] = []
    try:
        items = json.loads(hours_json or "[]")
    except json.JSONDecodeError:
        return rows
    for item in items[:7]:
        if ":" in item:
            day, text = item.split(":", 1)
            rows.append(HoursRow(day=day.strip()[:20], text=text.strip()[:40]))
    return rows


def config_from_lead(lead: sqlite3.Row, *, credit: str | None = None) -> SiteConfig:
    """Deterministic base config using ONLY facts stored on the lead. No LLM needed."""
    city = lead["city"]
    return SiteConfig(
        slug=slugify(lead["name"], lead["id"]),
        business_name=lead["name"],
        theme=theme_for_category(lead["category"]),
        tagline=f"Serving {city}" if city else "Welcome",
        phone=pretty_us(lead["phone_e164"]),
        phone_e164=lead["phone_e164"],
        address=lead["address"],
        maps_query=f'{lead["name"]} {lead["address"] or ""}'.strip(),
        hours=_hours_rows(lead["hours_json"]),
        credit=credit,
    )
