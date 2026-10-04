"""Finalists: robust stage-2 configs, re-run trade by trade and stressed:
  * daily-clustered t-stat (all coins' R on the same day summed)  -> removes cross-coin double counting
  * random-entry baseline with the same exit (shows survivorship/drift)
  * portfolio: 1% risk of equity per trade, max 10 open, compounding (full + OOS only)
  * cross-venue check on Hyperliquid candles (free data; HYPE candles have no taker volume)

    python finalists.py   -> results/finalists.parquet, results/finalist_trades.parquet, results/baseline.parquet
"""
import os
for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(v, "1")
import sys, warnings
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
import ta
import trade_sim as TS
from stage1 import OOS_START
from stage2 import data_tags

warnings.filterwarnings("ignore")
PER_TF = 10
TFS = ("15m", "1h", "4h", "1d")


def pick(tf):
    p = os.path.join(ta.OUT, f"stage2_{tf}_summary.parquet")
    if not os.path.exists(p):
        return pd.DataFrame()
    s = pd.read_parquet(p)
    yc = [c for c in s.columns if c.startswith("y20")]
    s["yrs_pos"] = (s[yc] > 0).sum(1); s["yrs_n"] = s[yc].notna().sum(1)
    nmin = (80, 40) if tf == "1d" else (150, 100)
    ok = s[(s.n_is >= nmin[0]) & (s.n_oos >= nmin[1]) & (s.avgR_is >= 0.08) & (s.avgR_oos >= 0.08) &
           (s.pf_is >= 1.2) & (s.pf_oos >= 1.2) & (s.t_is >= 3) & (s.t_oos >= 3) &
           (s.sym_pos_oos >= 0.55) & (s.yrs_pos >= 0.75 * s.yrs_n)].copy()
    ok["score"] = np.minimum(ok.t_is, ok.t_oos) * np.minimum(ok.avgR_is, ok.avgR_oos)
    ok = ok.sort_values("score", ascending=False).drop_duplicates(["dir", "trigger"]).head(PER_TF)
    ok["tf"] = tf
    return ok


def name_of(r):
    f = [x for x in (r.state1, r.state2) if x != "none"]
    return f"{r.tf} {r.dir} {r.trigger}" + (" | " + " + ".join(f) if f else "") + f" [{r.exit}]"


def _one(args):
    sym, tf, specs, venue = args
    warnings.filterwarnings("ignore")
    try:
        k = ta.load(sym if venue == "binance" else ta.HL_MAP.get(sym, sym[:-4]), tf, venue)
    except FileNotFoundError:
        return None
    if len(k) < (200 if tf == "1d" else 300):
        return None
    T, S, aux = ta.signals(k, tf, sym)
    o, h, l, c = (k[x].values.astype(float) for x in ["open", "high", "low", "close"])
    cf = k["cum_funding"].values.astype(float)
    ts, cts = k["ts"].dt.tz_convert(None).values, k["close_time"].dt.tz_convert(None).values
    cost = TS.SIDE_COST if venue == "binance" else 0.0006
    out = []
    for sp in specs:
        d = 0 if sp["dir"] == "long" else 1
        if sp["trigger"] == "always":
            sig = np.ones(len(c), bool)
        else:
            sig = T[sp["trigger"]][d] & S[sp["state1"]][d] & S[sp["state2"]][d]
        sl, tp, tr, mb = TS.EXITS[sp["exit"]]
        ei, xi, ret, rr = TS.simulate(o, h, l, c, aux["atr"], cf, sig, 1 if d == 0 else -1, sl, tp, tr, mb, cost)
        if len(ei):
            out.append(pd.DataFrame({"name": sp["name"], "symbol": sym, "entry_ts": ts[ei], "exit_ts": cts[xi], "ret": ret, "R": rr}))
    return pd.concat(out) if out else None


def trades(tf, specs, venue="binance", workers=8):
    with ProcessPoolExecutor(workers) as ex:
        parts = [p for p in ex.map(_one, [(s, tf, specs, venue) for s in ta.universe()]) if p is not None]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["name", "symbol", "entry_ts", "exit_ts", "ret", "R"])


