"""Breast-health early-detection flow: intake, screening schedule, concern triage, referral tracking."""
import json
from datetime import date, timedelta

import pytest

from app import breast_ops as ops
from app import scheduler
from app.triage import Level
from tests.conftest import make_patient

PHONE = "962790000111"


def say(eng, text, phone=PHONE):
    return eng.handle_inbound(phone, text)


@pytest.fixture
def bp(db, eng):
    """A consented, breast-programme patient (Levantine, female) who has NOT done intake yet."""
    return make_patient(db, name="سلمى", phone=PHONE, gender="f", dialect="levantine", conditions="breast")


def patient(db):
    return db.one("SELECT * FROM patients WHERE phone=?", (PHONE,))


def alerts(db):
    return db.all("SELECT * FROM alerts ORDER BY id")


def refs(db):
    return db.all("SELECT * FROM referrals ORDER BY id")


def do_intake(eng, age="46", family="لا", atypia="لا", gene="لا", rad="لا", mammo="ايلول 2025"):
    eng.start_checkin(eng.find_by_phone(PHONE)["id"], scheduled=False)
    for ans in (age, family, atypia, gene, rad, mammo):
        out = say(eng, ans)
    return out


# ── intake ──────────────────────────────────────────────────────────────────
def test_intake_computes_risk_and_screening_status(eng, db, bp):
    out = do_intake(eng)
    p = patient(db)
    assert p["intake_done"] == 1 and p["risk_category"] == "average" and p["birth_year"] == 1980
    assert p["last_mammogram"] == "2025-09-15" and p["screening_status"] == "due"        # 12-month interval just passed
    assert "حان موعد" in out[-1] and not alerts(db)


def test_intake_questions_are_gendered_and_in_order(eng, db, bp):
    eng.start_checkin(bp, scheduled=False)
    msgs = [m["body"] for m in db.all("SELECT body FROM messages WHERE direction='out' ORDER BY id")]
    assert "عمرك" in msgs[-1] and "اكتبي" in msgs[-1]                      # feminine imperative
    assert "سنة ميلادك" in msgs[-1]


def test_elevated_risk_gets_specialist_plan_alert_and_routine_referral(eng, db, bp):
    out = do_intake(eng, family="ايوه امي وعمرها 45")
    p = patient(db)
    assert p["risk_category"] == "elevated" and p["screening_status"] == "specialist_plan"
    a = alerts(db)
    assert len(a) == 1 and a[0]["level"] == Level.WATCH and "elevated" in a[0]["summary_en"].lower()
    r = refs(db)
    assert len(r) == 1 and r[0]["priority"] == "routine" and "elevated_risk_review" in r[0]["reason"]
    assert "خطة فحص" in out[-1]


def test_unknown_answers_do_not_elevate_risk(eng, db, bp):
    do_intake(eng, family="ما اعرف", atypia="مش عارفة", gene="لا اعرف", rad="لا", mammo="ما اذكر")
    p = patient(db)
    assert p["risk_category"] == "average" and p["last_mammogram"] is None and p["screening_status"] == "due"


def test_young_patient_is_not_yet_eligible_for_mammograms(eng, db, bp):
    out = do_intake(eng, age="1996", mammo="لم اجر")
    assert patient(db)["screening_status"] == "not_yet" and "شهريًا" in out[-1]


def test_minors_are_declined(eng, db, bp):
    eng.start_checkin(bp, scheduled=False)
    out = say(eng, "16")
    assert "18" in out[-1] and not patient(db)["intake_done"] and patient(db)["state"] == "idle"


def test_long_overdue_screening_is_flagged_overdue(eng, db, bp):
    out = do_intake(eng, mammo="March 2024")
    assert patient(db)["screening_status"] == "overdue" and "تأخر" in out[-1]


def test_never_screened_and_recent_screening(eng, db, bp):
    do_intake(eng, age="50", mammo="never")
    assert patient(db)["screening_status"] == "due"
    db.execute("UPDATE patients SET intake_done=0")
    do_intake(eng, age="50", mammo="قبل 3 شهور")
    assert patient(db)["screening_status"] == "up_to_date"


