"""Kedai Kopi Senja — aplikasi pemesanan web + panel admin.

Entri hackathon TestSprite Season 4: setiap pull request diuji otomatis
oleh TestSprite terhadap URL live aplikasi ini.

Jalankan lokal:
    pip install -r requirements.txt
    python app.py            # http://127.0.0.1:5000

Produksi (contoh):
    gunicorn app:app --bind 0.0.0.0:$PORT
"""

import hashlib
import os
import sys
import uuid
from functools import wraps
from urllib.parse import urlencode

from flask import Flask, abort, redirect, request, session, url_for
from markupsafe import escape

import db
import rate_limit

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-senja-ganti-di-produksi")
# Tanpa default yang diketahui umum: kosong = login admin nonaktif.
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# Tautan "Admin" disembunyikan dari navigasi publik: URL panel admin
# tidak perlu diiklankan ke pengunjung. Ini hygiene, BUKAN security —
# rate limit di admin_login_post yang menahan brute force. Akses tetap
# lewat URL langsung (/admin).
# Untuk demo/hackathon ketika panel perlu ditunjukkan, set
# SHOW_ADMIN_LINK=1 agar tautannya muncul lagi di navigasi.
SHOW_ADMIN_LINK = os.environ.get("SHOW_ADMIN_LINK", "") == "1"

db.init_db()

KATEGORI_LABEL = {"kopi": "Kopi", "nonkopi": "Non-Kopi", "snack": "Snack"}


def admin_nav():
    """Tautan Admin di navigasi.

    Sengaja fungsi, bukan konstanta modul: url_for() butuh application
    context, jadi tidak boleh dipanggil di level modul (crash saat boot
    kalau SHOW_ADMIN_LINK=1).
    """
    if not SHOW_ADMIN_LINK:
        return ""
    return f"<a href='{url_for('admin_login')}'>Admin</a>"


# ---------------------------------------------------------------- helpers
def rupiah(n):
    return "Rp " + f"{int(n):,}".replace(",", ".")


def visitor_id():
    if "vid" not in session:
        session["vid"] = uuid.uuid4().hex
    return session["vid"]


def web_user_id():
    """ID pelanggan integer (stabil per browser) untuk lapisan db."""
    h = hashlib.sha256(visitor_id().encode()).hexdigest()[:12]
    return int(h, 16)


def admin_required(f):
    @wraps(f)
    def _w(*a, **kw):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return f(*a, **kw)

    return _w


