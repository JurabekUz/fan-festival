"""Sinov uchun soxta ishtirokchilar yaratadi (ishlab chiqarishda ISHLATMANG).
Ishlatish: python scripts/seed_demo.py [soni] [http://localhost:8000]"""
import random
import sys
import httpx
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
base = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"
names = ["Aziz", "Dilnoza", "Jasur", "Madina", "Bekzod", "Zilola", "Sardor", "Nigora", "Otabek", "Malika"]
for i in range(n):
    c = httpx.Client(base_url=base)
    r = c.post("/api/register", json={"first_name": random.choice(names), "last_name": f"Demo{i}",
                                      "phone": f"93 700 {i:04d}", "pin": "1234"})
    if r.status_code != 200:
        continue
    for z in random.sample(range(1, 10), random.choice([9, 9, 9, 7, 5, 3])):
        c.post("/api/checkin", json={"zone": z, "code": config.ZONE_CODES[z]})
print("tayyor")
