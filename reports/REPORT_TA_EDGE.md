# Backtest semua indikator favorit — data GRATIS saja (tanpa OI & funding)

Dibuat 2026-10-04. Proyek: `C:\Crypto data\Crypto-Momentum Rotations+Flush Basket`. Proyek ini terpisah dari Crypto-Hold-14d dan MEX. Kode ada di `research/`, tabel lengkap (CSV) di `reports/tables/`.

## TL;DR

1. **1,29 juta uji kombinasi dan 424 juta trade tersimulasi.** Isinya 61 indikator (MA, VWAP, SMC/ICT, volume, oscillator, Ichimoku, candle, taker flow) × 0/1/2 filter × 4 TF. Semua memakai **data gratis saja**: tanpa OI, tanpa funding sebagai sinyal, tanpa LS ratio.
2. **15m dan 1h: tidak ada edge.** Tidak ada indikator yang positif sendirian di IS & OOS (long 0/61 di 15m dan 1h; short 0/61 di 15m dan 2/61 di 1h). Dari ratusan kombinasi terbaik, **0 lolos** syarat finalis di 15m. VWAP, SMC, RSI, BB, dan EMA cross di TF kecil semuanya kalah setelah biaya.
3. **4h/1d: indikator trend + trailing stop sedikit mengalahkan entry acak** (+0,05 s/d +0,13R per trade). Contohnya Keltner/BB breakout 1d, VWAP bulanan 4h, Ichimoku TK 4h, dan Donchian-55 short 4h. Edge-nya kecil dan DD portofolionya besar.
4. **Kombinasi:** 21 finalis lolos IS & OOS per trade, tapi setelah trade **di hari yang sama digabung, hanya 3 yang lolos** (semuanya harian long, pakai data gratis F&G / stablecoin / breadth). Hari independennya sedikit (54–143 hari OOS).
5. **Edge paling meyakinkan dari data gratis:** **momentum lintas koin** (long 20% koin dengan return 14 hari terkuat, hanya saat BTC > EMA50, rebalance harian). Excess vs basket bobot sama: +0,28%/hari IS (t 3,7), +0,39%/hari OOS (t 3,7), +0,30%/hari di HYPE (t 4,0). ⚠️ DD −60% dan bias universe besar.
6. **Flush basket harga-saja** (≥10–20 koin serentak BB revert + volume tinggi, 4h): +0,16 s/d +0,28R per event, OOS positif. Ini sekitar setengah kualitas versi OI (CLR-1). **OI memang menambah edge**, tapi tanpa OI masih ada sisa.
7. **Tidak ada edge:** momentum short, reversal, trend MA short, dan breadth thrust.

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
- **Tahap 1:** setiap trigger × 0/1/2 filter × long/short × 4 horizon × 4 TF, total **1,293,322 uji**. Lolos kalau excess return di atas drift koin positif di IS & OOS, t ≥ 3/2, positif di ≥ 55%/50% koin, dan positif di ≥ 70% tahun.
- **Tahap 2:** semua indikator sendirian ditambah 200 kombinasi terbaik per TF × 6 skema exit ATR × 150 koin, total **424 juta trade tersimulasi**.
- **Tahap 3 (finalis):** t-stat **per hari** (semua koin di hari yang sama digabung supaya tidak double count), baseline **entry acak** dengan exit yang sama, portofolio 1% risiko (maks 10 posisi), dan cek silang di candle **HYPE**.
- **Tambahan (portofolio):** momentum/reversal lintas koin dan trend MA (1.334 konfigurasi), basket breadth (672 konfigurasi), breadth thrust (197 konfigurasi).

| TF | Uji stage 1 (trigger × filter × arah × horizon) | Lolos stage 1 | Trade tersimulasi stage 2 |
|---|---|---|---|
| 15m | 338,864 | 768 | 305,501,064 |
| 1h | 338,385 | 1,012 | 87,027,229 |
| 4h | 325,816 | 1,057 | 25,896,913 |
| 1d | 290,257 | 606 | 5,449,383 |
| **Total** | **1,293,322** | | **423,874,589** |

## 3. Baseline: entry acak (masuk setiap kali flat, exit sama)

Indikator yang bagus harus **mengalahkan baseline ini**, bukan sekadar > 0.

| TF | Long IS | Long OOS | Short IS | Short OOS |
|---|---|---|---|---|
| 15m | -0.25 … -0.09 | -0.25 … -0.08 | -0.20 … -0.07 | -0.20 … -0.06 |
| 1h | -0.14 … -0.05 | -0.13 … -0.04 | -0.08 … -0.02 | -0.09 … -0.03 |
| 4h | -0.09 … -0.01 | -0.07 … +0.00 | -0.05 … -0.01 | -0.03 … +0.00 |
| 1d | -0.00 … +0.18 | -0.04 … +0.10 | -0.13 … -0.04 | -0.03 … +0.02 |

Di 15m dan 1h, entry acak rugi −0,1 s/d −0,25R per trade karena biaya. Di 1d, long acak positif karena koin yang masih hidup cenderung naik (survivorship). Jadi "long 1d positif" belum tentu edge.

## 4. Indikator favorit SENDIRIAN

Exit terbaik dipilih di IS, lalu dicek di OOS.

| TF | Long positif IS & OOS | Short positif IS & OOS | Long > baseline acak (IS & OOS) | Short > baseline acak |
|---|---|---|---|---|
| 15m | 0 / 61 | 0 / 61 | 14 | 15 |
| 1h | 0 / 61 | 2 / 61 | 17 | 30 |
| 4h | 27 / 59 | 32 / 59 | 32 | 41 |
| 1d | 52 / 59 | 20 / 59 | 23 | 31 |

**Per grup** (✅ = positif di IS & OOS, mengalahkan baseline acak di keduanya, dan t > 2 di keduanya):

