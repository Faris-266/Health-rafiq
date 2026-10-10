import hashlib, hmac, json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RAFIQ_DB", str(tmp_path / "api.db"))
    monkeypatch.setenv("RAFIQ_SCHEDULER", "0")
    monkeypatch.setenv("RAFIQ_DEMO_SEED", "1")
    monkeypatch.setenv("RAFIQ_DASHBOARD_KEY", "secret")
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "vt")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "appsecret")
    from app.main import app
    with TestClient(app, headers={"X-API-Key": "secret"}) as c:
        yield c


def test_auth_required(client):
    assert client.get("/api/overview", headers={"X-API-Key": "nope"}).status_code == 401
    assert client.get("/api/overview").status_code == 200
    assert client.get("/health", headers={"X-API-Key": "x"}).status_code == 200


def test_overview_and_alert_queue_sorted_urgent_first(client):
    ov = client.get("/api/overview").json()
    assert ov["patients"] == 6 and ov["open_urgent"] >= 1
    al = client.get("/api/alerts").json()
    assert al[0]["level"] == 2


def test_ack_and_resolve_are_audited(client):
    a = client.get("/api/alerts").json()[0]
    assert client.post(f"/api/alerts/{a['id']}/ack", json={"note": "called patient"}).status_code == 200
    assert client.get("/api/alerts?status=ack").json()[0]["note"] == "called patient"
    assert client.get("/api/overview").json()["median_urgent_ack_min"] is not None


def test_patient_detail_has_no_internal_fields(client):
    pid = client.get("/api/patients").json()[0]["id"]
    d = client.get(f"/api/patients/{pid}").json()
    assert "session" not in d["patient"] and d["readings"]


def test_enroll_validation_and_welcome(client):
    bad = client.post("/api/patients", json={"name": "x", "phone": "962799999999", "dialect": "klingon"})
    assert bad.status_code == 422
    ok = client.post("/api/patients", json={"name": "ليلى", "phone": "962799999999", "gender": "f", "dialect": "gulf",
                                            "conditions": ["diabetes"], "medications": [{"name": "ميتفورمين", "times": ["08:00"]}]})
    assert ok.status_code == 201
    msgs = client.get(f"/api/patients/{ok.json()['id']}/messages").json()
    assert "نعم" in msgs[0]["body"]
    assert client.post("/api/patients", json={"name": "d", "phone": "962799999999"}).status_code == 409


def test_simulator_roundtrip(client):
    pid = next(p["id"] for p in client.get("/api/patients").json() if p["name"] == "أبو فهد")
    client.post(f"/api/patients/{pid}/start-checkin")
    r = client.post("/api/sim/send", json={"patient_id": pid, "text": "ضغط"}).json()
    r = client.post("/api/sim/send", json={"patient_id": pid, "text": "40"}).json()
    assert any("⚠️" in m for m in r["replies"])


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(b"appsecret", body, hashlib.sha256).hexdigest()


def wa_payload(msg_id, text, phone="962790000006"):
    return {"entry": [{"changes": [{"value": {"messages": [{"id": msg_id, "from": phone, "type": "text", "text": {"body": text}}]}}]}]}


def test_webhook_verification(client):
    ok = client.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "vt", "hub.challenge": "123"})
    assert ok.status_code == 200 and ok.text == "123"
    assert client.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "bad", "hub.challenge": "1"}).status_code == 403


def test_webhook_rejects_bad_signature_and_dedupes(client):
    body = json.dumps(wa_payload("wamid.1", "عندي وجع في صدري")).encode()
    assert client.post("/webhook/whatsapp", content=body, headers={"X-Hub-Signature-256": "sha256=bad"}).status_code == 401
    h = {"X-Hub-Signature-256": sign(body), "Content-Type": "application/json"}
    assert client.post("/webhook/whatsapp", content=body, headers=h).status_code == 200
    assert client.post("/webhook/whatsapp", content=body, headers=h).status_code == 200   # Meta retry
    al = [a for a in client.get("/api/alerts").json() if a["patient_name"] == "يوسف الخطيب" and a["level"] == 2]
    assert len(al) == 1
