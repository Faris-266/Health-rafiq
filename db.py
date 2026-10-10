"""Tiny SQLite wrapper + schema. Swap for Postgres in production (see README)."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS clinicians (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    language TEXT NOT NULL DEFAULT 'en'
);
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    gender TEXT NOT NULL DEFAULT 'm',
    dialect TEXT NOT NULL DEFAULT 'levantine',
    country TEXT NOT NULL DEFAULT 'JO',
    tz TEXT NOT NULL DEFAULT 'Asia/Amman',
    conditions TEXT NOT NULL DEFAULT 'diabetes',
    clinician_id INTEGER REFERENCES clinicians(id),
    consent INTEGER NOT NULL DEFAULT 0,
    consent_at TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL DEFAULT 'idle',
    session TEXT NOT NULL DEFAULT '{}',
    checkin_time TEXT NOT NULL DEFAULT '08:00',
    last_prompt_date TEXT,
    last_inbound_at TEXT,
    followup_at TEXT,
    pending_reminder TEXT,
    enrolled_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    name TEXT NOT NULL,
    dose TEXT,
    times TEXT NOT NULL DEFAULT '["08:00"]'
);
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    kind TEXT NOT NULL,              -- glucose | bp
    value1 REAL NOT NULL,            -- glucose mg/dL | systolic
    value2 REAL,                     -- diastolic
    context TEXT,                    -- fasting | post_meal | random
    source TEXT NOT NULL DEFAULT 'text',
    level INTEGER NOT NULL DEFAULT 0,
    taken_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_readings_patient ON readings(patient_id, kind, taken_at);
CREATE TABLE IF NOT EXISTS checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    local_date TEXT NOT NULL,
    symptoms TEXT NOT NULL DEFAULT '[]',
    free_text TEXT,
    meds_taken INTEGER,              -- 1 / 0 / NULL(unknown)
    level INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_checkins_patient ON checkins(patient_id, created_at);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id),
    level INTEGER NOT NULL,
    reasons TEXT NOT NULL,           -- JSON list of {code, level, data}
    summary_en TEXT NOT NULL,
    summary_ar TEXT NOT NULL,
    rules_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',   -- open | ack | resolved
    notified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    ack_by TEXT,
    ack_at TEXT,
    note TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER REFERENCES patients(id),
    direction TEXT NOT NULL,         -- in | out | clinician_out
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_patient ON messages(patient_id, id);
CREATE TABLE IF NOT EXISTS processed_messages (
    wa_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminder_log (
    patient_id INTEGER NOT NULL,
    med_id INTEGER NOT NULL,
    local_date TEXT NOT NULL,
    slot TEXT NOT NULL,
    taken INTEGER,
    PRIMARY KEY (patient_id, med_id, local_date, slot)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    patient_id INTEGER,
    detail TEXT
);
"""


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


class DB:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def init(self) -> None:
        with self._lock:
            self.conn.executescript(SCHEMA)

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        with self._lock:
            cur = self.conn.execute(sql, tuple(params))
            return cur.lastrowid

    def all(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, tuple(params)).fetchall()]

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        with self._lock:
            r = self.conn.execute(sql, tuple(params)).fetchone()
            return dict(r) if r else None

    def audit(self, actor: str, action: str, patient_id: int | None = None, detail: str = "") -> None:
        self.execute(
            "INSERT INTO audit_log(ts, actor, action, patient_id, detail) VALUES (?,?,?,?,?)",
            (iso(utcnow()), actor, action, patient_id, detail),
        )

    def close(self) -> None:
        self.conn.close()


def j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
