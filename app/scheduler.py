"""Time-driven behaviour. `tick()` is pure w.r.t. time (pass `now`) so it is easy to test
and to drive from the demo dashboard. In production run it every minute (see main.py)."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import messages as M
from .conversation import Engine
from .db import iso, j, parse_iso
from .triage import Level

log = logging.getLogger("rafiq.scheduler")

CHECKIN_WINDOW_MIN = 180      # still start today's check-in if the server was down at 08:00
REMINDER_WINDOW_MIN = 30
NUDGE_AFTER = timedelta(hours=2)
ABANDON_AFTER = timedelta(hours=8)


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def tick(engine: Engine, now: datetime | None = None) -> dict:
    now = now or engine.now()
    stats = {"checkins": 0, "reminders": 0, "nudges": 0, "abandoned": 0, "followups": 0, "silent": 0}
    th = engine.th

    for p in engine.db.all("SELECT * FROM patients WHERE active=1 AND consent=1"):
        local = now.astimezone(ZoneInfo(p["tz"]))
        today, minute = local.date().isoformat(), local.hour * 60 + local.minute

        # 1 ── stale check-in sessions: nudge once, then save what we have and reset
        if p["state"].startswith("awaiting_") and p["state"] != "awaiting_consent":
            sess = json.loads(p["session"] or "{}")
            started = parse_iso(sess.get("started_at"))
            if started:
                age = now - started
                if age >= ABANDON_AFTER:
                    if sess.get("glucose") or sess.get("bp") or sess.get("symptoms"):
                        engine._finalize(p, sess, partial=True)
                    else:
                        engine._set(p["id"], "idle")
                    stats["abandoned"] += 1
                    p = engine.patient(p["id"])
                elif age >= NUDGE_AFTER and not sess.get("nudged"):
                    sess["nudged"] = True
                    engine._set(p["id"], p["state"], sess)
                    engine.deliver(p, engine.t(p, "nudge", name=p["name"]))
                    stats["nudges"] += 1

        # 2 ── daily check-in
        ct = _minutes(p["checkin_time"])
        if p["last_prompt_date"] != today and ct <= minute < ct + CHECKIN_WINDOW_MIN and p["state"] == "idle":
            engine._save(p["id"], last_prompt_date=today)
            engine.start_checkin(p["id"], scheduled=True)
            stats["checkins"] += 1
            p = engine.patient(p["id"])

        # 3 ── medication reminders
        for med in engine.db.all("SELECT * FROM medications WHERE patient_id=?", (p["id"],)):
            for slot in json.loads(med["times"]):
                s = _minutes(slot)
                if s <= minute < s + REMINDER_WINDOW_MIN:
                    seen = engine.db.one(
                        "SELECT 1 FROM reminder_log WHERE patient_id=? AND med_id=? AND local_date=? AND slot=?",
                        (p["id"], med["id"], today, slot))
                    if seen:
                        continue
                    engine.db.execute("INSERT INTO reminder_log(patient_id, med_id, local_date, slot) VALUES (?,?,?,?)",
                                      (p["id"], med["id"], today, slot))
                    engine._save(p["id"], pending_reminder=j({"med_id": med["id"], "slot": slot, "date": today}))
                    p = engine.patient(p["id"])
                    engine.deliver(p, engine.t(p, "med_reminder", med=med["name"]),
                                   template=None if engine._in_window(p) else "rafiq_med_reminder",
                                   params=[p["name"], med["name"]])
                    stats["reminders"] += 1

        # 4 ── safety follow-up after an urgent message
        if p["followup_at"] and now >= parse_iso(p["followup_at"]):
            engine._save(p["id"], followup_at=None)
            engine.deliver(p, engine.sh(p, "followup_urgent"))
            stats["followups"] += 1

        # 5 ── silent patient (no completed check-in for N days) → clinician alert
        last = engine.db.one(
            "SELECT created_at FROM checkins WHERE patient_id=? AND completed=1 ORDER BY created_at DESC LIMIT 1", (p["id"],))
        ref = parse_iso(last["created_at"]) if last else parse_iso(p["enrolled_at"])
        days = (now - ref).days if ref else 0
        if days >= th["silent_days_watch"]:
            open_nc = [a for a in engine.db.all("SELECT reasons FROM alerts WHERE patient_id=? AND status='open'", (p["id"],))
                       if any(r["code"] == "no_contact" for r in json.loads(a["reasons"]))]
            if not open_nc:
                engine.raise_alert(p, Level.WATCH, [{"code": "no_contact", "level": 1, "data": {"days": days}}])
                stats["silent"] += 1
    return stats


async def run_forever(make_engine, interval: int = 60) -> None:
    """Background loop used by the FastAPI app."""
    while True:
        try:
            await asyncio.to_thread(lambda: tick(make_engine()))
        except Exception:  # noqa: BLE001 — a scheduler failure must never kill the server
            log.exception("scheduler tick failed")
        await asyncio.sleep(interval)
