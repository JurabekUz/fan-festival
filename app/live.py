"""Jonli o'yin: taymer -> "nomlar maydoni" (nomlar birin-ketin o'chadi) -> natija.

Holat bitta qatorda (live_state) saqlanadi va xotirada keshlanadi — shuning uchun
ochiq /api/live ga ko'p odam kirsa ham bazaga murojaat qilinmaydi (1 ta jarayon).

- Ro'yxat (roster) raund rejalashtirilganda muzlatiladi va ekranda ko'rsatiladi.
- O'yin boshlanganda g'oliblar va har bir yutqazuvchining o'chish vaqti serverda
  aniqlanadi. Ochiq ko'rinish o'chishlarni faqat LOOKAHEAD_MS oldindan beradi,
  g'oliblar ro'yxati esa faqat oxirida — natijani oldindan bilib bo'lmaydi.
"""
import json
import random
import threading

from . import db, draw

_lock = threading.RLock()
_cache: dict | None = None

MIN_SPIN_SEC, MAX_SPIN_SEC, DEFAULT_SPIN_SEC = 8, 120, 20
MAX_COUNTDOWN_SEC = 3600
LOOKAHEAD_MS = 2500          # o'chishlar ekranlarga shuncha oldin yuboriladi (so'rovlar oralig'i uchun)
FINAL_PAUSE_MS = 2200        # oxirgi o'chishdan keyin g'oliblar e'lon qilinguncha
EASE_POWER = 1.6             # boshida tez, oxirida sekin o'chish
ACTIVE = ("countdown", "paused", "spinning")


class LiveError(Exception):
    """Holatga mos kelmaydigan amal (HTTP 409)."""


def pubname(first: str, last: str) -> str:
    return f"{first} {last[:1]}." if last else first


def reset_cache():
    global _cache
    with _lock:
        _cache = None


def _state(con) -> dict:
    global _cache
    if _cache is None:
        row = con.execute("SELECT state_json FROM live_state WHERE id=1").fetchone()
        _cache = json.loads(row["state_json"]) if row else {"status": "idle"}
    return _cache


def _save(con, st: dict):
    global _cache
    con.execute("INSERT OR REPLACE INTO live_state(id,state_json) VALUES(1,?)",
                (json.dumps(st, ensure_ascii=False),))
    _cache = st


def load():
    with db.tx() as con:
        with _lock:
            _state(con)


# ---------------- o'tishlar ----------------
def _elimination(n_tiles: int, keep: set[int], spin_ms: int, rnd) -> list[list[int]]:
    """[[plitka_indeksi, start_dan_ms], ...] vaqt bo'yicha tartiblangan. keep — g'oliblar."""
    losers = [i for i in range(n_tiles) if i not in keep]
    rnd.shuffle(losers)
    span, n = max(1000, spin_ms - FINAL_PAUSE_MS), len(losers)
    return [[i, round(span * (1 - (1 - (k + 1) / n) ** (1 / EASE_POWER)))] for k, i in enumerate(losers)]