def portfolio(tr, risk=0.01, max_pos=10, start=None):
    tr = tr.sort_values("entry_ts")
    if start is not None:
        tr = tr[tr.entry_ts >= pd.Timestamp(start)]
    eq = 1.0; open_ = []; curve = []
    for r in tr.itertuples():
        still = []
        for x in sorted(open_):
            if x[0] <= r.entry_ts:
                eq += x[2] * x[1]; curve.append((x[0], eq))
            else:
                still.append(x)
        open_ = still
        if len(open_) >= max_pos or any(x[3] == r.symbol for x in open_):
            continue
        open_.append((r.exit_ts, r.R, eq * risk, r.symbol))
    for x in sorted(open_):
        eq += x[2] * x[1]; curve.append((x[0], eq))
    cv = pd.DataFrame(curve, columns=["ts", "equity"]).set_index("ts")["equity"]
    if cv.empty:
        return {}, cv
    yrs = max((cv.index[-1] - cv.index[0]).days / 365.25, 1e-9)
    daily = cv.resample("1D").last().ffill().pct_change().dropna()
    return {"final_x": cv.iloc[-1], "cagr": cv.iloc[-1] ** (1 / yrs) - 1, "max_dd": (cv / cv.cummax() - 1).min(),
            "sharpe": daily.mean() / daily.std() * np.sqrt(365) if daily.std() > 0 else np.nan, "taken": len(curve)}, cv


def clustered_t(tr):
    d = tr.assign(day=pd.to_datetime(tr.entry_ts).dt.floor("D")).groupby("day")["R"].sum()
    return d.mean() / (d.std() / np.sqrt(len(d))) if len(d) > 2 and d.std() > 0 else np.nan


def baseline():
    """random-entry (enter every time flat) with each exit, per TF and direction."""
    rows = []
    for tf in TFS:
        specs = [dict(name=f"{d}|{e}", dir=d, trigger="always", state1="none", state2="none", exit=e)
                 for d in ("long", "short") for e in TS.EXITS]
        tr = trades(tf, specs)
        yr = pd.to_datetime(tr.entry_ts).dt.year
        for nm, g in tr.groupby("name"):
            y = yr.loc[g.index]
            rows.append(dict(tf=tf, dir=nm.split("|")[0], exit=nm.split("|")[1], n=len(g),
                             avgR_is=g.R[y < OOS_START].mean(), avgR_oos=g.R[y >= OOS_START].mean()))
        print("baseline", tf, flush=True)
    b = pd.DataFrame(rows)
    b.to_parquet(os.path.join(ta.OUT, "baseline.parquet"), index=False)
    return b


if __name__ == "__main__":
    bp = os.path.join(ta.OUT, "baseline.parquet")
    b = pd.read_parquet(bp) if os.path.exists(bp) else baseline()
    tfs = sys.argv[1].split(",") if len(sys.argv) > 1 else TFS
    tag = sys.argv[2] if len(sys.argv) > 2 else ""
    fin = pd.concat([pick(tf) for tf in tfs], ignore_index=True)
    fin["name"] = [name_of(r) for r in fin.itertuples()]
    print(fin[["name", "data", "n_is", "avgR_is", "t_is", "n_oos", "avgR_oos", "t_oos"]].to_string(), flush=True)
    all_tr, rows = [], []
    for tf, g in fin.groupby("tf"):
        specs = g[["name", "dir", "trigger", "state1", "state2", "exit"]].to_dict("records")
        tr = trades(tf, specs); tr["tf"] = tf; all_tr.append(tr)
        hl = trades(tf, specs, venue="hl")
        for sp in specs:
            t = tr[tr.name == sp["name"]]
            yr = pd.to_datetime(t.entry_ts).dt.year
            rec = {"name": sp["name"], "t_daily_is": clustered_t(t[yr < OOS_START]), "t_daily_oos": clustered_t(t[yr >= OOS_START]),
                   "days_is": t[yr < OOS_START].entry_ts.dt.floor("D").nunique(), "days_oos": t[yr >= OOS_START].entry_ts.dt.floor("D").nunique()}
            bb = b[(b.tf == tf) & (b.dir == sp["dir"]) & (b.exit == sp["exit"])]
            rec["base_avgR_is"] = bb.avgR_is.iloc[0]; rec["base_avgR_oos"] = bb.avgR_oos.iloc[0]
            st, _ = portfolio(t); rec.update({f"pf_{k}": v for k, v in st.items()})
            st, _ = portfolio(t, start=f"{OOS_START}-01-01"); rec.update({f"oos_{k}": v for k, v in st.items()})
            h = hl[hl.name == sp["name"]]
            rec["hl_n"] = len(h); rec["hl_avgR"] = h.R.mean() if len(h) else np.nan
            rec["hl_wr"] = (h.R > 0).mean() if len(h) else np.nan
            rec["hl_t_daily"] = clustered_t(h) if len(h) > 5 else np.nan
            rows.append(rec)
            print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in rec.items()}, flush=True)
    res = fin.merge(pd.DataFrame(rows), on="name")
    res.to_parquet(os.path.join(ta.OUT, f"finalists{tag}.parquet"), index=False)
    pd.concat(all_tr).to_parquet(os.path.join(ta.OUT, f"finalist_trades{tag}.parquet"), index=False)
