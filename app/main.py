"""Rafiq (رفيق) API: clinician dashboard backend, patient simulator, WhatsApp webhook."""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import scheduler
from .channels import NullChannel, build_channel, verify_signature
from .config import COUNTRY_TZ, load_thresholds, settings
from .conversation import Engine
from .db import DB, iso, j, parse_iso, utcnow
from .messages import DIALECTS, SYMPTOM_NAMES
from .seed import seed

log = logging.getLogger("rafiq")
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = settings()
    db = DB(s.db_path)
    db.init()
    if s.demo_seed:
        seed(db)
    app.state.db = db
    app.state.channel = build_channel()
    task = None
    if s.scheduler_enabled:
        task = asyncio.create_task(scheduler.run_forever(lambda: Engine(db, app.state.channel)))
    if not s.dashboard_key:
        log.warning("RAFIQ_DASHBOARD_KEY is not set: the dashboard API is OPEN. Set it before any real use.")
    yield
    if task:
        task.cancel()
    db.close()


app = FastAPI(title="Rafiq – Arabic AI triage & chronic disease monitoring", version="1.0.0", lifespan=lifespan)


# ── auth ────────────────────────────────────────────────────────────────────
def require_key(request: Request, x_api_key: str | None = Header(default=None)) -> str:
    key = settings().dashboard_key
    if key and not (x_api_key and hmac.compare_digest(x_api_key, key)):
        raise HTTPException(401, "Invalid or missing X-API-Key")
    return request.headers.get("x-actor", "clinician")


def db_(request: Request) -> DB:
    return request.app.state.db


def sim_engine(request: Request) -> Engine:
    return Engine(request.app.state.db, NullChannel())


def live_engine(request: Request) -> Engine:
    return Engine(request.app.state.db, request.app.state.channel)


# ── models ──────────────────────────────────────────────────────────────────
class MedIn(BaseModel):
    name: str
    dose: str | None = None
    times: list[str] = ["08:00"]


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
        if not v or not set(v) <= {"diabetes", "hypertension"}:
            raise ValueError("conditions must be a non-empty subset of diabetes, hypertension")
        return v

    @field_validator("checkin_time")
    @classmethod
    def _t(cls, v):
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("checkin_time must be HH:MM")
        return v


class PatchIn(BaseModel):
    dialect: str | None = None
    gender: str | None = None
    checkin_time: str | None = None
    active: bool | None = None


class AckIn(BaseModel):
    note: str = ""


class SimIn(BaseModel):
    patient_id: int
    text: str = ""


class TickIn(BaseModel):
    at: str | None = None   # ISO UTC, lets the demo jump to e.g. 08:00 local


# ── dashboard API ───────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True, "time": iso(utcnow())}


@app.get("/api/thresholds", dependencies=[Depends(require_key)])
def thresholds():
    return load_thresholds()


@app.get("/api/config", dependencies=[Depends(require_key)])
def config(request: Request):
    return {"channel": request.app.state.channel.name, "dialects": DIALECTS, "countries": sorted(COUNTRY_TZ),
            "auth_required": bool(settings().dashboard_key), "symptoms": SYMPTOM_NAMES, "rules_version": load_thresholds()["version"]}