def _start_spin(con, st: dict, now: int):
    p = st["params"]
    roster = st["roster"]
    spin_end = now + st["spin_sec"] * 1000
    visible_at = db.iso_from_ms(((spin_end + 999) // 1000) * 1000)
    # o'yin faqat muzlatilgan ro'yxat ichida; shu orada o'ynay olmaydigan bo'lganlar tushib qoladi
    filters = dict(p["filters"], user_ids=[x["id"] for x in roster])
    try:
        res = draw.run_round(con, st["moderator"], p["mode"], filters, n=p.get("n"),
                             chance_pct=p.get("chance_pct"), at_least_one=p.get("at_least_one", False),
                             prize=p.get("prize", ""), note=p.get("note", ""), visible_at=visible_at)
    except ValueError as e:
        _save(con, {"status": "idle", "error": str(e)})
        db.audit(con, st["moderator"], "live_failed", {"error": str(e)})
        return
    rnd = random.SystemRandom()
    idx = {x["id"]: i for i, x in enumerate(roster)}
    in_pool = {x["id"] for x in res["pool"]}
    win_idx = [idx[w["id"]] for w in res["winners"]]
    gone = [[idx[x["id"]], 0] for x in roster if x["id"] not in in_pool]   # o'ynay olmaydiganlar darhol o'chadi
    rest = [i for i in range(len(roster)) if roster[i]["id"] in in_pool]
    sub = _elimination(len(rest), {rest.index(i) for i in win_idx}, st["spin_sec"] * 1000, rnd)
    out = gone + [[rest[i], dt] for i, dt in sub]
    st.update(status="spinning", spin_start_ms=now, spin_end_ms=spin_end,
              round_id=res["round_id"], pool_size=res["pool_size"], out=out,
              winners=[{"idx": idx[w["id"]], "name": pubname(w["first_name"], w["last_name"]),
                        "full_name": w["name"], "passport_no": w["passport_no"]} for w in res["winners"]])
    _save(con, st)


def advance(con) -> dict:
    """Vaqti kelgan o'tishlarni bajaradi (taymer tugadi -> aylanish -> natija)."""
    with _lock:
        st = _state(con)
        now = db.now_ms()
        if st.get("status") == "countdown" and now >= st["countdown_ends_ms"]:
            ends = st["countdown_ends_ms"]
            # kechikish kichik bo'lsa, taymer tugagan paytdan boshlaymiz (hamma ekranda bir xil)
            _start_spin(con, st, ends if now - ends <= 2000 else now)
            st = _state(con)
        if st.get("status") == "spinning" and now >= st["spin_end_ms"]:
            st["status"] = "done"
            _save(con, st)
        return st


def tick():
    """Fon vazifa: har 0.5 s da chaqiriladi, kerak bo'lsa o'tishni bajaradi."""
    st = _cache
    if st is None:
        return
    now = db.now_ms()
    due = ((st.get("status") == "countdown" and now >= st["countdown_ends_ms"]) or
           (st.get("status") == "spinning" and now >= st["spin_end_ms"]))
    if due:
        with db.tx() as con:
            advance(con)


# ---------------- moderator amallari ----------------
def schedule(con, moderator: str, params: dict, countdown_sec: int, spin_sec: int) -> dict:
    if not (0 <= countdown_sec <= MAX_COUNTDOWN_SEC):
        raise ValueError(f"Taymer 0–{MAX_COUNTDOWN_SEC} soniya bo'lsin")
    if not (MIN_SPIN_SEC <= spin_sec <= MAX_SPIN_SEC):
        raise ValueError(f"Charxpalak vaqti {MIN_SPIN_SEC}–{MAX_SPIN_SEC} soniya bo'lsin")
    if params["mode"] == "top_n" and not (params.get("n") and params["n"] >= 1):
        raise ValueError("G'oliblar soni (N) kamida 1 bo'lsin")
    if params["mode"] == "chance" and not (params.get("chance_pct") and 1 <= params["chance_pct"] <= 100):
        raise ValueError("Ehtimollik 1 dan 100 gacha bo'lsin")
    if params["mode"] not in ("top_n", "chance"):
        raise ValueError("Noma'lum usul")
    with _lock:
        st = advance(con)
        if st.get("status") in ACTIVE:
            raise LiveError("Boshqa raund hali tugamagan")
        people = draw.pool(con, params["filters"])
        if not people:
            raise ValueError("Maydon bo'sh: o'ynay oladigan ishtirokchi yo'q")
        random.SystemRandom().shuffle(people)
        now = db.now_ms()
        number = draw.next_number(con)
        st = {"status": "countdown", "moderator": moderator, "params": params,
              "roster_ver": f"{number}-{now}",
              "roster": [{"id": x["id"], "name": pubname(x["first_name"], x["last_name"]),
                          "passport_no": x["passport_no"]} for x in people],
              "number": number, "countdown_sec": countdown_sec, "spin_sec": spin_sec,
              "countdown_ends_ms": now + countdown_sec * 1000}
        _save(con, st)
        db.audit(con, moderator, "live_schedule", {"number": st["number"], "countdown": countdown_sec,
                                                   "spin": spin_sec, "prize": params.get("prize", "")})
        return advance(con)


def pause(con, moderator: str):
    with _lock:
        st = advance(con)
        if st.get("status") != "countdown":
            raise LiveError("Taymer ishlamayapti")
        st["remaining_ms"] = max(0, st["countdown_ends_ms"] - db.now_ms())
        st["status"] = "paused"
        _save(con, st)
        db.audit(con, moderator, "live_pause", {"remaining_ms": st["remaining_ms"]})


def resume(con, moderator: str):
    with _lock:
        st = advance(con)
        if st.get("status") != "paused":
            raise LiveError("Taymer to'xtatilmagan")
        st["countdown_ends_ms"] = db.now_ms() + st.pop("remaining_ms", 0)
        st["status"] = "countdown"
        _save(con, st)
        db.audit(con, moderator, "live_resume", {})


def start_now(con, moderator: str):
    with _lock:
        st = advance(con)
        if st.get("status") not in ("countdown", "paused"):
            raise LiveError("Boshlash uchun taymer bo'lishi kerak")
        st["countdown_ends_ms"] = db.now_ms()
        st["status"] = "countdown"
        st.pop("remaining_ms", None)
        _save(con, st)
        db.audit(con, moderator, "live_start_now", {})
        advance(con)


def cancel(con, moderator: str):
    with _lock:
        st = advance(con)
        if st.get("status") not in ("countdown", "paused"):
            raise LiveError("Bekor qilinadigan taymer yo'q (aylanish boshlangan bo'lsa, u tugashini kuting)")
        _save(con, {"status": "idle"})
        db.audit(con, moderator, "live_cancel", {"number": st.get("number")})


# ---------------- ko'rinishlar ----------------
def view(st: dict | None = None, full: bool = False) -> dict:
    """Ochiq (full=False) yoki moderator (full=True) uchun holat. Natijani oldindan oshkor qilmaydi."""
    st = st if st is not None else (_cache or {"status": "idle"})
    now = db.now_ms()
    status = st.get("status", "idle")
    if status == "spinning" and now >= st["spin_end_ms"]:
        status = "done"
    out = {"server_ms": now, "status": status}
    if status == "idle":
        if st.get("error"):
            out["error"] = st["error"]
        return out
    p = st.get("params", {})
    out.update(number=st.get("number") or st.get("round_id"), prize=p.get("prize", ""), mode=p.get("mode"),
               n=p.get("n"), chance_pct=p.get("chance_pct"), countdown_sec=st.get("countdown_sec"),
               spin_sec=st.get("spin_sec"), roster_ver=st.get("roster_ver"), roster_size=len(st.get("roster", [])))
    if status == "countdown":
        out["countdown_ends_ms"] = st["countdown_ends_ms"]
    elif status == "paused":
        out["remaining_ms"] = st["remaining_ms"]
    else:  # spinning | done
        out.update(spin_start_ms=st["spin_start_ms"], spin_end_ms=st["spin_end_ms"],
                   pool_size=st["pool_size"], round_id=st["round_id"])
        horizon = now - st["spin_start_ms"] + LOOKAHEAD_MS
        out["out"] = st["out"] if status == "done" else [e for e in st["out"] if e[1] <= horizon]
        if status == "done":
            out["winners"] = [{"idx": w["idx"], "name": w["full_name"] if full else w["name"],
                               "passport_no": w["passport_no"]} for w in st["winners"]]
    if full:
        out["moderator"] = st.get("moderator")
        out["params"] = p
    return out


def roster() -> dict:
    """Ekrandagi plitkalar: [{name, passport_no}] (tartib — plitka indeksi)."""
    st = _cache or {}
    return {"ver": st.get("roster_ver"),
            "names": [{"name": x["name"], "passport_no": x["passport_no"]} for x in st.get("roster", [])]
            if st.get("status", "idle") != "idle" else []}
