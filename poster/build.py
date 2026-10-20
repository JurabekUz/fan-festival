"""A3 poster: FORMULA–2026 Fan festivali.

    python3 poster/build.py   -> poster/poster-{kirill,lotin}.{html,pdf,png}
PDF/PNG are printed with headless Chrome. QR code: poster/qr.svg (https://formula.academy.uz).
"""
import base64, pathlib, re, subprocess

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
SITE = "formula.academy.uz"

def b64(p):
    return base64.b64encode(pathlib.Path(p).read_bytes()).decode()

def fonts_css():
    css = (ROOT / "public/fonts/fonts.css").read_text()
    css = re.sub(r"url\(/fonts/([^)]+)\)",
                 lambda m: f"url(data:font/woff2;base64,{b64(ROOT / 'public/fonts' / m.group(1))})", css)
    return re.sub(r"font-weight: \d+;", "font-weight: 100 900;", css)

QR = (HERE / "qr.svg").read_text()
QR = re.sub(r'width="\d+" height="\d+"', 'viewBox="0 0 33 33" width="100%" height="100%"', QR)
QR = QR.replace('transform="scale(10)" ', "")
LOGO = b64(HERE / "logo.png")

T = {
 "kirill": dict(lang="uz-Cyrl",
   org1="Ўзбекистон Республикаси", org2="Фанлар академияси",
   kicker="Фанлар академиясининг анъанавий илмий-маърифий тадбири",
   title2="ФАН ФЕСТИВАЛИ",
   lead="Тошкент ботаника боғида Фанлар академиясининг илмий ташкилотлари тажриба, кузатув, квест ва викториналар билан фанни яқиндан кўрсатади.",
   meta=["21-октябр, 2026 · чоршанба", "10:00–18:00", "Тошкент ботаника боғи"],
   aw_k="9 та майдон · 1 кун", aw_h="Сизни нималар кутмоқда",
   aw_who="Мактаб ўқувчилари, талабалар, ўқитувчилар ва оилалар учун",
   acts=[("Жонли тажрибалар","Кимё, лазер ва плазма тажрибаларини ўз кўзингиз билан кўринг — олимлар ҳар бир ҳодисани тушунтиради."),
         ("Мастер-класслар","Амалий машғулотларда тажрибани ўз қўлингиз билан бажариб, натижасини ўзингиз олинг."),
         ("Квестлар","Боғ бўйлаб майдонма-майдон юриб, илмий топшириқларни ечинг ва кейинги босқичга ўтинг."),
         ("Викториналар","Билимингизни синанг: астрономия, математика, ботаника бўйича саволлар ва танловлар."),
         ("Кўргазмалар","Илмий муассасаларнинг ишланмалари, коллекциялари ва кашфиётлари бир жойда."),
         ("Олимлар билан мулоқот","Ҳақиқий тадқиқотчиларга саволингизни бевосита беринг, касб сирларини билиб олинг.")],
   fields=["Кимё","Астрономия","Математика","Ботаника","Антропология","Иммунология","Лазер технологиялари","Плазма физикаси"],
   game_k="Интерактив ўйин · совғалар", game_h="Илмий паспорт ўйини",
   steps=[("QR-кодни сканерланг","Сайтда телефон рақамингиз билан рўйхатдан ўтинг — бир дақиқа."),
          ("9 майдонни айланинг","Ҳар бир майдонда кодни олиб, паспортингизга муҳр босинг."),
          ("Совға ютинг!","9/9 муҳр тўплаганлар орасидан ғолиблар кун давомида тасодифий аниқланади.")],
   cta="Сканерланг ва<br>паспортингизни очинг",
   prog=[("10:00","Кутиб олиш"),("11:00","Очилиш"),("11:40","Интерактив майдонлар"),("17:00","Тақдирлаш")],
 ),
 "lotin": dict(lang="uz-Latn",
   org1="O‘zbekiston Respublikasi", org2="Fanlar akademiyasi",
   kicker="Fanlar akademiyasining an’anaviy ilmiy-ma’rifiy tadbiri",
   title2="FAN FESTIVALI",
   lead="Toshkent botanika bog‘ida Fanlar akademiyasining ilmiy tashkilotlari tajriba, kuzatuv, kvest va viktorinalar bilan fanni yaqindan ko‘rsatadi.",
   meta=["21-oktabr, 2026 · chorshanba", "10:00–18:00", "Toshkent botanika bog‘i"],
   aw_k="9 ta maydon · 1 kun", aw_h="Sizni nimalar kutmoqda",
   aw_who="Maktab o‘quvchilari, talabalar, o‘qituvchilar va oilalar uchun",
   acts=[("Jonli tajribalar","Kimyo, lazer va plazma tajribalarini o‘z ko‘zingiz bilan ko‘ring — olimlar har bir hodisani tushuntiradi."),
         ("Master-klasslar","Amaliy mashg‘ulotlarda tajribani o‘z qo‘lingiz bilan bajarib, natijasini o‘zingiz oling."),
         ("Kvestlar","Bog‘ bo‘ylab maydonma-maydon yurib, ilmiy topshiriqlarni yeching va keyingi bosqichga o‘ting."),
         ("Viktorinalar","Bilimingizni sinang: astronomiya, matematika, botanika bo‘yicha savollar va tanlovlar."),
         ("Ko‘rgazmalar","Ilmiy muassasalarning ishlanmalari, kolleksiyalari va kashfiyotlari bir joyda."),
         ("Olimlar bilan muloqot","Haqiqiy tadqiqotchilarga savolingizni bevosita bering, kasb sirlarini bilib oling.")],
   fields=["Kimyo","Astronomiya","Matematika","Botanika","Antropologiya","Immunologiya","Lazer texnologiyalari","Plazma fizikasi"],
   game_k="Interaktiv o‘yin · sovg‘alar", game_h="Ilmiy pasport o‘yini",
   steps=[("QR-kodni skanerlang","Saytda telefon raqamingiz bilan ro‘yxatdan o‘ting — bir daqiqa."),
          ("9 maydonni aylaning","Har bir maydonda kodni olib, pasportingizga muhr bosing."),
          ("Sovg‘a yuting!","9/9 muhr to‘plaganlar orasidan g‘oliblar kun davomida tasodifiy aniqlanadi.")],
   cta="Skanerlang va<br>pasportingizni oching",
   prog=[("10:00","Kutib olish"),("11:00","Ochilish"),("11:40","Interaktiv maydonlar"),("17:00","Taqdirlash")],
 ),
}