# ---------------------------------------------------------------- layout
CSS = """
:root{
--paper:#FAF5EB; --card:#FFFFFF; --ink:#2B1D12; --muted:#8C7355;
--line:#E7DCC6; --accent:#B4531F; --accent-dark:#8F3E12; --accent-soft:#F7E8D8;
--danger:#B3261E; --danger-soft:#F9DEDC; --ok:#3F6B2A; --ok-soft:#E2EDD8;
--info:#2A5B8C; --info-soft:#DCE9F5; --warn:#8A5A00; --warn-soft:#F7EAC8;
--teal:#1F6E9E; --teal-soft:#E4F0F7;
}
*{box-sizing:border-box;margin:0;padding:0}
::selection{background:var(--accent);color:#fff}
body{background:var(--paper);color:var(--ink);font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:var(--accent)}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
header.top{background:var(--paper);border-bottom:1px solid var(--line);border-top:4px solid var(--accent);position:sticky;top:0;z-index:10}
header.top .wrap{display:flex;align-items:center;justify-content:space-between;padding:14px 20px}
.brand{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--ink);font-family:'Fraunces',Georgia,'Times New Roman',serif;font-weight:700;font-size:1.3rem}
.brand svg{flex:none}
.brand em{font-style:normal;color:var(--accent)}
nav.links a{margin-left:22px;text-decoration:none;font-weight:600;font-size:.95rem;color:var(--ink)}
nav.links a:hover{color:var(--accent);text-decoration:underline;text-underline-offset:4px}
.hero{display:flex;gap:32px;align-items:center;padding:64px 0 10px}
.hero-text{flex:1;min-width:0}
.eyebrow{text-transform:uppercase;letter-spacing:2.5px;font-size:.75rem;font-weight:700;color:var(--accent);margin-bottom:14px}
.hero h1{font-family:'Fraunces',Georgia,'Times New Roman',serif;font-weight:700;font-size:clamp(2.2rem,5vw,3.4rem);line-height:1.08;margin-bottom:16px}
.hero h1 em{font-style:italic;color:var(--accent)}
.lede{color:var(--muted);font-size:1.08rem;max-width:34rem;margin-bottom:26px}
.hero-cta{display:flex;gap:12px;flex-wrap:wrap}
.hero-art{flex:none}
@media(max-width:760px){.hero{padding:42px 0 8px}.hero-art{display:none}}
.grid{display:grid;grid-template-columns:1fr 330px;gap:38px;padding:34px 0 70px;align-items:start}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.menu-cat{margin-bottom:6px}
.menu-cat>h2{font-family:'Fraunces',Georgia,'Times New Roman',serif;font-size:1.65rem;font-weight:700;margin:32px 0 4px;display:flex;align-items:center;gap:14px}
.menu-cat>h2::after{content:"";flex:1;border-bottom:1px solid var(--line)}
.menu-list{list-style:none}
.menu-item{padding:18px 4px;border-bottom:1px solid var(--line)}
.mi-head{display:flex;align-items:baseline;gap:12px}
.mi-head h3{font-family:'Fraunces',Georgia,'Times New Roman',serif;font-size:1.18rem;font-weight:700}
.dots{flex:1;border-bottom:2px dotted #D9C8A6;transform:translateY(-5px);min-width:24px}
.price{font-family:'Fraunces',Georgia,'Times New Roman',serif;font-weight:700;font-size:1.12rem;color:var(--accent-dark);white-space:nowrap}
.desc{color:var(--muted);font-size:.93rem;margin:4px 0 10px;max-width:36rem}
.qtyform{display:flex;gap:10px;align-items:center}
.qtyform label{font-size:.85rem;color:var(--muted);font-weight:600}
.qtyform input[type=number]{width:64px;padding:8px 10px;border-radius:8px;border:1px solid var(--line);background:#fff;color:var(--ink);font-size:.95rem;font-family:inherit}
button,.btn{background:var(--accent);color:#fff;border:0;border-radius:10px;padding:11px 20px;font-weight:700;cursor:pointer;font-size:.95rem;text-decoration:none;display:inline-block;font-family:inherit}
button:hover,.btn:hover{background:var(--accent-dark)}
button.ghost,.btn.ghost{background:transparent;color:var(--accent);border:1.5px solid var(--accent)}
button.ghost:hover,.btn.ghost:hover{background:var(--accent-soft)}
button.danger{background:var(--danger)}
button.small{padding:7px 12px;font-size:.85rem;border-radius:8px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;position:sticky;top:100px;box-shadow:0 8px 24px rgba(43,29,18,.06)}
.panel h2{font-family:'Fraunces',Georgia,'Times New Roman',serif;font-size:1.3rem;margin-bottom:14px}
.cartline{display:flex;justify-content:space-between;gap:8px;padding:9px 0;border-bottom:1px dashed var(--line);font-size:.92rem;align-items:center}
.cartline .n{flex:1}
.total{display:flex;justify-content:space-between;font-weight:700;font-size:1.15rem;margin:14px 0;font-family:'Fraunces',Georgia,'Times New Roman',serif}
.empty{color:var(--muted);font-style:italic}
h2.sec{font-family:'Fraunces',Georgia,'Times New Roman',serif;font-size:1.7rem;margin:36px 0 16px}
form.stack{display:flex;flex-direction:column;gap:14px;max-width:520px}
form.stack>label{font-weight:600;font-size:.92rem;display:flex;flex-direction:column;gap:6px}
input[type=text],input[type=password],input[type=number],select,textarea{padding:11px 13px;border-radius:10px;border:1px solid var(--line);background:#fff;color:var(--ink);font-size:1rem;width:100%;font-family:inherit}
input:focus,select:focus{outline:2px solid var(--accent);outline-offset:1px;border-color:var(--accent)}
fieldset{border:1px solid var(--line);border-radius:10px;padding:14px}
legend{padding:0 8px;font-weight:700}
.radio{display:flex;gap:20px;flex-wrap:wrap}
.radio label{display:flex;flex-direction:row;align-items:center;gap:8px;font-weight:500}
.notice{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:10px;padding:14px 18px;margin:18px 0}
.error{background:var(--danger-soft);border:1px solid var(--danger);color:#7a1a14;border-radius:10px;padding:12px 16px;margin:16px 0}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:.92rem;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:11px 10px;border-bottom:1px solid var(--line);vertical-align:middle}
th{background:#F4EBDA;text-transform:uppercase;font-size:.75rem;letter-spacing:1px}
tr:last-child td{border-bottom:0}
.badge{display:inline-block;padding:4px 12px;border-radius:20px;font-size:.8rem;font-weight:700;white-space:nowrap}
.badge.baru{background:var(--warn-soft);color:var(--warn)}
.badge.dimasak{background:var(--info-soft);color:var(--info)}
.badge.siap{background:var(--teal-soft);color:var(--teal)}
.badge.selesai{background:var(--ok-soft);color:var(--ok)}
.badge.batal{background:var(--danger-soft);color:var(--danger)}
.kode{font-family:ui-monospace,'SF Mono',Menlo,monospace;font-size:1.5rem;font-weight:700;color:var(--accent-dark);letter-spacing:1px}
.receipt{background:var(--card);border:1px solid var(--line);border-top:4px solid var(--accent);border-radius:14px;padding:28px;max-width:580px;margin:32px auto;box-shadow:0 8px 24px rgba(43,29,18,.06)}
.receipt .thanks{font-family:'Fraunces',Georgia,'Times New Roman',serif;font-size:1.45rem;margin-bottom:6px}
footer.site{background:#211510;color:#CBB99E;margin-top:60px}
footer.site .wrap{padding:28px 20px;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;font-size:.88rem}
footer.site strong{color:#F5EAD9;font-family:'Fraunces',Georgia,'Times New Roman',serif;font-size:1.02rem}
footer.site em{color:#8f7c5f}
.inline{display:inline}
.mt{margin-top:16px}
code{background:#F1E7D2;padding:2px 6px;border-radius:6px;font-size:.88em}
/* tabel admin yang rapi */
.table-wrap{overflow-x:auto;margin:16px 0;border:1px solid var(--line);border-radius:12px;background:var(--card);box-shadow:0 8px 24px rgba(43,29,18,.05)}
.table-wrap table{margin:0;border:0;border-radius:0;box-shadow:none}
table.admin{min-width:760px;table-layout:fixed}
table.admin th,table.admin td{padding:13px 14px;overflow-wrap:break-word}
table.admin tbody tr:nth-child(even){background:#FCF7EC}
table.admin .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
table.admin .nowrap{white-space:nowrap}
table.admin .nowrap .sub{white-space:normal}
table.admin .inline{display:inline-flex;gap:8px;align-items:center;flex-wrap:wrap}
table.admin select{max-width:100%;padding:8px 10px;font-size:.88rem}
table.admin input[type=number]{width:100%;min-width:80px;padding:8px 10px;font-size:.88rem}
/* lebar kolom eksplisit: pesanan & menu proporsional, Aksi tidak memonopoli */
table.admin.orders th:nth-child(1){width:26%}
table.admin.orders th:nth-child(2){width:15%}
table.admin.orders th:nth-child(3){width:13%}
table.admin.orders th:nth-child(4){width:19%}
table.admin.orders td:nth-child(4) .badge{white-space:normal}
table.admin.orders th:nth-child(5){width:27%}
table.admin.menus th:nth-child(1){width:38%}
table.admin.menus th:nth-child(2){width:14%}
table.admin.menus th:nth-child(3){width:12%}
table.admin.menus th:nth-child(4){width:36%}
.stacked{display:flex;flex-direction:column;gap:2px}
.stacked .sub{color:var(--muted);font-size:.82rem}
"""



