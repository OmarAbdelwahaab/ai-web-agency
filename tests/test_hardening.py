import csv
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agency.compliance import gates
from agency.config import Settings
from agency.db import connect, init_db, insert_lead, record_legal_review
from agency.logging_config import JSONFormatter, setup_logging
from agency.reporting import (
    VALID_TABLES,
    export_all_to_csv,
    export_table_to_csv,
    get_dashboard_stats,
    render_dashboard,
)
from agency.retry import retry


@pytest.fixture()
def db_conn():
    conn = connect(":memory:")
    init_db(conn)
    return conn


@pytest.fixture()
def sample_lead(db_conn):
    lid = insert_lead(
        db_conn,
        source="places",
        source_id="h100",
        name="Hardened Tech Support",
        category="it_services",
        phone_e164="+15125550180",
        city="Austin",
        state="TX",
        timezone="America/Chicago",
        status="ready",
        attempts=0,
    )
    return db_conn, lid


# --- 1. Daily Call Cap & Cooldown Gate Tests ---

def test_daily_call_cap_enforcement(sample_lead):
    conn, lid = sample_lead
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lid,)).fetchone()
    now_utc = datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc)
    s = Settings(daily_call_cap=2)

    # 0 calls made today -> allowed
    res0 = gates.can_dial(conn, lead, settings=s, now_utc=now_utc)
    assert res0.allowed is True

    # Insert 1 call today
    conn.execute("INSERT INTO calls (lead_id, started_at) VALUES (?, '2026-06-15 10:00:00')", (lid,))
    conn.commit()
    res1 = gates.can_dial(conn, lead, settings=s, now_utc=now_utc)
    assert res1.allowed is True

    # Insert 2nd call today -> reaches cap of 2
    conn.execute("INSERT INTO calls (lead_id, started_at) VALUES (?, '2026-06-15 12:00:00')", (lid,))
    conn.commit()
    res2 = gates.can_dial(conn, lead, settings=s, now_utc=now_utc)
    assert res2.allowed is False
    assert "daily call cap reached (2/2)" in res2.reason


def test_cooldown_interval_between_attempts(sample_lead):
    conn, lid = sample_lead
    # Simulate lead with 1 previous attempt made 1 hour ago
    conn.execute("UPDATE leads SET attempts = 1 WHERE id = ?", (lid,))
    conn.execute("INSERT INTO calls (lead_id, started_at) VALUES (?, '2026-06-15 13:00:00')", (lid,))
    conn.commit()
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lid,)).fetchone()

    s = Settings(min_call_interval_hours=4)

    # 1 hour later (14:00 UTC) -> cooldown of 4 hours not elapsed -> blocked
    check_time_1h = datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc)
    res_blocked = gates.can_dial(conn, lead, settings=s, now_utc=check_time_1h)
    assert res_blocked.allowed is False
    assert "cooldown between attempts not elapsed" in res_blocked.reason

    # 5 hours later (18:00 UTC) -> cooldown elapsed -> allowed
    check_time_5h = datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc)
    res_allowed = gates.can_dial(conn, lead, settings=s, now_utc=check_time_5h)
    assert res_allowed.allowed is True


# --- 2. Legal Review Enforcement Tests ---

def test_legal_review_gate_enforcement(sample_lead):
    conn, lid = sample_lead
    lead = conn.execute("SELECT * FROM leads WHERE id = ?", (lid,)).fetchone()
    now_utc = datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc)

    # Both switches ON, but no attorney review in DB -> blocked
    s = Settings(live_dialing_enabled=True, legal_review_done=True)
    res_no_review = gates.can_dial(conn, lead, live=True, settings=s, now_utc=now_utc)
    assert res_no_review.allowed is False
    assert res_no_review.reason == "no attorney sign-off recorded in database"

    # Record sign-off in DB
    rid = record_legal_review(conn, "Marcus Vance, Esq.", "Telemarketing Law Group", "Approved calling workflow")
    assert rid > 0

    # Now allowed!
    res_with_review = gates.can_dial(conn, lead, live=True, settings=s, now_utc=now_utc)
    assert res_with_review.allowed is True


# --- 3. Structured Logging Tests ---

