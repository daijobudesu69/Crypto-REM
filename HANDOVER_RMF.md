# HANDOVER — RMF (Rotasi Momentum + Flush Basket), forward test HYPE 200 USD

Ditulis 2026-10-04, di akhir sesi riset. Folder proyek: `C:\Crypto data\Crypto-Momentum Rotations+Flush Basket`. Repo git-nya sendiri, terpisah dari Crypto-Hold-14d dan Crypto-MEX, dan belum ada commit. **Baca file ini dulu** sebelum melanjutkan.

## 0. Ringkasan 1 menit

- **Keputusan user:** forward test di **HYPE (Hyperliquid)**, modal **200 USDC**.
- **Yang live:** hanya **momentum**. **Flush** jalan di **mode paper**, karena sinyalnya butuh candle futures Binance dan itu diblokir dari jaringan user (detail di §5).
- **Ekspektasi** (simulasi harga HYPE, Jul 2024 → Okt 2026, 27 bulan): momentum saja 200 → ±314 USDC, CAGR ±22%, max DD −35%, bulan terburuk −12%. Ini batas atas, karena universe dipilih dari koin yang ramai sekarang.
- **Keyakinan:** momentum saja di HYPE 3/10. RMF lengkap dengan sinyal flush futures 4–5/10.
- **Langkah berikut:** bangun bot HYPE (mode paper dulu, live hanya dinyalakan user). Lihat §9.

## 1. Aturan strategi (versi final)

### A. Rotasi momentum (LIVE)

| Item | Aturan |
|---|---|
| Waktu | Sekali sehari setelah candle harian close: 00:00 UTC = **07:00 WIB** |
| Filter rezim | BTC close harian (HYPE) **> EMA50** dari close harian BTC. Kalau tidak: **jual semua** posisi momentum dan cash |
| Universe | Perp HYPE yang belum delist, dengan **≥60 hari data harian**. Ranking butuh ≥44 hari |
| Ranking | Return 14 hari = close terakhir ÷ close 14 hari sebelumnya − 1. Urutkan dari tertinggi (1 = terkuat) |
| Beli | Isi sampai **10 posisi** dengan koin peringkat 1–10 yang belum dipegang, di open harian berikutnya |
| Jual | Koin dijual kalau peringkatnya **> 15** (buffer), atau filter BTC mati. **Tidak ada TP, tidak ada SL harga** |
| Ukuran | Ekuitas × 0,5 ÷ 10 per koin. Di 200 USDC = **10 USDC per koin**, persis di minimum order HYPE. Kalau ekuitas < 200, tetap 10 USDC (eksposur sedikit > 0,5×) |
| Margin | **Cross margin di subaccount khusus**, tanpa leverage. Isolated paling tinggi 1–2×. **Jangan 3–5× isolated**: saat crash 10 Okt 2025, median altcoin −65% intrabar |
| Rebalance | Hanya jual yang keluar dan beli yang masuk. Posisi lama tidak di-rebalance |

### B. Flush basket (PAPER dulu)

| Item | Aturan |
|---|---|
| Waktu | Setiap close 4h: 07, 11, 15, 19, 23, 03 WIB |
| Sinyal per koin | Close candle sebelumnya ≤ Bollinger bawah (SMA20 − 2σ) **dan** close sekarang > Bollinger bawah, **dan** volume > 1,5× SMA20 volume |
| Syarat | **≥10 koin** memberi sinyal di candle yang sama |
| Entry | Long semua (maks 15, acak) di open 4h berikutnya |
| SL / TP / waktu | Entry ∓ **2 × ATR(14) 4h**, keluar paksa setelah 48 candle (8 hari) |
| Risiko | min(0,5%, 8% ÷ jumlah koin) ekuitas per koin. Total event **tidak dipotong** (bisa > 8% karena minimum order; maks ±11% di simulasi). Hard cap 8% dihapus 2026-10-05, lihat docs/audit/AUDIT_2026-10-05.md Q1 |
| Aturan v2 | Tolak koin kalau risiko yang dipaksa minimum order > 2× target. Total notional (momentum + flush) ≤ 2× ekuitas |
| **Sumber sinyal** | **Harus candle futures Binance.** Sinyal dari candle HYPE: +0,02R per event (tidak ada edge). Dari candle spot Binance: +0,05R, t 0,5 (tidak terbukti). Dari futures Binance lalu dieksekusi di HYPE: **+0,18R** |

