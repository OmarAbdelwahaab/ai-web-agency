import json
import sqlite3
from unittest.mock import MagicMock, patch

import httpx
import pytest

from agency.config import Settings
from agency.db import connect, init_db, insert_lead
from agency.leads import geoapify


@pytest.fixture()
def db_conn():
    conn = connect(":memory:")
    init_db(conn)
    return conn


def test_geocode_city_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [{"lat": 30.2672, "lon": -97.7431, "state_code": "TX"}]
    }
    client = MagicMock()
    client.get.return_value = mock_resp

    lat, lon, state = geoapify.geocode_city("Austin, TX", "test_key", client=client)
    assert lat == 30.2672
    assert lon == -97.7431
    assert state == "TX"


def test_geocode_city_not_found():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": []}
    client = MagicMock()
    client.get.return_value = mock_resp

    with pytest.raises(ValueError, match="Could not geocode city"):
        geoapify.geocode_city("InvalidCityName123", "test_key", client=client)


def test_search_missing_key():
    s = Settings(geoapify_api_key="")
    with pytest.raises(RuntimeError, match="GEOAPIFY_API_KEY is not set"):
        geoapify.search("restaurant", "Austin, TX", settings=s)


def test_search_success_with_mock():
    s = Settings(geoapify_api_key="mock_key")
    mock_geocode_resp = MagicMock()
    mock_geocode_resp.status_code = 200
    mock_geocode_resp.json.return_value = {
        "results": [{"lat": 30.2672, "lon": -97.7431, "state_code": "TX"}]
    }

    mock_places_resp = MagicMock()
    mock_places_resp.status_code = 200
    mock_places_resp.json.return_value = {
        "features": [
            {
                "properties": {
                    "place_id": "p1",
                    "name": "Bella Italia",
                    "contact": {"phone": "+15125550111"},
                    "website": None,
                    "city": "Austin",
                    "state_code": "TX",
                }
            },
            {
                "properties": {
                    "place_id": "p2",
                    "name": "Has Website Cafe",
                    "contact": {"phone": "+15125550222"},
                    "website": "https://haswebsite.com",
                }
            },
        ]
    }

    client = MagicMock()
    client.get.side_effect = [mock_geocode_resp, mock_places_resp]

    results = geoapify.search("restaurant", "Austin, TX", settings=s, client=client)
    assert len(results) == 2
    assert results[0]["name"] == "Bella Italia"
    assert results[1]["name"] == "Has Website Cafe"


def test_save_places_filters_and_dedupes(db_conn):
    # Pre-existing phone in database
    insert_lead(
        db_conn,
        source="manual",
        source_id="m1",
        name="Existing Shop",
        phone_e164="+15125550999",
        category="retail",
    )

    places = [
        # Candidate 1: valid phone, no website -> should be saved
        {
            "place_id": "geo_1",
            "name": "Austin Master Plumber",
            "contact": {"phone": "+1 (512) 555-0144"},
            "website": None,
            "city": "Austin",
            "state_code": "TX",
            "lat": 30.26,
            "lon": -97.74,
            "opening_hours": "Mo-Fr 08:00-17:00",
        },
        # Candidate 2: has website -> should be skipped
        {
            "place_id": "geo_2",
            "name": "Big Firm Plumbing",
            "contact": {"phone": "+1 (512) 555-0155"},
            "website": "https://bigfirm.com",
            "city": "Austin",
            "state_code": "TX",
        },
        # Candidate 3: no phone -> should be skipped
        {
            "place_id": "geo_3",
            "name": "Unknown Phone Locksmith",
            "website": None,
        },
        # Candidate 4: duplicate phone with existing -> should be skipped
        {
            "place_id": "geo_4",
            "name": "Duplicate Phone Plumber",
            "contact": {"phone": "+15125550999"},
            "website": None,
        },
    ]

    saved_count = geoapify.save(db_conn, places, category="plumber")
    assert saved_count == 1

    row = db_conn.execute("SELECT * FROM leads WHERE source = 'geoapify'").fetchone()
    assert row is not None
    assert row["name"] == "Austin Master Plumber"
    assert row["phone_e164"] == "+15125550144"
    assert row["category"] == "plumber"
    assert row["status"] == "new"
    assert "08:00-17:00" in row["hours_json"]
