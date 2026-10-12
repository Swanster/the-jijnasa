"""Rate limit + lockout untuk endpoint login admin.

Kenapa modul terpisah: logika keamanan harus bisa diuji tanpa database,
dan jelas terbaca sebagai satu unit yang tidak pecah.

Model: fixed window per IP. Hitungan disimpan in-memory (dict) dengan
batas jumlah entri agar tidak tumbuh tanpa batas dari penyerang dengan
banyak IP. Untuk satu proses gunicorn worker ini cukup; kalau nanti
di-scale ke banyak worker/host, pindahkan ke Redis (lihat CATATAN).

CATATAN SKALA: counter hidup di memori proses. Dengan N worker gunicorn,
efektif ada N counter terpisah, jadi batas sebenarnya N x MAX_ATTEMPTS.
Untuk app demo satu host ini tidak masalah; untuk produksi serius pakai
Redis/Postgres supaya rate limit konsisten lintas worker.
"""

import os
import threading
import time
from collections import OrderedDict

from flask import request

# Default: 5 percobaan gagal per 15 menit, lalu kunci 15 menit.
MAX_ATTEMPTS = int(os.environ.get("ADMIN_MAX_ATTEMPTS", "5"))
WINDOW_SECONDS = int(os.environ.get("ADMIN_WINDOW_SECONDS", "900"))
LOCKOUT_SECONDS = int(os.environ.get("ADMIN_LOCKOUT_SECONDS", "900"))

# Batas entri supaya dict tidak tumbuh tanpa batas.
MAX_ENTRIES = 10000

# Kepercayaan X-Forwarded-For HANYA benar di belakang reverse proxy yang
# menimpa header itu. Tanpa ini, penyerang cukup memutar header tiap request
# untuk mendapat kuota baru setiap kali — lockout jadi tidak berguna.
# Set TRUSTED_PROXY=1 hanya kalau app memang duduk di belakang proxy.
TRUSTED_PROXY = os.environ.get("TRUSTED_PROXY", "") == "1"

_lock = threading.Lock()
# {ip: [count, window_start, locked_until]}
_hits = OrderedDict()


def _now():
    return time.monotonic()


def _prune(now):
    """Buang entri kedaluwarsa. Dipanggil dengan _lock dipegang."""
    stale = [ip for ip, st in _hits.items() if now - st[1] > WINDOW_SECONDS]
    for ip in stale:
        del _hits[ip]
    while len(_hits) > MAX_ENTRIES:
        _hits.popitem(last=False)


def client_ip():
    """IP request untuk keperluan rate limit.

    Default: pakai remote_addr langsung dan abaikan X-Forwarded-For, karena
    header itu bisa dipalsukan klien. Kalau app di belakang reverse proxy,
    set TRUSTED_PROXY=1 supaya IP asli di balik proxy ikut terhitung.
    """
    if TRUSTED_PROXY:
        fwd = request.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"


def status(ip):
    """Kembalikan (allowed, remaining, retry_after_seconds)."""
    now = _now()
    with _lock:
        _prune(now)
        st = _hits.get(ip)
        if not st:
            return True, MAX_ATTEMPTS, 0
        count, start, locked_until = st
        if locked_until > now:
            return False, 0, int(locked_until - now) + 1
        if now - start > WINDOW_SECONDS:
            # Jendela lewat, tapi belum ada percobaan baru: reset diam-diam.
            _hits.pop(ip, None)
            return True, MAX_ATTEMPTS, 0
        remaining = max(0, MAX_ATTEMPTS - count)
        return remaining > 0, remaining, 0


def record_failure(ip):
    """Catat satu kegagalan. Kunci IP kalau sudah habis kuota."""
    now = _now()
    with _lock:
        _prune(now)
        st = _hits.get(ip)
        if not st or now - st[1] > WINDOW_SECONDS:
            st = [0, now, 0.0]
        st[0] += 1
        if st[0] >= MAX_ATTEMPTS:
            st[2] = now + LOCKOUT_SECONDS
        _hits[ip] = st
        _hits.move_to_end(ip)
        return st[0]


def reset(ip):
    """Bersihkan counter IP — dipanggil setelah login berhasil."""
    with _lock:
        _hits.pop(ip, None)


def _reset_for_tests():
    with _lock:
        _hits.clear()