"""Authentication, sessions and role guards (stdlib only: scrypt + server-side sessions).

* Passwords: scrypt with per-user salt.
* Sessions: random 256-bit token in an HttpOnly, SameSite=Lax cookie; only its SHA-256 is stored,
  so a database leak does not leak live sessions, and sessions can be revoked server-side.
* Brute force: per-username lockout (in-memory; use Redis if you run several workers).
* Roles: admin (everything), clinician (own patients), patient (own record only).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import threading
import time
from datetime import timedelta

from fastapi import Depends, HTTPException, Request

from .config import settings
from .db import DB, iso, parse_iso, utcnow

COOKIE = "rafiq_session"
ROLES = ("admin", "clinician", "patient")
MIN_PASSWORD = 8


# ── passwords ───────────────────────────────────────────────────────────────
def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        scheme, salt, dk = stored.split("$")
        if scheme != "scrypt":
            return False
        calc = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc.hex(), dk)
    except Exception:  # noqa: BLE001
        return False


_DUMMY = hash_password("not-a-real-password")  # equalises timing for unknown usernames


def temp_password() -> str:
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no look-alike characters
    return "".join(secrets.choice(alphabet) for _ in range(12))


def check_strength(pw: str) -> None:
    if len(pw) < MIN_PASSWORD:
        raise HTTPException(422, f"Password must be at least {MIN_PASSWORD} characters")
    if pw.lower() in {"password", "12345678", "qwerty123", "11111111"}:
        raise HTTPException(422, "Password is too common")


# ── login throttling ────────────────────────────────────────────────────────
class Throttle:
    MAX_FAILS, WINDOW, LOCK = 5, 15 * 60, 5 * 60

    def __init__(self) -> None:
        self._d: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def locked(self, key: str) -> int:
        with self._lock:
            ent = self._d.get(key)
            if ent and ent[2] > time.time():
                return int(ent[2] - time.time())
        return 0

    def fail(self, key: str) -> None:
        now = time.time()
        with self._lock:
            n, first, until = self._d.get(key, [0, now, 0])
            if now - first > self.WINDOW:
                n, first = 0, now
            n += 1
            self._d[key] = [n, first, now + self.LOCK if n >= self.MAX_FAILS else 0]

    def ok(self, key: str) -> None:
        with self._lock:
            self._d.pop(key, None)


throttle = Throttle()


# ── users & sessions ────────────────────────────────────────────────────────
def create_user(db: DB, username: str, display_name: str, role: str, password: str,
                clinician_id: int | None = None, patient_id: int | None = None, must_change: bool = False) -> int:
    if role not in ROLES:
        raise ValueError("bad role")
    return db.execute(
        "INSERT INTO users(username, display_name, password_hash, role, clinician_id, patient_id, active, must_change, created_at)"
        " VALUES (?,?,?,?,?,?,1,?,?)",
        (username.strip().lower(), display_name, hash_password(password), role, clinician_id, patient_id,
         int(must_change), iso(utcnow())))


def new_session(db: DB, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    exp = utcnow() + timedelta(hours=settings().session_hours)
    db.execute("INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
               (hashlib.sha256(token.encode()).hexdigest(), user_id, iso(utcnow()), iso(exp)))
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (iso(utcnow()),))
    return token


def drop_session(db: DB, token: str) -> None:
    db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))


def drop_user_sessions(db: DB, user_id: int, keep_token: str | None = None) -> None:
    keep = hashlib.sha256(keep_token.encode()).hexdigest() if keep_token else ""
    db.execute("DELETE FROM sessions WHERE user_id=? AND token_hash<>?", (user_id, keep))


def user_from_request(request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    db: DB = request.app.state.db
    row = db.one(
        "SELECT u.*, s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
        (hashlib.sha256(token.encode()).hexdigest(),))
    if not row or not row["active"] or parse_iso(row["expires_at"]) < utcnow():
        return None
    row.pop("password_hash", None)
    row["_token"] = token
    return row


# ── dependencies ────────────────────────────────────────────────────────────
def current_user(request: Request) -> dict:
    u = user_from_request(request)
    if not u:
        raise HTTPException(401, "Not signed in")
    return u


def require(*roles: str):
    """Role guard. Users who must change their password can do nothing else until they do."""
    def dep(user: dict = Depends(current_user)) -> dict:
        if user["must_change"]:
            raise HTTPException(403, "password_change_required")
        if user["role"] not in roles:
            raise HTTPException(403, "Not allowed for your role")
        return user
    return dep


staff = require("admin", "clinician")
admin_only = require("admin")
patient_only = require("patient")


def scope(user: dict, alias: str = "p") -> tuple[str, list]:
    """SQL fragment limiting rows to patients this staff member may see."""
    if user["role"] == "admin":
        return "1=1", []
    return f"{alias}.clinician_id = ?", [user["clinician_id"] or -1]


def ensure_patient_access(db: DB, user: dict, pid: int) -> dict:
    p = db.one("SELECT * FROM patients WHERE id=?", (pid,))
    if not p:
        raise HTTPException(404, "patient not found")
    if user["role"] == "admin" or (user["role"] == "clinician" and p["clinician_id"] == user["clinician_id"]):
        return p
    if user["role"] == "patient" and user["patient_id"] == pid:
        return p
    raise HTTPException(404, "patient not found")  # 404, not 403: don't confirm that the record exists
