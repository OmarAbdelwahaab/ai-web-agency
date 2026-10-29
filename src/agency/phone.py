from __future__ import annotations

import phonenumbers


def to_e164(raw: str | None, region: str = "US") -> str | None:
    """Return a valid E.164 number or None."""
    if not raw:
        return None
    try:
        num = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(num):
        return None
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)


def pretty_us(e164: str | None) -> str:
    if not e164:
        return ""
    try:
        return phonenumbers.format_number(phonenumbers.parse(e164, "US"), phonenumbers.PhoneNumberFormat.NATIONAL)
    except phonenumbers.NumberParseException:
        return e164
