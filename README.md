# FORMULA–2026 · Ilmiy pasport

FastAPI + SQLite. Bitta jarayon ham API'ni, ham sahifalarni beradi.

| Sahifa | Kim uchun |
|---|---|
| `/` | Tashrifchi: ro'yxatdan o'tish, 9 maydon kodi, oxirgi raund g'oliblari |
| `/live` | Hamma: jonli "nomlar maydoni" (proyektor ham shu) |
| `/mod` | Moderator: hisobot, ishtirokchilar, PIN tiklash, raundlar |
| `/live-demo` | Sinov: soxta ismlar, bazaga yozmaydi |

Reja va qoidalar: [PLAN.md](PLAN.md).

## Lokal ishga tushirish

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env          # lokalda COOKIE_SECURE=false
.venv/bin/uvicorn app.main:app --port 8000
.venv/bin/python -m pytest -q tests
```

Soxta ishtirokchilar: `.venv/bin/python scripts/seed_demo.py 30` (faqat sinov bazasida).

## Serverga o'rnatish (Ubuntu, venv + systemd + nginx)

Python ≥ 3.10 kerak.

```bash
sudo apt install -y python3-venv nginx certbot python3-certbot-nginx
sudo useradd --system --home /opt/formula2026 formula
sudo mkdir -p /opt/formula2026 && sudo chown formula: /opt/formula2026
# kodni /opt/formula2026 ga ko'chiring (git clone yoki rsync), so'ng:
cd /opt/formula2026
sudo -u formula python3 -m venv .venv
sudo -u formula .venv/bin/pip install -r requirements.txt
sudo -u formula mkdir -p data backups
sudo -u formula cp .env.example .env   # tahrirlang: kuchli parollar, COOKIE_SECURE=true
sudo chmod 600 .env
sudo cp deploy/formula.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now formula
sudo cp deploy/nginx.conf /etc/nginx/sites-available/formula2026   # domenni yozing
sudo ln -s /etc/nginx/sites-available/formula2026 /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d DOMEN
sudo -u formula crontab -e   # */5 * * * * /opt/formula2026/scripts/backup.sh
```

Tekshirish: `systemctl status formula`, jurnal: `journalctl -u formula -f`.

**Muhim:**
- `--workers 1` ni o'zgartirmang — jonli o'yin holati xotirada.
- `.env` noto'g'ri bo'lsa (kodlar yo'q, moderator yo'q) server ishga tushmaydi; namunaviy/zaif parol bo'lsa jurnalga ogohlantirish yoziladi.
- Kodni yangilash: fayllarni almashtiring → `sudo systemctl restart formula` (baza `data/` da qoladi).

## Tadbir kuni

- PIN unutilsa: `/mod` → Ishtirokchilar → qidirish → ochish → yangi PIN.
- O'yin: `/mod` → O'yin → ishtirokchilarni belgilang (yoki «Hammasini tanlash») → sovg'a, N yoki p%, taymer → «Taymerni ishga tushirish». Pauza / hozir boshlash / bekor qilish tepadagi panelda.
- Taymer tugagach `/live` da nomlar 20 s (8–120 s) davomida o'chib boradi, oxirida g'oliblar qoladi. Natija oxirigacha oshkor bo'lmaydi (o'chishlar ekranlarga atigi 2.5 s oldin yuboriladi).
- Yutganlar qayta o'ynamaydi. Xato raund: Raundlar → Bekor qilish (tarixda qoladi, g'oliblari yana o'ynay oladi).
- `/live` ni proyektorda ⛶ tugmasi bilan to'liq ekran qiling.
- Oxirida: Hisobot → CSV eksport.
