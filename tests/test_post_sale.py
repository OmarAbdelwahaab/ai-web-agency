import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agency.config import Settings
from agency.db import connect, init_db, insert_lead
from agency.notify import telegram
from agency.payments.links import create_payment_link
from agency.pipeline import post_sale


@pytest.fixture()
def post_sale_env(tmp_path):
    conn = connect(":memory:")
    init_db(conn)
    lid = insert_lead(
        conn,
        source="places",
        source_id="p301",
        name="Lone Star Locksmith",
        category="locksmith",
        phone_e164="+15125550133",
        city="Austin",
        state="TX",
        timezone="America/Chicago",
        status="ready",
    )
    s = Settings(
        agency_name="Apex Web Studio",
        output_dir=tmp_path / "output",
        pricing_path=Path("pricing.yaml"),
        telegram_token="test_token_123",
        telegram_chat_id="999888",
    )
    return conn, lid, s, tmp_path


# --- 1. Payment Link Tests ---

def test_payment_link_manual(post_sale_env):
    _, _, s, _ = post_sale_env
    assert create_payment_link("manual", client_id=1, amount_usd=299.0, description="Starter", settings=s) is None


def test_payment_link_custom(post_sale_env):
    _, _, s, _ = post_sale_env
    s_custom = Settings(
        payment_provider="custom",
        payment_link_template="https://pay.example.com/checkout?cid={client_id}&amt={amount_usd}",
    )
    link = create_payment_link("custom", client_id=42, amount_usd=499.0, description="Standard", settings=s_custom)
    assert link == "https://pay.example.com/checkout?cid=42&amt=499.0"

    with pytest.raises(ValueError, match="PAYMENT_LINK_TEMPLATE is required"):
        create_payment_link("custom", client_id=42, amount_usd=499.0, description="Standard", settings=Settings())


def test_payment_link_stripe(post_sale_env):
    _, _, _, _ = post_sale_env
    s_stripe = Settings(payment_provider="stripe", stripe_api_key="sk_test_123")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"url": "https://checkout.stripe.com/c/pay/cs_test_abc123"}

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        link = create_payment_link("stripe", client_id=10, amount_usd=299.0, description="Starter site", settings=s_stripe)
        assert link == "https://checkout.stripe.com/c/pay/cs_test_abc123"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["auth"] == ("sk_test_123", "")
        assert call_kwargs["data"]["line_items[0][price_data][unit_amount]"] == "29900"

    with pytest.raises(ValueError, match="STRIPE_API_KEY is required"):
        create_payment_link("stripe", client_id=10, amount_usd=299.0, description="Starter", settings=Settings(stripe_api_key=""))


def test_payment_link_unsupported():
    with pytest.raises(NotImplementedError, match="not supported"):
        create_payment_link("crypto_currency", client_id=1, amount_usd=100.0, description="Test")


# --- 2. Deal Handling & Idempotency Tests ---

def test_handle_deal_end_to_end(post_sale_env):
    conn, lid, s, _ = post_sale_env

    with patch("agency.pipeline.post_sale.send_message", return_value=True) as mock_send_msg:
        res = post_sale.handle_deal(
            conn,
            lid,
            package_id="starter",
            contact_email="owner@lonestarlock.com",
            call_notes="24/7 lockout service and commercial rekeying",
            settings=s,
        )

    assert "client_id" in res
    cid = res["client_id"]
    assert Path(res["site_dir"]).exists()

    # Check client database record
    client_row = conn.execute("SELECT * FROM clients WHERE id = ?", (cid,)).fetchone()
    assert client_row["lead_id"] == lid
    assert client_row["package_id"] == "starter"
    assert client_row["contact_email"] == "owner@lonestarlock.com"
    assert client_row["status"] == "awaiting_review"
    assert client_row["payment_status"] == "unpaid"

    # Check lead status transitioned to 'yes'
    lead_row = conn.execute("SELECT status FROM leads WHERE id = ?", (lid,)).fetchone()
    assert lead_row["status"] == "yes"

    # Telegram message sent with review & approval instructions
    mock_send_msg.assert_called_once()
    alert_text = mock_send_msg.call_args[0][0]
    assert f"New client #{cid}: Lone Star Locksmith" in alert_text
    assert f"/approve {cid}" in alert_text
    assert f"/reject {cid}" in alert_text

    # --- Idempotency Check: Calling handle_deal again returns existing client ---
    mock_send_msg.reset_mock()
    res2 = post_sale.handle_deal(
        conn,
        lid,
        package_id="starter",
        contact_email="owner@lonestarlock.com",
        settings=s,
    )
    assert res2 == {"client_id": cid, "existing": True}
    mock_send_msg.assert_not_called()

    # Total clients remains 1
    count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    assert count == 1


