import os
import sqlite3
from datetime import time
from pathlib import Path

import pytest

from agency.config import Settings, _bool, _time, get_settings
from agency.db import connect, get_lead, init_db, insert_lead


# --- Config Tests ---

@pytest.mark.parametrize("val,expected", [
    ("1", True),
    ("true", True),
    ("True", True),
    ("TRUE", True),
    ("yes", True),
    ("YES", True),
    ("on", True),
    ("ON", True),
    ("0", False),
    ("false", False),
    ("False", False),
    ("no", False),
    ("off", False),
    ("", False),
    ("anything_else", False),
])
def test_config_bool_parser(monkeypatch, val, expected):
    monkeypatch.setenv("TEST_FLAG", val)
    assert _bool("TEST_FLAG") == expected


def test_config_bool_default():
    assert _bool("NON_EXISTENT_VAR", default=True) is True
    assert _bool("NON_EXISTENT_VAR", default=False) is False


@pytest.mark.parametrize("val,expected_time", [
    ("08:00", time(8, 0)),
    ("8:30", time(8, 30)),
    ("21:00", time(21, 0)),
    ("0:00", time(0, 0)),
    ("23:59", time(23, 59)),
])
def test_config_time_parser(monkeypatch, val, expected_time):
    monkeypatch.setenv("TEST_TIME", val)
    assert _time("TEST_TIME", "12:00") == expected_time


def test_settings_frozen():
    s = Settings()
    with pytest.raises(Exception):
        s.live_dialing_enabled = True  # type: ignore


def test_settings_custom_overrides():
    s = Settings(
        agency_name="Custom Agency",
        max_attempts=5,
        deploy_enabled=True,
    )
    assert s.agency_name == "Custom Agency"
    assert s.max_attempts == 5
    assert s.deploy_enabled is True


def test_get_settings():
    s = get_settings()
    assert isinstance(s, Settings)
    assert s.pricing_path.name == "pricing.yaml"


# --- DB Tests ---

def test_db_init_and_tables(tmp_path):
    db_file = tmp_path / "subdir" / "test.db"
    conn = connect(db_file)
    init_db(conn)

    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"leads", "calls", "gate_log", "dnc", "clients"}.issubset(tables)


def test_db_foreign_keys_enabled():
    conn = connect(":memory:")
    init_db(conn)

    # Foreign key enforcement should be ON
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk_status == 1

    # Inserting a call with non-existent lead_id must raise an IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO calls (lead_id, outcome) VALUES (99999, 'test')")


def test_insert_and_get_lead():
    conn = connect(":memory:")
    init_db(conn)

    lid = insert_lead(
        conn,
        source="osm",
        source_id="node_123",
        name="Baker's Delight",
        phone_e164="+15125550199",
        city="Austin",
        state="TX",
        status="new",
    )
    assert lid is not None

    lead = get_lead(conn, lid)
    assert lead is not None
    assert lead["name"] == "Baker's Delight"
    assert lead["phone_e164"] == "+15125550199"
    assert lead["status"] == "new"
    assert lead["attempts"] == 0


def test_insert_lead_duplicate_unique_constraint():
    conn = connect(":memory:")
    init_db(conn)

    lid1 = insert_lead(conn, source="osm", source_id="node_dup", name="Shop 1")
    assert lid1 is not None

    # Inserting duplicate (source, source_id) must return None and not insert duplicate row
    lid2 = insert_lead(conn, source="osm", source_id="node_dup", name="Shop 1 Duplicate")
    assert lid2 is None

    count = conn.execute("SELECT COUNT(*) FROM leads WHERE source_id = 'node_dup'").fetchone()[0]
    assert count == 1


def test_clients_unique_lead_constraint():
    conn = connect(":memory:")
    init_db(conn)

    lid = insert_lead(conn, source="places", source_id="place_1", name="Plumber Inc")
    assert lid is not None

    conn.execute("INSERT INTO clients (lead_id, package_id) VALUES (?, 'starter')", (lid,))
    conn.commit()

    # Inserting second client with same lead_id should violate UNIQUE constraint
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO clients (lead_id, package_id) VALUES (?, 'pro')", (lid,))
