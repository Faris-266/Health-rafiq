"""Public sign-up, verification, and the patient's data rights (export / delete)."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from . import auth, notify
from .config import COUNTRY_TZ, settings
from .db import DB, iso, j, parse_iso, utcnow
from .messages import DIALECTS

router = APIRouter(tags=["account"])
MIN_AGE = 18
CODE_TTL_MIN, MAX_ATTEMPTS, RESEND_COOLDOWN = 15, 5, 60


def db_(request: Request) -> DB:
    return request.app.state.db


class _Limiter:
    """N events per window per key (in-memory; use Redis for several workers)."""
    def __init__(self, n: int, window: int):
        self.n, self.window, self._d, self._l = n, window, {}, threading.Lock()

    def hit(self, key: str) -> bool:
        now = time.time()
        with self._l:
            q = [t for t in self._d.get(key, []) if now - t < self.window]
            if len(q) >= self.n:
                self._d[key] = q
                return False
            q.append(now)
            self._d[key] = q
            return True


signup_limiter = _Limiter(5, 3600)
resend_limiter = _Limiter(5, 3600)
verify_limiter = _Limiter(20, 3600)


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=7, max_length=20)
    email: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=8, max_length=200)
    birth_year: int
    gender: str = "f"
    dialect: str = "en"
    country: str = "JO"
    invite_code: str | None = Field(default=None, max_length=32)
    prefers_female_clinician: bool = False
    consent: bool

    @field_validator("phone")
    @classmethod
    def _p(cls, v):
        d = "".join(ch for ch in v if ch.isdigit())
        if not 7 <= len(d) <= 15:
            raise ValueError("phone must have 7-15 digits (include the country code)")
        return d

    @field_validator("email")
    @classmethod
    def _e(cls, v):
        if v in (None, ""):
            return None
        v = v.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("invalid email")
        return v

    @field_validator("gender")
    @classmethod
    def _g(cls, v):
        if v not in ("m", "f"):
            raise ValueError("gender must be m or f")
        return v

    @field_validator("dialect")
    @classmethod
    def _d(cls, v):
        if v not in DIALECTS:
            raise ValueError(f"dialect must be one of {list(DIALECTS)}")
        return v


class VerifyIn(BaseModel):
    username: str
    code: str = Field(min_length=6, max_length=6)


class ResendIn(BaseModel):
    username: str


class ForgotIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=120)


class ResetIn(BaseModel):
    identifier: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=1, max_length=200)


class DeleteIn(BaseModel):
    password: str
    confirm: str


def find_user(db: DB, ident: str) -> dict | None:
    """Sign in with username, email, or (for patients) the phone number they registered with."""
    key = ident.strip().lower()
    u = db.one("SELECT * FROM users WHERE username=?", (key,)) or db.one("SELECT * FROM users WHERE email=?", (key,))
    if u:
        return u
    d = "".join(ch for ch in key if ch.isdigit())
    if len(d) >= 7:
        for p in db.all("SELECT id, phone FROM patients"):
            if "".join(ch for ch in p["phone"] if ch.isdigit()) == d:
                return db.one("SELECT * FROM users WHERE patient_id=?", (p["id"],))
    return None


def _hash_code(uid: int, code: str) -> str:
    return hashlib.sha256(f"{uid}:{code}".encode()).hexdigest()


def _issue_code(request: Request, db: DB, user: dict, phone: str, lang: str) -> bool:
    mode = settings().effective_verify
    code = f"{secrets.randbelow(10 ** 6):06d}"
    db.execute("DELETE FROM verifications WHERE user_id=?", (user["id"],))
    db.execute("INSERT INTO verifications(user_id, channel, code_hash, expires_at, attempts, created_at) VALUES (?,?,?,?,?,?)",
               (user["id"], mode, _hash_code(user["id"], code), iso(utcnow() + timedelta(minutes=CODE_TTL_MIN)), 0, iso(utcnow())))
    return notify.send_code(request.app.state.channel, mode, phone, user.get("email"), code, lang)


def _start_session(db: DB, user: dict, response: Response) -> None:
    token = auth.new_session(db, user["id"])
    db.execute("UPDATE users SET last_login=? WHERE id=?", (iso(utcnow()), user["id"]))
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax", secure=settings().cookie_secure,
                        max_age=settings().session_hours * 3600, path="/")


@router.get("/api/auth/signup-config")
def signup_config():
    s = settings()
    return {"org": notify.org(), "enabled": s.allow_signup, "verification": s.effective_verify, "invite_required": s.require_invite, "min_age": MIN_AGE,
            "dialects": DIALECTS, "countries": sorted(COUNTRY_TZ)}


@router.get("/register", include_in_schema=False)
def register_page(request: Request):
    from fastapi.responses import FileResponse, RedirectResponse
    from .main import HOME, PAGES
    u = auth.user_from_request(request)
    if u:
        return RedirectResponse(HOME[u["role"]], status_code=303)
    return FileResponse(PAGES / "register.html", headers={"Cache-Control": "no-store"})


@router.post("/api/auth/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: DB = Depends(db_)):
    s = settings()
    ip = request.client.host if request.client else "?"
    if not s.allow_signup:
        raise HTTPException(403, "Self-registration is turned off. Please contact your clinic.")
    if not signup_limiter.hit(ip):
        raise HTTPException(429, "Too many sign-ups from this network. Try again later.")
    if not body.consent:
        raise HTTPException(422, "You must agree to the privacy and consent terms to create an account.")
    today = date.today()
    if not 1900 <= body.birth_year <= today.year or today.year - body.birth_year < MIN_AGE:
        raise HTTPException(422, f"You must be at least {MIN_AGE} years old to create an account.")
    auth.check_strength(body.password)
    clinician_id = None
    if body.invite_code:
        c = db.one("SELECT id FROM clinicians WHERE invite_code=?", (body.invite_code.strip().upper(),))
        if not c:
            raise HTTPException(422, "That clinic code isn't valid. Check it with your clinic.")
        clinician_id = c["id"]
    elif s.require_invite:
        raise HTTPException(422, "A clinic code is required. Ask your clinic for yours.")
    username = body.email or body.phone
    if (db.one("SELECT 1 FROM users WHERE username=? OR email=?", (username, body.email or "-")) or
            any("".join(ch for ch in x["phone"] if ch.isdigit()) == body.phone for x in db.all("SELECT phone FROM patients"))):
        raise HTTPException(409, "An account with this phone number or email already exists. Try signing in.")
    mode = s.effective_verify
    if mode == "email" and not body.email:
        raise HTTPException(422, "An email address is required to verify your account.")
    tz = COUNTRY_TZ.get(body.country.upper(), "Asia/Amman")
    pid = db.execute(
        "INSERT INTO patients(name, phone, gender, dialect, country, tz, conditions, clinician_id, email, birth_year, consent, consent_at, "
        "prefers_female_clinician, checkin_day, enrolled_at) VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)",
        (body.name.strip(), body.phone, body.gender, body.dialect, body.country.upper(), tz, "breast", clinician_id, body.email,
         body.birth_year, iso(utcnow()), int(body.prefers_female_clinician), min(today.day, 28), iso(utcnow())))
    uid = auth.create_user(db, username, body.name.strip(), "patient", body.password, patient_id=pid)
    db.execute("UPDATE users SET email=?, verified=? WHERE id=?", (body.email, 0 if mode != "none" else 1, uid))
    db.audit(username, "register", pid, f"verify={mode} invite={'yes' if clinician_id else 'no'} ip={ip}")
    user = db.one("SELECT * FROM users WHERE id=?", (uid,))
    if mode == "none":
        notify.send_welcome(db, request.app.state.channel, db.one("SELECT * FROM patients WHERE id=?", (pid,)))
        _start_session(db, user, response)
        return {"status": "ok", "redirect": "/patient", "verification": "none"}
    sent = _issue_code(request, db, user, body.phone, "en" if body.dialect == "en" else "ar")
    return {"status": "verification_required", "verification": mode, "username": username, "sent": sent}


@router.post("/api/auth/verify")
def verify(body: VerifyIn, request: Request, response: Response, db: DB = Depends(db_)):
    ip = request.client.host if request.client else "?"
    if not verify_limiter.hit(ip):
        raise HTTPException(429, "Too many attempts. Try again later.")
    user = find_user(db, body.username)
    bad = HTTPException(400, "Invalid or expired code.")
    if not user or user["verified"]:
        raise bad
    v = db.one("SELECT * FROM verifications WHERE user_id=? ORDER BY id DESC LIMIT 1", (user["id"],))
    if not v or parse_iso(v["expires_at"]) < utcnow() or v["attempts"] >= MAX_ATTEMPTS:
        raise bad
    if not hmac.compare_digest(_hash_code(user["id"], body.code), v["code_hash"]):
        db.execute("UPDATE verifications SET attempts=attempts+1 WHERE id=?", (v["id"],))
        raise bad
    db.execute("UPDATE users SET verified=1 WHERE id=?", (user["id"],))
    db.execute("DELETE FROM verifications WHERE user_id=?", (user["id"],))
    db.audit(user["username"], "verified", user["patient_id"])
    if user["patient_id"]:
        notify.send_welcome(db, request.app.state.channel, db.one("SELECT * FROM patients WHERE id=?", (user["patient_id"],)))
    _start_session(db, user, response)
    return {"status": "ok", "redirect": "/patient"}


@router.post("/api/auth/resend")
def resend(body: ResendIn, request: Request, db: DB = Depends(db_)):
    ip = request.client.host if request.client else "?"
    if not resend_limiter.hit(ip):
        raise HTTPException(429, "Too many requests. Try again later.")
    user = find_user(db, body.username)
    if user and not user["verified"]:
        v = db.one("SELECT created_at FROM verifications WHERE user_id=? ORDER BY id DESC LIMIT 1", (user["id"],))
        if v and (utcnow() - parse_iso(v["created_at"])).total_seconds() < RESEND_COOLDOWN:
            raise HTTPException(429, f"Please wait {RESEND_COOLDOWN} seconds before requesting another code.")
        p = db.one("SELECT phone, dialect FROM patients WHERE id=?", (user["patient_id"],))
        _issue_code(request, db, user, p["phone"], "en" if p["dialect"] == "en" else "ar")
    return {"status": "ok"}          # same answer whether or not the account exists


# ── forgotten password (code by WhatsApp / email) ───────────────────────────
forgot_limiter = _Limiter(5, 3600)


@router.post("/api/auth/forgot")
def forgot_password(body: ForgotIn, request: Request, db: DB = Depends(db_)):
    """Always answers the same way, so it can't be used to discover who has an account."""
    ip = request.client.host if request.client else "?"
    if not forgot_limiter.hit(ip):
        raise HTTPException(429, "Too many requests. Try again later.")
    if settings().effective_verify == "none":
        return {"status": "unavailable"}          # no WhatsApp/email configured: an administrator must reset it
    user = find_user(db, body.identifier)
    if user and user["active"] and user["patient_id"]:
        p = db.one("SELECT phone, email, dialect FROM patients WHERE id=?", (user["patient_id"],))
        v = db.one("SELECT created_at FROM verifications WHERE user_id=? ORDER BY id DESC LIMIT 1", (user["id"],))
        if not (v and (utcnow() - parse_iso(v["created_at"])).total_seconds() < RESEND_COOLDOWN):
            _issue_code(request, db, {**user, "email": user.get("email") or p["email"]}, p["phone"], "en" if p["dialect"] == "en" else "ar")
            db.audit(user["username"], "password_reset_requested", user["patient_id"])
    return {"status": "ok"}


