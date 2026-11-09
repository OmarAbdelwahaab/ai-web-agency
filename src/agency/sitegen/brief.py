"""Generate structured design briefs (brief.json and brief.md) for custom agent-built sites."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from agency.config import Settings, get_settings
from agency.db import get_enrichment, get_lead
from agency.enrichment.images import LocalAssetSource
from agency.sitegen.schema import clean_address, parse_hours, pretty_us, slugify, theme_for_category

CATEGORY_SUGGESTIONS = {
    "food": {
        "recommended_sections": [
            "Hero with immediate Call / Order CTA and vibe statement",
            "About & Story (neighborhood history, family recipe focus if in notes)",
            "Specialties & Menu Highlights (only authentic items from notes/reviews)",
            "Opening Hours Table (cleanly formatted, clear open/closed status)",
            "Location & Directions Link with Google Maps query",
            "Customer Testimonials (attributed review snippets)",
        ],
        "tone": "Warm, inviting, appetizing, rooted in community and neighborhood hospitality.",
        "color_palette_advice": "Rich terracotta, deep olive, warm cream, roasted coffee tones, or bakery gold. Avoid sterile grays.",
    },
    "trades": {
        "recommended_sections": [
            "Urgent Call CTA Hero with prominent click-to-call button and service area tag",
            "Services Grid (clear breakdown of core repairs, installations, and emergency help)",
            "Service Area Coverage (cities and communities served)",
            "Reliability & Direct Contact (honest years, owner on site, upfront pricing policy)",
            "Hours & Emergency Availability",
            "Customer Reviews & Peace of Mind",
        ],
        "tone": "Direct, dependable, capable, honest, no fluff.",
        "color_palette_advice": "High-contrast slate, deep navy, safety amber or bronze accent. Clean, rugged, and legible.",
    },
    "health": {
        "recommended_sections": [
            "Comforting Care Hero with primary phone contact and location",
            "Practice Philosophy & Patient Comfort",
            "Specialized Services & Procedures Offered",
            "Attributed Patient Experiences & Reviews",
            "Office Hours & Walk-in / Appointment Guidance",
            "Directions & Parking info",
        ],
        "tone": "Reassuring, professional, empathetic, transparent, calming.",
        "color_palette_advice": "Soft sage, warm teal, crisp ivory, comforting stone. Gentle contrast, never harsh.",
    },
    "retail": {
        "recommended_sections": [
            "Storefront Welcome Hero with visit CTA and shop hours",
            "Featured Collections & Specialty Inventory",
            "About the Shop & Local Roots",
            "Location, Parking & Map Directions",
            "Customer Reviews & Recommendations",
            "Contact Phone & Quick Questions",
        ],
        "tone": "Curated, friendly, helpful, passionate about local craftsmanship or selection.",
        "color_palette_advice": "Earthy neutrals, boutique emerald, espresso or muted brass.",
    },
}

DEFAULT_SUGGESTION = {
    "recommended_sections": [
        "Welcome Hero with primary Call-to-Action",
        "About the Business & Local Service",
        "Core Offerings & Specialties",
        "Hours of Operation",
        "Location & Directions",
        "Customer Reviews",
    ],
    "tone": "Professional, welcoming, straightforward local business.",
    "color_palette_advice": "High-contrast clean palette with intentional primary accent.",
}


def build_brief_dict(
    conn: sqlite3.Connection,
    lead_id: int,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Compile all real business facts, enrichment data, and constraints into a brief dictionary."""
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

    # Enrichment categories
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
    images_list = [
        {"path": img.url_or_path, "caption": img.caption, "source_type": img.source_type}
        for img in local_images
    ]

    suggestions = CATEGORY_SUGGESTIONS.get(theme, DEFAULT_SUGGESTION)

    return {
        "lead_id": lead_id,
        "slug": slug,
        "business_name": name,
        "theme": theme,
        "category": lead["category"] or "local business",
        "categories": categories,
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
        "owner_notes": owner_notes.strip() if owner_notes else "",
        "data_richness": enrichment_row["data_richness"] if enrichment_row else 0.0,
        "images": images_list,
        "agency_credit": f"Website by {s.agency_name}",
        "design_constraints": [
            "Single self-contained HTML page with inline CSS and zero external JS/CSS frameworks.",
            "Mobile-first: perfect layout on 375px phone screen without horizontal scrolling.",
            "Primary click-to-call button prominently linked to tel:<phone_e164>.",
            "Accurate directions link to Google Maps.",
            "Opening hours table displaying only verified hours (never guess or invent).",
            "Zero invented claims: no fake awards, no fabricated testimonials, no unverified menu items.",
        ],
        "category_suggestions": suggestions,
    }


