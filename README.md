# Crypto Momentum Rotations + Flush Basket (RMF)

> **Mulai di sini:** [HANDOVER_RMF.md](HANDOVER_RMF.md) (keputusan, aturan, angka) dan
> [docs/SETUP.md](docs/SETUP.md) (GitHub, Telegram, Sheets, HYPE).

Forward test di **HYPE (Hyperliquid)**, modal **200 USDC**:

- **Momentum** (harian, 07:00 WIB): filter BTC > EMA50, pegang 10 koin dengan return
  14 hari tertinggi, jual kalau peringkat > 15. Paper selalu jalan; live di subaccount
  khusus hanya kalau user menyalakannya.
- **Flush** (4h, **paper**): ≥10 koin serentak menembus balik Bollinger bawah dengan
  volume > 1,5×, long maks 15 koin, SL/TP 2 ATR, keluar paksa 8 hari. Sinyal dari
  candle spot Binance (futures diblokir dari rumah dan dari GitHub).
- **Aturan berhenti:** DD > 40%, atau 9 bulan berturut-turut sleeve momentum 1× kalah
  dari basket "beli semua koin" 1×, atau return 6 bulan < −12,5% (persentil 5
  simulasi HYPE). Bot menandai dan mengirim alarm; keputusan di tangan user.
- Universe = daftar riset (top 150 HYPE per Sep 2026). Forward test mulai 2026-10-05.
- Buku paper **pembanding** dengan universe bulanan (`rolling_monthly`: masuk top 150
  volume, keluar > 200, refresh tanggal 1 tiap bulan ±07:02 WIB), menyala sejak
  2026-10-09 (`universe.compare_rolling` di `config.yaml`). Hanya paper, tidak menyentuh
  buku utama, aturan berhenti, alarm, Sheets, atau live. Parameter belum diuji.

> [!WARNING]
> Ekspektasi momentum di HYPE (simulasi Jul 2024 → Okt 2026): 200 → ±314 USDC, CAGR
> ±22%, DD −35%, keyakinan 3/10. Itu batas atas karena universe dipilih dari koin yang
> ramai sekarang. Jangan menilai dari 3 bulan: di backtest 29% periode 3 bulan rugi.

## Cara kerja

```
GitHub Actions (bot.yml)  cron -> watcher hidup ~5,5 jam, siklus tiap 10 menit
  └─ run_cycle.py
       ├─ momentum: sekali per hari UTC (>= 00:02 UTC)
       │    data 1d semua perp HYPE -> rezim + peringkat (state/momentum_view.json)
       │    -> buku paper -> [live: subaccount HYPE, kalau mode live/manage/flatten]
       ├─ flush: sekali per candle 4h
       │    spot Binance 150 pair -> event? -> buku paper (SL/TP/waktu di candle HYPE)
       └─ Telegram (outbox) + log CSV di state/ (+ cermin Google Sheets)
  └─ tools/save_state.sh  commit state/ ke repo
watchdog.yml   alarm + nyalakan watcher baru kalau state tidak diperbarui > 90 menit
control.yml    ganti mode: gh workflow run control.yml -f momentum=live
ci.yml         tes offline (gerbang) + cek konektivitas harian
```

| Mode momentum (`control/bot.yaml`) | Paper | Live |
|---|---|---|
| `paper` (default) | ✅ | — |
| `live` | ✅ | jual + beli |
| `manage` | ✅ | jual saja |
| `flatten` | ✅ | tutup semua |
| `off` | — | — |

## Perintah

```bash
python run_status.py --flush
```

Melihat rezim, top 15, dan rencana jual/beli hari ini tanpa mengubah state.

```bash
python -m pytest -q tests --ignore=tests/test_connectivity.py
```

```bash
python run_cycle.py
```

Satu siklus penuh (dipakai watcher). Tanpa secret Telegram, pesan dicetak ke layar.

## Struktur

