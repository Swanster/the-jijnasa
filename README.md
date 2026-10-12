# ☕ Kedai Kopi Senja — Web Order App

Aplikasi pemesanan kopi via web + panel admin. Dibangun untuk **TestSprite Hackathon Season 4**:
setiap pull request diuji otomatis oleh TestSprite terhadap URL live aplikasi ini.

**Live URL:** `https://senja.keysproject.web.id/`

## Apa aplikasinya

Kedai Kopi Senja adalah web app pemesanan untuk kedai kopi fiktif — versi web dari
bot Telegram "Kedai Kopi Senja" (portfolio bot saya). Pelanggan bisa:

- Lihat menu (Kopi / Non-Kopi / Snack) dan tambah ke keranjang
- Checkout: isi nama, pilih ambil/diantar, pilih tunai/QRIS
- Terima **kode pesanan** (cth: `KS-20261009-001`, nomor urut persisten per hari)
- Pantau status pesanan: Baru masuk → Sedang dimasak → Siap → Selesai

Admin (login username + kata sandi) bisa:

- Lihat pesanan hari ini dan ubah statusnya
- **Riwayat pesanan lintas tanggal** (`/admin/pesanan`): cari kode
  (`KS-20261009-001`), filter rentang tanggal, paginasi, klik kode untuk
  lihat detail item + ubah status — data di-query langsung dari SQLite
  setiap request, halaman admin selalu `Cache-Control: no-store`
- Kelola menu: tambah, ubah harga, aktif/nonaktif
- **Muat Ulang Aplikasi** (Pemeliharaan): graceful reload worker gunicorn
  via SIGHUP — sesi admin tetap sah (cookie + `SECRET_KEY` tidak berubah),
  semua data dari database. Hanya aktif di bawah gunicorn (mode dev
  melaporkan tidak tersedia).

Data tersimpan di **SQLite** — menu, keranjang, pelanggan, dan pesanan semuanya
persisten (tidak hilang saat restart).

## Yang di-cover test suite TestSprite

Suite di-generate di portal TestSprite 3.0 terhadap live URL di atas:

1. **Alur pelanggan end-to-end** — buka menu → tambah item ke keranjang → checkout
   → terima kode pesanan → cek status dengan kode tersebut
2. **Validasi form** — checkout tanpa nama ditolak; tambah menu tanpa nama/harga ditolak
3. **Alur admin** — login salah ditolak; login benar → tambah menu → menu muncul di
   halaman pelanggan; ubah status pesanan → terlihat di halaman status pelanggan
4. **Persistensi** — kode pesanan unik & berurutan; keranjang tidak hilang antar halaman

## Jalankan lokal (dev)

```bash
pip install -r requirements.txt
python app.py
# buka http://127.0.0.1:5000
```

Atur username & kata sandi admin lewat env `ADMIN_USER` (default: `admin`) dan
`ADMIN_PASSWORD` — tanpa `ADMIN_PASSWORD`, login admin dinonaktifkan (semua
percobaan ditolak). Setelah logout, username & kata sandi harus diisi ulang.

```bash
# contoh dengan env sendiri
ADMIN_USER=bu-admin ADMIN_PASSWORD=rahasia123 SECRET_KEY=acak-kuat PORT=5000 python app.py
```

## Keamanan login admin

Tautan "Admin" **disembunyikan** dari navigasi publik secara default — panel
tidak perlu diiklankan ke pengunjung. Akses tetap lewat URL langsung `/admin`.

Yang menahan brute force adalah **rate limit**, bukan menyembunyikan URL:

| Env | Default | Arti |
| --- | --- | --- |
| `ADMIN_MAX_ATTEMPTS` | `5` | percobaan gagal sebelum dikunci |
| `ADMIN_WINDOW_SECONDS` | `900` | panjang jendela (15 menit) |
| `ADMIN_LOCKOUT_SECONDS` | `900` | lama IP terkunci |
| `TRUSTED_PROXY` | `0` | set `1` **hanya** kalau di belakang reverse proxy |
| `SHOW_ADMIN_LINK` | `0` | set `1` untuk menampilkan kembali tautan Admin |

Contoh ERROR message: `Kata sandi salah. Sisa percobaan: 3.` lalu
`Terlalu banyak percobaan. Coba lagi dalam 15 menit.`

Untuk **demo hackathon** (panel perlu dinilai juri), tampilkan tautannya:

```bash
SHOW_ADMIN_LINK=1 ADMIN_USER=... ADMIN_PASSWORD=... python app.py
```

Batas yang perlu diketahui:

- Counter hidup di memori proses. Dengan N worker gunicorn, batas efektif jadi
  N x `ADMIN_MAX_ATTEMPTS`, dan restart proses mengembalikan kuota.
  Untuk multi-worker atau produksi serius, pindahkan counter ke Redis.
- `X-Forwarded-For` **tidak** dipercaya kecuali `TRUSTED_PROXY=1`. Kalau header
  itu dipercaya tanpa proxy yang menimpanya, penyerang cukup memutar header tiap
  request untuk lolos lockout.

## Deploy (supaya dapat Live URL)

Dijalankan di VPS sendiri dengan **gunicorn di belakang PM2** (proses auto-restart,
persisten antar reboot):

```bash
pip install -r requirements.txt
npm install -g pm2

# SHOW_ADMIN_LINK=1 → tautan "Admin" tampil di navigasi (untuk demo hackathon,
# supaya juri bisa menemukan panel). Hapus untuk produksi: panel tetap bisa
# diakses via URL /admin, dan rate limit tetap berlaku.
ADMIN_USER=<username-admin> ADMIN_PASSWORD=<kata-sandi-admin> SECRET_KEY=<acak-kuat> \
PORT=5000 SHOW_ADMIN_LINK=1 TRUSTED_PROXY=1 \
pm2 start gunicorn --name kedai-senja --cwd /path/to/kedai-web -- -b 127.0.0.1:5000 app:app

pm2 save          # simpan daftar proses
pm2 startup       # ikuti perintah yang dicetak agar jalan saat server reboot
```

