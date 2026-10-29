"""Payment link generator supporting manual (default), stripe, and custom providers."""
from __future__ import annotations

import logging
import os

import httpx

from agency.config import Settings, get_settings

log = logging.getLogger(__name__)


def create_payment_link(
    provider: str,
    *,
    client_id: int,
    amount_usd: float | None,
    description: str,
    settings: Settings | None = None,
) -> str | None:
    """Return a payment URL, or None when payment is handled manually.

    - 'manual' (default): the owner sends an invoice or link by hand after the Telegram alert.
    - 'stripe': generates a Stripe Checkout Session via Stripe API using STRIPE_API_KEY.
    - 'custom': formats PAYMENT_LINK_TEMPLATE with client_id, amount_usd, and description.
    """
    s = settings or get_settings()
    p = (provider or s.payment_provider or "manual").lower().strip()

    if p == "manual":
        return None

    if p == "stripe":
        key = s.stripe_api_key or os.environ.get("STRIPE_API_KEY", "")
        if not key:
            raise ValueError("STRIPE_API_KEY is required when PAYMENT_PROVIDER=stripe")
        cents = int(round((amount_usd or 0) * 100))
        resp = httpx.post(
            "https://api.stripe.com/v1/checkout/sessions",
            auth=(key, ""),
            data={
                "payment_method_types[0]": "card",
                "line_items[0][price_data][currency]": "usd",
                "line_items[0][price_data][unit_amount]": str(cents),
                "line_items[0][price_data][product_data][name]": description or f"Website Setup #{client_id}",
                "line_items[0][quantity]": "1",
                "mode": "payment",
                "client_reference_id": str(client_id),
                "success_url": f"https://example.com/success?client_id={client_id}",
                "cancel_url": f"https://example.com/cancel?client_id={client_id}",
            },
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            log.error("Stripe Checkout creation failed: %s %s", resp.status_code, resp.text[:200])
            raise RuntimeError(f"Stripe API error {resp.status_code}: {resp.text[:200]}")
        return resp.json().get("url")

    if p == "custom":
        template = s.payment_link_template or os.environ.get("PAYMENT_LINK_TEMPLATE", "")
        if not template:
            raise ValueError("PAYMENT_LINK_TEMPLATE is required when PAYMENT_PROVIDER=custom")
        return template.format(client_id=client_id, amount_usd=amount_usd or 0, description=description)

    raise NotImplementedError(f"Payment provider '{provider}' is not supported")
