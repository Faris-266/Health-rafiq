"""Chronic-disease programme (the default): sign-up with conditions, self-service medications, demo data, welcome wording."""
import re

import pytest
from fastapi.testclient import TestClient

from app import routes_account

PW = "Rafiq-demo-1"
NEW = {"name": "سمير خليل", "phone": "962796660001", "email": "samir@example.com", "password": "Str0ng-pass-1", "birth_year": 1968,
       "gender": "m", "dialect": "levantine", "country": "JO", "consent": True, "conditions": ["diabetes", "hypertension"]}


@pytest.fixture
def cclient(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for k, v in {"RAFIQ_DB": str(tmp_path / "c.db"), "RAFIQ_PROGRAMME": "chronic", "RAFIQ_SCHEDULER": "0", "RAFIQ_DEMO_SEED": "1"}.items():
        monkeypatch.setenv(k, v)
    from app import auth
    from app.main import app
    auth.throttle._d.clear()
    for lim in (routes_account.signup_limiter, routes_account.resend_limiter, routes_account.verify_limiter, routes_account.forgot_limiter):
        lim._d.clear()
    with TestClient(app) as c:
        c.app_ = app
        yield c


def who(c, user=None, pw=PW):
    k = TestClient(c.app_); k.app_ = c.app_
    if user:
        assert k.post("/api/auth/login", json={"username": user, "password": pw}).status_code == 200
    return k


def test_default_programme_is_chronic_and_demo_is_chronic(cclient):
    cfg = who(cclient).get("/api/auth/signup-config").json()
    assert cfg["programme"] == "chronic" and cfg["conditions"] == ["diabetes", "hypertension"]
    lina = who(cclient, "demo-lina")
    names = {p["name"] for p in lina.get("/api/patients").json()}
    assert "أم خالد" in names and not any("breast" in ",".join(p["conditions"]) for p in lina.get("/api/patients").json())
    ov = lina.get("/api/overview").json()
    assert ov["open_urgent"] >= 0 and ov["adherence_7d"] is not None and ov["screening"]["breast_patients"] == 0


def test_chronic_demo_has_urgent_hypoglycaemia_trends_and_a_silent_patient(cclient):
    admin = who(cclient, "demo-admin")
    al = admin.get("/api/alerts?status=all").json()
    text = " ".join(a["summary_en"] for a in al)
    assert any(a["level"] == 2 and a["patient_name"] == "فاطمة الزهراء" for a in al) and "Low glucose" in text
    assert "No completed check-in" in text and "above target" in text


def test_register_requires_choosing_a_condition_and_rejects_breast_in_chronic_mode(cclient):
    c = who(cclient)
    assert c.post("/api/auth/register", json={**NEW, "conditions": None}).status_code == 422
    assert c.post("/api/auth/register", json={**NEW, "conditions": ["breast"]}).status_code == 422
    assert c.post("/api/auth/register", json={**NEW, "conditions": ["asthma"]}).status_code == 422


def test_register_chronic_patient_then_checkin_in_web_chat(cclient):
    c = who(cclient)
    assert c.post("/api/auth/register", json={**NEW, "checkin_time": "07:30"}).status_code == 201
    s = c.get("/api/me/summary").json()
    assert s["programme"] == "chronic" and s["profile"]["conditions"] == ["diabetes", "hypertension"] and s["breast"] is None
    assert s["profile"]["checkin_time"] == "07:30"
    out = c.post("/api/me/chat", json={"text": "ابدأ"}).json()["replies"]
    assert any("السكر" in m for m in out)
    c.post("/api/me/chat", json={"text": "سكري 118"}); c.post("/api/me/chat", json={"text": "130/85"})
    c.post("/api/me/chat", json={"text": "لا"}); r = c.post("/api/me/chat", json={"text": "ايوه"}).json()["replies"]
    assert "منيحة" in r[-1] and c.get("/api/me/summary").json()["last_checkin"]["level"] == 0
    assert c.get("/api/me/summary").json()["readings"]


def test_dangerous_reading_from_a_self_registered_patient_pages_the_clinician(cclient):
    c = who(cclient)
    c.post("/api/auth/register", json={**NEW, "invite_code": "DEMOLINA"})
    c.post("/api/me/chat", json={"text": "ابدأ"}); r = c.post("/api/me/chat", json={"text": "سكري 42"}).json()["replies"]
    assert any("15" in m for m in r)
    lina = who(cclient, "demo-lina")
    urgent = [a for a in lina.get("/api/alerts").json() if a["patient_name"] == "سمير خليل" and a["level"] == 2]
    assert urgent and urgent[0]["notified"] == 1


def test_patient_manages_own_medications_which_drive_reminders(cclient):
    c = who(cclient); c.post("/api/auth/register", json=NEW)
    assert c.put("/api/me/medications", json={"medications": [{"name": "ميتفورمين", "dose": "500mg", "times": ["08:00", "20:00"]}, {"name": "Amlodipine", "dose": "5mg", "times": ["09:00"]}]}).status_code == 200
    meds = c.get("/api/me/summary").json()["medications"]
    assert [m["name"] for m in meds] == ["ميتفورمين", "Amlodipine"] and meds[0]["times"] == ["08:00", "20:00"]
    assert c.put("/api/me/medications", json={"medications": [{"name": "x", "times": ["25:99"]}]}).status_code == 422
    assert c.put("/api/me/medications", json={"medications": [{"name": "", "times": ["08:00"]}]}).status_code == 422
    assert c.put("/api/me/medications", json={"medications": []}).status_code == 200 and c.get("/api/me/summary").json()["medications"] == []


def test_patient_can_change_checkin_time_but_not_see_other_patients_meds(cclient):
    c = who(cclient, "demo-patient1")
    assert c.patch("/api/me/preferences", json={"checkin_time": "06:45"}).status_code == 200
    assert c.patch("/api/me/preferences", json={"checkin_time": "6pm"}).status_code == 422
    assert c.get("/api/me/summary").json()["profile"]["checkin_time"] == "06:45"
    other = who(cclient, "demo-patient2")
    other.put("/api/me/medications", json={"medications": [{"name": "OnlyMine", "times": ["10:00"]}]})
    assert "OnlyMine" not in str(c.get("/api/me/summary").json())


def test_welcome_message_describes_the_chronic_programme(cclient, monkeypatch):
    monkeypatch.setenv("RAFIQ_DEMO_SEED", "0")
    c = who(cclient); c.post("/api/auth/register", json={**NEW, "dialect": "en"})
    w = [m["body"] for m in c.get("/api/me/messages").json()][0]
    assert "chronic-disease monitoring programme (diabetes and blood pressure)" in w and "breast" not in w.lower()
    pat = who(cclient, "demo-admin")
    assert pat.get("/api/admin/system").json()["programme"] == "chronic"


def test_consent_message_for_staff_enrolled_patients_uses_chronic_wording(cclient):
    admin = who(cclient, "demo-admin")
    pid = admin.post("/api/patients", json={"name": "منى", "phone": "962797770001", "dialect": "en", "conditions": ["diabetes"]}).json()["id"]
    msgs = admin.get(f"/api/patients/{pid}/messages").json()
    assert "blood-sugar and blood-pressure readings" in msgs[0]["body"] and "breast" not in msgs[0]["body"].lower()


def test_scheduler_runs_daily_chronic_checkins_not_breast_ones(cclient):
    admin = who(cclient, "demo-admin")
    pid = admin.post("/api/patients", json={"name": "منى", "phone": "962797770002", "dialect": "levantine", "conditions": ["hypertension"], "checkin_time": "08:00", "send_welcome": False}).json()["id"]
    db = cclient.app_.state.db
    db.execute("UPDATE patients SET consent=1 WHERE id=?", (pid,))
    r = admin.post("/api/sim/tick", json={"at": "2026-10-10T05:30:00"}).json()       # 08:30 Amman
    assert r["checkins"] >= 1 and r["monthly"] == 0
