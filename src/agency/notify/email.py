"""Optional: email the finished site link to a client who agreed to the deal."""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def email_configured() -> bool:
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"))


def send_site_link(to: str, business: str, url: str, agency: str) -> None:
    msg = EmailMessage()
    msg["From"], msg["To"] = os.environ["SMTP_FROM"], to
    msg["Subject"] = f"Your new website for {business}"
    msg.set_content(
        f"Hi,\n\nThanks for choosing {agency}. Your website is ready to review:\n\n{url}\n\n"
        "Reply to this email with any changes you would like.\n\n" + agency
    )
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587"))) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(msg)
