"""Lead enrichment package for deep local business context and assets."""
from __future__ import annotations

from agency.enrichment.images import CompositeImageSource, ImageSourceAdapter, LocalAssetSource, StockImageSource
from agency.enrichment.models import ImageInfo, LeadEnrichment, PhotoReference, ReviewSnippet
from agency.enrichment.places_details import fetch_place_details
from agency.enrichment.score import compute_data_richness, is_rich_lead
from agency.enrichment.service import enrich_lead, record_owner_note

__all__ = [
    "CompositeImageSource",
    "ImageInfo",
    "ImageSourceAdapter",
    "LeadEnrichment",
    "LocalAssetSource",
    "PhotoReference",
    "ReviewSnippet",
    "StockImageSource",
    "compute_data_richness",
    "enrich_lead",
    "fetch_place_details",
    "is_rich_lead",
    "record_owner_note",
]