| Grup | 15m | 1h | 4h | 1d |
|---|---|---|---|---|
| MA | 0/16 (OOS rata2 -0.08) | 0/16 (OOS rata2 -0.03) | 4/16 (OOS rata2 +0.00) | 3/16 (OOS rata2 +0.10) |
| Trend/momentum | 0/20 (OOS rata2 -0.08) | 0/20 (OOS rata2 -0.03) | 4/20 (OOS rata2 +0.03) | 1/20 (OOS rata2 +0.09) |
| Oscillator | 0/18 (OOS rata2 -0.08) | 0/18 (OOS rata2 -0.05) | 2/18 (OOS rata2 -0.01) | 1/18 (OOS rata2 +0.02) |
| Volatilitas | 0/12 (OOS rata2 -0.08) | 0/12 (OOS rata2 -0.04) | 3/12 (OOS rata2 +0.04) | 2/12 (OOS rata2 +0.04) |
| Candle | 0/4 (OOS rata2 -0.08) | 0/4 (OOS rata2 -0.05) | 0/4 (OOS rata2 +0.03) | 0/4 (OOS rata2 -0.03) |
| VWAP | 0/12 (OOS rata2 -0.08) | 0/12 (OOS rata2 -0.02) | 2/12 (OOS rata2 +0.02) | 0/12 (OOS rata2 +0.05) |
| Volume | 0/10 (OOS rata2 -0.08) | 0/10 (OOS rata2 -0.03) | 0/10 (OOS rata2 +0.03) | 0/10 (OOS rata2 +0.05) |
| Taker flow (delta/CVD) | 0/8 (OOS rata2 -0.07) | 0/8 (OOS rata2 -0.04) | 2/8 (OOS rata2 +0.01) | 0/8 (OOS rata2 +0.09) |
| SMC/ICT | 0/22 (OOS rata2 -0.07) | 0/22 (OOS rata2 -0.04) | 2/18 (OOS rata2 +0.00) | 0/18 (OOS rata2 +0.04) |

**Indikator tunggal terbaik** (diurutkan dari selisih vs baseline di OOS):

| TF | Arah | Indikator | Grup | Exit | n IS | avgR IS | n OOS | avgR OOS | Baseline acak OOS | Data |
|---|---|---|---|---|---|---|---|---|---|---|
| 1d | long | keltner_breakout | Volatilitas | sl2_trail3 | 1,492 | +0.31 | 1,290 | +0.23 | +0.10 | ohlcv |
| 4h | long | vwap_month_x | VWAP | sl2_trail3 | 9,656 | +0.07 | 10,127 | +0.12 | +0.00 | ohlcv |
| 1d | long | bb_breakout | Volatilitas | sl2_trail3 | 1,661 | +0.26 | 1,461 | +0.21 | +0.10 | ohlcv |
| 4h | long | ichi_tk_x | Trend/momentum | sl2_trail3 | 4,180 | +0.09 | 3,545 | +0.11 | +0.00 | ohlcv |
| 4h | short | donchian_55 | Trend/momentum | sl1.5_tp4_trail2.5 | 4,674 | +0.10 | 5,454 | +0.07 | -0.02 | ohlcv |
| 1d | short | ma_ribbon_align | MA | sl1.5_tp4_trail2.5 | 1,312 | +0.12 | 1,423 | +0.10 | +0.02 | ohlcv |
| 4h | short | bb_breakout | Volatilitas | sl1.5_tp4_trail2.5 | 9,532 | +0.09 | 9,014 | +0.06 | -0.02 | ohlcv |
| 4h | short | ichi_tk_x | Trend/momentum | sl2_trail3 | 4,391 | +0.14 | 5,421 | +0.07 | +0.00 | ohlcv |
| 1d | long | price_x_ema50 | MA | sl2_trail3 | 1,748 | +0.21 | 1,694 | +0.17 | +0.10 | ohlcv |
| 4h | short | smc_choch | SMC/ICT | sl1.5_tp4_trail2.5 | 10,676 | +0.05 | 10,261 | +0.05 | -0.02 | ohlcv |
| 4h | long | delta_surge | Taker flow (delta/CVD) | sl2_trail3 | 3,191 | +0.13 | 3,575 | +0.07 | +0.00 | taker |
| 4h | short | macd_x | Trend/momentum | sl1.5_tp4_trail2.5 | 16,690 | +0.04 | 16,116 | +0.04 | -0.02 | ohlcv |

<details><summary>Matriks lengkap LONG: avgR IS / OOS per TF (✅ lolos semua syarat, · positif tapi tidak signifikan / kalah baseline)</summary>

