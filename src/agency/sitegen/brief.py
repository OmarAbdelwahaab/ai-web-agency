"""Generate structured facts (facts.json) and design briefs (brief.md) for custom agent-built sites."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from agency.config import Settings, get_settings
from agency.db import get_enrichment, get_lead
from agency.enrichment.images import LocalAssetSource
from agency.sitegen.schema import clean_address, parse_hours, pretty_us, slugify, theme_for_category


def build_facts_dict(
    conn: sqlite3.Connection,
    lead_id: int,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Compile strict, validated business facts and enrichment data for a lead."""
    s = settings or get_settings()
    lead = get_lead(conn, lead_id)
    if lead is None:
        raise ValueError(f"Lead #{lead_id} not found in database")

    enrichment_row = get_enrichment(conn, lead_id)
    name = lead["name"]
    slug = slugify(name, lead["id"])
    theme = theme_for_category(lead["category"])
    addr_clean = clean_address(lead["address"], name)
    phone_clean = pretty_us(lead["phone_e164"]) if lead["phone_e164"] else lead["phone_e164"]

    # Parse opening hours
    hours_rows = parse_hours(lead["hours_json"])
    formatted_hours = [{"day": h.day, "text": h.text} for h in hours_rows]

    # Enrichment reviews
    reviews: list[dict[str, Any]] = []
    if enrichment_row and enrichment_row["top_reviews_json"]:
        try:
            reviews = json.loads(enrichment_row["top_reviews_json"])
        except Exception:
            pass

    # Categories
    categories: list[str] = []
    if enrichment_row and enrichment_row["categories_json"]:
        try:
            categories = json.loads(enrichment_row["categories_json"])
        except Exception:
            pass
    if not categories and lead["category"]:
        categories = [lead["category"]]

    # Owner notes
    owner_notes = (
        enrichment_row["owner_notes"]
        if (enrichment_row and enrichment_row["owner_notes"])
        else (lead["notes"] or "")
    )

    # Local assets
    local_images = LocalAssetSource(s.assets_dir).get_images(lead_id)
    photos_list = [
        {"path": img.url_or_path, "caption": img.caption, "source_type": img.source_type}
        for img in local_images
    ]

    return {
        "lead_id": lead_id,
        "slug": slug,
        "business_name": name,
        "business_type": lead["category"] or "local business",
        "category": lead["category"] or "local business",
        "categories": categories,
        "theme": theme,
        "phone": phone_clean,
        "phone_e164": lead["phone_e164"],
        "address": addr_clean,
        "city": lead["city"],
        "state": lead["state"],
        "maps_query": f'{name} {addr_clean or ""}'.strip(),
        "maps_url": f"https://maps.google.com/?q={name}+{addr_clean or ''}".replace(" ", "+"),
        "hours": formatted_hours,
        "rating": enrichment_row["rating"] if enrichment_row else lead["rating"],
        "review_count": enrichment_row["review_count"] if enrichment_row else lead["rating_count"],
        "top_reviews": reviews,
        "photos": photos_list,
        "images": photos_list,  # alias for backwards compatibility
        "owner_notes": owner_notes.strip() if owner_notes else "",
        "data_richness": enrichment_row["data_richness"] if enrichment_row else 0.0,
        "agency_credit": f"Website by {s.agency_name}",
        "website_confirmed_none": (
            bool(enrichment_row["website_confirmed_none"])
            if enrichment_row
            else (not bool(lead["website_uri"]))
        ),
        "design_constraints": [
            "Single self-contained HTML page with inline CSS and zero external JS/CSS frameworks.",
            "Mobile-first: perfect layout on 375px phone screen without horizontal scrolling.",
            "Primary click-to-call button prominently linked to tel:<phone_e164>.",
            "Accurate directions link to Google Maps.",
            "Opening hours table displaying only verified hours (never guess or invent).",
            "Zero invented claims: no fake awards, no fabricated testimonials, no unverified menu items.",
        ],
    }


