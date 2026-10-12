"""Smoke test lokal kedai-web — pengganti mahal untuk TestSprite token.

Jalankan:  .venv/bin/python smoke_test.py

WAJIB: env var DB di app adalah KEDAI_DB (lihat db.py), bukan DB_PATH.
Menyetel KEDAI_DB ke file sementara membuat smoke test ini tidak pernah
menyentuh kedai.db produksi. Jangan ganti ke DB_PATH — itu tidak dibaca
db.py dan test akan diam-diam menulis ke database produksi.
"""
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="kedai-smoke-")
TEST_DB = os.path.join(TMP, "test.db")
os.environ["KEDAI_DB"] = TEST_DB
os.environ["SECRET_KEY"] = "smoke-test-key"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASSWORD"] = "rahasia-smoke"
ADMIN_PASS = os.environ["ADMIN_PASSWORD"]

import db as D  # noqa: E402

# Fail-fast: pastikan yang ter-import benar-benar DB sementara.
if os.path.realpath(D.DB_PATH) != os.path.realpath(TEST_DB):
    print(f"FAIL: db.py memakai {D.DB_PATH}, bukan DB sementara {TEST_DB}")
    print("      Hentikan proses: ada yang meng-import db sebelum env diset.")
    sys.exit(2)

import app as A  # noqa: E402

if os.path.realpath(D.DB_PATH) != os.path.realpath(TEST_DB):
    print(f"FAIL: setelah import app, DB_PATH jadi {D.DB_PATH}")
    sys.exit(2)

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    print(("PASS  " if cond else "FAIL  ") + name + ((" | " + extra) if extra else ""))


D.init_db()

# --- seed menu agar alur checkout bisa diuji end-to-end ---
if not D.menu_aktif():
    D.tambah_menu("kopi", "Kopi Susu", 18000, "Uji smoke")
    D.tambah_menu("snack", "Roti Bakar", 15000, "Uji smoke")

menu = D.menu_aktif()
KODE_MENU, HARGA_MENU = menu[0]["id"], menu[0]["harga"]


def uid_for(vid):
    """user_id pelanggan yang Stabil untuk session visitor tertentu."""
    with A.app.test_request_context():
        from flask import session as _s

        _s["vid"] = vid
        return A.web_user_id()


# ============================================================ PUBLIK
print("--- Publik ---")
c = A.app.test_client()

r = c.get("/healthz")
check("GET /healthz -> 200", r.status_code == 200, f"status={r.status_code}")

r = c.get("/")
check("GET / -> 200", r.status_code == 200, f"status={r.status_code}")
check("Halaman utama menampilkan menu aktif", "Kopi Susu" in r.get_data(as_text=True))

r = c.get("/status")
check("GET /status -> 200", r.status_code == 200, f"status={r.status_code}")

r = c.get("/status?kode=ZZZ-999")
check("GET /status kode tak dikenal -> 200 + pesan error",
      r.status_code == 200 and "tidak ditemukan" in r.get_data(as_text=True),
      f"status={r.status_code}")

# --- keranjang ---
# Samakan session browser dengan vid tetap supaya uid hitungan test sama
# dengan uid yang dipakai request (web_user_id = sha256(vid)[:12]).
with c.session_transaction() as s:
    s["vid"] = "smoke-vid-001"

r = c.post("/cart/add", data={"menu_id": KODE_MENU, "qty": "2"}, follow_redirects=False)
check("POST /cart/add -> 302", r.status_code == 302, f"status={r.status_code}")

UID = uid_for("smoke-vid-001")
items = D.cart_items(UID)
check("Keranjang berisi 1 item qty 2", len(items) == 1 and items[0]["qty"] == 2,
      f"items={[dict(i) for i in items]}")
check("cart_total = 2 x harga", D.cart_total(items) == 2 * HARGA_MENU,
      f"total={D.cart_total(items)} harga={HARGA_MENU}")

# input tidak valid tidak boleh 500
r = c.post("/cart/add", data={"menu_id": "abc", "qty": "x"}, follow_redirects=False)
check("POST /cart/add input ngawur -> 302 (tidak 500)", r.status_code == 302,
      f"status={r.status_code}")

r = c.post("/cart/remove", data={"menu_id": str(KODE_MENU)}, follow_redirects=False)
check("POST /cart/remove -> 302", r.status_code == 302, f"status={r.status_code}")
check("Keranjang kosong setelah remove", len(D.cart_items(UID)) == 0)

