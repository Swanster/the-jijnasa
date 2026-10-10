# PRD — Kedai Kopi Senja (Web Order App)

**Purpose of this document:** source material for TestSprite test generation.
All behavior described here is implemented in the live app at
`https://senja.keysproject.web.id/`.

## 1. Overview

Kedai Kopi Senja is a public web ordering app for a coffee shop. Two roles:

- **Customer** — no account, no login. A browser session (cookie) identifies
  the visitor and keeps their cart.
- **Admin** — password-protected panel at `/admin` (password comes from the
  server env `ADMIN_PASSWORD`; never hardcode or display it).

Site language is Indonesian. UI text, menu names, and error messages are in
Indonesian.

## 2. Features & expected behavior

### 2.1 Menu (page `/`)
- Menu is grouped into exactly three categories shown in this order:
  **Kopi**, **Non-Kopi**, **Snack**.
- Only **active** items are visible to customers; inactive items must not
  appear anywhere on the customer-facing menu.
- Each item shows: name, description (may be empty), price in IDR
  (format `Rp 18.000` — dot as thousands separator), and a quantity form.
- Quantity input: default 1, min 1, max 20 (client-side).
- If every item is inactive, the menu area shows an empty-state message
  ("Menu belum tersedia"), never a broken page.

### 2.2 Cart (right-side panel on `/`)
- Adding an item keeps the chosen quantity; adding the same item again
  increments the previous quantity.
- Each line can be removed; removing does not affect other lines.
- Cart shows a running total (`sum(price × qty)`).
- **Persistence:** the cart survives page navigation and server restarts —
  it is stored server-side, keyed by the visitor's session.
- Empty cart shows an empty-state message, and `/checkout` redirects to `/`
  instead of showing a form.

### 2.3 Checkout (GET/POST `/checkout`)
- Form fields: **Nama pemesan** (required, max 80 chars), **tipe pesanan**
  (`ambil` | `antar`), **pembayaran** (`tunai` | `qris`).
- Submitting with an empty name is rejected: user is returned to the checkout
  page with the error message "Nama pemesan wajib diisi."
- Invalid `tipe`/`bayar` values fall back to defaults (`ambil`, `tunai`)
  instead of erroring.
- On success: the order is created, the cart is cleared, and the user is
  redirected to `/sukses/<kode>`.

### 2.4 Order code (receipt `/sukses/<kode>`)
- Format: `KS-YYYYMMDD-NNN` (example `KS-20261009-001`).
- `NNN` is a **daily sequence starting at 001, persistent across restarts**
  (not reset when the server restarts).
- Codes are **unique**; two checkouts happening at the same time must never
  receive the same code.
- Receipt shows: order code, customer name, tipe, payment method, item lines
  with line totals, grand total, and current status label.

### 2.5 Order status (GET `/status?kode=...`)
- Customer enters the code received at checkout.
- Valid code → shows customer name, total, item lines, and a status badge.
- Unknown code → error message "Kode <X> tidak ditemukan." (page still
  renders, HTTP 200, no crash).
- The page reflects status changes made by the admin **without** any action
  from the customer other than re-submitting/refreshing the lookup.

### 2.6 Admin login (`/admin`)
- Password form; correct password → redirect to `/admin/dashboard`.
- Wrong password → redirected back to the login page with
  "Kata sandi salah." — no stack trace, no information about the password.
- The login page must **not** display, hint at, or prefill the password.
- Unauthenticated access to any `/admin/*` page (except the login form
  itself) redirects to `/admin`; POST endpoints are equally protected.
- `/admin/logout` ends the session and returns to `/`.

### 2.7 Admin dashboard (`/admin/dashboard`)
- **Pesanan Hari Ini:** orders created today, newest first, with columns:
  kode + nama, tipe + bayar, total, status badge, and a status selector.
- Changing a status accepts only these five values:
  `baru` → "Baru masuk", `dimasak` → "Sedang dimasak", `siap` →
  "Siap diambil/diantar", `selesai` → "Selesai", `batal` → "Dibatalkan".
  Any other value is rejected/ignored.
- **Kelola Menu:** every item (active and inactive) with price editing and
  an activate/deactivate toggle.
- **Tambah Menu Baru:** name (required), category (one of kopi/nonkopi/
  snack), price (integer > 0 required), description (optional). Missing name
  or non-positive price is rejected and no row is created.
- A newly added menu item immediately appears on the customer menu page.

## 3. Business rules summary

1. Cart total and order total are computed server-side from current prices.
2. Creating an order clears the customer's cart exactly once.
3. Order codes are unique and daily-sequenced; item lines are snapshotted
   (name/price/qty copied into the order), so later price edits do not alter
   past orders.
4. Only active items can be added to the cart.

## 4. Out of scope (do not test as if implemented)

- Real payment processing (QRIS/tunai are labels only).
- Real delivery tracking, maps, or courier flow.
- Customer accounts, password reset, email/SMS notifications.
- Search, coupons, discounts, reviews, multi-currency (IDR only).

## 5. Non-functional expectations

- All pages return HTTP 200 for normal flows (forms reject via redirect +
  error message, not 5xx).
- Unknown order code → 200 with error message; unknown receipt URL → 404.
- Works in a modern browser at mobile width (single-column layout).
- `/healthz` returns `ok` with HTTP 200.
