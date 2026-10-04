"""Assemble reports/REPORT_TA_EDGE.md from the result files.   python build_report.py"""
import os, sys, glob
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import ta
import report as R

O = ta.OUT
TFS = R.TFS


def f2(x, d=2, pct=False):
    if pd.isna(x):
        return "–"
    return f"{x*100:+.{d}f}%" if pct else f"{x:+.{d}f}"


def counts():
    rows = ["| TF | Uji stage 1 (trigger × filter × arah × horizon) | Lolos stage 1 | Trade tersimulasi stage 2 |", "|---|---|---|---|"]
    tot1 = tot2 = 0
    for tf in TFS:
        e = os.path.join(O, f"event_{tf}.parquet")
        if not os.path.exists(e):
            continue
        n1 = len(pd.read_parquet(e, columns=["trigger"]))
        n2 = int(pd.read_parquet(os.path.join(O, f"stage2_{tf}_agg.parquet"), columns=["n"]).n.sum())
        ps = len(pd.read_parquet(os.path.join(O, f"stage1_pass_{tf}.parquet"), columns=["trigger"]))
        rows.append(f"| {tf} | {n1:,} | {ps:,} | {n2:,} |"); tot1 += n1; tot2 += n2
    rows.append(f"| **Total** | **{tot1:,}** | | **{tot2:,}** |")
    return "\n".join(rows), tot1, tot2


def baseline_tbl():
    b = pd.read_parquet(os.path.join(O, "baseline.parquet"))
    rows = ["| TF | Long IS | Long OOS | Short IS | Short OOS |", "|---|---|---|---|---|"]
    for tf in TFS:
        x = b[b.tf == tf]
        L, S = x[x.dir == "long"], x[x.dir == "short"]
        rows.append(f"| {tf} | {L.avgR_is.min():+.2f} … {L.avgR_is.max():+.2f} | {L.avgR_oos.min():+.2f} … {L.avgR_oos.max():+.2f} | "
                    f"{S.avgR_is.min():+.2f} … {S.avgR_is.max():+.2f} | {S.avgR_oos.min():+.2f} … {S.avgR_oos.max():+.2f} |")
    return "\n".join(rows)


