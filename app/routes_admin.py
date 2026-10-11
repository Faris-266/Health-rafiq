"""Admin console API: users, clinicians, audit log, system status. Admin role only."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from . import auth
from .config import load_thresholds, settings
from .db import DB

router = APIRouter(prefix="/api/admin", tags=["admin"])


def db_(request: Request) -> DB:
    return request.app.state.db


class UserIn(BaseModel):
    username: str | None = Field(default=None, max_length=40)   # patients default to their phone number
    display_name: str = Field(min_length=1, max_length=80)
    role: str
    clinician_id: int | None = None
    patient_id: int | None = None

    @field_validator("username")
    @classmethod
    def _u(cls, v):
        if v is None:
            return v
        v = v.strip().lower()
        if not re.fullmatch(r"[a-z0-9_.\-]{3,40}", v):
            raise ValueError("username: letters, digits, . _ - only")
        return v

    @field_validator("role")
    @classmethod
    def _r(cls, v):
        if v not in auth.ROLES:
            raise ValueError(f"role must be one of {auth.ROLES}")
        return v


class UserPatch(BaseModel):
    active: bool | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=80)


class ClinicianIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str | None = Field(default=None, max_length=20)
    language: str = "en"
    create_login: bool = False
    username: str | None = None

    @field_validator("language")
    @classmethod
    def _l(cls, v):
        if v not in ("en", "ar"):
            raise ValueError("language must be en or ar")
        return v


@router.get("/users")
def users(db: DB = Depends(db_), user: dict = Depends(auth.admin_only)):
    return db.all(
        "SELECT u.id, u.username, u.display_name, u.role, u.active, u.must_change, u.created_at, u.last_login, "
        "u.clinician_id, u.patient_id, c.name clinician_name, p.name patient_name "
        "FROM users u LEFT JOIN clinicians c ON c.id=u.clinician_id LEFT JOIN patients p ON p.id=u.patient_id ORDER BY u.role, u.username")


@router.post("/users", status_code=201)
def create_user(body: UserIn, db: DB = Depends(db_), user: dict = Depends(auth.admin_only)):
    if body.role == "patient" and not body.username and body.patient_id:
        ph = db.one("SELECT phone FROM patients WHERE id=?", (body.patient_id,))
        body.username = "".join(ch for ch in (ph["phone"] if ph else "") if ch.isdigit()) or None
    if not body.username:
        raise HTTPException(422, "username is required")
    if db.one("SELECT 1 FROM users WHERE username=?", (body.username,)):
        raise HTTPException(409, "username already exists")
    if body.role == "clinician":
        if not body.clinician_id or not db.one("SELECT 1 FROM clinicians WHERE id=?", (body.clinician_id,)):
            raise HTTPException(422, "clinician accounts must link to an existing clinician")
        body.patient_id = None
    elif body.role == "patient":
        if not body.patient_id or not db.one("SELECT 1 FROM patients WHERE id=?", (body.patient_id,)):
            raise HTTPException(422, "patient accounts must link to an existing patient")
        if db.one("SELECT 1 FROM users WHERE patient_id=?", (body.patient_id,)):
            raise HTTPException(409, "this patient already has a login")
        body.clinician_id = None
    else:
        body.clinician_id = body.patient_id = None
    pw = auth.temp_password()
    uid = auth.create_user(db, body.username, body.display_name, body.role, pw, body.clinician_id, body.patient_id, must_change=True)
    db.audit(user["username"], "create_user", body.patient_id, f"{body.username} ({body.role})")
    return {"id": uid, "username": body.username, "temp_password": pw}   # shown once; user must change it at first login


@router.patch("/users/{uid}")
def patch_user(uid: int, body: UserPatch, db: DB = Depends(db_), user: dict = Depends(auth.admin_only)):
    target = db.one("SELECT * FROM users WHERE id=?", (uid,))
    if not target:
        raise HTTPException(404, "user not found")
    if body.active is False and uid == user["id"]:
        raise HTTPException(422, "you cannot deactivate your own account")
    if body.active is not None:
        db.execute("UPDATE users SET active=? WHERE id=?", (int(body.active), uid))
        if not body.active:
            auth.drop_user_sessions(db, uid)
    if body.display_name:
        db.execute("UPDATE users SET display_name=? WHERE id=?", (body.display_name, uid))
    db.audit(user["username"], "patch_user", target["patient_id"], f"{target['username']} active={body.active}")
    return {"ok": True}


@router.post("/users/{uid}/reset-password")
def reset_password(uid: int, db: DB = Depends(db_), user: dict = Depends(auth.admin_only)):
    target = db.one("SELECT * FROM users WHERE id=?", (uid,))
    if not target:
        raise HTTPException(404, "user not found")
    pw = auth.temp_password()
    db.execute("UPDATE users SET password_hash=?, must_change=1 WHERE id=?", (auth.hash_password(pw), uid))
    auth.drop_user_sessions(db, uid)
    db.audit(user["username"], "reset_password", target["patient_id"], target["username"])
    return {"username": target["username"], "temp_password": pw}


@router.get("/clinicians")
def clinicians(db: DB = Depends(db_), user: dict = Depends(auth.admin_only)):
    return db.all("SELECT c.*, (SELECT COUNT(*) FROM patients p WHERE p.clinician_id=c.id) patients, "
                  "(SELECT u.username FROM users u WHERE u.clinician_id=c.id LIMIT 1) username FROM clinicians c ORDER BY c.name")


@router.post("/clinicians", status_code=201)
def add_clinician(body: ClinicianIn, db: DB = Depends(db_), user: dict = Depends(auth.admin_only)):
    cid = db.execute("INSERT INTO clinicians(name, phone, language) VALUES (?,?,?)", (body.name, body.phone, body.language))
    login = None
    if body.create_login:
        uname = (body.username or re.sub(r"[^a-z0-9]+", ".", body.name.lower()).strip(".") or f"clinician{cid}")[:40]
        if db.one("SELECT 1 FROM users WHERE username=?", (uname.lower(),)):
            raise HTTPException(409, "username already exists")
        pw = auth.temp_password()
        auth.create_user(db, uname, body.name, "clinician", pw, clinician_id=cid, must_change=True)
        login = {"username": uname.lower(), "temp_password": pw}
    db.audit(user["username"], "add_clinician", None, body.name)
    return {"id": cid, "login": login}


@router.get("/audit")
def audit(limit: int = 200, action: str | None = None, db: DB = Depends(db_), user: dict = Depends(auth.admin_only)):
    limit = max(1, min(limit, 1000))
    if action:
        return db.all("SELECT a.*, p.name patient_name FROM audit_log a LEFT JOIN patients p ON p.id=a.patient_id WHERE a.action=? ORDER BY a.id DESC LIMIT ?", (action, limit))
    return db.all("SELECT a.*, p.name patient_name FROM audit_log a LEFT JOIN patients p ON p.id=a.patient_id ORDER BY a.id DESC LIMIT ?", (limit,))


@router.get("/system")
def system(request: Request, db: DB = Depends(db_), user: dict = Depends(auth.admin_only)):
    s = settings()
    count = lambda t, w="1=1": db.one(f"SELECT COUNT(*) c FROM {t} WHERE {w}")["c"]  # noqa: E731 (table names are constants)
    return {
        "database": "PostgreSQL" if db.kind == "pg" else "SQLite", "channel": request.app.state.channel.name,
        "scheduler": s.scheduler_enabled, "rules_version": load_thresholds()["version"],
        "rules_status": load_thresholds()["status"], "demo_mode": bool(request.app.state.demo),
        "counts": {"patients": count("patients"), "users": count("users"), "clinicians": count("clinicians"),
                   "open_alerts": count("alerts", "status='open'"), "readings": count("readings"), "messages": count("messages")},
        "cookie_secure": s.cookie_secure,
    }
