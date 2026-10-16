"""Synthetic demo data. Every name/number is fictional. The breast-health story is produced by driving the REAL
engine (intake chats, a reported lump, a BI-RADS 4 result) with a back-dated clock, then letting the real
scheduler notice the overdue referral."""
from __future__ import annotations

import random
from datetime import timedelta

from . import auth
from . import breast_ops as ops
from . import scheduler
from .config import COUNTRY_TZ
from .conversation import Engine
from .db import DB, iso, j, utcnow
from .triage import TriageInput, evaluate

DEMO_PASSWORD = "Rafiq-demo-1"
DEMO_INVITE = "DEMOLINA"

#   name, phone, gender, dialect, country, conditions, clinician(0=Lina,1=Omar)
PATIENTS = [
    ("أم خالد", "962790000001", "f", "levantine", "JO", "breast", 0),
    ("سارة المنصوري", "966500000002", "f", "gulf", "SA", "breast", 0),
    ("Hala Nasser", "971500000003", "f", "en", "AE", "breast", 1),
    ("فاطمة الزهراء", "212600000004", "f", "maghrebi", "MA", "breast", 1),
    ("منى عادل", "201000000005", "f", "egyptian", "EG", "breast", 0),
    ("Reem Saleh", "962790000006", "f", "en", "JO", "breast", 1),
    ("حسن محمود", "201000000007", "m", "egyptian", "EG", "hypertension", 0),
    ("أبو فهد", "966500000008", "m", "gulf", "SA", "diabetes", 1),
]


def seed(db: DB, programme: str = "both") -> bool:
    """Load demo data + demo logins for the chosen programme. Returns True if it seeded."""
    if db.one("SELECT 1 FROM patients LIMIT 1"):
        return False
    return _seed_chronic(db) if programme == "chronic" else _seed_mixed(db)


#   name, phone, gender, dialect, country, conditions, clinician(0=Lina,1=Omar), glucose profile, bp profile, meds
CHRONIC = [
    ("أم خالد", "962790000001", "f", "levantine", "JO", "diabetes,hypertension", 0, "rising", "high"),
    ("أبو فهد", "966500000002", "m", "gulf", "SA", "diabetes", 1, "stable", None),
    ("حسن محمود", "201000000003", "m", "egyptian", "EG", "hypertension", 0, None, "stable"),
    ("فاطمة الزهراء", "212600000004", "f", "maghrebi", "MA", "diabetes", 1, "low", None),
    ("Hala Nasser", "971500000005", "f", "en", "AE", "diabetes,hypertension", 0, "stable", "stable"),
    ("Reem Saleh", "962790000006", "f", "en", "JO", "hypertension", 1, None, "rising"),
    ("يوسف الخطيب", "962790000007", "m", "levantine", "JO", "diabetes", 0, "silent", None),
]


