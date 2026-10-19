"""Clinician → patient messaging API. A clinician can only ever message the patients assigned to them."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import auth
from . import messages as M
from .conversation import Engine
from .db import DB, iso, parse_iso
from .messaging import clean_staff_text
from .routes_account import _Limiter

router = APIRouter(tags=["messaging"])
send_limiter = _Limiter(30, 3600)          # per staff user, per hour


def db_(request: Request) -> DB:
    return request.app.state.db


class StaffMsgIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


@router.post("/api/patients/{pid}/message", status_code=201)
def message_patient(pid: int, body: StaffMsgIn, request: Request, db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    p = auth.ensure_patient_access(db, user, pid)               # 404 for anyone else's patient
    if not p["active"] or not p["consent"]:
        raise HTTPException(409, "This patient has not agreed to receive messages (or has opted out).")
    try:
        text = clean_staff_text(body.text)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if not send_limiter.hit(user["username"]):
        raise HTTPException(429, "You have sent many messages in the last hour. Please try again later.")
    eng = Engine(db, request.app.state.channel)
    receipt = eng.staff_send(p, user["display_name"], text)      # in-app + WhatsApp (template if outside the 24h window)
    db.audit(user["username"], "staff_message", pid, f"len={len(text)} whatsapp={receipt['whatsapp']}")
    return {"ok": True, "delivery": receipt, "thread_until": db.one("SELECT clinician_thread_until t FROM patients WHERE id=?", (pid,))["t"]}


@router.get("/api/patients/{pid}/message-suggestions")
def suggestions(pid: int, db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    p = auth.ensure_patient_access(db, user, pid)
    return {"language": M._lang(p["dialect"]), "suggestions": M.SUGGESTIONS[M._lang(p["dialect"])]}