# --- checkout end-to-end (keranjang harus berisi, kalau kosong app redirect ke /) ---
r = c.post("/cart/add", data={"menu_id": KODE_MENU, "qty": "1"}, follow_redirects=False)
r = c.get("/checkout")
check("GET /checkout dengan isi keranjang -> 200", r.status_code == 200,
      f"status={r.status_code}")

r = c.post("/cart/remove", data={"menu_id": str(KODE_MENU)}, follow_redirects=False)
r = c.get("/checkout", follow_redirects=False)
check("GET /checkout keranjang kosong -> 302 ke /", r.status_code == 302,
      f"loc={r.headers.get('Location')}")
c.post("/cart/add", data={"menu_id": KODE_MENU, "qty": "1"}, follow_redirects=False)

r = c.post("/checkout", data={"nama": "", "tipe": "ambil", "bayar": "tunai"},
           follow_redirects=False)
check("Checkout tanpa nama -> redirect ke /checkout?err=",
      r.status_code == 302 and "err=" in r.headers.get("Location", ""),
      f"loc={r.headers.get('Location')}")

r = c.post("/checkout", data={"nama": "Budi", "tipe": "ambil", "bayar": "tunai"},
           follow_redirects=False)
check("Checkout valid -> 302", r.status_code == 302, f"loc={r.headers.get('Location')}")
KODE_PESANAN = r.headers.get("Location", "").rsplit("/", 1)[-1]
# Format: "KS-" + YYYYMMDD (8) + "-" + NN (3) = 15 karakter
check("Kode pesanan format KS-YYYYMMDD-NNN",
      KODE_PESANAN.startswith("KS-") and len(KODE_PESANAN) == 15, f"kode={KODE_PESANAN}")

r = c.get(f"/sukses/{KODE_PESANAN}")
check("GET /sukses/<kode> -> 200", r.status_code == 200, f"status={r.status_code}")

r = c.get(f"/status?kode={KODE_PESANAN}")
check("Cek status pesanan menemukan kode",
      r.status_code == 200 and KODE_PESANAN in r.get_data(as_text=True),
      f"status={r.status_code}")

r = c.get("/sukses/TIDAK-ADA-999")
check("GET /sukses kode tak ada -> 404", r.status_code == 404, f"status={r.status_code}")

# --- 404 ---
r = c.get("/rute-yang-tidak-ada")
check("Route tak dikenal -> 404", r.status_code == 404, f"status={r.status_code}")

# ============================================================ ADMIN
print("\n--- Admin ---")
r = c.get("/admin/dashboard", follow_redirects=False)
check("Dashboard tanpa login -> 302 ke login", r.status_code == 302,
      f"loc={r.headers.get('Location')}")

r = c.post("/admin", data={"username": "admin", "password": "salah"},
           follow_redirects=False)
check("Login password salah -> redirect ?err=", r.status_code == 302
      and "err=" in r.headers.get("Location", ""), f"loc={r.headers.get('Location')}")

r = c.post("/admin", data={"username": "salah", "password": "rahasia-smoke"},
           follow_redirects=False)
check("Login username salah -> redirect ?err=", "err=" in r.headers.get("Location", ""),
      f"loc={r.headers.get('Location')}")

r = c.get("/admin")
check("GET /admin -> 200 form login", r.status_code == 200, f"status={r.status_code}")

r = c.post("/admin", data={"username": "admin", "password": "rahasia-smoke"},
           follow_redirects=False)
check("Login admin benar -> 302 dashboard", r.status_code == 302
      and "dashboard" in r.headers.get("Location", ""), f"loc={r.headers.get('Location')}")

r = c.get("/admin/dashboard")
check("GET /admin/dashboard -> 200", r.status_code == 200, f"status={r.status_code}")
check("Cache-Control no-store di halaman admin",
      "no-store" in r.headers.get("Cache-Control", ""), r.headers.get("Cache-Control", ""))

# Beranda memuat daftar menu. Kalau responsnya di-cache browser, admin yang
# baru saja menonaktifkan menu akan masih melihat daftar lama setelah reload.
r = c.get("/")
cc = r.headers.get("Cache-Control", "")
check("Cache-Control no-store di beranda (daftar menu)",
      "no-store" in cc and "max-age=0" in cc, f"cc={cc!r}")
check("Pragma/Expires anti-cache di beranda",
      r.headers.get("Pragma", "") == "no-cache" and r.headers.get("Expires", "") == "0",
      f"pragma={r.headers.get('Pragma','')!r} expires={r.headers.get('Expires','')!r}")