def test_english_patient_gets_english_intake(db, eng):
    pid = make_patient(db, name="Hala", phone="971500000001", gender="f", dialect="en", conditions="breast")
    eng.start_checkin(pid, scheduled=False)
    out = [m["body"] for m in db.all("SELECT body FROM messages WHERE patient_id=? AND direction='out'", (pid,))]
    assert "How old are you" in out[-1] and not any("؟" in m for m in out)
    for a in ("44", "no", "no", "no", "no", "March 2025"):
        res = eng.handle_inbound("971500000001", a)
    assert "Thank you" in res[-1] and db.one("SELECT risk_category FROM patients WHERE id=?", (pid,))["risk_category"] == "average"


# ── concern triage ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,code", [
    ("لقيت كتلة في صدري", "breast_lump"), ("في إفرازات من الحلمة", "nipple_discharge"), ("حلمتي غاطسة", "nipple_retraction"),
    ("جلد الثدي متجعد", "breast_skin_change"), ("كتلة تحت إبطي", "axillary_lump"), ("I found a lump in my breast", "breast_lump"),
    ("تغير حجم الثدي", "breast_shape_change"),
])
def test_any_breast_change_is_urgent_referral_in_any_state(eng, db, bp, text, code):
    out = say(eng, text)                       # patient is idle AND has not finished intake
    a = alerts(db)
    assert a[0]["level"] == Level.URGENT and a[0]["notified"] == 1
    assert code in a[0]["reasons"] or code in refs(db)[0]["reason"]
    r = refs(db)[0]
    assert r["priority"] == "urgent" and r["status"] == "new"
    assert "معظم تغيرات الثدي ليست سرطانًا" in out[-1] and "يومين" not in out[-1] and "2" in out[-1]


def test_concern_works_even_before_consent(eng, db, bp):
    db.execute("UPDATE patients SET consent=0")
    out = say(eng, "عندي كتلة في الثدي")
    assert alerts(db)[0]["level"] == Level.URGENT and out


def test_concern_interrupts_monthly_checkin_and_keeps_self_check_answer(eng, db, bp):
    do_intake(eng)
    eng.start_checkin(bp, scheduled=False)
    say(eng, "نعم")                              # checked: yes
    say(eng, "لقيت كتلة في صدري")
    ck = db.one("SELECT * FROM checkins WHERE kind='breast' ORDER BY id DESC LIMIT 1")
    assert ck["self_checked"] == 1 and "breast_lump" in ck["symptoms"] and patient(db)["state"] == "idle"


def test_negated_symptoms_do_not_raise_alert(eng, db, bp):
    do_intake(eng)
    eng.start_checkin(bp, scheduled=False)
    say(eng, "ايوه"); out = say(eng, "ما في كتلة ولا إفرازات")
    assert not alerts(db) and not refs(db)


def test_normal_monthly_checkin_never_gives_false_reassurance(eng, db, bp):
    do_intake(eng)
    eng.start_checkin(bp, scheduled=False)
    say(eng, "نعم"); out = say(eng, "لا")
    assert "لا يغني عن الفحص الدوري" in out[-1] and "حان موعد" in out[-1]        # reminder: screening is due
    assert not alerts(db)


def test_monthly_no_selfcheck_teaches_how(eng, db, bp):
    do_intake(eng)
    eng.start_checkin(bp, scheduled=False)
    out = say(eng, "لا")
    assert any("المرآة" in m for m in out)


def test_yes_then_detail_flow(eng, db, bp):
    do_intake(eng)
    eng.start_checkin(bp, scheduled=False)
    say(eng, "نعم"); out = say(eng, "نعم")
    assert "وصف التغيير" in out[-1]
    say(eng, "حاسة بشي غريب بالجهة اليمين")
    r = refs(db)
    assert r and r[0]["priority"] == "routine"                    # unclassified text goes to the clinician, never dropped
    assert "شي غريب" in alerts(db)[0]["summary_en"]


