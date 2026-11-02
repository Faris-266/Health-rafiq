"""Doctor ↔ patient messaging, automatic replies, and what must never happen."""
import json
from datetime import timedelta

import pytest

from app import messaging, routes_messaging
from app.channels import NullChannel
from app.conversation import Engine
from app.triage import Level
from tests.conftest import make_patient
from tests.test_api import PW, admin, client, lina, login, omar, patient1, sign, wa_payload  # noqa: F401

PHONE = "962790000111"
CLIN_PHONE = "962790009999"


class WA(NullChannel):
    name = "whatsapp"

    def __init__(self): super().__init__(); self.calls = []

    def send(self, phone, text, template=None, params=None):
        self.calls.append((phone, text, template, params)); return True


@pytest.fixture(autouse=True)
def _reset():
    routes_messaging.send_limiter._d.clear()


@pytest.fixture
def pid(db):
    return make_patient(db, name="سعاد", phone=PHONE, gender="f", dialect="levantine", conditions="diabetes")


def say(eng, text, phone=PHONE):
    return eng.handle_inbound(phone, text)


def msgs(db, pid):
    return db.all("SELECT * FROM messages WHERE patient_id=? ORDER BY id", (pid,))


# ── doctor → patient ────────────────────────────────────────────────────────
def test_doctor_message_is_stored_visible_and_opens_a_48h_thread(eng, db, pid, clock):
    receipt = eng.staff_send(eng.patient(pid), "Dr Test", "Please re-check your sugar in 15 minutes.")
    m = msgs(db, pid)[-1]
    assert m["direction"] == "out" and m["kind"] == "clinician" and m["sender"] == "Dr Test" and receipt["in_app"] and receipt["whatsapp"] == "off"
    until = eng.patient(pid)["clinician_thread_until"]
    assert until == (clock.dt + timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S")


def test_whatsapp_plain_text_inside_window_template_outside(db, clock, pid):
    wa = WA(); e = Engine(db, wa, now_fn=clock)
    db.execute("UPDATE patients SET last_inbound_at=?", ((clock.dt - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S"),))
    assert e.staff_send(e.patient(pid), "Dr Test", "Come today")["whatsapp"] == "sent"
    assert wa.calls[-1][1] == "Dr Test: Come today" and wa.calls[-1][2] is None
    db.execute("UPDATE patients SET last_inbound_at=?", ((clock.dt - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%S"),))
    assert e.staff_send(e.patient(pid), "Dr Test", "Line one\nLine two")["whatsapp"] == "template"
    phone, text, template, params = wa.calls[-1]
    assert template == "rafiq_clinician_message" and params == ["Dr Test", "Line one | Line two"]      # templates can't contain newlines


@pytest.mark.parametrize("bad", ["see http://evil.example now", "go to www.evil.example", "bit.ly/abc", "   ", "x" * 1001])
def test_unsafe_or_empty_staff_text_is_refused(bad):
    with pytest.raises(ValueError):
        messaging.clean_staff_text(bad)


def test_clean_text_strips_control_characters_but_keeps_arabic():
    assert messaging.clean_staff_text("  مرحبا\x07 يا سعاد  ") == "مرحبا يا سعاد"


# ── patient → doctor (automatic acknowledgement) ────────────────────────────
def test_reply_goes_to_the_doctor_with_one_automatic_acknowledgement(eng, db, pid, clock):
    eng.staff_send(eng.patient(pid), "Dr Test", "How are you today?")
    out = say(eng, "الحمد لله تمام")
    assert "Dr Test" in out[0] and "وسيردّ" in out[0]
    inbound = [m for m in msgs(db, pid) if m["direction"] == "in"][-1]
    assert inbound["kind"] == "clinician" and inbound["read_at"] is None
    assert not db.one("SELECT 1 FROM checkins")                                   # not treated as a questionnaire answer
    assert say(eng, "وبعدين؟") == []                                              # no second acknowledgement within 30 minutes
    clock.dt += timedelta(minutes=31)
    assert len(say(eng, "هل وصلتك رسالتي")) == 1


def test_acknowledgement_outside_clinic_hours_says_when_the_clinic_opens(eng, db, pid, monkeypatch):
    monkeypatch.setenv("RAFIQ_CLINIC_HOURS", "09:00-10:00")                         # it is 08:00 in Amman in the fixture
    eng.staff_send(eng.patient(pid), "Dr Test", "Hello")
    out = say(eng, "شكرا")
    assert "مغلقة" in out[0] and "09:00" in out[0]


def test_english_patient_gets_english_acknowledgement(eng, db):
    p2 = make_patient(db, name="Hala", phone="971500000009", gender="f", dialect="en", conditions="diabetes")
    eng.staff_send(eng.patient(p2), "Dr Test", "Hello Hala")
    out = eng.handle_inbound("971500000009", "thank you")
    assert "was sent to Dr Test" in out[0] and "911" in out[0] or "ambulance" in out[0]


def test_emergency_in_a_thread_still_escalates_first(eng, db, pid):
    eng.staff_send(eng.patient(pid), "Dr Test", "Hello")
    out = say(eng, "عندي وجع في صدري")
    assert "911" in out[-1] and db.one("SELECT 1 FROM alerts WHERE level=?", (int(Level.URGENT),))
    assert [m for m in msgs(db, pid) if m["direction"] == "in"][-1]["kind"] == "bot"     # never parked in the doctor's inbox


def test_opt_out_works_inside_a_thread(eng, db, pid):
    eng.staff_send(eng.patient(pid), "Dr Test", "Hello")
    say(eng, "إيقاف")
    assert eng.patient(pid)["active"] == 0


def test_start_returns_to_the_checkin_and_numbers_otherwise_go_to_the_doctor(eng, db, pid):
    eng.staff_send(eng.patient(pid), "Dr Test", "Send your sugar please")
    say(eng, "130")                                                                # a bare number goes to the doctor, not into a reading
    assert not db.one("SELECT 1 FROM readings")
    out = say(eng, "ابدأ")
    assert any("السكر" in m for m in out) and eng.patient(pid)["state"] == "awaiting_glucose"


def test_thread_expires_after_48_hours(eng, db, pid, clock):
    eng.staff_send(eng.patient(pid), "Dr Test", "Hello")
    clock.dt += timedelta(hours=49)
    out = say(eng, "مرحبا")
    assert eng.patient(pid)["state"].startswith("awaiting_") and out                # the bot is back in charge


# ── clinician writes to the bot's number ────────────────────────────────────
def test_clinician_phone_gets_an_automatic_digest_not_a_route_to_patients(eng, db, pid):
    eng.handle_inbound(PHONE, "عندي وجع في صدري")                                  # urgent alert for the doctor's patient
    out = eng.handle_inbound(CLIN_PHONE, "hello")
    assert "1 open alert" in out[0] and "[URGENT] سعاد" in out[0] and "dashboard" in out[0]
    assert not any(m["body"] == "hello" for m in db.all("SELECT body FROM messages"))
    assert "تنبيهات" not in out[0]


def test_clinician_digest_in_arabic_and_when_empty(eng, db, pid):
    db.execute("UPDATE clinicians SET language='ar' WHERE id=1")
    out = eng.handle_inbound("+962 79 000 9999", "تنبيهات")
    assert "لا توجد تنبيهات مفتوحة" in out[0]


def test_unknown_numbers_still_get_the_polite_refusal(eng, db, pid):
    assert "غير مسجل" in eng.handle_inbound("999000111", "hi")[0]


# ── API: who may message whom ───────────────────────────────────────────────
def pid_of(c, name):
    return next(p["id"] for p in c.get("/api/patients").json() if p["name"] == name)


def test_clinician_sends_to_own_patient_and_patient_sees_it_with_the_doctors_name(lina, patient1):
    pid = pid_of(lina, "أم خالد")
    r = lina.post(f"/api/patients/{pid}/message", json={"text": "Please bring your meter to the clinic."})
    assert r.status_code == 201 and r.json()["delivery"] == {"in_app": True, "whatsapp": "off", "thread_hours": 48}
    mine = [m for m in patient1.get("/api/me/messages").json() if m["kind"] == "clinician"]
    assert mine and mine[-1]["sender"] == "Dr. Lina Haddad" and mine[-1]["body"].startswith("Please bring")
    assert patient1.get("/api/me/summary").json()["thread"]["doctor"] == "Dr. Lina Haddad"


def test_a_clinician_can_message_only_their_own_patients(lina, omar, patient1, client):
    other = pid_of(omar, "Reem Saleh")
    assert lina.post(f"/api/patients/{other}/message", json={"text": "hi"}).status_code == 404
    mine = pid_of(lina, "أم خالد")
    assert patient1.post(f"/api/patients/{mine}/message", json={"text": "hi"}).status_code == 403            # patients can't use it
    anon = type(lina)(client.app_)
    assert anon.post(f"/api/patients/{mine}/message", json={"text": "hi"}).status_code == 401


def test_messages_to_patients_are_validated(lina, client):
    pid = pid_of(lina, "أم خالد")
    assert lina.post(f"/api/patients/{pid}/message", json={"text": "visit http://bad.example"}).status_code == 422
    assert lina.post(f"/api/patients/{pid}/message", json={"text": "  "}).status_code == 422
    client.app_.state.db.execute("UPDATE patients SET consent=0 WHERE id=?", (pid,))
    assert lina.post(f"/api/patients/{pid}/message", json={"text": "hello"}).status_code == 409           # no consent / opted out


def test_sending_is_rate_limited(lina):
    pid = pid_of(lina, "أم خالد")
    codes = [lina.post(f"/api/patients/{pid}/message", json={"text": f"note {i}"}).status_code for i in range(32)]
    assert codes[:30] == [201] * 30 and codes[30] == 429


def test_patient_reply_reaches_doctor_unread_badge_then_read(lina, patient1):
    pid = pid_of(lina, "أم خالد")
    lina.post(f"/api/patients/{pid}/message", json={"text": "How is your sugar?"})
    replies = patient1.post("/api/me/chat", json={"text": "better, thank you"}).json()["replies"]
    assert replies and "Dr. Lina Haddad" in replies[0]                                                  # automatic acknowledgement
    row = next(p for p in lina.get("/api/patients").json() if p["id"] == pid)
    assert row["unread"] == 1 and lina.get("/api/overview").json()["unread_messages"] == 1
    thread = lina.get(f"/api/patients/{pid}/messages").json()
    assert any(m["direction"] == "in" and m["kind"] == "clinician" for m in thread) and any(m["kind"] == "thread_ack" for m in thread)
    assert next(p for p in lina.get("/api/patients").json() if p["id"] == pid)["unread"] == 0          # opening the thread marked it read


def test_suggestions_follow_the_patients_language(lina, omar):
    ar = lina.get(f"/api/patients/{pid_of(lina, 'أم خالد')}/message-suggestions").json()
    en = omar.get(f"/api/patients/{pid_of(omar, 'Hala Nasser')}/message-suggestions").json()
    assert ar["language"] == "ar" and "العيادة" in " ".join(ar["suggestions"])
    assert en["language"] == "en" and "clinic" in " ".join(en["suggestions"]) and len(en["suggestions"]) >= 5


def test_simulated_patient_reply_is_routed_too(lina):
    pid = pid_of(lina, "أم خالد")
    lina.post(f"/api/patients/{pid}/message", json={"text": "Hello"})
    out = lina.post("/api/sim/send", json={"patient_id": pid, "text": "شكرا دكتورة"}).json()["replies"]
    assert out and "Dr. Lina Haddad" in out[0]


def test_clinician_whatsapp_number_receives_the_automatic_digest_via_the_webhook(client, lina, monkeypatch):
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "appsecret")
    fake = WA(); monkeypatch.setattr(client.app_.state, "channel", fake)
    body = json.dumps(wa_payload("wamid.staff1", "alerts", phone=CLIN_PHONE)).encode()
    import hashlib, hmac
    sig = "sha256=" + hmac.new(b"appsecret", body, hashlib.sha256).hexdigest()
    assert client.post("/webhook/whatsapp", content=body, headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"}).status_code == 200
    sent = [c for c in fake.calls if c[0] == CLIN_PHONE]
    assert sent and "open alert" in sent[0][1] and "not registered" not in sent[0][1]