def render_brief_markdown(brief: dict[str, Any]) -> str:
    """Format the brief dictionary into readable, actionable markdown for AI coding agents."""
    lines = [
        f"# Design Brief: {brief['business_name']}",
        f"**Slug:** `{brief['slug']}` | **Theme:** `{brief['theme']}` | **Category:** {brief['category']}",
        f"**Data Richness Score:** {brief['data_richness']:.2f}",
        "",
        "## 1. Verified Business Facts",
        f"- **Business Name:** {brief['business_name']}",
        f"- **Phone (Display):** {brief['phone']}",
        f"- **Phone (Tel Link):** `tel:{brief['phone_e164']}`",
        f"- **Address:** {brief['address'] or 'Local Service / Unlisted'}",
        f"- **City / State:** {brief['city'] or 'N/A'}, {brief['state'] or ''}",
        f"- **Directions Link:** [{brief['maps_query']}]({brief['maps_url']})",
        f"- **Agency Credit:** {brief['agency_credit']}",
        "",
        "## 2. Opening Hours",
    ]

    if brief["hours"]:
        lines.append("| Day | Hours |")
        lines.append("| --- | --- |")
        for h in brief["hours"]:
            lines.append(f"| {h['day']} | {h['text']} |")
    else:
        lines.append("*No verified opening hours listed. Prompt customer to call for current hours.*")

    lines.extend([
        "",
        "## 3. Owner Call Notes & Context",
    ])
    if brief["owner_notes"]:
        lines.append(f"> {brief['owner_notes']}")
    else:
        lines.append("*No owner call notes recorded.*")

    lines.extend([
        "",
        "## 4. Customer Reviews & Social Proof",
        f"**Rating:** {brief['rating'] or 'N/A'} ({brief['review_count'] or 0} reviews)",
    ])
    if brief["top_reviews"]:
        for r in brief["top_reviews"]:
            author = r.get("author_name") or r.get("author") or "Verified Customer"
            stars = f" ({r['rating']}★)" if r.get("rating") else ""
            lines.append(f"- \"{r.get('text', '').strip()}\" — *{author}{stars}*")
    else:
        lines.append("*No verified review snippets available.*")

    lines.extend([
        "",
        "## 5. Visual Assets & Images",
    ])
    if brief["images"]:
        for img in brief["images"]:
            lines.append(f"- **{img['caption']}**: `{img['path']}` (Source: {img['source_type']})")
    else:
        lines.append("*No local owner images provided. Rely on deliberate typography, layout, icons, and color palette.*")

    sug = brief.get("category_suggestions", {})
    lines.extend([
        "",
        "## 6. Design & Layout Direction",
        f"**Tone:** {sug.get('tone', '')}",
        f"**Palette Advice:** {sug.get('color_palette_advice', '')}",
        "",
        "**Recommended Structure:**",
    ])
    for sec in sug.get("recommended_sections", []):
        lines.append(f"- {sec}")

    lines.extend([
        "",
        "## 7. Hard Constraints (Non-Negotiable)",
    ])
    for c in brief["design_constraints"]:
        lines.append(f"- {c}")

    return "\n".join(lines) + "\n"


def generate_brief(
    conn: sqlite3.Connection,
    lead_id: int,
    output_dir: Path | str | None = None,
    settings: Settings | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    """Generate and write output/<slug>/brief.json and output/<slug>/brief.md."""
    s = settings or get_settings()
    out_base = Path(output_dir) if output_dir else s.output_dir

    brief_dict = build_brief_dict(conn, lead_id, settings=s)
    slug = brief_dict["slug"]
    slug_dir = out_base / slug
    slug_dir.mkdir(parents=True, exist_ok=True)

    json_path = slug_dir / "brief.json"
    md_path = slug_dir / "brief.md"

    json_path.write_text(json.dumps(brief_dict, indent=2), encoding="utf-8")
    md_path.write_text(render_brief_markdown(brief_dict), encoding="utf-8")

    return brief_dict, json_path, md_path
