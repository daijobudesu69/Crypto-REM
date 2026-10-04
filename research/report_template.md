# Backtest semua indikator favorit — data GRATIS saja (tanpa OI & funding)

Dibuat 2026-10-04. Proyek: `C:\Crypto data\Crypto-Momentum Rotations+Flush Basket`. Proyek ini terpisah dari Crypto-Hold-14d dan MEX. Kode ada di `research/`, tabel lengkap (CSV) di `reports/tables/`.

## TL;DR

__TLDR__

## 1. Data: mana yang gratis, mana yang di-skip

| Data | Dipakai di backtest? | Gratis untuk forward test / live? | Tag |
|---|---|---|---|
| Candle OHLCV Binance & HYPE | ✅ | ✅ Gratis (REST / websocket) | `ohlcv` |
| Taker buy volume (delta, CVD, taker flow) | ✅ | ✅ Gratis di kline Binance. ⚠️ **HYPE: tidak ada di candle**, jadi harus direkam sendiri dari websocket trades (gratis, tapi perlu recorder) | `taker` |
| Cross-section 150 koin (breadth % koin > EMA50, ranking return 7 hari) | ✅ | ✅ Gratis, cukup ambil candle semua koin | `cross` |
| Fear & Greed (alternative.me), market cap stablecoin (DefiLlama) | ✅ (lag 1 hari) | ✅ Gratis API harian | `macro` |
| Funding rate | Hanya sebagai **biaya** di PnL (disetujui) | — | — |
| **Open interest** | ❌ **SKIP** (permintaan user: berbayar) | — | — |
| **Long/short ratio, premium index** | ❌ **SKIP** (data derivatif) | — | — |

Setiap strategi di tabel hasil diberi tag di kolom **Data**. Kalau ada `taker`, strategi itu tidak bisa langsung dijalankan di HYPE tanpa recorder sendiri.

## 2. Metode

- **Universe:** 150 perp USDT Binance yang masih aktif per Sep 2026 (tanpa stablecoin dan TradFi). Konsekuensinya ada *survivorship bias* dan *selection bias*: koin dipilih dari volume terbaru, jadi koin yang baru pump ikut masuk.
- **Eksekusi:** sinyal dihitung di close bar, entry di open bar berikutnya (tanpa lookahead). **Biaya:** 0,07% per sisi (fee + slippage) ditambah funding riil sebagai biaya.
- **Split (disetujui):** in-sample (IS) 2020–2024 untuk memilih, out-of-sample (OOS) 2025-01 → 2026-10 untuk cek.
- **61 trigger + 37 filter.** Grup trigger: **MA** (EMA 9/21, 20/50, 50/200, golden cross SMA, harga×EMA50/200, ribbon, pullback EMA20) · **Trend** (Supertrend, PSAR, Heikin-Ashi, Donchian 20/55, MACD, MACD-0, ADX/DI, Ichimoku TK & kumo) · **Oscillator** (RSI 30/70, RSI 50, RSI(2), divergence RSI, Stoch, Williams %R, CCI, MFI, z-score) · **Volatilitas** (BB revert/breakout, Keltner, TTM squeeze, NR7, inside bar) · **Candle** (engulfing, pin bar) · **VWAP** (harian cross, ±1σ breakout, ±2σ revert, mingguan, bulanan, reclaim) · **Volume** (spike, reversal, climax, dry-up breakout, OBV) · **Taker flow** (delta surge, absorption, CVD divergence, delta flip) · **SMC/ICT** (BOS, CHoCH, FVG retest, OB retest, sweep swing, sweep/break PDH-PDL, sweep/break PWH-PWL, Asia range break/sweep).
- **Filter:** tren (EMA200, EMA50>200, ribbon, slope, daily/weekly trend, Ichimoku cloud), rezim BTC, VWAP harian/mingguan, ADX, RSI/MACD/Supertrend side, struktur SMC, discount/premium, volume tinggi/rendah, volatilitas expanding/contracting, taker flow, OBV, sesi Asia/Eropa/US, weekend, **breadth**, **kekuatan relatif (rank)**, BTC 1 hari, **Fear & Greed**, **pertumbuhan stablecoin**.
- **Tahap 1:** setiap trigger × 0/1/2 filter × long/short × 4 horizon × 4 TF, total **__TOT1__ uji**. Lolos kalau excess return di atas drift koin positif di IS & OOS, t ≥ 3/2, positif di ≥ 55%/50% koin, dan positif di ≥ 70% tahun.
- **Tahap 2:** semua indikator sendirian ditambah 200 kombinasi terbaik per TF × 6 skema exit ATR × 150 koin, total **__TOT2__ trade tersimulasi**.
- **Tahap 3 (finalis):** t-stat **per hari** (semua koin di hari yang sama digabung supaya tidak double count), baseline **entry acak** dengan exit yang sama, portofolio 1% risiko (maks 10 posisi), dan cek silang di candle **HYPE**.
- **Tambahan (portofolio):** momentum/reversal lintas koin dan trend MA (1.334 konfigurasi), basket breadth (672 konfigurasi), breadth thrust (197 konfigurasi).

