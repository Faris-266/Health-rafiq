"""Synthetic demo data (14 days). Every name/number here is fictional."""
from __future__ import annotations

import json
import random
from datetime import timedelta

from .config import COUNTRY_TZ
from . import auth
from .conversation import Engine
from .db import DB, iso, j, utcnow
from .triage import Level, TriageInput, evaluate

PATIENTS = [
    # name, phone, gender, dialect, country, conditions, glucose-profile, bp-profile
    ("أم خالد", "962790000001", "f", "levantine", "JO", "diabetes,hypertension", "rising", "high"),
    ("أبو فهد", "966500000002", "m", "gulf", "SA", "diabetes", "stable", None),
    ("حسن محمود", "201000000003", "m", "egyptian", "EG", "hypertension", None, "stable"),
    ("فاطمة الزهراء", "212600000004", "f", "maghrebi", "MA", "diabetes", "low", None),
    ("سعاد العلي", "971500000005", "f", "gulf", "AE", "diabetes,hypertension", "stable", "stable"),
    ("يوسف الخطيب", "962790000006", "m", "levantine", "JO", "hypertension", None, "rising"),
]


DEMO_PASSWORD = "Rafiq-demo-1"


def seed(db: DB) -> bool:
    """Load synthetic demo data + demo logins. Returns True if it seeded."""
    if db.one("SELECT 1 FROM patients LIMIT 1"):
        return False
    rnd = random.Random(7)
    now = utcnow()
    lina = db.execute("INSERT INTO clinicians(name, phone, language) VALUES (?,?,?)", ("Dr. Lina Haddad", "962790009999", "en"))
    omar = db.execute("INSERT INTO clinicians(name, phone, language) VALUES (?,?,?)", ("د. عمر ناصر", "962790008888", "ar"))
    auth.create_user(db, "demo-admin", "Admin (demo)", "admin", DEMO_PASSWORD)
    auth.create_user(db, "demo-lina", "Dr. Lina Haddad", "clinician", DEMO_PASSWORD, clinician_id=lina)
    auth.create_user(db, "demo-omar", "د. عمر ناصر", "clinician", DEMO_PASSWORD, clinician_id=omar)
    eng = Engine(db, _Null(), now_fn=lambda: now)
    for idx, (name, phone, gender, dialect, country, conds, gprof, bprof) in enumerate(PATIENTS):
        cid = lina if idx < 3 else omar
        pid = db.execute(
            "INSERT INTO patients(name, phone, gender, dialect, country, tz, conditions, clinician_id, consent, consent_at, state, session, enrolled_at)"
            " VALUES (?,?,?,?,?,?,?,?,1,?, 'idle', '{}', ?)",
            (name, phone, gender, dialect, country, COUNTRY_TZ[country], conds, cid, iso(now - timedelta(days=15)), iso(now - timedelta(days=15))))
        auth.create_user(db, f"demo-patient{idx + 1}", name, "patient", DEMO_PASSWORD, patient_id=pid)
        db.execute("INSERT INTO medications(patient_id, name, dose, times) VALUES (?,?,?,?)",
                   (pid, "ميتفورمين" if "diabetes" in conds else "أملوديبين", "500mg" if "diabetes" in conds else "5mg", j(["08:00", "20:00"])))
        def gen(d: int):
            g = bp = None
            if "diabetes" in conds:
                base = {"rising": 105 + (14 - d) * 6, "stable": 112, "low": 72}[gprof]
                g = round(base + rnd.uniform(-10, 14))
                if gprof == "low" and d <= 3:
                    g = rnd.choice([66, 62, 64])
            if "hypertension" in conds:
                base = {"high": 148 + (14 - d) // 2, "stable": 124, "rising": 118 + (14 - d) * 2}[bprof]
                s_ = round(base + rnd.uniform(-6, 8))
                bp = (s_, round(s_ * 0.62 + rnd.uniform(-4, 4)))
            return g, bp

        for d in range(14, 0, -1):                      # history
            ts = now - timedelta(days=d, hours=-1)
            taken = 0 if (name == "فاطمة الزهراء" and d in (2, 1)) or rnd.random() < 0.06 else 1
            g, bp = gen(d)
            if g is not None:
                db.execute("INSERT INTO readings(patient_id, kind, value1, context, source, level, taken_at) VALUES (?,?,?,?,?,?,?)",
                           (pid, "glucose", g, "fasting", "text", int(evaluate(TriageInput(glucose=g)).level), iso(ts)))
            if bp is not None:
                db.execute("INSERT INTO readings(patient_id, kind, value1, value2, source, level, taken_at) VALUES (?,?,?,?,?,?,?)",
                           (pid, "bp", bp[0], bp[1], "text", int(evaluate(TriageInput(sys=bp[0], dia=bp[1])).level), iso(ts)))
            db.execute("INSERT INTO checkins(patient_id, local_date, symptoms, meds_taken, level, completed, created_at) VALUES (?,?,?,?,?,1,?)",
                       (pid, ts.date().isoformat(), "[]", taken, 0, iso(ts)))

        # Today's check-in goes through the real engine path (persist + triage + alert + notify).
        g, bp = gen(0)
        sess = {"steps": [], "notes": [], "symptoms": [], "meds": True, "free_text": None}
        if g is not None:
            sess["glucose"] = {"mgdl": g, "context": "fasting", "source": "text"}
        if bp is not None:
            sess["bp"] = {"sys": bp[0], "dia": bp[1], "source": "text"}
        if name == "فاطمة الزهراء":
            sess.update(symptoms=["shaking_sweating"], meds=False)
        eng._finalize(db.one("SELECT * FROM patients WHERE id=?", (pid,)), sess)
    db.audit("system", "demo_seed")
    return True


class _Null:
    name = "simulator"
    def send(self, *a, **k):  # noqa: D401
        pass