| Grup | Indikator | 15m | 1h | 4h | 1d |
|---|---|---|---|---|---|
| MA | ema_x_9_21 | -0.10 / -0.10 | -0.05 / -0.03 | +0.03 / -0.06 | +0.27 / +0.18 · |
| MA | ema_x_20_50 | -0.09 / -0.09 | -0.03 / -0.02 | +0.06 / +0.06 ✅ | +0.27 / +0.11 · |
| MA | ema_x_50_200 | -0.08 / -0.07 | -0.02 / -0.04 | +0.02 / -0.02 | +0.16 / +0.14 · |
| MA | sma_x_50_200 | -0.08 / -0.09 | -0.04 / -0.02 | -0.04 / -0.01 | +0.11 / +0.01 · |
| MA | price_x_ema50 | -0.10 / -0.09 | -0.05 / -0.04 | +0.04 / +0.05 ✅ | +0.21 / +0.17 ✅ |
| MA | price_x_ema200 | -0.10 / -0.10 | -0.05 / +0.01 | +0.04 / +0.09 · | +0.21 / +0.12 · |
| MA | ma_ribbon_align | -0.09 / -0.09 | -0.03 / -0.06 | +0.05 / -0.06 | +0.24 / +0.18 · |
| MA | ema20_pullback | -0.09 / -0.08 | -0.04 / -0.06 | +0.07 / -0.00 | +0.13 / -0.07 |
| Trend/momentum | supertrend_flip | -0.10 / -0.09 | -0.04 / -0.05 | +0.04 / +0.05 · | +0.28 / +0.28 · |
| Trend/momentum | psar_flip | -0.09 / -0.09 | -0.06 / -0.05 | +0.02 / +0.04 · | +0.23 / +0.14 ✅ |
| Trend/momentum | ha_flip | -0.10 / -0.09 | -0.07 / -0.06 | -0.01 / +0.00 | +0.18 / +0.08 · |
| Trend/momentum | donchian_20 | -0.10 / -0.09 | -0.05 / -0.04 | +0.03 / +0.04 · | +0.24 / +0.20 · |
| Trend/momentum | donchian_55 | -0.09 / -0.08 | -0.04 / -0.03 | +0.00 / +0.06 · | +0.25 / +0.30 · |
| Trend/momentum | macd_x | -0.10 / -0.10 | -0.05 / -0.05 | +0.02 / +0.03 · | +0.30 / +0.06 · |
| Trend/momentum | macd_zero_x | -0.10 / -0.09 | -0.04 / -0.03 | +0.03 / -0.04 | +0.32 / +0.15 · |
| Trend/momentum | adx_di_x | -0.10 / -0.09 | -0.05 / -0.05 | +0.02 / +0.01 · | +0.09 / -0.02 |
| Trend/momentum | ichi_tk_x | -0.08 / -0.08 | -0.02 / -0.05 | +0.09 / +0.11 ✅ | +0.41 / +0.37 · |
| Trend/momentum | ichi_kumo_break | -0.10 / -0.09 | -0.03 / -0.02 | +0.03 / +0.04 · | +0.25 / +0.17 · |
| Oscillator | rsi_30_70_rev | -0.08 / -0.07 | -0.08 / -0.05 | -0.04 / -0.00 | +0.05 / +0.05 · |
| Oscillator | rsi_50_x | -0.10 / -0.10 | -0.06 / -0.06 | +0.03 / +0.03 ✅ | +0.26 / +0.14 ✅ |
| Oscillator | rsi2_extreme | -0.08 / -0.08 | -0.05 / -0.05 | -0.03 / -0.05 | +0.10 / +0.11 · |
| Oscillator | rsi_divergence | -0.08 / -0.08 | -0.08 / -0.03 | -0.01 / -0.08 | +0.06 / -0.09 |
| Oscillator | stoch_rev | -0.09 / -0.08 | -0.07 / -0.05 | -0.03 / -0.01 | +0.11 / +0.07 · |
| Oscillator | willr_rev | -0.10 / -0.09 | -0.07 / -0.05 | -0.02 / +0.00 | +0.17 / +0.09 · |
| Oscillator | cci_rev | -0.09 / -0.09 | -0.07 / -0.05 | -0.01 / +0.02 | +0.18 / +0.08 · |
| Oscillator | mfi_rev | -0.09 / -0.08 | -0.07 / -0.06 | -0.05 / +0.03 | +0.12 / +0.01 · |
| Oscillator | zscore_revert | -0.09 / -0.08 | -0.07 / -0.06 | -0.03 / -0.02 | +0.21 / -0.07 |
| Volatilitas | bb_revert | -0.09 / -0.08 | -0.08 / -0.05 | -0.04 / +0.01 | +0.09 / +0.06 · |
| Volatilitas | bb_breakout | -0.10 / -0.09 | -0.05 / -0.03 | +0.03 / +0.08 · | +0.26 / +0.21 ✅ |
| Volatilitas | keltner_breakout | -0.09 / -0.08 | -0.04 / -0.04 | +0.05 / +0.06 ✅ | +0.31 / +0.23 ✅ |
| Volatilitas | squeeze_fire | -0.11 / -0.09 | -0.08 / -0.04 | +0.02 / +0.15 · | +0.21 / +0.52 · |
| Volatilitas | nr7_breakout | -0.10 / -0.09 | -0.06 / -0.05 | -0.03 / -0.01 | +0.17 / +0.02 · |
| Volatilitas | inside_bar_break | -0.09 / -0.09 | -0.07 / -0.06 | -0.03 / +0.02 | +0.17 / -0.01 |
| Candle | engulfing | -0.11 / -0.10 | -0.09 / -0.06 | -0.03 / +0.07 | +0.16 / +0.13 · |
| Candle | pinbar | -0.10 / -0.08 | -0.08 / -0.05 | -0.03 / -0.01 | +0.10 / +0.05 · |
| VWAP | vwap_x | -0.10 / -0.09 | -0.06 / -0.04 | -0.00 / +0.02 | +0.17 / +0.07 · |
| VWAP | vwap_1sd_break | -0.09 / -0.09 | -0.05 / -0.04 | +0.00 / +0.02 · | +0.17 / +0.07 · |
| VWAP | vwap_2sd_revert | -0.09 / -0.08 | -0.06 / -0.03 | -0.02 / +0.02 | +0.17 / +0.07 · |
| VWAP | vwap_week_x | -0.09 / -0.11 | -0.04 / +0.01 | +0.05 / +0.06 ✅ | +0.21 / +0.09 · |
| VWAP | vwap_month_x | -0.10 / -0.08 | -0.03 / +0.06 | +0.07 / +0.12 ✅ | +0.21 / +0.07 · |
| VWAP | vwap_reclaim | -0.11 / -0.09 | -0.06 / -0.05 | +0.00 / +0.02 · | +0.18 / +0.07 · |
| Volume | vol_spike_candle | -0.08 / -0.08 | -0.02 / -0.02 | +0.06 / +0.17 · | +0.10 / +0.38 · |
| Volume | vol_spike_reversal | -0.08 / -0.08 | -0.00 / +0.04 | +0.03 / +0.04 · | +0.79 / -0.17 |
| Volume | vol_climax | -0.07 / -0.08 | -0.04 / -0.02 | -0.01 / +0.07 | +0.97 / +0.03 · |
| Volume | vol_dryup_break | -0.12 / -0.10 | -0.07 / -0.01 | -0.04 / -0.05 | +0.19 / +0.24 · |
| Volume | obv_break_20 | -0.10 / -0.09 | -0.05 / -0.04 | +0.00 / +0.07 · | +0.26 / +0.10 · |
| Taker flow (delta/CVD) | delta_surge ⚠️taker | -0.09 / -0.08 | -0.04 / -0.03 | +0.13 / +0.07 ✅ | +0.14 / +0.06 · |
| Taker flow (delta/CVD) | delta_absorption ⚠️taker | -0.08 / -0.08 | -0.05 / -0.04 | +0.03 / +0.03 · | +0.27 / +0.54 · |
| Taker flow (delta/CVD) | cvd_divergence ⚠️taker | -0.09 / -0.08 | -0.07 / -0.05 | -0.05 / -0.03 | +0.17 / +0.08 · |
| Taker flow (delta/CVD) | delta_flip ⚠️taker | -0.10 / -0.09 | -0.06 / -0.05 | -0.01 / +0.01 | +0.19 / -0.06 |
| SMC/ICT | smc_bos | -0.10 / -0.09 | -0.07 / -0.04 | -0.02 / -0.04 | +0.21 / +0.14 · |
| SMC/ICT | smc_choch | -0.10 / -0.10 | -0.06 / -0.05 | +0.02 / +0.02 · | +0.25 / +0.09 · |
| SMC/ICT | smc_fvg_retest | -0.09 / -0.08 | -0.05 / -0.05 | +0.03 / -0.01 | +0.19 / +0.02 · |
| SMC/ICT | smc_ob_retest | -0.11 / -0.09 | -0.06 / -0.06 | -0.03 / -0.07 | +0.06 / +0.05 · |
| SMC/ICT | smc_sweep_swing | -0.10 / -0.09 | -0.06 / -0.05 | +0.00 / -0.02 | +0.15 / +0.12 · |
| SMC/ICT | sweep_pdh_pdl | -0.08 / -0.09 | -0.04 / -0.05 | +0.02 / -0.01 | +0.16 / +0.06 · |
| SMC/ICT | break_pdh_pdl | -0.09 / -0.08 | -0.06 / -0.04 | +0.02 / +0.04 · | +0.19 / +0.07 · |
| SMC/ICT | sweep_pwh_pwl | -0.09 / -0.08 | -0.06 / -0.01 | +0.04 / +0.03 · | +0.18 / +0.10 · |
| SMC/ICT | break_pwh_pwl | -0.05 / -0.07 | -0.02 / -0.04 | +0.01 / -0.04 | +0.24 / +0.13 · |
| SMC/ICT | asia_range_break | -0.10 / -0.09 | -0.06 / -0.06 | – | – |
| SMC/ICT | asia_range_sweep | -0.11 / -0.10 | -0.07 / -0.06 | – | – |

