"""Verifikasi mode tautan admin untuk demo hackathon.

SHOW_ADMIN_LINK dibaca saat modul app di-import, jadi kedua mode harus
diuji dalam proses terpisah. Script ini menjalankan dua subproses.

Jalankan:  .venv/bin/python test_demo_admin_link.py
"""
import os
import subprocess
import sys
import tempfile

PY = sys.executable
RESULTS = []


def check(name, cond, extra=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + ((" | " + extra) if extra else ""))


def probe(show_link):
    """Jalankan subproses dengan SHOW_ADMIN_LINK tertentu, kembalikan hasil."""
    code = r'''
import os, sys
os.environ["KEDAI_DB"] = sys.argv[1]
os.environ["SECRET_KEY"] = "t"
os.environ["ADMIN_PASSWORD"] = "x"
os.environ["SHOW_ADMIN_LINK"] = sys.argv[2]
import app as A
c = A.app.test_client()
home = c.get("/").get_data(as_text=True)
admin = c.get("/admin").get_data(as_text=True)
print("LINK=" + ("yes" if "Admin</a>" in home else "no"))
print("HREF=" + ("yes" if "/admin" in home else "no"))
print("FORM=" + ("yes" if 'name="password"' in admin else "no"))
'''
    tmp = tempfile.mkdtemp(prefix="kedai-link-")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
    out = subprocess.run([PY, "-c", code, os.path.join(tmp, "t.db"), show_link],
                         capture_output=True, text=True, env=env, timeout=60)
    if out.returncode != 0:
        print(out.stderr[-600:])
        return None
    d = {}
    for line in out.stdout.strip().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k] = v
    return d


print("--- Default produksi (SHOW_ADMIN_LINK tidak di-set) ---")
d = probe("")
check("Tautan Admin TIDAK tampil di navigasi", d and d.get("LINK") == "no", str(d))
check("URL /admin tidak bocor di HTML publik", d and d.get("HREF") == "no", str(d))
check("Panel /admin tetap bisa diakses langsung", d and d.get("FORM") == "yes", str(d))

print("\n--- Mode demo hackathon (SHOW_ADMIN_LINK=1) ---")
d = probe("1")
check("Tautan Admin TAMPIL di navigasi", d and d.get("LINK") == "yes", str(d))
check("URL /admin ada di HTML (diharapkan)", d and d.get("HREF") == "yes", str(d))
check("Panel /admin tetap berfungsi", d and d.get("FORM") == "yes", str(d))

print("\n" + "=" * 50)
lulus = sum(1 for _, ok in RESULTS if ok)
total = len(RESULTS)
print(f"HASIL: {lulus}/{total} check lulus")
if lulus != total:
    print("GAGAL:")
    for n, ok in RESULTS:
        if not ok:
            print(f"  - {n}")
sys.exit(0 if lulus == total else 1)