# Siluet serigala melolong (CC0, dikurasi dari Pixabay via svgsilh.com) —
# dipakai di mark header dan hero art. Koordinat asli 10650x12800, sudah
# di-flip oleh group transform di bawah.
WOLF_D = (
    "M8975 12767 c-20 -20 -39 -53 -48 -87 -9 -30 -26 -89 -37 -130 -12 -41 -43 -115 -70 -165 "
    "-26 -49 -60 -126 -75 -170 -31 -94 -123 -272 -202 -394 -106 -163 -236 -304 -428 -463 "
    "-174 -145 -239 -248 -334 -529 l-53 -155 -79 -70 c-85 -74 -246 -183 -409 -278 -123 -71 "
    "-143 -96 -137 -178 5 -92 63 -195 166 -299 67 -67 104 -94 162 -123 42 -20 82 -36 90 -36 "
    "8 0 29 -9 47 -20 37 -23 42 -52 16 -102 -24 -47 -33 -83 -44 -183 -9 -80 -18 -106 -81 -238 "
    "-90 -189 -119 -267 -119 -318 0 -60 -22 -95 -67 -106 -33 -8 -39 -14 -60 -67 -14 -36 -41 "
    "-78 -72 -111 -52 -55 -70 -88 -90 -170 -19 -77 -61 -133 -201 -269 -147 -141 -258 -220 "
    "-435 -306 -222 -109 -559 -229 -711 -256 -114 -20 -379 -88 -469 -120 -38 -14 -135 -43 "
    "-215 -65 -80 -21 -185 -52 -235 -68 -49 -17 -122 -35 -161 -41 -40 -5 -118 -25 -175 -43 "
    "-57 -19 -158 -44 -224 -57 -181 -34 -268 -56 -364 -94 -47 -19 -116 -42 -153 -50 -96 -22 "
    "-180 -64 -278 -137 -47 -35 -115 -81 -152 -103 -64 -37 -100 -65 -305 -236 -49 -41 -118 "
    "-96 -154 -121 -42 -30 -79 -67 -104 -105 -21 -32 -86 -108 -145 -169 -138 -144 -191 -220 "
    "-257 -368 -30 -67 -79 -163 -109 -213 -46 -78 -55 -101 -60 -155 -7 -83 -18 -134 -48 -213 "
    "-14 -35 -34 -100 -46 -143 -13 -46 -44 -115 -74 -168 -29 -49 -65 -112 -81 -139 -15 -27 "
    "-47 -67 -70 -90 -24 -22 -63 -72 -88 -109 -39 -57 -115 -155 -345 -445 -19 -24 -55 -56 "
    "-80 -72 -68 -42 -196 -175 -262 -271 -67 -97 -104 -133 -170 -162 -68 -30 -98 -54 -105 -86 "
    "-7 -35 -39 -65 -130 -123 -59 -38 -75 -53 -99 -103 -38 -75 -124 -167 -180 -194 -34 -15 "
    "-47 -29 -56 -55 -6 -19 -30 -63 -52 -98 -70 -107 -149 -269 -160 -327 -6 -31 -15 -61 -20 "
    "-67 -5 -7 -12 -36 -15 -65 -3 -30 -19 -81 -35 -114 -36 -76 -35 -115 2 -193 25 -53 36 -65 "
    "72 -81 24 -10 68 -38 98 -63 66 -54 103 -74 153 -83 33 -6 40 -4 66 24 48 52 100 38 131 -35 "
    "25 -58 75 -264 94 -389 44 -292 61 -382 93 -505 51 -192 60 -249 77 -485 8 -116 20 -224 26 "
    "-240 6 -17 28 -50 49 -75 20 -25 49 -65 63 -90 15 -25 48 -66 75 -92 l48 -47 141 34 c77 18 "
    "157 41 177 51 34 16 37 16 84 -4 86 -36 130 -37 198 -2 46 23 73 30 117 30 31 0 59 4 62 9 "
    "17 26 -98 111 -381 281 -59 36 -131 88 -159 115 -43 42 -53 60 -67 115 -18 72 -81 592 -98 "
    "806 l-11 135 26 53 c45 91 415 460 561 559 56 38 242 127 265 127 6 0 53 31 106 68 52 37 "
    "163 105 247 151 83 46 220 122 304 168 84 46 210 106 280 132 231 88 404 171 567 275 43 27 "
    "123 66 178 87 121 46 178 78 243 139 75 69 105 90 131 90 33 0 46 -32 47 -114 0 -131 -98 "
    "-361 -274 -643 -35 -57 -86 -142 -114 -190 -32 -56 -74 -111 -117 -153 -86 -83 -110 -136 "
    "-116 -251 -3 -68 -1 -93 13 -120 10 -19 109 -126 219 -239 263 -267 329 -360 347 -487 11 "
    "-77 42 -140 103 -212 64 -73 92 -125 109 -197 17 -77 59 -149 99 -174 36 -22 47 -24 273 -50 "
    "96 -11 196 -28 230 -40 67 -23 107 -19 129 12 13 19 22 20 76 15 55 -6 62 -5 81 17 23 26 49 "
    "39 117 56 23 6 42 16 42 23 0 25 -168 170 -240 207 -22 11 -90 29 -152 40 -148 25 -177 34 "
    "-227 71 -130 94 -371 408 -440 572 -17 42 -52 120 -77 174 -56 120 -62 169 -39 300 34 190 "
    "82 281 225 424 94 95 176 151 500 344 292 173 341 207 395 271 26 30 51 54 57 54 18 0 159 "
    "86 219 134 34 26 71 68 90 101 19 32 63 94 98 139 133 168 218 328 250 471 28 130 73 251 "
    "91 248 8 -1 27 -5 42 -9 23 -5 35 2 83 47 57 54 70 55 77 9 2 -16 14 -30 32 -39 37 -17 132 "
    "-19 148 -3 7 7 29 12 49 12 40 0 54 11 64 52 8 32 39 63 55 53 5 -3 17 -22 25 -41 16 -39 28 "
    "-42 48 -13 15 20 16 20 41 3 22 -14 40 -16 94 -10 37 3 79 9 93 12 20 4 34 -2 64 -30 34 -32 "
    "43 -36 93 -36 39 0 80 10 144 35 108 43 209 68 242 59 14 -3 32 -14 41 -24 14 -15 14 -22 5 "
    "-40 -7 -12 -10 -36 -7 -54 7 -49 63 -185 99 -240 17 -28 58 -100 89 -160 32 -60 69 -120 82 "
    "-135 34 -35 130 -230 156 -315 12 -38 30 -121 41 -185 28 -160 45 -208 80 -226 30 -16 150 "
    "-185 150 -212 0 -9 13 -40 30 -69 16 -29 33 -71 36 -94 4 -23 25 -69 47 -103 22 -34 46 -82 "
    "54 -107 7 -25 33 -70 56 -100 61 -79 106 -156 185 -317 63 -129 79 -171 111 -288 6 -22 35 "
    "-83 66 -135 77 -132 139 -256 159 -318 21 -62 57 -93 140 -123 148 -52 500 -85 811 -76 164 "
    "4 198 8 248 27 58 22 59 22 120 4 43 -12 97 -18 177 -18 125 -1 180 12 205 47 18 26 19 47 3 "
    "47 -7 0 -74 45 -148 101 -125 93 -177 123 -385 219 -56 27 -91 54 -176 139 -157 156 -189 "
    "231 -209 488 -12 151 -24 221 -50 304 -39 121 -63 308 -80 634 -15 281 -33 453 -85 817 -52 "
    "367 -71 681 -62 1013 13 448 67 596 303 830 132 130 186 205 205 281 6 27 27 76 45 109 24 45 "
    "40 97 63 208 19 98 38 162 55 191 16 28 28 66 32 111 5 50 13 74 32 97 22 26 26 44 33 136 11 "
    "134 42 300 75 394 29 87 43 245 44 508 0 96 5 268 11 381 11 195 10 211 -11 318 -18 94 -20 "
    "130 -15 220 7 98 5 111 -14 149 -14 27 -25 76 -32 144 -13 129 -44 273 -76 358 -22 59 -26 "
    "88 -34 295 -10 244 -12 260 -54 453 -26 124 -42 171 -109 333 -65 155 -66 254 -7 502 67 280 "
    "148 531 229 712 27 61 55 128 62 149 17 52 7 171 -18 230 -23 51 -75 90 -107 80 -36 -12 -98 "
    "-61 -218 -172 -64 -60 -130 -115 -147 -122 -86 -36 -113 21 -155 333 -19 143 -52 251 -102 "
    "336 -49 83 -164 206 -267 283 -83 62 -205 128 -239 128 -11 0 -34 -15 -52 -33z"
)