# Regression: nonaktifkan semua menu lewat db, beranda harus kosong dan
# menampilkan empty-state, bukan cuma pesan keranjang kosong.
_id_aktif = [m["id"] for m in D.menu_aktif()]
for mid in _id_aktif:
    D.set_aktif(mid, False)
r = c.get("/")
_html = r.get_data(as_text=True)
check("Semua menu nonaktif -> query publik kosong", len(D.menu_aktif()) == 0)
check("Beranda tampil empty-state menu saat semua item nonaktif",
      "Menu belum tersedia" in _html, "empty-state tidak muncul")
check("Empty-state menu terpisah dari pesan keranjang kosong",
      "Menu belum tersedia" in _html and _html.count("Menu belum tersedia") == 1)
check("Tidak ada nama menu yang bocor ke halaman publik",
      not any(m["nama"] in _html for m in D.semua_menu()),
      "ada item menu yang masih tampil")
for mid in _id_aktif:
    D.set_aktif(mid, True)
check("Aktifkan kembali -> menu publik pulih", len(D.menu_aktif()) == len(_id_aktif))

r = c.get("/admin/pesanan")
check("GET /admin/pesanan -> 200", r.status_code == 200, f"status={r.status_code}")
check("Riwayat memuat pesanan uji", KODE_PESANAN in r.get_data(as_text=True))

r = c.get("/admin/pesanan?kode=" + KODE_PESANAN)
check("Filter riwayat bykode -> 200", r.status_code == 200
      and KODE_PESANAN in r.get_data(as_text=True), f"status={r.status_code}")

r = c.get(f"/admin/pesanan/{KODE_PESANAN}")
check("Detail pesanan -> 200", r.status_code == 200, f"status={r.status_code}")

pesanan, _items = D.cari_kode(KODE_PESANAN)
PID = pesanan["id"]
r = c.post("/admin/pesanan/status", data={"pesanan_id": str(PID), "status": "dimasak"},
           follow_redirects=False)
check("Ubah status -> 302", r.status_code == 302, f"status={r.status_code}")
row_pesanan, _items = D.get_pesanan(PID)
check("Status tersimpan di DB", row_pesanan["status"] == "dimasak",
      f"status={row_pesanan['status']}")

r = c.post("/admin/pesanan/status", data={"pesanan_id": "abc", "status": "ngawur"},
           follow_redirects=False)
check("Status input ngawur -> 302 tanpa 500", r.status_code == 302, f"status={r.status_code}")

r = c.post("/admin/menu/tambah", data={"nama": "Menu Uji", "kategori": "kopi",
                                       "harga": "20000", "deskripsi": ""},
           follow_redirects=False)
check("Tambah menu -> 302", r.status_code == 302, f"status={r.status_code}")
cek = [m for m in D.semua_menu() if m["nama"] == "Menu Uji"]
check("Menu baru ada di DB", len(cek) == 1, f"jumlah={len(cek)}")
if cek:
    m = cek[0]
    r = c.post("/admin/menu/harga", data={"menu_id": str(m["id"]), "harga": "25000"},
               follow_redirects=False)
    check("Ubah harga -> 302", r.status_code == 302, f"status={r.status_code}")
    check("Harga baru tersimpan", D.get_menu(m["id"])["harga"] == 25000,
          f"harga={D.get_menu(m['id'])['harga']}")
    r = c.post("/admin/menu/aktif", data={"menu_id": str(m["id"])},
               follow_redirects=False)
    check("Toggle aktif -> 302", r.status_code == 302, f"status={r.status_code}")

r = c.post("/admin/restart", follow_redirects=False)
check("POST /admin/restart -> 200 JSON (dev: dilewati)",
      r.status_code == 200 and "gunicorn" in r.get_data(as_text=True),
      f"status={r.status_code} body={r.get_data(as_text=True)[:80]}")

r = c.get("/admin/logout", follow_redirects=False)
check("Logout -> 302", r.status_code == 302, f"status={r.status_code}")
r = c.get("/admin/dashboard", follow_redirects=False)
check("Setelah logout dashboard -> 302", r.status_code == 302, f"status={r.status_code}")

# ============================================================ Keamanan
print("\n--- Keamanan: rate limit + sembunyikan tautan admin ---")

import re as _re  # noqa: E402

import rate_limit as RL  # noqa: E402

