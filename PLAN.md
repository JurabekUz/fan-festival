# FORMULA–2026 Fan festivali — "Ilmiy pasport" tizimi: reja (v2)

**Sana:** 21-oktabr 2026, 09:00–18:00, Toshkent Botanika bog'i. Bugun 19-oktabr — **2 kun qoldi**, reja ataylab sodda.

## 1. Maqsad

Tashrifchi telefonidan saytga kiradi → ism, familiya, telefon, 4 xonali PIN bilan ro'yxatdan o'tadi → 9 ta maydonda kod kiritib muhr yig'adi. Muhrlar **serverdagi bazada, telefon raqamiga bog'lab** saqlanadi.
Kun davomida moderator bir necha marta tasodifiy o'yin o'tkazadi. Moderator jonli hisobotni ko'radi, PIN tiklaydi, ishtirokchilarni boshqaradi.

## 2. Qarorlar (v1 dan o'zgargan)

| Mavzu | Qaror |
|---|---|
| Backend | **Python 3.12 + FastAPI + SQLite** (Flask ham bo'ladi, lekin FastAPI'da validatsiya va `/docs` test sahifasi tayyor) |
| Kodlar | Maxfiy emas. Sahifadagi tekshiruv qoladi; server ham `.env`dagi kod bilan oddiy solishtiradi (1 qator, axlat yozuv tushmasligi uchun) |
| Muhrlar | `localStorage` emas — SQLite bazasida, telefon raqamga bog'langan. CSV — faqat eksport uchun |
| Telefon | Unikal, yagona identifikator. SMS tasdiqlash yo'q |
| PIN unutilsa | Moderator telefon bo'yicha topib, yangi PIN o'rnatadi |
| Rollar | Faqat **moderator** (admin roli yo'q). Hamma moderatorlar teng huquqli |
| O'yin | Kun davomida **ko'p raund**, 2 xil usul, filtrlar, ishtirok tarixi (8-bo'lim) |
| Sozlamalar | `.env` |

## 3. Texnologiya

- **FastAPI** + **uvicorn** (1 worker — SQLite uchun yetarli va xavfsiz)
- **SQLite** (WAL rejimi), standart `sqlite3` moduli — ORM shart emas
- `bcrypt` (PIN hash), `python-dotenv`, `secrets` (tasodif uchun kriptografik generator)
- Frontend: artifactdagi tayyor HTML/JS, `fetch('/api/...')` ga ulanadi. Build/framework yo'q.

## 4. Ma'lumotlar modeli

```
users        id, first_name, last_name, phone UNIQUE (+998XXXXXXXXX),
             pin_hash, passport_no (F26-0001), created_at, blocked (0/1)
checkins     user_id, zone_id (1..9), created_at, PRIMARY KEY(user_id, zone_id)
sessions     token, kind ('user'|'mod'), subject (user_id | moderator nomi), expires_at
draw_rounds  id, created_at, moderator, mode ('top_n'|'chance'),
             n, chance_pct, filters_json, pool_size, note (masalan "10:00 — katta raund")
draw_entries round_id, user_id, won (0/1)          -- kim qaysi raundda qatnashdi
audit_log    id, moderator, action, payload_json, created_at
```

Zonalar va kodlar `.env`da: `ZONE_CODES=1:4821,2:7350,...`
Moderatorlar ham `.env`da: `MODERATORS=aziz:parol1,dilnoza:parol2` (har bir harakat kim qilgani bilan yoziladi).

## 5. Tashrifchi oqimi

1. **Ro'yxatdan o'tish:** ism, familiya, telefon (+998 maska), PIN (2 marta). Telefon band bo'lsa → "Kirish" ga yo'naltiradi.
2. **Kirish:** telefon + PIN. Sessiya httpOnly cookie'da 24 soat — sahifani yopib ochsa ham kirib turadi; boshqa telefondan kirsa ham muhrlar joyida.
3. **Kod kiritish:** maydon kartasida 4 raqam → `POST /api/checkin` → muhr bazaga yoziladi.
4. **Pasport:** `n/9` muhr, pasport raqami, "Siz yutdingiz!" xabari (agar biror raundda yutgan bo'lsa).
5. **G'oliblar** bo'limi har 10 soniyada yangilanadi: oxirgi raundlar va g'oliblar (telefon yashirilgan: `+998 90 *** ** 45`).

## 6. Moderator paneli (`/mod`)

- **Hisobot:** jami ro'yxatdan o'tganlar, har maydon bo'yicha muhrlar soni, 9/9 to'plaganlar, soatlik grafik, o'tkazilgan raundlar soni.
- **Ishtirokchilar jadvali:** ism / telefon / pasport № bo'yicha qidiruv; ustunlar: muhrlar, **o'yinda qatnashgan soni**, **yutgan soni**, oxirgi yutuq vaqti.
- **Ishtirokchi kartasi:** PINni tiklash, qo'lda muhr qo'yish/olib tashlash, bloklash, raundlar tarixi.
- **O'yin paneli** (8-bo'lim).
- **CSV eksport:** ishtirokchilar, muhrlar, raundlar va g'oliblar.

## 7. API

**Tashrifchi**
- `POST /api/register` · `POST /api/login` · `POST /api/logout`
- `GET  /api/me` — profil, muhrlar, yutuqlar
- `POST /api/checkin {zone, code}`
- `GET  /api/winners` — oxirgi raundlar (ommaviy)

**Moderator** (`/api/mod/*`)
- `POST login` · `GET stats`
- `GET  users?q=&min_stamps=&won=` · `GET users/{id}`
- `POST users/{id}/reset-pin {pin}` · `POST users/{id}/stamp {zone, on}` · `POST users/{id}/block`
- `POST draw/preview {filters}` — maydonda nechta odam borligini ko'rsatadi
- `POST draw {mode, n | chance_pct, filters, note}` — raundni o'tkazadi
- `GET  draw/rounds` · `DELETE draw/rounds/{id}` (xato raundni bekor qilish, audit'ga yoziladi)
- `GET  export/{users|rounds}.csv`

## 8. Tasodifiy o'yin — kun davomida ko'p raund

### Ikki usul

**1-usul — "N ta g'olib" (`top_n`)**
Maydondan aynan N kishi teng ehtimol bilan tanlanadi (`secrets.SystemRandom().sample`).
Misol: 10:00 — 9/9 to'plagan 340 kishidan 5 ta g'olib.

**2-usul — "Ehtimollik" (`chance`)**
Maydondagi **har bir** ishtirokchi alohida "tanga tashlaydi": `p%` ehtimol bilan yutadi. Natijada 0 dan hammagacha yutishi mumkin.
Misol: 11:00 — 4 ta talaba keldi, moderator ularni tanlaydi, `p = 50%` → har biri yarim imkoniyat bilan o'ynaydi, hech kim kutmaydi.
Agar "kamida bitta g'olib bo'lsin" kerak bo'lsa — galochka bilan yoqiladi (hech kim yutmasa, raund qayta aylanadi).

> Kichik guruh uchun ikkala usul ham ishlaydi: 4 kishidan "N=2" desa — aniq 2 tasi yutadi; "50%" desa — o'rtacha 2 tasi, lekin 0 ham, 4 ham bo'lishi mumkin. Moderator vaziyatga qarab tanlaydi.

### O'yin maydoni (kim o'ynaydi) — qoidalar

| Qoida | Tavsif |
|---|---|
| **9/9 muhr** (doim) | 9 ta kodni kiritmaganlar o'yinga kirmaydi. Bloklanganlar ham kirmaydi |
| **Yutganlar qayta o'ynamaydi** (doim) | Bir marta yutgan hech qachon boshqa raundga kiritilmaydi (bekor qilingan raund hisobga olinmaydi) |
| **Faqat belgilanganlar** | Moderator jadvaldan ishtirokchilarni belgilaydi ("Hali o'ynamaganlar" yoki "hamma o'ynay oladiganlar" orasidan; «Hammasini tanlash» bor). Hech kim belgilanmasa raund boshlanmaydi — ogohlantirish chiqadi |

Raund raqami (1, 2, 3…) va vaqti (Toshkent) avtomatik qo'yiladi. Ishtirokchilar ro'yxatida holat bayrog'i: yashil 9/9, sariq 5–8, qizil 0–4 yoki bloklangan.

Raund oldidan `preview` maydon hajmini ko'rsatadi: "Maydonda 87 kishi".

### Ishtirok tarixi

Har raundda maydondagi **hamma** `draw_entries`ga yoziladi (`won` = 1 yoki 0). Shundan:
- kim necha marta o'yinda qatnashdi,
- kim necha marta yutdi,
- har raund: usul, filtrlar, maydon hajmi, g'oliblar, moderator.

### Jonli o'yin (taymer + "nomlar maydoni")

Moderator ishtirokchilarni belgilab, raundni sozlaydi va taymer qo'yadi (pauza / hozir boshlash / bekor qilish). Ro'yxat shu paytda muzlatiladi. Taymer tugagach `/live` da maydondagi hamma nomlar plitka bo'lib turadi va 20 s davomida birin-ketin o'chadi (boshida tez, oxirida sekin); oxirida g'oliblar qoladi va katta ekranda e'lon qilinadi. Har qanday N va "p%" usuli bilan ishlaydi. Kirgan foydalanuvchining o'z nomi «SIZ» belgisi bilan ajralib turadi. Server o'chishlarni ekranlarga atigi 2.5 s oldindan, g'oliblarni esa faqat oxirida beradi. Asosiy sahifada jonli banner.

## 9. Xavfsizlik (minimal)

- PIN — bcrypt hash. 4 xonali bo'lgani uchun asosiy himoya — **login rate limit**: bitta telefonga 5 xato → 10 daqiqa blok.
- Moderator paroli `.env`da, sessiya alohida cookie'da.
- HTTPS (Let's Encrypt), cookie `HttpOnly; Secure; SameSite=Lax`.
- Har bir moderator harakati (PIN tiklash, muhr, raund, bekor qilish) `audit_log`da.

## 10. Papka tuzilmasi

```
fan-festeval/
  app/
    main.py          # FastAPI ilova, statik fayllar
    db.py            # SQLite ulanish, sxema
    auth.py          # PIN, sessiya, rate limit
    routes_public.py # register, login, checkin, me, winners
    routes_mod.py    # stats, users, draw, export
    draw.py          # top_n va chance mantiqi, filtrlar
  public/
    index.html       # tashrifchi sahifasi (artifactdan)
    mod.html         # moderator paneli
    draw.html        # proyektor ekrani
  tests/test_draw.py # o'yin mantiqi testlari
  .env.example
  requirements.txt
  scripts/backup.sh  # har 5 daqiqada baza nusxasi
```

## 11. Deploy

- 1 ta VPS (2 vCPU / 2 GB), Ubuntu, Python 3.12, `uvicorn` + `systemd`, oldida nginx + certbot.
- Domen + QR kodlar (kirishda va har maydonda).
- Har 5 daqiqada `sqlite3 .backup` (cron), kun oxirida CSV eksport.
- Bog'da internet sust bo'lishi mumkin → rasmlarni siqish, xatoda "qayta urinish" tugmasi.

## 12. Ish tartibi

**19-oktabr**
1. Sxema, register / login / me / checkin, rate limit — ~3 soat
2. Artifact sahifasini API'ga ulash, ro'yxat/kirish formasi, localStorage'ni olib tashlash — ~2 soat
3. Moderator: login, hisobot, ishtirokchilar jadvali, PIN tiklash, qo'lda muhr — ~3 soat

**20-oktabr**
4. O'yin: `top_n`, `chance`, filtrlar, preview, tarix, bekor qilish + testlar — ~3 soat
5. Proyektor ekrani, CSV eksport — ~1.5 soat
6. VPS, domen, HTTPS, backup — ~2 soat
7. Yuklama testi (3 000 foydalanuvchi, 30 000 check-in) + real telefonlarda sinov — ~1.5 soat
8. Moderatorlar uchun 1 sahifalik yo'riqnoma

**21-oktabr** — 08:00 tekshiruv; kun davomida raundlar; 18:00 dan keyin yakuniy eksport.

## 13. Qolgan savollar

1. FastAPI yoki Flask — yakuniy tanlov? (tavsiya: FastAPI)
2. Server va domen bormi?
3. Sovg'a nomini raundga yozib qo'yamizmi (masalan "10:00 — ryukzak × 5")?