# Mark header: matahari senja + garis horizon + serigala (varian C3), viewBox 100x100.
# Serigala berdiri di garis y=84 (scale 0.058 -> tinggi 74.24, mulai y=9.76).
BRAND_MARK = f"""<svg width="36" height="36" viewBox="0 0 100 100" aria-hidden="true">
<circle cx="50" cy="42" r="30" fill="#E8A94E"/>
<g stroke="#B4531F" stroke-linecap="round"><line x1="14" y1="84" x2="86" y2="84" stroke-width="3.5"/><line x1="26" y1="91" x2="74" y2="91" stroke-width="3" opacity=".55"/></g>
<g transform="translate(19.1 9.8) scale(0.058)"><g transform="translate(0,1280) scale(0.1,-0.1)"><path fill="#3B2417" d="{WOLF_D}"/></g></g>
</svg>"""

# Hero art homepage: motif senja yang sama, skala besar, viewBox 220x220.
HERO_ART = f"""<svg width="200" height="200" viewBox="0 0 220 220" fill="none" aria-hidden="true">
<circle cx="110" cy="78" r="52" fill="#F3D9A4"/>
<g stroke="#B4531F" stroke-width="5" stroke-linecap="round"><line x1="30" y1="176" x2="190" y2="176"/><line x1="56" y1="192" x2="164" y2="192"/></g>
<g transform="translate(49 29) scale(0.115)"><g transform="translate(0,1280) scale(0.1,-0.1)"><path fill="#3B2417" d="{WOLF_D}"/></g></g>
</svg>"""


def layout(title, body):
    return f"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} — Kedai Kopi Senja</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;0,9..144,700;1,9..144,500&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<header class="top"><div class="wrap">
<a class="brand" href="{url_for('index')}">
{BRAND_MARK}
<span>Kedai Kopi <em>Senja</em></span></a>
<nav class="links">
<a href="{url_for('index')}">Menu</a>
<a href="{url_for('cek_status')}">Cek Status</a>
{admin_nav()}
</nav>
</div></header>
<div class="wrap">{body}</div>
<footer class="site"><div class="wrap">
<div><strong>Kedai Kopi Senja</strong><br>Demo hackathon TestSprite Season 4</div>
<div>Dibangun oleh Suprapto &middot; JIJNASA<br><em>Keingintahuan yang membangun.</em></div>
</div></footer>
</body></html>"""


# ---------------------------------------------------------------- pelanggan
@app.get("/healthz")
def healthz():
    return "ok", 200


@app.get("/")
def index():
    uid = web_user_id()
    menu = db.menu_aktif()
    cart = db.cart_items(uid)
    by_cat = {}
    for m in menu:
        by_cat.setdefault(m["kategori"], []).append(m)

    sections = []
    for kat in ["kopi", "nonkopi", "snack"]:
        items = by_cat.get(kat, [])
        if not items:
            continue
        lis = []
        for m in items:
            lis.append(f"""
