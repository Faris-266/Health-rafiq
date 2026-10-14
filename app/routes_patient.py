"""Patient portal API. A patient can only ever read or write their own record."""
from __future__ import annotations

import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import auth
from . import breast as B
from .channels import NullChannel
from .config import emergency_number
from .conversation import Engine
from .db import DB, iso, utcnow
from .messages import DIALECTS, SYMPTOM_NAMES

router = APIRouter(prefix="/api/me", tags=["patient"])


def db_(request: Request) -> DB:
    return request.app.state.db


class ChatIn(BaseModel):
    text: str = Field(default="", max_length=1000)


class PrefsIn(BaseModel):
    dialect: str | None = None
    gender: str | None = None


def _patient(db: DB, user: dict) -> dict:
    p = db.one("SELECT * FROM patients WHERE id=?", (user["patient_id"],))
    if not p:
        raise HTTPException(404, "patient record not found")
    return p


def _breast(db: DB, p: dict) -> dict | None:
    """What a patient may see about her own breast-health pathway (no clinician-only notes)."""
    if "breast" not in p["conditions"]:
        return None
    refs = db.all("SELECT status, priority, appointment_date, visit_by, created_at FROM referrals WHERE patient_id=? AND status IN ('new','contacted','booked') ORDER BY id DESC", (p["id"],))
    return {"intake_done": bool(p["intake_done"]), "age": B.age_of(p["birth_year"], date.today()), "screening_status": p["screening_status"],
            "next_screening_due": p["next_screening_due"], "last_mammogram": p["last_mammogram"],
            "personalised_plan": p["risk_category"] == "elevated", "open_referrals": refs}


@router.get("/summary")
def summary(db: DB = Depends(db_), user: dict = Depends(auth.patient_only)):
    p = _patient(db, user)
    pid = p["id"]
    since = iso(utcnow() - timedelta(days=30))
    readings = db.all("SELECT kind, value1, value2, context, source, level, taken_at FROM readings WHERE patient_id=? AND taken_at>=? ORDER BY taken_at", (pid, since))
    checkins = db.all("SELECT local_date, symptoms, meds_taken, level, kind, self_checked, created_at FROM checkins WHERE patient_id=? ORDER BY created_at DESC LIMIT 14", (pid,))
    for c in checkins:
        c["symptoms"] = json.loads(c["symptoms"])
    meds = db.all("SELECT name, dose, times FROM medications WHERE patient_id=?", (pid,))
    for m in meds:
        m["times"] = json.loads(m["times"])
    adh = [c["meds_taken"] for c in checkins if c["meds_taken"] is not None]
    recent = db.one("SELECT level, created_at FROM checkins WHERE patient_id=? ORDER BY created_at DESC LIMIT 1", (pid,))
    doctor = db.one("SELECT c.name FROM clinicians c WHERE c.id=?", (p["clinician_id"],)) if p["clinician_id"] else None
    db.audit(user["username"], "patient_view_own", pid)
    return {
        "profile": {"name": p["name"], "dialect": p["dialect"], "gender": p["gender"], "country": p["country"],
                    "conditions": p["conditions"].split(","), "checkin_time": p["checkin_time"], "consent": bool(p["consent"]),
                    "emergency_number": emergency_number(p["country"]), "doctor": doctor["name"] if doctor else None},
        "breast": _breast(db, p), "readings": readings, "checkins": checkins, "medications": meds,
        "adherence_pct": round(100 * sum(adh) / len(adh)) if adh else None,
        "last_checkin": recent, "dialects": DIALECTS, "symptoms": SYMPTOM_NAMES,
    }


@router.get("/messages")
def messages(after: int = 0, db: DB = Depends(db_), user: dict = Depends(auth.patient_only)):
    return db.all("SELECT id, direction, body, created_at FROM messages WHERE patient_id=? AND direction<>'clinician_out' AND id>? ORDER BY id LIMIT 200",
                  (user["patient_id"], after))


@router.post("/chat")
def chat(body: ChatIn, request: Request, db: DB = Depends(db_), user: dict = Depends(auth.patient_only)):
    """The web chat runs through exactly the same engine as WhatsApp: same red-flag screen, triage and alerts.
    Replies stay on the web; clinician alerts still go out on the real staff channel."""
    p = _patient(db, user)
    eng = Engine(db, NullChannel(), staff_channel=request.app.state.channel)
    return {"replies": eng.handle_inbound(p["phone"], body.text)}


@router.patch("/preferences")
def prefs(body: PrefsIn, db: DB = Depends(db_), user: dict = Depends(auth.patient_only)):
    fields = {}
    if body.dialect is not None:
        if body.dialect not in DIALECTS:
            raise HTTPException(422, "bad dialect")
        fields["dialect"] = body.dialect
    if body.gender in ("m", "f"):
        fields["gender"] = body.gender
    if not fields:
        raise HTTPException(422, "nothing to update")
    cols = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE patients SET {cols} WHERE id=?", [*fields.values(), user["patient_id"]])
    return {"ok": True}
