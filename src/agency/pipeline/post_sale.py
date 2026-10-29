"""yes -> client row -> payment link -> preview site -> Telegram alert -> owner approves -> deploy -> send link."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from agency.config import Settings, get_settings
from agency.db import get_lead
from agency.notify import email as email_mod
from agency.notify.telegram import send_message, send_photo
from agency.payments.links import create_payment_link
from agency.voice.prompts import load_pricing

log = logging.getLogger(__name__)


def _package(pricing: dict, package_id: str) -> dict:
    for p in pricing.get("packages", []):
        if p["id"] == package_id:
            return p
    return {"id": package_id, "name": package_id.capitalize(), "price_usd": 299}


def handle_deal(
    conn: sqlite3.Connection,
    lead_id: int,
    *,
    package_id: str,
    contact_email: str | None,
    call_notes: str = "",
    settings: Settings | None = None,
) -> dict:
    """Idempotent: calling twice for the same lead returns the existing client."""
    from agency.sitegen.ai_fill import fill_config
    from agency.sitegen.render import render_site

    s = settings or get_settings()
    existing = conn.execute("SELECT * FROM clients WHERE lead_id = ?", (lead_id,)).fetchone()
    if existing:
        return {"client_id": existing["id"], "existing": True}

    lead = get_lead(conn, lead_id)
    if lead is None:
        raise ValueError(f"Lead {lead_id} not found")

    try:
        cur = conn.execute(
            "INSERT INTO clients (lead_id, package_id, contact_email) VALUES (?, ?, ?)",
            (lead_id, package_id, contact_email),
        )
        client_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        existing = conn.execute("SELECT * FROM clients WHERE lead_id = ?", (lead_id,)).fetchone()
        if existing:
            return {"client_id": existing["id"], "existing": True}
        raise

    conn.execute("UPDATE leads SET status = 'yes' WHERE id = ?", (lead_id,))
    conn.commit()

    pkg = _package(load_pricing(s.pricing_path), package_id)
    link = create_payment_link(
        s.payment_provider,
        client_id=client_id,
        amount_usd=pkg.get("price_usd"),
        description=pkg.get("name", package_id),
        settings=s,
    )

    cfg = fill_config(lead, call_notes, credit=f"Website by {s.agency_name}", settings=s)
    site_dir = render_site(cfg, s.output_dir)
    conn.execute(
        "UPDATE clients SET payment_link = ?, site_slug = ?, status = 'awaiting_review' WHERE id = ?",
        (link, cfg.slug, client_id),
    )
    conn.commit()

    qa_line = ""
    if s.qa_enabled:
        from agency.sitegen import qa

        qa_line = qa.summarize_for_owner(qa.run_detector(site_dir)) + "\n"
        shot = Path(s.output_dir) / "_qa" / cfg.slug / "mobile.png"  # outside the site folder: never deployed
        if qa.mobile_screenshot(site_dir, shot):
            send_photo(shot, f"Mobile preview for client #{client_id}", settings=s)

    send_message(
        f"New client #{client_id}: {lead['name']}\n"
        f"Package: {pkg.get('name', package_id)} (${pkg.get('price_usd', '?')})\n"
        f"Phone: {lead['phone_e164']}  Email: {contact_email or 'not given'}\n"
        f"Payment: {link or 'send your invoice/link manually, then /paid ' + str(client_id)}\n"
        f"Preview built at: {site_dir}\n"
        f"{qa_line}"
        f"Reply /approve {client_id} to deploy, or /reject {client_id}.",
        settings=s,
    )
    return {"client_id": client_id, "site_dir": str(site_dir), "payment_link": link}


def finalize_client(conn: sqlite3.Connection, client_id: int, *, settings: Settings | None = None) -> str:
    from agency.sitegen.deploy import deploy_pages

    s = settings or get_settings()
    c = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    if c is None:
        return f"Client {client_id} not found"
    if c["status"] == "deployed":
        return f"Already deployed: {c['site_url']}"
    if c["status"] != "awaiting_review":
        return f"Client {client_id} is {c['status']}, not awaiting review"

    url = deploy_pages(Path(s.output_dir) / c["site_slug"], c["site_slug"], settings=s)
    conn.execute("UPDATE clients SET status = 'deployed', site_url = ? WHERE id = ?", (url, client_id))
    conn.commit()

    note = "" if c["payment_status"] == "paid" else " (payment not marked paid)"
    if c["contact_email"] and email_mod.email_configured():
        try:
            lead = get_lead(conn, c["lead_id"])
            email_mod.send_site_link(c["contact_email"], lead["name"], url, s.agency_name)
            note += "; emailed to client"
        except Exception as e:
            log.exception("failed to email site link to client")
            note += f"; email failed ({e})"
    return f"Deployed: {url}{note}"
