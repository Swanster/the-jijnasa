#!/usr/bin/env bash
# Jalankan E2E test Camoufox terhadap kedai-web.
#
# PENTING: env var DB aplikasi adalah KEDAI_DB (db.py), bukan DB_PATH.
# Script ini menyalin kedai.db ke /tmp lalu menjalankan gunicorn dengan
# KEDAI_DB menunjuk ke salinan itu, jadi data produksi tidak tersentuh.
set -euo pipefail

cd "$(dirname "$0")"
PORT="${PORT:-8099}"
BASE="http://127.0.0.1:${PORT}"
WORKDB=/tmp/kedai-e2e-run.db
PIDFILE=/tmp/gunicorn-e2e-run.pid

if ss -ltn 2>/dev/null | grep -q ":${PORT} "; then
  echo "Port ${PORT} sudah dipakai — stop proses lain dulu." >&2
  exit 1
fi

# Fail-safe: pastikan app.py/db.py memang baca KEDAI_DB.
# db.py memecah baris, jadi cari nama variabelnya saja (bukan pola-petik penuh).
grep -q 'KEDAI_DB' db.py || {
  echo "PERINGATAN: db.py tidak lagi membaca KEDAI_DB — cek variabel DB sebelum lanjut." >&2
  exit 1
}
# Hard fail kalau ada env var DB yang salah nama dipakai di db.py.
if grep -q 'environ.get("DB_PATH"' db.py; then
  echo "PERINGATAN: db.py memakai DB_PATH — pastikan KEDAI_DB yang diset di runner." >&2
  exit 1
fi

rm -f "$WORKDB"
cp kedai.db "$WORKDB"

# Rate limit dikuji dengan jendela pendek supaya E2E tidak perlu menunggu
# 15 menit produksi. Nilai produksi tetap default 5 percobaan / 900 detik.
# Jendela dibuat == lockout supaya setelah lockout habis, jendela juga
# habis dan kuota ter-reset penuh.
LOCKOUT="${E2E_LOCKOUT_SECONDS:-3}"
WINDOW="${E2E_WINDOW_SECONDS:-3}"

# E2E memakai mode demo hackathon (SHOW_ADMIN_LINK=1) supaya jalur yang
# dipakai juri — tautan Admin di navigasi — ikut tercover.
ADMIN_LINK="${E2E_SHOW_ADMIN_LINK:-1}"

# PENTING: -w 1 (satu worker). Counter rate limit hidup di memori per proses,
# jadi dengan N worker batas efektif jadi N x MAX_ATTEMPTS. Dengan satu worker
# angka yang diuji persis sama dengan yang dikonfigurasi.
KEDAI_DB="$WORKDB" SECRET_KEY=e2e-secret ADMIN_USER=admin ADMIN_PASSWORD=rahasia-e2e \
  ADMIN_LOCKOUT_SECONDS="$LOCKOUT" ADMIN_WINDOW_SECONDS="$WINDOW" \
  SHOW_ADMIN_LINK="$ADMIN_LINK" \
  .venv/bin/gunicorn -w 1 -b "127.0.0.1:${PORT}" app:app \
  --daemon --pid "$PIDFILE" --log-file /tmp/gunicorn-e2e-run.log

cleanup() {
  # -d/--daemon: proses dilepas dari shell, jadi kill cukup lewat pidfile.
  if [ -f "$PIDFILE" ]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 30); do
  curl -sf "${BASE}/healthz" >/dev/null 2>&1 && break
  sleep 0.5
done

if ! curl -sf "${BASE}/healthz" >/dev/null 2>&1; then
  echo "Server tidak siap — lihat /tmp/gunicorn-e2e-run.log" >&2
  exit 1
fi

# Pastikan DB yang disentuh server adalah salinan, bukan produksi.
echo "Server jalan di ${BASE} dengan DB=${WORKDB}"

set +e
ADMIN_LOCKOUT_SECONDS="$LOCKOUT" ADMIN_WINDOW_SECONDS="$WINDOW" \
  ~/.venvs/camofox/bin/python e2e_camoufox.py "$BASE" 2>&1 \
  | grep -v -E 'Downloading|Extracting|%$'
rc="${PIPESTATUS[0]}"
set -e
exit "$rc"