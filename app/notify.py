"""One-time verification codes for new accounts (WhatsApp or email). Nothing is sent unless a channel is configured."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from .config import settings

log = logging.getLogger("rafiq.notify")


def send_email(to: str, subject: str, body: str) -> bool:
    s = settings()
    if not s.smtp_enabled:
        return False
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001 — never leak SMTP errors to the browser
        log.error("email send failed: %s", exc)
        return False


def send_code(channel, mode: str, phone: str, email: str | None, code: str, lang: str) -> bool:
    """Deliver a verification code. Returns True if it was handed to a delivery service."""
    if mode == "email" and email:
        subject = "Rafiq verification code" if lang == "en" else "رمز التحقق من رفيق"
        body = (f"Your Rafiq verification code is {code}. It expires in 15 minutes. If you didn't request it, ignore this email."
                if lang == "en" else f"رمز التحقق الخاص بك في رفيق هو {code}. ينتهي خلال 15 دقيقة. إن لم تطلبه فتجاهل هذه الرسالة.")
        return send_email(email, subject, body)
    if mode == "whatsapp":
        text = f"Rafiq verification code: {code}" if lang == "en" else f"رمز التحقق من رفيق: {code}"
        channel.send(phone, text, template="rafiq_verify", params=[code])
        return True
    return False