</details>

<details><summary>Matriks lengkap SHORT</summary>

| Grup | Indikator | 15m | 1h | 4h | 1d |
|---|---|---|---|---|---|
| MA | ema_x_9_21 | -0.07 / -0.07 | -0.01 / -0.01 | +0.08 / +0.01 · | +0.10 / +0.03 · |
| MA | ema_x_20_50 | -0.07 / -0.06 | +0.02 / -0.02 | +0.10 / +0.02 · | +0.16 / +0.06 · |
| MA | ema_x_50_200 | -0.06 / -0.06 | +0.01 / -0.06 | +0.06 / -0.08 | +0.05 / +0.18 · |
| MA | sma_x_50_200 | -0.06 / -0.06 | +0.05 / -0.08 | +0.01 / -0.10 | +0.12 / +0.20 · |
| MA | price_x_ema50 | -0.07 / -0.07 | -0.02 / +0.00 | +0.04 / +0.04 ✅ | +0.12 / +0.02 · |
| MA | price_x_ema200 | -0.08 / -0.06 | -0.02 / -0.01 | +0.04 / -0.01 | -0.03 / +0.11 |
| MA | ma_ribbon_align | -0.06 / -0.06 | +0.04 / -0.02 | +0.07 / +0.02 · | +0.12 / +0.10 ✅ |
| MA | ema20_pullback | -0.05 / -0.09 | +0.03 / -0.04 | +0.04 / +0.05 ✅ | +0.09 / +0.06 ✅ |
| Trend/momentum | supertrend_flip | -0.07 / -0.07 | -0.03 / -0.03 | +0.09 / +0.04 · | +0.07 / -0.05 |
| Trend/momentum | psar_flip | -0.06 / -0.06 | -0.02 / -0.02 | +0.01 / +0.06 · | +0.08 / -0.03 |
| Trend/momentum | ha_flip | -0.07 / -0.07 | -0.03 / -0.03 | -0.02 / +0.02 | +0.02 / +0.03 · |
| Trend/momentum | donchian_20 | -0.07 / -0.07 | -0.02 / -0.03 | +0.10 / +0.02 · | +0.10 / -0.12 |
| Trend/momentum | donchian_55 | -0.07 / -0.06 | +0.00 / -0.02 | +0.10 / +0.07 ✅ | +0.08 / -0.05 |
| Trend/momentum | macd_x | -0.06 / -0.06 | -0.02 / -0.02 | +0.04 / +0.04 ✅ | +0.06 / -0.03 |
| Trend/momentum | macd_zero_x | -0.07 / -0.07 | -0.01 / -0.04 | +0.10 / +0.01 · | +0.11 / +0.04 · |
| Trend/momentum | adx_di_x | -0.07 / -0.07 | -0.03 / -0.01 | -0.01 / +0.00 | +0.02 / +0.10 · |
| Trend/momentum | ichi_tk_x | -0.04 / -0.06 | +0.10 / -0.01 | +0.14 / +0.07 ✅ | +0.14 / +0.04 · |
| Trend/momentum | ichi_kumo_break | -0.07 / -0.06 | +0.00 / +0.00 · | +0.03 / +0.01 · | +0.06 / +0.07 · |
| Oscillator | rsi_30_70_rev | -0.07 / -0.07 | -0.04 / -0.06 | -0.07 / -0.04 | -0.09 / -0.02 |
| Oscillator | rsi_50_x | -0.07 / -0.07 | -0.03 / -0.01 | +0.03 / +0.02 ✅ | +0.10 / +0.05 · |
| Oscillator | rsi2_extreme | -0.06 / -0.06 | -0.03 / -0.06 | -0.01 / -0.01 | -0.04 / -0.01 |
| Oscillator | rsi_divergence | -0.05 / -0.06 | +0.01 / -0.07 | -0.02 / -0.01 | -0.05 / -0.04 |
| Oscillator | stoch_rev | -0.07 / -0.07 | -0.04 / -0.04 | -0.04 / -0.01 | -0.03 / +0.02 |
| Oscillator | willr_rev | -0.07 / -0.07 | -0.04 / -0.04 | -0.04 / -0.00 | -0.04 / +0.04 |
| Oscillator | cci_rev | -0.07 / -0.07 | -0.03 / -0.03 | -0.03 / +0.02 | +0.06 / -0.02 |
| Oscillator | mfi_rev | -0.07 / -0.07 | -0.05 / -0.04 | -0.05 / -0.02 | -0.04 / -0.02 |
| Oscillator | zscore_revert | -0.06 / -0.07 | -0.04 / -0.05 | -0.06 / -0.02 | -0.06 / -0.04 |
| Volatilitas | bb_revert | -0.06 / -0.07 | -0.03 / -0.04 | -0.03 / -0.02 | -0.02 / +0.00 |
| Volatilitas | bb_breakout | -0.07 / -0.07 | +0.00 / -0.06 | +0.09 / +0.06 ✅ | +0.15 / -0.12 |
| Volatilitas | keltner_breakout | -0.07 / -0.06 | -0.00 / -0.06 | +0.08 / +0.03 ✅ | +0.08 / -0.09 |
| Volatilitas | squeeze_fire | -0.07 / -0.07 | +0.02 / +0.01 · | +0.12 / +0.04 · | +0.09 / -0.15 |
| Volatilitas | nr7_breakout | -0.06 / -0.06 | -0.03 / -0.01 | +0.03 / +0.01 · | +0.00 / -0.09 |
| Volatilitas | inside_bar_break | -0.06 / -0.06 | -0.03 / -0.02 | +0.03 / +0.00 · | +0.00 / -0.04 |
| Candle | engulfing | -0.07 / -0.07 | -0.02 / -0.02 | +0.00 / +0.04 · | +0.06 / -0.24 |
| Candle | pinbar | -0.06 / -0.07 | -0.04 / -0.05 | -0.04 / -0.00 | +0.02 / -0.05 |
| VWAP | vwap_x | -0.07 / -0.07 | -0.02 / -0.03 | -0.01 / -0.01 | -0.04 / +0.02 |
| VWAP | vwap_1sd_break | -0.06 / -0.06 | -0.02 / -0.02 | +0.00 / -0.01 | -0.04 / +0.02 |
| VWAP | vwap_2sd_revert | -0.06 / -0.07 | -0.03 / -0.02 | -0.01 / -0.01 | -0.04 / +0.02 |
| VWAP | vwap_week_x | -0.07 / -0.07 | -0.02 / -0.03 | +0.01 / +0.05 · | +0.00 / +0.03 · |
| VWAP | vwap_month_x | -0.07 / -0.06 | -0.04 / -0.04 | +0.02 / +0.02 · | +0.05 / +0.03 · |
| VWAP | vwap_reclaim | -0.07 / -0.07 | -0.02 / -0.03 | -0.01 / -0.01 | -0.05 / +0.01 |
| Volume | vol_spike_candle | -0.07 / -0.05 | +0.05 / -0.02 | +0.11 / +0.02 · | -0.09 / -0.02 |
| Volume | vol_spike_reversal | -0.06 / -0.09 | -0.05 / -0.06 | +0.00 / -0.03 | +0.04 / -0.03 |
| Volume | vol_climax | -0.06 / -0.07 | -0.02 / -0.06 | +0.01 / -0.03 | +0.02 / -0.13 |
| Volume | vol_dryup_break | -0.10 / -0.08 | +0.04 / -0.09 | +0.10 / -0.01 | +0.16 / +0.09 · |
| Volume | obv_break_20 | -0.07 / -0.06 | -0.01 / -0.03 | +0.06 / +0.02 · | +0.01 / +0.01 · |
| Taker flow (delta/CVD) | delta_surge ⚠️taker | -0.06 / -0.06 | -0.02 / -0.04 | +0.01 / +0.00 · | -0.04 / +0.08 |
| Taker flow (delta/CVD) | delta_absorption ⚠️taker | -0.06 / -0.06 | -0.04 / -0.05 | -0.01 / -0.04 | -0.07 / -0.04 |
| Taker flow (delta/CVD) | cvd_divergence ⚠️taker | -0.06 / -0.07 | -0.03 / -0.05 | -0.03 / -0.03 | -0.07 / -0.01 |
| Taker flow (delta/CVD) | delta_flip ⚠️taker | -0.07 / -0.07 | -0.02 / -0.03 | +0.02 / +0.04 ✅ | -0.07 / +0.03 |
| SMC/ICT | smc_bos | -0.07 / -0.07 | -0.02 / -0.04 | +0.09 / +0.01 · | +0.12 / -0.07 |
| SMC/ICT | smc_choch | -0.07 / -0.07 | -0.02 / -0.02 | +0.05 / +0.05 ✅ | +0.09 / -0.08 |
| SMC/ICT | smc_fvg_retest | -0.06 / -0.06 | -0.01 / -0.01 | +0.06 / -0.03 | +0.03 / +0.04 · |
| SMC/ICT | smc_ob_retest | -0.07 / -0.07 | -0.02 / -0.05 | +0.04 / +0.01 · | +0.02 / +0.07 · |
| SMC/ICT | smc_sweep_swing | -0.06 / -0.07 | -0.01 / -0.03 | +0.00 / +0.04 · | +0.01 / +0.03 · |
| SMC/ICT | sweep_pdh_pdl | -0.06 / -0.06 | -0.02 / -0.03 | -0.02 / +0.01 | -0.05 / +0.03 |
| SMC/ICT | break_pdh_pdl | -0.07 / -0.05 | -0.02 / -0.02 | +0.03 / +0.04 ✅ | -0.02 / -0.01 |
| SMC/ICT | sweep_pwh_pwl | -0.09 / -0.05 | -0.05 / -0.03 | -0.04 / -0.00 | -0.01 / +0.06 |
| SMC/ICT | break_pwh_pwl | -0.06 / -0.05 | +0.03 / -0.04 | +0.06 / +0.01 · | +0.05 / -0.06 |
| SMC/ICT | asia_range_break | -0.05 / -0.05 | -0.02 / -0.05 | – | – |
| SMC/ICT | asia_range_sweep | -0.06 / -0.06 | -0.02 / -0.03 | – | – |