@router.post("/api/auth/reset")
def reset_password(body: ResetIn, request: Request, db: DB = Depends(db_)):
    ip = request.client.host if request.client else "?"
    if not verify_limiter.hit(ip):
        raise HTTPException(429, "Too many attempts. Try again later.")
    auth.check_strength(body.new_password)         # checked first, so a typo doesn't burn the code
    user = find_user(db, body.identifier)
    bad = HTTPException(400, "Invalid or expired code.")
    if not user or not user["active"]:
        raise bad
    v = db.one("SELECT * FROM verifications WHERE user_id=? ORDER BY id DESC LIMIT 1", (user["id"],))
    if not v or parse_iso(v["expires_at"]) < utcnow() or v["attempts"] >= MAX_ATTEMPTS:
        raise bad
    if not hmac.compare_digest(_hash_code(user["id"], body.code), v["code_hash"]):
        db.execute("UPDATE verifications SET attempts=attempts+1 WHERE id=?", (v["id"],))
        raise bad
    db.execute("UPDATE users SET password_hash=?, must_change=0, verified=1 WHERE id=?", (auth.hash_password(body.new_password), user["id"]))
    db.execute("DELETE FROM verifications WHERE user_id=?", (user["id"],))
    auth.drop_user_sessions(db, user["id"])
    db.audit(user["username"], "password_reset", user["patient_id"])
    return {"status": "ok"}