@app.get("/api/overview", dependencies=[Depends(require_key)])
def overview(db: DB = Depends(db_)):
    since = iso(utcnow() - timedelta(days=7))
    n = db.one("SELECT COUNT(*) c FROM patients WHERE active=1")["c"]
    open_ = {r["level"]: r["c"] for r in db.all("SELECT level, COUNT(*) c FROM alerts WHERE status='open' GROUP BY level")}
    adh = db.one("SELECT AVG(meds_taken) a FROM checkins WHERE created_at>=? AND meds_taken IS NOT NULL", (since,))["a"]
    done = db.one("SELECT COUNT(DISTINCT patient_id || '|' || local_date) c FROM checkins WHERE created_at>=? AND completed=1", (since,))["c"]
    acked = db.all("SELECT created_at, ack_at FROM alerts WHERE ack_at IS NOT NULL AND level=2")
    mins = [(parse_iso(a["ack_at"]) - parse_iso(a["created_at"])).total_seconds() / 60 for a in acked]
    return {
        "patients": n,
        "open_urgent": open_.get(2, 0), "open_watch": open_.get(1, 0),
        "adherence_7d": None if adh is None else round(adh * 100),
        "checkin_rate_7d": min(100, round(100 * done / max(n * 7, 1))),
        "median_urgent_ack_min": round(sorted(mins)[len(mins) // 2], 1) if mins else None,
    }


@app.get("/api/alerts", dependencies=[Depends(require_key)])
def alerts(status: str = Query("open", pattern="^(open|ack|resolved|all)$"), db: DB = Depends(db_)):
    where = "" if status == "all" else "WHERE a.status=?"
    rows = db.all(
        f"SELECT a.*, p.name patient_name, p.dialect, p.conditions FROM alerts a JOIN patients p ON p.id=a.patient_id {where} "
        "ORDER BY (a.status='open') DESC, a.level DESC, a.created_at DESC LIMIT 100",
        () if status == "all" else (status,))
    for r in rows:
        r["reasons"] = json.loads(r["reasons"])
    return rows


def _set_alert(db: DB, alert_id: int, status: str, note: str, actor: str) -> dict:
    a = db.one("SELECT * FROM alerts WHERE id=?", (alert_id,))
    if not a:
        raise HTTPException(404, "alert not found")
    db.execute("UPDATE alerts SET status=?, ack_by=COALESCE(ack_by, ?), ack_at=COALESCE(ack_at, ?), note=? WHERE id=?",
               (status, actor, iso(utcnow()), note or a["note"], alert_id))
    db.audit(actor, f"alert_{status}", a["patient_id"], f"alert={alert_id}")
    return {"ok": True}


@app.post("/api/alerts/{alert_id}/ack", dependencies=[Depends(require_key)])
def ack(alert_id: int, body: AckIn, request: Request, db: DB = Depends(db_), actor: str = Depends(require_key)):
    return _set_alert(db, alert_id, "ack", body.note, actor)


@app.post("/api/alerts/{alert_id}/resolve", dependencies=[Depends(require_key)])
def resolve(alert_id: int, body: AckIn, db: DB = Depends(db_), actor: str = Depends(require_key)):
    return _set_alert(db, alert_id, "resolved", body.note, actor)


@app.get("/api/patients", dependencies=[Depends(require_key)])
def patients(db: DB = Depends(db_)):
    out = []
    for p in db.all("SELECT * FROM patients ORDER BY name"):
        g = db.one("SELECT value1, taken_at, level FROM readings WHERE patient_id=? AND kind='glucose' ORDER BY taken_at DESC, id DESC LIMIT 1", (p["id"],))
        b = db.one("SELECT value1, value2, taken_at, level FROM readings WHERE patient_id=? AND kind='bp' ORDER BY taken_at DESC, id DESC LIMIT 1", (p["id"],))
        al = db.one("SELECT MAX(level) l FROM alerts WHERE patient_id=? AND status='open'", (p["id"],))["l"]
        last = db.one("SELECT created_at FROM checkins WHERE patient_id=? ORDER BY created_at DESC LIMIT 1", (p["id"],))
        out.append({
            "id": p["id"], "name": p["name"], "dialect": p["dialect"], "gender": p["gender"], "country": p["country"],
            "conditions": p["conditions"].split(","), "consent": bool(p["consent"]), "active": bool(p["active"]),
            "state": p["state"], "open_level": al or 0, "last_glucose": g, "last_bp": b,
            "last_checkin": last["created_at"] if last else None, "checkin_time": p["checkin_time"],
        })
    return out


@app.get("/api/patients/{pid}", dependencies=[Depends(require_key)])
def patient_detail(pid: int, db: DB = Depends(db_), actor: str = Depends(require_key)):
    p = db.one("SELECT * FROM patients WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404, "patient not found")
    db.audit(actor, "view_patient", pid)
    since = iso(utcnow() - timedelta(days=30))
    for k in ("session", "pending_reminder"):
        p.pop(k, None)
    p["conditions"] = p["conditions"].split(",")
    readings = db.all("SELECT kind, value1, value2, context, source, level, taken_at FROM readings WHERE patient_id=? AND taken_at>=? ORDER BY taken_at", (pid, since))
    checkins = db.all("SELECT local_date, symptoms, free_text, meds_taken, level, completed, created_at FROM checkins WHERE patient_id=? ORDER BY created_at DESC LIMIT 14", (pid,))
    for c in checkins:
        c["symptoms"] = json.loads(c["symptoms"])
    al = db.all("SELECT * FROM alerts WHERE patient_id=? ORDER BY created_at DESC LIMIT 12", (pid,))
    for a in al:
        a["reasons"] = json.loads(a["reasons"])
    msgs = db.all("SELECT id, direction, body, created_at FROM messages WHERE patient_id=? ORDER BY id DESC LIMIT 60", (pid,))[::-1]
    meds = db.all("SELECT name, dose, times FROM medications WHERE patient_id=?", (pid,))
    for m in meds:
        m["times"] = json.loads(m["times"])
    adh = [c["meds_taken"] for c in checkins if c["meds_taken"] is not None]
    return {"patient": p, "readings": readings, "checkins": checkins, "alerts": al, "messages": msgs,
            "medications": meds, "adherence_pct": round(100 * mean(adh)) if adh else None}


@app.get("/api/patients/{pid}/messages", dependencies=[Depends(require_key)])
def patient_messages(pid: int, after: int = 0, db: DB = Depends(db_)):
    return db.all("SELECT id, direction, body, created_at FROM messages WHERE patient_id=? AND id>? ORDER BY id", (pid, after))


@app.post("/api/patients", dependencies=[Depends(require_key)], status_code=201)
def enroll(body: EnrollIn, request: Request, db: DB = Depends(db_), actor: str = Depends(require_key)):
    if db.one("SELECT 1 FROM patients WHERE phone=?", (body.phone,)):
        raise HTTPException(409, "phone already enrolled")
    now = iso(utcnow())
    pid = db.execute(
        "INSERT INTO patients(name, phone, gender, dialect, country, tz, conditions, clinician_id, checkin_time, enrolled_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (body.name, body.phone, body.gender, body.dialect, body.country.upper(), COUNTRY_TZ.get(body.country.upper(), "Asia/Amman"),
         ",".join(body.conditions), body.clinician_id, body.checkin_time, now))
    for m in body.medications:
        db.execute("INSERT INTO medications(patient_id, name, dose, times) VALUES (?,?,?,?)", (pid, m.name, m.dose, j(m.times)))
    db.audit(actor, "enroll_patient", pid)
    if body.send_welcome:
        eng = live_engine(request)
        eng.send_welcome(eng.patient(pid))
    return {"id": pid}


@app.patch("/api/patients/{pid}", dependencies=[Depends(require_key)])
def patch_patient(pid: int, body: PatchIn, db: DB = Depends(db_), actor: str = Depends(require_key)):
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
    if not fields:
        raise HTTPException(422, "nothing to update")
    cols = ", ".join(f"{k}=?" for k in fields)
    db.execute(f"UPDATE patients SET {cols} WHERE id=?", [*fields.values(), pid])
    db.audit(actor, "patch_patient", pid, j(fields))
    return {"ok": True}


@app.post("/api/patients/{pid}/start-checkin", dependencies=[Depends(require_key)])
def start_checkin(pid: int, request: Request, simulate: bool = True):
    eng = sim_engine(request) if simulate else live_engine(request)
    eng.start_checkin(pid, scheduled=False)
    return {"sent": eng._out}


# ── simulator (never touches the real channel) ──────────────────────────────
@app.post("/api/sim/send", dependencies=[Depends(require_key)])
def sim_send(body: SimIn, request: Request, db: DB = Depends(db_)):
    p = db.one("SELECT phone FROM patients WHERE id=?", (body.patient_id,))
    if not p:
        raise HTTPException(404, "patient not found")
    eng = sim_engine(request)
    return {"replies": eng.handle_inbound(p["phone"], body.text)}


@app.post("/api/sim/tick", dependencies=[Depends(require_key)])
def sim_tick(body: TickIn, request: Request):
    eng = sim_engine(request)
    now = parse_iso(body.at) if body.at else utcnow()
    return scheduler.tick(eng, now)


# ── WhatsApp Cloud API webhook ──────────────────────────────────────────────
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
                    if got:
                        media = {"type": kind, "bytes": got[0], "mime": got[1]}
                    else:
                        continue
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


# ── static dashboard ────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")
