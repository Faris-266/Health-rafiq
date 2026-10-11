"""Tiny SQLite wrapper + schema. Swap for Postgres in production (see README)."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from decimal import Decimal
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
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,              -- admin | clinician | patient
    clinician_id INTEGER REFERENCES clinicians(id),
    patient_id INTEGER REFERENCES patients(id),
    active INTEGER NOT NULL DEFAULT 1,
    must_change INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_login TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
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


_TABLES_WITH_ID = {"clinicians", "patients", "medications", "readings", "checkins", "alerts",
                   "messages", "audit_log", "users"}
_INSERT = re.compile(r"^\s*INSERT\s+INTO\s+(\w+)", re.I)


def _clean(row: dict) -> dict:
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()}


class DB:
    """Thin wrapper over SQLite (default) or PostgreSQL (DATABASE_URL=postgresql://...).

    The application writes SQL once with `?` placeholders; this class translates for Postgres.
    One shared connection guarded by a lock is plenty for a single clinic; use a pool beyond that.
    """

    def __init__(self, target: str):
        self.target = target
        self.kind = "pg" if target.startswith(("postgres://", "postgresql://")) else "sqlite"
        self._lock = threading.RLock()
        self._connect()

    def _connect(self) -> None:
        if self.kind == "pg":
            import psycopg
            from psycopg.rows import dict_row
            self.conn = psycopg.connect(self.target, autocommit=True, row_factory=dict_row)
        else:
            self.conn = sqlite3.connect(self.target, check_same_thread=False, isolation_level=None)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")

    # kept for backwards compatibility with older code/tests
    @property
    def path(self) -> str:
        return self.target

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.kind == "pg" else sql

    def _run(self, sql: str, params: Iterable[Any]):
        sql = self._sql(sql)
        for attempt in (0, 1):
            try:
                cur = self.conn.cursor() if self.kind == "pg" else self.conn
                return cur.execute(sql, tuple(params))
            except Exception as exc:  # reconnect once if the Postgres connection was dropped
                if self.kind == "pg" and attempt == 0 and exc.__class__.__name__ in ("OperationalError", "InterfaceError"):
                    self._connect()
                    continue
                raise

    def init(self) -> None:
        with self._lock:
            if self.kind == "sqlite":
                self.conn.executescript(SCHEMA)
            else:
                ddl = SCHEMA.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY").replace(" REAL", " DOUBLE PRECISION")
                for stmt in ddl.split(";"):
                    if stmt.strip():
                        self.conn.execute(stmt)

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        """Run a statement. For INSERTs into tables with an `id`, returns the new id."""
        with self._lock:
            m = _INSERT.match(sql)
            if self.kind == "pg" and m and m.group(1).lower() in _TABLES_WITH_ID:
                cur = self._run(sql.rstrip().rstrip(";") + " RETURNING id", params)
                return cur.fetchone()["id"]
            cur = self._run(sql, params)
            return cur.lastrowid if self.kind == "sqlite" else 0

    def all(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self._lock:
            return [_clean(dict(r)) for r in self._run(sql, params).fetchall()]

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        with self._lock:
            r = self._run(sql, params).fetchone()
            return _clean(dict(r)) if r else None

    def audit(self, actor: str, action: str, patient_id: int | None = None, detail: str = "") -> None:
        self.execute(
            "INSERT INTO audit_log(ts, actor, action, patient_id, detail) VALUES (?,?,?,?,?)",
            (iso(utcnow()), actor, action, patient_id, detail),
        )

    def close(self) -> None:
        self.conn.close()


def j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)
