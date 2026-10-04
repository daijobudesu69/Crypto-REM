"""Narrative blocks for the report (numbers taken from the result files printed during the session)."""

XSEC_NOTES = """**Temuan terkuat dari data gratis: momentum lintas koin (long saja).** Setiap hari, koin diurutkan berdasarkan return 14 hari. Long 20% teratas (rata-rata ±13 koin, bobot sama) hanya saat **BTC > EMA50 harian**, rebalance tiap hari, dengan biaya dihitung dari turnover nyata (±45% per hari) ditambah funding.

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
- **Trend MA per koin (close > EMA-N, long saja):** IS bagus (t ≈ 3), tetapi OOS lemah (median t 0,3)."""

BREADTH_NOTES = """**Versi harga-saja dari CLR-1 (tanpa OI):** di close 4h, ≥ N koin serentak *close kembali di atas Bollinger bawah* dengan *volume > 1,5× rata-rata* → long semua koin itu, SL 2 ATR / TP 2 ATR.

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
- **Breadth thrust** (breadth naik dari < 10–30% ke > 50–70% dalam 3–10 hari): tidak ada edge. OOS ≈ 0 setelah dibandingkan baseline."""

FIN_NOTES = """**Cara membaca:** t per trade (kolom tahap 2) selalu tinggi (3–17), tetapi setelah trade di hari yang sama digabung, sebagian besar turun ke 1–2. Edge banyak kombinasi ternyata cuma beberapa puluh hari crash/pump yang terhitung ratusan kali. Contohnya *4h short VWAP 1σ break + vol contracting + F&G > 75*: OOS +1,43R per trade, tetapi hanya **10 hari** berbeda.

**Arti kombinasi yang lolos (semua harian, long, data gratis):**

| Kombinasi | Aturan dalam bahasa biasa | Data | Catatan |
|---|---|---|---|
| RSI(2) oversold + F&G < 25 + stablecoin naik | RSI(2) turun di bawah 10, Fear & Greed < 25 (extreme fear), market cap stablecoin naik > 1% dalam 30 hari. Exit SL 2 ATR, trailing 3 ATR | macro (gratis) | Beli kepanikan saat likuiditas (stablecoin) masih masuk. Positif di setiap tahun yang ada sinyalnya (2023 tidak ada sinyal) |
| MACD cross up + breadth < 20% + F&G naik | MACD cross ke atas saat < 20% koin di atas EMA50 masing-masing (pasar sangat lemah), dan F&G di atas rata-rata 30 harinya (sentimen mulai pulih). SL 1,5 / TP 3 ATR | cross + macro (gratis) | Mirip "capitulation recovery". Positif tiap tahun 2021–2026 |
| CCI revert + volatilitas sempit + stablecoin naik | CCI naik kembali di atas −100 saat ATR% ada di 30% terbawah, dan stablecoin naik > 1% dalam 30 hari. SL 1 / TP 2 ATR | macro (gratis) | 2023 hanya 3 trade (negatif) |"""

CONCLUSION = """1. **Indikator favorit yang dipakai sendirian tidak punya edge di 15m dan 1h setelah biaya.** VWAP, SMC (BOS/CHoCH/FVG/OB/sweep), RSI, BB, EMA cross, volume spike semuanya kalah atau setara dengan entry acak. Ini konsisten dengan riset sebelumnya.
2. Di **4h dan 1d**, indikator trend dengan **trailing stop** (Ichimoku TK, Keltner/BB breakout, VWAP bulanan/mingguan, harga×EMA50, PSAR) sedikit mengalahkan baseline (+0,05 s/d +0,12R per trade). Edge-nya kecil dan drawdown portofolionya besar.
3. **Edge data gratis yang paling layak diteruskan (urut keyakinan):**
   - **A. Momentum lintas koin + filter BTC (1d, long)** — `ohlcv` + `cross`. Konsisten IS, OOS, dan di HYPE, tapi bias universe besar dan DD −60%. Keyakinan **5/10**.
   - **B. Flush basket harga-saja (4h, ≥10–20 koin BB revert + volume tinggi)** — `ohlcv` + `cross`. +0,16 s/d +0,28R per event, OOS positif. Keyakinan **4/10** (event sedikit).
   - **C. Tiga kombinasi harian yang lolos t harian** (lihat tabel §5: MACD cross saat breadth < 20% + F&G naik; RSI(2) oversold saat F&G < 25 + stablecoin naik; CCI revert saat volatilitas sempit + stablecoin naik). Semuanya `macro`/`cross`, gratis, dan lolos di HYPE. Tetapi hari independennya hanya 50–140, jadi keyakinan **3–4/10**.
4. **Tanpa OI, edge yang tersisa lebih kecil.** CLR-1 (dengan OI) tetap lebih baik dari versi B. Catatan: arsip OI di `data.binance.vision` baru terbit H+1, jadi tidak bisa dipakai untuk live. Versi real-time-nya (API publik Binance) diblokir dari jaringanmu.
5. **Langkah berikut yang disarankan:** forward test paper untuk A dan B di HYPE (data candle HYPE gratis), dengan ukuran kecil, sebelum uang riil. Belum ada holdout baru yang dipakai. Kalau mau validasi tambahan, beri tahu dulu."""

TLDR = """1. **1,29 juta uji kombinasi dan 424 juta trade tersimulasi.** Isinya 61 indikator (MA, VWAP, SMC/ICT, volume, oscillator, Ichimoku, candle, taker flow) × 0/1/2 filter × 4 TF. Semua memakai **data gratis saja**: tanpa OI, tanpa funding sebagai sinyal, tanpa LS ratio.
2. **15m dan 1h: tidak ada edge.** Tidak ada indikator yang positif sendirian di IS & OOS (long 0/61 di 15m dan 1h; short 0/61 di 15m dan 2/61 di 1h). Dari ratusan kombinasi terbaik, **0 lolos** syarat finalis di 15m. VWAP, SMC, RSI, BB, dan EMA cross di TF kecil semuanya kalah setelah biaya.
3. **4h/1d: indikator trend + trailing stop sedikit mengalahkan entry acak** (+0,05 s/d +0,13R per trade). Contohnya Keltner/BB breakout 1d, VWAP bulanan 4h, Ichimoku TK 4h, dan Donchian-55 short 4h. Edge-nya kecil dan DD portofolionya besar.
4. **Kombinasi:** 21 finalis lolos IS & OOS per trade, tapi setelah trade **di hari yang sama digabung, hanya 3 yang lolos** (semuanya harian long, pakai data gratis F&G / stablecoin / breadth). Hari independennya sedikit (54–143 hari OOS).
5. **Edge paling meyakinkan dari data gratis:** **momentum lintas koin** (long 20% koin dengan return 14 hari terkuat, hanya saat BTC > EMA50, rebalance harian). Excess vs basket bobot sama: +0,28%/hari IS (t 3,7), +0,39%/hari OOS (t 3,7), +0,30%/hari di HYPE (t 4,0). ⚠️ DD −60% dan bias universe besar.
6. **Flush basket harga-saja** (≥10–20 koin serentak BB revert + volume tinggi, 4h): +0,16 s/d +0,28R per event, OOS positif. Ini sekitar setengah kualitas versi OI (CLR-1). **OI memang menambah edge**, tapi tanpa OI masih ada sisa.
7. **Tidak ada edge:** momentum short, reversal, trend MA short, dan breadth thrust."""