def test_handle_deal_with_qa_enabled(post_sale_env):
    from agency.sitegen.qa import DetectResult

    conn, lid, s, tmp_path = post_sale_env
    s_qa = Settings(
        agency_name=s.agency_name,
        output_dir=tmp_path / "output_qa",
        pricing_path=s.pricing_path,
        telegram_token=s.telegram_token,
        telegram_chat_id=s.telegram_chat_id,
        qa_enabled=True,
    )

    with patch("agency.sitegen.qa.run_detector", return_value=DetectResult("clean")) as mock_det, \
         patch("agency.sitegen.qa.mobile_screenshot", return_value=True) as mock_shot, \
         patch("agency.pipeline.post_sale.send_photo", return_value=True) as mock_photo, \
         patch("agency.pipeline.post_sale.send_message", return_value=True) as mock_msg:

        res = post_sale.handle_deal(
            conn,
            lid,
            package_id="standard",
            contact_email="info@lonestarlock.com",
            settings=s_qa,
        )

    cid = res["client_id"]
    mock_det.assert_called_once()
    mock_shot.assert_called_once()
    mock_photo.assert_called_once()
    mock_msg.assert_called_once()
    assert f"Mobile preview for client #{cid}" in mock_photo.call_args[0][1]


# --- 3. Client Finalization & Deploy Flow Tests ---

def test_finalize_client_deploy_disabled(post_sale_env):
    conn, lid, s, _ = post_sale_env
    res = post_sale.handle_deal(conn, lid, package_id="starter", contact_email="", settings=s)
    cid = res["client_id"]

    # DEPLOY_ENABLED is False by default
    s_no_deploy = Settings(deploy_enabled=False, output_dir=s.output_dir)
    with pytest.raises(RuntimeError, match="DEPLOY_ENABLED is false"):
        post_sale.finalize_client(conn, cid, settings=s_no_deploy)


def test_finalize_client_deploy_success_and_email(post_sale_env):
    conn, lid, s, _ = post_sale_env
    res = post_sale.handle_deal(conn, lid, package_id="starter", contact_email="client@test.com", settings=s)
    cid = res["client_id"]

    s_deploy = Settings(
        deploy_enabled=True,
        output_dir=s.output_dir,
        agency_name=s.agency_name,
    )

    with patch("agency.sitegen.deploy.deploy_pages", return_value="https://lonestar-lock.pages.dev") as mock_deploy, \
         patch("agency.notify.email.email_configured", return_value=True), \
         patch("agency.notify.email.send_site_link") as mock_email:

        summary = post_sale.finalize_client(conn, cid, settings=s_deploy)

    assert "Deployed: https://lonestar-lock.pages.dev" in summary
    assert "emailed to client" in summary
    mock_deploy.assert_called_once()
    mock_email.assert_called_once_with("client@test.com", "Lone Star Locksmith", "https://lonestar-lock.pages.dev", "Apex Web Studio")

    client_row = conn.execute("SELECT * FROM clients WHERE id = ?", (cid,)).fetchone()
    assert client_row["status"] == "deployed"
    assert client_row["site_url"] == "https://lonestar-lock.pages.dev"

    # Repeated finalize returns already deployed
    res_repeat = post_sale.finalize_client(conn, cid, settings=s_deploy)
    assert "Already deployed: https://lonestar-lock.pages.dev" in res_repeat