</details>

## 5. Kombinasi terbaik (finalis) dan uji anti-double-count

Ada 21 finalis (lolos IS & OOS: avgR ≥ 0,08, PF ≥ 1,2, t per trade ≥ 3). Syarat lolos akhir: **t harian ≥ 2 di IS dan OOS**, dengan minimal 20 hari OOS. **Yang lolos: 3.**

| # | Strategi | Data | n IS / OOS | avgR IS / OOS | Baseline acak OOS | **t harian IS / OOS** | Hari OOS | HYPE n / avgR / t harian | Portofolio penuh CAGR / DD | Lolos? |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1d long rsi2_extreme — fg_extreme + stable_growth [sl2_trail3] | macro | 215 / 455 | +0.54 / +0.33 | +0.10 | 2.2 / 2.7 | 54 | 444 / +0.32 / 2.4 | 11% / -14% | ✅ |
| 2 | 1d long macd_x — breadth_extreme + fg_trend [sl1.5_tp3] | cross+macro | 200 / 362 | +0.63 / +0.46 | +0.02 | 3.0 / 2.1 | 72 | 389 / +0.52 / 3.1 | 18% / -21% | ✅ |
| 3 | 1d long cci_rev — vol_contracting + stable_growth [sl1_tp2] | macro | 347 / 747 | +0.67 / +0.24 | -0.04 | 2.6 / 2.0 | 143 | 763 / +0.42 / 3.3 | 23% / -33% | ✅ |
| 4 | 1d short rsi2_extreme — rsi_side + vol_expanding [sl1_tp2] | ohlcv | 140 / 222 | +0.45 / +0.67 | +0.00 | 1.6 / 2.1 | 78 | 250 / +0.67 / 2.4 | 9% / -21% | ❌ |
| 5 | 4h short ichi_kumo_break — ribbon_aligned + fg_extreme [sl1.5_tp3] | macro | 328 / 102 | +0.49 / +0.51 | -0.02 | 2.2 / 2.1 | 10 | 184 / +0.34 / 1.4 | 18% / -30% | ❌ |
| 6 | 1d long cvd_divergence — fg_extreme + stable_growth [sl1.5_tp4_trail2.5] | macro+taker | 335 / 616 | +0.51 / +0.39 | +0.02 | 1.5 / 1.9 | 48 | – (tak ada taker di HYPE) | 7% / -25% | ❌ |
| 7 | 4h short vwap_1sd_break — vol_contracting + fg_extreme [sl1_tp2] | macro | 1990 / 177 | +0.18 / +1.43 | -0.03 | 1.4 / 1.9 | 10 | 450 / +0.74 / 2.1 | 28% / -71% | ❌ |
| 8 | 4h short rsi_50_x — vol_contracting + stable_growth [sl1.5_tp3] | macro | 1776 / 1605 | +0.21 / +0.17 | -0.02 | 2.6 / 1.8 | 133 | 1106 / +0.27 / 2.5 | 18% / -42% | ❌ |
| 9 | 1d short rsi_50_x — volume_high + stable_growth [sl1_tp2] | macro | 194 / 109 | +0.32 / +0.43 | +0.00 | 1.1 / 1.8 | 62 | 122 / +0.51 / 2.5 | 9% / -24% | ❌ |
| 10 | 4h short ichi_tk_x [sl1.5_tp4_trail2.5] | ohlcv | 4657 / 5749 | +0.13 / +0.12 | -0.02 | 2.7 / 1.8 | 557 | 4213 / +0.19 / 2.5 | 53% / -60% | ❌ |
| 11 | 1d short ha_flip — weekend + fg_trend [sl1.5_tp4_trail2.5] | macro | 473 / 375 | +0.30 / +0.31 | +0.02 | 1.9 / 1.7 | 67 | 595 / +0.37 / 3.0 | 15% / -18% | ❌ |
| 12 | 1d long rsi_30_70_rev — taker_flow_side + stable_growth [sl2_tp2] | macro+taker | 141 / 253 | +0.37 / +0.34 | +0.00 | 2.8 / 1.7 | 70 | – (tak ada taker di HYPE) | 7% / -12% | ❌ |
| 13 | 4h short smc_choch — rsi_side + vol_contracting [sl1.5_tp4_trail2.5] | ohlcv | 3166 / 3012 | +0.24 / +0.14 | -0.02 | 3.6 / 1.7 | 433 | 2473 / +0.18 / 2.0 | 94% / -71% | ❌ |
| 14 | 1d long stoch_rev — fg_extreme + stable_growth [sl1.5_tp4_trail2.5] | macro | 392 / 688 | +0.56 / +0.34 | +0.02 | 1.7 / 1.7 | 62 | 732 / +0.36 / 1.9 | 11% / -22% | ❌ |
| 15 | 1h long zscore_revert — above_vwap_w + stable_growth [sl1.5_tp4_trail2.5] | macro | 2462 / 1903 | +0.17 / +0.18 | -0.08 | 1.8 / 1.7 | 215 | 232 / +0.35 / 1.4 | 25% / -52% | ❌ |
| 16 | 4h short bb_breakout — vol_contracting + fg_trend [sl1_tp2] | macro | 1844 / 1278 | +0.28 / +0.26 | -0.03 | 2.6 / 1.6 | 181 | 1031 / +0.17 / 1.0 | 71% / -55% | ❌ |
| 17 | 4h long bb_revert — adx_trending + volume_high [sl1.5_tp3] | ohlcv | 1913 / 1430 | +0.16 / +0.22 | -0.04 | 1.6 / 1.6 | 302 | 1422 / +0.14 / 1.1 | 3% / -64% | ❌ |
| 18 | 1d short vwap_month_x — smc_structure + stable_growth [sl1_tp2] | macro | 612 / 598 | +0.31 / +0.35 | +0.00 | 2.0 / 1.5 | 112 | 521 / +0.37 / 1.7 | 15% / -38% | ❌ |
| 19 | 4h long vol_spike_reversal — breadth_extreme + stable_growth [sl2_tp2] | cross+macro | 515 / 353 | +0.21 / +0.21 | -0.04 | 1.1 / 1.4 | 80 | 765 / +0.03 / 0.3 | 5% / -26% | ❌ |
| 20 | 4h short donchian_55 — sess_europe + weekend [sl1.5_tp3] | ohlcv | 358 / 732 | +0.71 / +0.42 | -0.02 | 1.8 / 1.3 | 104 | 615 / +0.48 / 1.6 | 24% / -46% | ❌ |
| 21 | 4h short keltner_breakout — ema50_gt_200 + fg_extreme [sl2_trail3] | macro | 268 / 204 | +0.59 / +0.59 | +0.00 | 2.2 / 0.9 | 9 | 209 / +0.67 / 1.2 | 17% / -12% | ❌ |

