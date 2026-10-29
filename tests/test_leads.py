import json
import sqlite3
from unittest.mock import MagicMock

import httpx
import pytest

from agency.config import Settings
from agency.db import connect, init_db, insert_lead
from agency.leads import osm, places, verify


@pytest.fixture()
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


# --- Places API Tests ---

def test_places_missing_api_key():
    settings = Settings(places_api_key="")
    with pytest.raises(RuntimeError, match="GOOGLE_PLACES_API_KEY is not set"):
        places.search("plumber in Austin", settings=settings)


def test_places_search_pagination_and_cost():
    mock_client = MagicMock()
    # Mock two pages of results
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.json.return_value = {
        "places": [{"id": f"p{i}", "displayName": {"text": f"Place {i}"}} for i in range(20)],
        "nextPageToken": "token_page_2",
    }
    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.json.return_value = {
        "places": [{"id": f"p{i}", "displayName": {"text": f"Place {i}"}} for i in range(20, 25)],
    }
    mock_client.post.side_effect = [resp1, resp2]

    settings = Settings(places_api_key="fake-key")
    results = places.search("plumber in Austin", limit=25, settings=settings, client=mock_client)
    assert len(results) == 25
    assert mock_client.post.call_count == 2


def test_places_save_and_dedupe(conn):
    # Insert an existing lead from another source with phone +15125550100
    insert_lead(conn, source="csv", source_id="csv_1", name="Old Shop", phone_e164="+15125550100")

    candidates = [
        # Candidate with duplicate phone -> should be skipped
        {
            "id": "place_dup",
            "businessStatus": "OPERATIONAL",
            "displayName": {"text": "Dup Shop"},
            "nationalPhoneNumber": "(512) 555-0100",
            "addressComponents": [{"types": ["locality"], "longText": "Austin"}, {"types": ["administrative_area_level_1"], "shortText": "TX"}],
            "location": {"latitude": 30.26, "longitude": -97.74},
        },
        # Candidate with new phone -> should be inserted
        {
            "id": "place_new",
            "businessStatus": "OPERATIONAL",
            "displayName": {"text": "New Shop"},
            "nationalPhoneNumber": "(512) 555-0199",
            "addressComponents": [{"types": ["locality"], "longText": "Austin"}, {"types": ["administrative_area_level_1"], "shortText": "TX"}],
            "location": {"latitude": 30.26, "longitude": -97.74},
        },
        # Closed business -> should be skipped
        {
            "id": "place_closed",
            "businessStatus": "CLOSED_PERMANENTLY",
            "nationalPhoneNumber": "(512) 555-0188",
        },
    ]

    saved = places.save(conn, candidates, category="plumber")
    assert saved == 1

    row = conn.execute("SELECT * FROM leads WHERE source_id = 'place_new'").fetchone()
    assert row is not None
    assert row["name"] == "New Shop"
    assert row["phone_e164"] == "+15125550199"


# --- OSM Tests ---

def test_osm_build_query():
    q = osm.build_query("plumber", "Austin")
    assert 'area["name"="Austin"]' in q
    assert 'nwr["craft"~"^(plumber)$"]' in q


def test_osm_search():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "elements": [
            {"type": "node", "id": 101, "tags": {"name": "Bob Plumbing", "phone": "+15125550122"}},
        ]
    }
    mock_client.post.return_value = mock_resp

    elements = osm.search("plumber", "Austin", client=mock_client)
    assert len(elements) == 1
    assert elements[0]["tags"]["name"] == "Bob Plumbing"


def test_osm_save_and_cross_source_dedupe(conn):
    # Existing lead from places with same phone
    insert_lead(conn, source="places", source_id="p123", name="Shop One", phone_e164="+15125550133")

    elements = [
        # Duplicate phone
        {"type": "node", "id": 201, "tags": {"name": "Shop One Duplicate", "phone": "(512) 555-0133"}, "lat": 30.2, "lon": -97.7},
        # New candidate
        {"type": "node", "id": 202, "tags": {"name": "Shop Two New", "contact:phone": "+15125550144"}, "lat": 30.2, "lon": -97.7},
        # Missing phone
        {"type": "node", "id": 203, "tags": {"name": "Shop Three No Phone"}, "lat": 30.2, "lon": -97.7},
    ]

    saved = osm.save(conn, elements, category="plumber", state="TX")
    assert saved == 1

    row = conn.execute("SELECT * FROM leads WHERE source_id = 'node/202'").fetchone()
    assert row is not None
    assert row["name"] == "Shop Two New"
    assert row["phone_e164"] == "+15125550144"


# --- Verify & Web Presence Tests ---

def test_timezone_for():
    # Austin, TX coordinates
    tz = verify.timezone_for(30.2672, -97.7431)
    assert tz == "America/Chicago"
    # None coordinates
    assert verify.timezone_for(None, -97.7431) is None