def test_isolated_breast_pain_is_watch_not_urgent(eng, db, bp):
    out = say(eng, "عندي وجع في الثدي")
    assert alerts(db)[0]["level"] == Level.WATCH and refs(db)[0]["priority"] == "routine"
    assert alerts(db)[0]["notified"] == 0


def test_red_inflamed_breast_with_fever_is_same_day(eng, db, bp):
    out = say(eng, "عندي حرارة واحمرار بالثدي")
    assert "اليوم نفسه" in out[-1] and alerts(db)[0]["level"] == Level.URGENT


def test_chest_pain_is_still_a_cardiac_red_flag_not_a_breast_issue(eng, db, bp):
    out = say(eng, "وجع بصدري")
    assert "911" in out[-1] and not refs(db)


def test_elevated_risk_marks_the_alert(eng, db, bp):
    do_intake(eng, family="نعم")
    say(eng, "عندي وجع في الثدي")
    assert any(a["level"] == Level.WATCH and "ELEVATED" in a["summary_en"] for a in alerts(db))


def test_english_concern_reply(db, eng):
    pid = make_patient(db, name="Hala", phone="971500000001", gender="f", dialect="en", conditions="breast")
    out = eng.handle_inbound("971500000001", "I found a lump in my left breast")
    assert "Most breast changes are not cancer" in out[-1] and "working days" in out[-1]


# ── referrals ───────────────────────────────────────────────────────────────
def test_repeat_reports_share_one_referral_and_pain_upgrades_to_urgent(eng, db, bp, clock):
    say(eng, "عندي وجع في الثدي")
    assert refs(db)[0]["priority"] == "routine"
    clock.dt += timedelta(hours=3)
    say(eng, "لقيت كتلة في صدري")
    r = refs(db)
    assert len(r) == 1 and r[0]["priority"] == "urgent" and "breast_lump" in r[0]["reason"]


def test_referral_dates_follow_policy(eng, db, bp):
    say(eng, "لقيت كتلة في صدري")
    r = refs(db)[0]
    assert r["contact_by"] == "2026-10-12" and r["visit_by"] == "2026-10-24"       # +2 and +14 days from 2026-10-10


def test_update_referral_lifecycle_and_validation(eng, db, bp, clock):
    say(eng, "لقيت كتلة في صدري")
    rid = refs(db)[0]["id"]
    now = clock.dt
    r = ops.update_referral(db, rid, {"status": "contacted"}, "dr", now); assert r["status"] == "contacted"
    r = ops.update_referral(db, rid, {"appointment_date": "2026-10-15"}, "dr", now); assert r["status"] == "booked"
    with pytest.raises(ValueError):
        ops.update_referral(db, rid, {"status": "closed"}, "dr", now)               # outcome required to close
    with pytest.raises(ValueError):
        ops.update_referral(db, rid, {"status": "nonsense"}, "dr", now)
    r = ops.update_referral(db, rid, {"status": "closed", "outcome": "benign"}, "dr", now)
    assert r["closed_at"] and r["outcome"] == "benign"


def test_scheduler_chases_patient_then_alerts_staff_when_contact_and_visit_are_overdue(eng, db, bp, clock):
    say(eng, "لقيت كتلة في صدري")
    rid = refs(db)[0]["id"]
    db.execute("UPDATE patients SET checkin_time='23:00'")
    clock.dt += timedelta(days=1)
    st = scheduler.tick(eng); assert st["referral_chases"] == 0 and st["referral_alerts"] == 0
    clock.dt += timedelta(days=2, hours=1)                                          # day 3: past contact_by, chase due
    st = scheduler.tick(eng)
    assert st["referral_chases"] == 1 and st["referral_alerts"] == 1
    assert any("not yet contacted" in a["summary_en"] for a in alerts(db))
    assert scheduler.tick(eng)["referral_alerts"] == 0                              # no duplicate alerts
    out = say(eng, "لا")                                                            # "have you got an appointment?" → no
    assert "العيادة الاتصال" in out[-1]
    assert any("NOT got an appointment" in a["summary_en"] for a in alerts(db))
    clock.dt += timedelta(days=13)                                                  # past visit_by
    st = scheduler.tick(eng)
    assert any(a["level"] == Level.URGENT and "OVERDUE" in a["summary_en"] for a in alerts(db))