**Cara membaca:** t per trade (kolom tahap 2) selalu tinggi (3–17), tetapi setelah trade di hari yang sama digabung, sebagian besar turun ke 1–2. Edge banyak kombinasi ternyata cuma beberapa puluh hari crash/pump yang terhitung ratusan kali. Contohnya *4h short VWAP 1σ break + vol contracting + F&G > 75*: OOS +1,43R per trade, tetapi hanya **10 hari** berbeda.

**Arti kombinasi yang lolos (semua harian, long, data gratis):**

| Kombinasi | Aturan dalam bahasa biasa | Data | Catatan |
|---|---|---|---|
| RSI(2) oversold + F&G < 25 + stablecoin naik | RSI(2) turun di bawah 10, Fear & Greed < 25 (extreme fear), market cap stablecoin naik > 1% dalam 30 hari. Exit SL 2 ATR, trailing 3 ATR | macro (gratis) | Beli kepanikan saat likuiditas (stablecoin) masih masuk. Positif di setiap tahun yang ada sinyalnya (2023 tidak ada sinyal) |
| MACD cross up + breadth < 20% + F&G naik | MACD cross ke atas saat < 20% koin di atas EMA50 masing-masing (pasar sangat lemah), dan F&G di atas rata-rata 30 harinya (sentimen mulai pulih). SL 1,5 / TP 3 ATR | cross + macro (gratis) | Mirip "capitulation recovery". Positif tiap tahun 2021–2026 |
| CCI revert + volatilitas sempit + stablecoin naik | CCI naik kembali di atas −100 saat ATR% ada di 30% terbawah, dan stablecoin naik > 1% dalam 30 hari. SL 1 / TP 2 ATR | macro (gratis) | 2023 hanya 3 trade (negatif) |

