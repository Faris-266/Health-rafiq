"""Breast-health conversation flow, mixed into Engine.

  intake (once)   age → family history → biopsy/atypia → known gene change → chest radiation → last mammogram
  monthly         "did you check?" → "any change?"        (+ spontaneous reports at ANY time, in ANY state)
  follow-through  screening reminders, referral chasing, staff alerts when a referral slips
"""
from __future__ import annotations

from datetime import date

from . import breast as B
from . import breast_ops as ops
from . import messages as M
from . import nlu
from .config import emergency_number, load_breast_policy
from .db import iso, j
from .triage import Level

INTAKE_STEPS = ["intake_age", "intake_family", "intake_atypia", "intake_gene", "intake_radiation", "intake_mammo"]
MONTHLY_STEPS = ["breast_checked", "breast_symptoms"]
BREAST_STATES = {f"awaiting_{s}" for s in INTAKE_STEPS + MONTHLY_STEPS + ["breast_detail"]}
FLAG_OF_STEP = {"intake_family": "family_first_degree", "intake_atypia": "prior_atypia",
                "intake_gene": "known_mutation", "intake_radiation": "chest_radiation"}


class BreastMixin:
    # ── sessions ────────────────────────────────────────────────────────────
    def _new_breast_session(self, p: dict) -> dict:
        intake = not p["intake_done"]
        return {"kind": "intake" if intake else "breast", "steps": list(INTAKE_STEPS if intake else MONTHLY_STEPS),
                "intake": {}, "symptoms": [], "free_text": None, "self_checked": None, "retries": 0,
                "started_at": iso(self.now()), "notes": []}

    def _today(self, p: dict) -> date:
        return date.fromisoformat(self.local_date(p))

    # ── step handlers ───────────────────────────────────────────────────────
    def _breast_step(self, p: dict, sess: dict, text: str, sym: nlu.SymptomResult, state: str) -> None:
        step = state[len("awaiting_"):]
        today = self._today(p)
        if step == "intake_age":
            by = nlu.parse_birth_year(text, today.year)
            if by is None or today.year - by > 110:
                return self._retry(p, sess, "intake_bad_age")
            if today.year - by < 18:
                self._set(p["id"], "idle")
                self.deliver(p, self.t(p, "intake_minor"))
                return
            sess["intake"]["birth_year"] = by
            return self._advance(p, sess)
        if step in FLAG_OF_STEP:
            v = nlu.parse_yes_no_unknown(text)
            if v is None:
                return self._retry(p, sess, "intake_unclear_yn")
            sess["intake"][FLAG_OF_STEP[step]] = None if v == "unknown" else bool(v)
            return self._advance(p, sess)
        if step == "intake_mammo":
            kind, d = nlu.parse_when(text, today)
            if kind == "bad":
                return self._retry(p, sess, "intake_bad_when")
            sess["intake"]["last_mammogram"] = d.isoformat() if d else None
            sess["intake"]["mammo"] = kind
            return self._advance(p, sess)
        if step == "breast_checked":
            yn = nlu.parse_yes_no(text)
            if yn is None:
                return self._retry(p, sess, "unclear")
            sess["self_checked"] = int(yn)
            if not yn:
                self.deliver(p, self.t(p, "breast_checked_no"))
            return self._advance(p, sess)
        if step == "breast_symptoms":
            # Breast changes never reach here: they are caught by the global screen first.
            if sym.none_declared:
                sess["symptoms"] = []
            elif nlu.parse_yes_no(text) is True and len(nlu.tokens(text)) <= 2:
                sess["steps"].insert(1, "breast_detail")            # "yes" → ask what changed
            elif sym.unrecognised:
                sess["free_text"] = text.strip()[:300]
            else:
                return self._retry(p, sess, "unclear")
            return self._advance(p, sess)
        if step == "breast_detail":
            if sym.none_declared and not sym.unrecognised:
                sess["symptoms"] = []
            else:
                sess["free_text"] = text.strip()[:300]               # forwarded verbatim to the clinician
            return self._advance(p, sess)

    # ── completion ──────────────────────────────────────────────────────────
    def _finalize_intake(self, p: dict, sess: dict) -> None:
        it = sess.get("intake", {})
        flags = {k: it.get(k) for k in FLAG_OF_STEP.values()}
        cat = B.risk_category(flags)
        self._save(p["id"], birth_year=it.get("birth_year"), risk_flags=j(flags), risk_category=cat, intake_done=1,
                   last_mammogram=it.get("last_mammogram"), next_screening_due=None)
        status = ops.refresh_screening(self.db, self.patient(p["id"]), self._today(p))
        p2 = self.patient(p["id"])
        self.deliver(p2, self.t(p2, f"intake_done_{status}", due=p2["next_screening_due"] or ""))
        if cat == "elevated":
            aid = self.raise_alert(p2, Level.WATCH, [{"code": "elevated_risk_review", "level": 1, "data": {}}])
            ops.create_referral(self.db, p2, aid, "routine", ["elevated_risk_review"], self.now())
        self.db.audit("patient", "intake_completed", p["id"], f"risk={cat} screening={status}")
        self._set(p["id"], "idle")

    def _screening_line(self, p: dict) -> str:
        p = self.patient(p["id"])
        key = {"due": "scr_due", "overdue": "scr_overdue", "due_soon": "scr_due_soon"}.get(p["screening_status"])
        return self.t(p, key, due=p["next_screening_due"] or "") if key else ""

    def _finalize_breast(self, p: dict, sess: dict, partial: bool = False):
        pol = load_breast_policy()
        sx, ft = set(sess.get("symptoms", [])), sess.get("free_text")
        res = B.evaluate_breast(sx, p["risk_category"], ft, pol)
        now = self.now()
        stored = sorted(sx & (B.BREAST_CODES | {"fever"}))
        self.db.execute(
            "INSERT INTO checkins(patient_id, local_date, symptoms, free_text, meds_taken, level, completed, kind, self_checked, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (p["id"], self.local_date(p), j(stored), ft, None, int(res.level), 0 if partial else 1, "breast", sess.get("self_checked"), iso(now)))
        contact_by = ""
        if res.level >= Level.WATCH:
            aid = self.raise_alert(p, res.level, [r.to_dict() for r in res.reasons])
            codes = sorted({r.code for r in res.reasons if r.level > 0} | set(stored))
            rid, _ = ops.create_referral(self.db, p, aid, "urgent" if res.level == Level.URGENT else "routine", codes, now)
            contact_by = self.db.one("SELECT contact_by FROM referrals WHERE id=?", (rid,))["contact_by"]
            self.db.audit("system", "breast_concern_reported", p["id"], f"alert={aid} referral={rid} level={res.level.label}")
        acts = M.actions_block(res.actions, emergency_number(p["country"]), M._lang(p["dialect"]),
                               days=pol["referral"]["urgent_contact_days"], date=contact_by)
        if res.level == Level.URGENT:
            self.deliver(p, self.t(p, "done_breast_urgent", actions=acts))
        elif res.level == Level.WATCH:
            self.deliver(p, self.t(p, "done_breast_watch", actions=acts))
        else:
            self.deliver(p, self.t(p, "done_breast_normal", screening=self._screening_line(p)))
        self._set(p["id"], "idle")
        return res

    def _breast_report(self, p: dict, symptoms: set[str], text: str) -> None:
        """A breast change mentioned at ANY time (idle, mid-check-in, before consent) is handled immediately."""
        sess = self._sess(p) if p["state"].startswith("awaiting_") else {}
        if sess.get("kind") != "breast":
            sess = {"kind": "breast", "steps": [], "self_checked": None, "notes": []}
        sess["symptoms"] = sorted(set(sess.get("symptoms", [])) | set(symptoms))
        self._finalize_breast(p, sess)

    # ── follow-through (called by the scheduler) ────────────────────────────
    def send_screening_reminder(self, p: dict) -> None:
        self._save(p["id"], last_screening_reminder=iso(self.now()), pending_reminder=j({"type": "screening"}))
        p = self.patient(p["id"])
        self.deliver(p, self.t(p, "screening_reminder"), template=None if self._in_window(p) else "rafiq_health_reminder", params=[p["name"]])

    def chase_referral(self, p: dict, ref: dict) -> None:
        self.db.execute("UPDATE referrals SET chased_at=? WHERE id=?", (iso(self.now()), ref["id"]))
        self._save(p["id"], pending_reminder=j({"type": "referral", "referral_id": ref["id"]}))
        p = self.patient(p["id"])
        self.deliver(p, self.t(p, "referral_chase", name=p["name"]), template=None if self._in_window(p) else "rafiq_health_followup", params=[p["name"]])
