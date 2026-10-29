"""Call tool logic. No LiveKit imports so it can be tested offline."""
from __future__ import annotations

import sqlite3

from agency.compliance.gates import add_dnc
from agency.config import Settings
from agency.voice.prompts import format_price_list, load_pricing

OUTCOMES = {"yes", "no", "callback", "voicemail", "wrong_number", "dnc"}


class CallTools:
    def __init__(self, conn: sqlite3.Connection, settings: Settings, lead_id: int):
        self.conn, self.s, self.lead_id = conn, settings, lead_id
        self.call_id: int | None = None
        self.notes: list[str] = []

    def start_call(self, gate_reason: str = "ok") -> int:
        cur = self.conn.execute(
            "INSERT INTO calls (lead_id, gate_decision) VALUES (?, ?)", (self.lead_id, gate_reason)
        )
        self.conn.execute(
            "UPDATE leads SET attempts = attempts + 1, status = 'calling' WHERE id = ?", (self.lead_id,)
        )
        self.conn.commit()
        self.call_id = cur.lastrowid
        return self.call_id

    def get_price_list(self) -> str:
        return format_price_list(load_pricing(self.s.pricing_path))

    def save_notes(self, notes: str) -> str:
        self.notes.append(notes.strip())
        self.conn.execute("UPDATE leads SET notes = COALESCE(notes, '') || ? WHERE id = ?", (f"\n[call] {notes.strip()}", self.lead_id))
        self.conn.commit()
        return "saved"

    def schedule_callback(self, when_text: str) -> str:
        self.conn.execute("UPDATE leads SET callback_at = ? WHERE id = ?", (when_text[:100], self.lead_id))
        return self.record_outcome("callback", f"asked for callback: {when_text}")

    def record_outcome(self, outcome: str, summary: str = "") -> str:
        if outcome not in OUTCOMES:
            return f"invalid outcome; use one of {sorted(OUTCOMES)}"
        lead = self.conn.execute("SELECT attempts FROM leads WHERE id = ?", (self.lead_id,)).fetchone()
        status = {
            "yes": "yes", "no": "no", "callback": "callback", "wrong_number": "disqualified", "dnc": "dnc",
            "voicemail": "voicemail" if lead["attempts"] >= self.s.max_attempts else "ready",
        }[outcome]
        self.conn.execute("UPDATE leads SET status = ? WHERE id = ?", (status, self.lead_id))
        self.conn.execute(
            "UPDATE calls SET outcome = ?, summary = ?, ended_at = datetime('now') WHERE id = ?",
            (outcome, summary[:500], self.call_id),
        )
        self.conn.commit()
        return "recorded"

    def mark_do_not_call(self, reason: str = "opt-out on call") -> str:
        phone = self.conn.execute("SELECT phone_e164 FROM leads WHERE id = ?", (self.lead_id,)).fetchone()["phone_e164"]
        if phone:
            add_dnc(self.conn, phone, reason)
        return self.record_outcome("dnc", reason)

    def create_deal(self, package_id: str, contact_email: str = "") -> str:
        from agency.pipeline.post_sale import handle_deal  # lazy import: pulls in sitegen

        self.record_outcome("yes", f"package={package_id} email={contact_email}")
        result = handle_deal(
            self.conn, self.lead_id, package_id=package_id, contact_email=contact_email or None,
            call_notes="\n".join(self.notes), settings=self.s,
        )
        return f"deal created (client {result['client_id']}); a payment link and preview will follow"