# Night-sky decoration: deterministic star field.
def stars():
    import random
    r = random.Random(2026)
    out = []
    for _ in range(150):
        x, y = r.uniform(0, 297), r.uniform(0, 260)
        s = r.choice([.25, .3, .35, .45, .6])
        o = r.uniform(.2, .8)
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{s}" fill="#fff" opacity="{o:.2f}"/>')
    return "".join(out)

ICONS = {
 "flask": '<path d="M9 3h6M10 3v6L4.5 18.5A2 2 0 0 0 6.2 21.5h11.6a2 2 0 0 0 1.7-3L14 9V3"/><path d="M7 15h10"/>',
 "hand":  '<path d="M18 11V6a2 2 0 0 0-4 0v5M14 10V4a2 2 0 0 0-4 0v6M10 10.5V6a2 2 0 0 0-4 0v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.9-6-2.4l-3.6-3.6a2 2 0 0 1 2.8-2.8L7 15"/>',
 "map":   '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14M15 6v14"/>',
 "quiz":  '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14"/><circle cx="12" cy="17.2" r=".6" fill="currentColor"/>',
 "eye":   '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
 "chat":  '<path d="M21 12a8 8 0 0 1-11.8 7L4 20.5l1.5-4.6A8 8 0 1 1 21 12z"/><path d="M8.5 11h.01M12 11h.01M15.5 11h.01" stroke-width="2.4"/>',
 "cal":   '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
 "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 "pin":   '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
}
ACT_IC = ["flask", "hand", "map", "quiz", "eye", "chat"]
ACT_COL = ["var(--amber)", "var(--teal)", "var(--lav)", "var(--coral)", "var(--teal)", "var(--amber)"]

def icon(k):
    return f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{ICONS[k]}</svg>'

