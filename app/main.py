"""Rafiq (رفيق) API: staff dashboard, admin console, patient portal, WhatsApp webhook."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
from urllib.parse import urlparse

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import auth, notify, scheduler
from . import breast as B
from . import breast_ops as ops
from .channels import NullChannel, build_channel, verify_signature
from .config import COUNTRY_TZ, emergency_number, load_thresholds, settings
from .conversation import Engine
from .db import DB, iso, j, parse_iso, utcnow
from .messages import DIALECTS, SYMPTOM_NAMES
from .routes_account import find_user, router as account_router
from .routes_messaging import router as messaging_router
from .routes_live import router as live_router
from .seed import seed

log = logging.getLogger("rafiq")
HERE = Path(__file__).parent
STATIC, PAGES = HERE / "static", HERE / "pages"
HOME = {"admin": "/admin", "clinician": "/dashboard", "patient": "/patient"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = settings()
    db = DB(s.db_target)
    db.init()
    app.state.db = db
    app.state.channel = build_channel()
    app.state.demo = False
    if s.admin_user and s.admin_password and not db.one("SELECT 1 FROM users WHERE username=?", (s.admin_user.lower(),)):
        auth.check_strength(s.admin_password)
        auth.create_user(db, s.admin_user, "Administrator", "admin", s.admin_password)
        log.info("Created admin user %s", s.admin_user)
    if s.demo_seed:
        app.state.demo = seed(db, s.programme)
        if app.state.demo:
            log.warning("DEMO MODE: synthetic patients and well-known demo passwords. Never use with real data.")
    if not db.one("SELECT 1 FROM users LIMIT 1"):
        log.warning("No users exist. Create the first admin: python -m app.manage create-user --role admin")
    app.state.demo = bool(db.one("SELECT 1 FROM users WHERE username='demo-admin'")) and s.demo_seed
    task = asyncio.create_task(scheduler.run_forever(lambda: Engine(db, app.state.channel))) if s.scheduler_enabled else None
    yield
    if task:
        task.cancel()
    db.close()


app = FastAPI(title="Rafiq – Arabic AI triage & chronic disease monitoring", version="2.0.0", lifespan=lifespan)

CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
       "script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


@app.middleware("http")
async def guard(request: Request, call_next):
    # CSRF defence in depth (cookies are also SameSite=Lax): reject cross-origin state changes.
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.url.path.startswith("/webhook"):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Cross-origin request blocked"}, status_code=403)
    resp = await call_next(request)
    resp.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                         "Referrer-Policy": "same-origin", "Content-Security-Policy": CSP})
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def db_(request: Request) -> DB:
    return request.app.state.db


def sim_engine(request: Request) -> Engine:
    return Engine(request.app.state.db, NullChannel())


def live_engine(request: Request) -> Engine:
    return Engine(request.app.state.db, request.app.state.channel)


# ── models ──────────────────────────────────────────────────────────────────
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class ChangePwIn(BaseModel):
    current: str
    new: str


class MedIn(BaseModel):
    name: str
    dose: str | None = None
    times: list[str] = ["08:00"]

    @field_validator("times")
    @classmethod
    def _t(cls, v):
        if not all(re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", x) for x in v):
            raise ValueError("times must be HH:MM")
        return v


class EnrollIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=7, max_length=20)
    gender: str = "m"
    dialect: str = "levantine"
    country: str = "JO"
    conditions: list[str] = ["diabetes"]
    checkin_time: str = "08:00"
    clinician_id: int | None = None
    medications: list[MedIn] = []
    send_welcome: bool = True
    create_login: bool = False
    birth_year: int | None = None
    email: str | None = None
    prefers_female_clinician: bool = False

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

    @field_validator("conditions")
    @classmethod
    def _c(cls, v):
        if not v or not set(v) <= {"breast", "diabetes", "hypertension"}:
            raise ValueError("conditions must be a non-empty subset of breast, diabetes, hypertension")
        return v

    @field_validator("checkin_time")
    @classmethod
    def _tm(cls, v):
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("checkin_time must be HH:MM")
        return v


class PatchIn(BaseModel):
    dialect: str | None = None
    gender: str | None = None
    checkin_time: str | None = None
    active: bool | None = None
    next_screening_due: str | None = None      # "" clears; used for individual (elevated-risk) screening plans
    risk_category: str | None = None           # clinician override: average | elevated
    checkin_day: int | None = Field(default=None, ge=1, le=28)


class ReferralPatch(BaseModel):
    status: str | None = None
    appointment_date: str | None = None
    outcome: str | None = None
    notes: str | None = Field(default=None, max_length=1000)


class ScreeningIn(BaseModel):
    kind: str
    done_on: str
    birads: int | None = Field(default=None, ge=0, le=6)
    result: str | None = None
    notes: str | None = Field(default=None, max_length=500)


class AckIn(BaseModel):
    note: str = Field(default="", max_length=500)


class SimIn(BaseModel):
    patient_id: int
    text: str = Field(default="", max_length=1000)


class TickIn(BaseModel):
    at: str | None = None


# ── pages ───────────────────────────────────────────────────────────────────
def _page(name: str, *roles: str):
    def handler(request: Request):
        u = auth.user_from_request(request)
        if not u:
            return RedirectResponse("/login", status_code=303)
        if roles and u["role"] not in roles:
            return RedirectResponse(HOME[u["role"]], status_code=303)
        return FileResponse(PAGES / name, headers={"Cache-Control": "no-store"})
    return handler


app.get("/dashboard", include_in_schema=False)(_page("dashboard.html", "admin", "clinician"))
app.get("/admin", include_in_schema=False)(_page("admin.html", "admin"))
app.get("/patient", include_in_schema=False)(_page("patient.html", "patient"))


@app.get("/", include_in_schema=False)
def index(request: Request):
    u = auth.user_from_request(request)
    return RedirectResponse(HOME[u["role"]] if u else "/login", status_code=303)


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    u = auth.user_from_request(request)
    if u:
        return RedirectResponse(HOME[u["role"]], status_code=303)
    return FileResponse(PAGES / "login.html", headers={"Cache-Control": "no-store"})


# ── auth ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True, "time": iso(utcnow())}


@app.get("/api/auth/public")
def auth_public(request: Request):
    out = {"demo": bool(request.app.state.demo), "org": notify.org(), "programme": settings().programme}
    if out["demo"]:
        out["accounts"] = [{"username": u, "role": r} for u, r in
                           (("demo-admin", "admin"), ("demo-lina", "clinician"), ("demo-omar", "clinician"), ("demo-patient1", "patient"), ("demo-patient5", "patient"))]
        out["password"] = "Rafiq-demo-1"
        out["invite_code"] = "DEMOLINA"
    return out


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: DB = Depends(db_)):
    key = body.username.strip().lower()
    wait = auth.throttle.locked(key)
    if wait:
        raise HTTPException(429, f"Too many attempts. Try again in {wait // 60 + 1} min.", headers={"Retry-After": str(wait)})
    row = find_user(db, key)
    good = auth.verify_password(body.password, row["password_hash"] if row else auth._DUMMY) and bool(row) and bool(row["active"])
    ip = request.client.host if request.client else "?"
    if not good:
        auth.throttle.fail(key)
        db.audit(key, "login_failed", None, f"ip={ip}")
        raise HTTPException(401, "Invalid username or password")
    auth.throttle.ok(key)
    if not row["verified"]:
        raise HTTPException(403, "verification_required")
    token = auth.new_session(db, row["id"])
    db.execute("UPDATE users SET last_login=? WHERE id=?", (iso(utcnow()), row["id"]))
    db.audit(key, "login", row["patient_id"], f"ip={ip}")
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite="lax", secure=settings().cookie_secure,
                        max_age=settings().session_hours * 3600, path="/")
    return {"role": row["role"], "redirect": HOME[row["role"]], "must_change": bool(row["must_change"])}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db: DB = Depends(db_)):
    tok = request.cookies.get(auth.COOKIE)
    if tok:
        u = auth.user_from_request(request)
        auth.drop_session(db, tok)
        if u:
            db.audit(u["username"], "logout", u["patient_id"])
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict = Depends(auth.current_user)):
    return {k: user[k] for k in ("id", "username", "display_name", "role", "clinician_id", "patient_id")} | {"must_change": bool(user["must_change"])}


@app.post("/api/auth/change-password")
def change_password(body: ChangePwIn, user: dict = Depends(auth.current_user), db: DB = Depends(db_)):
    row = db.one("SELECT password_hash FROM users WHERE id=?", (user["id"],))
    if not auth.verify_password(body.current, row["password_hash"]):
        raise HTTPException(403, "Current password is incorrect")
    auth.check_strength(body.new)
    if body.new == body.current:
        raise HTTPException(422, "New password must be different")
    db.execute("UPDATE users SET password_hash=?, must_change=0 WHERE id=?", (auth.hash_password(body.new), user["id"]))
    auth.drop_user_sessions(db, user["id"], keep_token=user["_token"])
    db.audit(user["username"], "password_changed", user["patient_id"])
    return {"ok": True}


# ── staff API (admin + clinician, clinicians scoped to their own patients) ──
@app.get("/api/thresholds")
def thresholds(user: dict = Depends(auth.staff)):
    return load_thresholds()


@app.get("/api/config")
def config(request: Request, user: dict = Depends(auth.staff)):
    return {"channel": request.app.state.channel.name, "dialects": DIALECTS, "countries": sorted(COUNTRY_TZ),
            "symptoms": SYMPTOM_NAMES, "programme": settings().programme, "rules_version": load_thresholds()["version"],
            "user": {"name": user["display_name"], "role": user["role"]}}


@app.get("/api/overview")
def overview(db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    sc, sp = auth.scope(user)
    since = iso(utcnow() - timedelta(days=7))
    n = db.one(f"SELECT COUNT(*) c FROM patients p WHERE p.active=1 AND {sc}", sp)["c"]
    open_ = {r["level"]: r["c"] for r in db.all(
        f"SELECT a.level, COUNT(*) c FROM alerts a JOIN patients p ON p.id=a.patient_id WHERE a.status='open' AND {sc} GROUP BY a.level", sp)}
    adh = db.one(f"SELECT AVG(c.meds_taken) a FROM checkins c JOIN patients p ON p.id=c.patient_id "
                 f"WHERE c.created_at>=? AND c.meds_taken IS NOT NULL AND {sc}", [since, *sp])["a"]
    done = db.one(f"SELECT COUNT(DISTINCT c.patient_id || '|' || c.local_date) n FROM checkins c JOIN patients p ON p.id=c.patient_id "
                  f"WHERE c.created_at>=? AND c.completed=1 AND {sc}", [since, *sp])["n"]
    acked = db.all(f"SELECT a.created_at, a.ack_at FROM alerts a JOIN patients p ON p.id=a.patient_id "
                   f"WHERE a.ack_at IS NOT NULL AND a.level=2 AND {sc}", sp)
    mins = [(parse_iso(a["ack_at"]) - parse_iso(a["created_at"])).total_seconds() / 60 for a in acked]
    return {
        "patients": n, "open_urgent": open_.get(2, 0), "open_watch": open_.get(1, 0),
        "adherence_7d": None if adh is None else round(float(adh) * 100),
        "checkin_rate_7d": min(100, round(100 * done / max(n * 7, 1))),
        "median_urgent_ack_min": round(sorted(mins)[len(mins) // 2], 1) if mins else None,
        "unread_messages": db.one(f"SELECT COUNT(*) c FROM messages m JOIN patients p ON p.id=m.patient_id WHERE m.direction='in' AND m.kind='clinician' AND m.read_at IS NULL AND {sc}", sp)["c"],
        "screening": ops.coverage(db, sc, sp), "referrals": ops.referral_kpis(db, sc, sp, date.today()),
    }


@app.get("/api/alerts")
def alerts(status: str = Query("open", pattern="^(open|ack|resolved|all)$"), db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    sc, sp = auth.scope(user)
    where = sc + ("" if status == "all" else " AND a.status=?")
    rows = db.all(
        "SELECT a.*, p.name patient_name, p.phone patient_phone, p.dialect, p.conditions FROM alerts a JOIN patients p ON p.id=a.patient_id "
        f"WHERE {where} ORDER BY (a.status='open') DESC, a.level DESC, a.created_at DESC LIMIT 100",
        sp + ([] if status == "all" else [status]))
    for r in rows:
        r["reasons"] = json.loads(r["reasons"])
    return rows


def _set_alert(db: DB, alert_id: int, status: str, note: str, user: dict) -> dict:
    a = db.one("SELECT * FROM alerts WHERE id=?", (alert_id,))
    if not a:
        raise HTTPException(404, "alert not found")
    auth.ensure_patient_access(db, user, a["patient_id"])
    db.execute("UPDATE alerts SET status=?, ack_by=COALESCE(ack_by, ?), ack_at=COALESCE(ack_at, ?), note=? WHERE id=?",
               (status, user["display_name"], iso(utcnow()), note or a["note"], alert_id))
    db.audit(user["username"], f"alert_{status}", a["patient_id"], f"alert={alert_id}")
    return {"ok": True}


@app.post("/api/alerts/{alert_id}/ack")
def ack(alert_id: int, body: AckIn, db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    return _set_alert(db, alert_id, "ack", body.note, user)


@app.post("/api/alerts/{alert_id}/resolve")
def resolve(alert_id: int, body: AckIn, db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    return _set_alert(db, alert_id, "resolved", body.note, user)


@app.get("/api/patients")
def patients(db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    sc, sp = auth.scope(user, "p")
    out = []
    for p in db.all(f"SELECT * FROM patients p WHERE {sc} ORDER BY p.name", sp):
        g = db.one("SELECT value1, taken_at, level FROM readings WHERE patient_id=? AND kind='glucose' ORDER BY taken_at DESC, id DESC LIMIT 1", (p["id"],))
        b = db.one("SELECT value1, value2, taken_at, level FROM readings WHERE patient_id=? AND kind='bp' ORDER BY taken_at DESC, id DESC LIMIT 1", (p["id"],))
        al = db.one("SELECT MAX(level) l FROM alerts WHERE patient_id=? AND status='open'", (p["id"],))["l"]
        last = db.one("SELECT created_at FROM checkins WHERE patient_id=? ORDER BY created_at DESC LIMIT 1", (p["id"],))
        unread = db.one("SELECT COUNT(*) c FROM messages WHERE patient_id=? AND direction='in' AND kind='clinician' AND read_at IS NULL", (p["id"],))["c"]
        out.append({
            "unread": unread, "id": p["id"], "name": p["name"], "dialect": p["dialect"], "gender": p["gender"], "country": p["country"], "clinician_id": p["clinician_id"],
            "conditions": p["conditions"].split(","), "consent": bool(p["consent"]), "active": bool(p["active"]),
            "state": p["state"], "open_level": al or 0, "last_glucose": g, "last_bp": b,
            "last_checkin": last["created_at"] if last else None, "checkin_time": p["checkin_time"],
            "screening_status": p["screening_status"], "risk_category": p["risk_category"], "intake_done": bool(p["intake_done"]),
            "age": B.age_of(p["birth_year"], date.today()),
        })
    return out


def _detail(db: DB, p: dict) -> dict:
    pid = p["id"]
    since = iso(utcnow() - timedelta(days=30))
    readings = db.all("SELECT kind, value1, value2, context, source, level, taken_at FROM readings WHERE patient_id=? AND taken_at>=? ORDER BY taken_at", (pid, since))
    checkins = db.all("SELECT local_date, symptoms, free_text, meds_taken, level, completed, created_at FROM checkins WHERE patient_id=? ORDER BY created_at DESC LIMIT 14", (pid,))
    for c in checkins:
        c["symptoms"] = json.loads(c["symptoms"])
    meds = db.all("SELECT name, dose, times FROM medications WHERE patient_id=?", (pid,))
    for m in meds:
        m["times"] = json.loads(m["times"])
    adh = [c["meds_taken"] for c in checkins if c["meds_taken"] is not None]
    return {"readings": readings, "checkins": checkins, "medications": meds,
            "adherence_pct": round(100 * mean(adh)) if adh else None}


def _breast_block(db: DB, p: dict) -> dict | None:
    if "breast" not in p["conditions"]:
        return None
    today = date.today()
    refs = db.all("SELECT * FROM referrals WHERE patient_id=? ORDER BY id DESC", (p["id"],))
    for r in refs:
        r["reason"] = json.loads(r["reason"])
        r["overdue"] = ops.is_overdue(r, today)
    return {"age": B.age_of(p["birth_year"], today), "risk_category": p["risk_category"], "risk_flags": json.loads(p["risk_flags"] or "{}"),
            "intake_done": bool(p["intake_done"]), "screening_status": p["screening_status"], "last_mammogram": p["last_mammogram"],
            "next_screening_due": p["next_screening_due"], "screening_booked_at": p["screening_booked_at"],
            "prefers_female_clinician": bool(p["prefers_female_clinician"]), "referrals": refs,
            "screenings": db.all("SELECT * FROM screenings WHERE patient_id=? ORDER BY done_on DESC, id DESC", (p["id"],))}


@app.get("/api/patients/{pid}")
def patient_detail(pid: int, db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    p = auth.ensure_patient_access(db, user, pid)
    db.audit(user["username"], "view_patient", pid)
    d = _detail(db, p)
    for k in ("session", "pending_reminder"):
        p.pop(k, None)
    p["conditions"] = p["conditions"].split(",")
    al = db.all("SELECT * FROM alerts WHERE patient_id=? ORDER BY created_at DESC LIMIT 12", (pid,))
    for a in al:
        a["reasons"] = json.loads(a["reasons"])
    msgs = db.all("SELECT id, direction, body, kind, sender, created_at FROM messages WHERE patient_id=? ORDER BY id DESC LIMIT 60", (pid,))[::-1]
    return {"patient": p, "alerts": al, "messages": msgs, "breast": _breast_block(db, p), **d}


@app.get("/api/patients/{pid}/messages")
def patient_messages(pid: int, after: int = 0, db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    auth.ensure_patient_access(db, user, pid)
    rows = db.all("SELECT id, direction, body, kind, sender, read_at, created_at FROM messages WHERE patient_id=? AND id>? ORDER BY id", (pid, after))
    db.execute("UPDATE messages SET read_at=? WHERE patient_id=? AND direction='in' AND kind='clinician' AND read_at IS NULL", (iso(utcnow()), pid))
    return rows


def enroll_patient(db: DB, body: EnrollIn, clinician_id: int | None, actor: str, engine: Engine | None) -> dict:
    if db.one("SELECT 1 FROM patients WHERE phone=?", (body.phone,)):
        raise HTTPException(409, "phone already enrolled")
    if clinician_id and not db.one("SELECT 1 FROM clinicians WHERE id=?", (clinician_id,)):
        raise HTTPException(422, "unknown clinician")
    pid = db.execute(
        "INSERT INTO patients(name, phone, gender, dialect, country, tz, conditions, clinician_id, checkin_time, email, birth_year, "
        "prefers_female_clinician, checkin_day, enrolled_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (body.name, body.phone, body.gender, body.dialect, body.country.upper(), COUNTRY_TZ.get(body.country.upper(), "Asia/Amman"),
         ",".join(body.conditions), clinician_id, body.checkin_time, body.email, body.birth_year,
         int(body.prefers_female_clinician), min(date.today().day, 28), iso(utcnow())))
    for m in body.medications:
        db.execute("INSERT INTO medications(patient_id, name, dose, times) VALUES (?,?,?,?)", (pid, m.name, m.dose, j(m.times)))
    db.audit(actor, "enroll_patient", pid)
    login = None
    if body.create_login:
        username = "".join(ch for ch in body.phone if ch.isdigit())
        pw = auth.temp_password()
        auth.create_user(db, username, body.name, "patient", pw, patient_id=pid, must_change=True)
        db.audit(actor, "create_login", pid, f"username={username}")
        login = {"username": username, "temp_password": pw}
    if body.send_welcome and engine:
        engine.send_welcome(engine.patient(pid))
    return {"id": pid, "login": login}


@app.post("/api/patients", status_code=201)
def enroll(body: EnrollIn, request: Request, db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    cid = user["clinician_id"] if user["role"] == "clinician" else body.clinician_id  # clinicians enroll into their own panel
    return enroll_patient(db, body, cid, user["username"], live_engine(request))


@app.patch("/api/patients/{pid}")
def patch_patient(pid: int, body: PatchIn, db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    auth.ensure_patient_access(db, user, pid)
    fields = {}
    if body.dialect is not None:
        if body.dialect not in DIALECTS:
            raise HTTPException(422, "bad dialect")
        fields["dialect"] = body.dialect
    if body.gender in ("m", "f"):
        fields["gender"] = body.gender
    if body.checkin_time and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", body.checkin_time):
        fields["checkin_time"] = body.checkin_time
    if body.active is not None:
        fields["active"] = int(body.active)
    if body.checkin_day is not None:
        fields["checkin_day"] = body.checkin_day
    if body.risk_category is not None:
        if body.risk_category not in ("average", "elevated"):
            raise HTTPException(422, "risk_category must be average or elevated")
        fields["risk_category"] = body.risk_category
    if body.next_screening_due is not None:
        try:
            fields["next_screening_due"] = date.fromisoformat(body.next_screening_due).isoformat() if body.next_screening_due else None
        except ValueError:
            raise HTTPException(422, "next_screening_due must be YYYY-MM-DD")
    if not fields:
        raise HTTPException(422, "nothing to update")
    cols = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE patients SET {cols} WHERE id=?", [*fields.values(), pid])
    if "risk_category" in fields or "next_screening_due" in fields:
        ops.refresh_screening(db, db.one("SELECT * FROM patients WHERE id=?", (pid,)), date.today())
    db.audit(user["username"], "patch_patient", pid, j(fields))
    return {"ok": True}


@app.get("/api/referrals")
def referrals(status: str = Query("open", pattern="^(open|overdue|all)$"), db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    sc, sp = auth.scope(user)
    rows = db.all("SELECT r.*, p.name patient_name, p.dialect, p.prefers_female_clinician, p.birth_year, p.clinician_id FROM referrals r "
                  f"JOIN patients p ON p.id=r.patient_id WHERE {sc} ORDER BY r.created_at DESC LIMIT 300", sp)
    today, out = date.today(), []
    for r in rows:
        r["reason"] = json.loads(r["reason"])
        r["overdue"] = ops.is_overdue(r, today)
        r["age"] = B.age_of(r.pop("birth_year"), today)
        if status == "all" or (status == "open" and r["status"] in ops.OPEN) or (status == "overdue" and r["overdue"]):
            out.append(r)
    out.sort(key=lambda r: (not r["overdue"], r["priority"] != "urgent", r["created_at"]))
    return out


@app.patch("/api/referrals/{rid}")
def patch_referral(rid: int, body: ReferralPatch, db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    r = db.one("SELECT * FROM referrals WHERE id=?", (rid,))
    if not r:
        raise HTTPException(404, "referral not found")
    auth.ensure_patient_access(db, user, r["patient_id"])
    try:
        return ops.update_referral(db, rid, body.model_dump(exclude_none=True), user["username"], utcnow())
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/patients/{pid}/screenings", status_code=201)
def add_screening(pid: int, body: ScreeningIn, db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    p = auth.ensure_patient_access(db, user, pid)
    try:
        return ops.log_screening(db, p, body.model_dump(), user["username"], utcnow())
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/api/patients/{pid}/start-checkin")
def start_checkin(pid: int, request: Request, simulate: bool = True, db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    auth.ensure_patient_access(db, user, pid)
    eng = sim_engine(request) if simulate else live_engine(request)
    eng.start_checkin(pid, scheduled=False)
    return {"sent": eng._out}


@app.post("/api/sim/send")
def sim_send(body: SimIn, request: Request, db: DB = Depends(db_), user: dict = Depends(auth.staff)):
    p = auth.ensure_patient_access(db, user, body.patient_id)
    return {"replies": sim_engine(request).handle_inbound(p["phone"], body.text)}


@app.post("/api/sim/tick")
def sim_tick(body: TickIn, request: Request, user: dict = Depends(auth.admin_only)):
    now = parse_iso(body.at) if body.at else utcnow()
    return scheduler.tick(sim_engine(request), now)


# ── WhatsApp Cloud API webhook (authenticated by Meta's HMAC signature, not by cookie) ──
@app.get("/webhook/whatsapp")
def wa_verify(hub_mode: str = Query(None, alias="hub.mode"), hub_verify_token: str = Query(None, alias="hub.verify_token"),
              hub_challenge: str = Query(None, alias="hub.challenge")):
    s = settings()
    if hub_mode == "subscribe" and s.wa_verify_token and hmac.compare_digest(hub_verify_token or "", s.wa_verify_token):
        return Response(content=hub_challenge or "", media_type="text/plain")
    raise HTTPException(403, "verification failed")


def _process_wa(app: FastAPI, payload: dict) -> None:
    db: DB = app.state.db
    channel = app.state.channel
    eng = Engine(db, channel)
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []) or []:
                wa_id = msg.get("id", "")
                if wa_id:
                    if db.one("SELECT 1 FROM processed_messages WHERE wa_id=?", (wa_id,)):
                        continue  # Meta retries; handle each message exactly once
                    db.execute("INSERT INTO processed_messages(wa_id, created_at) VALUES (?,?)", (wa_id, iso(utcnow())))
                phone, kind = msg.get("from", ""), msg.get("type")
                text, media = "", None
                if kind == "text":
                    text = msg["text"]["body"]
                elif kind == "button":
                    text = msg["button"].get("text", "")
                elif kind == "interactive":
                    ir = msg["interactive"]
                    text = (ir.get("button_reply") or ir.get("list_reply") or {}).get("title", "")
                elif kind in ("audio", "image") and hasattr(channel, "download_media"):
                    got = channel.download_media(msg[kind]["id"])
                    if not got:
                        continue
                    media = {"type": kind, "bytes": got[0], "mime": got[1]}
                else:
                    continue
                try:
                    eng.handle_inbound(phone, text, media)
                except Exception:  # noqa: BLE001
                    log.exception("failed handling inbound message")


@app.post("/webhook/whatsapp")
async def wa_receive(request: Request, background: BackgroundTasks, x_hub_signature_256: str | None = Header(default=None)):
    raw = await request.body()
    if not verify_signature(raw, x_hub_signature_256, settings().wa_app_secret):
        raise HTTPException(401, "bad signature")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "invalid JSON")
    background.add_task(_process_wa, request.app, payload)
    return JSONResponse({"status": "received"})


from .routes_admin import router as admin_router  # noqa: E402
from .routes_patient import router as patient_router  # noqa: E402

app.include_router(admin_router)
app.include_router(patient_router)
app.include_router(account_router)
app.include_router(messaging_router)
app.include_router(live_router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
