# Setup bot RMF

Urutan yang disarankan. Langkah 1–2 cukup untuk mulai paper. Telegram, Sheets, dan
HYPE bisa ditambahkan kapan saja tanpa mengubah kode: bot otomatis memakainya begitu
secret-nya ada.

| Langkah | Wajib untuk | Status |
|---|---|---|
| 1. Repo GitHub + Actions | semua | |
| 2. Cek paper jalan | semua | |
| 3. Telegram | notifikasi | menyusul |
| 4. Google Sheets | cermin log | menyusul, opsional |
| 5. HYPE API wallet + subaccount | live momentum | menyusul |
| 6. Nyalakan live | live momentum | dilakukan user sendiri |

---

## 1. Repo GitHub

Repo: **https://github.com/daijobudesu69/Crypto-RMF** (publik). Publik dipilih supaya
menit Actions tidak dibatasi (watcher nonstop ±4.500 menit/bulan; repo privat hanya
dapat 2.000). Konsekuensinya: isi `state/` (ekuitas, posisi, order) bisa dibaca
siapa saja. Secret tetap aman.

- Workflow meminta izin tulis sendiri (`permissions: contents: write`), jadi tidak
  perlu mengubah setting repo.
- Cron menyalakan `RMF bot` otomatis. Untuk mulai segera:

```bash
gh workflow run bot.yml --repo daijobudesu69/Crypto-RMF -f mode=loop
```

- Forward test mulai `forward_start` di `config.yaml` (2026-10-05, 07:00 WIB).
  Sebelum itu bot hanya mencatat run, tanpa trading.

## 2. Cek paper jalan

- Tab Actions → `RMF bot` → log `siklus #1`. Siklus harian butuh ±3–5 menit (candle
  1d ±180 perp HYPE dengan jeda rate limit). Siklus tanpa pekerjaan ±1 detik.
- `state/equity.csv` dapat satu baris per hari setelah 00:02 UTC (07:02 WIB).
- Lokal, tanpa mengubah state apa pun:

```bash
python run_status.py --flush
```

## 3. Telegram

1. Chat `@BotFather` → `/newbot` → simpan token.
2. Kirim satu pesan ke bot, lalu buka
   `https://api.telegram.org/bot<TOKEN>/getUpdates` dan ambil `chat.id`.
3. Simpan sebagai secret:

```bash
gh secret set --repo daijobudesu69/Crypto-RMF TELEGRAM_BOT_TOKEN
```

```bash
gh secret set --repo daijobudesu69/Crypto-RMF TELEGRAM_CHAT_ID
```

Yang dikirim: ringkasan harian momentum (±07:02–07:15 WIB), event dan exit flush,
perubahan mode, error (maks 1× per 6 jam per jenis), aturan berhenti, watchdog.
Pesan yang gagal terkirim disimpan di `state/outbox.json` dan dicoba ulang 48 jam.

## 4. Google Sheets (opsional)

Pilih **satu**:

**A. Apps Script (paling mudah, tanpa kunci).** Buka spreadsheet → Extensions →
Apps Script → tempel `docs/apps_script.gs` → Deploy → New deployment → Web app,
Execute as: *Me*, Who has access: *Anyone* → salin URL.

```bash
gh secret set --repo daijobudesu69/Crypto-RMF GSHEET_WEBHOOK_URL
```

**B. Service account.** Buat service account di Google Cloud, aktifkan Sheets API,
unduh kunci JSON, bagikan spreadsheet ke `client_email` dengan akses Editor.

```bash
gh secret set --repo daijobudesu69/Crypto-RMF GOOGLE_SERVICE_ACCOUNT_JSON < key.json
```

```bash
gh secret set --repo daijobudesu69/Crypto-RMF GSHEET_SPREADSHEET_ID
```

Tab yang ditulis: `equity`, `orders`, `flush_trades`, `flush_signals` (hanya event).
Gagal menulis ke Sheets tidak pernah menggagalkan run.

## 5. HYPE: akun + API wallet

Status 2026-10-05:
- API wallet **RMF.bot** `0x855127eb9d86d715aae469c399c26d31ef85627c`, terpisah dari
  MEX.bot, berlaku s/d 2027-01-03. Kuncinya di secret `HYPE_RMF_AGENT_KEY_66_CHAR`.
- Akun RMF = akun utama `0x123bb2a1fe74395a57081d48077c28c9ca55a93b` (keputusan user).
  MEX (live di-hold) pindah ke subaccount lain **sebelum** dinyalakan lagi.