### Aturan berhenti (disepakati sebelum mulai)

- DD > 40% dari puncak, **atau**
- 9 bulan berturut-turut kalah dari basket "beli semua koin", **atau**
- Hasil 6 bulan jauh di bawah ekspektasi.

Jangan menilai dari 3 bulan saja: di backtest, 29% periode 3 bulan berakhir rugi.

## 2. Status hari ini (data close 2026-10-03, API HYPE)

- BTC 84.716 > EMA50 78.569, jadi **filter ON**.
- 10 koin peringkat teratas: **GRASS, SAND, SUPER, ZRO, NIL, MINA, INIT, PUMP, SEI, WLD**. Cadangan 11–15: SUI, PURR, MON, NEAR, RUNE.
  - **Koreksi (dicek bot dengan API HYPE, 2026-10-04):** daftar awal tidak memuat INIT karena data lake INIT berhenti di 2026-10-02, jadi INIT tidak eligible. Dengan candle lengkap, INIT peringkat 7 (+49%), SUI turun ke 11, 0G keluar dari 15 besar. BTC 84.716 / EMA50 78.569 sama persis.
- Flush: tidak ada sinyal (maks 3 koin per candle dalam 5 hari terakhir). Event terakhir di backtest: 2026-09-16 20:00 UTC (13 koin).
- Ranking berubah setiap hari, jadi hitung ulang di hari mulai.

## 3. Angka penting

### Ekspektasi di HYPE (yang relevan untuk forward test)

| Jul 2024 → Okt 2026 | 200 USDC → | CAGR | Max DD | Bulan terburuk | Bisa dari rumah? |
|---|---|---|---|---|---|
| **Momentum saja (rencana live)** | **314** | **22%** | **−35%** | −12% | ✅ |
| Momentum + flush sinyal spot Binance | 411 | 38% | −26% | −12% | ✅, tapi edge flush tidak terbukti |
| Momentum + flush sinyal futures Binance | 517 | 53% | −25% | −8% | ❌ perlu VPS yang tidak diblokir |

- Mulai Jan 2025: momentum saja 200 → 287 (DD −26%), dengan flush spot 200 → 321.
- **200 vs 300 USDC:** dalam persen hampir sama (selisih 1–3 poin CAGR). 200 hanya punya bantalan lebih kecil sebelum minimum order memaksa ukuran posisi naik.

### Backtest Binance (angka v1, untuk perbandingan saja; jangan dijadikan ekspektasi)

- 300 USD, Jan 2020 → Okt 2026: 21.693 USD, CAGR 89%, DD −33%. Dengan aturan v2: 20.457, DD −38%.
- **Kenapa lebih tinggi dari HYPE:** Binance punya lebih banyak koin, termasuk listing baru yang pump. Ini sumber bias universe (koin dipilih dari volume per Sep 2026). DD hampir sama karena rugi dibatasi aturan yang sama: rata-rata bulan rugi −4,7% (HYPE) vs −4,1% (Binance); bulan untung +9,1% vs +13,0%.

### Karakter momentum (backtest Binance, 10 koin + buffer 15)

- **Frekuensi:** ±23 koin baru per bulan (±47 order beli+jual), atau ±27 di bulan yang filter-nya aktif. 12 dari 81 bulan full cash.
- **Lama pegang:** rata-rata 6,9 hari, median 4.
- **Pola untung-rugi:** win rate per posisi hanya 38,5%, tapi posisi untung rata-rata +26,7% vs rugi −8,8%.
- **Filter BTC:** ON 53% dari hari, berganti ±24× per tahun.
- **Fee:** di 200 USDC kecil sekali. ±47 order × 10 USDC × 0,045% ≈ 0,2 USDC per bulan.

## 4. Kritik yang sudah dicek (v2)

User menempelkan kritik 15 poin: 11 benar, 3 sebagian, 1 salah. Yang mengubah keputusan:

