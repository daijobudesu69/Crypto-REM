# Changelog

Setiap perubahan parameter strategi di `config.yaml` dicatat di sini dengan tanggal
dan alasan. Tanpa catatan, forward test tidak bisa dibandingkan dengan simulasi.

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
