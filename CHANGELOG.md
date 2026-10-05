# Changelog

Setiap perubahan parameter strategi di `config.yaml` dicatat di sini dengan tanggal
dan alasan. Tanpa catatan, forward test tidak bisa dibandingkan dengan simulasi.

## rmf-0.1.5 — 2026-10-05

Infrastruktur; aturan strategi tidak berubah.
- Watcher menyalakan penggantinya sendiri: cron GitHub di repo ini hanya terpicu
  tiap 3-6 jam (terukur 4-5 Okt; watchdog terakhir jalan 06:17 UTC), sehingga
  watcher yang selesai pukul 13:02 UTC tidak punya pengganti. Saat anggaran
  waktunya habis, watcher (mode loop) dispatch bot.yml lewat GITHUB_TOKEN; run
  baru antre di concurrency group dan mulai begitu job lama selesai. Cron dan
  watchdog tetap cadangan.

## rmf-0.1.4 — 2026-10-05

Alat uji; aturan strategi tidak berubah.
- Canary (`canary.yml`, `run_canary.py`, `rmf/canary.py`), pola Crypto-MEX: manual,
  1 trade ~10 USDC beli IOC lalu jual reduce-only lewat jalur order live, setiap
  langkah + komponen ekuitas saat posisi terbuka ke Telegram. Ditolak kalau mode
  live/manage/flatten. Tidak menulis state/.

## rmf-0.1.3 — 2026-10-05

Rem darurat baru; aturan strategi tidak berubah. Keputusan pemilik 2026-10-05.
- Status TAHAN: setiap siklus (live/manage/flatten) posisi akun dibandingkan dengan
  catatan posisi RMF. Posisi RMF yang hilang/mengecil tanpa dijual bot (tutup manual,
  likuidasi, ADL, delisting) -> Telegram SAAT ITU JUGA, lalu tidak ada pembelian sama
  sekali sampai pemilik mengaktifkan kembali (`control.yml -f resume=true`). Jual
  sesuai aturan tetap jalan; buku paper tidak terpengaruh.
- Kontrol: input baru `resume` (control.yml, control/bot.yaml, tools/set_control.py).

## rmf-0.1.2 — 2026-10-05

Audit infrastruktur ([docs/audit/AUDIT_2026-10-05.md](docs/audit/AUDIT_2026-10-05.md)).
Aturan strategi momentum tidak berubah. Flush (paper), keputusan pemilik:
- Q1: hard cap risiko event 8% DIHAPUS, sizing kembali sama dengan simulasi riset
  (small_capital.simulate): risiko per koin = min(0,5%, 8% / n koin), total event
  tidak dipotong (bisa > 8% karena minimum order). Simulasi ulang
  (research/q1_event_cap.py): 200 -> 410,6 tanpa cap vs 397,5 dengan cap 8%;
  20 seed: cap tidak pernah lebih baik. Risiko event maks di simulasi 11-12,6%.
- Q2: tetap (pilih acak 15 dulu, baru buang yang tidak bisa diperdagangkan).
- F1: candle 1d koin yang gagal di-fetch tidak lagi membuat posisinya dijual;
  siklus dicoba ulang sampai 03:00 UTC, lalu jalan dengan alarm.
- F2: order beli live yang timeout tapi terisi tetap tercatat milik RMF (tidak HALT).
- F3: pesan Telegram yang ditolak permanen (400) tidak menahan alarm di belakangnya.
- F4: alarm 14 hari sebelum API wallet kedaluwarsa (RMF.bot: 2027-01-03).
- F5: ekuitas live di mode unifiedAccount = spot USDC + uPnL (perp accountValue
  diabaikan). Wajib dicocokkan dengan UI HYPE di hari live pertama.
- F6: siklus terakhir watcher selalu selesai sebelum timeout job.
- F7: catatan harian yang terputus diselesaikan sebelum hari baru.
- F8: run_status.py --flush menilai bar yang diminta.
- F9: actions/checkout@v5, actions/setup-python@v6 (Node 24).
- Pesan harian: baris penutup "Pesan ini muncul 1× sehari ..." dihapus (permintaan pemilik).
- Blokir MEX: `execution.blocked_agents` (MEX.bot) -> alarm harian selama masih
  terdaftar di akun RMF. Crypto-MEX diblokir dari akun ini di repo MEX.

## rmf-0.1.1 — 2026-10-05

Infrastruktur saja; aturan strategi tidak berubah.
- Watcher bangun tepat 2m10s setelah close candle 4h (00:02:10 UTC = 07:02 WIB untuk
  momentum), bukan menunggu jadwal 10 menit berikutnya. Hari ke-1: siklus 07:10,
  pesan ±07:16 WIB.
- Funding basket diambil SETELAH order dan pesan terkirim (basket hanya dipakai aturan
  berhenti). Diukur dengan data asli: pesan terkirim 138 detik setelah siklus mulai,
  pencatatan selesai di detik ke-326. Perkiraan pesan sampai ±07:04–07:05 WIB.
  Kalau job mati di tengah, pencatatan dilanjutkan di siklus berikutnya.
- Flush: sinyal dinilai di candle yang dimaksud walau data sudah memuat candle lebih baru.
- Live: hanya menyentuh posisi yang dibuka RMF; akun = akun utama (keputusan user).
- Pesan Telegram sementara memakai tata letak heartbeat MEX; smoke test (smoke.yml).

## rmf-0.1.0 — 2026-10-04

- Infrastruktur bot: momentum harian (paper + live opsional) dan flush 4h (paper),
  watcher GitHub Actions, kontrol mode, watchdog, Telegram, Google Sheets, tes offline.
- Parameter = versi final riset (HANDOVER_RMF.md §1). Modal 200 USDC.
- Disamakan dengan riset atas permintaan user:
  - Universe = daftar riset `hyperliquid_top150.csv` (config/hype_universe.txt),
    koin delist dibuang otomatis. Mode `rolling` tersedia tapi tidak dipakai.
  - Basket "beli semua koin" = definisi `research/xsec_hl.py`: bobot sama koin
    eligible, open -> open dikurangi funding, 1x. Dibandingkan dengan sleeve
    momentum 1x (return akun / eksposur aktual).
  - "6 bulan jauh di bawah ekspektasi" = return 6 bulan < −12,5%, persentil 5 dari
    639 jendela 6 bulan simulasi HYPE momentum 200 USDC (simulasi 200 -> 313,7,
    diulang dan cocok persis). Terburuk −19,2%, median +3,8%, 42,6% jendela negatif.
- Forward test mulai 2026-10-05 00:00 UTC (07:00 WIB).
- Repo: github.com/daijobudesu69/Crypto-RMF (publik).
