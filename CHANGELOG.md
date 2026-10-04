# Changelog

Setiap perubahan parameter strategi di `config.yaml` dicatat di sini dengan tanggal
dan alasan. Tanpa catatan, forward test tidak bisa dibandingkan dengan simulasi.

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
- Repo: github.com/daijobudesu69/Crypto-REM (publik).
