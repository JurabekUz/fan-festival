import asyncio
import fcntl
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, live
from .routes_mod import router as mod_router
from .routes_public import router as public_router

PUBLIC = Path(__file__).resolve().parent.parent / "public"
log = logging.getLogger("formula")


def check_config():
    """Noto'g'ri .env bilan ishga tushmaslik uchun."""
    missing = [z for z in range(1, config.ZONE_COUNT + 1) if not config.ZONE_CODES.get(z)]
    if missing:
        raise RuntimeError(f".env: ZONE_CODES da maydon kodlari yo'q: {missing}")
    if not config.MODERATORS:
        raise RuntimeError(".env: MODERATORS bo'sh — kamida bitta moderator kerak")
    weak = [m for m, pw in config.MODERATORS.items() if len(pw) < 8 or pw.startswith("ozgartiring")]
    if weak:
        log.warning("Zaif yoki namunaviy moderator paroli: %s — serverda almashtiring!", ", ".join(weak))
    if not config.COOKIE_SECURE:
        log.warning("COOKIE_SECURE=false — faqat lokal sinov uchun, serverda true bo'lsin")


def single_process_lock():
    """Jonli o'yin holati xotirada — ikkinchi jarayon (--workers 2+) jim ishlab, ekranlarni
    sakratib qo'ymasin: qulfni ololmasa ishga tushmaydi."""
    path = Path(config.DB_PATH).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        raise RuntimeError("Ilova allaqachon boshqa jarayonda ishlayapti — faqat --workers 1 bilan ishga tushiring")
    return fh


@asynccontextmanager
async def lifespan(app):
    check_config()
    lock = single_process_lock()
    db.init()
    live.reset_cache()
    live.load()

    async def ticker():
        while True:
            try:
                await asyncio.to_thread(live.tick)
            except Exception:  # fon vazifa to'xtab qolmasin, lekin xato jurnalga yozilsin
                log.exception("live.tick xatosi")
            await asyncio.sleep(0.5)

    task = asyncio.create_task(ticker())
    yield
    task.cancel()
    lock.close()


app = FastAPI(title="FORMULA-2026", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.middleware("http")
async def no_cache_html(request, call_next):
    resp = await call_next(request)
    if resp.headers.get("content-type", "").startswith("text/html") or request.url.path.startswith("/api"):
        resp.headers["Cache-Control"] = "no-cache"
    elif request.url.path.startswith("/fonts/"):  # shriftlar o'zgarmaydi — qayta yuklanmasin
        resp.headers["Cache-Control"] = "public, max-age=31536000"
    return resp


app.include_router(public_router)
app.include_router(mod_router)


@app.get("/mod")
def mod_page():
    return FileResponse(PUBLIC / "mod.html")


@app.get("/live-demo")
def live_demo_page():
    return FileResponse(PUBLIC / "live-demo.html")


@app.get("/live")
@app.get("/mod/draw")  # eski manzil
def live_page():
    return FileResponse(PUBLIC / "live.html")


app.mount("/", StaticFiles(directory=PUBLIC, html=True), name="public")
