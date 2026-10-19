import csv
import io
import json
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from . import auth, config, db, draw, live

router = APIRouter(prefix="/api/mod")
UZ = "'+5 hours'"  # Toshkent vaqti (UTC+5)


class ModLogin(BaseModel):
    login: str
    password: str


@router.post("/login")
def mod_login(body: ModLogin, resp: Response):
    key = "mod:" + body.login
    with db.tx() as con:
        if auth.too_many(con, key, 8, 600):
            raise HTTPException(429, "Ko'p xato urinish. Keyinroq urinib ko'ring.")
        real = config.MODERATORS.get(body.login)
        if not real or not secrets.compare_digest(real, body.password):
            auth.record_fail(con, key)
            con.commit()
            raise HTTPException(401, "Login yoki parol noto'g'ri")
        auth.clear_fails(con, key)
        token = auth.new_session(con, "mod", body.login)
        db.audit(con, body.login, "login")
    resp.set_cookie(auth.MOD_COOKIE, token, httponly=True, samesite="lax",
                    secure=config.COOKIE_SECURE, max_age=config.SESSION_HOURS * 3600)
    return {"login": body.login}


@router.post("/logout")
def mod_logout(resp: Response, mod: str = Depends(auth.require_mod)):
    resp.delete_cookie(auth.MOD_COOKIE)
    return {"ok": True}


@router.get("/whoami")
def whoami(mod: str = Depends(auth.require_mod)):
    return {"login": mod}


@router.get("/stats")
def stats(mod: str = Depends(auth.require_mod)):
    with db.tx() as con:
        total = con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        by_zone = {z: 0 for z in range(1, config.ZONE_COUNT + 1)}
        for r in con.execute("SELECT zone_id, COUNT(*) c FROM checkins GROUP BY zone_id"):
            by_zone[r["zone_id"]] = r["c"]
        dist = {k: 0 for k in range(config.ZONE_COUNT + 1)}
        for r in con.execute(
            """SELECT COALESCE(s.c,0) k, COUNT(*) n FROM users u
               LEFT JOIN (SELECT user_id, COUNT(*) c FROM checkins GROUP BY user_id) s ON s.user_id=u.id
               GROUP BY k"""):
            dist[r["k"]] = r["n"]
        hourly_users = {r["h"]: r["c"] for r in con.execute(
            f"SELECT strftime('%H', created_at, {UZ}) h, COUNT(*) c FROM users GROUP BY h")}
        hourly_checkins = {r["h"]: r["c"] for r in con.execute(
            f"SELECT strftime('%H', created_at, {UZ}) h, COUNT(*) c FROM checkins GROUP BY h")}
        rounds = con.execute("SELECT COUNT(*) c FROM draw_rounds WHERE cancelled=0").fetchone()["c"]
        winners = con.execute(
            """SELECT COUNT(DISTINCT e.user_id) c FROM draw_entries e JOIN draw_rounds r
               ON r.id=e.round_id WHERE r.cancelled=0 AND e.won=1""").fetchone()["c"]
    return {
        "total_users": total, "by_zone": by_zone, "stamp_distribution": dist,
        "full_passports": dist[config.ZONE_COUNT],
        "hourly_users": hourly_users, "hourly_checkins": hourly_checkins,
        "rounds": rounds, "distinct_winners": winners,
    }


USER_SQL = """
SELECT u.id,u.first_name,u.last_name,u.phone,u.passport_no,u.blocked,u.created_at,
  (SELECT COUNT(*) FROM checkins c WHERE c.user_id=u.id) AS stamps,
  (SELECT COUNT(*) FROM draw_entries e JOIN draw_rounds r ON r.id=e.round_id
     WHERE e.user_id=u.id AND r.cancelled=0) AS plays,
  (SELECT COUNT(*) FROM draw_entries e JOIN draw_rounds r ON r.id=e.round_id
     WHERE e.user_id=u.id AND r.cancelled=0 AND e.won=1) AS wins,
  (SELECT MAX(r.created_at) FROM draw_entries e JOIN draw_rounds r ON r.id=e.round_id
     WHERE e.user_id=u.id AND r.cancelled=0 AND e.won=1) AS last_win
FROM users u"""


