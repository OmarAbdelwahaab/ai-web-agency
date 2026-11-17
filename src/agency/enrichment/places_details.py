"""Google Places API (New) details fetcher. Official API only; no Maps scraping.

Policy & Terms of Service Compliance:
- Place IDs (id) may be stored indefinitely.
- Place Details content (reviews, ratings) may be temporarily cached up to 30 days.
- User reviews must preserve author attribution and must not be altered.
- Photo binaries must NEVER be scraped or stored permanently without license. We store
  photo reference IDs and photographer author attributions only, which can be retrieved
  or linked with full attribution at render time.
- Standard default for site rendering remains local owner-supplied photos.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from agency.config import Settings, get_settings
from agency.enrichment.models import PhotoReference, ReviewSnippet
from agency.retry import retry

log = logging.getLogger(__name__)

DETAILS_BASE_URL = "https://places.googleapis.com/v1"
FIELDS = ",".join(
    (
        "id",
        "displayName",
        "formattedAddress",
        "rating",
        "userRatingCount",
        "reviews",
        "photos",
        "types",
        "primaryType",
        "regularOpeningHours",
        "nationalPhoneNumber",
        "websiteUri",
    )
)

GENERIC_TYPES = {
    "point_of_interest",
    "establishment",
}


def _clean_types(types: list[str] | None, primary_type: str | None = None) -> list[str]:
    cleaned: list[str] = []
    if primary_type and primary_type not in GENERIC_TYPES:
        cleaned.append(primary_type.replace("_", " "))
    for t in types or []:
        if t not in GENERIC_TYPES and t != primary_type:
            cleaned.append(t.replace("_", " "))
    return cleaned


@retry(max_retries=3, base_delay=0.5, retryable_exceptions=(httpx.RequestError, httpx.HTTPStatusError))
def _fetch_details_raw(
    place_id: str,
    api_key: str,
    client: httpx.Client,
) -> dict[str, Any]:
    # Place ID might already be formatted as "places/ChIJ..." or raw "ChIJ..."
    resource_path = place_id if place_id.startswith("places/") else f"places/{place_id}"
    url = f"{DETAILS_BASE_URL}/{resource_path}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELDS,
    }
    resp = client.get(url, headers=headers)
    if resp.status_code == 404:
        log.warning("Place %s not found on Google Places API (404)", place_id)
        return {}
    resp.raise_for_status()
    return resp.json()


def fetch_place_details(
    place_id: str,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Fetch details for a Google Place ID via the official Places API (New).
    
    Logs estimated cost (~$0.025 Enterprise SKU with Atmosphere).
    """
    s = settings or get_settings()
    if not s.places_api_key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not set")

    if client is not None:
        raw = _fetch_details_raw(place_id, s.places_api_key, client)
    else:
        with httpx.Client(timeout=15.0) as c:
            raw = _fetch_details_raw(place_id, s.places_api_key, c)

    log.info(
        "Google Places details for '%s': 1 request made. Estimated cost: $0.025 (Enterprise/Atmosphere SKU)",
        place_id,
    )

    if not raw:
        return {}

    # Extract reviews with required author attribution
    reviews: list[ReviewSnippet] = []
    for r in raw.get("reviews", []):
        text_obj = r.get("text")
        text = text_obj.get("text", "") if isinstance(text_obj, dict) else str(text_obj or "")
        text = text.strip()
        if not text:
            continue
        # Truncate long reviews to concise snippet
        if len(text) > 250:
            text = text[:247].rstrip() + "..."
        author = r.get("authorAttribution", {})
        author_name = author.get("displayName") or "Verified Customer"
        reviews.append(
            ReviewSnippet(
                author_name=author_name,
                text=text,
                rating=float(r["rating"]) if "rating" in r else None,
                relative_publish_time=r.get("relativePublishTimeDescription"),
            )
        )

    # Extract photo references with mandatory author attribution (do NOT store photo binaries)
    photos: list[PhotoReference] = []
    for p in raw.get("photos", []):
        name = p.get("name")
        if not name:
            continue
        attributions = p.get("authorAttributions", [])
        author_name = attributions[0].get("displayName") if attributions else None
        author_uri = attributions[0].get("uri") if attributions else None
        photos.append(
            PhotoReference(
                name=name,
                author_name=author_name,
                author_uri=author_uri,
                width_px=p.get("widthPx"),
                height_px=p.get("heightPx"),
            )
        )

    categories = _clean_types(raw.get("types"), raw.get("primaryType"))
    website_uri = raw.get("websiteUri")

    return {
        "place_id": raw.get("id", place_id),
        "name": raw.get("displayName", {}).get("text"),
        "formatted_address": raw.get("formattedAddress"),
        "phone": raw.get("nationalPhoneNumber"),
        "rating": raw.get("rating"),
        "review_count": raw.get("userRatingCount"),
        "reviews": reviews,
        "photos": photos,
        "categories": categories,
        "website_uri": website_uri,
        "website_confirmed_none": not bool(website_uri),
        "raw_json": raw,
    }
