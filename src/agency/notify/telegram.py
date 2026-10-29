"""Telegram Bot API over plain httpx. Only the owner's chat (TELEGRAM_CHAT_ID) is ever served."""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

import httpx

from agency.config import Settings, get_settings

log = logging.getLogger(__name__)


def _api(s: Settings, method: str) -> str:
    return f"https://api.telegram.org/bot{s.telegram_token}/{method}"


def send_message(text: str, *, settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    if not (s.telegram_token and s.telegram_chat_id):
        log.info("Telegram not configured; message was: %s", text)
        return False
    r = httpx.post(_api(s, "sendMessage"), json={"chat_id": s.telegram_chat_id, "text": text[:4000]}, timeout=15)
    if r.status_code != 200:
        log.error("Telegram send failed: %s", r.text[:200])
    return r.status_code == 200


def send_photo(path: str | Path, caption: str = "", *, settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    if not (s.telegram_token and s.telegram_chat_id):
        return False
    p = Path(path)
    if not p.is_file():
        log.warning("Telegram photo skipped: %s does not exist", p)
        return False
    with open(p, "rb") as f:
        r = httpx.post(
            _api(s, "sendPhoto"),
            data={"chat_id": s.telegram_chat_id, "caption": caption[:1000]},
            files={"photo": f},
            timeout=30,
        )
    if r.status_code != 200:
        log.error("Telegram photo failed: %s", r.text[:200])
    return r.status_code == 200


def handle_command(conn: sqlite3.Connection, text: str, settings: Settings) -> str:
    from agency.pipeline.post_sale import finalize_client  # lazy import

    parts = text.strip().split()
    cmd = parts[0].lower() if parts else ""
    arg = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None

    if cmd == "/status":
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status").fetchall()
        return "Leads: " + (", ".join(f"{r['status']}={r['n']}" for r in rows) if rows else "no leads yet")

    if cmd == "/clients":
        rows = conn.execute("SELECT id, status, payment_status, site_slug FROM clients ORDER BY id DESC LIMIT 10").fetchall()
        return "\n".join(f"#{r['id']} {r['status']} {r['payment_status']} {r['site_slug']}" for r in rows) or "No clients yet"

    if cmd == "/preview":
        if not arg:
            return "Usage: /preview <client_id>"
        c = conn.execute("SELECT * FROM clients WHERE id = ?", (arg,)).fetchone()
        if not c:
            return f"Client {arg} not found"
        site_path = Path(settings.output_dir) / (c["site_slug"] or "")
        return f"Client #{arg} preview: {site_path} (status: {c['status']})"

    if cmd == "/paid":
        if not arg:
            return "Usage: /paid <client_id>"
        cur = conn.execute("UPDATE clients SET payment_status = 'paid' WHERE id = ?", (arg,))
        conn.commit()
        if cur.rowcount == 0:
            return f"Client {arg} not found"
        return f"Client {arg} marked paid"

    if cmd == "/reject":
        if not arg:
            return "Usage: /reject <client_id>"
        cur = conn.execute("UPDATE clients SET status = 'rejected' WHERE id = ?", (arg,))
        conn.commit()
        if cur.rowcount == 0:
            return f"Client {arg} not found"
        return f"Client {arg} rejected"

    if cmd == "/approve":
        if not arg:
            return "Usage: /approve <client_id>"
        try:
            return finalize_client(conn, arg, settings=settings)
        except Exception as e:  # report to owner instead of crashing the bot
            log.exception("finalize failed")
            return f"Deploy failed: {e}"

    return "Commands: /status, /clients, /preview <id>, /paid <id>, /approve <id>, /reject <id>"


def run_bot(conn: sqlite3.Connection, settings: Settings | None = None, once: bool = False) -> None:
    """Long-poll loop. Ignores every chat except the owner's.

    When once=True, processes pending updates in a single batch and returns.
    """
    s = settings or get_settings()
    if not (s.telegram_token and s.telegram_chat_id):
        log.error("Telegram bot cannot run: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must both be set")
        return

    offset = 0
    while True:
        try:
            r = httpx.get(_api(s, "getUpdates"), params={"timeout": 30, "offset": offset}, timeout=40)
            if r.status_code != 200:
                log.error("Telegram getUpdates failed: %s %s", r.status_code, r.text[:200])
                if once:
                    break
                time.sleep(5)
                continue

            for upd in r.json().get("result", []):
                offset = max(offset, upd["update_id"] + 1)
                msg = upd.get("message") or upd.get("edited_message") or {}
                if str(msg.get("chat", {}).get("id")) != str(s.telegram_chat_id):
                    continue
                text = msg.get("text", "")
                if text.startswith("/"):
                    response = handle_command(conn, text, s)
                    send_message(response, settings=s)
        except Exception:
            log.exception("bot loop error")
            if once:
                break
            time.sleep(5)

        if once:
            break
