"""Build the self-contained mobile report: reports/RMF_report.html  (python build_html.py)"""
import os, json, html
import ta

D = json.load(open(os.path.join(ta.OUT, "rmf_report.json"), encoding="utf-8"))
REP = os.path.join(os.path.dirname(ta.HERE), "reports")
S, O = D["stats"], D["oos"]
TA, TY = D["trades_avg"], D["trades_per_year"]
FS, MS, C = D["flush_stats"], D["mom_stints"], D["costs"]
HT, BL, BF = D["hype_today"], D["binance_last"], D["btc_filter"]


def pct(x, d=0, sign=False):
    s = f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%"
    return s.replace(".", ",")


def num(x, d=0):
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def esc(s):
    return html.escape(str(s))


def table(head, rows, cls=""):
    h = "".join(f"<th>{esc(x)}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for r in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def sgn(v, d=1, suffix="%"):
    cls = "pos" if v > 0 else ("neg" if v < 0 else "")
    s = (f"{v:+.{d}f}" if d else f"{v:+.0f}").replace(".", ",")
    return f'<span class="{cls}">{s}{suffix}</span>'


# ---------------- today
today_rows = []
for i, r in enumerate(HT["table"], 1):
    today_rows.append([str(i), f"<b>{esc(r['coin'])}</b>" if r["pick"] else esc(r["coin"]), sgn(r["ret14"]), num(r["vol30_musd"], 1),
                       '<span class="chip on">BELI</span>' if r["pick"] else ('<span class="chip">cadangan</span>' if i <= 15 else "")])
picks = [r["coin"] for r in HT["table"] if r["pick"]]
per_coin_300 = 300 * 0.5 / 10

# ---------------- trades per year
ty_rows = [[t["year"], num(t["mom_in"]), num(t["mom_orders"]), num(t["per_month_mom"], 1), num(t["fl_ev"]), num(t["fl_tr"]), num(t["per_month_fl"], 1),
            f"{t['active']}%"] for t in TY]
tpm_rows = [[t["m"], str(t["mom_in"]), str(t["mom_out"]), str(t["fl_ev"]), str(t["fl_tr"]), str(t["mom_in"] + t["mom_out"] + 2 * t["fl_tr"]), f"{t['active']}%"]
            for t in D["trades_per_month"][::-1]]

# ---------------- yearly
y_rows = [[str(y["year"]), sgn(y["ret"], 0), sgn(y["dd"], 0), num(y["end"]), sgn(y["mom_usd"], 0, " $"), sgn(y["flush_usd"], 0, " $"), f"{BF['on_by_year'].get(str(y['year']), '–')}%"]
          for y in D["yearly"]]

# ---------------- monthly heatmap
months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
hm = ['<div class="tw"><table class="heat"><thead><tr><th>Tahun</th>' + "".join(f"<th>{m}</th>" for m in months) + "<th>Tahun</th></tr></thead><tbody>"]
for y in range(2020, 2027):
    cells = []
    for m in range(1, 13):
        v = D["monthly"].get(f"{y}-{m:02d}")
        if v is None:
            cells.append("<td></td>")
        else:
            a = min(abs(v) / 30, 1) * 70 + 8
            var = "--pos" if v >= 0 else "--neg"
            usd = D["monthly_usd"].get(f"{y}-{m:02d}", [0, 0, 0])
            cells.append(f'<td style="background:color-mix(in srgb,var({var}) {a:.0f}%,transparent)" title="Momentum {usd[0]:+.0f}$ · Flush {usd[1]:+.0f}$ · Ekuitas {usd[2]:,.0f}$">{v:+.0f}</td>')
    yr = next((x["ret"] for x in D["yearly"] if x["year"] == y), None)
    hm.append(f"<tr><th>{y}</th>{''.join(cells)}<td><b>{yr:+.0f}</b></td></tr>")
hm.append("</tbody></table></div>")
heat = "".join(hm)

# ---------------- rolling + start dates
rl = D["rolling"]
roll_rows = [[k.replace("m", " bulan"), str(v["n"]), f"{v['p_loss']:.0f}%", sgn(v["median"]), sgn(v["worst"]), sgn(v["best"]), v["worst_end"]] for k, v in rl.items()]
sd_rows = [[s["start"], num(s["end_usd"]) + " $", sgn((s["end_usd"] / 300 - 1) * 100, 0), sgn(s["dd"], 0)] for s in D["start_dates"]]

# ---------------- variants
var_rows = []
for v in D["variants"]:
    star = " ★" if (v["q"] == 10 and v["f"] == 0.5) else ""
    var_rows.append([f"{v['q']} koin", f"{v['f']}×".replace(".", ","), num(v["final"]) + " $", f"{v['cagr']}%", f"{v['dd']}%", str(v["sharpe"]).replace(".", ","), sgn(v["worst_month"]) + star])
buf_rows = [[f"> {b['exit_rank']}" + (" ★" if b["exit_rank"] == 15 else ""), num(b["entries_pm"], 1), num(b["final"]) + " $", f"{b['cagr']}%", f"{b['dd']}%", str(b["sharpe"]).replace(".", ",")] for b in D["buffer"]]
sens_rows = [
    ["Setting final (10 koin, buffer 15, 0,5×, + flush)", num(S["final"]) + " $", pct(S["cagr"]), pct(S["maxdd"])],
    ["Lookback 7 hari (bukan 14)*", num(D["lookback"][0]["final"]) + " $", f"{D['lookback'][0]['cagr']}%", f"{D['lookback'][0]['dd']}%"],
    ["Lookback 30 hari*", num(D["lookback"][1]["final"]) + " $", f"{D['lookback'][1]['cagr']}%", f"{D['lookback'][1]['dd']}%"],
    ["Tanpa filter BTC*", num(D["no_btc_filter"]["final"]) + " $", f"{D['no_btc_filter']['cagr']}%", f"{D['no_btc_filter']['dd']}%"],
    ["Hanya koin listing sebelum 2023*", num(D["old_coins_only"]["final"]) + " $", f"{D['old_coins_only']['cagr']}%", f"{D['old_coins_only']['dd']}%"],
    ["Biaya 2× lipat (0,14%/sisi)*", num(D["double_cost"]["final"]) + " $", f"{D['double_cost']['cagr']}%", f"{D['double_cost']['dd']}%"],
    [f"Flush ≥15 koin ({D['flush_thr'][0]['events']} event)", num(D["flush_thr"][0]["final"]) + " $", f"{D['flush_thr'][0]['cagr']}%", f"{D['flush_thr'][0]['dd']}%"],
    [f"Flush ≥20 koin ({D['flush_thr'][1]['events']} event)", num(D["flush_thr"][1]["final"]) + " $", f"{D['flush_thr'][1]['cagr']}%", f"{D['flush_thr'][1]['dd']}%"],
]

# ---------------- coins
coin_rows = [[f"<b>{esc(c['coin'])}</b>", str(c["days"]), str(c["stints"]), f"{c['wr']}%", sgn(c["avg"]), sgn(c["sum"], 0)] for c in D["coins_top"][:20]]
best_rows = [[esc(c["coin"]), sgn(c["sum"], 0), str(c["stints"])] for c in D["coins_contrib_best"]]
worst_rows = [[esc(c["coin"]), sgn(c["sum"], 0), str(c["stints"])] for c in D["coins_contrib_worst"]]
py_rows = [[y, esc(", ".join(v))] for y, v in D["coins_per_year"].items()]
mb_rows = [[esc(t["coin"]), t["entry"], str(t["days"]), sgn(t["ret"])] for t in D["mom_best"]]
mw_rows = [[esc(t["coin"]), t["entry"], str(t["days"]), sgn(t["ret"])] for t in D["mom_worst"]]
rh_rows = [[h["day"], "ON" if h["btc_ok"] else "OFF", esc(", ".join(h["coins"])) if h["coins"] else "–"] for h in D["recent_holdings"][-15:-1][::-1]]
dh = MS["days_hist"]
dh_rows = [[("15+" if k == "15" else k) + " hari", str(v), f"{v / MS['n'] * 100:.0f}%".replace(".", ",")] for k, v in dh.items()]

# ---------------- flush
fe = D["flush_events"]
fe_rows = [[e["t"], str(e["n"]), str(e["taken"]), sgn(e["avgR"], 2, "R"), f"{e['wins']}/{e['taken']}", f"{e['hold_h']:.0f} j", esc(", ".join(e["coins"]))] for e in fe[::-1]]
fe_recent = fe_rows[:12]
fe_years = {}
for e in fe:
    y = e["t"][:4]; fe_years.setdefault(y, []).append(e["avgR"])
fey_rows = [[y, str(len(v)), sgn(sum(v) / len(v), 2, "R"), f"{sum(1 for x in v if x > 0)}/{len(v)}"] for y, v in fe_years.items()]
fc_rows = [[esc(c["coin"]), str(c["n"]), sgn(c["avgR"], 2, "R")] for c in D["flush_coins"][:15]]

# ---------------- costs
cost_rows = [[y, num(C["fee_usd_by_year"].get(y, 0)) + " $", sgn(C["funding_usd_by_year"].get(y, 0), 0, " $")] for y in C["fee_usd_by_year"]]

DATA_JS = json.dumps({"eq": D["equity"], "mom": D["equity_mom1x"], "fl": D["equity_flush"], "dd": D["drawdown"]})

faq = [
    ("Kenapa 10 koin? Kemarin katanya 7.",
     "Kemarin saya pakai aturan \"10% teratas\". Rata-rata historisnya 6,7 koin karena tahun 2020–2021 jumlah koin masih sedikit, tapi di universe sekarang (±150 koin) 10% = 15 koin. Dengan 300 USDT × 0,5 = 150 USDT, 15 koin berarti 10 USDT per koin, persis di batas minimum order HYPE. Karena itu saya ganti ke jumlah tetap dan menguji 3/5/7/10/15 koin. Hasilnya 10 koin punya risiko paling rendah (Sharpe 1,86, bulan terburuk −11,6%), dan 15 USDT per koin aman di atas minimum. Lihat tabel Skenario."),
    ("Berapa trade per bulan?",
     f"Momentum rata-rata <b>{num(TA['mom_in_all'], 1)} koin baru masuk per bulan</b> (≈{num(TA['mom_orders_all'], 0)} order beli+jual). Di bulan yang filter BTC-nya aktif: {num(TA['mom_in_active'], 1)} entry. Flush rata-rata <b>{num(TA['fl_ev'], 2)} event per bulan</b> dengan ±{num(TA['fl_tr'], 0)} trade. Ada {TA['months_no_flush']} dari 81 bulan tanpa flush sama sekali, dan {TA['months_no_mom']} bulan momentum total cash. Jadi rata-rata sekitar 1–2 perubahan momentum per hari, dan flush sekitar sekali sebulan tapi langsung 10–15 koin."),
    ("Koin apa saja yang dibeli?",
     f"Koinnya <b>berganti terus</b>, bukan daftar tetap. Setiap hari dipilih 10 koin dengan return 14 hari tertinggi. Kalau mulai hari ini (data close {HT['asof']}): <b>{', '.join(picks)}</b>. Dalam 6,7 tahun ada {D['n_coins_ever']} koin berbeda yang pernah dipegang. Yang paling sering: ETH, BNB, SOL, ZEC, LINK, BTC, ADA. Lihat bagian Koin."),
    ("Jam berapa eksekusinya?",
     "Momentum: sekali sehari setelah candle harian close, 00:00 UTC = <b>07:00 WIB</b>. Hitung ranking, lalu beli/jual di harga open sekitar jam itu. Flush: dicek setiap close 4h, yaitu <b>07:00, 11:00, 15:00, 19:00, 23:00, 03:00 WIB</b>. Kalau ≥10 koin memberi sinyal, entry di open bar berikutnya (jam yang sama)."),
    ("Kalau saya telat eksekusi beberapa jam?",
     "Backtest memakai harga open tepat 00:00 UTC. Telat beberapa jam <b>belum diuji</b>. Untuk momentum (pegang rata-rata 6,9 hari) efeknya kemungkinan kecil, tapi bisa merugikan di hari yang bergerak kencang. Untuk flush, telat lebih berbahaya karena rebound sering terjadi di 4–8 jam pertama. Solusinya: pakai bot."),
    ("Bagaimana aturan keluar momentum? Ada TP/SL?",
     "Tidak ada TP dan tidak ada SL harga. Koin dibeli saat masuk peringkat 1–10, dan <b>dijual kalau peringkatnya turun ke > 15</b> (buffer) atau kalau BTC close di bawah EMA50 harian (semua dijual). Rata-rata pegang 6,9 hari, median 4 hari. Win rate per posisi hanya 38,5%, tetapi rata-rata posisi untung +26,7% vs rugi −8,8%. Jadi momentum hidup dari sedikit pemenang besar."),
    ("Kenapa tidak pakai SL untuk momentum? Bukankah berbahaya?",
     "Di backtest, \"stop\"-nya adalah ranking harian. Kalau koin anjlok, peringkatnya turun dan koin dijual besok pagi. Posisi terburuk masih bisa −50% s/d −60% (contoh BULLA, SAGA, BTR di 2026), tapi karena tiap koin hanya 5% ekuitas (0,5× / 10), kerugiannya sekitar −3% ekuitas. SL harga (misalnya −25%) <b>belum diuji</b> dan bisa merusak momentum karena koin pump sering koreksi tajam dulu. Kalau mau, uji dulu sebelum dipakai."),
    ("Aturan flush lengkapnya?",
     f"Di setiap close 4h, cek semua koin: (1) close candle sebelumnya ≤ Bollinger bawah (20, 2σ) dan close sekarang > Bollinger bawah (naik kembali ke dalam band); (2) volume candle ini > 1,5× rata-rata volume 20 candle. Kalau ≥10 koin memenuhi keduanya di candle yang sama, long semua (maks 15, pilih acak) di open berikutnya. SL = entry − 2×ATR(14) 4h, TP = entry + 2×ATR(14) 4h, keluar paksa setelah 48 candle (8 hari). Hasil: {FS['tp_hit']}% kena TP, {FS['sl_hit']}% kena SL, {FS['time_exit']}% keluar waktu. Median pegang {FS['median_hold_h']:.0f} jam."),
    ("Kenapa flush harus ≥10 koin? Kalau 1 koin saja?",
     "Sinyal BB-revert + volume di satu koin rata-rata <b>rugi</b> (−0,04R, 1.507 event). Edge baru muncul kalau banyak koin flush bersamaan, karena artinya ada likuidasi massal yang biasanya diikuti rebound. Makin banyak koin, makin bagus: ≥10 koin +0,16R, ≥20 +0,28R, ≥30 +0,38R per event. Tapi eventnya juga makin jarang."),
    ("Berapa ukuran posisi dengan 300 USDT?",
     f"Momentum: 300 × 0,5 / 10 = <b>{num(per_coin_300, 0)} USDC per koin</b> (notional). Flush: risiko 0,5% = 1,5 USDC per koin. Dengan SL median {num(FS['stop_median'], 1)}%, notional ≈ 1,5 / 0,078 ≈ <b>19 USDC per koin</b>. Total risiko per event maks 8% (= 2,4 USDC per koin kalau event-nya besar). Ukuran dihitung ulang dari ekuitas terbaru setiap kali buka posisi baru."),
    ("Modal minimal berapa?",
     "Minimum order HYPE 10 USDC. Momentum butuh ekuitas × 0,5 / 10 ≥ ±12 USDC (beri ruang di atas 10), jadi <b>modal ≥ ±250 USDC</b>. Flush kadang butuh notional kecil (SL lebar 15% → 1,5/0,15 = 10 USDC), jadi 300 USDC memang mepet di batas bawah. Dengan 500–1.000 USDC jauh lebih nyaman."),
    ("Leverage berapa dan cross atau isolated?",
     f"Momentum hanya 0,5× ekuitas, jadi sebenarnya tidak butuh leverage. Tapi flush kadang menumpuk: notional rata-rata gabungan {num(S['avg_gross_x'], 2)}× ekuitas, puncak {num(S['max_gross_x'], 1)}×. Pakai <b>cross margin di subaccount khusus</b> (atau isolated maks 1–2×). Saran v1 \"isolated 3–5×\" salah: crash 10 Okt 2025 membuat median altcoin −65% intrabar, sehingga posisi 3× ke atas terlikuidasi walaupun SL dipasang (SL bisa terlewat saat wick)."),
    ("HYPE pakai USDC, bukan USDT?",
     "Ya. Hyperliquid memakai USDC sebagai margin, jadi 300 USDT harus diubah ke USDC dan di-deposit ke Hyperliquid (lewat Arbitrum). Semua angka di report ini berlaku sama untuk USDC."),
    ("Koin yang sama dipegang momentum dan flush sekaligus?",
     "Bisa terjadi. Di HYPE satu koin = satu posisi (one-way), jadi ukurannya dijumlah. Pasang TP/SL flush sebagai order <b>reduce-only</b> seukuran bagian flush saja, supaya bagian momentum tidak ikut tertutup. Bot harus mencatat dua bagian ini terpisah."),
    ("Bagaimana kalau koin top-10 tidak ada di HYPE atau baru listing?",
     "Ranking dihitung langsung dari koin yang ada di HYPE (universe: perp HYPE yang belum delist, listing ≥ 60 hari). Jadi koin yang tidak ada di HYPE otomatis tidak ikut. Backtest memakai universe Binance; cek silang momentum di candle HYPE memberi hasil serupa (excess +0,30%/hari, t 4,0)."),
    ("Kenapa ada filter BTC > EMA50?",
     f"Momentum alt hanya bekerja saat pasar naik. Filter ini ON {BF['pct_on']}% dari hari, dan di 2022 hanya ON 19%, sehingga menyelamatkan dari sebagian besar bear. Tanpa filter, max DD naik dari −33% ke {D['no_btc_filter']['dd']}%. Filter berganti sekitar {num(BF['switches_per_year'], 0)}× per tahun (±2× per bulan), dan biaya whipsaw-nya sudah dihitung. Pergantian terakhir: {BF['last_switch']} (ON)."),
    ("Status hari ini?",
     f"Data close {HT['asof']}: BTC {num(HT['btc_close'])} > EMA50 {num(HT['btc_ema50'])}, jadi filter <b>ON</b>. Momentum aktif, beli 10 koin: {', '.join(picks)}. Flush: tidak ada sinyal (maks 3 koin per candle dalam 5 hari terakhir). Event flush terakhir di backtest: {fe[-1]['t']} UTC, {fe[-1]['n']} koin."),
    ("Kenapa tidak short?",
     "Sudah diuji: momentum short (short koin terlemah), reversal, dan trend MA short <b>tidak punya edge</b> (0 dari 192 konfigurasi short lolos). Sebagian karena survivorship (koin lemah yang mati tidak ada di data), sebagian karena alt cenderung pump tiba-tiba."),
    ("Berapa realistisnya hasil live?",
     "Backtest CAGR 89% adalah <b>batas atas</b>. Universe dipilih dari koin yang hidup dan ramai per Sep 2026, jadi koin yang pump lalu mati tidak ada, dan koin yang baru pump otomatis ikut. Angka Agu–Sep 2026 paling bias. Banyak riset momentum crypto memakai asumsi setengah atau kurang dari angka backtest. Ini hasil riset, bukan janji atau nasihat keuangan."),
    ("Kerugian terburuk yang harus siap ditanggung?",
     f"Backtest: max DD {pct(S['maxdd'])}, bulan terburuk {pct(S['worst_month'], 1)}, hari terburuk {pct(S['worst_day'], 1)}, underwater terlama {S['longest_underwater_days']:.0f} hari. Dari jendela 12 bulan, {rl['12m']['p_loss']:.0f}% berakhir rugi (terburuk {rl['12m']['worst']:+.1f}%). Live bisa lebih buruk, jadi rencanakan untuk DD −50%."),
    ("Kalau 2022 terulang?",
     "2022 di backtest: −14% setahun, DD −21%. Filter BTC membuat momentum hampir selalu cash, dan flush justru untung (+329 $ dari ekuitas ±2.000 $). Tapi crash yang sangat cepat (sebelum filter mati) tetap bisa memukul."),
    ("Kapan sebaiknya berhenti?",
     "Tentukan sebelum mulai, misalnya: (1) DD > 45% dari puncak; (2) 9 bulan berturut-turut kalah dari basket \"beli semua koin\"; (3) hasil forward test 3 bulan jauh di bawah backtest periode yang sama. Jangan berhenti hanya karena 1–3 bulan rugi: di backtest 38% bulan memang negatif."),
    ("Bisa jalankan momentum saja atau flush saja?",
     "Bisa. Momentum saja 1×: CAGR 125%, DD −67%. Flush saja: CAGR 20%, DD −19%, 300 → 1.010 $. Gabungan dengan momentum 0,5× punya rasio untung/risiko terbaik karena korelasinya hanya 0,08."),
    ("Kenapa lookback 14 hari, bukan 7 atau 30?",
     f"14 hari dipilih dari grid 2020–2024. Hasil tetangganya: 7 hari CAGR {D['lookback'][0]['cagr']}% DD {D['lookback'][0]['dd']}%, 30 hari CAGR {D['lookback'][1]['cagr']}% DD {D['lookback'][1]['dd']}% (versi tanpa buffer). Semuanya positif, jadi tidak rapuh."),
    ("Apakah ini overfit?",
     "Risikonya ada, tapi beberapa tanda bagus: (1) 128 dari 192 variasi momentum lolos IS t>2 dan OOS>0; (2) 3/5/7/10/15 koin semuanya positif; (3) flush membaik monoton seiring jumlah koin; (4) OOS 2025–2026 positif; (5) cek di candle HYPE serupa. Yang <b>tidak</b> bisa dihapus: bias universe (survivorship/selection)."),
    ("Biaya trading berapa?",
     f"Backtest: 0,07% per sisi (fee taker + slippage) + funding riil. Momentum turnover ±{C['avg_turnover']:.0f}% per hari aktif, sehingga fee ≈ {num(C['mom_fee_pct_equity_per_year'], 1)}% ekuitas per tahun. Fee HYPE base tier sekitar 0,045% taker / 0,015% maker (cek tier akunmu). Dengan biaya 2× lipat, CAGR turun ke {D['double_cost']['cagr']}%."),
    ("Funding?",
     "Funding dihitung sebagai biaya riil (data Binance). Koin momentum sering punya funding ekstrem. Di 2026 strategi justru <b>menerima</b> ±2.200 $ funding karena banyak koin pump dengan funding negatif (short ramai). Ini bisa berbeda di HYPE (funding per jam, rumus berbeda), jadi jangan mengandalkannya."),
    ("Perlu data berbayar?",
     "Tidak. Semuanya dari candle (OHLCV): ranking return 14 hari, EMA50 BTC, Bollinger, volume, ATR. Semua gratis via API HYPE (endpoint info, type candleSnapshot). Tidak perlu OI, funding, atau taker volume sebagai sinyal."),
    ("Bisa dijalankan manual?",
     "Momentum manual bisa: ±10 menit setiap jam 07:00 WIB, rata-rata 1–2 perubahan per hari. Flush sulit manual karena dicek 6× sehari, termasuk jam 03:00 dan 23:00 WIB, dan harus pasang 10–15 order + TP/SL sekaligus. Sangat disarankan bot."),
    ("Hubungannya dengan MEX 3.0?",
     "Terpisah total. MEX 3.0 jalan live di HYPE (13 koin). Jalankan RMF di <b>subaccount terpisah</b> supaya risiko dan margin tidak bercampur. Cek juga apakah ada koin yang dipegang dua strategi sekaligus, karena eksposurnya jadi dobel."),
    ("Kenapa indikator favorit (VWAP, SMC, RSI) tidak dipakai?",
     "Sudah diuji 1,29 juta kombinasi. Di 15m dan 1h, tidak ada satu pun yang mengalahkan entry acak setelah biaya. Di 4h/1d hanya trend + trailing yang sedikit positif. Edge yang bertahan justru datang dari perbandingan antar koin, bukan pola di satu chart. Detail di REPORT_TA_EDGE.md."),
    ("Data sampai kapan?",
     f"Backtest Binance 2020-01 s/d 2026-10-02. Ranking hari ini dari API HYPE langsung (close {HT['asof']}). Periode OOS: 2025-01 s/d 2026-10. Report dibuat 2026-10-04."),
]
faq_html = "".join(f"<details class='faq'><summary>{esc(q)}</summary><div>{a}</div></details>" for q, a in faq)

gloss = [("R", "Satuan untung/rugi relatif terhadap risiko. +1R = untung sebesar jarak SL. Flush: 1R = 2×ATR."),
         ("ATR(14)", "Average True Range 14 candle: rata-rata rentang gerak harga. Dipakai untuk jarak SL/TP flush."),
         ("Bollinger bawah (20, 2)", "SMA20 close dikurangi 2× standar deviasi 20 close."),
         ("EMA50", "Exponential moving average 50 hari dari close harian BTC."),
         ("Return 14 hari", "close hari ini ÷ close 14 hari sebelumnya − 1. Dasar ranking momentum."),
         ("Buffer 15", "Koin dibeli saat peringkat ≤10, baru dijual saat peringkat >15. Mengurangi keluar-masuk."),
         ("Drawdown (DD)", "Penurunan dari puncak ekuitas tertinggi sebelumnya."),
         ("CAGR", "Pertumbuhan majemuk per tahun."),
         ("Sharpe", "Return ÷ volatilitas (tahunan). >1 bagus, >2 sangat bagus (di backtest)."),
         ("IS / OOS", "In-sample 2020–2024 (untuk memilih aturan) / out-of-sample 2025–2026 (untuk cek)."),
         ("Survivorship bias", "Data hanya berisi koin yang masih hidup, jadi hasil long terlihat lebih bagus dari kenyataan."),
         ("Notional", "Nilai posisi = harga × jumlah koin. 0,5× ekuitas = posisi total setengah dari modal."),
         ("Turnover", "Persentase portofolio yang diganti per hari.")]
gloss_html = "".join(f"<div class='g'><dt>{esc(a)}</dt><dd>{esc(b)}</dd></div>" for a, b in gloss)

page = open(os.path.join(ta.HERE, "rmf_template.html"), encoding="utf-8").read()
rep = {
    "FINAL": num(S["final"]), "CAGR": pct(S["cagr"]), "MAXDD": pct(S["maxdd"]), "SHARPE": num(S["sharpe"], 2), "VOL": pct(S["vol_ann"]),
    "WM": pct(S["worst_month"], 1), "WD": pct(S["worst_day"], 1), "BM": pct(S["best_month"], 0), "POSM": pct(S["pos_months"]), "UW": f"{S['longest_underwater_days']:.0f}",
    "OOS_FINAL": num(O["final"]), "OOS_CAGR": pct(O["cagr"]), "OOS_DD": pct(O["maxdd"]), "OOS_WM": pct(O["worst_month"], 1), "OOS_POSM": pct(O["pos_months"]),
    "ASOF": HT["asof"], "BTC": num(HT["btc_close"]), "EMA": num(HT["btc_ema50"]), "BTCOK": "ON" if HT["btc_ok"] else "OFF",
    "PICKS": ", ".join(picks), "PERCOIN": num(per_coin_300, 0),
    "TODAY_TABLE": table(["#", "Koin", "Return 14h", "Vol 30h (jt $/hari)", "Aksi"], today_rows),
    "MOM_IN": num(TA["mom_in_all"], 1), "MOM_IN_ACT": num(TA["mom_in_active"], 1), "MOM_ORD": num(TA["mom_orders_all"], 0),
    "FL_EV": num(TA["fl_ev"], 2), "FL_TR": num(TA["fl_tr"], 0), "NOFL": str(TA["months_no_flush"]), "NOMOM": str(TA["months_no_mom"]),
    "TY_TABLE": table(["Tahun", "Momentum entry", "Order momentum (beli+jual)", "Entry/bulan", "Event flush", "Trade flush", "Flush/bulan", "Filter BTC ON"], ty_rows),
    "TPM_TABLE": table(["Bulan", "Mom. beli", "Mom. jual", "Event flush", "Trade flush", "Total order*", "Hari momentum aktif"], tpm_rows),
    "Y_TABLE": table(["Tahun", "Return", "Max DD", "Ekuitas akhir ($)", "P&L momentum", "P&L flush", "Filter BTC ON"], y_rows),
    "HEAT": heat,
    "ROLL_TABLE": table(["Jendela", "Jumlah", "Peluang rugi", "Median", "Terburuk", "Terbaik", "Akhir jendela terburuk"], roll_rows),
    "SD_TABLE": table(["Mulai 300 $ pada", "Nilai 12 bulan kemudian", "Return", "Max DD dalam 12 bulan"], sd_rows),
    "VAR_TABLE": table(["Jumlah koin", "Ukuran momentum", "300 $ menjadi", "CAGR", "Max DD", "Sharpe", "Bulan terburuk"], var_rows),
    "BUF_TABLE": table(["Jual kalau peringkat", "Entry/bulan", "300 $ menjadi", "CAGR", "Max DD", "Sharpe"], buf_rows),
    "SENS_TABLE": table(["Variasi", "300 $ menjadi", "CAGR", "Max DD"], sens_rows),
    "COIN_TABLE": table(["Koin", "Hari dipegang", "Kali masuk", "Win rate", "Rata2/posisi", "Total %"], coin_rows),
    "BEST_TABLE": table(["Koin", "Total % (jumlah semua posisi)", "Kali masuk"], best_rows),
    "WORST_TABLE": table(["Koin", "Total %", "Kali masuk"], worst_rows),
    "PY_TABLE": table(["Tahun", "Paling lama dipegang (hari)"], py_rows),
    "MB_TABLE": table(["Koin", "Masuk", "Hari", "Return"], mb_rows), "MW_TABLE": table(["Koin", "Masuk", "Hari", "Return"], mw_rows),
    "RH_TABLE": table(["Tanggal (sinyal)", "Filter BTC", "10 koin dipegang"], rh_rows),
    "DH_TABLE": table(["Lama pegang", "Jumlah posisi", "Porsi"], dh_rows),
    "MS_N": num(MS["n"]), "MS_MED": num(MS["median_days"], 0), "MS_MEAN": num(MS["mean_days"], 1), "MS_WR": num(MS["wr"], 1), "MS_AVG": num(MS["avg_ret"], 1),
    "MS_AW": num(MS["avg_win"], 1), "MS_AL": num(MS["avg_loss"], 1), "MS_MEDR": num(MS["median_ret"], 1), "NCOINS": str(D["n_coins_ever"]),
    "FS_EV": str(FS["events"]), "FS_TR": num(FS["trades"]), "FS_WR": num(FS["wr"], 1), "FS_R": num(FS["avgR"], 2), "FS_EVWR": num(FS["ev_wr"], 1),
    "FS_HOLD": f"{FS['median_hold_h']:.0f}", "FS_SL": num(FS["stop_median"], 1), "FS_SL10": num(FS["stop_p10"], 1), "FS_SL90": num(FS["stop_p90"], 1),
    "FS_TP": num(FS["tp_hit"], 1), "FS_SLH": num(FS["sl_hit"], 1), "FS_TE": num(FS["time_exit"], 1),
    "FS_BEST": f"{FS['best']['t']} ({FS['best']['taken']} koin, {FS['best']['avgR']:+.2f}R)", "FS_WORST": f"{FS['worst']['t']} ({FS['worst']['taken']} koin, {FS['worst']['avgR']:+.2f}R)",
    "FE_RECENT": table(["Waktu entry (UTC)", "Koin sinyal", "Diambil", "Hasil", "Menang", "Median pegang", "Koin"], fe_recent),
    "FE_ALL": table(["Waktu entry (UTC)", "Koin sinyal", "Diambil", "Hasil", "Menang", "Median pegang", "Koin"], fe_rows),
    "FEY_TABLE": table(["Tahun", "Event", "Rata2 per event", "Event untung"], fey_rows),
    "FC_TABLE": table(["Koin", "Kali ikut flush", "Rata2 R"], fc_rows),
    "COST_TABLE": table(["Tahun", "Fee momentum (≈)", "Funding momentum (+ = bayar)"], cost_rows),
    "FEE_PY": num(C["mom_fee_pct_equity_per_year"], 1), "FUND_PY": num(C["mom_funding_pct_equity_per_year"], 1), "TURN": f"{C['avg_turnover']:.0f}",
    "BF_ON": str(BF["pct_on"]), "BF_SW": num(BF["switches_per_year"], 0), "BF_LAST": BF["last_switch"],
    "R1P": f"{rl['1m']['p_loss']:.0f}", "R12P": f"{rl['12m']['p_loss']:.0f}", "R12W": num(rl["12m"]["worst"], 1), "R12M": num(rl["12m"]["median"], 0),
    "GROSS_AVG": num(S["avg_gross_x"], 2), "GROSS_MAX": num(S["max_gross_x"], 1),
    "UPDATE": __import__("update_v2").build(D, table),
    "FAQ": faq_html, "GLOSS": gloss_html, "DATA_JS": DATA_JS, "LASTFL": f"{fe[-1]['t']} UTC ({fe[-1]['n']} koin)",
}
for k, v in rep.items():
    page = page.replace("[[" + k + "]]", str(v))
import re
left = re.findall(r"\[\[[A-Z_0-9]+\]\]", page)
assert not left, left
open(os.path.join(REP, "RMF_report.html"), "w", encoding="utf-8").write(page)
print("written", len(page))
