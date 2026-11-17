"""Pydantic data models for enriched lead details, reviews, and photos."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ReviewSnippet(BaseModel):
    """Short customer review snippet with attribution."""
    author_name: str
    text: str
    rating: float | None = None
    relative_publish_time: str | None = None


class PhotoReference(BaseModel):
    """Google Places photo reference with required photographer attribution."""
    name: str  # e.g., places/ChIJ.../photos/...
    author_name: str | None = None
    author_uri: str | None = None
    width_px: int | None = None
    height_px: int | None = None


class ImageInfo(BaseModel):
    """Concrete image asset ready for static site rendering."""
    url_or_path: str
    caption: str | None = None
    source_type: str = "local"  # "local", "stock", "google_ref"
    attribution: str | None = None


class LeadEnrichment(BaseModel):
    """Aggregated enrichment data for a lead."""
    lead_id: int
    rating: float | None = None
    review_count: int | None = None
    top_reviews: list[ReviewSnippet] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    photo_refs: list[PhotoReference] = Field(default_factory=list)
    website_confirmed_none: bool = True
    owner_notes: str | None = None
    data_richness: float = 0.0
    raw_json: dict[str, Any] | None = None
