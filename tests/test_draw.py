from conftest import register


def _users(client, k, stamps=9):
    return [register(client, i, stamps) for i in range(1, k + 1)]


def test_top_n_exact_and_history(client, mod):
    _users(client, 10)
    r = mod.post("/api/mod/draw", json={"mode": "top_n", "n": 3, "prize": "Ryukzak"}).json()
    assert r["pool_size"] == 10 and len(r["winners"]) == 3
    rounds = mod.get("/api/mod/draw/rounds").json()["rounds"]
    assert rounds[0]["prize"] == "Ryukzak" and len(rounds[0]["winners"]) == 3
    us = mod.get("/api/mod/users").json()["users"]
    assert sum(u["plays"] for u in us) == 10 and sum(u["wins"] for u in us) == 3


def test_exclude_winners_default(client, mod):
    _users(client, 5)
    first = {w["id"] for w in mod.post("/api/mod/draw", json={"mode": "top_n", "n": 3}).json()["winners"]}
    second = mod.post("/api/mod/draw", json={"mode": "top_n", "n": 5}).json()
    assert second["pool_size"] == 2 and not first & {w["id"] for w in second["winners"]}
    # pool bo'sh
    assert mod.post("/api/mod/draw", json={"mode": "top_n", "n": 1}).status_code == 422


def test_winners_never_play_again(client, mod):
    _users(client, 3)
    first = {w["id"] for w in mod.post("/api/mod/draw", json={"mode": "top_n", "n": 2}).json()["winners"]}
    # eski mijoz max_wins yuborsa ham qoida o'zgarmaydi; qo'lda tanlansa ham kirmaydi
    r = mod.post("/api/mod/draw", json={"mode": "top_n", "n": 3,
                                        "filters": {"max_wins": 5, "user_ids": list(first) + [99]}})
    assert r.status_code == 422
    assert mod.post("/api/mod/draw/preview", json={}).json()["pool_size"] == 1
    us = mod.get("/api/mod/users").json()["users"]
    assert max(u["wins"] for u in us) == 1


def test_only_full_passports_always(client, mod):
    _users(client, 3, stamps=9)
    register(client, 4, stamps=5)
    assert mod.post("/api/mod/draw/preview", json={}).json()["pool_size"] == 3
    # qo'lda tanlangan ro'yxatda 5 muhrli odam bo'lsa ham o'yinga kirmaydi
    ids = [u["id"] for u in mod.get("/api/mod/users").json()["users"]]
    r = mod.post("/api/mod/draw", json={"mode": "top_n", "n": 9, "filters": {"user_ids": ids}}).json()
    assert r["pool_size"] == 3 and len(r["winners"]) == 3


def test_manual_pool_subset(client, mod):
    _users(client, 5)
    ids = [u["id"] for u in mod.get("/api/mod/users").json()["users"]][:2]
    r = mod.post("/api/mod/draw", json={"mode": "top_n", "n": 5, "filters": {"user_ids": ids}}).json()
    assert r["pool_size"] == 2 and len(r["winners"]) == 2  # n > maydon -> hammasi


def test_exclude_played(client, mod):
    _users(client, 4)
    mod.post("/api/mod/draw", json={"mode": "top_n", "n": 1})  # maydon 4, hammasi o'ynadi, 1 tasi yutdi
    assert mod.post("/api/mod/draw/preview", json={"filters": {"exclude_played": True}}).json()["pool_size"] == 0
    assert mod.post("/api/mod/draw/preview", json={}).json()["pool_size"] == 3


def test_round_number_and_time_auto(client, mod):
    _users(client, 3)
    assert mod.get("/api/mod/draw/next").json()["number"] == 1
    r1 = mod.post("/api/mod/draw", json={"mode": "top_n", "n": 1}).json()
    assert r1["round_id"] == 1 and r1["created_at"].endswith("Z")
    assert mod.get("/api/mod/draw/next").json()["number"] == 2
    r2 = mod.post("/api/mod/draw", json={"mode": "top_n", "n": 1}).json()
    assert r2["round_id"] == 2


def test_users_status_and_played_filters(client, mod):
    _users(client, 2, stamps=9)
    register(client, 3, stamps=4)
    q = lambda s: mod.get("/api/mod/users?" + s).json()["total"]
    assert q("status=eligible") == 2 and q("status=incomplete") == 1 and q("played=no") == 3
    mod.post("/api/mod/draw", json={"mode": "top_n", "n": 1})
    assert q("played=no") == 1


def test_chance_extremes(client, mod):
    _users(client, 4)
    r = mod.post("/api/mod/draw", json={"mode": "chance", "chance_pct": 100}).json()
    assert len(r["winners"]) == 4
    assert mod.post("/api/mod/draw/preview", json={}).json()["pool_size"] == 0   # hammasi yutdi
    register(client, 5)
    r = mod.post("/api/mod/draw", json={"mode": "chance", "chance_pct": 1, "at_least_one": True}).json()
    assert len(r["winners"]) == 1
    assert mod.post("/api/mod/draw", json={"mode": "chance", "chance_pct": 0}).status_code == 422


def test_chance_statistics():
    from app import draw
    ids = list(range(2000))
    got = len(draw.pick_chance(ids, 50))
    assert 850 < got < 1150


def test_cancel_round_restores_eligibility(client, mod):
    _users(client, 3)
    rid = mod.post("/api/mod/draw", json={"mode": "top_n", "n": 3}).json()["round_id"]
    assert mod.post("/api/mod/draw/preview", json={}).json()["pool_size"] == 0
    assert mod.delete(f"/api/mod/draw/rounds/{rid}").status_code == 200
    assert mod.post("/api/mod/draw/preview", json={}).json()["pool_size"] == 3
    assert client.get("/api/winners").json()["rounds"] == []
    # tarix saqlangan
    assert mod.get("/api/mod/draw/rounds").json()["rounds"][0]["cancelled"] == 1


def test_public_winners_masks_phone(client, mod):
    _users(client, 2)
    mod.post("/api/mod/draw", json={"mode": "top_n", "n": 1, "prize": "Kitob"})
    w = client.get("/api/winners").json()
    assert w["eligible"] == 2
    win = w["rounds"][0]["winners"][0]
    assert "***" in win["phone"] and win["name"].endswith(".")