## 6. Strategi tingkat portofolio (data candle gratis)

| Strategi | Konfigurasi | IS t > 2 | IS t > 2 & OOS > 0 | Median t IS | Median t OOS |
|---|---|---|---|---|---|
| Momentum long (beli koin terkuat) | 192 | 149 | 128 | 2.36 | 0.95 |
| Momentum short (short koin terlemah) | 192 | 0 | 0 | -1.51 | -0.15 |
| Momentum long-short | 192 | 7 | 7 | 1.05 | 0.56 |
| Reversal long (beli koin terlemah) | 192 | 2 | 1 | 0.97 | -0.36 |
| Reversal short | 192 | 0 | 0 | -1.51 | -1.39 |
| Reversal long-short | 192 | 0 | 0 | -0.62 | -1.60 |
| Trend MA long (close > EMA-N) | 60 | 30 | 23 | 1.99 | 0.33 |
| Trend MA short | 60 | 0 | 0 | -1.07 | 0.04 |
| Trend MA long-short | 60 | 8 | 8 | 1.01 | 0.36 |

**Temuan terkuat dari data gratis: momentum lintas koin (long saja).** Setiap hari, koin diurutkan berdasarkan return 14 hari. Long 20% teratas (rata-rata ±13 koin, bobot sama) hanya saat **BTC > EMA50 harian**, rebalance tiap hari, dengan biaya dihitung dari turnover nyata (±45% per hari) ditambah funding.

| Versi (L14, top 20%, filter BTC) | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 (YTD) | Max DD | CAGR OOS |
|---|---|---|---|---|---|---|---|---|---|
| Semua koin | +232% | +1950% | −52% | +110% | +92% | −21% | +216% | −64% | +70% |
| Hanya koin listing < 2023 (mengurangi bias "dipilih karena baru pump") | +232% | +1950% | −52% | +113% | +109% | −10% | +126% | −61% | +51% |
| Pembanding: semua koin bobot sama + filter BTC yang sama (tanpa momentum) | +54% | +678% | −42% | +134% | −3% | −52% | +88% | −76% | – |
| Pembanding: beli & tahan semua koin bobot sama | +110% | +612% | −78% | +120% | +28% | −57% | +111% | – | – |