@pytest.mark.parametrize("uri,expected", [
    (None, "none"),
    ("", "none"),
    ("https://www.facebook.com/austinbakery", "social"),
    ("https://instagram.com/austinbakery", "social"),
    ("https://yelp.com/biz/austinbakery", "social"),
    ("https://austinbakery.com", "real"),
    ("http://myshop.net/home", "real"),
])
def test_classify_website(uri, expected):
    assert verify.classify_website(uri) == expected


def test_check_web_presence_filters_aggregators():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Search returns Yelp, BBB, and YellowPages
    mock_resp.json.return_value = {
        "items": [
            {"link": "https://www.yelp.com/biz/sample-plumbing-austin"},
            {"link": "https://www.bbb.org/us/tx/austin/profile/sample-plumbing"},
            {"link": "https://www.yellowpages.com/austin-tx/mip/sample-plumbing"},
        ]
    }
    mock_client.get.return_value = mock_resp

    site = verify.check_web_presence("Sample Plumbing", "Austin", "TX", api_key="fake", client=mock_client)
    assert site is None  # no real website found among aggregators


def test_check_web_presence_finds_real_site():
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Search returns Yelp then a real business domain
    mock_resp.json.return_value = {
        "items": [
            {"link": "https://www.yelp.com/biz/sample-plumbing-austin"},
            {"link": "https://www.sampleplumbingaustin.com"},
        ]
    }
    mock_client.get.return_value = mock_resp

    site = verify.check_web_presence("Sample Plumbing", "Austin", "TX", api_key="fake", client=mock_client)
    assert site == "https://www.sampleplumbingaustin.com"


def test_verify_lead_outcomes(conn):
    # 1. Invalid phone
    lid1 = insert_lead(conn, source="t", source_id="1", name="Bad Phone", phone_e164="123", lat=30.2, lng=-97.7)
    lead1 = conn.execute("SELECT * FROM leads WHERE id = ?", (lid1,)).fetchone()
    assert verify.verify_lead(conn, lead1) == "disqualified"

    # 2. Missing coordinates
    lid2 = insert_lead(conn, source="t", source_id="2", name="No Coord", phone_e164="+15125550100")
    lead2 = conn.execute("SELECT * FROM leads WHERE id = ?", (lid2,)).fetchone()
    assert verify.verify_lead(conn, lead2) == "disqualified"

    # 3. Has real website
    lid3 = insert_lead(conn, source="t", source_id="3", name="Has Site", phone_e164="+15125550100", lat=30.2, lng=-97.7, website_uri="https://hassite.com")
    lead3 = conn.execute("SELECT * FROM leads WHERE id = ?", (lid3,)).fetchone()
    assert verify.verify_lead(conn, lead3) == "disqualified"

    # 4. Social only website -> verified
    lid4 = insert_lead(conn, source="t", source_id="4", name="Social Only", phone_e164="+15125550100", lat=30.2, lng=-97.7, website_uri="https://facebook.com/socialonly")
    lead4 = conn.execute("SELECT * FROM leads WHERE id = ?", (lid4,)).fetchone()
    assert verify.verify_lead(conn, lead4) == "verified"

    # 5. Search API finds website -> disqualified
    mock_search = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": [{"link": "https://discovered-site.com"}]}
    mock_search.get.return_value = mock_resp

    lid5 = insert_lead(conn, source="t", source_id="5", name="Secret Site", phone_e164="+15125550155", lat=30.2, lng=-97.7)
    lead5 = conn.execute("SELECT * FROM leads WHERE id = ?", (lid5,)).fetchone()
    settings = Settings(search_api_key="key123")
    assert verify.verify_lead(conn, lead5, settings=settings, search_client=mock_search) == "disqualified"

    updated = conn.execute("SELECT * FROM leads WHERE id = ?", (lid5,)).fetchone()
    assert updated["website_checked"] == 1
    assert "found website via search" in updated["notes"]


def test_scrub_all(conn):
    from agency.compliance.gates import add_dnc

    add_dnc(conn, "+15125550100")

    # Lead 1: verified and on DNC -> status should become 'dnc'
    insert_lead(conn, source="t", source_id="1", name="DNC Shop", phone_e164="+15125550100", status="verified")
    # Lead 2: verified and NOT on DNC -> status should become 'ready'
    insert_lead(conn, source="t", source_id="2", name="Ready Shop", phone_e164="+15125550199", status="verified")

    counts = verify.scrub_all(conn)
    assert counts == {"ready": 1, "dnc": 1}

    row1 = conn.execute("SELECT status FROM leads WHERE source_id = '1'").fetchone()
    row2 = conn.execute("SELECT status FROM leads WHERE source_id = '2'").fetchone()
    assert row1["status"] == "dnc"
    assert row2["status"] == "ready"