- **B4:** simulasi akun penuh di HYPE jauh lebih rendah dari Binance (lihat tabel §3).
- **A1–A4:** modal kecil + minimum order 10 USDC mengubah risiko. Di 100 USD tidak layak (risiko event flush sampai 20–48%), jadi user memilih 200.
- **Saran v1 "isolated 3–5×" salah.** Sudah diganti cross margin.
- **B6 (bug):** angka "tanpa filter BTC" tertimpa. Angka yang benar: DD −52% vs −35% dengan filter.
- **B3:** tanpa pemasukan funding, CAGR backtest 90% → 82%.
- **B7:** seed acak tidak berpengaruh (20 seed, DD −32 s/d −34%).
- **B5 salah:** backtest juga memakai syarat ≥60 hari.
- **Belum diuji:** eksekusi telat, SL harga untuk momentum, koin delisted, filter likuiditas.

## 5. Infrastruktur & batasan jaringan user

- **Dari jaringan rumah user:**
  - `api.hyperliquid.xyz` ✅
  - `www.binance.com` (web) ✅
  - `data-api.binance.vision` (spot) ✅
  - `fapi.binance.com` / `api.binance.com` / `www.binance.com/fapi` ❌ (timeout, dites 2026-10-04)
- **Akibatnya:** bot momentum HYPE bisa jalan di PC rumah. Sinyal flush futures butuh VPS.
- **Opsi VPS:**
  - Oracle Free Tier tidak pasti. Binance kabarnya memblokir IP data center Singapura (error 451); Tokyo belum terverifikasi.
  - Oracle mematikan VM gratis yang idle (CPU dan jaringan persentil-95 < 15% selama 7 hari).
  - Home region Oracle tidak bisa diganti.
  - Kalau dicoba, tes dulu dari VM: `curl -s -w " %{http_code}\n" https://fapi.binance.com/fapi/v1/time`.
  - VPS berbayar 5 USD/bulan = 30%/tahun dari modal 200.
- **HYPE:**
  - Margin pakai USDC (bukan USDT), deposit lewat Arbitrum.
  - Minimum order 10 USDC. Perhatikan `szDecimals`.
  - Fee base tier ±0,045% taker / 0,015% maker.
  - Satu koin = satu posisi (one-way). Kalau momentum dan flush memegang koin yang sama, TP/SL flush harus reduce-only seukuran bagian flush.
- **Endpoint data:**
  - `POST https://api.hyperliquid.xyz/info` dengan body `{"type":"candleSnapshot","req":{"coin":"SOL","interval":"1d","startTime":..,"endTime":..}}`.
  - Daftar koin & szDecimals: `{"type":"meta"}`.
- Jalankan di **subaccount terpisah dari MEX 3.0** (MEX live di HYPE, 13 koin). Cek koin yang overlap.

## 6. Peta file

```
HANDOVER_RMF.md            <- file ini
README.md                  <- ringkasan proyek + status data gratis/berbayar
reports/
  RMF_report.html          <- report lengkap v2 (mobile), sumber artifact https://claude.ai/artifact/JDNZ4Y3Lo25RTjEAjiHPgH
  REPORT_TA_EDGE.md        <- riset awal: 1,29 juta kombinasi indikator (15m/1h/4h/1d), finalis, portofolio
  STRATEGY_RMF.md          <- spesifikasi v1 (10% teratas) + catatan update
  strategy_300usdt.png     <- grafik ekuitas/DD/bulanan (Binance, 300 USD)
  tables/*.csv             <- tabel lengkap (single indicators, finalis, momentum grid, breadth, baseline)
research/
  ta.py                    <- library 61 trigger + 37 filter, loader (data lake), konteks breadth/rank/macro
  stage1.py / stage2.py    <- event study & trade sim semua kombinasi
  finalists.py             <- t harian, baseline acak, portofolio, cek HYPE
  xsec.py / xsec_detail.py / xsec_hl.py   <- momentum lintas koin (grid, detail, HYPE)
  buffer_test.py           <- momentum N koin + buffer exit (FINAL: N=10, exit >15)
  breadth.py               <- basket ≥N koin + breadth thrust
  strategy_sim.py          <- simulasi akun 300 USD (Binance) -> sim_variants.pkl
  small_capital.py         <- simulasi dengan minimum order (floor), tolak risiko, gross cap, seed, funding stress
  hl_full.py / hl_diag.py / bn_overlap.py <- simulasi penuh di HYPE + diagnosis selisih venue
  flush_cross.py           <- sinyal futures Binance dieksekusi di HYPE
  flush_spot.py            <- sinyal SPOT Binance dieksekusi di HYPE + simulasi 200 USD
  cap_compare.py / q_extra.py / hl_small.py <- 200 vs 300, 100 USD Binance, 100 USD HYPE
  report_data.py + build_html.py + rmf_template.html + update_v2.py <- generator report HTML
  results/                 <- semua output (parquet/json/log); parquet di-.gitignore
```

