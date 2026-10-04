"""Cross-venue check of cross-sectional momentum (long-only) on Hyperliquid daily candles + HL funding cost.
Excess = strategy minus equal-weight basket of all eligible HL coins.   python xsec_hl.py"""
import os, warnings
import numpy as np, pandas as pd
import ta

warnings.filterwarnings("ignore")


def run():
    uni = pd.read_csv(os.path.join(ta.DATA, "universe", "hyperliquid_top150.csv"))
    col = [c for c in uni.columns if c.lower() in ("coin", "name", "symbol")][0]
    O, C, CF = {}, {}, {}
    for s in uni[col]:
        try:
            k = ta.load(s, "1d", "hl")
        except FileNotFoundError:
            continue
        t = k["ts"].dt.tz_convert(None).values
        O[s] = pd.Series(k.open.values, t); C[s] = pd.Series(k.close.values, t); CF[s] = pd.Series(k.cum_funding.values, t)
    O, C, CF = pd.DataFrame(O).sort_index(), pd.DataFrame(C).sort_index(), pd.DataFrame(CF).sort_index().ffill()
    age = C.notna().cumsum(); el = (age >= 60) & C.notna() & O.shift(-1).notna()
    btc = C["BTC"]; bull = btc > pd.Series(ta.F.ema(btc.values, 50), btc.index)
    tt = lambda x: x.mean() / (x.std() / np.sqrt(len(x))) if len(x) > 2 else np.nan
    rows = []
    for L in (3, 7, 14):
        for H in (1, 7):
            for q in (0.1, 0.2):
                for reg in ("none", "btc"):
                    r = O.shift(-(1 + H)) / O.shift(-1) - 1; f = CF.shift(-H) - CF
                    rk = (C / C.shift(L) - 1).where(el & (age >= L + 30)).rank(axis=1, pct=True)
                    top = rk >= 1 - q
                    if reg == "btc":
                        top = top & bull.values[:, None]
                    reb = C.index[::H]
                    p = ((r - f).where(top)).mean(1).loc[reb] - 0.0014
                    bb = (r - f).where(el).mean(1).loc[reb] - 0.0014
                    ex = (p - bb).dropna(); p = p.dropna()
                    p = p[p.index < C.index[-H - 2]]; ex = ex[ex.index < C.index[-H - 2]]
                    e25 = ex[ex.index >= "2025"]
                    rows.append(dict(L=L, H=H, q=q, regime=reg, n=len(p), mean=p.mean(), t=tt(p), excess=ex.mean(), t_excess=tt(ex),
                                     excess_2025=e25.mean(), t_excess_2025=tt(e25)))
    df = pd.DataFrame(rows)
    df.to_parquet(os.path.join(ta.OUT, "xsec_hl.parquet"), index=False)
    return df


if __name__ == "__main__":
    print(run().round(4).to_string())