# ── patient data rights ─────────────────────────────────────────────────────
@router.get("/api/me/export")
def export_my_data(db: DB = Depends(db_), user: dict = Depends(auth.patient_only)):
    pid = user["patient_id"]
    p = db.one("SELECT * FROM patients WHERE id=?", (pid,))
    for k in ("session", "pending_reminder"):
        p.pop(k, None)
    data = {
        "exported_at": iso(utcnow()), "profile": p,
        "account": {"username": user["username"], "email": user["email"], "created_at": user["created_at"]},
        "readings": db.all("SELECT * FROM readings WHERE patient_id=? ORDER BY taken_at", (pid,)),
        "checkins": db.all("SELECT * FROM checkins WHERE patient_id=? ORDER BY created_at", (pid,)),
        "screenings": db.all("SELECT * FROM screenings WHERE patient_id=? ORDER BY done_on", (pid,)),
        "referrals": db.all("SELECT * FROM referrals WHERE patient_id=? ORDER BY created_at", (pid,)),
        "medications": db.all("SELECT * FROM medications WHERE patient_id=?", (pid,)),
        "messages": db.all("SELECT direction, body, created_at FROM messages WHERE patient_id=? AND direction<>'clinician_out' ORDER BY id", (pid,)),
    }
    db.audit(user["username"], "export_my_data", pid)
    return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="rafiq-my-data.json"'})


