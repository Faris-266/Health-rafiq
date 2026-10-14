"""Public registration, verification, login aliases, data rights, and the staff breast-health API."""
import re

import pytest
from fastapi.testclient import TestClient

from app import routes_account
from tests.test_api import PW, admin, client, lina, login, omar, patient1  # noqa: F401

NEW = {"name": "ليلى حداد", "phone": "+962 79 555 0101", "email": "Laila@Example.com", "password": "Str0ng-pass-1", "birth_year": 1982,
       "gender": "f", "dialect": "levantine", "country": "JO", "consent": True}


@pytest.fixture(autouse=True)
def _reset_limiters():
    for lim in (routes_account.signup_limiter, routes_account.resend_limiter, routes_account.verify_limiter, routes_account.forgot_limiter):
        lim._d.clear()


def anon(client):
    c = TestClient(client.app_)
    c.app_ = client.app_
    return c


class FakeChannel:
    name = "whatsapp"
    def __init__(self): self.sent = []
    def send(self, phone, text, template=None, params=None): self.sent.append((phone, text, template, params))


# ── sign-up ─────────────────────────────────────────────────────────────────
def test_signup_config_is_public(client):
    j = anon(client).get("/api/auth/signup-config").json()
    assert j["enabled"] and j["min_age"] == 18 and "en" in j["dialects"]


def test_register_without_verification_logs_in_and_starts_intake(client):
    c = anon(client)
    r = c.post("/api/auth/register", json=NEW)
    assert r.status_code == 201 and r.json()["redirect"] == "/patient"
    s = c.get("/api/me/summary").json()
    assert s["profile"]["name"] == "ليلى حداد" and s["breast"]["intake_done"] is False and s["profile"]["consent"] is True
    out = c.post("/api/me/chat", json={"text": "ابدأ"}).json()["replies"]
    assert any("عمرك" in m for m in out)                                  # intake begins in the web chat
    msgs = c.get("/api/me/messages").json()
    assert msgs and all(m["direction"] in ("in", "out") for m in msgs)


def test_full_intake_in_web_chat_completes_profile(client):
    c = anon(client); c.post("/api/auth/register", json=NEW)
    for t in ("ابدأ", "44", "لا", "لا", "لا", "لا", "ما اذكر"):
        c.post("/api/me/chat", json={"text": t})
    b = c.get("/api/me/summary").json()["breast"]
    assert b["intake_done"] and b["screening_status"] == "due" and b["age"] == 44


def test_login_by_email_phone_and_username(client):
    anon(client).post("/api/auth/register", json=NEW)
    for ident in ("laila@example.com", "LAILA@example.com", "962795550101", "+962 79 555 0101"):
        assert anon(client).post("/api/auth/login", json={"username": ident, "password": NEW["password"]}).status_code == 200, ident


@pytest.mark.parametrize("patch,code", [
    ({"consent": False}, 422), ({"birth_year": 2015}, 422), ({"password": "short"}, 422), ({"password": "password"}, 422),
    ({"phone": "123"}, 422), ({"email": "not-an-email"}, 422), ({"dialect": "klingon"}, 422), ({"invite_code": "NOPE1234"}, 422),
])
def test_register_validation(client, patch, code):
    assert anon(client).post("/api/auth/register", json={**NEW, **patch}).status_code == code


def test_duplicate_registration_is_rejected(client):
    anon(client).post("/api/auth/register", json=NEW)
    assert anon(client).post("/api/auth/register", json={**NEW, "email": "other@example.com"}).status_code == 409     # same phone
    assert anon(client).post("/api/auth/register", json={**NEW, "phone": "962795550999"}).status_code == 409           # same email


def test_signup_is_rate_limited(client):
    codes = [anon(client).post("/api/auth/register", json={**NEW, "phone": f"96279555{i:04d}", "email": f"u{i}@e.com"}).status_code for i in range(7)]
    assert codes[:5] == [201] * 5 and codes[5] == 429


