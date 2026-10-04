"""v2 section of the RMF report: critique check, HYPE reality, 100 USD plan (numbers from result JSON files)."""
import os, json
import ta


def _j(name):
    return json.load(open(os.path.join(ta.OUT, f"{name}.json"), encoding="utf-8"))


def build(D, table):
    SC, HF, BO, FX, HS = _j("small_capital"), _j("hl_full"), _j("bn_overlap"), _j("flush_cross"), _j("hl_small")
    sv = {(r["variant"], r["start"][:4]): r for r in SC["variants"]}
    hf = {(r["venue"], r["variant"]): r for r in HF["sims"]}
    hs = {r["variant"]: r for r in HS}
    seeds = SC["seeds"]; fund = {(r["case"], r["start"][:4]): r for r in SC["funding"]}
    ok = lambda v: {"B": '<span class="chip on">Benar</span>', "S": '<span class="chip">Sebagian</span>', "X": '<span class="chip">Salah</span>'}[v]
    f25 = sv[("100 desain dipaksa (10 koin -> 1,0x, flush floor 10$)", "2025")]
    f22 = sv[("100 desain dipaksa (10 koin -> 1,0x, flush floor 10$)", "2022")]
    nb = D["no_btc_filter"]
    fw, fo = fund[("tanpa pemasukan funding", "2020")], fund[("dengan funding riil", "2020")]
    fw26, fo26 = fund[("tanpa pemasukan funding", "2026")], fund[("dengan funding riil", "2026")]
    hr, hm = hf[("HYPE", "RMF (0,5x + flush)")], hf[("HYPE", "Momentum saja 0,5x")]
    br, bm = hf[("Binance", "RMF (0,5x + flush)")], hf[("Binance", "Momentum saja 0,5x")]
    verdict = [
        ["A1 Momentum dipaksa 1×", ok("B"), f"100$ × 0,5 ÷ 10 = 5$ &lt; 10$. Simulasi dengan floor 10$ (mulai 2025): DD {f25['maxdd']}%, bulan terburuk {f25['worst_month']}%."],
        ["A2 Leverage naik saat rugi", ok("B"), f"Terbukti di simulasi floor. Mulai 2022: ekuitas turun ke {f22['min_equity']}$, eksposur momentum naik sampai ±1,5×, dan risiko satu event flush sampai {float(f22['event_risk_max']) * 100:.0f}% ekuitas."],
        ["A3 Risiko flush membengkak", ok("B"), "Hitungannya benar. 19 Jan 2025 16:00 (15 koin, −1,02R) dan 20 Jan 2025 08:00 (15 koin, −1,02R) memang terjadi, dengan event +0,39R di antaranya. Di 100$, risiko per event rata-rata 7–10% ekuitas, maksimal 27–48%."],
        ["A4 Eksposur 2,5× + crash", ok("B"), "Gross notional sampai 6,6× di simulasi 100$. Crash 10 Okt 2025: median altcoin −65% intrabar, 99 dari 129 koin wick di bawah −50%. Saran v1 \"isolated 3–5×\" salah dan sudah diganti."],
        ["A5 Biaya ±12%/tahun", ok("S"), "Fee 0,07%/sisi + funding sudah dipotong di semua angka backtest, jadi bukan biaya tambahan. Tapi dengan eksposur dipaksa 1×, biayanya memang 2× lipat dari desain."],
        ["A6 Hasil kecil di 100$", ok("S"), "Hitungannya benar. Sepadan atau tidak dengan usahanya, itu keputusanmu."],
        ["B1 Look-ahead universe", ok("B"), f"Sudah disebut di v1, sekarang terukur. Jul 2024–Okt 2026, momentum 0,5×: 150 koin Binance 300→{bm['final']:.0f}$, hanya koin yang juga ada di HYPE 300→{BO['mom_only']['final']:.0f}$."],
        ["B2 Profit menumpuk di 2026", ok("B"), "2026 = 63% kenaikan dolar. Dalam persen, 2026 (+167%) tahun terbaik setelah 2021. OOS sebagian besar dari 2026; 2025 sendiri +37%."],
        ["B3 Funding windfall", ok("B"), f"Tanpa pemasukan funding: 2020–2026 300→{fw['final']:,.0f}$ (CAGR {fw['cagr']}%), dengan funding riil {fo['final']:,.0f}$ (CAGR {fo['cagr']}%). Mulai 2026: {fw26['final']:.0f}$ vs {fo26['final']:.0f}$."],
        ["B4 Belum diuji di HYPE", ok("B"), f"Ini temuan paling penting. Simulasi akun penuh di candle HYPE (Jul 2024–Okt 2026): 300→{hr['final']:.0f}$, DD {hr['maxdd']}%. Binance periode sama: 300→{br['final']:,.0f}$. Lihat tabel di bawah."],
        ["B5 Aturan ≥60 hari beda", ok("X"), "Backtest juga memakai syarat ≥60 hari data (dan ≥44 hari untuk ranking). Di v1 tidak ditulis jelas; sekarang sudah."],
        ["B6 Angka tanpa filter BTC salah", ok("B"), f"Bug tampilan di v1 (tertimpa angka buffer &gt;30). Angka benar: tanpa filter BTC 300→{nb['final']:,}$, CAGR {nb['cagr']}%, DD {nb['dd']}%; dengan filter 21.351$, CAGR 88%, DD −35%. Jadi filter memang memangkas DD ±17 poin."],
        ["B7 Sampel flush kecil, seed", ok("S"), f"20 seed pemilihan acak: akhir {min(s['final'] for s in seeds):,.0f}–{max(s['final'] for s in seeds):,.0f}$, DD {min(s['maxdd'] for s in seeds)} s/d {max(s['maxdd'] for s in seeds)}%, jadi seed tidak berpengaruh. Ambang ≥10 diwarisi dari riset CLR-1 (dipilih di data 2020–2024); ≥15 dan ≥20 tetap positif. 107 event memang sedikit."],
        ["B8 Belum diuji (telat, SL, delist)", ok("B"), "Masih belum diuji."],
        ["B9 Dua kaki long saat crash", ok("B"), "Korelasi 0,08 itu mingguan. 10 Okt 2025: momentum memegang 10 koin (−4,5% hari itu di backtest open-to-open); kebetulan tidak ada flush terbuka."],
    ]
    hyp = [
        ["Binance, 150 koin (angka v1)", f"{br['final']:,.0f} $", f"{br['maxdd']}%", f"{bm['final']:.0f} $", f"{HF['events']['bn_ev_avgR']:+.2f}R"],
        ["Binance, hanya koin yang ada di HYPE", f"{BO['rmf']['final']:.0f} $", f"{BO['rmf']['maxdd']}%", f"{BO['mom_only']['final']:.0f} $", f"{BO['ev_avgR']:+.2f}R"],
        ["Candle HYPE, semua sinyal dari data HYPE", f"{hr['final']:.0f} $", f"{hr['maxdd']}%", f"{hm['final']:.0f} $", f"{HF['events']['hl_ev_avgR']:+.2f}R"],
        ["<b>Candle HYPE + sinyal flush dari Binance</b>", f"<b>{hs['300: 10 koin 0,5x + flush']['final']:.0f} $</b>", f"{hs['300: 10 koin 0,5x + flush']['maxdd']}%",
         f"{hs['300: 10 koin 0,5x saja']['final']:.0f} $", f"{FX['ev_avgR_hl']:+.2f}R"],
    ]

    def r100(r, label):
        return [label, f"{r['final']:,.0f} $", f"{r['cagr']}%", f"{r['maxdd']}%", f"{r['worst_month']}%", f"{r['gross_max']}×", f"{float(r.get('event_risk_max', 0)) * 100:.0f}%"]

    c100 = [
        r100(sv[("100 desain dipaksa (10 koin -> 1,0x, flush floor 10$)", "2025")], "Desain dipaksa: 10 koin × 10$ (=1,0×) + flush floor 10$"),
        r100(sv[("100 desain dipaksa + tolak risiko >2x + gross <=2x", "2025")], "Sama + tolak risiko &gt;2× target + gross ≤2×"),
        r100(sv[("100: 5 koin 0,5x + flush (tolak >2x, gross <=2x)", "2025")], "5 koin × 10$ (0,5×) + flush (tolak &gt;2×, gross ≤2×)"),
        r100(sv[("100: 5 koin 0,5x, tanpa flush", "2025")], "5 koin × 10$ (0,5×), tanpa flush"),
        r100(sv[("100: 10 koin 1,0x, tanpa flush", "2025")], "10 koin × 10$ (1,0×), tanpa flush"),
        r100(sv[("100: flush saja (tolak >2x)", "2025")], "Flush saja (tolak &gt;2×)"),
    ]
    h100 = [r100(hs[k], lab) for k, lab in (
        ("100: 10 koin dipaksa 10$ + flush", "Desain dipaksa: 10 koin × 10$ + flush floor 10$"),
        ("100: 5 koin 0,5x + flush (tolak>2x, gross<=2x)", "5 koin × 10$ + flush (tolak &gt;2×, gross ≤2×)"),
        ("100: 5 koin 0,5x saja", "5 koin × 10$ (0,5×), tanpa flush"),
        ("100: flush saja (tolak>2x)", "Flush saja (tolak &gt;2×)"))]
    head = ["Versi", "Akhir", "CAGR", "Max DD", "Bulan terburuk", "Gross maks", "Risiko event maks"]
    m5 = hs["100: 5 koin 0,5x saja"]; r3 = hs["300: 10 koin 0,5x + flush"]; m3 = hs["300: 10 koin 0,5x saja"]
    return f"""
<h2 id="update">Update v2: cek kritik, realita di HYPE, dan rencana 100 USD</h2>
<p>Kritik yang masuk sebagian besar benar. Dari 15 poin, 11 terbukti oleh data, 3 benar sebagian, dan 1 salah. Temuan terpenting: <b>angka v1 (backtest Binance) jauh lebih bagus dari yang bisa didapat di HYPE.</b></p>
<h3>1. Verdict tiap poin</h3>
{table(["Poin kritik", "Status", "Bukti dari data"], verdict)}
<h3>2. Realita di HYPE (poin B4)</h3>
{table(["Versi (Jul 2024 → Okt 2026, mulai 300 $)", "RMF akhir", "Max DD", "Momentum saja 0,5×", "Flush per event"], hyp)}
<ul>
<li><b>Momentum:</b> sebagian besar selisih datang dari koin yang hanya ada di Binance, yang sering berupa koin baru yang pump (sumber bias universe). Di harga HYPE, momentum 0,5× hanya 300→{m3['final']:.0f} $ dalam 27 bulan (CAGR {m3['cagr']}%, DD {m3['maxdd']}%).</li>
<li><b>Flush:</b> kalau sinyal dihitung dari candle HYPE, edge-nya hilang (+0,02R per event), kemungkinan karena pola volume HYPE berbeda. Kalau sinyal diambil dari candle Binance lalu dieksekusi di harga HYPE, edge tetap ada: +{FX['ev_avgR_hl']:.2f}R per event, {FX['events']} event. Jadi <b>flush wajib memakai data Binance futures</b> untuk sinyal. API publik Binance futures gratis, tapi diblokir dari jaringanmu dan kemungkinan juga dari server AS (mis. GitHub Actions). Perlu VPS di region yang tidak diblokir; ini harus dicek dulu.</li>
<li><b>Ekspektasi realistis</b> (harga HYPE + sinyal flush dari Binance, 300 $): 300→{r3['final']:.0f} $ dalam 27 bulan, CAGR {r3['cagr']}%, DD {r3['maxdd']}%. Universe HYPE juga dipilih dari volume sekarang, jadi angka ini pun masih batas atas.</li>
</ul>
<h3>3. Modal 100 USD</h3>
<p>Minimum order 10 USDC membuat RMF di 100 $ menjadi strategi yang berbeda dari yang di-backtest. Simulasi di bawah memakai floor 10 $ yang tidak ikut turun saat ekuitas turun.</p>
{table(["Versi 100 $ — backtest Binance, mulai 2025-01"] + head[1:], c100)}
{table(["Versi 100 $ — harga HYPE, mulai 2024-07"] + head[1:], h100)}
<ul>
<li><b>Desain dipaksa (10 koin + flush floor):</b> hasilnya bisa tinggi, tapi DD −35% s/d −46%, bulan terburuk sampai −27%, dan satu event flush bisa mempertaruhkan 20–48% ekuitas. Itu melanggar aturan risiko strategi sendiri.</li>
<li><b>Flush di 100 $ tidak layak.</b> Kalau risiko yang dipaksa floor diikuti, risikonya membengkak. Kalau koin berisiko tinggi ditolak, edge-nya hampir hilang (100→{hs['100: flush saja (tolak>2x)']['final']:.0f} $ di harga HYPE dalam 27 bulan).</li>
<li><b>Tidak ada versi 100 $ yang bagus.</b> Semua versi punya DD −26% s/d −46% dan sampelnya pendek (21–27 bulan). Pilihannya tinggal trade-off:
<ul>
<li><b>Paling sederhana:</b> momentum saja, 5 koin × 10 USDC (0,5×), cross margin tanpa leverage. Cukup data HYPE dan eksekusi 1× sehari. Harga HYPE sejak Jul 2024: 100→{m5['final']:.0f} $, DD {m5['maxdd']}%, bulan terburuk {m5['worst_month']}%. Ini versi dengan DD terburuk di tabel HYPE.</li>
<li><b>Paling seimbang:</b> 5 koin + flush dengan aturan tolak &gt;2× dan gross ≤2×. DD −28% (Binance) / −38% (HYPE). Butuh sinyal flush dari Binance futures (VPS) dan bot 6× sehari.</li>
<li><b>Tidak disarankan:</b> desain 10 koin yang dipaksa 10 $ per koin. Risiko event sampai 20–48% ekuitas.</li>
</ul></li>
<li>5 koin lebih kasar dari 10 koin: di backtest 6,7 tahun bulan terburuknya −21% (10 koin: −13%). Saat ekuitas &lt; 100 $, ukuran 10 $ per koin berarti eksposur &gt; 0,5×.</li>
<li><b>Alternatif:</b> paper trading (0 $) 2–3 bulan untuk kedua kaki, atau tambah modal ke ≥ 300 $ supaya ukuran posisi sesuai desain. Dengan ekspektasi realistis di HYPE, 100 $ lebih cocok dianggap biaya validasi daripada sumber profit.</li>
</ul>
<h3>4. Yang diubah di report ini</h3>
<ul>
<li>Saran margin: <b>cross margin di subaccount khusus</b>, atau isolated maks 1–2×. Jangan 3–5× isolated (crash 10 Okt 2025: median altcoin −65% intrabar).</li>
<li>Aturan baru: total notional (momentum + flush) ≤ 2× ekuitas, dan tolak koin flush yang risikonya &gt; 2× target. Aturan ini belum ada di v1.</li>
<li>Angka "tanpa filter BTC" diperbaiki. Aturan ≥60 hari ditulis eksplisit.</li>
<li>KPI di bagian bawah tetap backtest Binance (v1) supaya bisa dibandingkan. Untuk ekspektasi live, pakai angka HYPE di atas.</li>
</ul>
"""
