#!/usr/bin/env bash
#
# Deploy kedai-web ke VPS: pull, reset database, restart PM2 dalam mode demo.
#
# Script ini TIDAK menyentuh apa pun di luar folder aplikasi dan backup
# database. Yang bisa hilang hanya isi kedai.db, dan itu selalu dicadangkan
# dulu ke backup/ dengan timestamp.
#
# Pakai:
#   ./deploy.sh              # preview dulu (tidak mengubah apa pun)
#   ./deploy.sh --apply      # jalankan sungguhan
#   ./deploy.sh --keep-db    # jalankan tapi JANGAN reset database
#
# Secret dibaca dari environment. Jangan tulis nilainya di file ini.

set -euo pipefail

cd "$(dirname "$0")"

APP_DIR="$(pwd)"
PM2_NAME="${PM2_NAME:-kedai-senja}"
DB_FILE="${KEDAI_DB:-$APP_DIR/kedai.db}"
BACKUP_DIR="$APP_DIR/backup"
BRANCH="${DEPLOY_BRANCH:-main}"
PORT="${PORT:-5000}"

APPLY=0
RESET_DB=1
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --keep-db) RESET_DB=0 ;;
    -h|--help) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Argumen tidak dikenal: $arg" >&2; exit 1 ;;
  esac
done

say()  { printf '%s\n' "$*"; }
step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
warn() { printf '\033[33mPERINGATAN: %s\033[0m\n' "$*"; }
die()  { printf '\033[31mGAGAL: %s\033[0m\n' "$*" >&2; exit 1; }

# ------------------------------------------------------------ preflight
step "Pengecekan awal"

command -v git >/dev/null || die "git tidak ditemukan"
command -v pm2  >/dev/null || die "pm2 tidak ditemukan — jalankan: npm install -g pm2"
[ -f app.py ]  || die "app.py tidak ada; jalankan dari folder aplikasi"
[ -f db.py ]   || die "db.py tidak ada"
git rev-parse --git-dir >/dev/null 2>&1 || die "bukan folder git"

# Secret wajib sebagai env. Praktik: taruh di ~/.kedai-deploy.env lalu
#   source ~/.kedai-deploy.env && ./deploy.sh --apply
for v in ADMIN_USER ADMIN_PASSWORD SECRET_KEY; do
  [ -n "${!v:-}" ] || die "env $v belum diset — lihat bagian 'Secret' di README"
done
[ "${#SECRET_KEY}" -ge 16 ] || die "SECRET_KEY terlalu pendek (min 16 karakter)"

say "  folder    : $APP_DIR"
say "  database  : $DB_FILE"
say "  branch    : $BRANCH"
say "  pm2       : $PM2_NAME"
say "  port      : $PORT"
say "  reset DB  : $([ "$RESET_DB" -eq 1 ] && echo ya || echo tidak)"
say "  mode      : $([ "$APPLY" -eq 1 ] && echo 'JALAN SEBENARNYA' || echo 'PREVIEW (belum ada yang berubah)')"

if [ "$APPLY" -eq 0 ]; then
  say ""
  say "Ini mode preview. Tidak ada file yang diubah."
  say "Jalankan ulang dengan --apply untuk benar-benar deploy."
  say ""
  say "Ringkasan yang akan terjadi:"
  say "  1. git pull origin $BRANCH"
  [ "$RESET_DB" -eq 1 ] && say "  2. backup $DB_FILE ke $BACKUP_DIR/<timestamp>/"
  [ "$RESET_DB" -eq 1 ] && say "  3. hapus $DB_FILE (akan dibangun ulang: 8 menu seed)"
  say "  4. pm2 restart $PM2_NAME --update-env"
  say "  5. cek http://127.0.0.1:$PORT/healthz"
  exit 0
fi

# ------------------------------------------------------------ git pull
step "1. Menarik kode terbaru"
git fetch origin "$BRANCH"
if git diff --quiet HEAD "origin/$BRANCH"; then
  say "  Sudah paling baru, tidak ada perubahan."
