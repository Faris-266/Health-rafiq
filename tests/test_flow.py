"""End-to-end conversation tests through the real engine (no mocks of the logic)."""
import json
from datetime import timedelta

from app import scheduler
from app.triage import Level
from tests.conftest import make_patient

PHONE = "962790000111"


def say(eng, text, phone=PHONE):
    return eng.handle_inbound(phone, text)


def alerts(db):
    return db.all("SELECT * FROM alerts ORDER BY id")


def test_unknown_number_gets_polite_refusal(eng):
    out = eng.handle_inbound("999999999", "hi")
    assert "غير مسجل" in out[0]


def test_consent_gate_then_checkin(eng, db, pid):
    db.execute("UPDATE patients SET consent=0")
    out = say(eng, "مرحبا")
    assert "نعم" in out[0] and db.one("SELECT state FROM patients")["state"] == "awaiting_consent"
    out = say(eng, "نعم")
    assert db.one("SELECT consent FROM patients")["consent"] == 1
    assert any("السكر" in m for m in out)          # check-in starts right after consent


def test_consent_refusal_stops_everything(eng, db, pid):
    db.execute("UPDATE patients SET consent=0")
    say(eng, "hello"); say(eng, "لا")
    p = db.one("SELECT * FROM patients")
    assert p["active"] == 0 and p["consent"] == 0


def test_full_normal_checkin_levantine_female(eng, db, pid):
    eng.start_checkin(pid)
    first = db.all("SELECT body FROM messages WHERE direction='out'")
    assert "صباح الخير" in first[0]["body"] and "السكر" in first[1]["body"]
    assert "اكتبي" in first[1]["body"]            # feminine imperative
    say(eng, "١٠٥")
    out = say(eng, "120/80")
    assert "يتعبك" in out[-1]                       # symptoms question
    out = say(eng, "لا")                            # symptoms: none
    assert "أخدتي" in out[-1]                       # meds question, feminine form
    out = say(eng, "ايوه")                          # meds: yes
    assert "منيحة" in out[-1]
    assert not alerts(db)
    assert db.one("SELECT COUNT(*) c FROM readings")["c"] == 2
    ck = db.one("SELECT * FROM checkins")
    assert ck["completed"] == 1 and ck["meds_taken"] == 1 and ck["level"] == 0


def test_watch_alert_created_not_notified(eng, db, pid):
    eng.start_checkin(pid)
    say(eng, "165"); say(eng, "128/82"); say(eng, "لا"); say(eng, "اه")
    a = alerts(db)
    assert len(a) == 1 and a[0]["level"] == Level.WATCH and a[0]["notified"] == 0


def test_dangerous_glucose_escalates_immediately_without_finishing(eng, db, pid):
    eng.start_checkin(pid)
    out = say(eng, "45")
    a = alerts(db)
    assert a and a[0]["level"] == Level.URGENT and a[0]["notified"] == 1
    assert "15" in out[-1] or "سكر" in out[-1]       # sugar instruction shown
    p = db.one("SELECT * FROM patients")
    assert p["state"] == "idle" and p["followup_at"]
    assert any(m["direction"] == "clinician_out" for m in db.all("SELECT * FROM messages"))


def test_red_flag_in_any_state_overrides_the_flow(eng, db, pid):
    eng.start_checkin(pid)
    say(eng, "110")                                  # now awaiting BP
    out = say(eng, "عندي وجع في صدري")
    a = alerts(db)
    assert a[0]["level"] == Level.URGENT
    assert "911" in out[-1]                          # Jordan emergency number
    assert db.one("SELECT state FROM patients")["state"] == "idle"
    assert db.one("SELECT COUNT(*) c FROM readings")["c"] == 1   # the glucose we already had is preserved


def test_red_flag_even_when_idle_or_unconsented(eng, db, pid):
    db.execute("UPDATE patients SET consent=0")
    out = say(eng, "مش قادر اتنفس")
    assert alerts(db)[0]["level"] == Level.URGENT and "911" in out[-1]


def test_self_harm_gets_supportive_message_and_clinician_alert(eng, db, pid):
    out = say(eng, "بدي اموت")
    assert "لا تبقَ وحدك" in out[-1] and "911" in out[-1]
    a = alerts(db)[0]
    assert a["level"] == Level.URGENT and a["notified"] == 1


def test_negated_red_flag_does_not_escalate(eng, db, pid):
    eng.start_checkin(pid)
    say(eng, "110"); say(eng, "120/80")
    say(eng, "ما عندي وجع صدر ولا ضيق نفس")
    assert not alerts(db)


def test_both_numbers_in_one_message(eng, db, pid):
    eng.start_checkin(pid)
    out = say(eng, "سكري 105 وضغطي 125/80")
    assert "السكر" not in out[-1] and "ضغط" not in out[-1]   # skipped straight to symptoms
    assert db.one("SELECT state FROM patients")["state"] == "awaiting_symptoms"


def test_unclear_reading_retries_then_moves_on(eng, db, pid):
    eng.start_checkin(pid)
    for _ in range(3):
        out = say(eng, "مش عارف")
    assert db.one("SELECT state FROM patients")["state"] == "awaiting_bp"


