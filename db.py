"""Lapisan database SQLite untuk Kedai Kopi Senja v2.

Semua data persisten: menu, keranjang, pelanggan, pesanan.
Cukup pakai stdlib (sqlite3), tanpa dependensi tambahan.
"""

import os
import sqlite3
from datetime import date

DB_PATH = os.environ.get(
    "KEDAI_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "kedai.db")
)

STATUS_LIST = ["baru", "dimasak", "siap", "selesai", "batal"]
STATUS_LABEL = {
    "baru": "Baru masuk",
    "dimasak": "Sedang dimasak",
    "siap": "Siap diambil/diantar",
    "selesai": "Selesai",
    "batal": "Dibatalkan",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS menu (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    kategori  TEXT NOT NULL,
    nama      TEXT NOT NULL,
    harga     INTEGER NOT NULL,
    deskripsi TEXT NOT NULL DEFAULT '',
    aktif     INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS pelanggan (
    user_id INTEGER PRIMARY KEY,
    nama    TEXT NOT NULL DEFAULT '',
    dibuat  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS keranjang (
    user_id INTEGER NOT NULL,
    menu_id INTEGER NOT NULL REFERENCES menu(id),
    qty     INTEGER NOT NULL,
    PRIMARY KEY (user_id, menu_id)
);
CREATE TABLE IF NOT EXISTS pesanan (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    kode    TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    nama    TEXT NOT NULL,
    tipe    TEXT NOT NULL,
    bayar   TEXT NOT NULL,
    status  TEXT NOT NULL DEFAULT 'baru',
    total   INTEGER NOT NULL,
    dibuat  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pesanan_item (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pesanan_id INTEGER NOT NULL REFERENCES pesanan(id),
    menu_id    INTEGER NOT NULL,
    nama       TEXT NOT NULL,
    harga      INTEGER NOT NULL,
    qty        INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pesanan_hari ON pesanan(dibuat);
CREATE INDEX IF NOT EXISTS idx_pesanan_user ON pesanan(user_id);
"""

# Data awal = menu dari bot demo v1
SEED_MENU = [
    ("kopi", "Kopi Susu Senja", 18000, "Espresso, susu segar, gula aren."),
    ("kopi", "Kopi Tubruk", 12000, "Kopi tubruk robusta asli."),
    ("kopi", "Caffe Latte", 20000, "Espresso lembut dengan susu steamed."),
    ("nonkopi", "Matcha Latte", 22000, "Matcha premium, manisnya pas."),
    ("nonkopi", "Cokelat Hangat", 18000, "Cokelat hangat yang creamy."),
    ("nonkopi", "Teh Tarik", 15000, "Teh tarik manis legit."),
    ("snack", "Pisang Goreng Cokelat", 15000, "Pisang goreng topping cokelat lumer."),
    ("snack", "Roti Bakar Cokelat", 12000, "Roti bakar renyah isi cokelat."),
]


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    """Buat tabel + isi menu awal kalau masih kosong."""
    with _conn() as c:
        c.executescript(SCHEMA)
        n = c.execute("SELECT COUNT(*) AS n FROM menu").fetchone()["n"]
        if n == 0:
            c.executemany(
                "INSERT INTO menu (kategori, nama, harga, deskripsi) VALUES (?,?,?,?)",
                SEED_MENU,
            )


# --- Menu ------------------------------------------------------------------
def menu_aktif():
    with _conn() as c:
        return c.execute(
            "SELECT * FROM menu WHERE aktif=1 ORDER BY kategori, nama"
        ).fetchall()


def semua_menu():
    with _conn() as c:
        return c.execute("SELECT * FROM menu ORDER BY aktif DESC, kategori, nama").fetchall()


def get_menu(menu_id):
    with _conn() as c:
        return c.execute("SELECT * FROM menu WHERE id=?", (menu_id,)).fetchone()


def tambah_menu(kategori, nama, harga, deskripsi=""):
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO menu (kategori, nama, harga, deskripsi) VALUES (?,?,?,?)",
            (kategori, nama, harga, deskripsi),
        )
        return cur.lastrowid


def set_harga(menu_id, harga):
    with _conn() as c:
        c.execute("UPDATE menu SET harga=? WHERE id=?", (harga, menu_id))


def set_aktif(menu_id, aktif):
    with _conn() as c:
        c.execute("UPDATE menu SET aktif=? WHERE id=?", (1 if aktif else 0, menu_id))


# --- Pelanggan --------------------------------------------------------------
def upsert_pelanggan(user_id, nama=""):
    with _conn() as c:
        c.execute(
            "INSERT INTO pelanggan (user_id, nama) VALUES (?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET nama=excluded.nama",
            (user_id, nama),
        )


# --- Keranjang (persisten, tidak hilang saat restart) ------------------------
def cart_items(user_id):
    with _conn() as c:
        return c.execute(
            "SELECT k.menu_id, k.qty, m.nama, m.harga, m.aktif "
            "FROM keranjang k JOIN menu m ON m.id=k.menu_id "
            "WHERE k.user_id=? ORDER BY m.nama",
            (user_id,),
        ).fetchall()


def cart_set(user_id, menu_id, qty):
    with _conn() as c:
        if qty <= 0:
            c.execute(
                "DELETE FROM keranjang WHERE user_id=? AND menu_id=?",
                (user_id, menu_id),
            )
        else:
            c.execute(
                "INSERT INTO keranjang (user_id, menu_id, qty) VALUES (?,?,?) "
                "ON CONFLICT(user_id, menu_id) DO UPDATE SET qty=excluded.qty",
                (user_id, menu_id, qty),
            )


def cart_clear(user_id):
    with _conn() as c:
        c.execute("DELETE FROM keranjang WHERE user_id=?", (user_id,))


def cart_total(items):
    return sum(r["harga"] * r["qty"] for r in items)


# --- Pesanan -----------------------------------------------------------------
def buat_pesanan(user_id, nama, tipe, bayar):
    """Buat pesanan dari isi keranjang. Return (kode, pesanan_id, total).

    Nomor urut dihitung dari database (tidak reset saat restart).
    """
    items = cart_items(user_id)
    if not items:
        raise ValueError("keranjang kosong")
    total = cart_total(items)
    hari = date.today().strftime("%Y%m%d")
    with _conn() as c:
        seq = (
            c.execute(
                "SELECT COUNT(*) AS n FROM pesanan "
                "WHERE date(dibuat,'localtime')=date('now','localtime')"
            ).fetchone()["n"]
            + 1
        )
        kode = f"KS-{hari}-{seq:03d}"
        cur = c.execute(
            "INSERT INTO pesanan (kode, user_id, nama, tipe, bayar, status, total)"
            " VALUES (?,?,?,?,?,'baru',?)",
            (kode, user_id, nama, tipe, bayar, total),
        )
        pid = cur.lastrowid
        c.executemany(
            "INSERT INTO pesanan_item (pesanan_id, menu_id, nama, harga, qty)"
            " VALUES (?,?,?,?,?)",
            [(pid, r["menu_id"], r["nama"], r["harga"], r["qty"]) for r in items],
        )
        c.execute("DELETE FROM keranjang WHERE user_id=?", (user_id,))
    return kode, pid, total


def pesanan_hari_ini():
    with _conn() as c:
        return c.execute(
            "SELECT * FROM pesanan "
            "WHERE date(dibuat,'localtime')=date('now','localtime') "
            "ORDER BY id DESC"
        ).fetchall()


def pesanan_user(user_id, limit=5):
    with _conn() as c:
        return c.execute(
            "SELECT * FROM pesanan WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


def get_pesanan(pesanan_id):
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM pesanan WHERE id=?", (pesanan_id,)
        ).fetchone()
        items = (
            c.execute(
                "SELECT * FROM pesanan_item WHERE pesanan_id=?", (pesanan_id,)
            ).fetchall()
            if row
            else []
        )
    return row, items


def set_status(pesanan_id, status):
    if status not in STATUS_LIST:
        raise ValueError(f"status tidak dikenal: {status}")
    with _conn() as c:
        c.execute(
            "UPDATE pesanan SET status=? WHERE id=?", (status, pesanan_id)
        )
        return c.execute(
            "SELECT id, kode, user_id, status FROM pesanan WHERE id=?",
            (pesanan_id,),
        ).fetchone()


def cari_kode(kode):
    """Cari pesanan berdasarkan kode (mis. KS-20261009-001)."""
    kode = (kode or "").strip().upper()
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM pesanan WHERE kode=?", (kode,)
        ).fetchone()
        items = (
            c.execute(
                "SELECT * FROM pesanan_item WHERE pesanan_id=?", (row["id"],)
            ).fetchall()
            if row
            else []
        )
    return row, items
