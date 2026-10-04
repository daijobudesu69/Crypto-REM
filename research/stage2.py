"""Stage 2: real trade simulation (ATR stop / target / trailing / time stop) for every indicator alone
plus the best stage-1 combos, 6 exit schemes, all 150 coins. Costs 0.07%/side + real funding (cost only).

Selection uses IS (2020-2024) only for ranking; OOS (2025-2026) is reported, and stage-1 also requires
the OOS sign to agree (same rule as the earlier REPORT_EDGE research so results are comparable).

    python stage2.py 4h   -> results/stage2_4h_summary.parquet
"""
import os
for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(v, "1")
import sys, time, warnings
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
import ta
import trade_sim as TS  # from the data-lake research folder (same engine as REPORT_EDGE)
from stage1 import OOS_START

warnings.filterwarnings("ignore")
TOP_N = 200


def select(tf):
    ev = pd.read_parquet(os.path.join(ta.OUT, f"event_{tf}.parquet"))
    ev = ev[ev["trigger"] != "always"]
    ycols = [c for c in ev.columns if c.startswith("y20")]
    ev["years_pos"] = (ev[ycols] > 0).sum(1); ev["years_n"] = ev[ycols].notna().sum(1)
    ev["br_is"] = ev["sym_pos_is"] / ev["sym_is"].clip(lower=1)
    ev["br_oos"] = ev["sym_pos_oos"] / ev["sym_oos"].clip(lower=1)
    ev = ev[(ev.state1 != ev.state2) | (ev.state1 == "none")]
    for p in ("is", "oos"):
        se = (ev[f"mean_{p}"] / ev[f"t_{p}"]).abs()
        ev[f"tx_{p}"] = ev[f"excess_{p}"] / se
    nmin_is, nmin_oos = (100, 40) if tf == "1d" else (300, 80)
    good = ev[(ev.n_is >= nmin_is) & (ev.n_oos >= nmin_oos) & (ev.mean_is > 0) & (ev.mean_oos > 0) &
              (ev.excess_is > 0.001) & (ev.excess_oos > 0.001) & (ev.tx_is >= 3) & (ev.tx_oos >= 2) &
              (ev.br_is >= 0.55) & (ev.br_oos >= 0.5) & (ev.years_pos >= 0.7 * ev.years_n)].copy()
    good["score"] = np.minimum(good.tx_is, 1.5 * good.tx_oos)
    good["nf"] = (good.state1 != "none").astype(int) + (good.state2 != "none").astype(int)
    good = good.sort_values(["score", "nf"], ascending=[False, True]).drop_duplicates(["dir", "h", "trigger", "n_is", "n_oos"])
    good = good.drop_duplicates(["dir", "trigger", "state1", "state2"])
    good = good.groupby(["dir", "trigger"]).head(12)
    best = good.head(TOP_N)[["dir", "trigger", "state1", "state2"]]
    singles = ev[(ev.state1 == "none") & (ev.state2 == "none")][["dir", "trigger", "state1", "state2"]].drop_duplicates()
    cands = pd.concat([singles.assign(src="single"), best.assign(src="combo")]).drop_duplicates(
        ["dir", "trigger", "state1", "state2"]).reset_index(drop=True)
    cands["cid"] = np.arange(len(cands))
    return cands, good, len(ev)