<li class="menu-item">
<div class="mi-head">
<h3>{escape(m['nama'])}</h3>
<span class="dots" aria-hidden="true"></span>
<span class="price">{rupiah(m['harga'])}</span>
</div>
<p class="desc">{escape(m['deskripsi'] or '') or '<i>Belum ada deskripsi.</i>'}</p>
<form class="qtyform" method="post" action="{url_for('cart_add')}">
<input type="hidden" name="menu_id" value="{m['id']}">
<label>Jumlah <input type="number" name="qty" value="1" min="1" max="20" aria-label="Jumlah {escape(m['nama'])}"></label>
<button type="submit">Tambah</button>
</form>
</li>""")
        sections.append(
            f"<section class='menu-cat'><h2>{KATEGORI_LABEL.get(kat, kat)}</h2>"
            f"<ul class='menu-list'>{''.join(lis)}</ul></section>"
        )

    if cart:
        lines = []
        for r in cart:
            lines.append(f"""
<div class="cartline">
<span class="n">{escape(r['nama'])} &times; {r['qty']}</span>
<span>{rupiah(r['harga'] * r['qty'])}</span>
<form class="inline" method="post" action="{url_for('cart_remove')}">
<input type="hidden" name="menu_id" value="{r['menu_id']}">
<button class="small ghost" type="submit" aria-label="Hapus {escape(r['nama'])}">hapus</button>
</form>
</div>""")
        cart_html = (
            "".join(lines)
            + f"<div class='total'><span>Total</span><span>{rupiah(db.cart_total(cart))}</span></div>"
            + f"<a class='btn' href='{url_for('checkout')}'>Lanjut ke Checkout</a>"
        )
    else:
        cart_html = "<p class='empty'>Keranjang masih kosong. Pilih menu favoritmu di samping.</p>"

    body = f"""
<div class="hero">
<div class="hero-text">
<p class="eyebrow">Kedai kopi &middot; pesan dari browser</p>
<h1>Senja diseduh,<br>pesanan <em>tercatat.</em></h1>
<p class="lede">Pilih menu, checkout, terima kode pesanan &mdash; lalu pantau statusnya sampai siap diambil. Tanpa antre, tanpa install aplikasi.</p>
<p class="hero-cta"><a class="btn" href="#menu">Lihat menu</a> <a class="btn ghost" href="{url_for('cek_status')}">Cek status pesanan</a></p>
</div>
<div class="hero-art" aria-hidden="true">
{HERO_ART}
</div>
</div>
<div class="grid" id="menu">
<div>{''.join(sections) or '<p class="empty">Menu belum tersedia.</p>'}</div>
<aside class="panel" aria-label="Keranjang belanja">
<h2>Keranjang</h2>
{cart_html}
</aside>
</div>"""
    return layout("Menu", body)


@app.post("/cart/add")
def cart_add():
    try:
        menu_id = int(request.form.get("menu_id", 0))
        qty = int(request.form.get("qty", 1))
    except (TypeError, ValueError):
        return redirect(url_for("index"))
    m = db.get_menu(menu_id)
    if not m or not m["aktif"]:
        return redirect(url_for("index"))
    uid = web_user_id()
    existing = {r["menu_id"]: r["qty"] for r in db.cart_items(uid)}
    db.cart_set(uid, menu_id, existing.get(menu_id, 0) + max(qty, 1))
    return redirect(url_for("index"))


@app.post("/cart/remove")
def cart_remove():
    try:
        menu_id = int(request.form.get("menu_id", 0))
    except (TypeError, ValueError):
        return redirect(url_for("index"))
    db.cart_set(web_user_id(), menu_id, 0)
    return redirect(url_for("index"))


@app.get("/checkout")
def checkout():
    cart = db.cart_items(web_user_id())
    if not cart:
        return redirect(url_for("index"))
    lines = "".join(
        f"<div class='cartline'><span class='n'>{escape(r['nama'])} &times; {r['qty']}</span>"
        f"<span>{rupiah(r['harga'] * r['qty'])}</span></div>"
        for r in cart
    )
    err = request.args.get("err", "")
    err_html = f"<p class='error'>{escape(err)}</p>" if err else ""
    body = f"""
<h2 class="sec">Checkout</h2>
{err_html}
<div class="notice"><strong>Ringkasan pesanan</strong>{lines}
<div class="total"><span>Total bayar</span><span>{rupiah(db.cart_total(cart))}</span></div></div>
<form class="stack" method="post" action="{url_for('checkout_post')}">
<label>Nama pemesan <input type="text" name="nama" required maxlength="80" placeholder="Nama kamu"></label>
<fieldset><legend>Tipe pesanan</legend><div class="radio">
<label><input type="radio" name="tipe" value="ambil" checked> Ambil di kedai</label>
<label><input type="radio" name="tipe" value="antar"> Diantar</label>
</div></fieldset>
<fieldset><legend>Pembayaran</legend><div class="radio">
<label><input type="radio" name="bayar" value="tunai" checked> Tunai</label>
<label><input type="radio" name="bayar" value="qris"> QRIS</label>
</div></fieldset>
<button type="submit">Buat Pesanan</button>
</form>"""
    return layout("Checkout", body)


@app.post("/checkout")
def checkout_post():
    nama = (request.form.get("nama") or "").strip()
    tipe = request.form.get("tipe", "ambil")
    bayar = request.form.get("bayar", "tunai")
    if not nama:
        return redirect(url_for("checkout", err="Nama pemesan wajib diisi."))
    if tipe not in ("ambil", "antar"):
        tipe = "ambil"
    if bayar not in ("tunai", "qris"):
        bayar = "tunai"
    uid = web_user_id()
    try:
        db.upsert_pelanggan(uid, nama)
        kode, _pid, _total = db.buat_pesanan(uid, nama, tipe, bayar)
    except ValueError:
        return redirect(url_for("index"))
    return redirect(url_for("sukses", kode=kode))


@app.get("/sukses/<kode>")
def sukses(kode):
    pesanan, items = db.cari_kode(kode)
    if not pesanan:
        abort(404)
    lines = "".join(
        f"<div class='cartline'><span class='n'>{escape(r['nama'])} &times; {r['qty']}</span>"
        f"<span>{rupiah(r['harga'] * r['qty'])}</span></div>"
        for r in items
    )
    body = f"""
