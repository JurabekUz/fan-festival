import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, db  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "COOKIE_SECURE", False)
    monkeypatch.setattr(config, "MODERATORS", {"aziz": "pw1"})
    monkeypatch.setattr(config, "ZONE_CODES", {i: f"{i}{i}{i}{i}" for i in range(1, 10)})
    from app.main import app
    with TestClient(app) as c:
        yield c


def register(client, n, stamps=9, phone=None):
    """n-chi foydalanuvchini ro'yxatdan o'tkazib, stamps ta muhr qo'yadi. (yangi mijoz qaytaradi)"""
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/register", json={"first_name": f"Ism{n}", "last_name": f"Fam{n}",
                                      "phone": phone or f"90 100 {n:04d}", "pin": "1234"})
    assert r.status_code == 200, r.text
    for z in range(1, stamps + 1):
        assert c.post("/api/checkin", json={"zone": z, "code": f"{z}{z}{z}{z}"}).status_code == 200
    return c


@pytest.fixture()
def mod(client):
    from app.main import app
    m = TestClient(app)
    assert m.post("/api/mod/login", json={"login": "aziz", "password": "pw1"}).status_code == 200
    return m