def test_json_formatter():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="agency.test",
        level=logging.INFO,
        pathname="test_hardening.py",
        lineno=100,
        msg="Dial attempt for lead %d",
        args=(42,),
        exc_info=None,
    )
    record.lead_id = 42  # extra attribute
    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "agency.test"
    assert parsed["message"] == "Dial attempt for lead 42"
    assert "timestamp" in parsed
    assert parsed["extra"]["lead_id"] == 42


def test_setup_logging():
    s_json = Settings(log_format="json")
    setup_logging(s_json)
    root = logging.getLogger()
    assert isinstance(root.handlers[0].formatter, JSONFormatter)

    s_text = Settings(log_format="text")
    setup_logging(s_text)
    assert not isinstance(root.handlers[0].formatter, JSONFormatter)


# --- 4. Retries with Exponential Backoff Tests ---

def test_retry_success():
    calls = 0

    @retry(max_retries=3, base_delay=0.01, jitter=False)
    def flaky_func():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ValueError("temporary glitch")
        return "success"

    assert flaky_func() == "success"
    assert calls == 3


def test_retry_failure():
    calls = 0

    @retry(max_retries=2, base_delay=0.01, jitter=False)
    def fail_func():
        nonlocal calls
        calls += 1
        raise ConnectionError("network down")

    with pytest.raises(ConnectionError, match="network down"):
        fail_func()
    assert calls == 3  # initial attempt + 2 retries


# --- 5. Dashboard & Reporting Tests ---

def test_dashboard_stats_and_render(sample_lead):
    conn, lid = sample_lead
    record_legal_review(conn, "Sarah Connor, Esq.", "Cyber Compliance", "Sign-off complete")
    conn.execute("INSERT INTO calls (lead_id, started_at, outcome, summary) VALUES (?, datetime('now'), 'yes', 'Deal agreed')", (lid,))
    conn.execute("INSERT INTO clients (lead_id, package_id, status, payment_status) VALUES (?, 'starter', 'awaiting_review', 'unpaid')", (lid,))
    conn.commit()

    stats = get_dashboard_stats(conn)
    assert stats["total_leads"] == 1
    assert stats["total_calls"] == 1
    assert stats["calls_today"] == 1
    assert stats["total_clients"] == 1
    assert stats["legal_reviews_recorded"] == 1

    dashboard_text = render_dashboard(conn)
    assert "AGENCY DASHBOARD" in dashboard_text
    assert "Total Leads: 1" in dashboard_text
    assert "Total Clients:      1" in dashboard_text
    assert "Today's Call Cap:" in dashboard_text


def test_export_table_to_csv(sample_lead, tmp_path):
    conn, lid = sample_lead
    csv_file = tmp_path / "leads.csv"
    count = export_table_to_csv(conn, "leads", csv_file)
    assert count == 1
    assert csv_file.exists()

    with open(csv_file, newline="", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert reader[0][3] == "name"
        assert reader[1][3] == "Hardened Tech Support"

    with pytest.raises(ValueError, match="Unknown table"):
        export_table_to_csv(conn, "non_existent_table", tmp_path / "err.csv")


def test_export_all_to_csv(sample_lead, tmp_path):
    conn, _ = sample_lead
    out_dir = tmp_path / "exports"
    results = export_all_to_csv(conn, out_dir)

    for table in VALID_TABLES:
        assert table in results
        assert (out_dir / f"{table}.csv").exists()


# --- 6. CLI Command Integration Tests ---

def test_cli_dashboard_and_export(sample_lead, monkeypatch, capsys, tmp_path):
    from agency.cli import main

    conn, _ = sample_lead
    monkeypatch.setattr("agency.cli._conn", lambda: conn)

    # Test dashboard command
    main(["dashboard"])
    out_dash = capsys.readouterr().out
    assert "AGENCY DASHBOARD" in out_dash

    # Test record-legal-review command
    main(["record-legal-review", "--attorney", "David Miller", "--firm", "Miller Legal", "--notes", "Full approval"])
    out_review = capsys.readouterr().out
    assert "Legal review #" in out_review
    assert "David Miller" in out_review

    # Test export-csv command
    export_dir = tmp_path / "cli_exports"
    main(["export-csv", "--table", "all", "--output", str(export_dir)])
    out_exp = capsys.readouterr().out
    assert "Exported tables to" in out_exp
    assert (export_dir / "leads.csv").exists()
