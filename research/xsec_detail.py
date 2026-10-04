"""Detail for the chosen cross-sectional momentum config: real turnover-based cost, yearly, DD, liquidity split.
   python xsec_detail.py"""
import os, warnings
import numpy as np, pandas as pd
import ta, xsec

warnings.filterwarnings("ignore")
SIDE = 0.0007


def run(L=14, q=0.2, regime="btc", univ="all", n_fixed=None):
    W = xsec.wide(xsec.panel())
    O, C, QV, CF = W["open"], W["close"], W["qv"], W["cf"].ffill()
    age = C.notna().cumsum(); liq_rank = QV.rolling(30, min_periods=20).mean().rank(axis=1, ascending=False)
    el = (age >= 60) & C.notna() & O.shift(-1).notna() & (age >= L + 30)
    if univ == "top50":
        el &= liq_rank <= 50
    if univ == "old":  # only coins listed before 2023 -> less exposed to "selected because it pumped in 2025-26"
        first = C.apply(lambda x: x.first_valid_index())
        el &= pd.DataFrame(np.broadcast_to((first < pd.Timestamp("2023-01-01")).values, el.shape), index=el.index, columns=el.columns)
    btc = C["BTCUSDT"]; bull = btc > pd.Series(ta.F.ema(btc.values, 50), btc.index)
    rk = (C / C.shift(L) - 1).where(el).rank(axis=1, pct=True)
    top = (rk >= 1 - q)
    if n_fixed:  # fixed number of coins instead of a quantile
        top = (C / C.shift(L) - 1).where(el).rank(axis=1, ascending=False, method="first") <= n_fixed
    if regime == "btc":
        top &= bull.values[:, None]
    w = top.div(top.sum(1).replace(0, np.nan), axis=0).fillna(0)
    r = (O.shift(-2) / O.shift(-1) - 1).fillna(0)   # open t+1 -> open t+2
    f = (CF.shift(-1) - CF).fillna(0)
    gross = (w * (r - f)).sum(1)
    turn = (w - w.shift(1).fillna(0)).abs().sum(1)
    net = gross - turn * SIDE
    net = net[net.index < C.index[-3]]
    eq = (1 + net).cumprod()
    yr = net.groupby(net.index.year)
    out = pd.DataFrame({"return": yr.apply(lambda x: (1 + x).prod() - 1), "maxdd": yr.apply(lambda x: ((1 + x).cumprod() / (1 + x).cumprod().cummax() - 1).min()),
                        "days_in_market": yr.apply(lambda x: (x != 0).sum())})
    ew = (el.astype(float).div(el.sum(1).replace(0, np.nan), axis=0).fillna(0) * (r - f)).sum(1)
    ew = ew[ew.index < C.index[-3]]
    out["equal_weight_all"] = ew.groupby(ew.index.year).apply(lambda x: (1 + x).prod() - 1)
    stats = dict(avg_turnover_per_day=turn.loc[net.index][net != 0].mean(), avg_coins=top.sum(1)[top.sum(1) > 0].mean(),
                 cagr=eq.iloc[-1] ** (365 / len(net)) - 1, maxdd=(eq / eq.cummax() - 1).min(),
                 sharpe=net.mean() / net.std() * np.sqrt(365),
                 cagr_oos=(1 + net[net.index >= "2025"]).prod() ** (365 / (net.index >= "2025").sum()) - 1)
    return out, stats, net


if __name__ == "__main__":
    for args in [dict(), dict(univ="top50"), dict(univ="old"), dict(univ="old", regime="none"), dict(L=7, q=0.1, regime="none"), dict(L=3, q=0.1, regime="btc")]:
        out, st, net = run(**args)
        print(args, {k: round(v, 3) for k, v in st.items()})
        print(out.round(3).to_string())
        net.to_frame("ret").to_parquet(os.path.join(ta.OUT, f"xsec_detail_{'_'.join(f'{k}{v}' for k, v in args.items()) or 'base'}.parquet"))