- Deposit sampai 200 USDC setelah 10 hari paper.

Aturan:
- Akun RMF harus khusus RMF. Bot hanya menyentuh posisi yang dibukanya sendiri
  (tercatat di `state/momentum_live.json`). Ada posisi lain (mis. MEX) = live
  berhenti dengan alarm, tanpa order. `flatten` hanya menutup posisi milik RMF.
- Ekuitas = seluruh saldo akun (mode unified: USDC spot + PnL). Ukuran order
  ikut saldo itu, jadi isi akun hanya dengan modal RMF.
- API wallet maks 180 hari. Sebelum kedaluwarsa: buat yang baru, ganti isi secret,
  perbarui `agent_address` dan `agent_valid_until` di `config.yaml`.
- Cek hanya-baca kapan saja dengan smoke test (di bawah).

## Smoke test (kapan saja)

Cek Telegram, Sheets (tab kosong diisi dari CSV), kunci API wallet HYPE (hanya
baca: alamat agent, akun utama, masa berlaku, daftar subaccount), dan sumber
data. Hasil dikirim ke Telegram. Tidak ada order.

```bash
gh workflow run smoke.yml --repo daijobudesu69/Crypto-RMF
```

## 6. Menyalakan live (user sendiri)

```bash
gh workflow run control.yml --repo daijobudesu69/Crypto-RMF -f momentum=live
```

- Berlaku ≤ ~10 menit. Telegram mengonfirmasi "mode sekarang".
- Kalau dinyalakan di tengah hari, live langsung membeli top 10 hari itu di harga
  saat itu (memakai peringkat hari itu yang sama dengan buku paper).
- Buku paper tetap jalan sebagai pembanding eksekusi.

Rem dan pembatalan:

```bash
gh workflow run control.yml --repo daijobudesu69/Crypto-RMF -f momentum=manage
```

```bash
gh workflow run control.yml --repo daijobudesu69/Crypto-RMF -f momentum=flatten
```

```bash
gh workflow run control.yml --repo daijobudesu69/Crypto-RMF -f momentum=paper
```

- `manage`: tanpa beli baru, jual tetap sesuai aturan.
- `flatten`: tutup semua posisi subaccount tiap siklus sampai mode diganti.
- Breaker DD > 40%: live otomatis berhenti membeli. Reset (mis. setelah deposit/withdraw):

```bash
gh workflow run control.yml --repo daijobudesu69/Crypto-RMF -f reset_breaker=true
```

### Status TAHAN (posisi ditutup di luar bot)

Selama mode live/manage/flatten, setiap siklus (±10 menit) bot membandingkan posisi
akun dengan catatan posisi RMF. Kalau ada posisi RMF yang hilang atau mengecil
padahal bot tidak menjualnya (tutup manual, likuidasi, ADL, delisting):

- Telegram langsung dikirim: "🛑 RMF — posisi ditutup di luar bot".
- Bot **tidak membeli apa pun** sampai diaktifkan kembali, termasuk di siklus harian.
- Sisa posisi RMF tetap dijual sesuai aturan (peringkat > 15, filter BTC OFF).
- Buku paper tetap jalan seperti biasa (pembanding: "kalau tidak diintervensi").

Intervensi darurat jadi cukup: tutup posisi di aplikasi HYPE. Tidak perlu mengubah
mode. Aktifkan kembali (pembelian normal mulai siklus harian berikutnya):

```bash
gh workflow run control.yml --repo daijobudesu69/Crypto-RMF -f resume=true
```

Dari HP: Actions → RMF control → Run workflow → centang `resume`.

## Flush dengan sinyal futures (opsional, butuh VPS)

Sinyal terbaik (+0,18R per event) butuh candle futures Binance. `fapi.binance.com`
diblokir dari rumah user dan dari runner GitHub (IP AS, HTTP 451). Di VPS yang lolos:

```bash
curl -s -w " %{http_code}\n" https://fapi.binance.com/fapi/v1/time
```

Kalau 200: jalankan `run_cycle.py` di VPS tiap 10 menit (cron) dengan
`flush.signal_source: binance_futures`. Jangan jalankan watcher GitHub dan VPS
bersamaan di state yang sama.

## Jalan di PC (alternatif tanpa GitHub)

```bash
pip install -r requirements.txt
```

Task Scheduler Windows: jalankan `python run_cycle.py` tiap 10 menit di folder repo.
State ditulis ke `state/`. Dengan GitHub aktif, jangan jalankan ini bersamaan.
