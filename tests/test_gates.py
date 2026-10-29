from datetime import datetime, time, timezone

import pytest

from agency.compliance import gates
from agency.config import Settings
from agency.db import connect, get_lead, init_db, insert_lead


@pytest.fixture()
def conn():
    c = connect(":memory:")
    init_db(c)
    return c


def make_lead(conn, **over):
    fields = dict(source="t", source_id="1", name="Test Shop", phone_e164="+15125550100", timezone="America/Chicago",
                  state="TX", status="ready", attempts=0)
    fields.update(over)
    return get_lead(conn, insert_lead(conn, **fields))


NOON_CT = datetime(2026, 10, 26, 17, 0, tzinfo=timezone.utc)   # 12:00 in Chicago (CDT)
NIGHT_CT = datetime(2026, 10, 27, 3, 30, tzinfo=timezone.utc)  # 22:30 in Chicago


def test_window_uses_lead_local_time():
    assert gates.within_calling_window("America/Chicago", now_utc=NOON_CT)
    assert not gates.within_calling_window("America/Chicago", now_utc=NIGHT_CT)
    # same instant is 10:00 in Los Angeles but 13:00 in New York
    assert gates.within_calling_window("America/Los_Angeles", now_utc=NOON_CT)
    assert gates.within_calling_window("America/New_York", now_utc=NOON_CT)


def test_allowed_in_dry_run(conn):
    lead = make_lead(conn)
    assert gates.can_dial(conn, lead, settings=Settings(), now_utc=NOON_CT).allowed


def test_blocks_outside_window(conn):
    lead = make_lead(conn)
    r = gates.can_dial(conn, lead, settings=Settings(), now_utc=NIGHT_CT)
    assert not r.allowed and "window" in r.reason


def test_blocks_dnc(conn):
    lead = make_lead(conn)
    gates.add_dnc(conn, "+15125550100")
    r = gates.can_dial(conn, lead, settings=Settings(), now_utc=NOON_CT)
    assert not r.allowed and "DNC" in r.reason


def test_blocks_attempt_limit(conn):
    lead = make_lead(conn, attempts=2)
    assert not gates.can_dial(conn, lead, settings=Settings(), now_utc=NOON_CT).allowed


def test_blocks_non_us_and_bad_status(conn):
    assert not gates.can_dial(conn, make_lead(conn, source_id="2", phone_e164="+201155347345"), settings=Settings(), now_utc=NOON_CT).allowed
    assert not gates.can_dial(conn, make_lead(conn, source_id="3", status="new"), settings=Settings(), now_utc=NOON_CT).allowed


def test_live_requires_both_switches(conn):
    lead = make_lead(conn)
    off = Settings()
    assert not gates.can_dial(conn, lead, live=True, settings=off, now_utc=NOON_CT).allowed


def test_gate_decisions_are_logged(conn):
    lead = make_lead(conn)
    gates.can_dial(conn, lead, settings=Settings(), now_utc=NOON_CT)
    assert conn.execute("SELECT COUNT(*) FROM gate_log").fetchone()[0] == 1
