"""The single gate every call must pass. Keep this module free of network and LiveKit imports."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from agency.config import Settings, get_settings
from agency.db import has_legal_review
from agency.phone import to_e164

# TODO(lawyer): fill with stricter per-state windows, e.g. {"OK": (time(8, 0), time(20, 0))}.
# Keys are two-letter state codes. Leave empty to use the default window from settings.
STATE_WINDOWS: dict[str, tuple[time, time]] = {}


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reason: str


def local_now(tz_name: str, now_utc: datetime | None = None) -> datetime:
    now_utc = now_utc or datetime.now(timezone.utc)
    return now_utc.astimezone(ZoneInfo(tz_name))


def within_calling_window(
    tz_name: str,
    *,
    start: time = time(8, 0),
    end: time = time(21, 0),
    now_utc: datetime | None = None,
) -> bool:
    """True if the lead's LOCAL time is in [start, end)."""
    try:
        t = local_now(tz_name, now_utc).time()
    except Exception:
        return False
    if start <= end:
        return start <= t < end
    return t >= start or t < end


def is_dnc(conn: sqlite3.Connection, phone_e164: str | None) -> bool:
    if not phone_e164:
        return False
    norm = to_e164(phone_e164)
    candidates = {phone_e164}
    if norm:
        candidates.add(norm)
        if norm.startswith("+1") and len(norm) == 12:
            candidates.add(norm[2:])   # 10-digit national without country code
            candidates.add(norm[1:])   # 11-digit national with leading 1
    placeholders = ", ".join("?" for _ in candidates)
    row = conn.execute(f"SELECT 1 FROM dnc WHERE phone_e164 IN ({placeholders})", tuple(candidates)).fetchone()
    return row is not None


def add_dnc(conn: sqlite3.Connection, phone_e164: str, reason: str = "opt-out") -> None:
    norm = to_e164(phone_e164) or phone_e164
    conn.execute("INSERT OR IGNORE INTO dnc (phone_e164, reason) VALUES (?, ?)", (norm, reason))
    conn.commit()


def can_dial(
    conn: sqlite3.Connection,
    lead: sqlite3.Row,
    *,
    live: bool = False,
    settings: Settings | None = None,
    now_utc: datetime | None = None,
    log: bool = True,
) -> GateResult:
    """Decide whether a call may be placed right now. Logs every decision."""
    s = settings or get_settings()
    result = _evaluate(conn, lead, live, s, now_utc)
    if log:
        conn.execute(
            "INSERT INTO gate_log (lead_id, allowed, reason) VALUES (?, ?, ?)",
            (lead["id"], int(result.allowed), result.reason),
        )
        conn.commit()
    return result


def _evaluate(conn, lead, live: bool, s: Settings, now_utc: datetime | None) -> GateResult:
    if live and not s.live_dialing_enabled:
        return GateResult(False, "LIVE_DIALING_ENABLED is false")
    if live and not s.legal_review_done:
        return GateResult(False, "LEGAL_REVIEW_DONE is false")
    if live and not has_legal_review(conn):
        return GateResult(False, "no attorney sign-off recorded in database")

    # Check daily call cap
    if now_utc is not None:
        date_str = now_utc.strftime("%Y-%m-%d")
        row = conn.execute("SELECT COUNT(*) FROM calls WHERE date(started_at) = date(?)", (date_str,)).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) FROM calls WHERE date(started_at) = date('now')").fetchone()
    calls_today = row[0] if row else 0
    if calls_today >= s.daily_call_cap:
        return GateResult(False, f"daily call cap reached ({calls_today}/{s.daily_call_cap})")

    phone = lead["phone_e164"]
    if not phone or not phone.startswith("+1"):
        return GateResult(False, "missing or non-US phone number")
    if lead["status"] in {"dnc", "disqualified", "yes", "no"}:
        return GateResult(False, f"lead status is {lead['status']}")
    if lead["status"] not in {"ready", "callback"}:
        return GateResult(False, f"lead status {lead['status']} is not callable")
    if is_dnc(conn, phone):
        return GateResult(False, "number is in internal DNC list")
    if lead["attempts"] >= s.max_attempts:
        return GateResult(False, "attempt limit reached")

    # Check cooldown between previous call attempt and now
    if lead["attempts"] > 0 and s.min_call_interval_hours > 0:
        prev = conn.execute(
            "SELECT started_at FROM calls WHERE lead_id = ? ORDER BY id DESC LIMIT 1",
            (lead["id"],),
        ).fetchone()
        if prev and prev["started_at"]:
            try:
                prev_dt = datetime.fromisoformat(prev["started_at"])
                if prev_dt.tzinfo is None:
                    prev_dt = prev_dt.replace(tzinfo=timezone.utc)
                now_check = now_utc if now_utc is not None else datetime.now(timezone.utc)
                diff_hours = (now_check - prev_dt).total_seconds() / 3600.0
                if diff_hours < s.min_call_interval_hours:
                    return GateResult(False, f"cooldown between attempts not elapsed ({diff_hours:.1f}h < {s.min_call_interval_hours}h)")
            except Exception:
                pass

    tz = lead["timezone"]
    if not tz:
        return GateResult(False, "unknown lead timezone")
    try:
        local_now(tz, now_utc)
    except Exception:
        return GateResult(False, f"invalid lead timezone: {tz}")
    start, end = STATE_WINDOWS.get((lead["state"] or "").upper(), (s.window_start, s.window_end))
    if not within_calling_window(tz, start=start, end=end, now_utc=now_utc):
        return GateResult(False, f"outside calling window in {tz}")
    return GateResult(True, "ok")