else
  say "  Perubahan yang akan datang:"
  git log --oneline HEAD.."origin/$BRANCH" | sed 's/^/    /'
fi
git pull --ff-only origin "$BRANCH" || die "git pull gagal (branch lokal nyempong? git reset --hard dulu)"

say "  HEAD sekarang: $(git log -1 --oneline)"

# ------------------------------------------------------------ backup + reset db
if [ "$RESET_DB" -eq 1 ]; then
  step "2. Backup database lama"
  STAMP="$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$BACKUP_DIR/$STAMP"
  if [ -f "$DB_FILE" ]; then
    cp -p "$DB_FILE" "$BACKUP_DIR/$STAMP/"
    say "  Disalin ke $BACKUP_DIR/$STAMP/$(basename "$DB_FILE")"
    say "  Restore: cp $BACKUP_DIR/$STAMP/$(basename "$DB_FILE") $DB_FILE"
  else
    say "  $DB_FILE belum ada — dilewati (app akan membuat yang baru)."
  fi

  step "3. Mereset database"
  if [ -f "$DB_FILE" ]; then
    rm -f "$DB_FILE"
    say "  $DB_FILE dihapus."
  fi
  say "  Table & 8 menu seed akan dibuat ulang saat app start."
else
  step "2-3. Database dipertahankan (--keep-db)"
fi

# ------------------------------------------------------------ restart pm2
step "4. Restart aplikasi"
# WAJIB --update-env, tanpa itu PM2 memakai env lama dan SHOW_ADMIN_LINK
# tidak akan aktif.
export SHOW_ADMIN_LINK="${SHOW_ADMIN_LINK:-1}"
export TRUSTED_PROXY="${TRUSTED_PROXY:-1}"
export KEDAI_DB="$DB_FILE"
export PORT="$PORT"

if ! pm2 describe "$PM2_NAME" >/dev/null 2>&1; then
  die "proses pm2 '$PM2_NAME' tidak ada — jalankan: pm2 start gunicorn --name $PM2_NAME -- -b 127.0.0.1:$PORT app:app"
fi

pm2 restart "$PM2_NAME" --update-env >/dev/null || die "pm2 restart gagal"
say "  pm2 restart $PM2_NAME --update-env selesai."

# ------------------------------------------------------------ verifikasi
step "5. Verifikasi"
OK=0
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then OK=1; break; fi
  sleep 1
done

if [ "$OK" -ne 1 ]; then
  warn "server tidak merespons dalam 30 detik."
  warn "cek log: pm2 logs $PM2_NAME --lines 50"
  exit 1
fi

BODY="$(curl -s "http://127.0.0.1:$PORT/healthz")"
say "  /healthz            -> $BODY"

if [ "$SHOW_ADMIN_LINK" = "1" ]; then
  if curl -s "http://127.0.0.1:$PORT/" | grep -q "Admin</a>"; then
    say "  tautan Admin        -> tampil (mode demo)"
  else
    warn "  tautan Admin tidak tampil padahal SHOW_ADMIN_LINK=1"
  fi
else
  if curl -s "http://127.0.0.1:$PORT/" | grep -q "Admin</a>"; then
    warn "  tautan Admin tampil padahal SHOW_ADMIN_LINK bukan 1"
  else
    say "  tautan Admin        -> disembunyikan"
  fi
fi

ADMIN_CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/admin")"
say "  /admin              -> HTTP $ADMIN_CODE (form login)"

say ""
say "Deploy selesai."
say ""
say "Sebelum membuka PR ke GitHub, jalankan test lokal dulu (gratis):"
say "  .venv/bin/python smoke_test.py"
say "  ./run_e2e.sh"
say ""
say "TestSprite tidak jalan otomatis lagi. Untuk menjalankan:"
say "  gh pr edit <nomor> --add-label run-testsprite"