CSS = """
@page{size:297mm 420mm;margin:0}
:root{--bg:#0b1130;--fg:#f2f4ff;--muted:#aab2dc;
 --amber:#f6b938;--teal:#4fd6c4;--lav:#a3acf5;--coral:#ff7a5c;--ink:#0c1230;
 --f-d:"Unbounded","Golos Text",sans-serif;--f-b:"Golos Text",sans-serif;--f-m:"JetBrains Mono",monospace}
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:297mm;height:420mm;background:var(--bg);color:var(--fg);font-family:var(--f-b);-webkit-print-color-adjust:exact;print-color-adjust:exact}
.poster{position:relative;width:297mm;height:420mm;overflow:hidden;
 background:radial-gradient(110mm 90mm at 88% 10%,rgba(163,172,245,.22),transparent 70%),
            radial-gradient(160mm 120mm at 0% 55%,rgba(79,214,196,.12),transparent 70%),
            linear-gradient(180deg,#0b1130 0%,#0e1640 55%,#0b1130 100%)}
.sky{position:absolute;inset:0;width:297mm;height:420mm}
.in{position:absolute;inset:14mm 16mm 0 16mm}
.top{display:flex;align-items:center;gap:4mm}
.tile{width:14mm;height:14mm;border-radius:3.5mm;background:#fff;display:grid;place-items:center}
.tile img{width:10.5mm}
.org{font-family:var(--f-m);font-size:9pt;letter-spacing:.14em;text-transform:uppercase;line-height:1.35;color:var(--muted)}
.org b{color:var(--fg);font-weight:600}
.kicker{margin-top:7mm;font-family:var(--f-m);font-size:9.5pt;letter-spacing:.16em;text-transform:uppercase;color:var(--amber)}
h1{font-family:var(--f-d);font-weight:800;line-height:1;margin-top:3mm}
h1 .f{display:block;font-size:26pt;color:var(--lav);letter-spacing:.03em}
h1 .f em{font-style:normal;color:var(--amber)}
h1 .t{display:block;font-size:50pt;margin-top:1.5mm;letter-spacing:-.01em;white-space:nowrap}
.lead{margin-top:5mm;max-width:225mm;font-size:14pt;line-height:1.42;color:#dfe3ff}
.meta{margin-top:5mm;display:flex;gap:7mm;font-size:11.5pt;color:var(--muted);font-weight:600}
.meta span{display:flex;align-items:center;gap:2mm;white-space:nowrap}
.meta svg{width:5mm;height:5mm;color:var(--amber)}

.aw{margin-top:7mm}
.aw-k{font-family:var(--f-m);font-size:10pt;letter-spacing:.18em;text-transform:uppercase;color:var(--teal)}
.aw-h{display:flex;align-items:baseline;justify-content:space-between;gap:6mm;margin-top:2mm}
.aw-h h2{font-family:var(--f-d);font-weight:800;font-size:31pt;line-height:1.05;white-space:nowrap}
.aw-h p{font-size:11.5pt;color:var(--muted);text-align:right;max-width:80mm;line-height:1.3}
.acts{margin-top:5mm;display:grid;grid-template-columns:repeat(3,1fr);gap:4mm}
.act{position:relative;border-radius:5mm;padding:6mm 5.5mm 6.5mm 7mm;background:linear-gradient(160deg,rgba(32,42,96,.95),rgba(20,28,68,.9));border:1px solid rgba(170,182,255,.2);overflow:hidden}
.act::before{content:"";position:absolute;left:0;top:0;bottom:0;width:1.6mm;background:var(--c)}
.act .ic{width:13mm;height:13mm;border-radius:3.5mm;display:grid;place-items:center;background:color-mix(in srgb,var(--c) 18%,transparent);color:var(--c)}
.act .ic svg{width:8mm;height:8mm}
.act b{display:block;font-family:var(--f-d);font-weight:700;font-size:15.5pt;margin-top:3.5mm;line-height:1.15}
.act span{display:block;font-size:11.5pt;color:#c9cff2;margin-top:2mm;line-height:1.38}
.chips{margin-top:4.5mm;display:flex;flex-wrap:wrap;gap:1.8mm}
.chip{font-size:10pt;font-weight:600;padding:1.4mm 3.2mm;border-radius:99mm;border:1px solid rgba(170,182,255,.3);color:#dfe3ff}

.bottom{position:absolute;left:0;right:0;bottom:0;height:138mm;background:#f6f7fd;color:var(--ink);
 border-radius:10mm 10mm 0 0;padding:11mm 16mm 0;display:grid;grid-template-columns:1fr 104mm;gap:9mm}
.game-k{font-family:var(--f-m);font-size:10pt;letter-spacing:.18em;text-transform:uppercase;color:#a96a00;font-weight:700}
.game h3{white-space:nowrap;font-family:var(--f-d);font-weight:800;font-size:25pt;margin-top:2.5mm;line-height:1.05}
.steps{list-style:none;margin-top:6mm;display:grid;gap:5mm}
.steps li{display:grid;grid-template-columns:15mm 1fr;gap:5mm;align-items:start}
.steps .n{width:15mm;height:15mm;border-radius:50%;background:var(--c);color:var(--ink);font-family:var(--f-d);font-weight:800;font-size:18pt;display:grid;place-items:center}
.steps b{display:block;font-family:var(--f-d);font-size:16pt;font-weight:700;line-height:1.2;margin-top:.5mm}
.steps span{display:block;font-size:12.5pt;color:#454d78;margin-top:1.2mm;line-height:1.38}
.prog{margin-top:6mm;display:flex;border-top:1px dashed rgba(30,40,100,.2);padding-top:3.5mm}
.prog div{flex:1}
.prog i{font-style:normal;display:block;font-family:var(--f-m);font-weight:700;font-size:10pt;color:#4651c4}
.prog span{display:block;font-size:9.5pt;color:#545c86;margin-top:.5mm;line-height:1.25;padding-right:2mm}
.qrbox{background:var(--ink);color:var(--fg);border-radius:8mm;padding:7mm;align-self:start;text-align:center;margin-top:-16mm;box-shadow:0 4mm 14mm rgba(12,18,48,.4);border:1.2mm solid var(--amber)}
.qr{background:#fff;border-radius:4mm;padding:5mm;width:84mm;height:84mm;margin:0 auto}
.qr svg{display:block}
.cta{font-family:var(--f-d);font-weight:700;font-size:14pt;line-height:1.25;margin-top:5mm}
.url{margin-top:4mm;font-family:var(--f-m);font-weight:800;font-size:18pt;color:var(--amber)}
"""

