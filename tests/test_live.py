import pytest
from fastapi.testclient import TestClient

from app import db, live
from conftest import register


@pytest.fixture()
def clock(monkeypatch):
    t = {"ms": 1_800_000_000_000}
    monkeypatch.setattr(db, "now_ms", lambda: t["ms"])
    return t


def adv(clock, sec):
    clock["ms"] += int(sec * 1000)
    live.tick()


def sched(mod, **kw):
    body = {"mode": "top_n", "n": 2, "prize": "Ryukzak", "countdown_sec": 30, "spin_sec": 20}
    body.update(kw)
    return mod.post("/api/mod/live/schedule", json=body)


def users(client, k):
    return [register(client, i) for i in range(1, k + 1)]


def test_full_flow_hidden_until_reveal(clock, client, mod):
    cs = users(client, 5)
    r = sched(mod)
    assert r.status_code == 200 and r.json()["status"] == "countdown" and r.json()["number"] == 1
    pub = client.get("/api/live").json()
    assert pub["status"] == "countdown" and pub["countdown_ends_ms"] == clock["ms"] + 30_000
    assert "out" not in pub and "winners" not in pub and pub["roster_size"] == 5
    ros = client.get("/api/live/roster").json()
    assert ros["ver"] == pub["roster_ver"] and len(ros["names"]) == 5
    assert all(x["name"].endswith(".") and x["passport_no"].startswith("F26-") for x in ros["names"])

    adv(clock, 10)                                    # pauza
    assert mod.post("/api/mod/live/pause").json()["status"] == "paused"
    assert client.get("/api/live").json()["remaining_ms"] == 20_000
    adv(clock, 100)                                   # to'xtab turibdi
    assert client.get("/api/live").json()["status"] == "paused"
    assert mod.post("/api/mod/live/resume").json()["status"] == "countdown"
    adv(clock, 19)
    assert client.get("/api/live").json()["status"] == "countdown"
    adv(clock, 1.5)                                   # taymer tugadi -> aylanish

    pub = client.get("/api/live").json()
    assert pub["status"] == "spinning" and pub["pool_size"] == 5
    assert pub["out"] == [] and "winners" not in pub          # o'chishlar faqat 2.5 s oldindan beriladi
    assert client.get("/api/winners").json()["rounds"] == []          # hali oshkor emas
    assert all(c.get("/api/me").json()["wins"] == [] for c in cs)

    adv(clock, 13)                                    # 16 s gacha bo'lgan o'chishlar ko'rinadi
    pub = client.get("/api/live").json()
    assert pub["status"] == "spinning" and len(pub["out"]) == 2 and "winners" not in pub
    assert all(dt <= 13_500 + 2_500 for _, dt in pub["out"])
    assert client.get("/api/winners").json()["rounds"] == []

    adv(clock, 8)                                     # tugadi
    pub = client.get("/api/live").json()
    assert pub["status"] == "done" and len(pub["winners"]) == 2
    assert all(w["name"].endswith(".") for w in pub["winners"])
    out_idx = {i for i, _ in pub["out"]}
    assert len(out_idx) == 3 and not out_idx & {w["idx"] for w in pub["winners"]}
    assert all(ros["names"][w["idx"]]["name"] == w["name"] for w in pub["winners"])
    rounds = client.get("/api/winners").json()["rounds"]
    assert len(rounds) == 1 and rounds[0]["prize"] == "Ryukzak" and len(rounds[0]["winners"]) == 2
    assert sum(len(c.get("/api/me").json()["wins"]) for c in cs) == 2
    full = mod.get("/api/mod/live").json()
    assert {w["name"] for w in full["winners"]} == {w["name"] for w in mod.get("/api/mod/draw/rounds").json()["rounds"][0]["winners"]}


def test_zero_countdown_and_start_now(clock, client, mod):
    users(client, 3)
    assert sched(mod, countdown_sec=0).json()["status"] == "spinning"
    adv(clock, 21)
    assert client.get("/api/live").json()["status"] == "done"
    # yangi raund (done dan keyin mumkin) + "hozir boshlash"
    assert sched(mod, n=1, countdown_sec=300).json()["number"] == 2
    assert mod.post("/api/mod/live/start").json()["status"] == "spinning"


def test_cancel_only_before_spin(clock, client, mod):
    users(client, 3)
    sched(mod)
    assert mod.post("/api/mod/live/cancel").json()["status"] == "idle"
    assert mod.get("/api/mod/draw/rounds").json()["rounds"] == []     # raund yaratilmagan
    sched(mod, countdown_sec=0)
    assert mod.post("/api/mod/live/cancel").status_code == 409        # aylanish boshlangan


def test_busy_and_validation(clock, client, mod):
    users(client, 3)
    assert sched(mod, spin_sec=3).status_code == 422
    assert sched(mod, countdown_sec=-1).status_code == 422
    assert sched(mod, mode="top_n", n=0).status_code == 422
    assert sched(mod).status_code == 200
    assert sched(mod).status_code == 409
    assert mod.post("/api/mod/live/resume").status_code == 409


def test_empty_pool_rejected_and_tick_failure(clock, client, mod):
    assert sched(mod).status_code == 422                               # hech kim yo'q
    users(client, 2)
    sched(mod)                                                         # 2 kishi bor
    # taymer paytida hamma bloklansa — boshlanganda xato bilan idle ga qaytadi
    for u in mod.get("/api/mod/users").json()["users"]:
        mod.post(f"/api/mod/users/{u['id']}/block", json={"blocked": True})
    adv(clock, 31)
    st = client.get("/api/live").json()
    assert st["status"] == "idle" and "Maydon" in st.get("error", "")


def test_chance_mode_everyone_can_drop(clock, client, mod):
    users(client, 3)
    sched(mod, mode="chance", n=None, chance_pct=1, countdown_sec=0)   # deyarli hech kim yutmaydi
    adv(clock, 21)
    pub = client.get("/api/live").json()
    assert pub["status"] == "done" and len(pub["out"]) + len(pub["winners"]) == 3


def test_roster_frozen_and_ineligible_drop_first(clock, client, mod):
    users(client, 4)
    sched(mod, n=1)
    ros = client.get("/api/live/roster").json()["names"]
    register(client, 9)                                                 # taymer paytida kelgan — ro'yxatga kirmaydi
    uid = next(u["id"] for u in mod.get("/api/mod/users").json()["users"] if u["passport_no"] == ros[0]["passport_no"])
    mod.post(f"/api/mod/users/{uid}/block", json={"blocked": True})      # bloklangan — darhol o'chadi
    adv(clock, 31)
    pub = client.get("/api/live").json()
    assert pub["pool_size"] == 3 and [0, 0] in pub["out"]
    assert len(client.get("/api/live/roster").json()["names"]) == 4


def test_live_requires_mod(client):
    assert client.post("/api/mod/live/schedule", json={"mode": "top_n", "n": 1}).status_code == 401
    assert client.get("/api/live").json()["status"] == "idle"


def test_instant_draw_blocked_during_live(clock, client, mod):
    users(client, 3)
    sched(mod)
    assert mod.post("/api/mod/draw", json={"mode": "top_n", "n": 1}).status_code == 409
    mod.post("/api/mod/live/cancel")
    assert mod.post("/api/mod/draw", json={"mode": "top_n", "n": 1}).status_code == 200