def test_finalize_client_invalid_status(post_sale_env):
    conn, lid, s, _ = post_sale_env
    res = post_sale.handle_deal(conn, lid, package_id="starter", contact_email="", settings=s)
    cid = res["client_id"]

    # Reject client
    conn.execute("UPDATE clients SET status = 'rejected' WHERE id = ?", (cid,))
    conn.commit()

    err = post_sale.finalize_client(conn, cid, settings=s)
    assert f"Client {cid} is rejected, not awaiting review" in err

    not_found = post_sale.finalize_client(conn, 9999, settings=s)
    assert "Client 9999 not found" in not_found


# --- 4. Telegram Commands & Bot Loop Tests ---

def test_telegram_commands(post_sale_env):
    conn, lid, s, _ = post_sale_env

    # /status
    st = telegram.handle_command(conn, "/status", s)
    assert "Leads: ready=1" in st

    # /clients (empty before handle_deal)
    cl = telegram.handle_command(conn, "/clients", s)
    assert "No clients yet" in cl

    # Create client
    deal = post_sale.handle_deal(conn, lid, package_id="starter", contact_email="a@b.com", settings=s)
    cid = deal["client_id"]

    # /clients (shows client)
    cl2 = telegram.handle_command(conn, "/clients", s)
    assert f"#{cid} awaiting_review unpaid" in cl2

    # /preview
    prev = telegram.handle_command(conn, f"/preview {cid}", s)
    assert f"Client #{cid} preview:" in prev
    assert "awaiting_review" in prev

    # /preview without ID
    assert telegram.handle_command(conn, "/preview", s) == "Usage: /preview <client_id>"

    # /paid
    paid_res = telegram.handle_command(conn, f"/paid {cid}", s)
    assert f"Client {cid} marked paid" in paid_res
    c_row = conn.execute("SELECT payment_status FROM clients WHERE id = ?", (cid,)).fetchone()
    assert c_row["payment_status"] == "paid"

    # /paid without ID
    assert telegram.handle_command(conn, "/paid", s) == "Usage: /paid <client_id>"

    # /reject
    rej_res = telegram.handle_command(conn, f"/reject {cid}", s)
    assert f"Client {cid} rejected" in rej_res
    c_row = conn.execute("SELECT status FROM clients WHERE id = ?", (cid,)).fetchone()
    assert c_row["status"] == "rejected"

    # /approve with deploy error reported cleanly
    # Set back to awaiting_review to test approve
    conn.execute("UPDATE clients SET status = 'awaiting_review' WHERE id = ?", (cid,))
    conn.commit()
    app_res = telegram.handle_command(conn, f"/approve {cid}", s)
    assert "Deploy failed: DEPLOY_ENABLED is false" in app_res

    # /help / unrecognized
    assert "Commands: /status, /clients, /preview <id>, /paid <id>, /approve <id>, /reject <id>" in telegram.handle_command(conn, "/unknown", s)


def test_telegram_run_bot_loop(post_sale_env):
    conn, lid, s, _ = post_sale_env

    mock_updates_resp = MagicMock()
    mock_updates_resp.status_code = 200
    mock_updates_resp.json.return_value = {
        "ok": True,
        "result": [
            {
                "update_id": 101,
                "message": {
                    "chat": {"id": 12345},  # wrong chat id -> ignored
                    "text": "/status",
                },
            },
            {
                "update_id": 102,
                "message": {
                    "chat": {"id": int(s.telegram_chat_id)},  # owner chat id -> handled
                    "text": "/status",
                },
            },
        ],
    }

    with patch("httpx.get", return_value=mock_updates_resp) as mock_get, \
         patch("agency.notify.telegram.send_message", return_value=True) as mock_send:
        telegram.run_bot(conn, settings=s, once=True)

    mock_get.assert_called_once()
    # Exactly one reply sent (for update 102, update 101 was ignored)
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][0]
    assert "Leads: ready=1" in sent_text
