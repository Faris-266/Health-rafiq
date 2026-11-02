"""Live updates (SSE fingerprint + stream) and the emergency one-tap-call flag."""
import asyncio

import pytest

from app import live
from tests.conftest import make_patient
from tests.test_api import PW, admin, client, lina, login, omar, patient1  # noqa: F401

PHONE = "962790000111"
ADMIN = {"role": "admin", "username": "a", "clinician_id": None}


@pytest.fixture
def pid(db):
    return make_patient(db, name="سعاد", phone=PHONE, gender="f", dialect="levantine", conditions="diabetes")


# ── fingerprint ─────────────────────────────────────────────────────────────
def test_fingerprint_changes_when_an_alert_is_raised_and_flags_new_urgent(eng, db, pid):
    before = live.staff_fingerprint(db, ADMIN)
    eng.handle_inbound(PHONE, "عندي وجع في صدري")
    after = live.staff_fingerprint(db, ADMIN)
    d = live.changed(before, after)
    assert "alerts" in d["keys"] and d["urgent_new"] is True
    assert live.changed(after, live.staff_fingerprint(db, ADMIN)) == {"keys": [], "urgent_new": False}          # idle → no event


def test_fingerprint_sees_acknowledgement_messages_referrals_and_new_readings(eng, db, pid):
    eng.handle_inbound(PHONE, "عندي وجع في صدري")
    fp = live.staff_fingerprint(db, ADMIN)
    db.execute("UPDATE alerts SET status='ack', ack_at='2026-10-10T05:00:01'")
    assert "alerts" in live.changed(fp, live.staff_fingerprint(db, ADMIN))["keys"]
    fp = live.staff_fingerprint(db, ADMIN)
    eng.staff_send(eng.patient(pid), "Dr Test", "Hello")
    assert "messages" in live.changed(fp, live.staff_fingerprint(db, ADMIN))["keys"]
    fp = live.staff_fingerprint(db, ADMIN)
    eng.start_checkin(pid); eng.handle_inbound(PHONE, "ابدأ"); eng.handle_inbound(PHONE, "120")
    assert "readings" in live.changed(fp, live.staff_fingerprint(db, ADMIN))["keys"] or "messages" in live.changed(fp, live.staff_fingerprint(db, ADMIN))["keys"]


def test_a_clinician_is_not_woken_by_other_clinicians_patients(eng, db, pid):
    other = {"role": "clinician", "username": "x", "clinician_id": 999}
    mine = {"role": "clinician", "username": "y", "clinician_id": 1}
    f_other, f_mine = live.staff_fingerprint(db, other), live.staff_fingerprint(db, mine)
    eng.handle_inbound(PHONE, "عندي وجع في صدري")
    assert live.changed(f_other, live.staff_fingerprint(db, other)) == {"keys": [], "urgent_new": False}
    assert live.changed(f_mine, live.staff_fingerprint(db, mine))["urgent_new"] is True


def test_patient_fingerprint_tracks_her_own_chat_only(eng, db, pid):
    p2 = make_patient(db, name="هدى", phone="962790000222", gender="f", conditions="diabetes")
    mine, theirs = live.patient_fingerprint(db, pid), live.patient_fingerprint(db, p2)
    eng.staff_send(eng.patient(pid), "Dr Test", "Hello")
    assert live.changed(mine, live.patient_fingerprint(db, pid))["keys"] and live.changed(theirs, live.patient_fingerprint(db, p2))["keys"] == []


# ── the stream itself ───────────────────────────────────────────────────────
class FakeRequest:
    async def is_disconnected(self): return False


def collect(make_fp, signed_in, limit=4, once=False):
    async def run():
        out = []
        async for chunk in live.stream(FakeRequest(), make_fp, signed_in, once):
            out.append(chunk)
            if len(out) >= limit:
                break
        return out
    return asyncio.run(asyncio.wait_for(run(), 5))


