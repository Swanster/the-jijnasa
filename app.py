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
import uuid
from functools import wraps

from flask import Flask, abort, redirect, request, session, url_for

import db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-senja-ganti-di-produksi")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "senja123")

db.init_db()

KATEGORI_LABEL = {"kopi": "Kopi", "nonkopi": "Non-Kopi", "snack": "Snack"}


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
input[type=text],input[type=password],select,textarea{padding:11px 13px;border-radius:10px;border:1px solid var(--line);background:#fff;color:var(--ink);font-size:1rem;width:100%;font-family:inherit}
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
table.admin{min-width:760px}
table.admin th,table.admin td{padding:13px 16px}
table.admin tbody tr:nth-child(even){background:#FCF7EC}
table.admin .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
table.admin .nowrap{white-space:nowrap}
table.admin .inline{display:inline-flex;gap:8px;align-items:center}
table.admin select{width:auto;padding:8px 10px;font-size:.88rem}
table.admin input[type=number]{padding:8px 10px;font-size:.88rem}
.stacked{display:flex;flex-direction:column;gap:2px}
.stacked .sub{color:var(--muted);font-size:.82rem}
"""



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
<svg width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden="true">
<circle cx="16" cy="10" r="6" fill="#E8A94E"/>
<path d="M8 15h13v5a6 6 0 0 1-6 6h-1a6 6 0 0 1-6-6v-5z" stroke="#B4531F" stroke-width="2.4" stroke-linejoin="round"/>
<path d="M21 16h2.5a3.5 3.5 0 0 1 0 7H21" stroke="#B4531F" stroke-width="2.4" stroke-linecap="round"/>
<path d="M13 5c-1.5-2 1.5-2.6 0-4.5M18 5c-1.5-2 1.5-2.6 0-4.5" stroke="#B4531F" stroke-width="1.8" stroke-linecap="round"/>
</svg>
<span>Kedai Kopi <em>Senja</em></span></a>
<nav class="links">
<a href="{url_for('index')}">Menu</a>
<a href="{url_for('cek_status')}">Cek Status</a>
<a href="{url_for('admin_login')}">Admin</a>
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
<h3>{m['nama']}</h3>
<span class="dots" aria-hidden="true"></span>
<span class="price">{rupiah(m['harga'])}</span>
</div>
<p class="desc">{m['deskripsi'] or ''}</p>
<form class="qtyform" method="post" action="{url_for('cart_add')}">
<input type="hidden" name="menu_id" value="{m['id']}">
<label>Jumlah <input type="number" name="qty" value="1" min="1" max="20" aria-label="Jumlah {m['nama']}"></label>
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
<span class="n">{r['nama']} &times; {r['qty']}</span>
<span>{rupiah(r['harga'] * r['qty'])}</span>
<form class="inline" method="post" action="{url_for('cart_remove')}">
<input type="hidden" name="menu_id" value="{r['menu_id']}">
<button class="small ghost" type="submit" aria-label="Hapus {r['nama']}">hapus</button>
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
<svg width="200" height="200" viewBox="0 0 220 220" fill="none" stroke="#B4531F" stroke-width="3" stroke-linecap="round">
<circle cx="110" cy="62" r="32" fill="#F3D9A4" stroke="none"/>
<path d="M72 128h68v32a24 24 0 0 1-24 24h-20a24 24 0 0 1-24-24v-32z"/>
<path d="M140 136h11a13 13 0 0 1 0 26h-13"/>
<path d="M94 106c-6-8 6-12 0-20M112 106c-6-8 6-12 0-20M130 106c-6-8 6-12 0-20"/>
<line x1="54" y1="202" x2="166" y2="202"/>
</svg>
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
        f"<div class='cartline'><span class='n'>{r['nama']} &times; {r['qty']}</span>"
        f"<span>{rupiah(r['harga'] * r['qty'])}</span></div>"
        for r in cart
    )
    err = request.args.get("err", "")
    err_html = f"<p class='error'>{err}</p>" if err else ""
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
        f"<div class='cartline'><span class='n'>{r['nama']} &times; {r['qty']}</span>"
        f"<span>{rupiah(r['harga'] * r['qty'])}</span></div>"
        for r in items
    )
    body = f"""
<div class="receipt">
<p class="thanks">Pesanan diterima.</p>
<p class="kode">{pesanan['kode']}</p>
<p>Atas nama <strong>{pesanan['nama']}</strong> &middot; {pesanan['tipe']} &middot; {pesanan['bayar'].upper()}</p>
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
            hasil = f"<p class='error'>Kode <strong>{kode.upper()}</strong> tidak ditemukan. Periksa lagi ya.</p>"
        else:
            lines = "".join(
                f"<div class='cartline'><span class='n'>{r['nama']} &times; {r['qty']}</span>"
                f"<span>{rupiah(r['harga'] * r['qty'])}</span></div>"
                for r in items
            )
            hasil = f"""
<div class="notice">
<p class="kode">{pesanan['kode']}</p>
<p>Atas nama <strong>{pesanan['nama']}</strong> &middot; total {rupiah(pesanan['total'])}</p>
{lines}
<p class="mt">Status: <span class="badge {pesanan['status']}">{db.STATUS_LABEL[pesanan['status']]}</span></p>
</div>"""
    body = f"""
<h2 class="sec">Cek Status Pesanan</h2>
<form class="stack" method="get" action="{url_for('cek_status')}">
<label>Kode pesanan <input type="text" name="kode" value="{kode.upper()}" placeholder="cth: KS-20261009-001" required></label>
<button type="submit">Cek Status</button>
</form>
<div class="mt">{hasil}</div>"""
    return layout("Cek Status", body)


# ---------------------------------------------------------------- admin
@app.get("/admin")
def admin_login():
    if session.get("is_admin"):
        return redirect(url_for("admin_dash"))
    err = request.args.get("err", "")
    err_html = f"<p class='error'>{err}</p>" if err else ""
    body = f"""
<h2 class="sec">Login Admin</h2>
{err_html}
<form class="stack" method="post" action="{url_for('admin_login_post')}">
<label>Kata sandi admin <input type="password" name="password" required autocomplete="current-password"></label>
<button type="submit">Masuk</button>
</form>
<p class="empty mt">Demo: kata sandi bawaan <code>senja123</code> (ubah via env <code>ADMIN_PASSWORD</code>).</p>"""
    return layout("Login Admin", body)


@app.post("/admin")
def admin_login_post():
    if request.form.get("password") == ADMIN_PASSWORD:
        session["is_admin"] = True
        return redirect(url_for("admin_dash"))
    return redirect(url_for("admin_login", err="Kata sandi salah."))


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
<td class="nowrap"><div class="stacked"><strong>{o['kode']}</strong><span class="sub">{o['nama']}</span></div></td>
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
        f"<div class='table-wrap'><table class='admin'><thead><tr><th>Kode / Nama</th><th>Tipe / Bayar</th><th class='num'>Total</th><th>Status</th><th>Aksi</th></tr></thead>"
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
<td><div class="stacked"><strong>{m['nama']}</strong><span class="sub">{KATEGORI_LABEL.get(m['kategori'], m['kategori'])} &middot; {m['deskripsi']}</span></div></td>
<td class="num">{rupiah(m['harga'])}</td>
<td class="nowrap">{aktif_txt}</td>
<td class="nowrap">
<form class="inline" method="post" action="{url_for('admin_menu_harga')}">
<input type="hidden" name="menu_id" value="{m['id']}">
<input type="number" name="harga" value="{m['harga']}" min="0" step="500" style="width:110px" aria-label="Harga baru {m['nama']}">
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
        f"<div class='table-wrap'><table class='admin'><thead><tr><th>Menu</th><th class='num'>Harga</th><th>Status</th><th>Aksi</th></tr></thead>"
        f"<tbody>{''.join(mrows)}</tbody></table></div>"
    )

    body = f"""
<h2 class="sec">Dashboard Admin <a class="btn ghost small" href="{url_for('admin_logout')}">Keluar</a></h2>
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
</form>"""
    return layout("Dashboard Admin", body)


@app.post("/admin/pesanan/status")
@admin_required
def admin_set_status():
    try:
        pid = int(request.form.get("pesanan_id", 0))
        db.set_status(pid, request.form.get("status", ""))
    except (TypeError, ValueError):
        pass
    return redirect(url_for("admin_dash"))


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

