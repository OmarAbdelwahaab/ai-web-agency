from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT,
    name TEXT NOT NULL,
    category TEXT,
    phone_e164 TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    lat REAL,
    lng REAL,
    timezone TEXT,
    website_uri TEXT,
    website_checked INTEGER NOT NULL DEFAULT 0,
    rating REAL,
    rating_count INTEGER,
    business_status TEXT,
    hours_json TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    attempts INTEGER NOT NULL DEFAULT 0,
    callback_at TEXT,
    notes TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone_e164);

CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id),
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT,
    outcome TEXT,
    summary TEXT,
    transcript TEXT,
    recorded INTEGER NOT NULL DEFAULT 0,
    gate_decision TEXT
);

CREATE TABLE IF NOT EXISTS gate_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    allowed INTEGER NOT NULL,
    reason TEXT NOT NULL,
    at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dnc (
    phone_e164 TEXT PRIMARY KEY,
    reason TEXT,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL UNIQUE REFERENCES leads(id),
    package_id TEXT,
    contact_email TEXT,
    status TEXT NOT NULL DEFAULT 'new',  -- new, awaiting_review, approved, deployed, rejected
    payment_status TEXT NOT NULL DEFAULT 'unpaid',
    payment_link TEXT,
    site_slug TEXT,
    site_url TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

LEAD_STATUSES = (
    "new", "verified", "ready", "calling", "yes", "no", "callback", "dnc", "disqualified", "voicemail",
)


def connect(path: str | Path = "data/agency.db") -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def insert_lead(conn: sqlite3.Connection, **fields) -> int | None:
    """Insert a lead; returns new id, or None if (source, source_id) already exists."""
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    cur = conn.execute(f"INSERT OR IGNORE INTO leads ({cols}) VALUES ({marks})", tuple(fields.values()))
    conn.commit()
    return cur.lastrowid if cur.rowcount else None


def get_lead(conn: sqlite3.Connection, lead_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