- **Data lake** (read-only, tidak dipindah): `C:\Crypto data\backtest data and more\data`. Path-nya hardcoded di `research/ta.py` (`LAKE`).
- **Python:** 3.14, pandas 3, numba. Jalankan dengan `PYTHONIOENCODING=utf-8`, karena ada koin bernama karakter Cina.

## 7. Metodologi singkat

- **Eksekusi:** sinyal di close, entry di open berikutnya. Biaya 0,07% per sisi + funding riil (hanya sebagai biaya, bukan sinyal).
- **Split:** IS 2020–2024 / OOS 2025–2026 (disetujui user untuk riset ini). Pemilihan N=10 dan buffer 15 dilihat dari periode penuh, tapi tetangganya juga positif.
- **Tidak dipakai sebagai sinyal:** OI, funding, LS ratio, premium (permintaan user: data berbayar).
- **Bias yang tidak bisa dihapus:** universe = koin hidup dan ramai per Sep 2026 (Binance top 150, HYPE top 150).

## 8. Preferensi user (penting)

- Bahasa Indonesia, singkat dan to the point, angka dari data sendiri.
- Sebut "HYPE" untuk Hyperliquid, bukan "HL".
- **Jangan menjalankan OOS/holdout/walk-forward baru tanpa izin user.**
- User sering membaca dari HP di luar Claude Code. Untuk dokumen yang perlu dibaca di sana, publish artifact.
- Bot: Claude membangun kode. **API key dan menyalakan mode live dilakukan user sendiri.**

## 9. Langkah berikutnya

> **Update 2026-10-04 (sesi kedua):** infrastruktur bot sudah dibangun, siap GitHub. Lihat §10.

1. ~~**Bot HYPE (momentum live + flush paper)**~~ (selesai di level kode, lihat §10), jalan di PC rumah:
   - Fetch candle 1d semua perp HYPE.
   - Filter BTC > EMA50 → ranking 14 hari → aturan buffer (masuk ≤10, keluar >15).
   - Order 10 USDC per koin di open 07:00 WIB, dengan pembulatan szDecimals.
   - Log PnL harian dan perbandingan dengan basket "beli semua".
   - Mode `paper` (default) vs `live`.
   - Flush paper memakai sinyal spot Binance (`data-api.binance.vision`), dan kalau suatu saat ada akses, futures Binance. Hasilnya dicatat untuk evaluasi.
2. **Evaluasi 6 bulan** dengan aturan berhenti di §1. Bandingkan hasil live dengan simulasi HYPE periode yang sama.
3. **Opsional:**
   - Cari VPS yang lolos tes `fapi.binance.com`, lalu flush live dengan sinyal futures.
   - Uji yang belum diuji: eksekusi telat beberapa jam, SL darurat momentum, filter likuiditas.
4. Setelah folder dipindah, artifact (link di §6) masih menampilkan v2 (300 USD/Binance + update HYPE/100 USD). Update artifact dengan versi 200 USD HYPE hanya kalau user minta.

## 10. Infrastruktur bot (2026-10-04, sesi kedua)

Pola diambil dari Crypto-MEX (hanya referensi, tidak ada kode yang di-import): watcher GitHub Actions, state di-commit ke `state/`, kontrol mode lewat file + workflow, watchdog, Telegram dengan outbox. Panduan: [docs/SETUP.md](docs/SETUP.md). Ringkasan: [README.md](README.md).