def best_singles(d, n=12):
    x = d[d.pos_both & d.beats_base & (d.t_is > 2) & (d.t_oos > 2)].copy()
    x["edge_oos"] = x.avgR_oos - x.b_oos
    x = x.sort_values("edge_oos", ascending=False).head(n)
    rows = ["| TF | Arah | Indikator | Grup | Exit | n IS | avgR IS | n OOS | avgR OOS | Baseline acak OOS | Data |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in x.itertuples():
        rows.append(f"| {r.tf} | {r.dir} | {r.trigger} | {r.family} | {r.exit} | {r.n_is:,} | {r.avgR_is:+.2f} | {r.n_oos:,} | {r.avgR_oos:+.2f} | {r.b_oos:+.2f} | {ta.DATA_TAG.get(r.trigger, 'ohlcv')} |")
    return "\n".join(rows)


def family_tbl(d):
    rows = ["| Grup | 15m | 1h | 4h | 1d |", "|---|---|---|---|---|"]
    for fam in R.FAMILY:
        cells = []
        for tf in TFS:
            x = d[(d.tf == tf) & (d.family == fam)]
            if x.empty:
                cells.append("–"); continue
            ok = (x.pos_both & x.beats_base & (x.t_is > 2) & (x.t_oos > 2)).sum()
            cells.append(f"{ok}/{len(x)} (OOS rata2 {x.avgR_oos.mean():+.2f})")
        rows.append(f"| {fam} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def finalists():
    parts = [pd.read_parquet(p) for p in sorted(glob.glob(os.path.join(O, "finalists_*.parquet")))]
    f = pd.concat(parts, ignore_index=True)
    f["survive"] = (f.t_daily_is >= 2) & (f.t_daily_oos >= 2) & (f.days_oos >= 20)
    f.to_csv(os.path.join(R.TAB, "finalists.csv"), index=False)
    rows = ["| # | Strategi | Data | n IS / OOS | avgR IS / OOS | Baseline acak OOS | **t harian IS / OOS** | Hari OOS | HYPE n / avgR / t harian | Portofolio penuh CAGR / DD | Lolos? |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(f.sort_values(["survive", "t_daily_oos"], ascending=False).itertuples(), 1):
        hl = f"{r.hl_n} / {f2(r.hl_avgR)} / {r.hl_t_daily:.1f}" if r.hl_n else "– (tak ada taker di HYPE)" if "taker" in r.data else "–"
        rows.append(f"| {i} | {r.name.replace(' | ', ' — ')} | {r.data} | {r.n_is} / {r.n_oos} | {r.avgR_is:+.2f} / {r.avgR_oos:+.2f} | {f2(r.base_avgR_oos)} | "
                    f"{r.t_daily_is:.1f} / {r.t_daily_oos:.1f} | {r.days_oos} | {hl} | {r.pf_cagr*100:.0f}% / {r.pf_max_dd*100:.0f}% | {'✅' if r.survive else '❌'} |")
    return f, "\n".join(rows)


def xsec_tbl():
    g = pd.read_parquet(os.path.join(O, "xsec_grid.parquet"))
    rows = ["| Strategi | Konfigurasi | IS t > 2 | IS t > 2 & OOS > 0 | Median t IS | Median t OOS |", "|---|---|---|---|---|---|"]
    lab = {"mom_long": "Momentum long (beli koin terkuat)", "mom_short": "Momentum short (short koin terlemah)", "mom_ls": "Momentum long-short",
           "rev_long": "Reversal long (beli koin terlemah)", "rev_short": "Reversal short", "rev_ls": "Reversal long-short",
           "trend_long": "Trend MA long (close > EMA-N)", "trend_short": "Trend MA short", "trend_ls": "Trend MA long-short"}
    for s, l in lab.items():
        x = g[g.side == s]
        rows.append(f"| {l} | {len(x)} | {(x.t_is > 2).sum()} | {((x.t_is > 2) & (x.mean_oos > 0)).sum()} | {x.t_is.median():.2f} | {x.t_oos.median():.2f} |")
    return "\n".join(rows)


if __name__ == "__main__":
    for tf in TFS:
        ta.signals(ta.load("BTCUSDT", tf), tf, "BTCUSDT")
    d = R.singles()
    cnt, tot1, tot2 = counts()
    fin, fin_tbl = finalists()
    mats = dict(R.singles_matrix(d))
    sc = R.singles_count(d)
    tmpl = open(os.path.join(os.path.dirname(__file__), "report_template.md"), encoding="utf-8").read()
    out = tmpl.format(COUNTS=cnt, TOT1=f"{tot1:,}", TOT2=f"{tot2/1e6:.0f} juta", BASELINE=baseline_tbl(), SINGLE_COUNT=sc,
                      FAMILY=family_tbl(d), BEST_SINGLES=best_singles(d), MAT_LONG=mats["long"], MAT_SHORT=mats["short"],
                      FINALISTS=fin_tbl, N_FIN=len(fin), N_SURV=int(fin.survive.sum()), XSEC=xsec_tbl())
    import report_notes as N
    for key in ("TLDR", "FIN_NOTES", "XSEC_NOTES", "BREADTH_NOTES", "CONCLUSION"):
        out = out.replace(f"__{key}__", getattr(N, key, "(belum diisi)"))
    out = out.replace("__TOT1__", f"{tot1:,}").replace("__TOT2__", f"{tot2/1e6:.0f} juta")
    p = os.path.join(R.REP, "REPORT_TA_EDGE.md")
    open(p, "w", encoding="utf-8").write(out)
    print("written", p, len(out))