def test_invite_code_assigns_the_patient_to_that_clinician(client, lina, omar):
    anon(client).post("/api/auth/register", json={**NEW, "invite_code": "demolina"})
    assert "ليلى حداد" in {p["name"] for p in lina.get("/api/patients").json()}
    assert "ليلى حداد" not in {p["name"] for p in omar.get("/api/patients").json()}


def test_invite_can_be_required(client, monkeypatch):
    monkeypatch.setenv("RAFIQ_REQUIRE_INVITE", "1")
    assert anon(client).post("/api/auth/register", json=NEW).status_code == 422
    assert anon(client).post("/api/auth/register", json={**NEW, "invite_code": "DEMOOMAR"}).status_code == 201


def test_signup_can_be_disabled(client, monkeypatch):
    monkeypatch.setenv("RAFIQ_ALLOW_SIGNUP", "0")
    assert anon(client).post("/api/auth/register", json=NEW).status_code == 403


def test_staff_cannot_self_register_and_new_users_are_patients_only(client):
    anon(client).post("/api/auth/register", json={**NEW, "role": "admin"})            # unknown field is ignored
    me = anon(client).post("/api/auth/login", json={"username": "laila@example.com", "password": NEW["password"]})
    assert me.json()["role"] == "patient"


# ── verification ────────────────────────────────────────────────────────────
def test_email_verification_flow(client, monkeypatch):
    monkeypatch.setenv("RAFIQ_VERIFY", "email")
    sent = []
    monkeypatch.setattr("app.notify.send_email", lambda to, subject, body: sent.append((to, body)) or True)
    c = anon(client)
    r = c.post("/api/auth/register", json=NEW).json()
    assert r["status"] == "verification_required" and r["verification"] == "email" and sent[0][0] == "laila@example.com"
    code = re.search(r"\b(\d{6})\b", sent[0][1]).group(1)
    assert c.get("/api/me/summary").status_code == 401                                   # no session until verified
    assert anon(client).post("/api/auth/login", json={"username": NEW["email"], "password": NEW["password"]}).json()["detail"] == "verification_required"
    assert c.post("/api/auth/verify", json={"username": NEW["email"], "code": "000000"}).status_code == 400
    ok = c.post("/api/auth/verify", json={"username": NEW["email"], "code": code})
    assert ok.status_code == 200 and c.get("/api/me/summary").status_code == 200
    assert c.post("/api/auth/verify", json={"username": NEW["email"], "code": code}).status_code == 400   # codes are single-use


def test_verification_code_locks_after_five_wrong_attempts(client, monkeypatch):
    monkeypatch.setenv("RAFIQ_VERIFY", "email")
    sent = []
    monkeypatch.setattr("app.notify.send_email", lambda to, subject, body: sent.append(body) or True)
    c = anon(client); c.post("/api/auth/register", json=NEW)
    code = re.search(r"\b(\d{6})\b", sent[0]).group(1)
    for _ in range(5):
        c.post("/api/auth/verify", json={"username": NEW["email"], "code": "111111" if code != "111111" else "222222"})
    assert c.post("/api/auth/verify", json={"username": NEW["email"], "code": code}).status_code == 400


def test_whatsapp_verification_uses_template_and_resend_has_cooldown(client, monkeypatch):
    monkeypatch.setenv("RAFIQ_VERIFY", "whatsapp")
    fake = FakeChannel()
    monkeypatch.setattr(client.app_.state, "channel", fake)
    c = anon(client)
    assert c.post("/api/auth/register", json=NEW).json()["verification"] == "whatsapp"
    phone, text, template, params = fake.sent[0]
    assert phone == "962795550101" and template == "rafiq_verify" and params[0].isdigit() and len(params[0]) == 6
    assert c.post("/api/auth/resend", json={"username": NEW["email"]}).status_code == 429       # cooldown
    assert c.post("/api/auth/verify", json={"username": NEW["phone"], "code": params[0]}).status_code == 200


def test_email_mode_requires_an_email(client, monkeypatch):
    monkeypatch.setenv("RAFIQ_VERIFY", "email")
    assert anon(client).post("/api/auth/register", json={**NEW, "email": None}).status_code == 422