- Excess vs basket bobot sama, per hari: IS +0,28% (t 3,7), OOS +0,39% (t 3,7). **Di candle HYPE:** excess +0,30%/hari (t 4,0), sejak 2025 +0,28% (t 3,1).
- Momentum mengalahkan "filter BTC saja" di 2024, 2025, dan 2026. Jadi edge-nya bukan cuma dari filter rezim.
- ⚠️ **Bias terbesar ada di sini.** Universe dipilih dari volume Sep 2026, sehingga koin yang naik kencang di 2025–2026 otomatis masuk. Versi top-50 likuiditas melemah di OOS (+18%/tahun, t ≈ 1), dan versi tanpa filter BTC untuk koin lama negatif di OOS. **Drawdown −60% sampai −64%**, jadi wajib dikecilkan (misalnya 25–30% modal, atau digabung dengan stop portofolio).
- Momentum **short** (short koin terlemah), reversal, dan trend MA short **tidak bekerja**: 0 dari 192 konfigurasi short dengan IS t > 2. Sebagian ini efek survivorship, karena koin lemah yang mati tidak ada di data.
- **Trend MA per koin (close > EMA-N, long saja):** IS bagus (t ≈ 3), tetapi OOS lemah (median t 0,3).

## 7. Breadth (≥N koin serentak) dan breadth thrust

**Versi harga-saja dari CLR-1 (tanpa OI):** di close 4h, ≥ N koin serentak *close kembali di atas Bollinger bawah* dengan *volume > 1,5× rata-rata* → long semua koin itu, SL 2 ATR / TP 2 ATR.

| Min koin serentak | Event | Basket avgR | Event untung | t event | IS (n / avgR) | OOS (n / avgR) |
|---|---|---|---|---|---|---|
| 1 (sinyal biasa) | 1.507 | −0,04 | 47% | −1,6 | 755 / −0,03 | 752 / −0,04 |
| 5 | 235 | +0,07 | 54% | 1,4 | 142 / +0,10 | 93 / +0,02 |
| **10** | **107** | **+0,16** | 60% | **2,3** | 67 / +0,13 | 40 / **+0,21** |
| 15 | 62 | +0,20 | 66% | 2,2 | 37 / +0,25 | 25 / +0,13 |
| **20** | **39** | **+0,28** | 72% | **2,5** | 20 / +0,36 | 19 / +0,19 |
| 30 | 23 | +0,38 | 78% | 2,6 | 12 / +0,45 | 11 / +0,30 |

- Edge naik terus seiring jumlah koin (monoton). Ini pola yang sehat, bukan kebetulan satu parameter.
- Dari 672 konfigurasi basket (26 sinyal × 7 ambang × 3 exit), **hanya kombinasi ini** yang positif di IS & OOS dengan t > 2.
- Dibanding versi OI (CLR-1: ≥10 koin + OI −5% → 37 event, +0,37R, OOS +0,48R), **OI tetap menambah kualitas**. Versi harga-saja memberi lebih banyak event tetapi edge per event kira-kira setengahnya.
- **Breadth thrust** (breadth naik dari < 10–30% ke > 50–70% dalam 3–10 hari): tidak ada edge. OOS ≈ 0 setelah dibandingkan baseline.

## 8. Kesimpulan & rekomendasi

1. **Indikator favorit yang dipakai sendirian tidak punya edge di 15m dan 1h setelah biaya.** VWAP, SMC (BOS/CHoCH/FVG/OB/sweep), RSI, BB, EMA cross, volume spike semuanya kalah atau setara dengan entry acak. Ini konsisten dengan riset sebelumnya.
2. Di **4h dan 1d**, indikator trend dengan **trailing stop** (Ichimoku TK, Keltner/BB breakout, VWAP bulanan/mingguan, harga×EMA50, PSAR) sedikit mengalahkan baseline (+0,05 s/d +0,12R per trade). Edge-nya kecil dan drawdown portofolionya besar.
3. **Edge data gratis yang paling layak diteruskan (urut keyakinan):**
   - **A. Momentum lintas koin + filter BTC (1d, long)** — `ohlcv` + `cross`. Konsisten IS, OOS, dan di HYPE, tapi bias universe besar dan DD −60%. Keyakinan **5/10**.
   - **B. Flush basket harga-saja (4h, ≥10–20 koin BB revert + volume tinggi)** — `ohlcv` + `cross`. +0,16 s/d +0,28R per event, OOS positif. Keyakinan **4/10** (event sedikit).
   - **C. Tiga kombinasi harian yang lolos t harian** (lihat tabel §5: MACD cross saat breadth < 20% + F&G naik; RSI(2) oversold saat F&G < 25 + stablecoin naik; CCI revert saat volatilitas sempit + stablecoin naik). Semuanya `macro`/`cross`, gratis, dan lolos di HYPE. Tetapi hari independennya hanya 50–140, jadi keyakinan **3–4/10**.
4. **Tanpa OI, edge yang tersisa lebih kecil.** CLR-1 (dengan OI) tetap lebih baik dari versi B. Catatan: arsip OI di `data.binance.vision` baru terbit H+1, jadi tidak bisa dipakai untuk live. Versi real-time-nya (API publik Binance) diblokir dari jaringanmu.
5. **Langkah berikut yang disarankan:** forward test paper untuk A dan B di HYPE (data candle HYPE gratis), dengan ukuran kecil, sebelum uang riil. Belum ada holdout baru yang dipakai. Kalau mau validasi tambahan, beri tahu dulu.

## Batasan

- Sekitar 1,2 juta uji berarti banyak hasil bagus muncul karena kebetulan. Penyaring utamanya adalah OOS, t harian, baseline acak, breadth koin, dan konsistensi per tahun.
- Survivorship dan selection bias: universe dipilih dari koin hidup dengan volume tinggi per Sep 2026. Ini menguntungkan semua strategi **long**, terutama momentum di 2025–2026.
- Cek di HYPE **bukan data independen**, karena harga Binance dan HYPE berkorelasi 0,999. Cek ini hanya membuktikan bahwa strategi tetap jalan di venue dan biaya funding HYPE.
- Filter `macro` (Fear & Greed, stablecoin) adalah rezim lambat. Trade-nya bergerombol, jadi jumlah hari independennya kecil (lihat kolom Hari OOS).