@router.get("/users")
def users(q: str = "", status: str = "all", played: str = "all", won: str = "all", sort: str = "new",
          limit: int = Query(100, le=5000), offset: int = 0,
          mod: str = Depends(auth.require_mod)):
    where, args = ["1=1"], []
    q = q.strip()
    if q:
        digits = re.sub(r"\D", "", q)
        where.append("(u.first_name LIKE ? OR u.last_name LIKE ? OR u.passport_no LIKE ?"
                     + (" OR u.phone LIKE ?" if digits else "") + ")")
        args += [f"%{q}%"] * 3 + ([f"%{digits}%"] if digits else [])
    sql = f"SELECT * FROM ({USER_SQL} WHERE {' AND '.join(where)}) WHERE 1=1"
    if status == "eligible":      # 9/9, bloklanmagan
        sql += f" AND stamps>={config.ZONE_COUNT} AND blocked=0"
    elif status == "incomplete":
        sql += f" AND stamps<{config.ZONE_COUNT}"
    if played == "no":
        sql += " AND plays=0"
    if won == "yes":
        sql += " AND wins>0"
    elif won == "no":
        sql += " AND wins=0"
    order = {"new": "id DESC", "stamps": "stamps DESC, id", "plays": "plays DESC, id",
             "wins": "wins DESC, id", "name": "first_name, last_name"}.get(sort, "id DESC")
    with db.tx() as con:
        total = con.execute(f"SELECT COUNT(*) c FROM ({sql})", args).fetchone()["c"]
        rows = con.execute(f"{sql} ORDER BY {order} LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
    return {"total": total, "users": [dict(r) for r in rows]}


@router.get("/users/{uid}")
def user_detail(uid: int, mod: str = Depends(auth.require_mod)):
    with db.tx() as con:
        u = con.execute(f"{USER_SQL} WHERE u.id=?", (uid,)).fetchone()
        if not u:
            raise HTTPException(404, "Topilmadi")
        stamps = [dict(r) for r in con.execute(
            "SELECT zone_id,created_at,via FROM checkins WHERE user_id=? ORDER BY zone_id", (uid,))]
        history = [dict(r) for r in con.execute(
            """SELECT r.id round_id, r.created_at, r.prize, r.note, r.mode, e.won, r.cancelled
               FROM draw_entries e JOIN draw_rounds r ON r.id=e.round_id
               WHERE e.user_id=? ORDER BY r.id DESC""", (uid,))]
    return {"user": dict(u), "stamps": stamps, "history": history}


class PinIn(BaseModel):
    pin: str


@router.post("/users/{uid}/reset-pin")
def reset_pin(uid: int, body: PinIn, mod: str = Depends(auth.require_mod)):
    if not re.fullmatch(r"\d{4}", body.pin):
        raise HTTPException(422, "PIN 4 ta raqam bo'lsin")
    h = auth.hash_pin(body.pin)
    with db.tx() as con:
        if not con.execute("UPDATE users SET pin_hash=? WHERE id=?", (h, uid)).rowcount:
            raise HTTPException(404, "Topilmadi")
        con.execute("DELETE FROM sessions WHERE kind='user' AND subject=?", (str(uid),))
        con.execute("DELETE FROM attempts WHERE key=(SELECT 'login:'||phone FROM users WHERE id=?)", (uid,))
        db.audit(con, mod, "reset_pin", {"user": uid})
    return {"ok": True}


class StampIn(BaseModel):
    zone: int
    on: bool


@router.post("/users/{uid}/stamp")
def set_stamp(uid: int, body: StampIn, mod: str = Depends(auth.require_mod)):
    if not 1 <= body.zone <= config.ZONE_COUNT:
        raise HTTPException(422, "Maydon 1–9")
    with db.tx() as con:
        if not con.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
            raise HTTPException(404, "Topilmadi")
        if body.on:
            con.execute("INSERT OR IGNORE INTO checkins(user_id,zone_id,created_at,via) VALUES(?,?,?,?)",
                        (uid, body.zone, db.now_iso(), "mod:" + mod))
        else:
            con.execute("DELETE FROM checkins WHERE user_id=? AND zone_id=?", (uid, body.zone))
        db.audit(con, mod, "stamp", {"user": uid, "zone": body.zone, "on": body.on})
    return {"ok": True}


class BlockIn(BaseModel):
    blocked: bool


@router.post("/users/{uid}/block")
def block(uid: int, body: BlockIn, mod: str = Depends(auth.require_mod)):
    with db.tx() as con:
        if not con.execute("UPDATE users SET blocked=? WHERE id=?", (int(body.blocked), uid)).rowcount:
            raise HTTPException(404, "Topilmadi")
        db.audit(con, mod, "block", {"user": uid, "blocked": body.blocked})
    return {"ok": True}


# ---------------- o'yin ----------------
class Filters(BaseModel):
    exclude_played: bool = False
    user_ids: list[int] | None = None


class DrawIn(BaseModel):
    mode: str                      # top_n | chance
    n: int | None = None
    chance_pct: float | None = None
    at_least_one: bool = False
    prize: str = ""
    note: str = ""
    filters: Filters = Field(default_factory=Filters)


class PreviewIn(BaseModel):
    filters: Filters = Field(default_factory=Filters)


@router.get("/draw/next")
def next_round(mod: str = Depends(auth.require_mod)):
    """Keyingi raund raqami va server vaqti (avto)."""
    with db.tx() as con:
        return {"number": draw.next_number(con), "now": db.now_iso()}


@router.post("/draw/preview")
def preview(body: PreviewIn, mod: str = Depends(auth.require_mod)):
    with db.tx() as con:
        people = draw.pool(con, body.filters.model_dump())
    return {"pool_size": len(people), "sample": people[:20]}


@router.post("/draw")
def run_draw(body: DrawIn, mod: str = Depends(auth.require_mod)):
    """Animatsiyasiz darhol raund (API/zaxira). Jonli raund paytida ruxsat yo'q — raqamlar chalkashmasin."""
    with db.tx() as con:
        if live.advance(con).get("status") in live.ACTIVE:
            raise HTTPException(409, "Jonli raund davom etmoqda")
        try:
            return draw.run_round(con, mod, body.mode, body.filters.model_dump(), n=body.n,
                                  chance_pct=body.chance_pct, at_least_one=body.at_least_one,
                                  prize=body.prize, note=body.note)
        except ValueError as e:
            raise HTTPException(422, str(e))


def _rounds(con):
    out = []
    for r in con.execute("SELECT * FROM draw_rounds ORDER BY id DESC"):
        ws = [dict(w) for w in con.execute(
            """SELECT u.id, u.first_name||' '||u.last_name AS name, u.passport_no, u.phone
               FROM draw_entries e JOIN users u ON u.id=e.user_id
               WHERE e.round_id=? AND e.won=1 ORDER BY u.id""", (r["id"],))]
        d = dict(r)
        d["filters"] = json.loads(d.pop("filters_json"))
        d["winners"] = ws
        out.append(d)
    return out


# ---------------- jonli o'yin (taymer + charxpalak) ----------------
class LiveIn(DrawIn):
    countdown_sec: int = 60
    spin_sec: int = 20


def _live_call(fn, *a):
    try:
        with db.tx() as con:
            return fn(con, *a)
    except live.LiveError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/live")
def live_mod(mod: str = Depends(auth.require_mod)):
    with db.tx() as con:
        st = live.advance(con)
    return live.view(st, full=True)


@router.post("/live/schedule")
def live_schedule(body: LiveIn, mod: str = Depends(auth.require_mod)):
    params = {"mode": body.mode, "n": body.n, "chance_pct": body.chance_pct, "at_least_one": body.at_least_one,
              "prize": body.prize.strip(), "note": body.note.strip(), "filters": body.filters.model_dump()}
    st = _live_call(live.schedule, mod, params, body.countdown_sec, body.spin_sec)
    return live.view(st, full=True)


@router.post("/live/pause")
def live_pause(mod: str = Depends(auth.require_mod)):
    _live_call(live.pause, mod)
    return live.view(full=True)


@router.post("/live/resume")
def live_resume(mod: str = Depends(auth.require_mod)):
    _live_call(live.resume, mod)
    return live.view(full=True)


@router.post("/live/start")
def live_start(mod: str = Depends(auth.require_mod)):
    _live_call(live.start_now, mod)
    return live.view(full=True)


@router.post("/live/cancel")
def live_cancel(mod: str = Depends(auth.require_mod)):
    _live_call(live.cancel, mod)
    return live.view(full=True)


@router.get("/draw/rounds")
def rounds(mod: str = Depends(auth.require_mod)):
    with db.tx() as con:
        return {"rounds": _rounds(con)}


@router.delete("/draw/rounds/{rid}")
def cancel_round(rid: int, mod: str = Depends(auth.require_mod)):
    """Raund o'chirilmaydi — bekor qilinadi (tarix saqlanadi); hisoblardan chiqadi."""
    with db.tx() as con:
        if not con.execute(
            "UPDATE draw_rounds SET cancelled=1,cancelled_by=?,cancelled_at=? WHERE id=? AND cancelled=0",
            (mod, db.now_iso(), rid)).rowcount:
            raise HTTPException(404, "Raund topilmadi yoki allaqachon bekor qilingan")
        db.audit(con, mod, "cancel_round", {"round": rid})
    return {"ok": True}


@router.get("/audit")
def audit_log(limit: int = Query(200, le=1000), mod: str = Depends(auth.require_mod)):
    with db.tx() as con:
        rows = con.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return {"log": [dict(r) for r in rows]}


# ---------------- CSV ----------------
def _cell(v):
    """Excel formula in'ektsiyasidan himoya: =, +, -, @ bilan boshlangan matnga ' qo'yiladi."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def _csv(name, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows([[_cell(v) for v in r] for r in rows])
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/export/users.csv")
def export_users(mod: str = Depends(auth.require_mod)):
    with db.tx() as con:
        zones = {}
        for r in con.execute("SELECT user_id,zone_id FROM checkins"):
            zones.setdefault(r["user_id"], set()).add(r["zone_id"])
        rows = con.execute(f"{USER_SQL} ORDER BY u.id").fetchall()
        db.audit(con, mod, "export", {"what": "users"})
    head = ["id", "pasport", "ism", "familiya", "telefon", "ro'yxatdan o'tgan", "muhrlar", "o'ynagan", "yutgan",
            "oxirgi yutuq", "bloklangan"] + [f"maydon{z}" for z in range(1, 10)]
    data = [[r["id"], r["passport_no"], r["first_name"], r["last_name"], r["phone"], r["created_at"],
             r["stamps"], r["plays"], r["wins"], r["last_win"] or "", r["blocked"]]
            + [1 if z in zones.get(r["id"], ()) else 0 for z in range(1, 10)] for r in rows]
    return _csv("ishtirokchilar.csv", head, data)


@router.get("/export/rounds.csv")
def export_rounds(mod: str = Depends(auth.require_mod)):
    with db.tx() as con:
        rs = _rounds(con)
        db.audit(con, mod, "export", {"what": "rounds"})
    data = []
    for r in rs:
        base = [r["id"], r["created_at"], r["moderator"], r["mode"], r["n"] or "", r["chance_pct"] or "",
                r["prize"], r["note"], r["pool_size"], "bekor" if r["cancelled"] else ""]
        if r["winners"]:
            for w in r["winners"]:
                data.append(base + [w["name"], w["passport_no"], w["phone"]])
        else:
            data.append(base + ["", "", ""])
    return _csv("raundlar.csv", ["raund", "vaqt", "moderator", "usul", "N", "ehtimol%", "sovga", "izoh",
                                 "maydon", "holat", "g'olib", "pasport", "telefon"], data)
