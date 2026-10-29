import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agency.config import Settings
from agency.db import connect, init_db, insert_lead
from agency.voice.dispatch import _create_dispatch, dispatch_call


@pytest.fixture()
def dispatch_db():
    conn = connect(":memory:")
    init_db(conn)
    lid = insert_lead(
        conn,
        source="places",
        source_id="p200",
        name="Reliable Roofing Co",
        category="roofing",
        phone_e164="+15125550177",
        city="Austin",
        state="TX",
        lat=30.2672,
        lng=-97.7431,
        timezone="America/Chicago",
        status="ready",
        attempts=0,
    )
    return conn, lid


def test_dispatch_lead_not_found(dispatch_db):
    conn, _ = dispatch_db
    res = dispatch_call(conn, 9999)
    assert res == {"dispatched": False, "reason": "lead not found"}


def test_dispatch_dry_run_within_window(dispatch_db):
    conn, lid = dispatch_db
    # 18:00 UTC = 1:00 PM CDT (well within 08:00 - 21:00 window)
    now_utc = datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc)
    res = dispatch_call(conn, lid, live=False, now_utc=now_utc)

    assert res["dispatched"] is False
    assert res["dry_run"] is True
    assert res["would_dispatch"]["room"].startswith(f"call-{lid}-")
    assert res["would_dispatch"]["metadata"] == {
        "lead_id": lid,
        "phone_number": "+15125550177",
        "live": True,
    }

    # Verify decision recorded in gate_log
    log_row = conn.execute("SELECT * FROM gate_log WHERE lead_id = ? ORDER BY id DESC LIMIT 1", (lid,)).fetchone()
    assert log_row is not None
    assert log_row["allowed"] == 1
    assert log_row["reason"] == "ok"


def test_dispatch_dry_run_outside_window(dispatch_db):
    conn, lid = dispatch_db
    # 03:00 UTC = 10:00 PM CDT (outside 08:00 - 21:00 window)
    now_utc = datetime(2026, 6, 15, 3, 0, tzinfo=timezone.utc)
    res = dispatch_call(conn, lid, live=False, now_utc=now_utc)

    assert res["dispatched"] is False
    assert "outside calling window" in res["reason"]

    # Verify blocked decision recorded in gate_log
    log_row = conn.execute("SELECT * FROM gate_log WHERE lead_id = ? ORDER BY id DESC LIMIT 1", (lid,)).fetchone()
    assert log_row is not None
    assert log_row["allowed"] == 0
    assert "outside calling window" in log_row["reason"]


def test_dispatch_live_safety_switches(dispatch_db):
    conn, lid = dispatch_db
    now_utc = datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc)

    # 1. LIVE_DIALING_ENABLED is False
    s1 = Settings(live_dialing_enabled=False, legal_review_done=True, sip_trunk_id="ST_123")
    res1 = dispatch_call(conn, lid, live=True, settings=s1, now_utc=now_utc)
    assert res1 == {"dispatched": False, "reason": "LIVE_DIALING_ENABLED is false"}

    # 2. LEGAL_REVIEW_DONE is False
    s2 = Settings(live_dialing_enabled=True, legal_review_done=False, sip_trunk_id="ST_123")
    res2 = dispatch_call(conn, lid, live=True, settings=s2, now_utc=now_utc)
    assert res2 == {"dispatched": False, "reason": "LEGAL_REVIEW_DONE is false"}

    # 3. Attorney sign-off record missing in DB
    s_no_attorney = Settings(live_dialing_enabled=True, legal_review_done=True, sip_trunk_id="ST_123")
    res_no_attorney = dispatch_call(conn, lid, live=True, settings=s_no_attorney, now_utc=now_utc)
    assert res_no_attorney == {"dispatched": False, "reason": "no attorney sign-off recorded in database"}

    # Record sign-off for next checks
    from agency.db import record_legal_review
    record_legal_review(conn, "Jane Doe, Esq.", "TCPA Compliance PLLC", "Approved calling script")

    # 4. SIP_OUTBOUND_TRUNK_ID missing
    s3 = Settings(live_dialing_enabled=True, legal_review_done=True, sip_trunk_id="")
    res3 = dispatch_call(conn, lid, live=True, settings=s3, now_utc=now_utc)
    assert res3 == {"dispatched": False, "reason": "SIP_OUTBOUND_TRUNK_ID is not set"}


def test_dispatch_live_success(dispatch_db):
    from agency.db import record_legal_review

    conn, lid = dispatch_db
    record_legal_review(conn, "Jane Doe, Esq.", "TCPA Law", "Full review")
    now_utc = datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc)
    s = Settings(
        live_dialing_enabled=True,
        legal_review_done=True,
        sip_trunk_id="ST_test_trunk",
        livekit_agent_name="agency-caller",
    )

    with patch("agency.voice.dispatch._create_dispatch", new_callable=AsyncMock) as mock_dispatch:
        mock_dispatch.return_value = "dispatch_info_ok"
        res = dispatch_call(conn, lid, live=True, settings=s, now_utc=now_utc)

    assert res["dispatched"] is True
    assert res["room"].startswith(f"call-{lid}-")
    assert res["result"] == "dispatch_info_ok"
    mock_dispatch.assert_awaited_once()


def test_create_dispatch_helper():
    s = Settings(livekit_agent_name="test-agent")
    mock_lkapi = MagicMock()
    mock_lkapi.agent_dispatch = MagicMock()
    mock_lkapi.agent_dispatch.create_dispatch = AsyncMock(return_value="dispatch_response_obj")
    mock_lkapi.aclose = AsyncMock()

    with patch("livekit.api.LiveKitAPI", return_value=mock_lkapi):
        res = asyncio.run(_create_dispatch(s, "room-1", '{"lead_id": 1}'))

    assert res == "dispatch_response_obj"
    mock_lkapi.agent_dispatch.create_dispatch.assert_awaited_once()
    mock_lkapi.aclose.assert_awaited_once()


def test_cli_dial_command(dispatch_db, monkeypatch, capsys):
    from agency.cli import main

    conn, lid = dispatch_db
    monkeypatch.setattr("agency.cli._conn", lambda: conn)

    # Dial dry-run via CLI
    main(["dial", "--lead-id", str(lid)])
    out = capsys.readouterr().out
    assert '"dispatched": false' in out
