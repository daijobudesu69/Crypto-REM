"""Portfolio-level edges from free candle data only (one return per rebalance -> no cross-coin
double counting):

  A. Cross-sectional momentum / reversal: rank coins by past L-day return, hold top/bottom quantile H days.
  B. Time-series trend (MA): hold every coin whose daily close > EMA(N) (long) / < EMA(N) (short).
  Baseline: equal-weight buy & hold of all coins (shows the survivorship-bias drift).

Execution: signal at daily close t, trade at open t+1, hold H days, rebalance every H days.
Cost: 0.14% round trip on every rebalance (assumes 100% turnover = conservative) + real funding (cost only).
IS 2020-2024 is used for ranking, OOS 2025-2026 is reported.

    python xsec.py   -> results/xsec_grid.parquet, results/xsec_best_daily.parquet
"""
import os, sys, itertools, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import ta

warnings.filterwarnings("ignore")
COST = 0.0014
OOS = pd.Timestamp("2025-01-01")


def panel():
    p = os.path.join(ta.OUT, "panel_1d.parquet")
    if os.path.exists(p):
        return pd.read_parquet(p)
    rows = []
    for s in ta.universe():
        try:
            k = ta.load(s, "1d")
        except FileNotFoundError:
            continue
        rows.append(pd.DataFrame({"t": k["ts"].dt.tz_convert(None).values, "sym": s, "open": k["open"].values,
                                  "close": k["close"].values, "qv": k["quote_volume"].values, "cf": k["cum_funding"].values}))
    df = pd.concat(rows, ignore_index=True)
    df.to_parquet(p, index=False)
    return df


def wide(df):
    W = {c: df.pivot(index="t", columns="sym", values=c).sort_index() for c in ("open", "close", "qv", "cf")}
    return W


