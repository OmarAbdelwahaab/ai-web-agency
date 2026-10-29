"""Reporting and CSV export for leads, calls, gate logs, and client outcomes."""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any

from agency.config import Settings, get_settings


def get_dashboard_stats(conn: sqlite3.Connection, settings: Settings | None = None) -> dict[str, Any]:
    s = settings or get_settings()

    # 1. Leads by status
    lead_rows = conn.execute("SELECT status, COUNT(*) AS count FROM leads GROUP BY status").fetchall()
    leads_by_status = {r["status"]: r["count"] for r in lead_rows}
    total_leads = sum(leads_by_status.values())

    # 2. Calls
    call_total = conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
    calls_today = conn.execute("SELECT COUNT(*) FROM calls WHERE date(started_at) = date('now')").fetchone()[0]
    calls_week = conn.execute("SELECT COUNT(*) FROM calls WHERE date(started_at) >= date('now', '-7 days')").fetchone()[0]
    outcome_rows = conn.execute("SELECT outcome, COUNT(*) AS count FROM calls WHERE outcome IS NOT NULL GROUP BY outcome").fetchall()
    outcomes = {r["outcome"]: r["count"] for r in outcome_rows}

    # 3. Clients
    client_rows = conn.execute("SELECT status, payment_status FROM clients").fetchall()
    total_clients = len(client_rows)
    client_status = {}
    payment_status = {}
    for r in client_rows:
        client_status[r["status"]] = client_status.get(r["status"], 0) + 1
        payment_status[r["payment_status"]] = payment_status.get(r["payment_status"], 0) + 1

    # 4. Gate compliance
    gate_total = conn.execute("SELECT COUNT(*) FROM gate_log").fetchone()[0]
    gate_allowed = conn.execute("SELECT COUNT(*) FROM gate_log WHERE allowed = 1").fetchone()[0]
    gate_blocked = gate_total - gate_allowed
    top_blocks = conn.execute(
        "SELECT reason, COUNT(*) AS count FROM gate_log WHERE allowed = 0 GROUP BY reason ORDER BY count DESC LIMIT 5"
    ).fetchall()
    rejection_reasons = {r["reason"]: r["count"] for r in top_blocks}

    # 5. Legal review status
    legal_reviews_count = conn.execute("SELECT COUNT(*) FROM legal_reviews").fetchone()[0]

    return {
        "agency_name": s.agency_name,
        "total_leads": total_leads,
        "leads_by_status": leads_by_status,
        "total_calls": call_total,
        "calls_today": calls_today,
        "calls_week": calls_week,
        "daily_call_cap": s.daily_call_cap,
        "outcomes": outcomes,
        "total_clients": total_clients,
        "client_status": client_status,
        "payment_status": payment_status,
        "gate_total": gate_total,
        "gate_allowed": gate_allowed,
        "gate_blocked": gate_blocked,
        "rejection_reasons": rejection_reasons,
        "legal_review_done_setting": s.legal_review_done,
        "legal_reviews_recorded": legal_reviews_count,
        "live_dialing_enabled": s.live_dialing_enabled,
        "deploy_enabled": s.deploy_enabled,
    }


def render_dashboard(conn: sqlite3.Connection, settings: Settings | None = None) -> str:
    stats = get_dashboard_stats(conn, settings)

    lines = [
        "=" * 60,
        f"  AGENCY DASHBOARD: {stats['agency_name'].upper()}",
        "=" * 60,
        "",
        "--- SYSTEM SWITCHES & COMPLIANCE ---",
        f"  Live Dialing:       {'[ENABLED]' if stats['live_dialing_enabled'] else '[OFF] (Safe)'}",
        f"  Legal Review Setting: {'[YES]' if stats['legal_review_done_setting'] else '[NO]'}",
        f"  Attorney Reviews:   {stats['legal_reviews_recorded']} recorded",
        f"  Deploy Enabled:     {'[YES]' if stats['deploy_enabled'] else '[OFF]'}",
        "",
        "--- LEADS OVERVIEW ---",
        f"  Total Leads: {stats['total_leads']}",
    ]
    if stats["leads_by_status"]:
        lines.append("  Breakdown:")
        for status, cnt in sorted(stats["leads_by_status"].items()):
            lines.append(f"    - {status:<15}: {cnt:>5}")
    else:
        lines.append("  No leads in database yet.")

    lines.extend([
        "",
        "--- TELEPHONY & CALLS ---",
        f"  Today's Call Cap:   {stats['calls_today']} / {stats['daily_call_cap']} calls placed today",
        f"  Last 7 Days:        {stats['calls_week']} calls",
        f"  All-Time Calls:     {stats['total_calls']} calls",
    ])
    if stats["outcomes"]:
        lines.append("  Outcomes:")
        for outcome, cnt in sorted(stats["outcomes"].items()):
            lines.append(f"    - {outcome:<15}: {cnt:>5}")

    lines.extend([
        "",
        "--- COMPLIANCE GATE AUDIT ---",
        f"  Total Evaluations:  {stats['gate_total']}",
        f"  Allowed:            {stats['gate_allowed']}",
        f"  Blocked:            {stats['gate_blocked']}",
    ])
    if stats["rejection_reasons"]:
        lines.append("  Top Block Reasons:")
        for reason, cnt in stats["rejection_reasons"].items():
            lines.append(f"    - {reason:<35}: {cnt:>4}")

    lines.extend([
        "",
        "--- POST-SALE & CLIENTS ---",
        f"  Total Clients:      {stats['total_clients']}",
    ])
    if stats["client_status"]:
        lines.append("  Review Status:")
        for st, cnt in sorted(stats["client_status"].items()):
            lines.append(f"    - {st:<15}: {cnt:>5}")
        lines.append("  Payment Status:")
        for pst, cnt in sorted(stats["payment_status"].items()):
            lines.append(f"    - {pst:<15}: {cnt:>5}")

    lines.append("=" * 60)
    return "\n".join(lines)


VALID_TABLES = {"leads", "calls", "clients", "gate_log", "dnc", "legal_reviews"}


def export_table_to_csv(conn: sqlite3.Connection, table: str, output_path: Path | str) -> int:
    table = table.strip().lower()
    if table not in VALID_TABLES:
        raise ValueError(f"Unknown table '{table}'. Valid tables: {', '.join(sorted(VALID_TABLES))}")

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    cursor = conn.execute(f"SELECT * FROM {table}")
    headers = [d[0] for d in cursor.description]

    rows = cursor.fetchall()
    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(list(row))

    return len(rows)


def export_all_to_csv(conn: sqlite3.Connection, output_dir: Path | str) -> dict[str, int]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for table in sorted(VALID_TABLES):
        dest = out_dir / f"{table}.csv"
        results[table] = export_table_to_csv(conn, table, dest)
    return results
