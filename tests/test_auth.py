"""Authentication, roles, isolation and web hardening."""
import pytest
from fastapi.testclient import TestClient

from tests.test_api import PW, admin, client, lina, login, omar, patient1  # noqa: F401  (fixtures)


# ── sign-in ─────────────────────────────────────────────────────────────────
def test_pages_redirect_to_login_when_signed_out(client):
    c = TestClient(client.app_, follow_redirects=False)
    for path in ("/", "/dashboard", "/admin", "/patient"):
        r = c.get(path)
        assert r.status_code == 303 and r.headers["location"] == "/login"
    assert c.get("/login").status_code == 200


def test_apis_require_a_session(client):
    c = TestClient(client.app_)
    for path in ("/api/overview", "/api/patients", "/api/alerts", "/api/admin/users", "/api/me/summary", "/api/thresholds"):
        assert c.get(path).status_code == 401, path


def test_wrong_password_is_generic_and_audited(client):
    c = TestClient(client.app_)
    a = c.post("/api/auth/login", json={"username": "demo-admin", "password": "nope"})
    b = c.post("/api/auth/login", json={"username": "nobody", "password": "nope"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()      # no user enumeration
    assert any(r["action"] == "login_failed" for r in login(client, "demo-admin").get("/api/admin/audit").json())


def test_lockout_after_repeated_failures(client):
    c = TestClient(client.app_)
    for _ in range(5):
        c.post("/api/auth/login", json={"username": "demo-lina", "password": "bad"})
    r = c.post("/api/auth/login", json={"username": "demo-lina", "password": PW})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_session_cookie_is_httponly_samesite_and_hashed_in_db(client):
    c = TestClient(client.app_)
    r = c.post("/api/auth/login", json={"username": "demo-lina", "password": PW})
    sc = r.headers["set-cookie"].lower()
    assert "httponly" in sc and "samesite=lax" in sc
    token = c.cookies.get("rafiq_session")
    stored = [x["token_hash"] for x in client.app_.state.db.all("SELECT token_hash FROM sessions")]
    assert token not in stored and len(token) > 30


def test_logout_revokes_the_session_server_side(client):
    c = login(client, "demo-lina")
    token = c.cookies.get("rafiq_session")
    assert c.post("/api/auth/logout").status_code == 200
    c.cookies.set("rafiq_session", token)                  # replay the old cookie
    assert c.get("/api/overview").status_code == 401


def test_disabled_user_is_locked_out_immediately(client, admin):
    lina = login(client, "demo-lina")
    uid = next(u["id"] for u in admin.get("/api/admin/users").json() if u["username"] == "demo-lina")
    assert admin.patch(f"/api/admin/users/{uid}", json={"active": False}).status_code == 200
    assert lina.get("/api/overview").status_code == 401
    assert TestClient(client.app_).post("/api/auth/login", json={"username": "demo-lina", "password": PW}).status_code == 401


def test_admin_cannot_disable_self(client, admin):
    me = admin.get("/api/auth/me").json()
    assert admin.patch(f"/api/admin/users/{me['id']}", json={"active": False}).status_code == 422


def test_password_reset_signs_user_out_and_forces_change(client, admin):
    patient = login(client, "demo-patient2")
    uid = next(u["id"] for u in admin.get("/api/admin/users").json() if u["username"] == "demo-patient2")
    tmp = admin.post(f"/api/admin/users/{uid}/reset-password").json()["temp_password"]
    assert patient.get("/api/me/summary").status_code == 401
    c = TestClient(client.app_)
    assert c.post("/api/auth/login", json={"username": "demo-patient2", "password": tmp}).json()["must_change"]
    assert c.get("/api/me/summary").status_code == 403


# ── role isolation ──────────────────────────────────────────────────────────
def test_login_redirects_by_role(client):
    for user, dest in (("demo-admin", "/admin"), ("demo-lina", "/dashboard"), ("demo-patient1", "/patient")):
        r = TestClient(client.app_).post("/api/auth/login", json={"username": user, "password": PW})
        assert r.json()["redirect"] == dest


def test_pages_enforce_role(client, lina, patient1):
    lina_c, pat_c = TestClient(client.app_, follow_redirects=False), None
    lina_c.cookies.update(lina.cookies)
    assert lina_c.get("/admin").headers["location"] == "/dashboard"      # clinician can't open admin page
    pat = TestClient(client.app_, follow_redirects=False); pat.cookies.update(patient1.cookies)
    assert pat.get("/dashboard").headers["location"] == "/patient"
    assert pat.get("/patient").status_code == 200


def test_clinician_sees_only_own_patients(lina, omar):
    l = {p["name"] for p in lina.get("/api/patients").json()}
    o = {p["name"] for p in omar.get("/api/patients").json()}
    assert len(l) == 4 and len(o) == 4 and not l & o
    assert lina.get("/api/overview").json()["patients"] == 4
    assert all(a["patient_name"] in l for a in lina.get("/api/alerts?status=all").json())


def test_clinician_cannot_open_or_act_on_another_clinicians_patient(lina, omar):
    other = omar.get("/api/patients").json()[0]["id"]
    assert lina.get(f"/api/patients/{other}").status_code == 404
    assert lina.get(f"/api/patients/{other}/messages").status_code == 404
    assert lina.post("/api/sim/send", json={"patient_id": other, "text": "hi"}).status_code == 404
    assert lina.patch(f"/api/patients/{other}", json={"dialect": "gulf"}).status_code == 404
    alert = omar.get("/api/alerts").json()[0]
    assert lina.post(f"/api/alerts/{alert['id']}/ack", json={}).status_code == 404


def test_clinician_cannot_use_admin_apis(lina, patient1):
    for c in (lina, patient1):
        assert c.get("/api/admin/users").status_code == 403
        assert c.post("/api/admin/users", json={"username": "evil", "display_name": "x", "role": "admin"}).status_code == 403
        assert c.get("/api/admin/audit").status_code == 403
        assert c.post("/api/sim/tick", json={}).status_code == 403


def test_patient_cannot_use_staff_apis(patient1):
    for path in ("/api/patients", "/api/alerts", "/api/overview", "/api/patients/1", "/api/thresholds"):
        assert patient1.get(path).status_code == 403, path


def test_clinician_enrolls_into_own_panel_only(lina, admin):
    cid = admin.get("/api/admin/clinicians").json()
    omar_id = next(c["id"] for c in cid if "عمر" in c["name"])
    out = lina.post("/api/patients", json={"name": "جديد", "phone": "962788888888", "clinician_id": omar_id, "send_welcome": False}).json()
    assert "جديد" in {p["name"] for p in lina.get("/api/patients").json()}   # forced into Lina's own panel


# ── patient portal ──────────────────────────────────────────────────────────
def test_patient_summary_is_own_data_and_hides_clinical_internals(patient1):
    s = patient1.get("/api/me/summary").json()
    assert s["profile"]["name"] == "أم خالد" and s["profile"]["emergency_number"] == "911"
    assert s["breast"]["screening_status"] == "overdue" and "alerts" not in s and "summary_en" not in str(s)
    assert "risk_flags" not in str(s) and "notes" not in str(s["breast"])


def test_patient_web_chat_runs_the_same_safety_engine_and_pages_the_clinician(client, patient1, lina):
    r = patient1.post("/api/me/chat", json={"text": "عندي وجع في صدري"}).json()
    assert "911" in r["replies"][-1]
    urgent = [a for a in lina.get("/api/alerts").json() if a["patient_name"] == "أم خالد" and a["level"] == 2]
    assert urgent and urgent[0]["notified"] == 1
    msgs = patient1.get("/api/me/messages").json()
    assert any("911" in m["body"] for m in msgs) and all(m["direction"] in ("in", "out") for m in msgs)


def test_patient_checkin_by_web_chat(patient1, lina):
    patient1.post("/api/me/chat", json={"text": "ابدأ"})
    patient1.post("/api/me/chat", json={"text": "نعم"})
    patient1.post("/api/me/chat", json={"text": "لا"})
    last = patient1.get("/api/me/summary").json()["last_checkin"]
    assert last["level"] == 0


# ── admin console ───────────────────────────────────────────────────────────
def test_admin_creates_clinician_with_login_and_linked_user(admin, client):
    out = admin.post("/api/admin/clinicians", json={"name": "Dr Nour Saleh", "language": "en", "create_login": True}).json()
    assert out["login"]["username"] == "dr.nour.saleh"
    c = TestClient(client.app_)
    assert c.post("/api/auth/login", json={"username": "dr.nour.saleh", "password": out["login"]["temp_password"]}).json()["redirect"] == "/dashboard"


def test_admin_user_validation(admin):
    assert admin.post("/api/admin/users", json={"username": "x y", "display_name": "x", "role": "admin"}).status_code == 422
    assert admin.post("/api/admin/users", json={"username": "demo-admin", "display_name": "x", "role": "admin"}).status_code == 409
    assert admin.post("/api/admin/users", json={"username": "newclin", "display_name": "x", "role": "clinician"}).status_code == 422
    pid = admin.get("/api/patients").json()[0]["id"]
    assert admin.post("/api/admin/users", json={"display_name": "x", "role": "patient", "patient_id": pid}).status_code == 409   # already has a login


def test_system_status_and_demo_warning(admin):
    s = admin.get("/api/admin/system").json()
    assert s["demo_mode"] and s["counts"]["patients"] == 8 and s["database"] in ("SQLite", "PostgreSQL")


# ── web hardening ───────────────────────────────────────────────────────────
def test_cross_origin_state_change_is_blocked(lina):
    r = lina.post("/api/alerts/1/ack", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = lina.post("/api/auth/logout", headers={"Origin": "http://testserver"})
    assert r.status_code == 200


def test_security_headers_present(client):
    r = client.get("/login")
    assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert client.get("/api/auth/public").headers["cache-control"] == "no-store"


def test_demo_hint_endpoint_only_lists_demo_accounts(client):
    j = client.get("/api/auth/public").json()
    assert j["demo"] and all(a["username"].startswith("demo-") for a in j["accounts"])


def test_password_hashing_is_salted_and_verifiable():
    from app import auth
    a, b = auth.hash_password("same-pass-1"), auth.hash_password("same-pass-1")
    assert a != b and auth.verify_password("same-pass-1", a) and not auth.verify_password("other", a)
    assert not auth.verify_password("x", "garbage")