<div class="receipt">
<p class="thanks">Pesanan diterima.</p>
<p class="kode">{pesanan['kode']}</p>
<p>Atas nama <strong>{escape(pesanan['nama'])}</strong> &middot; {pesanan['tipe']} &middot; {pesanan['bayar'].upper()}</p>
{lines}
<div class="total"><span>Total</span><span>{rupiah(pesanan['total'])}</span></div>
<p>Status: <span class="badge {pesanan['status']}">{db.STATUS_LABEL[pesanan['status']]}</span></p>
<p class="mt"><a class="btn ghost" href="{url_for('cek_status', kode=pesanan['kode'])}">Pantau status pesanan</a>
<a class="btn" href="{url_for('index')}">Pesan lagi</a></p>
</div>"""
    return layout("Pesanan berhasil", body)


@app.get("/status")
def cek_status():
    kode = (request.args.get("kode") or "").strip()
    hasil = ""
    if kode:
        pesanan, items = db.cari_kode(kode)
        if not pesanan:
            hasil = f"<p class='error'>Kode <strong>{escape(kode.upper())}</strong> tidak ditemukan. Periksa lagi ya.</p>"
        else:
            lines = "".join(
                f"<div class='cartline'><span class='n'>{escape(r['nama'])} &times; {r['qty']}</span>"
                f"<span>{rupiah(r['harga'] * r['qty'])}</span></div>"
                for r in items
            )
            hasil = f"""
<div class="notice">
<p class="kode">{pesanan['kode']}</p>
<p>Atas nama <strong>{escape(pesanan['nama'])}</strong> &middot; total {rupiah(pesanan['total'])}</p>
{lines}
<p class="mt">Status: <span class="badge {pesanan['status']}">{db.STATUS_LABEL[pesanan['status']]}</span></p>
</div>"""
    body = f"""
<h2 class="sec">Cek Status Pesanan</h2>
<form class="stack" method="get" action="{url_for('cek_status')}">
<label>Kode pesanan <input type="text" name="kode" value="{escape(kode.upper())}" placeholder="cth: KS-20261009-001" required></label>
<button type="submit">Cek Status</button>
</form>
<div class="mt">{hasil}</div>"""
    return layout("Cek Status", body)


# ---------------------------------------------------------------- admin
@app.get("/admin")
def admin_login():
    # Saat sudah login, redirect ke dashboard — KECUALI ada parameter err
    # (login gagal): halaman error harus tetap tampil walau sesi admin lama
    # masih ada, jangan ditimpa redirect.
    if session.get("is_admin") and not request.args.get("err"):
        return redirect(url_for("admin_dash"))
    return _login_page(request.args.get("err", ""))


def _login_page(err=""):
    err_html = f"<p class='error'>{escape(err)}</p>" if err else ""
    body = f"""
<h2 class="sec">Login Admin</h2>
{err_html}
<form class="stack" method="post" action="{url_for('admin_login_post')}">
<label>Username <input type="text" name="username" required autocomplete="username"></label>
<label>Kata sandi <input type="password" name="password" required autocomplete="current-password"></label>
<button type="submit">Masuk</button>
</form>"""
    return layout("Login Admin", body)


@app.post("/admin")
def admin_login_post():
    ip = rate_limit.client_ip()

    # Rate limit: tolak sebelum menyentuh kredensial, supaya brute force
    # tidak bisa jalan pada kecepatan penuh.
    allowed, remaining, retry_after = rate_limit.status(ip)
    if not allowed:
        menit = max(1, retry_after // 60)
        return redirect(url_for("admin_login", err=(
            f"Terlalu banyak percobaan. Coba lagi dalam {menit} menit.")))

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    if ADMIN_PASSWORD and username == ADMIN_USER and password == ADMIN_PASSWORD:
        rate_limit.reset(ip)          # login sah: buka kuota untuk IP ini
        session["is_admin"] = True
        return redirect(url_for("admin_dash"))

    # Gagal: catat di limiter. Setelah kuota habis, percobaan berikutnya
    # diblokir di atas tanpa membandingkan password sama sekali.
    tries = rate_limit.record_failure(ip)
    sisa = max(0, rate_limit.MAX_ATTEMPTS - tries)
    if sisa > 0:
        err = f"Kata sandi salah. Sisa percobaan: {sisa}."
    else:
        menit = max(1, rate_limit.LOCKOUT_SECONDS // 60)
        err = f"Kata sandi salah. Login dikunci {menit} menit."
    # Login gagal: redirect ke halaman login dengan parameter err (kontrak
    # yang direkam suite TestSprite). Sesi admin lama TIDAK dibuang — GET
    # /admin dengan err menampilkan form + pesan error walau sesi ada.
    return redirect(url_for("admin_login", err=err))


@app.get("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


@app.get("/admin/dashboard")
@admin_required
def admin_dash():
    orders = db.pesanan_hari_ini()
    rows = []
    for o in orders:
        opts = "".join(
            f"<option value='{s}'{' selected' if o['status'] == s else ''}>{db.STATUS_LABEL[s]}</option>"
            for s in db.STATUS_LIST
        )
        rows.append(f"""
