"""Full RMF account simulation on Hyperliquid candles + HYPE funding (momentum 1d + flush 4h), 2024-07 -> 2026-10,
compared with the Binance simulation over the same window.   python hl_full.py -> results/hl_full.json"""
import os, json, warnings
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
import ta, strategy_sim as S, small_capital as SC
import trade_sim as TS

warnings.filterwarnings("ignore")
START = "2024-07-01"


def hl_universe():
    u = pd.read_csv(os.path.join(ta.DATA, "universe", "hyperliquid_top150.csv"))
    return list(u[u.isDelisted != True]["name"])


def momentum_hl(N=10, exit_rank=15, L=14):
    O, C, CF = {}, {}, {}
    for s in hl_universe():
        try:
            k = ta.load(s, "1d", "hl")
        except FileNotFoundError:
            continue
        t = k["ts"].dt.tz_convert(None).values
        O[s] = pd.Series(k.open.values, t); C[s] = pd.Series(k.close.values, t); CF[s] = pd.Series(k.cum_funding.values, t)
    O, C, CF = pd.DataFrame(O).sort_index(), pd.DataFrame(C).sort_index(), pd.DataFrame(CF).sort_index().ffill()
    age = C.notna().cumsum()
    el = (age >= 60) & C.notna() & O.shift(-1).notna() & (age >= L + 30)
    btc = C["BTC"]; bull = (btc > pd.Series(ta.F.ema(btc.values, 50), btc.index)).values
    rank = (C / C.shift(L) - 1).where(el).rank(axis=1, ascending=False, method="first").values
    hold = np.zeros(rank.shape, bool); cur = np.zeros(rank.shape[1], bool)
    for i in range(len(rank)):
        if not bull[i]:
            cur[:] = False
        else:
            rk = rank[i]; cur = cur & (rk <= exit_rank)
            free = N - cur.sum()
            if free > 0:
                cand = np.where((~cur) & (rk <= N))[0]; cand = cand[np.argsort(rk[cand])][:free]; cur[cand] = True
        hold[i] = cur
    top = pd.DataFrame(hold, index=C.index, columns=C.columns)
    w = top.div(top.sum(1).replace(0, np.nan), axis=0).fillna(0)
    r = (O.shift(-2) / O.shift(-1) - 1).fillna(0); f = (CF.shift(-1) - CF).fillna(0)
    turn = (w - w.shift(1).fillna(0)).abs().sum(1)
    net = (w * (r - f)).sum(1) - turn * 0.0007
    return net[net.index < C.index[-3]]


def _flush_one(coin):
    warnings.filterwarnings("ignore")
    try:
        k = ta.load(coin, "4h", "hl")
    except FileNotFoundError:
        return None
    if len(k) < 300:
        return None
    o, h, l, c, v = (k[x].values.astype(float) for x in ["open", "high", "low", "close", "volume"])
    mid, sd = ta.F.sma(c, 20), pd.Series(c).rolling(20).std().values
    bbl = mid - 2 * sd
    sig = ta.F.cross_up(c, bbl) & (v > 1.5 * ta.F.sma(v, 20))
    a = ta.F.atr(h, l, c, 14)
    ei, xi, ret, rr = TS.simulate(o, h, l, c, a, k["cum_funding"].values.astype(float), sig, 1, 2.0, 2.0, 0.0, 48, 0.0007)
    ts, cts = k["ts"].dt.tz_convert(None).values, k["close_time"].dt.tz_convert(None).values
    # all signal bars (for event counting) incl. ones skipped because a trade was open
    return (pd.DataFrame({"symbol": coin, "entry_ts": ts[ei], "exit_ts": cts[xi], "ret": ret, "R": rr}),
            pd.DataFrame({"symbol": coin, "bar": ts[np.where(sig)[0]]}))


def flush_hl(min_coins=10, max_coins=15, seed=1):
    with ProcessPoolExecutor(8) as ex:
        parts = [p for p in ex.map(_flush_one, hl_universe()) if p is not None]
    tr = pd.concat([p[0] for p in parts], ignore_index=True)
    tr["n_event"] = tr.groupby("entry_ts")["R"].transform("size")
    tr = tr[tr.n_event >= min_coins].copy()
    tr["stop_frac"] = (tr.ret / tr.R).where(tr.R.abs() > 1e-9); tr["stop_frac"] = tr.stop_frac.fillna(tr.stop_frac.median()).clip(0.005, 0.5)
    tr["rnd"] = np.random.default_rng(seed).random(len(tr))
    tr = tr[tr.groupby("entry_ts")["rnd"].rank() <= max_coins]
    return tr.sort_values("entry_ts")


def window_stats(df, start_cap):
    e = df.equity; e = e / e.iloc[0] * start_cap
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    mo = e.resample("ME").last().pct_change().dropna()
    return dict(final=round(float(e.iloc[-1]), 1), cagr=round(float((e.iloc[-1] / start_cap) ** (1 / yrs) - 1) * 100, 1),
                maxdd=round(float((e / e.cummax() - 1).min()) * 100, 1), worst_month=round(float(mo.min()) * 100, 1))


if __name__ == "__main__":
    out = {}
    mh = momentum_hl(); fh = flush_hl()
    fh = fh[pd.to_datetime(fh.entry_ts) >= START]
    mb = S.momentum_daily(); fb = S.flush_trades(); fb = fb[pd.to_datetime(fb.entry_ts) >= START]
    out["events"] = dict(hl=int(fh.entry_ts.nunique()), binance=int(fb.entry_ts.nunique()),
                         hl_ev_avgR=round(float(fh.groupby("entry_ts").R.mean().mean()), 3), bn_ev_avgR=round(float(fb.groupby("entry_ts").R.mean().mean()), 3),
                         hl_trade_wr=round(float((fh.R > 0).mean()) * 100, 1), bn_trade_wr=round(float((fb.R > 0).mean()) * 100, 1))
    for venue, (m, f) in {"HYPE": (mh, fh), "Binance": (mb, fb)}.items():
        for name, kw in {"RMF (0,5x + flush)": dict(f_mom=0.5), "Momentum saja 0,5x": dict(f_mom=0.5, use_flush=False), "Flush saja": dict(use_mom=False)}.items():
            df = S.simulate(mom=m[m.index >= "2024-06-29"], fl=f, **kw)
            df = df[df.index >= START]
            out.setdefault("sims", []).append(dict(venue=venue, variant=name, **window_stats(df, 300)))
        for nm, kw in {"100$ 5 koin + flush (tolak>2x, gross<=2x)": None}.items():
            pass
    # monthly correlation of momentum daily returns HYPE vs Binance
    j = pd.concat([mh, mb], axis=1, keys=["hl", "bn"]).dropna(); j = j[j.index >= START]
    out["mom_corr_daily"] = round(float(j.corr().iloc[0, 1]), 3)
    out["mom_active_days"] = dict(hl=round(float((mh[mh.index >= START] != 0).mean()) * 100), bn=round(float((mb[mb.index >= START] != 0).mean()) * 100))
    json.dump(out, open(os.path.join(ta.OUT, "hl_full.json"), "w"))
    print(json.dumps(out, indent=1))
