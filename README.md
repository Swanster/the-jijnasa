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

## Deploy (supaya dapat Live URL)

Dijalankan di VPS sendiri dengan **gunicorn di belakang PM2** (proses auto-restart,
persisten antar reboot):

```bash
pip install -r requirements.txt
npm install -g pm2

ADMIN_USER=<username-admin> ADMIN_PASSWORD=<kata-sandi-admin> SECRET_KEY=<acak-kuat> PORT=5000 \
pm2 start gunicorn --name kedai-senja --cwd /path/to/kedai-web -- -b 127.0.0.1:5000 app:app

pm2 save          # simpan daftar proses
pm2 startup       # ikuti perintah yang dicetak agar jalan saat server reboot
```

Di depannya pasang reverse proxy (nginx/caddy) ke `127.0.0.1:5000` untuk domain +
HTTPS — `senja.keysproject.web.id` sudah diarahkan ke sana.

Update kode setelah pull:

```bash
cd /path/to/kedai-web && git pull && pm2 restart kedai-senja
```

Catatan: `ADMIN_PASSWORD` dan `SECRET_KEY` wajib lewat env — kalau `SECRET_KEY`
berganti, sesi admin lama keluar semua.

## Wiring TestSprite (syarat hackathon)

Pilih salah satu:

- **Route A — GitHub App (tanpa ubah repo):** di dashboard TestSprite →
  Settings → GitHub App → install ke repo ini. Hasil tes muncul sebagai
  komentar di PR.
- **Route B — GitHub Actions (sudah disiapkan):** file
  `.github/workflows/testsprite.yml` sudah ada. Tinggal tambah dua secret di
  GitHub repo → Settings → Secrets → Actions:
  - `TESTSPRITE_API_KEY` — API key TestSprite kamu
  - `TESTSPRITE_PROJECT_ID` — project id dari portal 3.0 (mis. `proj_...`)

Keduanya dihitung. Setelah itu, buka satu PR (mis. ubah teks di README) dan
pastikan check TestSprite hijau — **link PR itulah yang disubmit**.

## Cara submit (sebelum 22 Okt 23:59 PT)

1. Pastikan suite sudah di-generate di portal TestSprite 3.0 (terhadap live URL)
2. Buka PR di repo ini yang memicu check TestSprite (harus hijau ✅)
3. Post di Discord TestSprite → `#hackathon-submissions`:
   - link PR
   - live URL
   - email + nama akun TestSprite
   - (opsional) link video demo

## Struktur proyek

```
kedai-web/
├── app.py                 # aplikasi Flask (rute pelanggan + admin)
├── db.py                  # lapisan SQLite (menu, keranjang, pesanan)
├── requirements.txt       # flask + gunicorn
├── .github/workflows/
│   └── testsprite.yml     # check otomatis tiap PR (Route B)
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