{COUNTS}

## 3. Baseline: entry acak (masuk setiap kali flat, exit sama)

Indikator yang bagus harus **mengalahkan baseline ini**, bukan sekadar > 0.

{BASELINE}

Di 15m dan 1h, entry acak rugi −0,1 s/d −0,25R per trade karena biaya. Di 1d, long acak positif karena koin yang masih hidup cenderung naik (survivorship). Jadi "long 1d positif" belum tentu edge.

## 4. Indikator favorit SENDIRIAN

Exit terbaik dipilih di IS, lalu dicek di OOS.

{SINGLE_COUNT}

**Per grup** (✅ = positif di IS & OOS, mengalahkan baseline acak di keduanya, dan t > 2 di keduanya):

{FAMILY}

**Indikator tunggal terbaik** (diurutkan dari selisih vs baseline di OOS):

{BEST_SINGLES}

<details><summary>Matriks lengkap LONG: avgR IS / OOS per TF (✅ lolos semua syarat, · positif tapi tidak signifikan / kalah baseline)</summary>

{MAT_LONG}

</details>

<details><summary>Matriks lengkap SHORT</summary>

{MAT_SHORT}

</details>

## 5. Kombinasi terbaik (finalis) dan uji anti-double-count

Ada {N_FIN} finalis (lolos IS & OOS: avgR ≥ 0,08, PF ≥ 1,2, t per trade ≥ 3). Syarat lolos akhir: **t harian ≥ 2 di IS dan OOS**, dengan minimal 20 hari OOS. **Yang lolos: {N_SURV}.**

{FINALISTS}

__FIN_NOTES__

## 6. Strategi tingkat portofolio (data candle gratis)

{XSEC}

__XSEC_NOTES__

## 7. Breadth (≥N koin serentak) dan breadth thrust

__BREADTH_NOTES__

## 8. Kesimpulan & rekomendasi

__CONCLUSION__

## Batasan

- Sekitar 1,2 juta uji berarti banyak hasil bagus muncul karena kebetulan. Penyaring utamanya adalah OOS, t harian, baseline acak, breadth koin, dan konsistensi per tahun.
- Survivorship dan selection bias: universe dipilih dari koin hidup dengan volume tinggi per Sep 2026. Ini menguntungkan semua strategi **long**, terutama momentum di 2025–2026.
- Cek di HYPE **bukan data independen**, karena harga Binance dan HYPE berkorelasi 0,999. Cek ini hanya membuktikan bahwa strategi tetap jalan di venue dan biaya funding HYPE.
- Filter `macro` (Fear & Greed, stablecoin) adalah rezim lambat. Trade-nya bergerombol, jadi jumlah hari independennya kecil (lihat kolom Hari OOS).
