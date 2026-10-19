#!/usr/bin/env bash
# SQLite bazaning onlayn nusxasi (server ishlab turganda ham xavfsiz).
# Cron (formula foydalanuvchisi): */5 * * * * /opt/formula2026/scripts/backup.sh
# Nomlar soat-daqiqa bo'yicha — bir kunda 288 ta nusxa, ertasi kuni ustidan yoziladi.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
.venv/bin/python - <<'PY'
import sqlite3, time
src = sqlite3.connect("data/festival.db")
dst = sqlite3.connect(time.strftime("backups/festival-%H%M.db"))
src.backup(dst)
dst.close(); src.close()
PY