# ── data rights ─────────────────────────────────────────────────────────────
def test_export_my_data(client):
    c = anon(client); c.post("/api/auth/register", json=NEW)
    c.post("/api/me/chat", json={"text": "ابدأ"})
    r = c.get("/api/me/export")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    d = r.json()
    assert d["profile"]["name"] == "ليلى حداد" and d["messages"] and "session" not in d["profile"] and "password_hash" not in str(d)


def test_delete_account_removes_everything_and_anonymises_audit(client, admin):
    c = anon(client); c.post("/api/auth/register", json=NEW)
    c.post("/api/me/chat", json={"text": "لقيت كتلة في صدري"})                     # creates alert + referral + messages
    assert c.post("/api/me/delete-account", json={"password": "wrong", "confirm": "DELETE"}).status_code == 403
    assert c.post("/api/me/delete-account", json={"password": NEW["password"], "confirm": "nope"}).status_code == 422
    assert c.post("/api/me/delete-account", json={"password": NEW["password"], "confirm": "DELETE"}).status_code == 200
    assert c.get("/api/me/summary").status_code == 401
    assert anon(client).post("/api/auth/login", json={"username": NEW["email"], "password": NEW["password"]}).status_code == 401
    db = client.app_.state.db
    assert not db.one("SELECT 1 FROM patients WHERE name=?", ("ليلى حداد",))
    assert not db.one("SELECT 1 FROM referrals r JOIN patients p ON p.id=r.patient_id WHERE p.name=?", ("ليلى حداد",))
    assert db.one("SELECT 1 FROM audit_log WHERE action='account_deleted'")
    assert not db.one("SELECT 1 FROM audit_log WHERE actor=? AND patient_id IS NOT NULL", (NEW["email"].lower(),))
    assert "ليلى حداد" not in {p["name"] for p in admin.get("/api/patients").json()}


# ── staff breast-health API ─────────────────────────────────────────────────
def test_referral_queue_is_scoped_and_sorted_overdue_first(lina, omar):
    mine = lina.get("/api/referrals").json()
    assert mine and mine[0]["patient_name"] == "سارة المنصوري" and mine[0]["overdue"] and mine[0]["priority"] == "urgent"
    assert all(r["patient_name"] != "Reem Saleh" for r in mine)
    assert any(r["patient_name"] == "Reem Saleh" for r in omar.get("/api/referrals").json())
    assert all(r["overdue"] for r in lina.get("/api/referrals?status=overdue").json())


def test_staff_updates_referral_through_its_lifecycle_and_clinicians_cannot_touch_others(lina, omar):
    rid = lina.get("/api/referrals").json()[0]["id"]
    assert omar.patch(f"/api/referrals/{rid}", json={"status": "contacted"}).status_code == 404
    assert lina.patch(f"/api/referrals/{rid}", json={"status": "contacted", "notes": "Called, no answer"}).json()["status"] == "contacted"
    assert lina.patch(f"/api/referrals/{rid}", json={"appointment_date": "2026-10-20"}).json()["status"] == "booked"
    assert lina.patch(f"/api/referrals/{rid}", json={"status": "closed"}).status_code == 422                      # outcome required
    assert lina.patch(f"/api/referrals/{rid}", json={"status": "seen"}).json()["seen_at"]
    out = lina.patch(f"/api/referrals/{rid}", json={"status": "closed", "outcome": "benign"}).json()
    assert out["status"] == "closed"
    assert not [a for a in lina.get("/api/alerts").json() if a["patient_name"] == "سارة المنصوري" and "OVERDUE" in a["summary_en"]]


def test_log_screening_via_api_and_validation(lina):
    pid = next(p["id"] for p in lina.get("/api/patients").json() if p["name"] == "أم خالد")
    ok = lina.post(f"/api/patients/{pid}/screenings", json={"kind": "mammogram", "done_on": "2026-10-01", "birads": 2})
    assert ok.status_code == 201 and ok.json()["next_due"] == "2027-10-01"
    d = lina.get(f"/api/patients/{pid}").json()["breast"]
    assert d["screening_status"] == "up_to_date" and d["screenings"][0]["birads"] == 2
    assert lina.post(f"/api/patients/{pid}/screenings", json={"kind": "xray", "done_on": "2026-10-01"}).status_code == 422
    assert lina.post(f"/api/patients/{pid}/screenings", json={"kind": "mammogram", "done_on": "2099-01-01"}).status_code == 422
    assert lina.post(f"/api/patients/{pid}/screenings", json={"kind": "mammogram", "done_on": "2026-10-01", "birads": 9}).status_code == 422