| Path | Isi |
|---|---|
| `config.yaml` | parameter strategi (= riset final), biaya, aturan berhenti, alamat live |
| `control/bot.yaml` | mode momentum/flush, dibaca tiap siklus |
| `rmf/momentum.py`, `rmf/flush.py` | logika strategi murni (tanpa jaringan) |
| `rmf/indicators.py` | EMA/ATR/Bollinger, rumus sama dengan helper riset |
| `rmf/hype.py`, `rmf/binance.py` | data publik HYPE (rate limit) dan Binance |
| `rmf/book.py` | buku paper (fee + slippage = 0,07%/sisi, funding riil HYPE) |
| `rmf/live.py` | eksekusi live via SDK resmi HYPE (cross margin, cloid "RMF") |
| `rmf/jobs.py` | job harian momentum dan job 4h flush |
| `rmf/stoprules.py` | aturan berhenti |
| `rmf/notify.py`, `rmf/sheets.py` | Telegram (outbox) dan Google Sheets |
| `run_cycle.py`, `run_status.py`, `run_watchdog.py` | entry point |
| `tools/` | simpan/sinkron state, kontrol, `check_live.py` (diagnostik live, hanya baca) |
| `tests/` | tes offline, termasuk rotasi bot vs loop riset hari demi hari |
| `state/` | log dan state forward test ([state/README.md](state/README.md)) |
| `research/`, `reports/` | riset asal (lihat di bawah) |

---

## Riset asal (Crypto-TA-Edge)

Riset edge **indikator teknikal dengan data gratis saja**: VWAP, SMC/ICT, MA, volume, oscillator, Ichimoku, candle, breadth, dan macro gratis. Proyek ini terpisah dari Crypto-Hold-14d dan MEX.

- Tidak memakai **OI, funding (sebagai sinyal), long/short ratio, atau premium index**. Funding hanya dihitung sebagai **biaya** riil di PnL.
- Data riset dibaca dari data lake `C:\Crypto data\backtest data and more\data` (tidak ikut di repo). Bot tidak membutuhkannya.
- Hasil lengkap: [reports/REPORT_TA_EDGE.md](reports/REPORT_TA_EDGE.md), spesifikasi: [reports/STRATEGY_RMF.md](reports/STRATEGY_RMF.md)

### Status data: gratis atau berbayar

| Data | Dipakai | Gratis untuk live / forward test? | Tag di hasil |
|---|---|---|---|
| Candle OHLCV (Binance, HYPE) | Ya | ✅ Gratis (REST/websocket) | `ohlcv` |
| Taker buy volume (delta, CVD) | Ya | ✅ Gratis di kline Binance. ⚠️ Di HYPE tidak ada di candle, jadi harus direkam sendiri dari websocket trades (gratis, tapi perlu recorder) | `taker` |
| Cross-section 150 koin (breadth, ranking kekuatan relatif) | Ya | ✅ Gratis (perlu ambil candle ~150 koin) | `cross` |
| Fear & Greed (alternative.me), market cap stablecoin (DefiLlama) | Ya | ✅ Gratis API, harian | `macro` |
| Funding rate | Hanya sebagai biaya | — | — |
| Open interest | ❌ SKIP | Permintaan user: dianggap berbayar | — |
| Long/short ratio, premium index | ❌ SKIP | Turunan data derivatif, tidak dipakai | — |

### Pipeline (`research/`)

| Script | Isi |
|---|---|
| `ta.py` | Library 61 trigger + 37 filter (data gratis) + loader + konteks cross-section/macro |
| `stage1.py <tf>` | Event study semua trigger × 0/1/2 filter × long/short × 4 horizon |
| `stage2.py <tf>` | Simulasi trade nyata (6 skema exit ATR) untuk semua indikator tunggal + 200 kombinasi terbaik |
| `finalists.py` | t harian (anti double-count), baseline entry acak, portofolio, cek silang di HYPE |
| `xsec.py` | Momentum/reversal lintas koin dan trend MA tingkat portofolio |
| `breadth.py` | Versi basket (≥N koin serentak) dan breadth thrust |
| `report.py` | Tulis tabel hasil ke `reports/` |

Split: in-sample 2020–2024 untuk memilih, out-of-sample 2025–2026 untuk cek (disetujui user 2026-10-04). Script riset butuh `features.py` dan `trade_sim.py` dari data lake (`backtest data and more/research`).
