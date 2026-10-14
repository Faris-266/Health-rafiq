"""Command-line admin tasks.

  python -m app.manage create-user --username faris --name "Faris" --role admin
  python -m app.manage reset-password --username faris
  python -m app.manage list-users
Uses DATABASE_URL (PostgreSQL) or RAFIQ_DB (SQLite file), like the server.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from . import auth
from .config import settings
from .db import DB


def main() -> int:
    ap = argparse.ArgumentParser(prog="app.manage")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-user")
    c.add_argument("--username", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--role", required=True, choices=auth.ROLES)
    c.add_argument("--clinician-id", type=int)
    c.add_argument("--patient-id", type=int)
    r = sub.add_parser("reset-password")
    r.add_argument("--username", required=True)
    sub.add_parser("list-users")
    a = ap.parse_args()

    db = DB(settings().db_target)
    db.init()
    if a.cmd == "list-users":
        for u in db.all("SELECT username, role, active FROM users ORDER BY role, username"):
            print(f"{u['username']:24} {u['role']:10} {'active' if u['active'] else 'DISABLED'}")
        return 0
    pw = getpass.getpass("Password (min 8 chars): ")
    if pw != getpass.getpass("Repeat: "):
        print("Passwords do not match", file=sys.stderr)
        return 1
    try:
        auth.check_strength(pw)
    except Exception as exc:  # noqa: BLE001
        print(getattr(exc, "detail", exc), file=sys.stderr)
        return 1
    if a.cmd == "create-user":
        auth.create_user(db, a.username, a.name, a.role, pw, a.clinician_id, a.patient_id)
        print(f"Created {a.role} '{a.username.lower()}'")
    else:
        n = db.one("SELECT id FROM users WHERE username=?", (a.username.lower(),))
        if not n:
            print("No such user", file=sys.stderr)
            return 1
        db.execute("UPDATE users SET password_hash=?, must_change=0 WHERE id=?", (auth.hash_password(pw), n["id"]))
        auth.drop_user_sessions(db, n["id"])
        print("Password updated; existing sessions signed out")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