def run():
    W = wide(panel())
    O, C, QV, CF = W["open"], W["close"], W["qv"], W["cf"].ffill()
    dates = C.index
    age = C.notna().cumsum()
    liq = QV.rolling(30, min_periods=20).mean()
    liq_rank = liq.rank(axis=1, ascending=False)
    btc = C["BTCUSDT"]; btc_e = pd.Series(ta.F.ema(btc.values, 50), index=dates)
    bull = (btc > btc_e)
    res, daily = [], {}

    def fwd(H):
        # return from open t+1 to open t+1+H, and funding paid over the same window (approx close t -> close t+H)
        r = O.shift(-(1 + H)) / O.shift(-1) - 1
        f = CF.shift(-H) - CF
        return r, f

    FW = {H: fwd(H) for H in (1, 3, 7, 14)}
    eligible_base = (age >= 60) & C.notna() & O.shift(-1).notna()

    def evaluate(name, wl, ws, H, params):
        """wl/ws: boolean frames of long / short members at each date (only rows on rebalance dates used)."""
        r, f = FW[H]
        reb = dates[::H]
        L = wl.loc[reb]; S_ = ws.loc[reb]
        rl = ((r - f).where(L)).loc[reb].mean(1)       # long leg: pay funding when positive
        rs = ((-r + f).where(S_)).loc[reb].mean(1)     # short leg: receive funding when positive
        nl, ns = L.sum(1), S_.sum(1)
        legs = []
        if wl.values.any():
            legs.append(rl.where(nl > 0, 0.0) - COST * (nl > 0))
        if ws.values.any():
            legs.append(rs.where(ns > 0, 0.0) - COST * (ns > 0))
        port = sum(legs) / len(legs)
        port = port.dropna()
        port = port[port.index < dates[-(H + 2)]]
        rec = dict(strategy=name, H=H, **params)
        for p, m in (("is", port.index < OOS), ("oos", port.index >= OOS)):
            x = port[m]
            x = x[x != 0] if len(x) else x
            per_year = 365 / H
            rec[f"n_{p}"] = len(x)
            rec[f"mean_{p}"] = x.mean()
            rec[f"t_{p}"] = x.mean() / (x.std() / np.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else np.nan
            rec[f"sharpe_{p}"] = x.mean() / x.std() * np.sqrt(per_year) if len(x) > 2 and x.std() > 0 else np.nan
            eq = (1 + x).cumprod()
            rec[f"cagr_{p}"] = eq.iloc[-1] ** (per_year / max(len(port[m]), 1)) - 1 if len(x) else np.nan
            rec[f"maxdd_{p}"] = (eq / eq.cummax() - 1).min() if len(x) else np.nan
        yr = port[port != 0].groupby(port[port != 0].index.year).mean()
        for y, v in yr.items():
            rec[f"y{y}"] = v
        res.append(rec)
        return port

    # ---- baseline: equal-weight buy & hold (rebalanced) of all eligible coins
    for H in (1, 7):
        daily[f"baseline_long_H{H}"] = evaluate("baseline_buyhold", eligible_base, eligible_base & False, H,
                                                dict(L=0, q=0, side="long", regime="none", univ="all"))
    # ---- A. cross-sectional momentum / reversal
    for L_, H, q, univ, regime in itertools.product((1, 3, 7, 14, 30, 60), (1, 3, 7, 14), (0.1, 0.2), ("all", "top50"), ("none", "btc")):
        el = eligible_base & (age >= L_ + 30)
        if univ == "top50":
            el = el & (liq_rank <= 50)
        past = (C / C.shift(L_) - 1).where(el)
        rk = past.rank(axis=1, pct=True)
        top, bot = rk >= 1 - q, rk <= q
        bl = bull.values[:, None] if regime == "btc" else True
        br_ = (~bull).values[:, None] if regime == "btc" else True
        z = top & False
        for side, wl, ws in (("mom_long", top & bl, z), ("mom_short", z, bot & br_), ("mom_ls", top & bl, bot & br_),
                             ("rev_long", bot & bl, z), ("rev_short", z, top & br_), ("rev_ls", bot & bl, top & br_)):
            p = evaluate("xsec", wl, ws, H, dict(L=L_, q=q, side=side, regime=regime, univ=univ))
            daily[f"xsec_{side}_L{L_}_H{H}_q{q}_{univ}_{regime}"] = p
    # ---- B. time-series trend (MA filter per coin)
    for N, H, univ, regime in itertools.product((10, 20, 50, 100, 200), (1, 3, 7), ("all", "top50"), ("none", "btc")):
        el = eligible_base & (age >= N)
        if univ == "top50":
            el = el & (liq_rank <= 50)
        e = C.apply(lambda s: pd.Series(ta.F.ema(s.values, N), index=s.index) if s.notna().sum() > N else s * np.nan)
        up, dn = (C > e) & el, (C < e) & el
        bl = bull.values[:, None] if regime == "btc" else True
        br_ = (~bull).values[:, None] if regime == "btc" else True
        z = up & False
        for side, wl, ws in (("trend_long", up & bl, z), ("trend_short", z, dn & br_), ("trend_ls", up & bl, dn & br_)):
            p = evaluate("ts_trend", wl, ws, H, dict(L=N, q=0, side=side, regime=regime, univ=univ))
            daily[f"trend_{side}_N{N}_H{H}_{univ}_{regime}"] = p
    out = pd.DataFrame(res)
    out.to_parquet(os.path.join(ta.OUT, "xsec_grid.parquet"), index=False)
    pd.DataFrame(daily).to_parquet(os.path.join(ta.OUT, "xsec_returns.parquet"))
    return out


if __name__ == "__main__":
    out = run()
    pd.set_option("display.width", 250)
    cols = ["strategy", "side", "L", "H", "q", "univ", "regime", "n_is", "mean_is", "t_is", "sharpe_is", "n_oos", "mean_oos", "t_oos", "sharpe_oos", "maxdd_oos"]
    print(out[out.strategy == "baseline_buyhold"][cols].round(4).to_string())
    ok = out[(out.t_is > 2) & (out.t_oos > 1.5) & (out.mean_oos > 0)].sort_values("t_is", ascending=False)
    print(len(out), "configs;", len(ok), "with IS t>2 & OOS t>1.5")
    print(ok[cols].head(40).round(4).to_string())
