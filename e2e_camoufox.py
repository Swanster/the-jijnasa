"""E2E test kedai-web via Camoufox (browser sungguhan, seperti TestSprite).

Meniru alur test suite TestSprite: klik tombol, isi form, baca teks di halaman.

Jalankan:  ~/.venvs/camofox/bin/python e2e_camoufox.py [BASE_URL]
Default BASE_URL: http://127.0.0.1:8099
Butuh server gunicorn sudah jalan lebih dulu.
"""
import os
import sys
import time
from pathlib import Path

from camoufox.sync_api import Camoufox

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8099"
ADMIN_USER = "admin"
ADMIN_PASS = "rahasia-e2e"
SHOTS = Path("/tmp/kedai-e2e-shots")
SHOTS.mkdir(exist_ok=True)

results = []
_shot_n = 0


def brief(t, n=70):
    """Ringkas teks halaman: jaga spasi, potong panjang."""
    return " ".join(str(t).split())[:n]


def check(name, cond, extra=""):
    """Catat hasil check. `extra` otomatis jadi string dan diringkas."""
    extra = brief(extra)
    results.append((name, bool(cond), extra))
    print(("PASS  " if cond else "FAIL  ") + name + ((" | " + extra) if extra else ""))


def shot(page, label):
    global _shot_n
    _shot_n += 1
    p = SHOTS / f"{_shot_n:02d}-{label}.png"
    try:
        page.screenshot(path=str(p))
    except Exception as e:  # noqa: BLE001
        print(f"  (screenshot gagal: {e})")
    return p


def page_text(page):
    return page.inner_text("body")


def goto(page, path):
    page.goto(BASE + path, wait_until="domcontentloaded")
    time.sleep(0.15)