@router.post("/api/me/delete-account")
def delete_account(body: DeleteIn, response: Response, db: DB = Depends(db_), user: dict = Depends(auth.patient_only)):
    """Permanently deletes the patient's record and login. Audit entries are kept but anonymised."""
    if body.confirm != "DELETE":
        raise HTTPException(422, 'Type DELETE to confirm.')
    row = db.one("SELECT password_hash FROM users WHERE id=?", (user["id"],))
    if not auth.verify_password(body.password, row["password_hash"]):
        raise HTTPException(403, "Password is incorrect")
    pid, uid = user["patient_id"], user["id"]
    for sql, arg in (("DELETE FROM sessions WHERE user_id=?", uid), ("DELETE FROM verifications WHERE user_id=?", uid), ("DELETE FROM users WHERE id=?", uid),
                     ("DELETE FROM referrals WHERE patient_id=?", pid), ("DELETE FROM screenings WHERE patient_id=?", pid),
                     ("DELETE FROM alerts WHERE patient_id=?", pid), ("DELETE FROM messages WHERE patient_id=?", pid),
                     ("DELETE FROM checkins WHERE patient_id=?", pid), ("DELETE FROM readings WHERE patient_id=?", pid),
                     ("DELETE FROM reminder_log WHERE patient_id=?", pid), ("DELETE FROM medications WHERE patient_id=?", pid),
                     ("UPDATE audit_log SET patient_id=NULL WHERE patient_id=?", pid), ("DELETE FROM patients WHERE id=?", pid)):
        db.execute(sql, (arg,))
    db.audit("system", "account_deleted", None, "ref=" + hashlib.sha256(f"{uid}".encode()).hexdigest()[:10])
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}
