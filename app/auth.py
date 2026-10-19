import re
import secrets
import time

import bcrypt
from fastapi import Cookie, HTTPException

from . import config, db

USER_COOKIE = "ff_session"
MOD_COOKIE = "ff_mod"


def hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt(rounds=10)).decode()


def check_pin(pin: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode(), hashed.encode())
    except ValueError:
        return False


def normalize_phone(raw: str):
    """'90 123 45 67', '+998901234567', '998901234567' -> '+998901234567'."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) == 12 and digits.startswith("998"):
        return "+" + digits
    return None


def mask_phone(phone: str) -> str:
    # +998901234567 -> +998 90 *** ** 67
    return f"+998 {phone[4:6]} *** ** {phone[-2:]}"


def new_session(con, kind: str, subject: str) -> str:
    token = secrets.token_urlsafe(32)
    exp = db.iso_from_ms(db.now_ms() + config.SESSION_HOURS * 3600 * 1000)
    con.execute(
        "INSERT INTO sessions(token,kind,subject,expires_at) VALUES(?,?,?,?)",
        (token, kind, subject, exp),
    )
    return token


def _session(con, token, kind):
    if not token:
        return None
    row = con.execute(
        "SELECT subject FROM sessions WHERE token=? AND kind=? AND expires_at>?",
        (token, kind, db.now_iso()),
    ).fetchone()
    return row["subject"] if row else None


def current_user(con, token):
    sub = _session(con, token, "user")
    if sub is None:
        return None
    return con.execute("SELECT * FROM users WHERE id=?", (int(sub),)).fetchone()


def current_mod(con, token):
    return _session(con, token, "mod")


def require_mod(ff_mod: str | None = Cookie(default=None)) -> str:
    with db.tx() as con:
        mod = current_mod(con, ff_mod)
    if not mod:
        raise HTTPException(401, "Moderator sifatida kiring")
    return mod


# --- urinishlar limiti ---
def too_many(con, key: str, limit: int, window: int) -> bool:
    cutoff = time.time() - window
    con.execute("DELETE FROM attempts WHERE ts<?", (time.time() - 3600,))
    n = con.execute(
        "SELECT COUNT(*) c FROM attempts WHERE key=? AND ts>?", (key, cutoff)
    ).fetchone()["c"]
    return n >= limit


def record_fail(con, key: str):
    con.execute("INSERT INTO attempts(key,ts) VALUES(?,?)", (key, time.time()))


def clear_fails(con, key: str):
    con.execute("DELETE FROM attempts WHERE key=?", (key,))
