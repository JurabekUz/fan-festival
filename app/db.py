import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  phone TEXT NOT NULL UNIQUE,
  pin_hash TEXT NOT NULL,
  passport_no TEXT UNIQUE,
  blocked INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  visitor_type_id INTEGER REFERENCES visitor_types(id)
);
CREATE TABLE IF NOT EXISTS visitor_types(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  sort INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkins(
  user_id INTEGER NOT NULL REFERENCES users(id),
  zone_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  via TEXT NOT NULL DEFAULT 'code',
  PRIMARY KEY(user_id, zone_id)
);
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  subject TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS draw_rounds(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  moderator TEXT NOT NULL,
  mode TEXT NOT NULL,
  n INTEGER,
  chance_pct REAL,
  prize TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  filters_json TEXT NOT NULL DEFAULT '{}',
  pool_size INTEGER NOT NULL,
  visible_at TEXT,
  cancelled INTEGER NOT NULL DEFAULT 0,
  cancelled_by TEXT,
  cancelled_at TEXT
);
CREATE TABLE IF NOT EXISTS draw_entries(
  round_id INTEGER NOT NULL REFERENCES draw_rounds(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  won INTEGER NOT NULL,
  PRIMARY KEY(round_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_entries_user ON draw_entries(user_id);
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  moderator TEXT NOT NULL,
  action TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS live_state(
  id INTEGER PRIMARY KEY CHECK(id=1),
  state_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts(
  key TEXT NOT NULL,
  ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts ON attempts(key, ts);
"""


# birinchi ishga tushishda; keyin moderator /mod da o'zgartiradi
DEFAULT_VISITOR_TYPES = ["Академия ходими", "Олий таълим ўқитувчиси", "Талаба", "Мактаб ўқитувчиси",
                         "Мактаб ўқувчиси", "Бошқа"]


def now_ms() -> int:
    """Yagona soat (testlarda almashtiriladi)."""
    return int(time.time() * 1000)


def iso_from_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso():
    return iso_from_ms(now_ms())


def connect():
    path = Path(config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


@contextmanager
def tx():
    """Bitta so'rov uchun ulanish; muvaffaqiyatda commit, xatoda rollback."""
    con = connect()
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def init():
    with tx() as con:
        con.executescript(SCHEMA)
        cols = {r["name"] for r in con.execute("PRAGMA table_info(draw_rounds)")}
        if "visible_at" not in cols:  # eski bazalar uchun
            con.execute("ALTER TABLE draw_rounds ADD COLUMN visible_at TEXT")
        ucols = {r["name"] for r in con.execute("PRAGMA table_info(users)")}
        if "visitor_type_id" not in ucols:  # eski bazalar uchun
            con.execute("ALTER TABLE users ADD COLUMN visitor_type_id INTEGER REFERENCES visitor_types(id)")
        if not con.execute("SELECT 1 FROM visitor_types LIMIT 1").fetchone():
            now = now_iso()
            con.executemany("INSERT INTO visitor_types(name,sort,created_at) VALUES(?,?,?)",
                            [(n, i, now) for i, n in enumerate(DEFAULT_VISITOR_TYPES)])
        con.execute("INSERT OR IGNORE INTO live_state(id,state_json) VALUES(1,?)",
                    (json.dumps({"status": "idle"}),))


def audit(con, moderator, action, payload=None):
    con.execute(
        "INSERT INTO audit_log(moderator,action,payload_json,created_at) VALUES(?,?,?,?)",
        (moderator, action, json.dumps(payload or {}, ensure_ascii=False), now_iso()),
    )
