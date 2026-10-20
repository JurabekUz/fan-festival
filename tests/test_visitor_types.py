from fastapi.testclient import TestClient

from conftest import register


def _reg(json):
    from app.main import app
    return TestClient(app).post("/api/register", json={"first_name": "A", "last_name": "B", "phone": "901112233",
                                                       "pin": "1234", **json})


def test_defaults_and_required(client):
    types = client.get("/api/visitor-types").json()["types"]
    assert len(types) == 6 and types[0]["name"] == "Академия ходими"
    assert _reg({}).status_code == 422                       # majburiy
    assert _reg({"visitor_type_id": 999}).status_code == 422  # mavjud emas
    r = _reg({"visitor_type_id": 3})
    assert r.status_code == 200 and r.json()["visitor_type_id"] == 3


def test_mod_crud_and_inactive(client, mod):
    tid = mod.post("/api/mod/visitor-types", json={"name": "  Журналист "}).json()["id"]
    assert mod.post("/api/mod/visitor-types", json={"name": "Журналист"}).status_code == 409
    assert any(t["name"] == "Журналист" for t in client.get("/api/visitor-types").json()["types"])
    assert mod.patch(f"/api/mod/visitor-types/{tid}", json={"active": False}).status_code == 200
    assert all(t["id"] != tid for t in client.get("/api/visitor-types").json()["types"])
    assert _reg({"visitor_type_id": tid}).status_code == 422  # nofaol turni tanlab bo'lmaydi
    assert mod.delete(f"/api/mod/visitor-types/{tid}").status_code == 200
    # ishlatilgan turni o'chirib bo'lmaydi
    register(client, 1, stamps=0)
    assert mod.delete("/api/mod/visitor-types/1").status_code == 409


def test_null_type_stats_and_mod_edit(client, mod):
    c = register(client, 1, stamps=0)
    from app import db
    with db.tx() as con:  # eski foydalanuvchi: turi yo'q
        con.execute("UPDATE users SET visitor_type_id=NULL")
    assert c.get("/api/me").json()["visitor_type_id"] is None
    by = {t["id"]: t["c"] for t in mod.get("/api/mod/stats").json()["by_type"]}
    assert by[None] == 1
    assert mod.post("/api/mod/users/1/type", json={"visitor_type_id": 2}).status_code == 200
    by = {t["id"]: t["c"] for t in mod.get("/api/mod/stats").json()["by_type"]}
    assert by[None] == 0 and by[2] == 1
    assert mod.get("/api/mod/users?vtype=2").json()["total"] == 1
    assert mod.get("/api/mod/users?vtype=none").json()["total"] == 0
    assert mod.post("/api/mod/users/1/type", json={"visitor_type_id": 5}).status_code == 200
    assert mod.get("/api/mod/users/1").json()["user"]["visitor_type"] == "Мактаб ўқувчиси"
    assert "Мактаб ўқувчиси" in mod.get("/api/mod/export/users.csv").text


def test_name_ru(client, mod):
    t = {x["name"]: x for x in client.get("/api/visitor-types").json()["types"]}
    assert t["Талаба"]["name_ru"] == "Студент"
    tid = mod.post("/api/mod/visitor-types", json={"name": "Журналист", "name_ru": " Журналист  СМИ "}).json()["id"]
    assert mod.patch(f"/api/mod/visitor-types/{tid}", json={"name_ru": "Журналист"}).status_code == 200
    t = {x["id"]: x for x in client.get("/api/visitor-types").json()["types"]}
    assert t[tid]["name_ru"] == "Журналист"