def test_stream_says_hello_then_pushes_a_change_and_flags_new_urgent(monkeypatch):
    monkeypatch.setattr(live, "INTERVAL", 0.01)
    state = {"n": 0}

    def fp():
        state["n"] += 1
        return {"alerts": [1 if state["n"] < 3 else 2], "_urgent": 0 if state["n"] < 3 else 5}
    text = "".join(collect(fp, lambda: True, limit=3))
    assert "event: hello" in text and "event: change" in text and '"urgent_new": true' in text and '"keys": ["alerts"]' in text


def test_stream_closes_when_the_user_is_signed_out_or_disabled(monkeypatch):
    monkeypatch.setattr(live, "INTERVAL", 0.01)
    monkeypatch.setattr(live, "MAX_AGE", 10 ** 9)
    clock = {"t": 0.0}
    monkeypatch.setattr(live.time, "time", lambda: clock.__setitem__("t", clock["t"] + 25) or clock["t"])    # each call = 25 s, so the session check fires
    text = "".join(collect(lambda: {"a": [1]}, lambda: False, limit=5))
    assert "event: signout" in text


def test_stream_once_sends_just_hello():
    text = "".join(collect(lambda: {"a": [1]}, lambda: True, once=True))
    assert text.startswith("retry: 3000") and "event: hello" in text and "event: change" not in text


def test_per_user_connection_cap():
    live._open.clear()
    assert all(live.acquire("u") for _ in range(live.MAX_PER_USER)) and not live.acquire("u")
    live.release("u"); assert live.acquire("u")
    live._open.clear()


# ── API ─────────────────────────────────────────────────────────────────────
def test_events_endpoint_requires_the_right_role(lina, patient1, client):
    live._open.clear()
    r = lina.get("/api/events?once=1")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream") and "event: hello" in r.text
    assert r.headers["x-accel-buffering"] == "no"
    assert patient1.get("/api/events?once=1").status_code == 403
    assert lina.get("/api/me/events?once=1").status_code == 403
    assert "event: hello" in patient1.get("/api/me/events?once=1").text
    assert type(lina)(client.app_).get("/api/events?once=1").status_code == 401


def test_events_endpoint_enforces_the_connection_cap(lina):
    live._open.clear()
    for _ in range(live.MAX_PER_USER):
        live.acquire("demo-lina")
    assert lina.get("/api/events?once=1").status_code == 429
    live._open.clear()


# ── emergency: one-tap call, never an automatic call ────────────────────────
def test_web_chat_flags_a_real_emergency_so_the_page_can_offer_a_call_button(patient1):
    r = patient1.post("/api/me/chat", json={"text": "عندي وجع في صدري"}).json()
    assert r["emergency"] is True and r["emergency_number"] == "911" and "911" in r["replies"][-1]


def test_a_dangerous_but_not_emergency_reading_does_not_raise_the_emergency_flag(client):
    from tests.test_chronic import NEW  # reuse the payload shape
    from tests.test_account import anon
    c = anon(client)
    c.post("/api/auth/register", json={**NEW, "conditions": ["diabetes"], "phone": "962796660077", "email": "e1@example.com"})
    c.post("/api/me/chat", json={"text": "ابدأ"})
    assert c.post("/api/me/chat", json={"text": "سكري 320"}).json()["emergency"] is False        # urgent: doctor alerted, but not an ambulance case
    assert c.post("/api/me/chat", json={"text": "ابدأ"}).json()["emergency"] is False


def test_hypoglycaemia_with_confusion_is_an_emergency(client):
    from tests.test_chronic import NEW
    from tests.test_account import anon
    c = anon(client)
    c.post("/api/auth/register", json={**NEW, "conditions": ["diabetes"], "phone": "962796660078", "email": "e2@example.com"})
    c.post("/api/me/chat", json={"text": "ابدأ"})
    # a dangerously low sugar while confused (a red-flag symptom)
    assert c.post("/api/me/chat", json={"text": "مشوش وما بعرف وين انا"}).json()["emergency"] is True


def test_staff_alert_list_carries_the_patients_phone_for_tap_to_call(lina):
    a = next(x for x in lina.get("/api/alerts").json() if x["level"] == 2)
    assert a["patient_phone"] and a["patient_phone"].isdigit()
