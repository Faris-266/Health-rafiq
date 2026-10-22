"""Conversation engine: daily check-in state machine + escalation.

Order of precedence for every inbound message
  1. Opt-out ("إيقاف" / stop)
  2. RED-FLAG SCREEN on the raw text, in ANY state, even before consent
  3. Consent gate
  4. Check-in state machine (glucose → bp → symptoms → meds)
Dangerous *measurements* escalate immediately, without waiting for the rest of the check-in.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import media as media_mod
from . import messages as M
from . import nlu
from .channels import Channel
from .config import emergency_number, load_thresholds
from .db import DB, iso, j, parse_iso, utcnow
from . import breast_ops
from .breast_flow import BREAST_STATES, BreastMixin
from .messaging import MessagingMixin
from .nlu import BREAST_CODES
from .triage import RED_FLAGS, Level, TriageInput, TriageResult, evaluate, is_plausible_bp, is_plausible_glucose

MAX_RETRIES = 2
WINDOW = timedelta(hours=24)


def digits(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())


class Engine(BreastMixin, MessagingMixin):
    def __init__(self, db: DB, channel: Channel, now_fn=utcnow, thresholds: dict | None = None, staff_channel: Channel | None = None):
        self.db = db
        self.channel = channel                      # patient-facing (WhatsApp, web chat, simulator)
        self.staff_channel = staff_channel or channel  # clinician alerts
        self.now = now_fn
        self.th = thresholds or load_thresholds()
        self._out: list[str] = []
        self._emergency = False
        self._src = "text"

    # ── small helpers ───────────────────────────────────────────────────────
    def patient(self, pid: int) -> dict:
        p = self.db.one("SELECT * FROM patients WHERE id=?", (pid,))
        if not p:
            raise KeyError(pid)
        return p

    def find_by_phone(self, phone: str) -> dict | None:
        d = digits(phone)
        for p in self.db.all("SELECT * FROM patients"):
            if digits(p["phone"]) == d:
                return p
        return None

    def _sess(self, p: dict) -> dict:
        return json.loads(p["session"] or "{}")

    def _save(self, pid: int, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.execute(f"UPDATE patients SET {cols} WHERE id=?", [*fields.values(), pid])

    def _set(self, pid: int, state: str, sess: dict | None = None) -> None:
        self._save(pid, state=state, session=j(sess if sess is not None else {}))

    def local_date(self, p: dict) -> str:
        return self.now().astimezone(ZoneInfo(p["tz"])).date().isoformat()

    def conditions(self, p: dict) -> set[str]:
        return {c.strip() for c in p["conditions"].split(",") if c.strip()}

    def t(self, p: dict, key: str, **kw) -> str:
        return M.tr(key, p["dialect"], p["gender"], emergency=emergency_number(p["country"]), **kw)

    def sh(self, p: dict, key: str, **kw) -> str:
        lang = M._lang(p["dialect"])
        default_clinic = "your clinic" if lang == "en" else "المركز الصحي"
        return M.shared(key, lang, emergency=emergency_number(p["country"]), clinic=kw.pop("clinic", default_clinic), **kw)

    def _in_window(self, p: dict) -> bool:
        if self.channel.name != "whatsapp":
            return True
        last = parse_iso(p["last_inbound_at"])
        return bool(last and self.now() - last < WINDOW)

    def deliver(self, p: dict, text: str, template: str | None = None, params: list[str] | None = None,
                kind: str = "bot", sender: str | None = None, wire_text: str | None = None):
        """Store the message (visible in the patient's chat) and hand it to the channel. Returns the channel's result."""
        self.db.execute(
            "INSERT INTO messages(patient_id, direction, body, kind, sender, created_at) VALUES (?,?,?,?,?,?)",
            (p["id"], "out", text, kind, sender, iso(self.now())),
        )
        self._out.append(text)
        return self.channel.send(p["phone"], wire_text or text, template=template, params=params)

    # ── public entry points ─────────────────────────────────────────────────
    def handle_inbound(self, phone: str, text: str = "", media: dict | None = None) -> list[str]:
        """Process one inbound message; returns the replies that were delivered."""
        self._out = []
        self._emergency = False
        p = self.find_by_phone(phone)
        if not p:
            staff = self.find_clinician_by_phone(phone)
            if staff:
                return self.handle_staff_inbound(staff, phone, text)
            self.channel.send(phone, M.shared("not_registered"))
            return [M.shared("not_registered")]
        now = self.now()
        self._save(p["id"], last_inbound_at=iso(now))
        p = self.patient(p["id"])
        if not p["active"]:
            return []

        source, msg_id = "text", None
        if media:
            if media["type"] == "audio":
                heard = media_mod.transcribe(media["bytes"], media.get("mime", "audio/ogg"))
                msg_id = self._log_in(p, "[🎤 voice note]" + (f" → {heard}" if heard else ""))
                if not heard:
                    self.deliver(p, self.sh(p, "audio_unsupported"))
                    return self._out
                text, source = heard, "voice"
                media = None
            else:
                self._log_in(p, "[📷 image]")
                self._handle_image(p, media)
                return self._out
        else:
            msg_id = self._log_in(p, text)

        # 1 ── opt-out
        if nlu.is_stop(text):
            self._save(p["id"], consent=0, active=0, state="idle", session="{}")
            self.db.audit("patient", "opt_out", p["id"])
            self.deliver(p, self.sh(p, "stopped"))
            return self._out

        # 2 ── red-flag screen (every message, every state)
        sym = nlu.analyze_symptoms(text)
        if sym.symptoms & RED_FLAGS:
            self._escalate_symptoms(p, sym.symptoms, text)
            return self._out

        # 3 ── breast concern screen: any reported breast change is handled at once (any state, even pre-consent)
        if sym.symptoms & BREAST_CODES:
            self._breast_report(p, sym.symptoms, text)
            return self._out

        # 4 ── consent gate
        if not p["consent"]:
            self._consent_flow(p, text)
            return self._out

        # 4b ── an open doctor↔patient thread: plain replies go to the doctor (with an automatic acknowledgement)
        if p["state"] == "idle" and self._thread_active(p) and not self._wants_bot(text):
            self._route_to_clinician(p, msg_id)
            return self._out

        # 5 ── state machine
        self._dispatch(p, text, sym, source)
        return self._out

    def _log_in(self, p: dict, body: str) -> int:
        return self.db.execute(
            "INSERT INTO messages(patient_id, direction, body, created_at) VALUES (?,?,?,?)",
            (p["id"], "in", body, iso(self.now())),
        )

    # ── consent ─────────────────────────────────────────────────────────────
    def send_welcome(self, p: dict) -> None:
        self._set(p["id"], "awaiting_consent")
        from .notify import org as _org, what_text as _what
        o = _org()
        ident = ""
        if o["official"]:
            ident = ("\nThis is an official service of " + o["name"] + ".") if M._lang(p["dialect"]) == "en" else ("\nهذه خدمة رسمية من " + o["name"] + ".")
        self.deliver(p, self.sh(p, "welcome_consent", name=p["name"], clinic=self._clinic_name(), what=_what(M._lang(p["dialect"]))) + ident,
                     template="rafiq_welcome", params=[p["name"]])

    def _clinic_name(self) -> str:
        from .config import settings
        return settings().clinic_name

    def _consent_flow(self, p: dict, text: str) -> None:
        if p["state"] != "awaiting_consent":
            self.send_welcome(p)
            return
        yn = nlu.parse_yes_no(text)
        if yn is True:
            self._save(p["id"], consent=1, consent_at=iso(self.now()))
            self.db.audit("patient", "consent_given", p["id"])
            self._set(p["id"], "idle")
            self.deliver(p, self.sh(p, "consent_ok"))
            self.start_checkin(p["id"], scheduled=False)
        elif yn is False:
            self._save(p["id"], consent=0, active=0)
            self._set(p["id"], "idle")
            self.deliver(p, self.sh(p, "stopped"))
        else:
            self.deliver(p, self.sh(p, "consent_reask"))

    # ── check-in lifecycle ──────────────────────────────────────────────────
    def start_checkin(self, pid: int, scheduled: bool = True, kind: str | None = None) -> None:
        self._out = []
        p = self.patient(pid)
        if not p["consent"]:
            self.send_welcome(p)
            return
        conds = self.conditions(p)
        kind = kind or ("breast" if "breast" in conds and not conds & {"diabetes", "hypertension"} else "chronic")
        if kind == "breast":
            self._begin(p, self._new_breast_session(p), scheduled, "rafiq_monthly_checkin")
            return
        steps = (["glucose"] if "diabetes" in conds else []) + (["bp"] if "hypertension" in conds else []) + ["symptoms", "meds"]
        sess = {"steps": steps, "glucose": None, "bp": None, "symptoms": [], "free_text": None,
                "meds": None, "source": "text", "retries": 0, "started_at": iso(self.now()), "notes": []}
        self._begin(p, sess, scheduled, "rafiq_daily_checkin")

    def _begin(self, p: dict, sess: dict, scheduled: bool, template: str) -> None:
        steps = sess["steps"]
        greeting = self.t(p, "greet" if scheduled else "hello", name=p["name"])
        if self._in_window(p):
            self.deliver(p, greeting)
            self._set(p["id"], f"awaiting_{steps[0]}", sess)
            self.deliver(p, self.t(p, f"ask_{steps[0]}"))
        else:
            # Business-initiated outside the 24h window → approved template only.
            self.deliver(p, greeting, template=template, params=[p["name"]])
            self._set(p["id"], "awaiting_start", sess)

    def _ask(self, p: dict, step: str) -> None:
        self.deliver(p, self.t(p, f"ask_{step}"))

    def _advance(self, p: dict, sess: dict) -> None:
        if sess["steps"]:
            sess["steps"].pop(0)
        sess["retries"] = 0
        if sess["steps"]:
            nxt = sess["steps"][0]
            self._set(p["id"], f"awaiting_{nxt}", sess)
            self._ask(p, nxt)
        else:
            self._finalize(p, sess)

    def _retry(self, p: dict, sess: dict, key: str, **kw) -> None:
        sess["retries"] += 1
        if sess["retries"] > MAX_RETRIES:
            sess["notes"].append(f"{sess['steps'][0]}_unanswered")
            self._advance(p, sess)
            return
        self._set(p["id"], p["state"], sess)
        if key in M.SHARED:
            self.deliver(p, self.sh(p, key, **kw))
        else:
            self.deliver(p, self.t(p, key, **kw))

    # ── state dispatch ──────────────────────────────────────────────────────
    def _dispatch(self, p: dict, text: str, sym: nlu.SymptomResult, source: str) -> None:
        state = p["state"]
        sess = self._sess(p)

        if state == "idle":
            if self._handle_reminder_reply(p, text):
                return
            if nlu.is_help(text):
                self.deliver(p, self.sh(p, "help"))
                return
            self.start_checkin(p["id"], scheduled=False)
            if nlu.has_digits(text):  # "سكري 120" — use it as the first answer
                p = self.patient(p["id"])
                if p["state"].startswith("awaiting_") and p["state"] != "awaiting_start":
                    self._dispatch(p, text, sym, source)
            return

        if nlu.is_help(text) and not nlu.has_digits(text):
            self.deliver(p, self.sh(p, "help"))
            return

        if state == "awaiting_start":
            state = f"awaiting_{sess['steps'][0]}"
            self._set(p["id"], state, sess)
            p = self.patient(p["id"])
            if not nlu.has_digits(text):
                self._ask(p, sess["steps"][0])
                return

        self._src = source
        if state == "awaiting_glucose":
            self._step_glucose(p, sess, text)
        elif state == "awaiting_bp":
            self._step_bp(p, sess, text)
        elif state == "awaiting_symptoms":
            self._step_symptoms(p, sess, text, sym)
        elif state == "awaiting_meds":
            self._step_meds(p, sess, text)
        elif state == "confirm_ocr":
            self._step_confirm_ocr(p, sess, text)
        elif state in BREAST_STATES:
            self._breast_step(p, sess, text, sym, state)
        else:  # unknown state → recover
            self._set(p["id"], "idle")
            self.deliver(p, self.t(p, "unclear"))

    # ── steps ───────────────────────────────────────────────────────────────
    def _step_glucose(self, p: dict, sess: dict, text: str) -> None:
        # Patient may give both numbers at once: "سكري 110 وضغطي 130/85"
        if "bp" in sess["steps"] and sess["bp"] is None:
            bp = nlu.parse_bp(text, allow_loose=False)
            if bp and is_plausible_bp(bp.sys, bp.dia, self.th):
                sess["bp"] = {"sys": bp.sys, "dia": bp.dia, "source": "text"}
                sess["steps"].remove("bp")
        g = nlu.parse_glucose(text)
        if g is None or g.ambiguous:
            return self._retry(p, sess, "unclear_reading", example=M.CHIP_EXAMPLES["glucose"])
        if not is_plausible_glucose(g.mgdl, self.th):
            return self._retry(p, sess, "implausible", value=f"{g.raw:g} {g.unit}")
        self._accept_glucose(p, sess, g.mgdl, g.context or "fasting", getattr(self, "_src", "text"))

    def _accept_glucose(self, p: dict, sess: dict, mgdl: float, context: str, source: str) -> None:
        sess["glucose"] = {"mgdl": mgdl, "context": context, "source": source}
        if self._quick_urgent(p, sess):
            return
        self._advance(p, sess)

    def _step_bp(self, p: dict, sess: dict, text: str) -> None:
        bp = nlu.parse_bp(text, allow_loose=True)
        if bp is None:
            return self._retry(p, sess, "unclear_reading", example=M.CHIP_EXAMPLES["bp"])
        if not is_plausible_bp(bp.sys, bp.dia, self.th):
            return self._retry(p, sess, "implausible", value=f"{bp.sys}/{bp.dia}")
        self._accept_bp(p, sess, bp.sys, bp.dia, getattr(self, "_src", "text"))

    def _accept_bp(self, p: dict, sess: dict, s: int, d: int, source: str) -> None:
        sess["bp"] = {"sys": s, "dia": d, "source": source}
        if self._quick_urgent(p, sess):
            return
        self._advance(p, sess)

    def _step_symptoms(self, p: dict, sess: dict, text: str, sym: nlu.SymptomResult) -> None:
        if sym.symptoms:
            sess["symptoms"] = sorted(sym.symptoms)
        elif sym.none_declared:
            sess["symptoms"] = []
        elif sym.unrecognised:
            sess["symptoms"], sess["free_text"] = [], text.strip()
        else:
            return self._retry(p, sess, "unclear")
        self._advance(p, sess)

    def _step_meds(self, p: dict, sess: dict, text: str) -> None:
        yn = nlu.parse_yes_no(text)
        if yn is None:
            return self._retry(p, sess, "unclear")
        sess["meds"] = yn
        self._advance(p, sess)

    # ── images (glucometer / BP cuff) ───────────────────────────────────────
    def _handle_image(self, p: dict, media: dict) -> None:
        state, sess = p["state"], self._sess(p)
        if state not in ("awaiting_glucose", "awaiting_bp") or not p["consent"]:
            self.deliver(p, self.sh(p, "image_idle"))
            return
        data = media_mod.read_meter(media["bytes"], media.get("mime", "image/jpeg"))
        step = sess["steps"][0]
        if step == "glucose" and data and data.get("glucose"):
            val = float(data["glucose"])
            mg = round(val * 18.016) if (data.get("unit") == "mmol/L" or val < 20) else val
            sess["pending_ocr"] = {"kind": "glucose", "mgdl": mg}
            shown = f"{mg:.0f} mg/dL"
        elif step == "bp" and data and data.get("systolic") and data.get("diastolic"):
            sess["pending_ocr"] = {"kind": "bp", "sys": int(data["systolic"]), "dia": int(data["diastolic"])}
            shown = f"{int(data['systolic'])}/{int(data['diastolic'])}"
        else:
            self.deliver(p, self.sh(p, "ocr_fail"))
            return
        self._set(p["id"], "confirm_ocr", sess)
        self.deliver(p, self.sh(p, "ocr_confirm", value=shown))

    def _step_confirm_ocr(self, p: dict, sess: dict, text: str) -> None:
        pend = sess.pop("pending_ocr", None)
        yn = nlu.parse_yes_no(text)
        step = sess["steps"][0]
        if yn and pend:
            if pend["kind"] == "glucose":
                return self._accept_glucose(p, sess, pend["mgdl"], "fasting", "image")
            return self._accept_bp(p, sess, pend["sys"], pend["dia"], "image")
        self._set(p["id"], f"awaiting_{step}", sess)
        self.deliver(p, self.sh(p, "ocr_fail"))

    # ── medication reminders ────────────────────────────────────────────────
    def _handle_reminder_reply(self, p: dict, text: str) -> bool:
        if not p["pending_reminder"]:
            return False
        yn = nlu.parse_yes_no(text)
        if yn is None:
            return False
        pr = json.loads(p["pending_reminder"])
        kind = pr.get("type", "med")
        self._save(p["id"], pending_reminder=None)
        if kind == "screening":
            if yn:
                self._save(p["id"], screening_booked_at=iso(self.now()))
            self.deliver(p, self.t(p, "screening_booked_ack" if yn else "screening_nobook_ack"))
            return True
        if kind == "referral":
            ref = self.db.one("SELECT * FROM referrals WHERE id=?", (pr["referral_id"],))
            if ref and yn and ref["status"] in ("new", "contacted"):
                breast_ops.update_referral(self.db, ref["id"], {"status": "booked"}, "patient", self.now())
            elif ref and not yn:
                self.raise_alert(p, Level.WATCH, [{"code": "referral_no_booking", "level": 1, "data": {"referral": ref["id"]}}])
            self.deliver(p, self.t(p, "referral_booked_ack" if yn else "referral_nobook_ack"))
            return True
        self.db.execute(
            "UPDATE reminder_log SET taken=? WHERE patient_id=? AND med_id=? AND local_date=? AND slot=?",
            (1 if yn else 0, p["id"], pr["med_id"], pr["date"], pr["slot"]),
        )
        self.deliver(p, self.sh(p, "reminder_ok_ack" if yn else "reminder_missed_ack"))
        return True

    # ── triage plumbing ─────────────────────────────────────────────────────
    def _history(self, p: dict) -> dict:
        g = [r["value1"] for r in self.db.all(
            "SELECT value1 FROM readings WHERE patient_id=? AND kind='glucose' ORDER BY taken_at DESC, id DESC LIMIT 6", (p["id"],))][::-1]
        b = self.db.all(
            "SELECT value1, value2 FROM readings WHERE patient_id=? AND kind='bp' ORDER BY taken_at DESC, id DESC LIMIT 6", (p["id"],))[::-1]
        return {"glucose": g, "sys": [r["value1"] for r in b], "bp_text": [f"{r['value1']:.0f}/{r['value2']:.0f}" for r in b]}

    def _missed_days(self, p: dict) -> int:
        rows = self.db.all("SELECT meds_taken FROM checkins WHERE patient_id=? ORDER BY created_at DESC, id DESC LIMIT 10", (p["id"],))
        n = 1  # today
        for r in rows:
            if r["meds_taken"] == 0:
                n += 1
            else:
                break
        return n

    def _input(self, p: dict, sess: dict, with_history: bool = True) -> TriageInput:
        hist = self._history(p) if with_history else {"glucose": [], "sys": []}
        g, bp = sess.get("glucose"), sess.get("bp")
        meds = sess.get("meds")
        return TriageInput(
            glucose=g["mgdl"] if g else None,
            glucose_context=g["context"] if g else "fasting",
            sys=bp["sys"] if bp else None, dia=bp["dia"] if bp else None,
            symptoms=set(sess.get("symptoms", [])), free_text=sess.get("free_text"),
            meds_taken=meds, missed_med_days=self._missed_days(p) if meds is False else 0,
            history_glucose=hist["glucose"], history_sys=hist["sys"],
        )

    def _quick_urgent(self, p: dict, sess: dict) -> bool:
        """A dangerous reading escalates now; no need to finish the questionnaire."""
        res = evaluate(self._input(p, sess, with_history=False), self.th)
        if res.level == Level.URGENT:
            self._finalize(p, sess, partial=True)
            return True
        return False

    def _escalate_symptoms(self, p: dict, symptoms: set[str], text: str) -> None:
        sess = self._sess(p) if p["state"].startswith("awaiting_") else {}
        sess = dict(sess) if sess else {"steps": [], "notes": []}
        sess["symptoms"] = sorted(set(sess.get("symptoms", [])) | symptoms)
        sess["free_text"] = text.strip()[:300]
        self._finalize(p, sess, partial=True)

    # ── finalize: persist, alert, reply ─────────────────────────────────────
    def _finalize(self, p: dict, sess: dict, partial: bool = False) -> TriageResult:
        if sess.get("kind") == "intake":
            return self._finalize_intake(p, sess)
        if sess.get("kind") == "breast":
            return self._finalize_breast(p, sess, partial)
        inp = self._input(p, sess)
        res = evaluate(inp, self.th)
        if res.emergency or "self_harm" in inp.symptoms:
            self._emergency = True
        bp_hist = self._history(p)["bp_text"][-4:]   # snapshot BEFORE today's reading is stored
        now = iso(self.now())

        g, bp = sess.get("glucose"), sess.get("bp")
        if g:
            lvl = evaluate(TriageInput(glucose=g["mgdl"], glucose_context=g["context"]), self.th).level
            self.db.execute(
                "INSERT INTO readings(patient_id, kind, value1, context, source, level, taken_at) VALUES (?,?,?,?,?,?,?)",
                (p["id"], "glucose", g["mgdl"], g["context"], g.get("source", "text"), int(lvl), now))
        if bp:
            lvl = evaluate(TriageInput(sys=bp["sys"], dia=bp["dia"]), self.th).level
            self.db.execute(
                "INSERT INTO readings(patient_id, kind, value1, value2, source, level, taken_at) VALUES (?,?,?,?,?,?,?)",
                (p["id"], "bp", bp["sys"], bp["dia"], bp.get("source", "text"), int(lvl), now))
        self.db.execute(
            "INSERT INTO checkins(patient_id, local_date, symptoms, free_text, meds_taken, level, completed, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (p["id"], self.local_date(p), j(sess.get("symptoms", [])), sess.get("free_text"),
             None if sess.get("meds") is None else int(sess["meds"]), int(res.level), 0 if partial else 1, now))

        alert_id = None
        if res.level >= Level.WATCH:
            alert_id = self._create_alert(p, res, inp, g, bp, bp_hist)

        # patient-facing reply
        ctx = M.actions_block(res.actions, emergency_number(p["country"]), M._lang(p["dialect"]))
        if "self_harm" in inp.symptoms:
            self.deliver(p, self.sh(p, "self_harm"))
        elif res.level == Level.URGENT:
            self.deliver(p, self.t(p, "done_urgent", name=p["name"], actions=ctx))
        elif res.level == Level.WATCH:
            self.deliver(p, self.t(p, "done_watch", name=p["name"], actions=ctx))
        else:
            self.deliver(p, self.t(p, "done_normal", name=p["name"]))

        fu = iso(self.now() + timedelta(minutes=30)) if res.level == Level.URGENT else None
        self._save(p["id"], followup_at=fu)
        self._set(p["id"], "idle")
        return res

    def _create_alert(self, p: dict, res: TriageResult, inp: TriageInput, g, bp, bp_hist: list[str]) -> int:
        reasons = [r.to_dict() for r in res.reasons]
        codes = sorted(r["code"] + str(r["data"].get("symptom", "")) for r in reasons if r["level"] > 0)
        since = iso(self.now() - timedelta(minutes=60))
        for a in self.db.all("SELECT * FROM alerts WHERE patient_id=? AND status='open' AND level=? AND created_at>=?",
                             (p["id"], int(res.level), since)):
            old = sorted(r["code"] + str(r["data"].get("symptom", "")) for r in json.loads(a["reasons"]) if r["level"] > 0)
            if old == codes:
                return a["id"]  # duplicate within the hour: don't re-notify

        if bp:
            bp_hist = bp_hist + [f"{bp['sys']}/{bp['dia']}"]
        hist = {"glucose": inp.history_glucose + ([g["mgdl"]] if g else []), "bp": bp_hist}
        lbl = res.level.label
        en = M.clinician_summary(p, lbl, reasons, hist, "en")
        ar = M.clinician_summary(p, lbl, reasons, hist, "ar")
        aid = self.db.execute(
            "INSERT INTO alerts(patient_id, level, reasons, summary_en, summary_ar, rules_version, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (p["id"], int(res.level), j(reasons), en, ar, res.rules_version, "open", iso(self.now())))
        if res.level == Level.URGENT:
            self._notify_clinician(p, aid, en, ar)
        return aid

    def _notify_clinician(self, p: dict, alert_id: int, en: str, ar: str) -> None:
        from .config import settings
        c = self.db.one("SELECT * FROM clinicians WHERE id=?", (p["clinician_id"],)) if p["clinician_id"] else None
        phone = (c["phone"] if c and c["phone"] else None) or settings().oncall_phone
        if not phone:
            # Nobody to page: the alert is still in the staff queue; leave an audit trail so this is visible.
            self.db.audit("system", "alert_not_delivered", p["id"], f"alert={alert_id} (no clinician phone / on-call number)")
            return
        name = c["name"] if c else "on-call"
        body = ar if (c and c["language"] == "ar") else en
        self.db.execute("INSERT INTO messages(patient_id, direction, body, created_at) VALUES (?,?,?,?)",
                        (p["id"], "clinician_out", f"→ {name}: {body}", iso(self.now())))
        self.staff_channel.send(phone, body, template="rafiq_clinician_alert",
                                params=[p["name"], "URGENT", body.replace("\n", " | ")[:900]])
        self.db.execute("UPDATE alerts SET notified=1 WHERE id=?", (alert_id,))
        self.db.audit("system", "clinician_notified", p["id"], f"alert={alert_id}")

    def raise_alert(self, p: dict, level: Level, reasons: list[dict], rules_version: str | None = None) -> int:
        """Alert not tied to a chronic check-in (breast concerns, silent patient, overdue referral…). De-duplicated per hour."""
        codes = sorted(r["code"] + str(r["data"].get("symptoms", r["data"].get("symptom", ""))) for r in reasons if r["level"] > 0)
        since = iso(self.now() - timedelta(minutes=60))
        for a in self.db.all("SELECT * FROM alerts WHERE patient_id=? AND status='open' AND level=? AND created_at>=?", (p["id"], int(level), since)):
            old = sorted(r["code"] + str(r["data"].get("symptoms", r["data"].get("symptom", ""))) for r in json.loads(a["reasons"]) if r["level"] > 0)
            if old == codes:
                return a["id"]
        hist = {"glucose": self._history(p)["glucose"], "bp": self._history(p)["bp_text"][-4:]}
        en = M.clinician_summary(p, level.label, reasons, hist, "en")
        ar = M.clinician_summary(p, level.label, reasons, hist, "ar")
        aid = self.db.execute(
            "INSERT INTO alerts(patient_id, level, reasons, summary_en, summary_ar, rules_version, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (p["id"], int(level), j(reasons), en, ar, rules_version or self.th["version"], "open", iso(self.now())))
        if level == Level.URGENT:
            self._notify_clinician(p, aid, en, ar)
        return aid
