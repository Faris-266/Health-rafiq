"""DB operations for breast screening and referral tracking.

The referral tracker is the heart of early detection: a screening programme only saves lives if a woman with an
abnormal finding is actually SEEN. Every referral therefore has a contact-by and a visit-by date, a status the
clinic updates, automatic chasing of the patient, and an alert to staff when it slips.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from . import breast as B
from .config import load_breast_policy
from .db import DB, iso, j

STATUSES = ("new", "contacted", "booked", "seen", "closed")
OPEN = ("new", "contacted", "booked")
OUTCOMES = ("benign", "further_tests", "treatment", "no_show", "declined", "other")
KINDS = ("mammogram", "ultrasound", "mri", "clinical_exam", "biopsy")


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def refresh_screening(db: DB, p: dict, today: date) -> str:
    """Recompute (and store) a patient's screening status. Cheap; called daily and after any change."""
    flags = json.loads(p["risk_flags"] or "{}")
    risk = p["risk_category"] if p["risk_category"] != "unknown" else B.risk_category(flags)
    status, due = B.screening_status(B.age_of(p["birth_year"], today), risk, _d(p["last_mammogram"]), today,
                                     manual_due=_d(p["next_screening_due"]))
    if not p["intake_done"]:
        status, due = "unknown", None
    elif any("birads_" in r["reason"] for r in db.all("SELECT reason FROM referrals WHERE patient_id=? AND status IN ('new','contacted','booked')", (p["id"],))):
        status, due = "referred", None           # a suspicious result is being worked up; routine screening is on hold
    db.execute("UPDATE patients SET screening_status=?, next_screening_due=? WHERE id=?",
               (status, due.isoformat() if due else None, p["id"]))
    return status