<tr>
<td class="nowrap"><div class="stacked"><strong>{o['kode']}</strong><span class="sub">{escape(o['nama'])}</span></div></td>
<td class="nowrap"><div class="stacked"><span>{o['tipe']}</span><span class="sub">{o['bayar'].upper()}</span></div></td>
<td class="num">{rupiah(o['total'])}</td>
<td class="nowrap"><span class="badge {o['status']}">{db.STATUS_LABEL[o['status']]}</span></td>
<td class="nowrap"><form class="inline" method="post" action="{url_for('admin_set_status')}">
<input type="hidden" name="pesanan_id" value="{o['id']}">
<select name="status" aria-label="Ubah status {o['kode']}">{opts}</select>
<button class="small" type="submit">Ubah</button>
</form></td>
</tr>""")
    orders_html = (
        f"<div class='table-wrap'><table class='admin orders'><thead><tr><th>Kode / Nama</th><th>Tipe / Bayar</th><th class='num'>Total</th><th>Status</th><th>Aksi</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        if rows
        else "<p class='empty'>Belum ada pesanan hari ini.</p>"
    )

    menus = db.semua_menu()
    mrows = []
    for m in menus:
        aktif_txt = "Aktif" if m["aktif"] else "Nonaktif"
        mrows.append(f"""
<tr>
<td><div class="stacked"><strong>{escape(m['nama'])}</strong><span class="sub">{KATEGORI_LABEL.get(m['kategori'], m['kategori'])} &middot; {escape(m['deskripsi']) or '&mdash;'}</span></div></td>
<td class="num">{rupiah(m['harga'])}</td>
<td class="nowrap">{aktif_txt}</td>
<td class="nowrap">
<form class="inline" method="post" action="{url_for('admin_menu_harga')}">
<input type="hidden" name="menu_id" value="{m['id']}">
<input type="number" name="harga" value="{m['harga']}" min="0" step="500" style="width:110px" aria-label="Harga baru {escape(m['nama'])}">
<button class="small" type="submit">Harga</button>
</form>
<form class="inline" method="post" action="{url_for('admin_menu_aktif')}">
<input type="hidden" name="menu_id" value="{m['id']}">
<input type="hidden" name="aktif" value="{0 if m['aktif'] else 1}">
<button class="small ghost" type="submit">{'Nonaktifkan' if m['aktif'] else 'Aktifkan'}</button>
</form>
</td>
</tr>""")
    menu_html = (
        f"<div class='table-wrap'><table class='admin menus'><thead><tr><th>Menu</th><th class='num'>Harga</th><th>Status</th><th>Aksi</th></tr></thead>"
        f"<tbody>{''.join(mrows)}</tbody></table></div>"
    )

    body = f"""
<h2 class="sec">Dashboard Admin <a class="btn ghost small" href="{url_for('admin_riwayat')}">Riwayat Pesanan</a> <a class="btn ghost small" href="{url_for('admin_logout')}">Keluar</a></h2>
<h2 class="sec">Pesanan Hari Ini ({len(rows)})</h2>
{orders_html}
<h2 class="sec">Kelola Menu</h2>
{menu_html}
<h2 class="sec">Tambah Menu Baru</h2>
<form class="stack" method="post" action="{url_for('admin_menu_tambah')}">
<label>Nama menu <input type="text" name="nama" required maxlength="80"></label>
<label>Kategori <select name="kategori">
<option value="kopi">Kopi</option><option value="nonkopi">Non-Kopi</option><option value="snack">Snack</option>
</select></label>
<label>Harga (Rp) <input type="number" name="harga" required min="0" step="500"></label>
<label>Deskripsi <input type="text" name="deskripsi" maxlength="200"></label>
<button type="submit">Tambah Menu</button>
</form>
<h2 class="sec">Pemeliharaan</h2>
<form class="inline" method="post" action="{url_for('admin_restart')}"
onsubmit="return confirm('Muat ulang aplikasi? Sesi admin tidak hilang.')">
<button class="small ghost" type="submit">Muat Ulang Aplikasi</button>
</form>
<p class="empty">Me-reload proses server (tidak menghapus sesi admin; menu &amp; pesanan dari database, tetap aman).</p>"""
    return layout("Dashboard Admin", body)


@app.after_request
def tanpa_cache_admin(resp):
    """Halaman admin jangan di-cache: data pesanan harus selalu segar."""
    if request.path.startswith("/admin"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.post("/admin/pesanan/status")
@admin_required
def admin_set_status():
    try:
        pid = int(request.form.get("pesanan_id", 0))
        db.set_status(pid, request.form.get("status", ""))
    except (TypeError, ValueError):
        pass
    return redirect(url_for("admin_dash"))


PER_HAL = 20


@app.get("/admin/pesanan")
@admin_required
def admin_riwayat():
    kode = (request.args.get("kode") or "").strip()
    dari = (request.args.get("dari") or "").strip()
    sampai = (request.args.get("sampai") or "").strip()
    try:
        hal = max(1, int(request.args.get("hal", 1)))
    except (TypeError, ValueError):
        hal = 1

    total = db.hitung_pesanan(kode, dari, sampai)
    total_hal = max(1, -(-total // PER_HAL))
    hal = min(hal, total_hal)
    orders = db.semua_pesanan(kode, dari, sampai, PER_HAL, (hal - 1) * PER_HAL)

    rows = []
    for o in orders:
        opts = "".join(
            f"<option value='{s}'{' selected' if o['status'] == s else ''}>{db.STATUS_LABEL[s]}</option>"
            for s in db.STATUS_LIST
        )
        rows.append(f"""
