"""Live updates (Server-Sent Events) so dashboards change the instant something happens, with no page refresh.

How it works: each open page holds ONE long-lived GET. Every ~1.5 s the server runs a few tiny indexed queries that build a
"fingerprint" of what the user is allowed to see; when it changes, the browser is told WHICH parts changed and re-fetches them
through the normal, permission-checked API. No data travels in the stream itself, so it can never leak anything the API would not.
Because it reads the database (not memory), it also works with several server processes.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time

from . import auth
from .db import DB

INTERVAL = float(os.environ.get("RAFIQ_SSE_INTERVAL", "1.5"))
KEEPALIVE = 15
MAX_AGE = 120               # the browser reconnects automatically; keeps shutdowns quick and connections fresh
MAX_PER_USER = 6

_open: dict[str, int] = {}
_lock = threading.Lock()


def staff_fingerprint(db: DB, user: dict) -> dict:
    sc, sp = auth.scope(user, "p")
    a = db.one(
        "SELECT COALESCE(MAX(a.id),0) mx, COALESCE(SUM(CASE WHEN a.status='open' THEN 1 ELSE 0 END),0) op, "
        "COALESCE(MAX(a.ack_at),'') ack, COALESCE(MAX(CASE WHEN a.level=2 THEN a.id END),0) urg "
        f"FROM alerts a JOIN patients p ON p.id=a.patient_id WHERE {sc}", sp)
    r = db.one(f"SELECT COALESCE(MAX(r.id),0) mx, COALESCE(MAX(r.updated_at),'') upd FROM referrals r JOIN patients p ON p.id=r.patient_id WHERE {sc}", sp)
    m = db.one(
        "SELECT COALESCE(MAX(m.id),0) mx, COALESCE(SUM(CASE WHEN m.direction='in' AND m.kind='clinician' AND m.read_at IS NULL THEN 1 ELSE 0 END),0) unread "
        f"FROM messages m JOIN patients p ON p.id=m.patient_id WHERE {sc}", sp)
    rd = db.one(f"SELECT COALESCE(MAX(x.id),0) mx FROM readings x JOIN patients p ON p.id=x.patient_id WHERE {sc}", sp)
    ck = db.one(f"SELECT COALESCE(MAX(c.id),0) mx FROM checkins c JOIN patients p ON p.id=c.patient_id WHERE {sc}", sp)
    pt = db.one(f"SELECT COUNT(*) n, COALESCE(MAX(p.id),0) mx FROM patients p WHERE {sc}", sp)
    return {
        "alerts": [a["mx"], a["op"], a["ack"]], "referrals": [r["mx"], r["upd"]], "messages": [m["mx"], m["unread"]],
        "readings": [rd["mx"], ck["mx"]], "patients": [pt["n"], pt["mx"]], "_urgent": a["urg"],
    }


def patient_fingerprint(db: DB, pid: int) -> dict:
    m = db.one("SELECT COALESCE(MAX(id),0) mx FROM messages WHERE patient_id=? AND direction<>'clinician_out'", (pid,))
    p = db.one("SELECT clinician_thread_until t, screening_status s, next_screening_due d FROM patients WHERE id=?", (pid,)) or {}
    c = db.one("SELECT COALESCE(MAX(id),0) mx FROM checkins WHERE patient_id=?", (pid,))
    rd = db.one("SELECT COALESCE(MAX(id),0) mx FROM readings WHERE patient_id=?", (pid,))
    rf = db.one("SELECT COALESCE(MAX(updated_at),'') u FROM referrals WHERE patient_id=?", (pid,))
    return {"messages": [m["mx"]], "profile": [p.get("t"), p.get("s"), p.get("d")], "data": [c["mx"], rd["mx"]], "referrals": [rf["u"]]}


def changed(prev: dict, cur: dict) -> dict:
    keys = [k for k in cur if not k.startswith("_") and cur[k] != prev.get(k)]
    return {"keys": keys, "urgent_new": cur.get("_urgent", 0) > prev.get("_urgent", 0)}


def ev(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def acquire(user_key: str) -> bool:
    with _lock:
        if _open.get(user_key, 0) >= MAX_PER_USER:
            return False
        _open[user_key] = _open.get(user_key, 0) + 1
        return True


def release(user_key: str) -> None:
    with _lock:
        _open[user_key] = max(0, _open.get(user_key, 1) - 1)


async def stream(request, make_fp, still_signed_in, once: bool = False):
    """Yield SSE text. `make_fp()` and `still_signed_in()` are blocking calls run in a worker thread."""
    yield "retry: 3000\n\n"
    prev = await asyncio.to_thread(make_fp)
    yield ev("hello", {"t": int(time.time())})
    if once:
        return
    started = last_send = last_check = time.time()
    while time.time() - started < MAX_AGE:
        if await request.is_disconnected():
            return
        await asyncio.sleep(INTERVAL)
        now = time.time()
        if now - last_check > 20:                                   # logout / disabled user / password reset closes the stream
            last_check = now
            if not await asyncio.to_thread(still_signed_in):
                yield ev("signout", {})
                return
        cur = await asyncio.to_thread(make_fp)
        diff = changed(prev, cur)
        if diff["keys"] or diff["urgent_new"]:
            prev = cur
            last_send = now
            yield ev("change", diff)
        elif now - last_send > KEEPALIVE:
            last_send = now
            yield ": keep-alive\n\n"
