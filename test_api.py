import hashlib, hmac, json
import pytest
from fastapi.testclient import TestClient

PW = "Rafiq-demo-1"


@pytest.fixture(params=["sqlite", "pg"])
def client(request, tmp_path, monkeypatch):
    if request.param == "pg":
        from tests.conftest import fresh_pg
        uri = request.getfixturevalue("pg_uri")
        fresh_pg(uri).close()
        monkeypatch.setenv("DATABASE_URL", uri)
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("RAFIQ_DB", str(tmp_path / "api.db"))
    for k, v in {"RAFIQ_SCHEDULER": "0", "RAFIQ_DEMO_SEED": "1", "WHATSAPP_VERIFY_TOKEN": "vt", "WHATSAPP_APP_SECRET": "appsecret"}.items():
        monkeypatch.setenv(k, v)
    from app import auth
    from app.main import app
    auth.throttle._d.clear()
    with TestClient(app) as c:
        c.app_ = app
        yield c


def login(client, user, pw=PW):
    c = TestClient(client.app_)          # separate cookie jar, shares the running app state
    c.app_ = client.app_
    r = c.post("/api/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def admin(client): return login(client, "demo-admin")
@pytest.fixture
def lina(client): return login(client, "demo-lina")
@pytest.fixture
def omar(client): return login(client, "demo-omar")
@pytest.fixture
def patient1(client): return login(client, "demo-patient1")


def test_overview_and_alert_queue(admin):
    ov = admin.get("/api/overview").json()
    assert ov["patients"] == 6 and ov["open_urgent"] >= 1 and ov["checkin_rate_7d"] <= 100
    assert admin.get("/api/alerts").json()[0]["level"] == 2


def test_ack_and_resolve_are_audited(admin):
    a = admin.get("/api/alerts").json()[0]
    assert admin.post(f"/api/alerts/{a['id']}/ack", json={"note": "called patient"}).status_code == 200
    assert admin.get("/api/alerts?status=ack").json()[0]["note"] == "called patient"
    assert admin.get("/api/overview").json()["median_urgent_ack_min"] is not None
    assert any(r["action"] == "alert_ack" for r in admin.get("/api/admin/audit").json())


def test_enroll_validation_welcome_and_patient_login(admin):
    assert admin.post("/api/patients", json={"name": "x", "phone": "962799999999", "dialect": "klingon"}).status_code == 422
    ok = admin.post("/api/patients", json={"name": "ليلى", "phone": "962799999999", "gender": "f", "dialect": "gulf", "conditions": ["diabetes"],
                                          "medications": [{"name": "ميتفورمين", "times": ["08:00"]}], "create_login": True})
    assert ok.status_code == 201 and ok.json()["login"]["username"] == "962799999999"
    msgs = admin.get(f"/api/patients/{ok.json()['id']}/messages").json()
    assert "نعم" in msgs[0]["body"]
    assert admin.post("/api/patients", json={"name": "d", "phone": "962799999999"}).status_code == 409
    # the new patient can sign in with the one-time password but must change it first
    c = TestClient(admin.app_)
    tmp = ok.json()["login"]["temp_password"]
    assert c.post("/api/auth/login", json={"username": "962799999999", "password": tmp}).json()["must_change"] is True
    assert c.get("/api/me/summary").status_code == 403
    assert c.post("/api/auth/change-password", json={"current": tmp, "new": "short"}).status_code == 422
    assert c.post("/api/auth/change-password", json={"current": tmp, "new": "a-Better-pass-9"}).status_code == 200
    assert c.get("/api/me/summary").status_code == 200


def test_simulator_roundtrip(lina):
    pid = next(p["id"] for p in lina.get("/api/patients").json() if p["name"] == "أبو فهد")
    lina.post(f"/api/patients/{pid}/start-checkin")
    r = lina.post("/api/sim/send", json={"patient_id": pid, "text": "40"}).json()
    assert any("⚠️" in m for m in r["replies"])


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(b"appsecret", body, hashlib.sha256).hexdigest()


def wa_payload(msg_id, text, phone="962790000006"):
    return {"entry": [{"changes": [{"value": {"messages": [{"id": msg_id, "from": phone, "type": "text", "text": {"body": text}}]}}]}]}


def test_webhook_verification_signature_and_dedupe(client, omar):
    assert client.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "123"}).text == "123"
    assert client.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "bad", "hub.challenge": "1"}).status_code == 403
    body = json.dumps(wa_payload("wamid.1", "عندي وجع في صدري")).encode()
    assert client.post("/webhook/whatsapp", content=body, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 401
    h = {"X-Hub-Signature-256": sign(body), "Content-Type": "application/json"}
    assert client.post("/webhook/whatsapp", content=body, headers=h).status_code == 200
    assert client.post("/webhook/whatsapp", content=body, headers=h).status_code == 200   # Meta retry
    al = [a for a in omar.get("/api/alerts").json() if a["patient_name"] == "يوسف الخطيب" and a["level"] == 2]
    assert len(al) == 1
