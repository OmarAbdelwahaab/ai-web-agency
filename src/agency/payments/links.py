from __future__ import annotations


def create_payment_link(provider: str, *, client_id: int, amount_usd: float | None, description: str) -> str | None:
    """Return a payment URL, or None when payment is handled manually.

    'manual' (default): the owner sends an invoice or link by hand after the Telegram alert.
    Real providers (Stripe, PayPal, Payoneer, Lemon Squeezy, ...) are a Phase 6 task. Availability depends on
    the owner's country, so pick the provider first, then implement it here behind this function.
    """
    if provider == "manual":
        return None
    raise NotImplementedError(f"Payment provider '{provider}' is not implemented yet (see docs/ROADMAP.md, phase 6)")