def _work(args):
    sym, tf, cands = args
    warnings.filterwarnings("ignore")
    try:
        k = ta.load(sym, tf)
    except FileNotFoundError:
        return None
    if len(k) < (250 if tf == "1d" else 500):
        return None
    T, S, aux = ta.signals(k, tf, sym)
    o, h, l, c = (k[x].values.astype(float) for x in ["open", "high", "low", "close"])
    cf = k["cum_funding"].values.astype(float); a = aux["atr"]; ts = k["ts"].values
    out = []
    for r in cands.itertuples():
        d = 0 if r.dir == "long" else 1
        sig = T[r.trigger][d] & S[r.state1][d] & S[r.state2][d]
        if sig.sum() == 0:
            continue
        for en, (sl, tp, tr, mb) in TS.EXITS.items():
            ei, xi, ret, rr = TS.simulate(o, h, l, c, a, cf, sig, 1 if d == 0 else -1, sl, tp, tr, mb, TS.SIDE_COST)
            if len(ei):
                out.append(pd.DataFrame({"cid": r.cid, "exit": en, "year": pd.DatetimeIndex(ts[ei]).year,
                                         "bars": xi - ei + 1, "ret": ret, "R": rr}))
    if not out:
        return None
    t = pd.concat(out, ignore_index=True)
    t["R2"] = t["R"] ** 2; t["win"] = t["R"] > 0
    t["posR"] = t["R"].clip(lower=0); t["negR"] = (-t["R"]).clip(lower=0)
    g = t.groupby(["cid", "exit", "year"]).agg(n=("R", "size"), sumR=("R", "sum"), sumR2=("R2", "sum"), wins=("win", "sum"),
                                                posR=("posR", "sum"), negR=("negR", "sum"), bars=("bars", "sum"),
                                                sumret=("ret", "sum")).reset_index()
    g["symbol"] = sym
    return g


def summarize(agg, cands):
    agg = agg.assign(period=np.where(agg["year"] >= OOS_START, "oos", "is"))
    out = None
    for p in ("is", "oos"):
        a = agg[agg.period == p]
        g = a.groupby(["cid", "exit"])[["n", "sumR", "sumR2", "wins", "posR", "negR", "bars", "sumret"]].sum()
        mean = g.sumR / g.n
        sd = np.sqrt(np.maximum(g.sumR2 / g.n - mean ** 2, 1e-12))
        sym = a.groupby(["cid", "exit", "symbol"])["sumR"].sum().reset_index()
        br = sym.assign(pos=sym.sumR > 0).groupby(["cid", "exit"])["pos"].mean()
        r = pd.DataFrame({f"n_{p}": g.n, f"avgR_{p}": mean, f"t_{p}": mean / (sd / np.sqrt(g.n)),
                          f"wr_{p}": g.wins / g.n, f"pf_{p}": g.posR / g.negR.replace(0, np.nan),
                          f"totR_{p}": g.sumR, f"avgret_{p}": g.sumret / g.n, f"sym_pos_{p}": br, f"bars_{p}": g.bars / g.n})
        out = r if out is None else out.join(r, how="outer")
    y = agg.groupby(["cid", "exit", "year"])[["n", "sumR"]].sum()
    y = (y.sumR / y.n).where(y.n >= 20).unstack("year")
    y.columns = [f"y{c}" for c in y.columns]
    return out.join(y).reset_index().merge(cands, on="cid")


def data_tags(df, tf):
    """what the combo needs live: ohlcv < cross/macro < taker (HL needs own recorder)."""
    if not ta.DATA_TAG:
        ta.signals(ta.load("BTCUSDT", tf), tf, "BTCUSDT")
    out = []
    for r in df[["trigger", "state1", "state2"]].itertuples(index=False):
        tags = sorted({ta.DATA_TAG.get(x, "ohlcv") for x in r} - {"ohlcv"})
        out.append("+".join(tags) if tags else "ohlcv")
    return out


if __name__ == "__main__":
    tf = sys.argv[1]
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    cands, good, ntests = select(tf)
    good.to_parquet(os.path.join(ta.OUT, f"stage1_pass_{tf}.parquet"), index=False)
    print(f"{tf}: stage-1 tests {ntests}, passing {len(good)}, candidates {len(cands)}", flush=True)
    t0 = time.time(); parts = []
    with ProcessPoolExecutor(workers) as ex:
        for i, df in enumerate(ex.map(_work, [(s, tf, cands) for s in ta.universe()])):
            if df is not None:
                parts.append(df)
            print(i + 1, f"{time.time()-t0:.0f}s", flush=True)
    trades = pd.concat(parts, ignore_index=True)
    trades.to_parquet(os.path.join(ta.OUT, f"stage2_{tf}_agg.parquet"), index=False)
    summ = summarize(trades, cands)
    summ.insert(0, "tf", tf)
    summ["data"] = data_tags(summ, tf)
    summ.to_parquet(os.path.join(ta.OUT, f"stage2_{tf}_summary.parquet"), index=False)
    print("done", int(trades.n.sum()), "trades")