def test_patient_confirming_booking_updates_referral(eng, db, bp, clock):
    say(eng, "لقيت كتلة في صدري")
    db.execute("UPDATE patients SET checkin_time='23:00'")
    clock.dt += timedelta(days=3, hours=1)
    scheduler.tick(eng)
    say(eng, "ايوه")
    assert refs(db)[0]["status"] == "booked"


def test_seen_referral_resolves_overdue_alerts_and_stops_chasing(eng, db, bp, clock):
    say(eng, "لقيت كتلة في صدري")
    db.execute("UPDATE patients SET checkin_time='23:00'")
    clock.dt += timedelta(days=20)
    scheduler.tick(eng)
    assert any(a["status"] == "open" and "OVERDUE" in a["summary_en"] for a in alerts(db))
    ops.update_referral(db, refs(db)[0]["id"], {"status": "seen"}, "dr", clock.dt)
    assert not any(a["status"] == "open" and ("OVERDUE" in a["summary_en"] or "not yet contacted" in a["summary_en"]) for a in alerts(db))
    assert scheduler.tick(eng)["referral_alerts"] == 0


def test_booked_appointment_in_time_is_not_overdue(eng, db, bp, clock):
    say(eng, "لقيت كتلة في صدري")
    db.execute("UPDATE patients SET checkin_time='23:00'")
    ops.update_referral(db, refs(db)[0]["id"], {"appointment_date": "2026-10-22"}, "dr", clock.dt)
    clock.dt += timedelta(days=15)                                                  # past visit_by, but appointment is in 7 days ± window
    clock.dt = clock.dt.replace(year=2026, month=10, day=21)
    assert scheduler.tick(eng)["referral_alerts"] == 0


def test_booked_appointment_that_passed_without_outcome_alerts(eng, db, bp, clock):
    say(eng, "لقيت كتلة في صدري")
    db.execute("UPDATE patients SET checkin_time='23:00'")
    ops.update_referral(db, refs(db)[0]["id"], {"appointment_date": "2026-10-12"}, "dr", clock.dt)
    clock.dt += timedelta(days=4)
    scheduler.tick(eng)
    assert any("OVERDUE" in a["summary_en"] for a in alerts(db))


# ── screening log & reminders ───────────────────────────────────────────────
def test_log_normal_mammogram_resets_schedule(eng, db, bp, clock):
    do_intake(eng)
    out = ops.log_screening(db, patient(db), {"kind": "mammogram", "done_on": "2026-10-01", "birads": 2}, "dr", clock.dt)
    p = patient(db)
    assert p["last_mammogram"] == "2026-10-01" and p["next_screening_due"] == "2027-10-01" and p["screening_status"] == "up_to_date"
    assert out["referral_id"] is None


@pytest.mark.parametrize("birads,prio", [(0, "urgent"), (4, "urgent"), (5, "urgent")])
def test_suspicious_birads_creates_urgent_referral(eng, db, bp, clock, birads, prio):
    do_intake(eng)
    out = ops.log_screening(db, patient(db), {"kind": "mammogram", "done_on": "2026-10-05", "birads": birads}, "dr", clock.dt)
    assert refs(db)[-1]["priority"] == prio and out["referral_id"] and out["status"] == "referred"


def test_birads_3_schedules_six_month_recheck(eng, db, bp, clock):
    do_intake(eng)
    ops.log_screening(db, patient(db), {"kind": "mammogram", "done_on": "2026-10-05", "birads": 3}, "dr", clock.dt)
    assert patient(db)["next_screening_due"] == "2027-04-05"


def test_log_screening_validation(eng, db, bp, clock):
    for bad in ({"kind": "xray", "done_on": "2026-10-01"}, {"kind": "mammogram", "done_on": "2027-01-01"}, {"kind": "mammogram", "done_on": "2026-10-01", "birads": 9}):
        with pytest.raises(ValueError):
            ops.log_screening(db, patient(db), bad, "dr", clock.dt)