# Halaman publik tidak boleh mengiklankan URL panel admin.
r = c.get("/")
html = r.get_data(as_text=True)
check("Tautan Admin tidak ada di navigasi publik", "Admin</a>" not in html)
check("Tautan /admin tidak ada di HTML publik",
      'href="/admin"' not in html and "href='/admin'" not in html)
check("Panel admin tetap bisa diakses via URL langsung",
      c.get("/admin", follow_redirects=False).status_code == 200)

RL._reset_for_tests()
c2 = A.app.test_client()
MAX = RL.MAX_ATTEMPTS
errs = []
for i in range(MAX + 3):
    rr = c2.post("/admin", data={"username": "admin", "password": f"salah-{i}"},
                 follow_redirects=True)
    m = _re.search(r"(Kata sandi salah[^.]*\.|Terlalu banyak percobaan[^.]*\.)",
                   rr.get_data(as_text=True))
    errs.append(m.group(1) if m else "?")
check(f"{MAX} percobaan pertama ditolak sebagai 'salah'",
      all("salah" in e and "Terlalu" not in e for e in errs[:MAX]), f"{errs[:MAX]}")
check(f"percobaan #{MAX + 1} diblokir (lockout aktif)",
      "Terlalu banyak" in errs[MAX], errs[MAX])
check("percobaan setelah lockout tetap diblokir",
      all("Terlalu banyak" in e for e in errs[MAX + 1:]), f"{errs[MAX + 1:]}")

# Password benar TIDAK boleh lolos saat terkunci.
rr = c2.post("/admin", data={"username": "admin", "password": ADMIN_PASS},
             follow_redirects=False)
check("Password benar ditolak saat IP terkunci",
      "err=" in str(rr.headers.get("Location", "")), rr.headers.get("Location"))

# Bypass lewat X-Forwarded-For harus gagal (header tidak dipercaya by default).
RL._reset_for_tests()
c3 = A.app.test_client()
for i in range(MAX + 5):
    c3.post("/admin", data={"username": "admin", "password": "salah"},
            headers={"X-Forwarded-For": f"10.0.0.{i}"})
rr = c3.post("/admin", data={"username": "admin", "password": "salah"},
             headers={"X-Forwarded-For": "10.9.9.9"}, follow_redirects=True)
check("Bypass X-Forwarded-For tidak lolos lockout",
      "Terlalu banyak" in rr.get_data(as_text=True))

# Login sah harus berhasil walau ada kegagalan sebelumnya, DAN kuota
# harus dibebaskan supaya admin yang salah ketik tidak terkunci permanen.
RL._reset_for_tests()
c4 = A.app.test_client()
for i in range(MAX - 1):                      # gagal, tapi belum habis kuota
    c4.post("/admin", data={"username": "admin", "password": "salah"})
rr = c4.post("/admin", data={"username": "admin", "password": ADMIN_PASS},
             follow_redirects=False)
check("Login sah berhasil setelah beberapa kegagalan",
      "dashboard" in rr.headers.get("Location", ""), rr.headers.get("Location"))
with c4.session_transaction():
    pass
rr2 = c4.post("/admin", data={"username": "admin", "password": ADMIN_PASS},
              follow_redirects=False)
check("Kuota dibebaskan setelah login sah",
      "dashboard" in str(rr2.headers.get("Location", "")),
      str(rr2.headers.get("Location")))

# Sesi admin yang sah harus tetap bisa dipakai walau login lain terkunci.
RL._reset_for_tests()
c5 = A.app.test_client()
c5.post("/admin", data={"username": "admin", "password": ADMIN_PASS},
        follow_redirects=False)
for i in range(MAX + 2):
    c5.post("/admin", data={"username": "admin", "password": "salah"})
check("Sesi admin sah tidak terganggu lockout IP sendiri",
      c5.get("/admin/dashboard", follow_redirects=False).status_code == 200)

RL._reset_for_tests()

# Tautan admin harus bisa dimunculkan untuk demo hackathon lewat env.
# Mode itu diuji terpisah di test_demo_admin_link.py karena SHOW_ADMIN_LINK
# dibaca saat import — tidak bisa berubah di proses yang sama.

print("\n" + "=" * 50)
lulus = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"HASIL: {lulus}/{total} check lulus")
if lulus != total:
    print("\nGAGAL:")
    for n, ok, e in results:
        if not ok:
            print(f"  - {n} {e}")
print(f"DB test: {D.DB_PATH}")
sys.exit(0 if lulus == total else 1)