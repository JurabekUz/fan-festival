import re
import secrets
import sqlite3

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, field_validator

from . import auth, config, db, live

router = APIRouter(prefix="/api")


def _set_cookie(resp: Response, name: str, token: str):
    resp.set_cookie(name, token, httponly=True, samesite="lax",
                    secure=config.COOKIE_SECURE, max_age=config.SESSION_HOURS * 3600)


def _pin(v: str) -> str:
    if not re.fullmatch(r"\d{4}", v or ""):
        raise ValueError("PIN 4 ta raqamdan iborat bo'lishi kerak")
    return v


class RegisterIn(BaseModel):
    first_name: str
    last_name: str
    phone: str
    pin: str
    visitor_type_id: int

    _p = field_validator("pin")(_pin)

    @field_validator("first_name", "last_name")
    @classmethod
    def _name(cls, v):
        v = " ".join(v.split())
        if not (1 <= len(v) <= 60):
            raise ValueError("Ism/familiya 1–60 belgi bo'lsin")
        return v


class LoginIn(BaseModel):
    phone: str
    pin: str

    _p = field_validator("pin")(_pin)


def check_type(con, tid):
    """Faqat faol tur tanlanishi mumkin (eski foydalanuvchilarda bazada NULL bo'lishi mumkin)."""
    if not con.execute(
            "SELECT 1 FROM visitor_types WHERE id=? AND active=1", (tid,)).fetchone():
        raise HTTPException(422, "Bunday tashrif buyuruvchi turi yo'q")
    return tid


class CheckinIn(BaseModel):
    zone: int
    code: str


def user_view(con, u):
    stamps = [r["zone_id"] for r in con.execute(
        "SELECT zone_id FROM checkins WHERE user_id=? ORDER BY zone_id", (u["id"],))]
    wins = [dict(r) for r in con.execute(
        """SELECT r.id round_id, r.created_at, r.prize FROM draw_entries e
           JOIN draw_rounds r ON r.id=e.round_id
           WHERE e.user_id=? AND e.won=1 AND r.cancelled=0
             AND COALESCE(r.visible_at,r.created_at)<=? ORDER BY r.id""", (u["id"], db.now_iso()))]
    plays = con.execute(
        """SELECT COUNT(*) c FROM draw_entries e JOIN draw_rounds r ON r.id=e.round_id
           WHERE e.user_id=? AND r.cancelled=0""", (u["id"],)).fetchone()["c"]
    return {
        "first_name": u["first_name"], "last_name": u["last_name"],
        "phone": u["phone"], "passport_no": u["passport_no"],
        "stamps": stamps, "wins": wins, "plays": plays,
        "visitor_type_id": u["visitor_type_id"],
    }


@router.post("/register")
def register(body: RegisterIn, resp: Response):
    phone = auth.normalize_phone(body.phone)
    if not phone:
        raise HTTPException(422, "Telefon raqami noto'g'ri. Masalan: 90 123 45 67")
    pin_hash = auth.hash_pin(body.pin)
    with db.tx() as con:
        check_type(con, body.visitor_type_id)
        try:
            cur = con.execute(
                "INSERT INTO users(first_name,last_name,phone,pin_hash,created_at,visitor_type_id) VALUES(?,?,?,?,?,?)",
                (body.first_name, body.last_name, phone, pin_hash, db.now_iso(), body.visitor_type_id))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Bu raqam allaqachon ro'yxatdan o'tgan. «Kirish» ni bosing.")
        uid = cur.lastrowid
        con.execute("UPDATE users SET passport_no=? WHERE id=?", (f"F26-{uid:04d}", uid))
        token = auth.new_session(con, "user", str(uid))
        u = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        data = user_view(con, u)
    _set_cookie(resp, auth.USER_COOKIE, token)
    return data


