import os
from dotenv import load_dotenv

load_dotenv()


def _pairs(raw):
    out = {}
    for part in raw.split(","):
        part = part.strip()
        if part and ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


DB_PATH = os.getenv("DB_PATH", "data/festival.db")
ZONE_CODES = {int(k): v for k, v in _pairs(os.getenv("ZONE_CODES", "")).items()}
MODERATORS = _pairs(os.getenv("MODERATORS", ""))
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "24"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
ZONE_COUNT = 9
# Kirish urinishlari limiti
LOGIN_MAX_FAILS = 5
LOGIN_WINDOW_SEC = 600
# bitta IP dan (mobil operator NAT ortida ko'p odam bo'ladi — shuning uchun katta)
LOGIN_IP_MAX_FAILS = 40
CODE_MAX_FAILS = 5
CODE_WINDOW_SEC = 60