def test_urgent_birads_via_api_creates_urgent_referral(lina):
    pid = next(p["id"] for p in lina.get("/api/patients").json() if p["name"] == "أم خالد")
    out = lina.post(f"/api/patients/{pid}/screenings", json={"kind": "mammogram", "done_on": "2026-10-05", "birads": 5}).json()
    assert out["referral_id"] and out["status"] == "referred"
    assert any(r["id"] == out["referral_id"] and r["priority"] == "urgent" for r in lina.get("/api/referrals").json())


def test_staff_can_set_an_individual_screening_plan(omar):
    pid = next(p["id"] for p in omar.get("/api/patients").json() if p["name"] == "فاطمة الزهراء")
    assert omar.get(f"/api/patients/{pid}").json()["breast"]["screening_status"] == "specialist_plan"
    assert omar.patch(f"/api/patients/{pid}", json={"next_screening_due": "2099-01-01"}).status_code == 200
    assert omar.get(f"/api/patients/{pid}").json()["breast"]["screening_status"] == "up_to_date"
    assert omar.patch(f"/api/patients/{pid}", json={"next_screening_due": "soon"}).status_code == 422


def test_overview_has_breast_kpis(lina):
    o = lina.get("/api/overview").json()
    assert o["screening"]["breast_patients"] == 3 and o["screening"]["intake_pending"] >= 1
    assert o["referrals"]["open"] >= 1 and o["referrals"]["overdue"] >= 1


def test_patient_detail_exposes_risk_profile_to_staff_only(lina, patient1):
    pid = next(p["id"] for p in lina.get("/api/patients").json() if p["name"] == "أم خالد")
    b = lina.get(f"/api/patients/{pid}").json()["breast"]
    assert b["risk_category"] == "average" and b["intake_done"] and "risk_flags" in b
    assert patient1.get(f"/api/patients/{pid}").status_code == 403


def test_admin_assigns_unassigned_patients_and_manages_invite_codes(client, admin, lina):
    anon(client).post("/api/auth/register", json=NEW)                                # no invite → unassigned
    assert admin.get("/api/admin/system").json()["unassigned_patients"] == 1
    pid = next(p["id"] for p in admin.get("/api/patients").json() if p["name"] == "ليلى حداد")
    lina_id = next(c["id"] for c in admin.get("/api/admin/clinicians").json() if c["invite_code"] == "DEMOLINA")
    assert admin.post(f"/api/admin/patients/{pid}/assign", json={"clinician_id": lina_id}).status_code == 200
    assert "ليلى حداد" in {p["name"] for p in lina.get("/api/patients").json()}
    code = admin.post(f"/api/admin/clinicians/{lina_id}/invite-code").json()["invite_code"]
    assert len(code) == 8 and anon(client).post("/api/auth/register", json={**NEW, "phone": "962795550777", "email": "x@y.com", "invite_code": "DEMOLINA"}).status_code == 422


# ── admin-set passwords, forced change, forgot password ─────────────────────
def test_admin_can_set_the_password_and_skip_forced_change(admin, client):
    out = admin.post("/api/admin/users", json={"username": "newdoc", "display_name": "Dr New", "role": "admin", "password": "Chosen-pass-1", "require_change": False})
    assert out.status_code == 201 and out.json()["temp_password"] is None and out.json()["must_change"] is False   # not echoed back
    c = anon(client)
    r = c.post("/api/auth/login", json={"username": "newdoc", "password": "Chosen-pass-1"})
    assert r.status_code == 200 and r.json()["must_change"] is False
    assert c.get("/api/admin/users").status_code == 200                            # works immediately, no "current password" prompt


