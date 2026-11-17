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

CREATE TABLE IF NOT EXISTS legal_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attorney_name TEXT NOT NULL,
    law_firm TEXT,
    notes TEXT,
    reviewed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lead_enrichment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL UNIQUE REFERENCES leads(id),
    rating REAL,
    review_count INTEGER,
    top_reviews_json TEXT,
    categories_json TEXT,
    photo_refs_json TEXT,
    website_confirmed_none INTEGER NOT NULL DEFAULT 1,
    owner_notes TEXT,
    data_richness REAL NOT NULL DEFAULT 0.0,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_enrichment_lead ON lead_enrichment(lead_id);

CREATE TABLE IF NOT EXISTS design_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id),
    variant TEXT NOT NULL,
    criterion TEXT NOT NULL,
    score INTEGER NOT NULL CHECK (score >= 1 AND score <= 5),
    reviewer TEXT NOT NULL DEFAULT 'owner',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_design_scores_lead ON design_scores(lead_id);
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


def phone_in_leads(conn: sqlite3.Connection, phone: str | None) -> bool:
    """Check if a phone number already exists in the leads table across common formats."""
    if not phone:
        return False
    from agency.phone import to_e164

    norm = to_e164(phone)
    candidates = {phone}
    if norm:
        candidates.add(norm)
        if norm.startswith("+1") and len(norm) == 12:
            candidates.add(norm[2:])  # 10 digits
            candidates.add(norm[1:])  # 11 digits
    placeholders = ", ".join("?" for _ in candidates)
    row = conn.execute(
        f"SELECT 1 FROM leads WHERE phone_e164 IN ({placeholders}) LIMIT 1",
        tuple(candidates),
    ).fetchone()
    return row is not None


def record_legal_review(conn: sqlite3.Connection, attorney_name: str, law_firm: str = "", notes: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO legal_reviews (attorney_name, law_firm, notes) VALUES (?, ?, ?)",
        (attorney_name.strip(), law_firm.strip(), notes.strip()),
    )
    conn.commit()
    return cur.lastrowid


def has_legal_review(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM legal_reviews").fetchone()
    return bool(row and row[0] > 0)


def save_enrichment(
    conn: sqlite3.Connection,
    lead_id: int,
    *,
    rating: float | None = None,
    review_count: int | None = None,
    top_reviews_json: str | None = None,
    categories_json: str | None = None,
    photo_refs_json: str | None = None,
    website_confirmed_none: bool = True,
    owner_notes: str | None = None,
    data_richness: float = 0.0,
    raw_json: str | None = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO lead_enrichment (
            lead_id, rating, review_count, top_reviews_json, categories_json,
            photo_refs_json, website_confirmed_none, owner_notes, data_richness, raw_json,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(lead_id) DO UPDATE SET
            rating = coalesce(excluded.rating, lead_enrichment.rating),
            review_count = coalesce(excluded.review_count, lead_enrichment.review_count),
            top_reviews_json = coalesce(excluded.top_reviews_json, lead_enrichment.top_reviews_json),
            categories_json = coalesce(excluded.categories_json, lead_enrichment.categories_json),
            photo_refs_json = coalesce(excluded.photo_refs_json, lead_enrichment.photo_refs_json),
            website_confirmed_none = excluded.website_confirmed_none,
            owner_notes = coalesce(excluded.owner_notes, lead_enrichment.owner_notes),
            data_richness = excluded.data_richness,
            raw_json = coalesce(excluded.raw_json, lead_enrichment.raw_json),
            updated_at = datetime('now')
        """,
        (
            lead_id,
            rating,
            review_count,
            top_reviews_json,
            categories_json,
            photo_refs_json,
            1 if website_confirmed_none else 0,
            owner_notes,
            data_richness,
            raw_json,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM lead_enrichment WHERE lead_id = ?", (lead_id,)).fetchone()
    return row[0] if row else cur.lastrowid


def get_enrichment(conn: sqlite3.Connection, lead_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM lead_enrichment WHERE lead_id = ?", (lead_id,)).fetchone()


def add_owner_note(conn: sqlite3.Connection, lead_id: int, notes: str) -> None:
    note_text = notes.strip()
    if not note_text:
        return
    conn.execute(
        """
        INSERT INTO lead_enrichment (lead_id, owner_notes, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(lead_id) DO UPDATE SET
            owner_notes = CASE
                WHEN lead_enrichment.owner_notes IS NULL OR lead_enrichment.owner_notes = '' THEN excluded.owner_notes
                ELSE lead_enrichment.owner_notes || char(10) || excluded.owner_notes
            END,
            updated_at = datetime('now')
        """,
        (lead_id, note_text),
    )
    conn.execute(
        """
        UPDATE leads
        SET notes = CASE
            WHEN notes IS NULL OR notes = '' THEN ?
            ELSE notes || char(10) || ?
        END
        WHERE id = ?
        """,
        (note_text, note_text, lead_id),
    )
    conn.commit()


def record_design_score(
    conn: sqlite3.Connection,
    lead_id: int,
    variant: str,
    criterion: str,
    score: int,
    reviewer: str = "owner",
) -> int:
    """Record a 1-5 design score for a specific variant and criterion."""
    if score < 1 or score > 5:
        raise ValueError(f"Score must be between 1 and 5 (got {score})")
    cur = conn.execute(
        """
        INSERT INTO design_scores (lead_id, variant, criterion, score, reviewer, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        """,
        (lead_id, variant.lower(), criterion.lower(), score, reviewer),
    )
    conn.commit()
    return cur.lastrowid


def get_design_scores(conn: sqlite3.Connection, lead_id: int | None = None) -> list[sqlite3.Row]:
    """Retrieve design scores, optionally filtered by lead_id."""
    if lead_id is not None:
        return conn.execute(
            "SELECT * FROM design_scores WHERE lead_id = ? ORDER BY id ASC",
            (lead_id,),
        ).fetchall()
    return conn.execute("SELECT * FROM design_scores ORDER BY id ASC").fetchall()


