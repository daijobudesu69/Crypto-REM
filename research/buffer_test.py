"""Momentum with a hold buffer: enter when rank <= N, keep until rank > exit_rank (or BTC filter off). python buffer_test.py"""
import numpy as np, pandas as pd, warnings
import ta, xsec, strategy_sim as S
warnings.filterwarnings("ignore")
SIDE = 0.0007


def run(N=10, exit_rank=20, L=14):
    W = xsec.wide(xsec.panel())
    O, C, CF = W["open"], W["close"], W["cf"].ffill()
    age = C.notna().cumsum()
    el = (age >= 60) & C.notna() & O.shift(-1).notna() & (age >= L + 30)
    btc = C["BTCUSDT"]; bull = (btc > pd.Series(ta.F.ema(btc.values, 50), btc.index)).values
    rank = (C / C.shift(L) - 1).where(el).rank(axis=1, ascending=False, method="first").values
    hold = np.zeros(rank.shape, bool); cur = np.zeros(rank.shape[1], bool)
    for i in range(len(rank)):
        if not bull[i]:
            cur[:] = False
        else:
            rk = rank[i]
            cur = cur & (rk <= exit_rank)           # keep while still inside the buffer (NaN rank -> drop)
            free = N - cur.sum()
            if free > 0:
                cand = np.where((~cur) & (rk <= N))[0]
                cand = cand[np.argsort(rk[cand])][:free]
                cur[cand] = True
        hold[i] = cur
    top = pd.DataFrame(hold, index=C.index, columns=C.columns)
    w = top.div(top.sum(1).replace(0, np.nan), axis=0).fillna(0)
    r = (O.shift(-2) / O.shift(-1) - 1).fillna(0); f = (CF.shift(-1) - CF).fillna(0)
    turn = (w - w.shift(1).fillna(0)).abs().sum(1)
    net = (w * (r - f)).sum(1) - turn * SIDE
    net = net[net.index < C.index[-3]]
    entries = (top & ~top.shift(1, fill_value=False)).sum(1)
    return net, top, entries


if __name__ == "__main__":
    fl = S.flush_trades()
    for ex in (10, 15, 20, 30):
        net, top, ent = run(10, ex)
        d = S.simulate(f_mom=0.5, mom=net, fl=fl); s = S.stats(d)
        d2 = S.simulate(f_mom=0.5, mom=net[net.index >= "2024-12-30"], fl=fl[pd.to_datetime(fl.entry_ts) >= "2025-01-01"]); d2 = d2[d2.index >= "2025-01-01"]
        o = S.stats(d2.assign(equity=d2.equity / d2.equity.iloc[0] * 300))
        epm = ent.groupby(ent.index.to_period("M")).sum()
        print(f"exit_rank {ex:2d}: entries/month {epm.mean():5.1f} (2024-26 {epm[epm.index >= pd.Period('2024-01')].mean():5.1f}) | final {s['final']:7.0f} cagr {s['cagr']*100:4.0f}% dd {s['maxdd']*100:4.0f}% sharpe {s['sharpe']:.2f} wm {s['worst_month']*100:5.1f}% | OOS cagr {o['cagr']*100:4.0f}% dd {o['maxdd']*100:4.0f}%")