`TRUSTED_PROXY=1` memang warranted di sini: aplikasi duduk di belakang reverse
proxy nginx/caddy yang menimpa `X-Forwarded-For`. Tanpa itu, semua pengunjung
berbalik ke satu IP sehingga rate limit ikut ikutnya — satu penyerang yang
mengunci IP itu juga mengunci semua orang lain.

> Penting: `ADMIN_PASSWORD` untuk demo publik harus kuat. Tautan Admin yang
> terlihat membuat panel mudah ditemukan — rate limit yang menahan, bukan
> menyembunyikan. Pakai password acak panjang, jangan `admin123`.

Di depannya pasang reverse proxy (nginx/caddy) ke `127.0.0.1:5000` untuk domain +
HTTPS — `senja.keysproject.web.id` sudah diarahkan ke sana.

Update kode setelah pull:

```bash
cd /path/to/kedai-web && git pull && pm2 restart kedai-senja
```

Atau pakai `deploy.sh` — ia menarik kode, mencadangkan DB, me-restart PM2 dengan
env demo (`SHOW_ADMIN_LINK=1`), lalu memverifikasi `/healthz`:

```bash
./deploy.sh                      # preview dulu, tidak mengubah apa pun
./deploy.sh --apply              # jalankan sungguhan
./deploy.sh --apply --keep-db    # jangan reset database

# secret dibaca dari env; simpan di file privat di luar repo
source ~/.kedai-deploy.env && ./deploy.sh --apply
```

Database tidak ikut `git pull` (`*.db` ada di `.gitignore`). `kedai.db` yang
dihapus akan dibangun ulang otomatis oleh `init_db()`: 6 tabel + 8 menu seed.
Backup lama disimpan di `backup/<timestamp>/`.

> Penting: `ADMIN_PASSWORD` dan `SECRET_KEY` wajib lewat env — kalau `SECRET_KEY`
> berubah, sesi admin lama keluar semua.

## Wiring TestSprite (syarat hackathon)

Pilih salah satu:

- **Route A — GitHub App (tanpa ubah repo):** di dashboard TestSprite →
  Settings → GitHub App → install ke repo ini. Hasil tes muncul sebagai
  komentar di PR.
### Route B — GitHub Actions (sudah disiapkan, tapi hemat token)

File `.github/workflows/testsprite.yml` sudah ada. Tambah dua secret di
GitHub repo → Settings → Secrets → Actions:

- `TESTSPRITE_API_KEY` — API key TestSprite kamu
- `TESTSPRITE_PROJECT_ID` — project id dari portal 3.0 (mis. `proj_...`)

Check **tidak jalan otomatis** di setiap PR. Token TestSprite terbatas, jadi
test hanya jalan kalau PR diberi label `run-testsprite`:

```bash
gh pr edit <nomor> --add-label run-testsprite
# atau lewat web: PR -> Labels -> run-testsprite
```

Hapus label tersebut (atau jangan pernah pasang) = nol token terpakai. Ini
memantau langkah sebelum membuka PR, jadi Anda tahu test sudah hijau tanpa
membakar token saat masih banyak yang akan dirombak:

```bash
.venv/bin/python smoke_test.py   # 53 check, tanpa browser
./run_e2e.sh                     # 44 check Camoufox (start/stop server otomatis)
```

Setelah yakin, baru buka PR + pasang label. **Link PR itulah yang disubmit.**

## Cara submit (sebelum 22 Okt 23:59 PT)

1. Pastikan suite sudah di-generate di portal TestSprite 3.0 (terhadap live URL)
2. Jalankan test lokal — gratis: `./run_e2e.sh` (44 check) dan
   `.venv/bin/python smoke_test.py` (53 check)
3. Buka PR di repo ini, lalu pasang label `run-testsprite` agar check jalan
   (harus hijau ✅)
4. Post di Discord TestSprite → `#hackathon-submissions`:
   - link PR
   - live URL
   - email + nama akun TestSprite
   - (opsional) link video demo

## Struktur proyek

```
kedai-web/
├── app.py                 # aplikasi Flask (rute pelanggan + admin)
├── db.py                  # lapisan SQLite (menu, keranjang, pesanan)
├── rate_limit.py          # rate limit + lockout login admin
├── requirements.txt       # flask + gunicorn
├── deploy.sh              # deploy ke VPS (backup DB + restart PM2)
├── smoke_test.py          # 53 check tanpa browser
├── e2e_camoufox.py        # 44 check lewat browser Camoufox
├── run_e2e.sh             # runner E2E (server start/stop otomatis)
├── test_demo_admin_link.py  # mode tautan admin (demo vs produksi)
├── .github/workflows/
│   └── testsprite.yml     # check TestSprite, jalan saat label run-testsprite
└── README.md
```

## Skenario demo 3 menit (untuk juri / klien)

1. Buka live URL → tambah 2 Kopi Susu Senja ke keranjang → checkout sebagai "Budi"
2. Catat kode pesanan → buka "Cek Status" → status "Baru masuk"
3. Login admin → ubah status jadi "Sedang dimasak"
4. Refresh halaman status pelanggan → berubah jadi "Sedang dimasak" ✨
5. Tunjukkan PR di GitHub dengan check TestSprite hijau

---
Dibuat oleh **Suprapto** — brand [JIJNASA](https://jijnasa.id) · *"Keingintahuan yang membangun."*
