"""Real messages to users: verification codes and the welcome message. Nothing is sent unless a channel is configured;
the welcome is always stored in the patient's in-app chat so it is visible on the web too.

HONESTY RULE: the text only says "official service" when the operator has opted in (RAFIQ_OFFICIAL=1) and the
system is not in demo mode. The real proof of identity on WhatsApp is a verified Meta Business account (green tick);
apply for it, and publish your sender numbers on your clinic's website and posters.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from . import messages as M
from .config import settings
from .db import DB, iso, utcnow

log = logging.getLogger("rafiq.notify")


def org() -> dict:
    s = settings()
    return {"name": s.clinic_name, "phone": s.org_phone, "url": s.org_url, "official": s.may_claim_official, "demo": s.demo_seed}


def _contact(lang: str) -> str:
    o = org()
    bits = [x for x in (o["phone"], o["url"]) if x]
    if not bits:
        return ""
    return ("\nContact: " if lang == "en" else "\nللتواصل: ") + " · ".join(bits)


def welcome_text(name: str, lang: str) -> str:
    o = org()
    key = "welcome_registered_demo" if o["demo"] else "welcome_registered_official" if o["official"] else "welcome_registered"
    return M.shared(key, lang, name=name, clinic=o["name"], contact=_contact(lang))


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
    except Exception as exc:  # noqa: BLE001 - never leak SMTP errors to the browser
        log.error("email send failed: %s", exc)
        return False


def send_code(channel, mode: str, phone: str, email: str | None, code: str, lang: str) -> bool:
    """Deliver a verification code that also tells the user WHO is sending it. True if handed to a delivery service."""
    text = M.shared("verify_code", lang, clinic=org()["name"], code=code)
    if mode == "email" and email:
        return send_email(email, "Rafiq verification code" if lang == "en" else "رمز التحقق من رفيق", text)
    if mode == "whatsapp":
        channel.send(phone, text, template="rafiq_verify", params=[code])
        return True
    return False


def send_welcome(db: DB, channel, patient: dict) -> dict:
    """Send the welcome message for a newly active account. Returns what was done (for audit / tests)."""
    lang = "en" if patient["dialect"] == "en" else "ar"
    text = welcome_text(patient["name"], lang)
    # 1) always visible in the patient's own chat on the website
    db.execute("INSERT INTO messages(patient_id, direction, body, created_at) VALUES (?,?,?,?)", (patient["id"], "out", text, iso(utcnow())))
    done = {"in_app": True, "whatsapp": False, "email": False}
    o = org()
    # 2) a real WhatsApp message (approved template; works outside the 24h window)
    if getattr(channel, "name", "") == "whatsapp":
        channel.send(patient["phone"], text, template="rafiq_welcome_official", params=[patient["name"], o["name"], o["phone"] or "-"])
        done["whatsapp"] = True
    # 3) and an email, if we have an address and SMTP is configured
    if patient.get("email") and settings().smtp_enabled:
        done["email"] = send_email(patient["email"], "Welcome to Rafiq" if lang == "en" else "مرحبًا بك في رفيق", text)
    db.audit("system", "welcome_sent", patient["id"], str({k: v for k, v in done.items() if v}))
    return done