def test_staff_sets_individual_plan_for_elevated_risk(eng, db, bp, clock):
    do_intake(eng, family="نعم")
    assert patient(db)["screening_status"] == "specialist_plan"
    db.execute("UPDATE patients SET next_screening_due='2026-11-05'")
    assert ops.refresh_screening(db, patient(db), date(2026, 10, 11)) == "due_soon"


def test_scheduler_sends_screening_reminder_once_and_handles_reply(eng, db, bp, clock):
    do_intake(eng)                                                                  # status: due
    db.execute("UPDATE patients SET checkin_time='23:30', last_breast_prompt='2026-10'")
    clock.dt = clock.dt.replace(hour=7)                                             # 10:00 Amman
    assert scheduler.tick(eng)["screening_reminders"] == 1
    assert scheduler.tick(eng)["screening_reminders"] == 0
    out = say(eng, "ايوه")
    assert "ممتاز" in out[0] and patient(db)["screening_booked_at"]
    clock.dt += timedelta(days=31)
    assert scheduler.tick(eng)["screening_reminders"] == 0                          # quiet period after booking
    clock.dt += timedelta(days=20)
    assert scheduler.tick(eng)["screening_reminders"] == 1


def test_monthly_checkin_is_sent_once_per_month(eng, db, bp, clock):
    do_intake(eng)
    db.execute("UPDATE patients SET last_breast_prompt=NULL, checkin_day=1")
    assert scheduler.tick(eng)["monthly"] == 1
    assert scheduler.tick(eng)["monthly"] == 0
    say(eng, "نعم"); say(eng, "لا")
    clock.dt += timedelta(days=31)
    assert scheduler.tick(eng)["monthly"] == 1


def test_abandoned_breast_session_with_free_text_is_still_forwarded(eng, db, bp, clock):
    do_intake(eng)
    eng.start_checkin(bp, scheduled=False)
    say(eng, "نعم"); say(eng, "نعم")                                               # → asked for details… then silence
    clock.dt += timedelta(hours=9)
    scheduler.tick(eng)
    assert patient(db)["state"] == "idle"


def test_urgent_alert_with_no_clinician_falls_back_and_is_audited(eng, db, monkeypatch):
    pid = make_patient(db, name="سارة", phone="962790000222", gender="f", conditions="breast")
    db.execute("UPDATE patients SET clinician_id=NULL WHERE id=?", (pid,))
    eng.handle_inbound("962790000222", "لقيت كتلة في صدري")
    assert db.one("SELECT 1 FROM audit_log WHERE action='alert_not_delivered'")
    monkeypatch.setenv("RAFIQ_ONCALL_PHONE", "962700000000")
    eng.handle_inbound("962790000222", "في إفرازات من الحلمة")
    assert any(m["direction"] == "clinician_out" for m in db.all("SELECT * FROM messages"))


def test_coverage_kpis(eng, db, bp):
    do_intake(eng, mammo="قبل 3 شهور")
    k = ops.coverage(db, "1=1", [])
    assert k["eligible"] == 1 and k["up_to_date"] == 1 and k["coverage_pct"] == 100


def test_open_suspicious_referral_puts_patient_in_referred_status_not_up_to_date(eng, db, bp, clock):
    do_intake(eng)
    ops.log_screening(db, patient(db), {"kind": "mammogram", "done_on": "2026-10-05", "birads": 4}, "dr", clock.dt)
    assert patient(db)["screening_status"] == "referred"
    rid = refs(db)[-1]["id"]
    ops.update_referral(db, rid, {"status": "closed", "outcome": "further_tests"}, "dr", clock.dt)
    p = patient(db)
    assert p["risk_category"] == "elevated" and p["screening_status"] == "specialist_plan"     # clinician-led plan from here on


def test_benign_outcome_returns_to_routine_schedule(eng, db, bp, clock):
    do_intake(eng)
    ops.log_screening(db, patient(db), {"kind": "mammogram", "done_on": "2026-10-05", "birads": 4}, "dr", clock.dt)
    ops.update_referral(db, refs(db)[-1]["id"], {"status": "closed", "outcome": "benign"}, "dr", clock.dt)
    assert patient(db)["screening_status"] == "up_to_date"