<tr>
<td class="nowrap"><a href="{url_for('admin_pesanan_detail', kode=o['kode'])}"><strong>{o['kode']}</strong></a></td>
<td class="nowrap"><div class="stacked">{escape(o['nama'])}<span class="sub">{o['dibuat']}</span></div></td>
<td class="nowrap">{o['tipe']}</td>
<td class="nowrap">{o['bayar'].upper()}</td>
<td class="num">{rupiah(o['total'])}</td>
<td class="nowrap"><span class="badge {o['status']}">{db.STATUS_LABEL[o['status']]}</span></td>
<td class="nowrap"><form class="inline" method="post" action="{url_for('admin_set_status')}">
<input type="hidden" name="pesanan_id" value="{o['id']}">
<select name="status" aria-label="Ubah status {o['kode']}">{opts}</select>
<button class="small" type="submit">Ubah</button>
</form></td>
</tr>""")
    tabel = (
        "<div class='table-wrap'><table class='admin riwayat'><thead><tr>"
        "<th>Kode</th><th>Pelanggan / Tanggal</th><th>Tipe</th><th>Bayar</th>"
        "<th class='num'>Total</th><th>Status</th><th>Aksi</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
        if rows
        else "<p class='empty'>Tidak ada pesanan untuk filter ini.</p>"
    )

    # kontrol halaman, pertahankan filter aktif
    def args_hal(h):
        q = {k: v for k, v in
             (("kode", kode), ("dari", dari), ("sampai", sampai)) if v}
        q["hal"] = h
        return "?" + urlencode(q)
    nav = ""
    if total_hal > 1:
        prev = f"<a class='btn ghost small' href='{url_for('admin_riwayat')}{args_hal(hal - 1)}'>&laquo; Sebelumnya</a>" if hal > 1 else ""
        nxt = f"<a class='btn ghost small' href='{url_for('admin_riwayat')}{args_hal(hal + 1)}'>Berikutnya &raquo;</a>" if hal < total_hal else ""
        nav = f"<p class='empty mt'>{prev} Halaman {hal} dari {total_hal} ({total} pesanan) {nxt}</p>"

    body = f"""
<h2 class="sec">Riwayat Pesanan
<a class="btn ghost small" href="{url_for('admin_dash')}">Dashboard</a></h2>
<form class="inline mt" method="get" action="{url_for('admin_riwayat')}">
<label>Cari kode <input type="text" name="kode" value="{escape(kode)}" placeholder="KS-20261009-001"></label>
<label>Dari tanggal <input type="date" name="dari" value="{escape(dari)}"></label>
<label>Sampai <input type="date" name="sampai" value="{escape(sampai)}"></label>
<button class="small" type="submit">Filter</button>
</form>
{tabel}
{nav}"""
    return layout("Riwayat Pesanan", body)


@app.get("/admin/pesanan/<kode>")
@admin_required
def admin_pesanan_detail(kode):
    row, items = db.cari_kode(kode)
    if not row:
        abort(404)
    opts = "".join(
        f"<option value='{s}'{' selected' if row['status'] == s else ''}>{db.STATUS_LABEL[s]}</option>"
        for s in db.STATUS_LIST
    )
    item_rows = "".join(
        f"<tr><td>{escape(i['nama'])}</td><td class='num'>{i['qty']}</td>"
        f"<td class='num'>{rupiah(i['harga'])}</td>"
        f"<td class='num'>{rupiah(i['harga'] * i['qty'])}</td></tr>"
        for i in items
    )
    body = f"""
<h2 class="sec">Pesanan {escape(row['kode'])}
<a class="btn ghost small" href="{url_for('admin_riwayat')}">Riwayat</a></h2>
<p class="mt"><strong>{escape(row['nama'])}</strong> &middot; {row['tipe']} &middot; {row['bayar'].upper()} &middot; {row['dibuat']}</p>
<div class="table-wrap mt"><table class="admin"><thead><tr>
<th>Item</th><th class="num">Qty</th><th class="num">Harga</th><th class="num">Subtotal</th>
</tr></thead><tbody>{item_rows}</tbody></table></div>
<p class="mt">Total: <strong>{rupiah(row['total'])}</strong></p>
<form class="inline mt" method="post" action="{url_for('admin_set_status')}">
<input type="hidden" name="pesanan_id" value="{row['id']}">
<label>Status <select name="status" aria-label="Ubah status">{opts}</select></label>
<button class="small" type="submit">Ubah</button>
</form>"""
    return layout(f"Pesanan {row['kode']}", body)


@app.post("/admin/restart")
@admin_required
def admin_restart():
    """Graceful reload proses worker (gunicorn): kirim SIGHUP ke master.

    Sesi admin tetap sah karena sesi berbasis cookie dengan SECRET_KEY yang
    tidak berubah. Di mode dev (tanpa gunicorn) reload dilewati dan hanya
    dilaporkan — mengirim sinyal ke proses induk non-gunicorn tidak aman.
    """
    if "gunicorn" not in sys.modules:
        return {"ok": False, "pesan": "Reload hanya tersedia saat berjalan di bawah gunicorn."}
    import signal
    import threading

    def _sighup():
        os.kill(os.getppid(), signal.SIGHUP)

    # Tunda sejenak supaya respons HTTP terkirim dulu sebelum worker reload.
    threading.Timer(0.5, _sighup).start()
    return {"ok": True, "pesan": "Aplikasi dimuat ulang. Sesi admin tetap aktif."}


@app.post("/admin/menu/tambah")
@admin_required
def admin_menu_tambah():
    nama = (request.form.get("nama") or "").strip()
    kategori = request.form.get("kategori", "kopi")
    try:
        harga = int(request.form.get("harga", 0))
    except (TypeError, ValueError):
        harga = 0
    deskripsi = (request.form.get("deskripsi") or "").strip()
    if nama and harga > 0 and kategori in KATEGORI_LABEL:
        db.tambah_menu(kategori, nama, harga, deskripsi)
    return redirect(url_for("admin_dash"))


@app.post("/admin/menu/harga")
@admin_required
def admin_menu_harga():
    try:
        db.set_harga(int(request.form.get("menu_id", 0)), int(request.form.get("harga", 0)))
    except (TypeError, ValueError):
        pass
    return redirect(url_for("admin_dash"))


@app.post("/admin/menu/aktif")
@admin_required
def admin_menu_aktif():
    try:
        db.set_aktif(int(request.form.get("menu_id", 0)), request.form.get("aktif") == "1")
    except (TypeError, ValueError):
        pass
    return redirect(url_for("admin_dash"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")