def page(t):
    acts = "".join(
        f'<div class="act" style="--c:{ACT_COL[i]}"><div class="ic">{icon(ACT_IC[i])}</div><b>{a}</b><span>{s}</span></div>'
        for i, (a, s) in enumerate(t["acts"]))
    chips = "".join(f'<span class="chip">{f}</span>' for f in t["fields"])
    meta = "".join(f"<span>{icon(k)}{v}</span>" for k, v in zip(["cal", "clock", "pin"], t["meta"]))
    cols = ["var(--amber)", "var(--teal)", "var(--lav)"]
    steps = "".join(
        f'<li style="--c:{cols[i]}"><span class="n">{i+1}</span><div><b>{a}</b><span>{s}</span></div></li>'
        for i, (a, s) in enumerate(t["steps"]))
    prog = "".join(f"<div><i>{a}</i><span>{b}</span></div>" for a, b in t["prog"])
    return f"""<!doctype html><html lang="{t['lang']}"><head><meta charset="utf-8">
<title>FORMULA–2026 poster</title><style>{fonts_css()}{CSS}</style></head><body>
<div class="poster">
 <svg class="sky" viewBox="0 0 297 420" preserveAspectRatio="none" aria-hidden="true">
  {stars()}
  <g fill="none" stroke="rgba(170,182,255,.28)" stroke-width=".35">
   <ellipse cx="248" cy="52" rx="52" ry="17" transform="rotate(-24 248 52)"/>
   <ellipse cx="248" cy="52" rx="52" ry="17" transform="rotate(36 248 52)"/>
   <ellipse cx="248" cy="52" rx="52" ry="17" transform="rotate(96 248 52)"/>
  </g>
  <circle cx="248" cy="52" r="10" fill="#f6b938" opacity=".15"/><circle cx="248" cy="52" r="6.5" fill="#f6b938"/>
  <circle cx="290" cy="38" r="2.4" fill="#4fd6c4"/><circle cx="226" cy="96" r="2" fill="#ff7a5c"/><circle cx="232" cy="12" r="1.8" fill="#a3acf5"/>
 </svg>
 <div class="in">
  <div class="top"><div class="tile"><img src="data:image/png;base64,{LOGO}" alt=""></div>
   <div class="org"><b>{t['org1']}</b><br>{t['org2']}</div></div>
  <div class="kicker">{t['kicker']}</div>
  <h1><span class="f">FORMULA<em>–</em>2026</span><span class="t">{t['title2']}</span></h1>
  <p class="lead">{t['lead']}</p>
  <div class="meta">{meta}</div>
  <section class="aw">
   <div class="aw-k">{t['aw_k']}</div>
   <div class="aw-h"><h2>{t['aw_h']}</h2><p>{t['aw_who']}</p></div>
   <div class="acts">{acts}</div>
   <div class="chips">{chips}</div>
  </section>
 </div>
 <div class="bottom">
  <div class="game"><div class="game-k">{t['game_k']}</div><h3>{t['game_h']}</h3><ol class="steps">{steps}</ol>
   <div class="prog">{prog}</div></div>
  <div class="qrbox"><div class="qr">{QR}</div><div class="cta">{t['cta']}</div><div class="url">{SITE}</div></div>
 </div>
</div></body></html>"""

if __name__ == "__main__":
    for k, t in T.items():
        html = HERE / f"poster-{k}.html"
        html.write_text(page(t))
        for args in ([f"--print-to-pdf={HERE}/poster-{k}.pdf", "--no-pdf-header-footer"],
                     [f"--screenshot={HERE}/poster-{k}.png", "--window-size=1123,1587"]):
            subprocess.run(["google-chrome", "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            "--force-device-scale-factor=1", *args, html.as_uri()],
                           check=True, capture_output=True)
        print("ok", k)
