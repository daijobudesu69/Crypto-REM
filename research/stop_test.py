"""Momentum (10 coins, buffer exit > 15, BTC > EMA50) + a price stop from the entry price.

Same rules and accounting as buffer_test.run (equal weight of held coins, open->open returns, 0.07%/side on
weight turnover, real funding as cost). Added: each position remembers its entry price (open of the entry day).
If the daily LOW of any held day reaches entry x (1 - stop), the position is sold at that price (or at the open
if the day already opens below it), minus STOP_SLIP extra slippage. The slot is cash for the rest of that day.

  reentry=True   the coin may be bought again at the next open if it is still rank <= 10 (what the bot does now)
  reentry=False  after a stop the coin is blocked until its rank goes > exit_rank (or the BTC filter turns off)

    python stop_test.py   -> results/stop_test.json
"""
import os, json, warnings
import numpy as np, pandas as pd
import ta, xsec

warnings.filterwarnings("ignore")
SIDE = 0.0007
STOP_SLIP = 0.002      # extra slippage on stop fills (stop-market in a fast move)
F_MOM = 0.5            # account notional = 0.5x equity (final setting)
START = "2022-01-01"


def frames(venue):
    if venue == "binance":
        syms = xsec.panel()["sym"].unique()
        btc_sym = "BTCUSDT"
    else:
        u = pd.read_csv(os.path.join(ta.DATA, "universe", "hyperliquid_top150.csv"))
        syms = list(u[u.isDelisted != True]["name"]); btc_sym = "BTC"
    D = {c: {} for c in ("open", "high", "low", "close", "cf")}
    for s in syms:
        try:
            k = ta.load(s, "1d", "binance" if venue == "binance" else "hl")
        except FileNotFoundError:
            continue
        t = k["ts"].dt.tz_convert(None).values
        D["open"][s] = pd.Series(k.open.values, t); D["high"][s] = pd.Series(k.high.values, t)
        D["low"][s] = pd.Series(k.low.values, t); D["close"][s] = pd.Series(k.close.values, t)
        D["cf"][s] = pd.Series(k.cum_funding.values, t)
    W = {c: pd.DataFrame(v).sort_index() for c, v in D.items()}
    W["cf"] = W["cf"].ffill()
    return W, btc_sym


def run(W, btc_sym, stop=None, reentry=True, N=10, exit_rank=15, L=14):
    O, Lo, C, CF = W["open"], W["low"], W["close"], W["cf"]
    age = C.notna().cumsum()
    el = (age >= 60) & C.notna() & O.shift(-1).notna() & (age >= L + 30)
    btc = C[btc_sym]; bull = (btc > pd.Series(ta.F.ema(btc.values, 50), btc.index)).values
    rank = (C / C.shift(L) - 1).where(el).rank(axis=1, ascending=False, method="first").values
    o1 = O.shift(-1).values; o2 = O.shift(-2).values; lo1 = Lo.shift(-1).values   # bar t+1 = the day we hold
    fund = (CF.shift(-1) - CF).fillna(0).values
    T, K = rank.shape
    cur = np.zeros(K, bool); blocked = np.zeros(K, bool); entry = np.full(K, np.nan)
    prev_w = np.zeros(K)
    net = np.zeros(T); n_stop = np.zeros(T, int); n_entry = np.zeros(T, int)
    for i in range(T):
        rk = rank[i]
        if not bull[i]:
            cur[:] = False; blocked[:] = False
        else:
            blocked &= ~(rk > exit_rank) & ~np.isnan(rk)   # unblock once it leaves the buffer
            cur = cur & (rk <= exit_rank)
            free = N - cur.sum()
            if free > 0:
                cand = np.where((~cur) & (rk <= N) & ~blocked)[0]
                cand = cand[np.argsort(rk[cand])][:free]
                cur[cand] = True; entry[cand] = o1[i, cand]; n_entry[i] = len(cand)
        n = cur.sum()
        w = np.where(cur, 1.0 / n, 0.0) if n else np.zeros(K)
        ret = np.where(cur, o2[i] / o1[i] - 1, 0.0)
        ret = np.nan_to_num(ret)
        post_w = w.copy()
        stop_cost = 0.0
        if stop is not None and n:
            sp = entry * (1 - stop)
            hit = cur & (lo1[i] <= sp)
            if hit.any():
                px = np.minimum(sp, o1[i]) * (1 - STOP_SLIP)
                ret[hit] = px[hit] / o1[i, hit] - 1
                stop_cost = (w[hit] * SIDE).sum()
                post_w[hit] = 0.0
                cur[hit] = False; n_stop[i] = hit.sum()
                if not reentry:
                    blocked[hit] = True
        turn = np.abs(w - prev_w).sum()
        net[i] = (w * (ret - fund[i])).sum() - turn * SIDE - stop_cost
        prev_w = post_w
    idx = C.index
    keep = idx < idx[-3]
    return (pd.Series(net[keep], idx[keep]), pd.Series(n_stop[keep], idx[keep]), pd.Series(n_entry[keep], idx[keep]))


def stats(net, start=START, f=F_MOM):
    m = net[net.index >= pd.Timestamp(start) - pd.Timedelta(days=1)]
    r = (f * m).shift(1).dropna()        # P&L of signal day t lands on day t+1
    r = r[r.index >= start]
    e = (1 + r).cumprod()
    dd = e / e.cummax() - 1
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    mo = e.resample("ME").last().pct_change().dropna()
    yr = e.resample("YE").last() / e.resample("YE").last().shift(1).fillna(1) - 1
    return dict(final_200=200 * e.iloc[-1], cagr=e.iloc[-1] ** (1 / yrs) - 1, maxdd=dd.min(),
                sharpe=r.mean() / r.std() * np.sqrt(365), worst_day=r.min(), worst_month=mo.min(),
                pos_months=(mo > 0).mean(), years={str(k.year): v for k, v in yr.items()})


if __name__ == "__main__":
    import buffer_test
    out = {}
    for venue, start in (("binance", START), ("hl", "2024-07-01")):
        W, b = frames(venue)
        if venue == "binance":   # sanity: no-stop run must equal the research function
            ref, _, _ = buffer_test.run(10, 15)
            mine, _, _ = run(W, b, None)
            j = ref.index.intersection(mine.index)
            print("check vs buffer_test: max abs diff", float((ref[j] - mine[j]).abs().max()))
        for stop in (None, 0.10, 0.15, 0.20, 0.25):
            for re_ in ((True, False) if stop else (True,)):
                net, ns, ne = run(W, b, stop, re_)
                s = stats(net, start)
                sel = ns.index >= start
                s["stops"] = int(ns[sel].sum()); s["entries"] = int(ne[sel].sum())
                key = f"{venue} {'none' if stop is None else int(stop*100)} {'re' if re_ else 'block'}"
                out[key] = s
                print(f"{key:22s} 200->{s['final_200']:9.0f} cagr {s['cagr']*100:6.1f}% dd {s['maxdd']*100:6.1f}% "
                      f"sharpe {s['sharpe']:.2f} wd {s['worst_day']*100:5.1f}% wm {s['worst_month']*100:5.1f}% "
                      f"stops {s['stops']:4d}/{s['entries']:4d} | " + " ".join(f"{k}:{v*100:+.0f}" for k, v in s['years'].items()))
    json.dump(out, open(os.path.join(ta.OUT, "stop_test.json"), "w"), indent=1, default=float)
