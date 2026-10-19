"""Tasodifiy o'yin mantiqi. Tasodif manbai: secrets (kriptografik)."""
import json
import secrets

from . import config, db

_rng = secrets.SystemRandom()


def clean_filters(f: dict | None) -> dict:
    """Qoidalar (filtr emas): pasport 9/9, bloklanmagan, hech qachon yutmagan."""
    f = f or {}
    return {
        "exclude_played": bool(f.get("exclude_played", False)),
        "user_ids": [int(x) for x in f["user_ids"]] if f.get("user_ids") else None,
    }


def pool(con, f: dict) -> list[dict]:
    """O'yin maydoni: 9/9 muhrli, bloklanmagan, hech qachon yutmagan. [{id, name, passport_no, ...}]"""
    f = clean_filters(f)
    sql = """
      SELECT u.id, u.first_name, u.last_name, u.passport_no,
        (SELECT COUNT(*) FROM checkins c WHERE c.user_id=u.id) AS stamps,
        (SELECT COUNT(*) FROM draw_entries e JOIN draw_rounds r ON r.id=e.round_id
           WHERE e.user_id=u.id AND r.cancelled=0 AND e.won=1) AS wins,
        (SELECT COUNT(*) FROM draw_entries e JOIN draw_rounds r ON r.id=e.round_id
           WHERE e.user_id=u.id AND r.cancelled=0) AS plays
      FROM users u WHERE u.blocked=0"""
    args = []
    if f["user_ids"] is not None:
        sql += f" AND u.id IN ({','.join('?' * len(f['user_ids']))})"
        args += f["user_ids"]
    out = []
    for r in con.execute(sql, args).fetchall():
        if r["stamps"] < config.ZONE_COUNT:
            continue
        if r["wins"] > 0:          # yutganlar qayta o'ynamaydi
            continue
        if f["exclude_played"] and r["plays"] > 0:
            continue
        out.append({
            "id": r["id"],
            "name": f"{r['first_name']} {r['last_name']}",
            "first_name": r["first_name"], "last_name": r["last_name"],
            "passport_no": r["passport_no"],
            "stamps": r["stamps"], "wins": r["wins"], "plays": r["plays"],
        })
    return out


def next_number(con) -> int:
    return (con.execute("SELECT COALESCE(MAX(id),0)+1 n FROM draw_rounds").fetchone()["n"])


def pick_top_n(ids: list[int], n: int) -> list[int]:
    return _rng.sample(ids, min(n, len(ids)))


def pick_chance(ids: list[int], pct: float, at_least_one: bool = False) -> list[int]:
    """Har bir ishtirokchi alohida pct% ehtimol bilan yutadi."""
    if not ids:
        return []
    while True:
        won = [i for i in ids if _rng.random() * 100 < pct]
        if won or not at_least_one:
            return won


def run_round(con, moderator: str, mode: str, filters: dict | None, n=None,
              chance_pct=None, at_least_one=False, prize="", note="", visible_at=None):
    f = clean_filters(filters)
    people = pool(con, f)
    if not people:
        raise ValueError("Maydon bo'sh: o'ynay oladigan ishtirokchi yo'q")
    ids = [p["id"] for p in people]
    if mode == "top_n":
        if not n or n < 1:
            raise ValueError("G'oliblar soni (N) kamida 1 bo'lishi kerak")
        won = pick_top_n(ids, int(n))
    elif mode == "chance":
        if chance_pct is None or not (1 <= chance_pct <= 100):
            raise ValueError("Ehtimollik 1 dan 100 gacha bo'lsin")
        won = pick_chance(ids, float(chance_pct), at_least_one)
    else:
        raise ValueError("Noma'lum usul")
    created = db.now_iso()
    cur = con.execute(
        """INSERT INTO draw_rounds(created_at,moderator,mode,n,chance_pct,prize,note,
           filters_json,pool_size,visible_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (created, moderator, mode, n if mode == "top_n" else None,
         chance_pct if mode == "chance" else None, prize.strip(), note.strip(),
         json.dumps(f, ensure_ascii=False), len(ids), visible_at or created),
    )
    rid = cur.lastrowid
    won_set = set(won)
    con.executemany(
        "INSERT INTO draw_entries(round_id,user_id,won) VALUES(?,?,?)",
        [(rid, i, 1 if i in won_set else 0) for i in ids],
    )
    db.audit(con, moderator, "draw", {"round": rid, "mode": mode, "pool": len(ids),
                                      "won": len(won), "prize": prize})
    by_id = {p["id"]: p for p in people}
    return {
        "round_id": rid, "created_at": created, "pool_size": len(ids),
        "winners": [by_id[i] for i in won],
        "pool": people,
    }