- **Jalan di:** GitHub Actions (bukan PC rumah). HYPE API dan `data-api.binance.vision` terjangkau dari runner. `fapi.binance.com` tetap tidak (IP AS kena 451), jadi flush tetap paper dengan sinyal spot.
- **Default aman:** `control/bot.yaml` = `momentum: paper`, `flush: paper`. Live hanya jalan kalau user mengganti ke `live` lewat `control.yml` **dan** secret `HYPE_RMF_AGENT_KEY_66_CHAR` + alamat di `config.yaml` sudah diisi.
- **Menyusul dari user:** secret Telegram, Google Sheets (Apps Script atau service account), API wallet HYPE + subaccount RMF.
- **Verifikasi yang sudah dilakukan:**
  - 53 tes offline lolos. Termasuk rotasi bot vs loop `hl_full.momentum_hl` hari demi hari (110 hari, rezim ON/OFF, koin listing baru): identik.
  - Satu siklus nyata (paper, state di scratchpad, tidak di repo): rezim & peringkat cocok dengan §2 (setelah koreksi INIT), 10 posisi paper dibeli, flush dicek di 150 pair spot (0 sinyal). Siklus harian ±3 menit, siklus idle ±1 detik.
  - Eksekusi live hanya diuji dengan bursa tiruan. **Belum pernah menyentuh akun HYPE sungguhan.** Jalankan `tools/check_live.py` (hanya baca) sebelum menyalakan live.
- **Disamakan dengan riset (permintaan user, sesi kedua):**
  - Universe = daftar riset `hyperliquid_top150.csv` → `config/hype_universe.txt`. Koin delist dibuang otomatis, urutan daftar dipakai untuk memecah seri seperti di riset.
  - Basket "beli semua koin" = definisi `xsec_hl.py`: bobot sama koin eligible (≥60 candle), open → open dikurangi funding, 1×, tanpa filter BTC. Aturan 9 bulan membandingkan **sleeve momentum 1×** (return akun ÷ eksposur aktual hari sebelumnya) dengan basket 1×.
  - "6 bulan jauh di bawah ekspektasi" = return 6 bulan **< −12,5%**: persentil 5 dari 639 jendela 6 bulan simulasi HYPE momentum 200 USDC. Simulasinya saya ulang (`SC.simulate` + `H.momentum_hl`, tanpa flush) dan cocok persis: 200 → 313,7, CAGR 22,2%, DD −35,1%. Distribusi 6 bulan: terburuk −19,2%, p10 −10,9%, median +3,8%, **42,6% jendela negatif**.
  - Breaker DD > 40% di live: otomatis berhenti beli baru (jual tetap jalan). Aturan berhenti lain hanya alarm.
  - Leverage setting cross 1× (eksposur diatur ukuran order 0,5×).
  - Forward test mulai **2026-10-05 07:00 WIB** (`forward_start`), supaya entry pertama tepat di open harian.
- **Repo:** https://github.com/daijobudesu69/Crypto-RMF (publik, menit Actions tidak dibatasi; isi `state/` bisa dibaca publik).
- **Akun live (2026-10-05):** akun utama `0x123bb…a93b` dipakai RMF (MEX live di-hold, pindah ke subaccount lain sebelum aktif lagi). API wallet terpisah **RMF.bot** `0x855127…627c`, berlaku s/d 2027-01-03, secret `HYPE_RMF_AGENT_KEY_66_CHAR`. Pengaman: live hanya menyentuh posisi yang dibuka RMF; posisi asing = berhenti + alarm.
- **Rencana user:** paper 10 hari dulu (hari ke-1 = 2026-10-05), lalu deposit sampai 200 USDC (saldo 2026-10-05: 127,52) dan user menyalakan `momentum: live` sendiri.
- **Telegram & Sheets aktif** sejak 2026-10-05. Format pesan sementara mengikuti heartbeat MEX; format final dibahas nanti. Smoke test: `gh workflow run smoke.yml`.
- **Belum ada:** flush live (butuh VPS lolos `fapi`), update artifact report.
- **Audit infrastruktur 2026-10-05** (rmf-0.1.2): 8 perbaikan + blokir MEX, lihat [docs/audit/AUDIT_2026-10-05.md](docs/audit/AUDIT_2026-10-05.md). Tindakan user ada di §5 laporan itu (hapus MEX.bot, cek ekuitas hari live pertama, API wallet baru sebelum 2026-12-20, keputusan Q1/Q2).