def build_brief_dict(
    conn: sqlite3.Connection,
    lead_id: int,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Compile brief dictionary (delegates to build_facts_dict)."""
    return build_facts_dict(conn, lead_id, settings=settings)


def render_brief_markdown(brief: dict[str, Any]) -> str:
    """Format facts, intent, and constraints into clean markdown with zero layout prescriptions."""
    b_type = brief.get("business_type") or brief.get("category") or "local business"
    lines = [
        f"# Design Brief: {brief['business_name']}",
        f"**Business Type:** {b_type} | **Slug:** `{brief['slug']}` | **Data Richness:** {brief.get('data_richness', 0.0):.2f}",
        "",
        "## 1. Design Intent",
        f"Design a bespoke, high-converting, single-page static website for **{brief['business_name']}**.",
        f"The visual tone, typography, and layout should authentically represent a quality local {b_type}.",
        "You have complete creative freedom over visual composition, component layout, color palette, and hierarchy.",
        "Do NOT follow a rigid template or repetitive section formula. Shape the structure to highlight the verified strengths and unique context of this business.",
        "",
        "## 2. Verified Business Facts",
        f"- **Business Name:** {brief['business_name']}",
        f"- **Phone (Display):** {brief['phone']}",
        f"- **Phone (Call CTA Link):** `tel:{brief['phone_e164']}`",
        f"- **Address:** {brief['address'] or 'Local Service / Unlisted'}",
        f"- **City / State:** {brief['city'] or 'N/A'}, {brief['state'] or ''}",
        f"- **Directions Link:** [{brief['maps_query']}]({brief['maps_url']})",
        f"- **Agency Credit:** {brief['agency_credit']}",
        "",
        "## 3. Opening Hours",
    ]

    if brief.get("hours"):
        lines.append("| Day | Hours |")
        lines.append("| --- | --- |")
        for h in brief["hours"]:
            lines.append(f"| {h['day']} | {h['text']} |")
    else:
        lines.append("*No verified opening hours listed. Prompt customers to call for current schedule.*")

    lines.extend([
        "",
        "## 4. Owner Call Notes & Context",
    ])
    if brief.get("owner_notes"):
        lines.append(f"> {brief['owner_notes']}")
    else:
        lines.append("*No owner call notes recorded.*")

    lines.extend([
        "",
        "## 5. Verified Customer Reviews",
        f"**Rating:** {brief.get('rating') or 'N/A'} ({brief.get('review_count') or 0} reviews)",
    ])
    reviews = brief.get("top_reviews") or []
    if reviews:
        for r in reviews:
            author = r.get("author_name") or r.get("author") or "Verified Customer"
            stars = f" ({r['rating']}★)" if r.get("rating") else ""
            lines.append(f"- \"{r.get('text', '').strip()}\" — *{author}{stars}*")
    else:
        lines.append("*No verified review snippets available.*")

    lines.extend([
        "",
        "## 6. Photo & Image Assets",
    ])
    photos = brief.get("photos") or brief.get("images") or []
    if photos:
        for img in photos:
            lines.append(f"- **{img['caption']}**: `{img['path']}` (Source: {img['source_type']})")
    else:
        lines.append("*No local owner images provided. Rely on deliberate typography, layout, icons, and color palette.*")

    lines.extend([
        "",
        "## 7. Hard Constraints (Non-Negotiable)",
    ])
    for c in brief.get("design_constraints", []):
        lines.append(f"- {c}")

    return "\n".join(lines) + "\n"


def generate_brief(
    conn: sqlite3.Connection,
    lead_id: int,
    output_dir: Path | str | None = None,
    settings: Settings | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    """Generate and write output/<slug>/facts.json, brief.json, and brief.md."""
    s = settings or get_settings()
    out_base = Path(output_dir) if output_dir else s.output_dir

    facts_dict = build_facts_dict(conn, lead_id, settings=s)
    slug = facts_dict["slug"]
    slug_dir = out_base / slug
    slug_dir.mkdir(parents=True, exist_ok=True)

    facts_path = slug_dir / "facts.json"
    brief_json_path = slug_dir / "brief.json"
    md_path = slug_dir / "brief.md"

    facts_content = json.dumps(facts_dict, indent=2)
    facts_path.write_text(facts_content, encoding="utf-8")
    brief_json_path.write_text(facts_content, encoding="utf-8")
    md_path.write_text(render_brief_markdown(facts_dict), encoding="utf-8")

    return facts_dict, brief_json_path, md_path