def create_referral(db: DB, p: dict, alert_id: int | None, priority: str, reasons: list[str], now: datetime) -> tuple[int, bool]:
    """Create a referral, or reuse/upgrade an open one from the last 14 days. Returns (id, created)."""
    today = now.date()
    for r in db.all("SELECT * FROM referrals WHERE patient_id=? AND status IN ('new','contacted','booked') ORDER BY id DESC", (p["id"],)):
        if (today - _d(r["created_at"][:10])).days <= 14:
            merged = sorted(set(json.loads(r["reason"])) | set(reasons))
            if priority == "urgent" and r["priority"] != "urgent":
                contact, visit = B.referral_dates("urgent", _d(r["created_at"][:10]))
                db.execute("UPDATE referrals SET priority='urgent', contact_by=?, visit_by=?, reason=?, updated_at=? WHERE id=?",
                           (contact.isoformat(), visit.isoformat(), j(merged), iso(now), r["id"]))
            else:
                db.execute("UPDATE referrals SET reason=?, updated_at=? WHERE id=?", (j(merged), iso(now), r["id"]))
            return r["id"], False
    contact, visit = B.referral_dates(priority, today)
    rid = db.execute(
        "INSERT INTO referrals(patient_id, alert_id, priority, reason, status, contact_by, visit_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (p["id"], alert_id, priority, j(sorted(reasons)), "new", contact.isoformat(), visit.isoformat(), iso(now), iso(now)))
    return rid, True


def update_referral(db: DB, rid: int, fields: dict, actor: str, now: datetime) -> dict:
    r = db.one("SELECT * FROM referrals WHERE id=?", (rid,))
    if not r:
        raise LookupError("referral not found")
    sets, params = {}, {}
    status = fields.get("status")
    if status is not None:
        if status not in STATUSES:
            raise ValueError("bad status")
        sets["status"] = status
    if "appointment_date" in fields and fields["appointment_date"]:
        date.fromisoformat(fields["appointment_date"])        # validates
        sets["appointment_date"] = fields["appointment_date"]
        if status is None and r["status"] in ("new", "contacted"):
            sets["status"] = status = "booked"
    if fields.get("outcome") is not None:
        if fields["outcome"] not in OUTCOMES:
            raise ValueError("bad outcome")
        sets["outcome"] = fields["outcome"]
    if fields.get("notes") is not None:
        sets["notes"] = fields["notes"][:1000]
    if status == "closed" and not (sets.get("outcome") or r["outcome"]):
        raise ValueError("an outcome is required to close a referral")
    if status in ("seen", "closed") and not r["seen_at"]:
        sets["seen_at"] = iso(now)
    if status == "closed":
        sets["closed_at"] = iso(now)
    sets["updated_at"] = iso(now)
    cols = ", ".join(f"{k}=?" for k in sets)
    db.execute(f"UPDATE referrals SET {cols} WHERE id=?", [*sets.values(), rid])
    db.audit(actor, "referral_update", r["patient_id"], j({k: v for k, v in sets.items() if k != "updated_at"}))
    outcome = sets.get("outcome") or r["outcome"]
    if status == "closed" and outcome in ("further_tests", "treatment"):
        # follow-up is now clinician-led: switch to an individual plan (we never guess a schedule for her)
        db.execute("UPDATE patients SET risk_category='elevated', next_screening_due=NULL WHERE id=?", (r["patient_id"],))
    if status in ("seen", "closed"):
        refresh_screening(db, db.one("SELECT * FROM patients WHERE id=?", (r["patient_id"],)), now.date())
    # a seen/closed referral resolves its overdue alerts
    if sets.get("status") in ("seen", "closed"):
        for a in db.all("SELECT id, reasons FROM alerts WHERE patient_id=? AND status='open'", (r["patient_id"],)):
            if any(x["code"] in ("referral_overdue", "referral_unanswered") for x in json.loads(a["reasons"])):
                db.execute("UPDATE alerts SET status='resolved', ack_by=COALESCE(ack_by,?), ack_at=COALESCE(ack_at,?) WHERE id=?", (actor, iso(now), a["id"]))
    return db.one("SELECT * FROM referrals WHERE id=?", (rid,))


def log_screening(db: DB, p: dict, data: dict, actor: str, now: datetime) -> dict:
    """Record a screening result. Returns {'screening_id', 'next_due', 'referral_id'|None, 'status'}."""
    kind = data["kind"]
    if kind not in KINDS:
        raise ValueError("bad kind")
    done_on = date.fromisoformat(data["done_on"])
    if done_on > now.date():
        raise ValueError("date is in the future")
    birads = data.get("birads")
    if birads is not None and not 0 <= int(birads) <= 6:
        raise ValueError("BI-RADS must be 0-6")
    result = data.get("result")
    if result not in (None, "normal", "abnormal", "needs_followup"):
        raise ValueError("bad result")
    sid = db.execute("INSERT INTO screenings(patient_id, kind, done_on, birads, result, notes, recorded_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (p["id"], kind, done_on.isoformat(), birads, result, (data.get("notes") or "")[:500], actor, iso(now)))
    out = B.outcome_of_screening(kind, done_on, None if birads is None else int(birads), result)
    if kind == "mammogram":
        db.execute("UPDATE patients SET last_mammogram=?, screening_booked_at=NULL WHERE id=?", (done_on.isoformat(), p["id"]))
    db.execute("UPDATE patients SET next_screening_due=? WHERE id=?", (out.next_due.isoformat() if out.next_due else None, p["id"]))
    rid = None
    if out.referral_priority:
        rid, _ = create_referral(db, p, None, out.referral_priority, [out.reason], now)
    p2 = db.one("SELECT * FROM patients WHERE id=?", (p["id"],))
    status = "referred" if (kind == "mammogram" and out.referral_priority and out.next_due is None) else None
    refresh_screening(db, p2, now.date())
    status = status or db.one("SELECT screening_status s FROM patients WHERE id=?", (p["id"],))["s"]
    db.audit(actor, "log_screening", p["id"], f"{kind} birads={birads} result={result}")
    return {"screening_id": sid, "next_due": out.next_due.isoformat() if out.next_due else None, "referral_id": rid, "status": status}


def coverage(db: DB, scope_sql: str, scope_params: list) -> dict:
    """Screening KPIs for the staff dashboard."""
    rows = db.all(f"SELECT p.screening_status s, COUNT(*) c FROM patients p WHERE p.active=1 AND p.conditions LIKE '%breast%' AND {scope_sql} GROUP BY p.screening_status", scope_params)
    by = {r["s"]: r["c"] for r in rows}
    eligible = sum(by.get(k, 0) for k in B.ELIGIBLE)
    up = by.get("up_to_date", 0) + by.get("due_soon", 0)
    return {"breast_patients": sum(by.values()), "eligible": eligible, "up_to_date": up, "due": by.get("due", 0), "overdue": by.get("overdue", 0),
            "specialist_plan": by.get("specialist_plan", 0), "intake_pending": by.get("unknown", 0),
            "coverage_pct": None if not eligible else round(100 * up / eligible)}


def referral_kpis(db: DB, scope_sql: str, scope_params: list, today: date) -> dict:
    rows = db.all(f"SELECT r.* FROM referrals r JOIN patients p ON p.id=r.patient_id WHERE {scope_sql}", scope_params)
    open_ = [r for r in rows if r["status"] in OPEN]
    overdue = [r for r in open_ if is_overdue(r, today)]
    days = sorted((_d(r["seen_at"][:10]) - _d(r["created_at"][:10])).days for r in rows if r["seen_at"])
    return {"open": len(open_), "overdue": len(overdue), "urgent_open": sum(1 for r in open_ if r["priority"] == "urgent"),
            "median_days_to_seen": days[len(days) // 2] if days else None, "seen": len(days)}


def is_overdue(r: dict, today: date) -> bool:
    """A referral is overdue if the clinic has not made contact by contact_by, or the patient has not been seen by visit_by."""
    if r["status"] not in OPEN:
        return False
    if r["status"] == "new" and r["contact_by"] and today > _d(r["contact_by"]):
        return True
    appt = _d(r["appointment_date"])
    visit_by = _d(r["visit_by"])
    if r["status"] == "booked" and appt:
        return appt < today or (visit_by is not None and (appt - visit_by).days > 7 and today > visit_by)
    return bool(visit_by and today > visit_by)