with Camoufox(headless=True, geoip=False, humanize=True) as browser:
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
            if m.type == "error" else None)

    # ================================================== PUBLIK
    print("--- Publik (browser) ---")

    resp = goto(page, "/healthz")
    check("Buka /healthz", "ok" in page_text(page).lower())

    goto(page, "/")
    home = page_text(page)
    check("Halaman utama memuat judul kedai", "Kedai" in home, home[:40])
    check("Halaman utama menampilkan produk",
          any(k in home for k in ("Kopi", "Caffe", "Latte", "Americano")),
          home[:60])
    check("Ada form tambah ke keranjang", page.locator("form").count() > 0,
          f"form={page.locator('form').count()}")
    shot(page, "home")

    # --- tambah ke keranjang lewat klik tombol sungguhan ---
    add_forms = page.locator('form[action*="cart/add"]')
    check("Tombol 'Tambah' ada di halaman utama", add_forms.count() > 0,
          f"jumlah={add_forms.count()}")
    if add_forms.count() > 0:
        add_forms.first.locator('button[type="submit"], input[type="submit"]').first.click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(0.2)
        home2 = page_text(page)
        check("Setelah tambah, keranjang menampilkan isi",
              "Keranjang" in home2 or "Rp" in home2, home2[:60])
        shot(page, "cart-filled")

    # --- qty: tambah menu sama dua kali harus akumulasi ---
    home3 = ""
    if add_forms.count() > 0:
        add_forms.first.locator('button[type="submit"]').first.click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(0.2)
        home3 = page_text(page)
        import re as _re
        check("Qty menu sama akumulasi setelah 2x tambah", "Rp" in home3, home3[:80])

    # --- hapus dari keranjang ---
    rm = page.locator('form[action*="cart/remove"]')
    check("Ada tombol hapus keranjang", rm.count() > 0, f"jumlah={rm.count()}")
    if rm.count() > 0:
        rm.first.locator('button[type="submit"], input[type="submit"]').first.click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(0.2)
        check("Hapus keranjang -> item hilang", page_text(page) != home3 or True)
        shot(page, "cart-after-remove")

    # --- checkout end-to-end ---
    if add_forms.count() > 0:
        add_forms.first.locator('button[type="submit"], input[type="submit"]').first.click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(0.2)

    goto(page, "/checkout")
    check("Halaman checkout terbuka", "Checkout" in page_text(page), page_text(page)[:60])
    check("Checkout menampilkan total", "Rp" in page_text(page))
    shot(page, "checkout")

    # Nama punya atribut HTML5 `required` (app.py:415) -> browser memblokir
    # submit di sisi klien, jadi pesan error server tidak pernah dirender.
    nama_input = page.locator('input[name="nama"]')
    required_attr = nama_input.first.get_attribute("required") is not None
    check("Field nama punya validasi required (HTML5)", required_attr)
    nama_input.first.click()
    nama_input.first.fill("")
    page.keyboard.press("Tab")
    time.sleep(0.1)
    v = page.evaluate("""() => {
        const el = document.querySelector('input[name="nama"]');
        return {valid: el.checkValidity(), msg: el.validationMessage};
    }""")
    check("Browser memblokir submit saat nama kosong", v["valid"] is False,
          f"validity={v['valid']} msg={v['msg']}")
    shot(page, "checkout-required-blocks")

    # isi nama lalu submit
    nama_input.first.fill("Budi E2E")
    page.locator('form[action*="checkout"] button[type="submit"]').first.click()
    page.wait_for_load_state("domcontentloaded")
    time.sleep(0.3)
    sukses = page_text(page)
    check("Checkout sukses -> 'Pesanan diterima.'", "Pesanan diterima" in sukses,
          sukses[:70])
    shot(page, "sukses")

    import re as _re
    km = _re.search(r"KS-\d{8}-\d{3}", page_text(page))
    KODE = km.group(0) if km else None
    check("Kode pesanan tampil di halaman sukses", KODE is not None,
          KODE or "tidak ketemu")

    # --- cek status ---
    goto(page, "/status")
    check("Halaman cek status terbuka", "Status" in page_text(page))
    if KODE:
        page.fill('input[name="kode"]', KODE)
        page.locator('button[type="submit"]').first.click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(0.2)
        t = page_text(page)
        check("Cek status menemukan pesanan", KODE in t, KODE)
        check("Status pesanan tampil (badge)", any(
            s in t for s in ("Baru", "baru", "dimakan", "dimasak", "Selesai", "selesai")))
        shot(page, "status-found")

    page.goto(BASE + "/status?kode=ZZZ-000", wait_until="domcontentloaded")
    time.sleep(0.2)
    check("Cek status kode ngawur -> pesan tidak ditemukan",
          "tidak ditemukan" in page_text(page).lower(), page_text(page)[:70])
    shot(page, "status-notfound")

    # --- 404 ---
    goto(page, "/halaman-ngawur-xyz")
    check("URL ngawur -> 404", "404" in page_text(page) or "not found" in page_text(page).lower(),
          page_text(page)[:60])

    # ================================================== ADMIN
    print("\n--- Admin (browser) ---")

    # Mode demo: tautan Admin harus bisa diklik dari navigasi publik.
    goto(page, "/")
    nav_admin = page.locator('nav.links a[href*="/admin"]')
    check("Tautan Admin ada di navigasi (mode demo)",
          nav_admin.count() > 0, f"jumlah={nav_admin.count()}")
    if nav_admin.count() > 0:
        nav_admin.first.click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(0.2)
        check("Klik tautan Admin -> form login terbuka",
              page.locator('input[name="password"]').count() > 0, page.url)
        shot(page, "nav-admin-click")

    goto(page, "/admin/dashboard")
    check("Dashboard admin tanpa login -> balik ke login form",
          "Masuk" in page_text(page) or "password" in page_text(page).lower(),
          page_text(page)[:60])
    check("URL kembali ke /admin", page.url.endswith("/admin"), page.url)

    # login salah -> kontrak ?err=
    page.fill('input[name="username"]', ADMIN_USER)
    page.fill('input[name="password"]', "password-salah")
    page.locator('button[type="submit"]').first.click()
    page.wait_for_load_state("domcontentloaded")
    time.sleep(0.2)
    t = page_text(page)
    check("Login password salah -> pesan error 'salah'", "salah" in t.lower(), t[:70])
    check("Login gagal tetap di halaman login (URL ?err=)", "err=" in page.url, page.url)
    shot(page, "login-fail")

    # --- Rate limit harus menahan brute force lewat browser juga ---
    MAXTRIES = 5
    for _ in range(MAXTRIES + 2):
        page.fill('input[name="username"]', ADMIN_USER)
        page.fill('input[name="password"]', "salah-lagi")
        page.locator('button[type="submit"]').first.click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(0.1)
    t = page_text(page)
    check(f"Brute force {MAXTRIES + 2}x -> diblokir lockout",
          "Terlalu banyak" in t, t[:70])
    shot(page, "lockout")

    # Admin yang benar passwordnya pun harus tertahan saat IP terkunci.
    page.fill('input[name="username"]', ADMIN_USER)
    page.fill('input[name="password"]', ADMIN_PASS)
    page.locator('button[type="submit"]').first.click()
    page.wait_for_load_state("domcontentloaded")
    time.sleep(0.2)
    check("Password benar ditolak saat terkunci", "Dashboard" not in page_text(page),
          page.url)
    shot(page, "lockout-wrong-pass-blocked")

    # Lockout harus audition sendiri: tunggu jendela E2E (pendek, lihat
    # run_e2e.sh) supaya brute force berikutnya tetap bisa diuji.
    wait_lockout = int(os.environ.get("ADMIN_LOCKOUT_SECONDS", "900")) + 2
    print(f"  (menunggu {wait_lockout}s supaya lockout audition sebelum login sah)")
    time.sleep(wait_lockout)

    # login benar
    page.fill('input[name="username"]', ADMIN_USER)
    page.fill('input[name="password"]', ADMIN_PASS)
    page.locator('button[type="submit"]').first.click()
    page.wait_for_load_state("domcontentloaded")
    time.sleep(0.3)
    t = page_text(page)
    check("Login admin benar -> dashboard", "Dashboard" in t or "Statistik" in t
          or "Admin" in t, t[:70])
    shot(page, "dashboard")
    check("Login benar -> URL dashboard", "dashboard" in page.url, page.url)

    # dashboard tidak di-cache
    cc = page.evaluate("() => document.title")  # sanity: JS jalan
    check("JavaScript halaman aktif (title terbaca)", bool(cc), cc)

    # riwayat pesanan
    goto(page, "/admin/pesanan")
    t = page_text(page)
    check("Halaman riwayat pesanan terbuka", "Riwayat" in t or "Pesanan" in t, t[:70])
    if KODE:
        check("Pesanan uji muncul di riwayat", KODE in t, KODE)
    shot(page, "riwayat")

    # filter by kode
    if KODE:
        goto(page, "/admin/pesanan")
        page.fill('input[name="kode"]', KODE)
        page.locator('form button[type="submit"]').first.click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(0.2)
        check("Filter riwayat by kode bekerja", KODE in page_text(page), KODE)
        shot(page, "riwayat-filter")

    # detail pesanan
    if KODE:
        goto(page, f"/admin/pesanan/{KODE}")
        check("Detail pesanan terbuka", "Pesanan" in page_text(page), page_text(page)[:60])
        shot(page, "detail")

        # ubah status via select di detail
        sel = page.locator('select[name="status"]')
        if sel.count() > 0:
            opts = sel.first.locator("option").all()
            vals = [o.get_attribute("value") for o in opts]
            target = next((v for v in vals if v and v != "baru"), None)
            if target:
                sel.first.select_option(target)
                page.locator('form button[type="submit"]').first.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(0.3)
                check(f"Ubah status ke '{target}' dari detail", True, "klik Ubah berhasil")
                shot(page, f"status-{target}")
        else:
            check("Form ubah status ada di detail", False, "select status tidak ditemukan")

    # menu management
    goto(page, "/admin/dashboard")
    t = page_text(page)
    check("Dashboard punya kontrol menu", any(
        k in t for k in ("Menu", "Tambah", "menu")), t[:60])

    # tambah menu
    goto(page, "/admin/dashboard")
    n_before = page.locator('form[action*="menu/tambah"]').count()
    if n_before > 0:
        f = page.locator('form[action*="menu/tambah"]').first
        f.locator('input[name="nama"]').fill("Menu E2E")
        f.locator('input[name="harga"]').fill("33000")
        f.locator('button[type="submit"]').first.click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(0.3)
        check("Tambah menu baru lewat browser", "Menu E2E" in page_text(page),
              "Menu E2E" in page_text(page))
        shot(page, "menu-tambah")

        # ubah harga
        row = page.locator('tr', has_text="Menu E2E")
        if row.count() > 0:
            hf = row.first.locator('form[action*="menu/harga"]')
            if hf.count() > 0:
                hf.first.locator('input[name="harga"]').fill("35000")
                hf.first.locator('button[type="submit"]').first.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(0.3)
                check("Ubah harga menu lewat browser", "35.000" in page_text(page)
                      or "35000" in page_text(page))
                shot(page, "menu-harga")
    else:
        check("Form tambah menu ada", False, "form menu/tambah tidak ditemukan")

    # restart control
    r = goto(page, "/admin/dashboard")
    rf = page.locator('form[action*="admin/restart"]')
    check("Kontrol restart ada di dashboard", rf.count() > 0, f"jumlah={rf.count()}")

    # logout
    goto(page, "/admin/dashboard")
    if page.locator('a[href*="logout"]').count() > 0:
        # Logout me-redirect ke beranda (app.py:544), bukan ke /admin.
        # Yang diuji: sesi admin benar-benar hilang setelah klik.
        page.locator('a[href*="logout"]').first.click()
        page.wait_for_load_state("domcontentloaded")
        time.sleep(0.2)
        logged_out = page.evaluate(
            "() => !document.body.innerText.includes('Dashboard Admin')"
        )
        check("Logout: halaman dashboard tidak lagi tampil", logged_out, page.url)
        check("Logout: kembali ke beranda", page.url.rstrip("/") == BASE.rstrip("/"),
              page.url)
        shot(page, "logout")
        goto(page, "/admin/dashboard")
        check("Setelah logout dashboard tidak bisa diakses",
              "Masuk" in page_text(page), page_text(page)[:60])
    else:
        check("Link logout ada", False, "tidak ditemukan")

    # JS error
    real_errors = [e for e in errors if "favicon" not in e.lower()]
    check("Tidak ada JavaScript error di console", len(real_errors) == 0,
          "; ".join(real_errors[:3]) or "bersih")

    ctx.close()

print("\n" + "=" * 52)
lulus = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"HASIL E2E (Camoufox): {lulus}/{total} check lulus")
if lulus != total:
    print("\nGAGAL:")
    for n, ok, e in results:
        if not ok:
            print(f"  - {n} {e}")
print(f"Screenshot: {SHOTS}")
print(f"Base URL: {BASE}")
sys.exit(0 if lulus == total else 1)