def _seed_chronic(db: DB) -> bool:
    """Diabetes / hypertension demo: rising trends, a hypoglycaemia emergency, missed medication, a silent patient."""
    now = utcnow()
    rnd = random.Random(7)
    lina = db.execute("INSERT INTO clinicians(name, phone, language, invite_code) VALUES (?,?,?,?)", ("Dr. Lina Haddad", "962790009999", "en", DEMO_INVITE))
    omar = db.execute("INSERT INTO clinicians(name, phone, language, invite_code) VALUES (?,?,?,?)", ("د. عمر ناصر", "962790008888", "ar", "DEMOOMAR"))
    auth.create_user(db, "demo-admin", "Admin (demo)", "admin", DEMO_PASSWORD)
    auth.create_user(db, "demo-lina", "Dr. Lina Haddad", "clinician", DEMO_PASSWORD, clinician_id=lina)
    auth.create_user(db, "demo-omar", "د. عمر ناصر", "clinician", DEMO_PASSWORD, clinician_id=omar)
    eng = Engine(db, _Null(), now_fn=lambda: now)
    for idx, (name, phone, gender, dialect, country, conds, c, gprof, bprof) in enumerate(CHRONIC):
        pid = db.execute(
            "INSERT INTO patients(name, phone, gender, dialect, country, tz, conditions, clinician_id, consent, consent_at, state, session, last_prompt_date, birth_year, enrolled_at)"
            " VALUES (?,?,?,?,?,?,?,?,1,?, 'idle', '{}', ?, ?, ?)",
            (name, phone, gender, dialect, country, COUNTRY_TZ[country], conds, (lina, omar)[c], iso(now - timedelta(days=20)),
             now.date().isoformat(), 1950 + idx * 6, iso(now - timedelta(days=20))))
        auth.create_user(db, f"demo-patient{idx + 1}", name, "patient", DEMO_PASSWORD, patient_id=pid)
        db.execute("INSERT INTO medications(patient_id, name, dose, times) VALUES (?,?,?,?)",
                   (pid, "ميتفورمين" if "diabetes" in conds else "أملوديبين", "500mg" if "diabetes" in conds else "5mg", j(["08:00", "20:00"])))

        def gen(d: int):
            g = bp = None
            if gprof:
                base = {"rising": 105 + (14 - d) * 6 * 0.5, "stable": 108, "low": 74, "silent": 112}[gprof]
                g = round(base + rnd.uniform(-9, 12))
                if gprof == "low" and d <= 3:
                    g = rnd.choice([66, 62, 64])
            if bprof:
                base = {"high": 148 + (14 - d) // 2, "stable": 124, "rising": 116 + (14 - d) * 2.2}[bprof]
                s_ = round(base + rnd.uniform(-5, 7))
                bp = (s_, round(s_ * 0.62 + rnd.uniform(-4, 4)))
            return g, bp

        last_hist = 14 if gprof != "silent" else 6          # the silent patient stopped checking in a week ago
        for d in range(14, 0, -1):
            if d < last_hist and gprof == "silent":
                continue
            ts = now - timedelta(days=d, hours=-1)
            taken = 0 if (gprof == "low" and d <= 2) or rnd.random() < 0.06 else 1
            g, bp = gen(d)
            if g is not None:
                db.execute("INSERT INTO readings(patient_id, kind, value1, context, source, level, taken_at) VALUES (?,?,?,?,?,?,?)",
                           (pid, "glucose", g, "fasting", "text", int(evaluate(TriageInput(glucose=g)).level), iso(ts)))
            if bp is not None:
                db.execute("INSERT INTO readings(patient_id, kind, value1, value2, source, level, taken_at) VALUES (?,?,?,?,?,?,?)",
                           (pid, "bp", bp[0], bp[1], "text", int(evaluate(TriageInput(sys=bp[0], dia=bp[1])).level), iso(ts)))
            db.execute("INSERT INTO checkins(patient_id, local_date, symptoms, meds_taken, level, completed, created_at) VALUES (?,?,?,?,?,1,?)",
                       (pid, ts.date().isoformat(), "[]", taken, 0, iso(ts)))
        if gprof == "silent":
            continue
        # today's check-in goes through the real engine path (persist + triage + alert + clinician notification)
        g, bp = gen(0)
        sess = {"steps": [], "notes": [], "symptoms": [], "meds": True, "free_text": None}
        if g is not None:
            sess["glucose"] = {"mgdl": g, "context": "fasting", "source": "text"}
        if bp is not None:
            sess["bp"] = {"sys": bp[0], "dia": bp[1], "source": "text"}
        if gprof == "low":
            sess.update(symptoms=["shaking_sweating"], meds=False)
        eng._finalize(db.one("SELECT * FROM patients WHERE id=?", (pid,)), sess)
    scheduler.tick(Engine(db, _Null(), now_fn=lambda: now), now)       # the silent patient is noticed by the real scheduler
    db.audit("system", "demo_seed", None, "programme=chronic")
    return True


def _seed_mixed(db: DB) -> bool:
    now = utcnow()
    rnd = random.Random(7)
    lina = db.execute("INSERT INTO clinicians(name, phone, language, invite_code) VALUES (?,?,?,?)", ("Dr. Lina Haddad", "962790009999", "en", DEMO_INVITE))
    omar = db.execute("INSERT INTO clinicians(name, phone, language, invite_code) VALUES (?,?,?,?)", ("د. عمر ناصر", "962790008888", "ar", "DEMOOMAR"))
    auth.create_user(db, "demo-admin", "Admin (demo)", "admin", DEMO_PASSWORD)
    auth.create_user(db, "demo-lina", "Dr. Lina Haddad", "clinician", DEMO_PASSWORD, clinician_id=lina)
    auth.create_user(db, "demo-omar", "د. عمر ناصر", "clinician", DEMO_PASSWORD, clinician_id=omar)

    ids = {}
    for idx, (name, phone, gender, dialect, country, conds, c) in enumerate(PATIENTS):
        pid = db.execute(
            "INSERT INTO patients(name, phone, gender, dialect, country, tz, conditions, clinician_id, consent, consent_at, state, session, checkin_day, enrolled_at)"
            " VALUES (?,?,?,?,?,?,?,?,1,?, 'idle', '{}', 1, ?)",
            (name, phone, gender, dialect, country, COUNTRY_TZ[country], conds, (lina, omar)[c], iso(now - timedelta(days=60)), iso(now - timedelta(days=60))))
        auth.create_user(db, f"demo-patient{idx + 1}", name, "patient", DEMO_PASSWORD, patient_id=pid)
        ids[idx] = pid

    def engine_at(delta_days: float) -> Engine:
        t = now - timedelta(days=delta_days)
        return Engine(db, _Null(), now_fn=lambda: t)

    def intake(idx: int, answers: list[str], days_ago: float = 40) -> None:
        e = engine_at(days_ago)
        e.start_checkin(ids[idx], scheduled=False)
        for a in answers:
            e.handle_inbound(PATIENTS[idx][1], a)

    # ── breast-health patients ──────────────────────────────────────────────
    intake(0, ["46", "لا", "لا", "لا", "لا", "قبل 15 شهر"])                                 # average risk, mammogram overdue
    intake(1, ["1988", "لا", "لا", "لا", "لا", "لم أجرِ تصويرًا"])                           # 38, not yet eligible
    intake(2, ["52", "no", "no", "no", "no", "5 months ago"], days_ago=3)                  # up to date (English)
    intake(3, ["44", "ايوه امي وعمرها 45", "لا", "ما اعرف", "لا", "ما اذكر"], days_ago=10)   # elevated → specialist plan + alert
    intake(5, ["58", "no", "no", "no", "no", "2023"])                                      # Reem
    for idx in (1, 0, 2, 3, 5):
        db.execute("UPDATE patients SET last_breast_prompt=?, last_screening_reminder=? WHERE id=?",
                   (now.strftime("%Y-%m"), iso(now - timedelta(days=3)), ids[idx]))
    # monthly check-in history (self-checked, nothing to report)
    for idx in (0, 1, 2, 3, 5):
        for k, chk in ((3, 1), (2, 1), (1, 0)):
            ts = now - timedelta(days=30 * k)
            db.execute("INSERT INTO checkins(patient_id, local_date, symptoms, meds_taken, level, completed, kind, self_checked, created_at) VALUES (?,?,?,?,?,1,'breast',?,?)",
                       (ids[idx], ts.date().isoformat(), "[]", None, 0, chk, iso(ts)))

    # Sara reports a lump 6 days ago; nobody has contacted her → the scheduler will flag the referral
    engine_at(6).handle_inbound(PATIENTS[1][1], "لقيت كتلة في صدري")
    # Fatima's elevated-risk review is already in progress
    fr = db.one("SELECT id FROM referrals WHERE patient_id=?", (ids[3],))
    if fr:
        ops.update_referral(db, fr["id"], {"status": "contacted", "notes": "Phone consult booked to plan individual screening"}, "demo", now - timedelta(days=1))
    # Reem: screening mammogram 12 days ago came back BI-RADS 4 → urgent referral, appointment booked
    p6 = db.one("SELECT * FROM patients WHERE id=?", (ids[5],))
    ops.log_screening(db, p6, {"kind": "mammogram", "done_on": (now - timedelta(days=12)).date().isoformat(), "birads": 4, "notes": "Suspicious mass, needs biopsy"},
                      "demo-omar", now - timedelta(days=12))
    r6 = db.one("SELECT id FROM referrals WHERE patient_id=? ORDER BY id DESC LIMIT 1", (ids[5],))
    ops.update_referral(db, r6["id"], {"appointment_date": (now + timedelta(days=3)).date().isoformat(), "status": "booked"}, "demo-omar", now - timedelta(days=10))
    # Mona has only just registered: consent given, intake not started (so she is "intake pending")

    # ── two chronic-disease patients (the original pack still works alongside) ──
    for idx, (conds, gprof, bprof) in ((6, ("hypertension", None, "stable")), (7, ("diabetes", "rising", None))):
        for d in range(14, 0, -1):
            ts = now - timedelta(days=d, hours=-1)
            if gprof:
                g = round(105 + (14 - d) * 6 * 0.5 + rnd.uniform(-10, 14))
                db.execute("INSERT INTO readings(patient_id, kind, value1, context, source, level, taken_at) VALUES (?,?,?,?,?,?,?)",
                           (ids[idx], "glucose", g, "fasting", "text", int(evaluate(TriageInput(glucose=g)).level), iso(ts)))
            if bprof:
                s_ = round(124 + rnd.uniform(-6, 8)); d_ = round(s_ * 0.62 + rnd.uniform(-4, 4))
                db.execute("INSERT INTO readings(patient_id, kind, value1, value2, source, level, taken_at) VALUES (?,?,?,?,?,?,?)",
                           (ids[idx], "bp", s_, d_, "text", int(evaluate(TriageInput(sys=s_, dia=d_)).level), iso(ts)))
            db.execute("INSERT INTO checkins(patient_id, local_date, symptoms, meds_taken, level, completed, created_at) VALUES (?,?,?,?,?,1,?)",
                       (ids[idx], ts.date().isoformat(), "[]", 0 if rnd.random() < 0.08 else 1, 0, iso(ts)))
        db.execute("INSERT INTO medications(patient_id, name, dose, times) VALUES (?,?,?,?)",
                   (ids[idx], "ميتفورمين" if gprof else "أملوديبين", "500mg" if gprof else "5mg", j(["08:00", "20:00"])))
        db.execute("UPDATE patients SET last_prompt_date=? WHERE id=?", (now.date().isoformat(), ids[idx]))

    # let the real scheduler notice what has slipped (Sara's referral: nobody contacted her within 2 days)
    scheduler.tick(Engine(db, _Null(), now_fn=lambda: now), now)
    db.audit("system", "demo_seed")
    return True


class _Null:
    name = "simulator"

    def send(self, *a, **k):  # noqa: D401
        pass