def test_implausible_value_asks_to_remeasure(eng, db, pid):
    eng.start_checkin(pid)
    out = say(eng, "5000")
    assert "غير معتاد" in out[-1] and db.one("SELECT state FROM patients")["state"] == "awaiting_glucose"


def test_unrecognised_complaint_is_forwarded_to_doctor(eng, db, pid):
    eng.start_checkin(pid)
    say(eng, "110"); say(eng, "120/80")
    say(eng, "عندي وجع بظهري من امس")
    say(eng, "اه")
    a = alerts(db)
    assert a and "وجع بظهري" in a[0]["summary_en"]


def test_missed_meds_two_days_in_a_row_flags(eng, db, pid, clock):
    for day in range(2):
        eng.start_checkin(pid)
        say(eng, "100"); say(eng, "120/80"); say(eng, "لا"); say(eng, "ما اخذت")
        clock.dt += timedelta(days=1)
    a = alerts(db)
    assert a and any(r["code"] == "missed_meds" and r["data"]["days"] == 2 for r in json.loads(a[-1]["reasons"]))


def test_opt_out(eng, db, pid):
    say(eng, "إيقاف")
    p = db.one("SELECT * FROM patients")
    assert p["active"] == 0 and p["consent"] == 0
    assert say(eng, "hi") == []                       # silent afterwards


def test_dialects_and_gender_agreement(eng, db):
    for dialect in ("levantine", "gulf", "egyptian", "maghrebi", "msa"):
        pid = make_patient(db, name="علي", phone=f"9627{abs(hash(dialect)) % 10**8:08d}", gender="m", dialect=dialect)
        eng.start_checkin(pid)
        msgs = db.all("SELECT body FROM messages WHERE patient_id=? AND direction='out'", (pid,))
        assert len(msgs) == 2 and "{" not in msgs[0]["body"] + msgs[1]["body"]


def test_duplicate_alert_within_an_hour_is_suppressed(eng, db, pid):
    for _ in range(2):
        eng.start_checkin(pid)
        say(eng, "45")
    assert len(alerts(db)) == 1


# ── scheduler ───────────────────────────────────────────────────────────────
def test_scheduler_starts_checkin_at_configured_time_once(eng, db, pid, clock):
    clock.dt = clock.dt.replace(hour=4)               # 07:00 Amman → too early
    assert scheduler.tick(eng)["checkins"] == 0
    clock.dt = clock.dt.replace(hour=5, minute=1)     # 08:01
    assert scheduler.tick(eng)["checkins"] == 1
    assert scheduler.tick(eng)["checkins"] == 0       # not twice the same day


def test_scheduler_med_reminder_and_reply(eng, db, pid, clock):
    db.execute("INSERT INTO medications(patient_id, name, times) VALUES (?,?,?)", (pid, "ميتفورمين", '["08:00"]'))
    db.execute("UPDATE patients SET checkin_time='12:00'")
    st = scheduler.tick(eng)
    assert st["reminders"] == 1
    out = say(eng, "تم")
    assert "ممتاز" in out[0]
    assert db.one("SELECT taken FROM reminder_log")["taken"] == 1
    assert scheduler.tick(eng)["reminders"] == 0


def test_scheduler_nudges_then_abandons_but_keeps_partial_data(eng, db, pid, clock):
    eng.start_checkin(pid)
    say(eng, "175")                                    # glucose captured, then silence
    clock.dt += timedelta(hours=2, minutes=5)
    assert scheduler.tick(eng)["nudges"] == 1
    clock.dt += timedelta(hours=7)
    assert scheduler.tick(eng)["abandoned"] == 1
    assert db.one("SELECT COUNT(*) c FROM readings")["c"] == 1
    assert db.one("SELECT completed FROM checkins")["completed"] == 0


def test_scheduler_urgent_followup_message(eng, db, pid, clock):
    say(eng, "عندي ضيق نفس")
    clock.dt += timedelta(minutes=31)
    assert scheduler.tick(eng)["followups"] == 1


def test_scheduler_flags_silent_patient_once(eng, db, pid, clock):
    clock.dt += timedelta(days=12)
    db.execute("UPDATE patients SET checkin_time='23:00'")
    assert scheduler.tick(eng)["silent"] == 1
    assert scheduler.tick(eng)["silent"] == 0


def test_whatsapp_24h_window_uses_template_when_outside(db, pid, clock):
    from app.conversation import Engine

    class WA:
        name = "whatsapp"
        def __init__(self): self.calls = []
        def send(self, phone, text, template=None, params=None): self.calls.append((template, text))

    ch = WA()
    e = Engine(db, ch, now_fn=clock)
    e.start_checkin(pid)                               # never messaged us → outside window
    assert ch.calls[0][0] == "rafiq_daily_checkin" and len(ch.calls) == 1
    assert db.one("SELECT state FROM patients")["state"] == "awaiting_start"
    ch.calls.clear()
    e.handle_inbound(PHONE, "ابدأ")                    # reply opens the window → first question as plain text
    assert ch.calls[0][0] is None and "السكر" in ch.calls[0][1]
