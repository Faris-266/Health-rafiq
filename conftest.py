import os, sys
from datetime import datetime, timezone
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.channels import NullChannel
from app.conversation import Engine
from app.db import DB


class Clock:
    def __init__(self, dt):
        self.dt = dt
    def __call__(self):
        return self.dt


@pytest.fixture
def clock():
    return Clock(datetime(2026, 10, 10, 5, 0, 0, tzinfo=timezone.utc))  # 08:00 Amman


@pytest.fixture
def db(tmp_path):
    d = DB(str(tmp_path / "t.db"))
    d.init()
    d.execute("INSERT INTO clinicians(name, phone, language) VALUES ('Dr Test','962790009999','en')")
    yield d
    d.close()


def make_patient(db, name="سعاد", phone="962790000111", gender="f", dialect="levantine", conditions="diabetes,hypertension", consent=1):
    return db.execute(
        "INSERT INTO patients(name, phone, gender, dialect, country, tz, conditions, clinician_id, consent, state, session, enrolled_at)"
        " VALUES (?,?,?,?,'JO','Asia/Amman',?,1,?,'idle','{}','2026-10-01T00:00:00')",
        (name, phone, gender, dialect, conditions, consent))


@pytest.fixture
def eng(db, clock):
    return Engine(db, NullChannel(), now_fn=clock)


@pytest.fixture
def pid(db):
    return make_patient(db)
