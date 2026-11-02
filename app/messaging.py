"""Doctor ↔ patient messaging with automatic replies (mixin for Engine).

Rules (safety first):
  * A clinician can message ONLY patients assigned to them (enforced in the API); never another staff member or a free phone number.
  * Opt-out, emergency red flags and breast-concern screens still run on every patient message BEFORE anything is routed to a doctor.
  * While a thread is open (48 h after the doctor writes) the patient's plain replies go to the doctor, who is not asked to wait for a bot;
    the patient gets an AUTOMATIC acknowledgement (different outside clinic hours). Typing "start" returns to the check-in questions.
  * A clinician who writes to the bot's number from their own phone gets an AUTOMATIC digest of their open alerts, never a route to patients.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import messages as M
from . import nlu
from .config import emergency_number, settings
from .db import iso, parse_iso

THREAD_HOURS = 48
ACK_EVERY = timedelta(minutes=30)
_BOT_WORDS = {"ابدا", "start", "begin", "checkin"}
_LINK = re.compile(r"(https?://|www\.|\b\w+\.(com|net|org|io|me|ly|co)\b)", re.I)


def clean_staff_text(text: str) -> str:
    """Normalise a doctor's message. Links are refused: a hijacked staff account must not be able to phish patients."""
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text or "").strip()
    if not t:
        raise ValueError("The message is empty.")
    if len(t) > 1000:
        raise ValueError("The message is too long (max 1000 characters).")
    if _LINK.search(t):
        raise ValueError("Links are not allowed in messages to patients.")
    return t


class MessagingMixin:
    # ── thread state ────────────────────────────────────────────────────────
    def _thread_active(self, p: dict) -> bool:
        until = parse_iso(p.get("clinician_thread_until"))
        return bool(until and until > self.now())

    def _wants_bot(self, text: str) -> bool:
        return bool(set(nlu.tokens(text)) & _BOT_WORDS) or nlu.is_help(text)

    def _clinic_open(self, p: dict) -> tuple[bool, str]:
        """(is the clinic open now in the patient's local time, opening time)"""
        try:
            a, b = settings().clinic_hours.split("-")
            local = self.now().astimezone(ZoneInfo(p["tz"]))
            mins = local.hour * 60 + local.minute
            f = lambda x: int(x[:2]) * 60 + int(x[3:5])  # noqa: E731
            return f(a) <= mins < f(b), a
        except Exception:  # noqa: BLE001 - a bad setting must never block a patient
            return True, ""

    # ── doctor → patient ────────────────────────────────────────────────────
    def staff_send(self, p: dict, sender: str, text: str) -> dict:
        """Deliver a clinician's message in-app and, if configured, on WhatsApp. Returns a delivery receipt for the doctor."""
        self._out = []
        use_template = self.channel.name == "whatsapp" and not self._in_window(p)
        wire = f"{sender}: {text}"
        ok = self.deliver(
            p, text, kind="clinician", sender=sender, wire_text=wire,
            template="rafiq_clinician_message" if use_template else None,
            params=[sender, re.sub(r"\s*\n+\s*", " | ", text)[:900]] if use_template else None)
        self._save(p["id"], clinician_thread_until=iso(self.now() + timedelta(hours=THREAD_HOURS)))
        whatsapp = "off" if self.channel.name != "whatsapp" else ("failed" if ok is False else "template" if use_template else "sent")
        return {"in_app": True, "whatsapp": whatsapp, "thread_hours": THREAD_HOURS}

    # ── patient → doctor (automatic acknowledgement) ────────────────────────
    def _route_to_clinician(self, p: dict, msg_id: int | None) -> None:
        if msg_id:
            self.db.execute("UPDATE messages SET kind='clinician' WHERE id=?", (msg_id,))
        last = self.db.one("SELECT created_at FROM messages WHERE patient_id=? AND kind='thread_ack' ORDER BY id DESC LIMIT 1", (p["id"],))
        if last and self.now() - parse_iso(last["created_at"]) < ACK_EVERY:
            return                                              # don't repeat the acknowledgement on every line she types
        c = self.db.one("SELECT name FROM clinicians WHERE id=?", (p["clinician_id"],)) if p["clinician_id"] else None
        is_open, opens = self._clinic_open(p)
        key = "thread_ack" if is_open else "thread_ack_closed"
        self.deliver(p, self.sh(p, key, doctor=c["name"] if c else ("your clinic" if M._lang(p["dialect"]) == "en" else "العيادة"), hours=opens), kind="thread_ack")

    # ── clinician writes to the bot's number ────────────────────────────────
    def find_clinician_by_phone(self, phone: str) -> dict | None:
        d = "".join(ch for ch in phone if ch.isdigit())
        for c in self.db.all("SELECT * FROM clinicians WHERE phone IS NOT NULL"):
            if "".join(ch for ch in c["phone"] if ch.isdigit()) == d:
                return c
        return None

    def handle_staff_inbound(self, c: dict, phone: str, text: str) -> list[str]:
        rows = self.db.all(
            "SELECT a.level, a.summary_en, a.summary_ar, p.name FROM alerts a JOIN patients p ON p.id=a.patient_id "
            "WHERE a.status='open' AND p.clinician_id=? ORDER BY a.level DESC, a.created_at DESC", (c["id"],))
        lang = "ar" if c["language"] == "ar" else "en"
        items = []
        for r in rows[:5]:
            lines = (r["summary_ar"] if lang == "ar" else r["summary_en"]).split("\n")
            items.append((r["level"], r["name"], (lines[1] if len(lines) > 1 else lines[0]).lstrip("• ").strip()[:90]))
        s = settings()
        reply = M.staff_overview_text(lang, c["name"], items, len(rows), s.app_url or s.org_url)
        self.staff_channel.send(phone, reply)
        return [reply]
