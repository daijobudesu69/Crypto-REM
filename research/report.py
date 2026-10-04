"""Build the tables for reports/REPORT_TA_EDGE.md (+ full CSVs in reports/tables/).

    python report.py   -> prints markdown snippets, writes CSVs
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import ta

REP = os.path.join(os.path.dirname(ta.HERE), "reports")
TAB = os.path.join(REP, "tables")
os.makedirs(TAB, exist_ok=True)
TFS = ["15m", "1h", "4h", "1d"]

FAMILY = {
    "MA": ["ema_x_9_21", "ema_x_20_50", "ema_x_50_200", "sma_x_50_200", "price_x_ema50", "price_x_ema200", "ma_ribbon_align", "ema20_pullback"],
    "Trend/momentum": ["supertrend_flip", "psar_flip", "ha_flip", "donchian_20", "donchian_55", "macd_x", "macd_zero_x", "adx_di_x", "ichi_tk_x", "ichi_kumo_break"],
    "Oscillator": ["rsi_30_70_rev", "rsi_50_x", "rsi2_extreme", "rsi_divergence", "stoch_rev", "willr_rev", "cci_rev", "mfi_rev", "zscore_revert"],
    "Volatilitas": ["bb_revert", "bb_breakout", "keltner_breakout", "squeeze_fire", "nr7_breakout", "inside_bar_break"],
    "Candle": ["engulfing", "pinbar"],
    "VWAP": ["vwap_x", "vwap_1sd_break", "vwap_2sd_revert", "vwap_week_x", "vwap_month_x", "vwap_reclaim"],
    "Volume": ["vol_spike_candle", "vol_spike_reversal", "vol_climax", "vol_dryup_break", "obv_break_20"],
    "Taker flow (delta/CVD)": ["delta_surge", "delta_absorption", "cvd_divergence", "delta_flip"],
    "SMC/ICT": ["smc_bos", "smc_choch", "smc_fvg_retest", "smc_ob_retest", "smc_sweep_swing", "sweep_pdh_pdl", "break_pdh_pdl",
                "sweep_pwh_pwl", "break_pwh_pwl", "asia_range_break", "asia_range_sweep"],
}
FAM_OF = {t: f for f, ts in FAMILY.items() for t in ts}


def fmt(x, d=2):
    return "–" if pd.isna(x) else f"{x:+.{d}f}"


def singles():
    """best exit chosen on IS per (tf, dir, trigger); OOS shown; flag beats random baseline in both periods."""
    b = pd.read_parquet(os.path.join(ta.OUT, "baseline.parquet"))
    rows = []
    for tf in TFS:
        p = os.path.join(ta.OUT, f"stage2_{tf}_summary.parquet")
        if not os.path.exists(p):
            continue
        s = pd.read_parquet(p)
        s = s[(s.src == "single") & (s.n_is >= 30)]
        s = s.merge(b.rename(columns={"avgR_is": "b_is", "avgR_oos": "b_oos", "n": "b_n"}), on=["tf", "dir", "exit"], how="left")
        best = s.sort_values("avgR_is", ascending=False).drop_duplicates(["dir", "trigger"])
        rows.append(best)
    d = pd.concat(rows, ignore_index=True)
    d["family"] = d.trigger.map(FAM_OF)
    d["pos_both"] = (d.avgR_is > 0) & (d.avgR_oos > 0)
    d["beats_base"] = (d.avgR_is > d.b_is) & (d.avgR_oos > d.b_oos)
    d.to_csv(os.path.join(TAB, "single_indicators.csv"), index=False)
    return d


def singles_matrix(d):
    out = []
    for dirn in ("long", "short"):
        x = d[d.dir == dirn]
        lines = ["| Grup | Indikator | " + " | ".join(TFS) + " |", "|---|---|" + "---|" * len(TFS)]
        for fam, trigs in FAMILY.items():
            for t in trigs:
                cells = []
                for tf in TFS:
                    r = x[(x.tf == tf) & (x.trigger == t)]
                    if r.empty:
                        cells.append("–"); continue
                    r = r.iloc[0]
                    mark = " ✅" if (r.pos_both and r.beats_base and r.t_oos > 2 and r.t_is > 2) else (" ·" if r.pos_both else "")
                    cells.append(f"{r.avgR_is:+.2f} / {r.avgR_oos:+.2f}{mark}")
                out_t = t + (" ⚠️taker" if ta.DATA_TAG.get(t) == "taker" else "")
                lines.append(f"| {fam} | {out_t} | " + " | ".join(cells) + " |")
        out.append((dirn, "\n".join(lines)))
    return out


def singles_count(d):
    lines = ["| TF | Long positif IS & OOS | Short positif IS & OOS | Long > baseline acak (IS & OOS) | Short > baseline acak |", "|---|---|---|---|---|"]
    for tf in TFS:
        x = d[d.tf == tf]
        if x.empty:
            continue
        L, S = x[x.dir == "long"], x[x.dir == "short"]
        lines.append(f"| {tf} | {L.pos_both.sum()} / {len(L)} | {S.pos_both.sum()} / {len(S)} | {L.beats_base.sum()} | {S.beats_base.sum()} |")
    return "\n".join(lines)


def finalists_table():
    f = pd.read_parquet(os.path.join(ta.OUT, "finalists.parquet"))
    f.to_csv(os.path.join(TAB, "finalists.csv"), index=False)
    lines = ["| # | Strategi | Data | n IS | avgR IS | n OOS | avgR OOS | baseline acak OOS | t harian IS / OOS | HYPE n / avgR | Portofolio OOS CAGR / DD |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(f.itertuples(), 1):
        hl = f"{r.hl_n} / {fmt(r.hl_avgR)}" if r.hl_n else "–"
        lines.append(f"| {i} | {r.name} | {r.data} | {r.n_is} | {fmt(r.avgR_is)} | {r.n_oos} | {fmt(r.avgR_oos)} | {fmt(r.base_avgR_oos)} | "
                     f"{r.t_daily_is:.1f} / {r.t_daily_oos:.1f} | {hl} | {r.oos_cagr*100:.0f}% / {r.oos_max_dd*100:.0f}% |")
    return f, "\n".join(lines)


if __name__ == "__main__":
    ta.signals(ta.load("BTCUSDT", "4h"), "4h", "BTCUSDT"); ta.signals(ta.load("BTCUSDT", "1h"), "1h", "BTCUSDT")
    d = singles()
    print(singles_count(d))
    for dirn, m in singles_matrix(d):
        print("\n###", dirn); print(m)
    if os.path.exists(os.path.join(ta.OUT, "finalists.parquet")):
        print(finalists_table()[1])
