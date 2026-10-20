"""Bazani tadbirdan oldin tozalaydi: ishtirokchilar, muhrlar, raundlar, sessiyalar, jurnal.

Tashrif buyuruvchi turlari (visitor_types) SAQLANADI. Nusxa olinmaydi — o'chirilgan ma'lumot qaytmaydi.
Pasport raqamlari yana F26-0001 dan, raundlar #1 dan boshlanadi.

Ishlatish (serverda, AVVAL servisni to'xtating):
  sudo systemctl stop formula
  cd /opt/formula2026
  sudo -u formula .venv/bin/python scripts/reset_db.py
  sudo systemctl start formula
"""
import fcntl
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)  # DB_PATH (data/festival.db) loyiha papkasiga nisbatan
sys.path.insert(0, str(ROOT))
from app import config  # noqa: E402

TABLES = ["draw_entries", "draw_rounds", "checkins", "sessions", "attempts", "audit_log", "users"]


def main():
    path = Path(config.DB_PATH)
    if not path.exists():
        sys.exit(f"Baza topilmadi: {path.resolve()}")

    # ilova ishlayotgan bo'lsa, u shu qulfni ushlab turadi (app/main.py)
    lock = open(path.with_suffix(".lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit("Ilova hali ishlayapti. Avval: sudo systemctl stop formula")

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    counts = {t: con.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"] for t in TABLES}
    print(f"Baza: {path.resolve()}")
    for t in TABLES:
        print(f"  {t:<14} {counts[t]:>6} ta yozuv")
    types = con.execute("SELECT COUNT(*) c FROM visitor_types").fetchone()["c"]
    print(f"  visitor_types  {types:>6} ta — saqlanadi")

    if input("\nHammasi o'chirilsinmi? Tasdiqlash uchun TOZALASH deb yozing: ").strip() != "TOZALASH":
        sys.exit("Bekor qilindi, hech narsa o'zgarmadi.")

    with con:
        for t in TABLES:
            con.execute(f"DELETE FROM {t}")
        con.execute(f"DELETE FROM sqlite_sequence WHERE name IN ({','.join('?' * len(TABLES))})", TABLES)
        con.execute("""INSERT OR REPLACE INTO live_state(id,state_json) VALUES(1,'{"status": "idle"}')""")
    con.execute("VACUUM")
    con.close()
    print("Tayyor: baza tozalandi. Endi: sudo systemctl start formula")


if __name__ == "__main__":
    main()
