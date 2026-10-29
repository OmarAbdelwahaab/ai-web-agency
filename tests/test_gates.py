from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

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


# --- Edge cases: Time zones around midnight ---

def test_timezone_around_midnight():
    """Verify boundaries around midnight: 23:59 (outside), 00:00 (outside), 07:59 (outside), 08:00 (inside)."""
    tz = "America/Chicago"
    # Chicago is UTC-5 in standard time (CST) or UTC-6
    # 2026-01-15 is CST (UTC-6)
    # Midnight CST is 06:00 UTC
    just_before_midnight = datetime(2026, 1, 15, 5, 59, 59, tzinfo=timezone.utc)  # 23:59:59 local
    midnight = datetime(2026, 1, 15, 6, 0, 0, tzinfo=timezone.utc)                # 00:00:00 local
    one_am = datetime(2026, 1, 15, 7, 0, 0, tzinfo=timezone.utc)                  # 01:00:00 local
    morning_before = datetime(2026, 1, 15, 13, 59, 59, tzinfo=timezone.utc)       # 07:59:59 local
    morning_open = datetime(2026, 1, 15, 14, 0, 0, tzinfo=timezone.utc)           # 08:00:00 local
    evening_close = datetime(2026, 1, 16, 3, 0, 0, tzinfo=timezone.utc)           # 21:00:00 local

    assert not gates.within_calling_window(tz, now_utc=just_before_midnight)
    assert not gates.within_calling_window(tz, now_utc=midnight)
    assert not gates.within_calling_window(tz, now_utc=one_am)
    assert not gates.within_calling_window(tz, now_utc=morning_before)
    assert gates.within_calling_window(tz, now_utc=morning_open)
    assert not gates.within_calling_window(tz, now_utc=evening_close)  # [08:00, 21:00) is exclusive at end


# --- Edge cases: Daylight Saving Time (DST) ---

def test_dst_spring_forward():
    """In 2026, US DST begins March 8. Clocks advance from 02:00 CST to 03:00 CDT (UTC-6 to UTC-5)."""
    tz = "America/Chicago"
    # Prior to DST: March 7, 14:00 UTC = 08:00 CST (in window)
    pre_dst = datetime(2026, 3, 7, 14, 0, 0, tzinfo=timezone.utc)
    assert gates.local_now(tz, pre_dst).hour == 8
    assert gates.within_calling_window(tz, now_utc=pre_dst)

    # After spring forward: March 9, 13:00 UTC = 08:00 CDT (in window, shifted by 1h UTC)
    post_dst = datetime(2026, 3, 9, 13, 0, 0, tzinfo=timezone.utc)
    assert gates.local_now(tz, post_dst).hour == 8
    assert gates.within_calling_window(tz, now_utc=post_dst)

    # March 9 at 12:59 UTC = 07:59 CDT (outside window)
    just_before_post = datetime(2026, 3, 9, 12, 59, 59, tzinfo=timezone.utc)
    assert not gates.within_calling_window(tz, now_utc=just_before_post)


def test_dst_fall_back():
    """In 2026, US DST ends November 1. Clocks shift back from 02:00 CDT to 01:00 CST (UTC-5 to UTC-6)."""
    tz = "America/Chicago"
    # Prior to fall-back: Oct 31, 13:00 UTC = 08:00 CDT (in window)
    pre_fallback = datetime(2026, 10, 31, 13, 0, 0, tzinfo=timezone.utc)
    assert gates.local_now(tz, pre_fallback).hour == 8
    assert gates.within_calling_window(tz, now_utc=pre_fallback)

    # After fall-back: Nov 2, 14:00 UTC = 08:00 CST (in window)
    post_fallback = datetime(2026, 11, 2, 14, 0, 0, tzinfo=timezone.utc)
    assert gates.local_now(tz, post_fallback).hour == 8
    assert gates.within_calling_window(tz, now_utc=post_fallback)

    # Nov 2 at 13:59 UTC = 07:59 CST (outside window)
    just_before_fallback = datetime(2026, 11, 2, 13, 59, 59, tzinfo=timezone.utc)
    assert not gates.within_calling_window(tz, now_utc=just_before_fallback)


def test_invalid_timezone_handling(conn):
    """Invalid or unknown timezone gracefully blocks call without unhandled exceptions."""
    lead_no_tz = make_lead(conn, source_id="no_tz", timezone=None)
    r1 = gates.can_dial(conn, lead_no_tz, settings=Settings(), now_utc=NOON_CT)
    assert not r1.allowed and "timezone" in r1.reason

    lead_bad_tz = make_lead(conn, source_id="bad_tz", timezone="Mars/Curiosity")
    r2 = gates.can_dial(conn, lead_bad_tz, settings=Settings(), now_utc=NOON_CT)
    assert not r2.allowed and "timezone" in r2.reason


def test_over_midnight_window():
    """Custom window crossing midnight: e.g. start=22:00, end=06:00."""
    tz = "UTC"
    at_23 = datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc)
    at_02 = datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc)
    at_12 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    assert gates.within_calling_window(tz, start=time(22, 0), end=time(6, 0), now_utc=at_23)
    assert gates.within_calling_window(tz, start=time(22, 0), end=time(6, 0), now_utc=at_02)
    assert not gates.within_calling_window(tz, start=time(22, 0), end=time(6, 0), now_utc=at_12)


# --- Edge cases: DNC matching with different phone formats ---

@pytest.mark.parametrize("dnc_input,query_input", [
    ("+15125550100", "+15125550100"),
    ("(512) 555-0100", "+15125550100"),
    ("512-555-0100", "+15125550100"),
    ("512.555.0100", "+15125550100"),
    ("5125550100", "+15125550100"),
    ("15125550100", "+15125550100"),
    ("+1 (512) 555-0100", "+15125550100"),
    ("+15125550100", "(512) 555-0100"),
    ("+15125550100", "5125550100"),
    ("+15125550100", "512-555-0100"),
])
def test_dnc_format_matching(conn, dnc_input, query_input):
    """Verify DNC matching works regardless of punctuation, parenthesis, dashes, or national prefix."""
    gates.add_dnc(conn, dnc_input)
    assert gates.is_dnc(conn, query_input)


def test_dnc_blocks_in_can_dial(conn):
    """Verify can_dial blocks a lead when DNC was recorded in a national or raw format."""
    lead = make_lead(conn, phone_e164="+15125550100")
    gates.add_dnc(conn, "(512) 555-0100")
    res = gates.can_dial(conn, lead, settings=Settings(), now_utc=NOON_CT)
    assert not res.allowed
    assert "DNC" in res.reason


# --- Edge cases: Attempt limits ---

@pytest.mark.parametrize("attempts,max_attempts,expected_allowed", [
    (0, 2, True),
    (1, 2, True),
    (2, 2, False),
    (3, 2, False),
    (0, 1, True),
    (1, 1, False),
    (0, 0, False),
])
def test_attempt_limits_boundary(conn, attempts, max_attempts, expected_allowed):
    lead = make_lead(conn, source_id=f"att_{attempts}_{max_attempts}", attempts=attempts)
    s = Settings(max_attempts=max_attempts)
    res = gates.can_dial(conn, lead, settings=s, now_utc=NOON_CT)
    assert res.allowed == expected_allowed
    if not expected_allowed:
        assert "attempt limit" in res.reason