def test_admin_set_password_can_still_require_change_and_is_validated(admin, client):
    assert admin.post("/api/admin/users", json={"username": "weak1", "display_name": "x", "role": "admin", "password": "short"}).status_code == 422
    admin.post("/api/admin/users", json={"username": "newdoc2", "display_name": "x", "role": "admin", "password": "Chosen-pass-1", "require_change": True})
    c = anon(client)
    assert c.post("/api/auth/login", json={"username": "newdoc2", "password": "Chosen-pass-1"}).json()["must_change"] is True
    assert c.get("/api/admin/users").status_code == 403                            # forced change first
    assert c.post("/api/auth/change-password", json={"current": "Chosen-pass-1", "new": "Another-pass-2"}).status_code == 200
    assert c.get("/api/admin/users").status_code == 200


def test_generated_temp_password_is_the_current_password_for_the_forced_change(admin, client):
    out = admin.post("/api/admin/users", json={"username": "newdoc3", "display_name": "x", "role": "admin"}).json()
    assert out["temp_password"] and out["must_change"] is True
    c = anon(client)
    c.post("/api/auth/login", json={"username": "newdoc3", "password": out["temp_password"]})
    assert c.post("/api/auth/change-password", json={"current": out["temp_password"], "new": "Brand-new-pass-3"}).status_code == 200


def test_clinician_created_with_own_password(admin, client):
    out = admin.post("/api/admin/clinicians", json={"name": "Dr Pass", "language": "en", "create_login": True, "password": "Doc-pass-2026", "require_change": False}).json()
    assert out["login"]["temp_password"] is None
    assert anon(client).post("/api/auth/login", json={"username": out["login"]["username"], "password": "Doc-pass-2026"}).json()["must_change"] is False


def test_forgot_password_unavailable_without_a_delivery_channel(client):
    assert anon(client).post("/api/auth/forgot", json={"identifier": "laila@example.com"}).json() == {"status": "unavailable"}


def test_forgot_and_reset_password_by_email_code(client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.notify.send_email", lambda to, subject, body: sent.append((to, body)) or True)
    anon(client).post("/api/auth/register", json=NEW)                               # (verification off → account is live)
    monkeypatch.setenv("RAFIQ_VERIFY", "email")
    c = anon(client)
    assert c.post("/api/auth/forgot", json={"identifier": "nobody@example.com"}).json() == {"status": "ok"}   # same answer for unknown accounts
    assert not sent
    assert c.post("/api/auth/forgot", json={"identifier": NEW["email"]}).json() == {"status": "ok"}
    code = re.search(r"\b(\d{6})\b", sent[0][1]).group(1)
    assert c.post("/api/auth/reset", json={"identifier": NEW["email"], "code": code, "new_password": "short"}).status_code == 422   # doesn't burn the code
    assert c.post("/api/auth/reset", json={"identifier": NEW["email"], "code": "000000", "new_password": "Reset-pass-9"}).status_code == 400
    assert c.post("/api/auth/reset", json={"identifier": NEW["email"], "code": code, "new_password": "Reset-pass-9"}).status_code == 200
    assert c.post("/api/auth/reset", json={"identifier": NEW["email"], "code": code, "new_password": "Reset-pass-9"}).status_code == 400   # single use
    assert anon(client).post("/api/auth/login", json={"username": NEW["email"], "password": NEW["password"]}).status_code == 401           # old password gone
    assert anon(client).post("/api/auth/login", json={"username": NEW["email"], "password": "Reset-pass-9"}).status_code == 200


def test_reset_signs_out_existing_sessions(client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.notify.send_email", lambda to, subject, body: sent.append(body) or True)
    c = anon(client); c.post("/api/auth/register", json=NEW)
    monkeypatch.setenv("RAFIQ_VERIFY", "email")
    anon(client).post("/api/auth/forgot", json={"identifier": NEW["phone"]})
    code = re.search(r"\b(\d{6})\b", sent[0]).group(1)
    anon(client).post("/api/auth/reset", json={"identifier": NEW["phone"], "code": code, "new_password": "Reset-pass-9"})
    assert c.get("/api/me/summary").status_code == 401