@router.post("/login")
def login(body: LoginIn, resp: Response, request: Request):
    phone = auth.normalize_phone(body.phone)
    if not phone:
        raise HTTPException(422, "Telefon raqami noto'g'ri")
    key = "login:" + phone
    ip_key = "loginip:" + (request.client.host if request.client else "?")
    with db.tx() as con:
        if (auth.too_many(con, key, config.LOGIN_MAX_FAILS, config.LOGIN_WINDOW_SEC) or
                auth.too_many(con, ip_key, config.LOGIN_IP_MAX_FAILS, config.LOGIN_WINDOW_SEC)):
            raise HTTPException(429, "Juda ko'p xato urinish. 10 daqiqadan keyin urinib ko'ring yoki moderatorga murojaat qiling.")
        u = con.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
        if not u or not auth.check_pin(body.pin, u["pin_hash"]):
            auth.record_fail(con, key)
            auth.record_fail(con, ip_key)
            con.commit()
            raise HTTPException(401, "Telefon yoki PIN noto'g'ri")
        if u["blocked"]:
            raise HTTPException(403, "Hisob bloklangan. Moderatorga murojaat qiling.")
        auth.clear_fails(con, key)
        token = auth.new_session(con, "user", str(u["id"]))
        data = user_view(con, u)
    _set_cookie(resp, auth.USER_COOKIE, token)
    return data


@router.post("/logout")
def logout(resp: Response, ff_session: str | None = Cookie(default=None)):
    if ff_session:
        with db.tx() as con:
            con.execute("DELETE FROM sessions WHERE token=?", (ff_session,))
    resp.delete_cookie(auth.USER_COOKIE)
    return {"ok": True}


def _need_user(con, token):
    u = auth.current_user(con, token)
    if not u or u["blocked"]:
        raise HTTPException(401, "Kiring yoki ro'yxatdan o'ting")
    return u


@router.get("/me")
def me(ff_session: str | None = Cookie(default=None)):
    with db.tx() as con:
        u = _need_user(con, ff_session)
        return user_view(con, u)


@router.get("/visitor-types")
def visitor_types():
    with db.tx() as con:
        return {"types": [dict(r) for r in con.execute(
            "SELECT id,name FROM visitor_types WHERE active=1 ORDER BY sort,id")]}


@router.post("/checkin")
def checkin(body: CheckinIn, ff_session: str | None = Cookie(default=None)):
    if body.zone not in config.ZONE_CODES:
        raise HTTPException(422, "Bunday maydon yo'q")
    with db.tx() as con:
        u = _need_user(con, ff_session)
        key = f"code:{u['id']}"
        if auth.too_many(con, key, config.CODE_MAX_FAILS, config.CODE_WINDOW_SEC):
            raise HTTPException(429, "Ko'p xato urinish. Bir daqiqa kuting.")
        if not secrets.compare_digest(body.code.strip(), config.ZONE_CODES[body.zone]):
            auth.record_fail(con, key)
            con.commit()
            raise HTTPException(400, "Kod noto'g'ri. Maydon volontyoridan kodni so'rang.")
        con.execute("INSERT OR IGNORE INTO checkins(user_id,zone_id,created_at) VALUES(?,?,?)",
                    (u["id"], body.zone, db.now_iso()))
        return user_view(con, u)


def _public_name(first, last):
    return f"{first} {last[:1]}." if last else first


@router.get("/winners")
def winners():
    with db.tx() as con:
        rounds = con.execute(
            """SELECT id,created_at,prize,note FROM draw_rounds WHERE cancelled=0
               AND COALESCE(visible_at,created_at)<=? ORDER BY id DESC LIMIT 30""", (db.now_iso(),)
        ).fetchall()
        out = []
        for r in rounds:
            ws = con.execute(
                """SELECT u.first_name,u.last_name,u.phone,u.passport_no FROM draw_entries e
                   JOIN users u ON u.id=e.user_id WHERE e.round_id=? AND e.won=1 ORDER BY u.id""",
                (r["id"],)).fetchall()
            out.append({
                "id": r["id"], "created_at": r["created_at"], "prize": r["prize"], "note": r["note"],
                "winners": [{"name": _public_name(w["first_name"], w["last_name"]),
                             "passport_no": w["passport_no"], "phone": auth.mask_phone(w["phone"])}
                            for w in ws],
            })
        eligible = con.execute(
            """SELECT COUNT(*) c FROM users u WHERE blocked=0 AND
               (SELECT COUNT(*) FROM checkins c WHERE c.user_id=u.id)>=?""",
            (config.ZONE_COUNT,)).fetchone()["c"]
    return {"rounds": out, "eligible": eligible}


@router.get("/live/roster")
def live_roster():
    """Joriy raund ro'yxati — faqat roster_ver o'zgarganda so'raladi."""
    return live.roster()


@router.get("/live")
def live_state():
    """Jonli o'yin holati (xotiradan, bazaga murojaat yo'q)."""
    return live.view()
