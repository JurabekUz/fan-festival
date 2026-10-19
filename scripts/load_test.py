"""Yengil yuklama sinovi: N ta foydalanuvchi ro'yxatdan o'tib, 9 ta kod kiritadi.
Ishlatish: python scripts/load_test.py 500 http://localhost:8000  (faqat sinov bazada!)"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
base = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"


def one(i):
    c = httpx.Client(base_url=base, timeout=30)
    r = c.post("/api/register", json={"first_name": "Load", "last_name": str(i),
                                      "phone": f"{91 + i // 10_000_000:02d} {i % 10_000_000:07d}"[:12], "pin": "1234"})
    if r.status_code != 200:
        return 0
    for z, code in config.ZONE_CODES.items():
        c.post("/api/checkin", json={"zone": z, "code": code})
    c.get("/api/winners")
    return 10


t = time.time()
with ThreadPoolExecutor(32) as ex:
    reqs = sum(ex.map(one, range(n)))
dt = time.time() - t
print(f"{n} foydalanuvchi, {reqs} so'rov, {dt:.1f}s, {reqs / dt:.0f} req/s")
