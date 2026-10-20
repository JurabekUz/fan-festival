"""Bazaga soxta tashrifchilar qo'shadi (to'g'ridan-to'g'ri SQLite'ga, server ishlab turganda ham bo'ladi).

Ishlatish (serverda):
  cd /opt/formula2026
  sudo -u formula .venv/bin/python scripts/seed_users.py 100            # 100 ta, tasodifiy maydonlar bilan
  sudo -u formula .venv/bin/python scripts/seed_users.py 100 --stamps 9 # hammasi 9/9 maydon
  sudo -u formula .venv/bin/python scripts/seed_users.py 50 --pin 0000
  sudo -u formula .venv/bin/python scripts/seed_users.py --clean        # soxtalarni o'chirish

Soxta tashrifchilar telefoni +998 00 ... bilan boshlanadi (haqiqiy operator kodi emas),
shu bo'yicha ular haqiqiy ishtirokchilardan ajratiladi va --clean bilan o'chiriladi.
"""
import argparse
import os
import random
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)  # DB_PATH (data/festival.db) loyiha papkasiga nisbatan
sys.path.insert(0, str(ROOT))
from app import auth, config, db  # noqa: E402

PREFIX = "+99800"

FIRST_NAMES = [
    "Aziz", "Dilnoza", "Jasur", "Madina", "Bekzod", "Zilola", "Sardor", "Nigora", "Otabek", "Malika",
    "Javohir", "Shahzoda", "Rustam", "Gulnora", "Sherzod", "Nodira", "Ulug'bek", "Kamola", "Farrux", "Feruza",
    "Doniyor", "Mohinur", "Islom", "Sevara", "Akmal", "Dildora", "Bobur", "Lola", "Shoxrux", "Munisa",
    "Temur", "Mahliyo", "Abdulla", "Ruxshona", "Elyor", "Sitora", "Jahongir", "Yulduz", "Asadbek", "Barno",
    "Diyor", "Charos", "Sanjar", "Nilufar", "Ibrohim", "Gulruh", "Muhammad", "Oydin", "Firdavs", "Zarina",
    "John", "Emma", "Michael", "Olivia", "David", "Sophia", "James", "Isabella", "Daniel", "Mia",
    "William", "Amelia", "Alexander", "Charlotte", "Henry", "Emily", "Lucas", "Grace", "Thomas", "Chloe",
    "Ethan", "Lily", "Noah", "Hannah", "Liam", "Ella", "Oliver", "Anna", "Samuel", "Sarah",
]

LAST_NAMES = [
    "Karimov", "Rahimova", "Yusupov", "Aliyeva", "Toshmatov", "Nazarova", "Ergashev", "Qodirova", "Saidov", "Mirzayeva",
    "Abdullayev", "Xolmatova", "Ismoilov", "Usmonova", "Jo'rayev", "Sobirova", "Raximov", "Hamidova", "Nurmatov", "Ahmedova",
    "Tursunov", "Valiyeva", "Islomov", "Sultonova", "Murodov", "Haydarova", "Rashidov", "Bakirova", "Sharipov", "Olimova",
    "Smith", "Johnson", "Brown", "Taylor", "Wilson", "Davies", "Evans", "Thomas", "Roberts", "Walker",
    "Wright", "Thompson", "White", "Hughes", "Edwards", "Green", "Hall", "Wood", "Harris", "Clarke",
]


def seed(count, pin, stamps):
    db.init()
    pin_hash = auth.hash_pin(pin)  # bitta xesh hammaga (bcrypt sekin)
    added = 0
    with db.tx() as con:
        used = {r["phone"] for r in con.execute("SELECT phone FROM users WHERE phone LIKE ?", (PREFIX + "%",))}
        types = [r["id"] for r in con.execute("SELECT id FROM visitor_types WHERE active=1")] or [None]
        free = (p for p in (f"{PREFIX}{i:07d}" for i in range(10_000_000)) if p not in used)
        for phone in free:
            if added >= count:
                break
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            try:
                cur = con.execute(
                    "INSERT INTO users(first_name,last_name,phone,pin_hash,created_at,visitor_type_id) VALUES(?,?,?,?,?,?)",
                    (first, last, phone, pin_hash, db.now_iso(), random.choice(types)))
            except sqlite3.IntegrityError:
                continue
            uid = cur.lastrowid
            con.execute("UPDATE users SET passport_no=? WHERE id=?", (f"F26-{uid:04d}", uid))
            k = stamps if stamps is not None else random.choice([9, 9, 9, 7, 5, 3, 1, 0])
            for z in random.sample(range(1, config.ZONE_COUNT + 1), k):
                con.execute("INSERT OR IGNORE INTO checkins(user_id,zone_id,created_at,via) VALUES(?,?,?,?)",
                            (uid, z, db.now_iso(), "seed"))
            added += 1
    print(f"Qo'shildi: {added} ta (PIN: {pin}). Telefonlar {PREFIX}... bilan boshlanadi.")
    print(f"Baza: {Path(config.DB_PATH).resolve()}")


def clean():
    with db.tx() as con:
        ids = [r["id"] for r in con.execute("SELECT id FROM users WHERE phone LIKE ?", (PREFIX + "%",))]
        played = {r["user_id"] for r in con.execute(
            f"SELECT DISTINCT user_id FROM draw_entries WHERE user_id IN ({','.join('?' * len(ids))})", ids)} if ids else set()
        removable = [i for i in ids if i not in played]
        for uid in removable:
            con.execute("DELETE FROM checkins WHERE user_id=?", (uid,))
            con.execute("DELETE FROM sessions WHERE kind='user' AND subject=?", (str(uid),))
            con.execute("DELETE FROM users WHERE id=?", (uid,))
    print(f"O'chirildi: {len(removable)} ta soxta tashrifchi.")
    if played:
        print(f"{len(played)} tasi o'yin raundlarida qatnashgani uchun qoldirildi (raund tarixi buzilmasin).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Soxta tashrifchilar qo'shish / o'chirish")
    ap.add_argument("count", nargs="?", type=int, default=100, help="nechta qo'shish (standart 100)")
    ap.add_argument("--pin", default="1234", help="hammasi uchun 4 xonali PIN (standart 1234)")
    ap.add_argument("--stamps", type=int, choices=range(0, 10), metavar="0-9",
                    help="har biriga nechta maydon belgisi (berilmasa tasodifiy)")
    ap.add_argument("--clean", action="store_true", help="+99800... telefonli soxta tashrifchilarni o'chirish")
    a = ap.parse_args()
    if a.clean:
        clean()
    else:
        if not (len(a.pin) == 4 and a.pin.isdigit()):
            sys.exit("PIN 4 ta raqam bo'lsin")
        seed(a.count, a.pin, a.stamps)
