"""Unit tests for lead enrichment, Places details, image adapters, and richness scoring."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from agency.config import Settings
from agency.db import (
    add_owner_note,
    connect,
    get_enrichment,
    get_lead,
    init_db,
    insert_lead,
    save_enrichment,
)
from agency.enrichment import (
    CompositeImageSource,
    ImageInfo,
    LeadEnrichment,
    LocalAssetSource,
    PhotoReference,
    ReviewSnippet,
    StockImageSource,
    compute_data_richness,
    enrich_lead,
    fetch_place_details,
    is_rich_lead,
    record_owner_note,
)


@pytest.fixture
def test_db(tmp_path: Path):
    db_file = tmp_path / "test_enrichment.db"
    conn = connect(db_file)
    init_db(conn)
    return conn


@pytest.fixture
def sample_lead_id(test_db):
    lid = insert_lead(
        test_db,
        source="places",
        source_id="places/ChIJ12345678",
        name="Thistle Cafe",
        category="cafe",
        phone_e164="+15125550100",
        address="123 Main St, Austin, TX 78701",
        city="Austin",
        state="TX",
        lat=30.2672,
        lng=-97.7431,
        hours_json=json.dumps(["Mo-Fr 07:30-14:30; Sa 08:00-12:00"]),
        rating=4.5,
        rating_count=12,
    )
    assert lid is not None
    return lid


def test_db_enrichment_crud(test_db, sample_lead_id):
    # Initial save
    eid = save_enrichment(
        test_db,
        lead_id=sample_lead_id,
        rating=4.8,
        review_count=35,
        top_reviews_json=json.dumps([{"author_name": "Alice", "text": "Great latte", "rating": 5.0}]),
        categories_json=json.dumps(["coffee shop", "bakery"]),
        photo_refs_json=json.dumps([{"name": "places/foo/photos/bar", "author_name": "Bob"}]),
        website_confirmed_none=True,
        owner_notes="Family owned since 2015",
        data_richness=0.85,
    )
    assert eid is not None

    row = get_enrichment(test_db, sample_lead_id)
    assert row is not None
    assert row["lead_id"] == sample_lead_id
    assert row["rating"] == 4.8
    assert row["review_count"] == 35
    assert row["website_confirmed_none"] == 1
    assert row["data_richness"] == 0.85
    assert "Alice" in row["top_reviews_json"]

    # Add owner note
    add_owner_note(test_db, sample_lead_id, "Best seller is cold brew")
    row_updated = get_enrichment(test_db, sample_lead_id)
    assert "Family owned since 2015" in row_updated["owner_notes"]
    assert "Best seller is cold brew" in row_updated["owner_notes"]

    # Verify leads table also synced
    lead_row = get_lead(test_db, sample_lead_id)
    assert "Best seller is cold brew" in lead_row["notes"]


def test_local_asset_source(tmp_path: Path):
    assets_dir = tmp_path / "assets"
    lead_dir = assets_dir / "42"
    lead_dir.mkdir(parents=True)

    (lead_dir / "interior.jpg").write_bytes(b"image-data")
    (lead_dir / "latte_art.png").write_bytes(b"image-data")
    (lead_dir / "notes.txt").write_text("not an image")

    source = LocalAssetSource(assets_dir)
    images = source.get_images(42)

    assert len(images) == 2
    captions = [img.caption for img in images]
    assert "Interior" in captions
    assert "Latte Art" in captions
    assert all(img.source_type == "local" for img in images)

    # Missing lead folder
    assert source.get_images(999) == []


def test_stock_image_source_safe_default():
    source = StockImageSource()
    assert source.get_images(1, category="cafe") == []

    composite = CompositeImageSource([source])
    assert composite.get_images(1) == []


def test_data_richness_scoring(test_db, sample_lead_id):
    lead = get_lead(test_db, sample_lead_id)

    # Empty enrichment
    empty_enrich = LeadEnrichment(lead_id=sample_lead_id)
    score_empty = compute_data_richness(empty_enrich, lead=None, local_image_count=0)
    assert score_empty == 0.0
    assert not is_rich_lead(score_empty, threshold=0.6)

    # Lead with hours and category from DB
    score_basic = compute_data_richness(empty_enrich, lead=lead, local_image_count=0)
    # hours (0.20) + category (0.15) = 0.35
    assert score_basic == 0.35

    # Rich enrichment
    rich_enrich = LeadEnrichment(
        lead_id=sample_lead_id,
        rating=4.9,
        review_count=50,
        top_reviews=[
            ReviewSnippet(author_name="A", text="Love this place!"),
            ReviewSnippet(author_name="B", text="Amazing pastry selection."),
        ],
        categories=["coffee shop", "bakery"],
        photo_refs=[
            PhotoReference(name="places/1/photos/a"),
            PhotoReference(name="places/1/photos/b"),
        ],
        owner_notes="Signature cinnamon rolls sell out by 10am.",
    )
    score_rich = compute_data_richness(rich_enrich, lead=lead, local_image_count=2)
    # photos(0.25) + reviews(0.25) + hours(0.20) + categories(0.15) + notes(0.15) = 1.0
    assert score_rich == 1.0
    assert is_rich_lead(score_rich, threshold=0.6)


def test_fetch_place_details_mock():
    mock_payload = {
        "id": "places/ChIJtest123",
        "displayName": {"text": "Austin Coffee Works"},
        "formattedAddress": "500 Congress Ave, Austin, TX 78701",
        "nationalPhoneNumber": "(512) 555-9876",
        "rating": 4.7,
        "userRatingCount": 88,
        "types": ["cafe", "point_of_interest", "establishment"],
        "primaryType": "coffee_shop",
        "websiteUri": None,
        "reviews": [
            {
                "authorAttribution": {"displayName": "Sarah K."},
                "text": {"text": "Best cold brew downtown!"},
                "rating": 5,
                "relativePublishTimeDescription": "a month ago",
            }
        ],
        "photos": [
            {
                "name": "places/ChIJtest123/photos/photoXYZ",
                "widthPx": 1200,
                "heightPx": 800,
                "authorAttributions": [{"displayName": "Photographer Dan", "uri": "https://maps.google.com/dan"}],
            }
        ],
    }

    settings = Settings(places_api_key="mock_key")

    def mock_handler(request: httpx.Request):
        assert request.headers["X-Goog-Api-Key"] == "mock_key"
        assert "places/ChIJtest123" in str(request.url)
        return httpx.Response(200, json=mock_payload)

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    details = fetch_place_details("ChIJtest123", settings=settings, client=client)

    assert details["name"] == "Austin Coffee Works"
    assert details["rating"] == 4.7
    assert details["website_confirmed_none"] is True
    assert len(details["reviews"]) == 1
    assert details["reviews"][0].author_name == "Sarah K."
    assert details["reviews"][0].text == "Best cold brew downtown!"
    assert len(details["photos"]) == 1
    assert details["photos"][0].author_name == "Photographer Dan"
    assert "coffee shop" in details["categories"]
    assert "cafe" in details["categories"]
    assert "point_of_interest" not in details["categories"]


def test_enrich_lead_service(test_db, sample_lead_id, tmp_path: Path):
    mock_payload = {
        "id": "places/ChIJ12345678",
        "displayName": {"text": "Thistle Cafe"},
        "rating": 4.9,
        "userRatingCount": 42,
        "types": ["cafe"],
        "primaryType": "cafe",
        "websiteUri": None,
        "reviews": [
            {"authorAttribution": {"displayName": "John"}, "text": {"text": "Great spot!"}, "rating": 5},
            {"authorAttribution": {"displayName": "Mary"}, "text": {"text": "Friendly staff!"}, "rating": 5},
        ],
        "photos": [{"name": "places/p1"}],
    }

    settings = Settings(places_api_key="mock_key", assets_dir=tmp_path / "assets")

    def mock_handler(request: httpx.Request):
        return httpx.Response(200, json=mock_payload)

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))

    enrichment = enrich_lead(test_db, sample_lead_id, settings=settings, client=client)
    assert enrichment.rating == 4.9
    assert enrichment.review_count == 42
    assert len(enrichment.top_reviews) == 2
    assert enrichment.website_confirmed_none is True
    assert enrichment.data_richness > 0.5

    # Check persistence
    row = get_enrichment(test_db, sample_lead_id)
    assert row is not None
    assert row["rating"] == 4.9

    # Record owner note and check richness update
    updated = record_owner_note(test_db, sample_lead_id, "Known for house roasted beans", settings=settings)
    assert "house roasted beans" in updated.owner_notes
    assert updated.data_richness >= enrichment.data_richness


def test_cli_enrich_and_note_lead(test_db, sample_lead_id, monkeypatch, capsys):
    from agency import cli

    monkeypatch.setattr(cli, "_conn", lambda: test_db)

    # Test note-lead with positional note
    cli.main(["note-lead", str(sample_lead_id), "Specialty: Gluten free pastries"])
    out = capsys.readouterr().out
    assert "Recorded owner note for Lead #" in out
    assert "Gluten free pastries" in out

    # Test enrich
    cli.main(["enrich", str(sample_lead_id)])
    out = capsys.readouterr().out
    assert "Enriched Lead #" in out
    assert "Thistle Cafe" in out
    assert "Data richness score:" in out

    # Test note-lead with --notes flag
    cli.main(["note-lead", str(sample_lead_id), "--notes", "Owner name: Alice"])
    out = capsys.readouterr().out
    assert "Owner name: Alice" in out

