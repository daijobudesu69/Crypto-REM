"""Flush: Binance signal (volume/BB on Binance perp candles) executed on HYPE 4h candles (SL/TP 2 ATR from HL candles)."""
import pandas as pd, numpy as np, os, json, warnings
from concurrent.futures import ProcessPoolExecutor
import ta, trade_sim as TS, strategy_sim as S, hl_full as H
warnings.filterwarnings("ignore")
INV = {"1000PEPEUSDT": "kPEPE", "1000SHIBUSDT": "kSHIB", "1000BONKUSDT": "kBONK", "1000FLOKIUSDT": "kFLOKI"}


def _one(args):
    sym, entries = args
    warnings.filterwarnings("ignore")
    coin = INV.get(sym, sym[:-4])
    try:
        k = ta.load(coin, "4h", "hl")
    except FileNotFoundError:
        return None
    o, h, l, c = (k[x].values.astype(float) for x in ["open", "high", "low", "close"])
    a = ta.F.atr(h, l, c, 14); ts = k["ts"].dt.tz_convert(None).values; cts = k["close_time"].dt.tz_convert(None).values
    pos = {t: i for i, t in enumerate(ts)}
    sig = np.zeros(len(c), bool)
    for e in entries:   # entry at open of bar e -> signal bar e-1
        i = pos.get(np.datetime64(e))
        if i is not None and i >= 1:
            sig[i - 1] = True
    ei, xi, ret, rr = TS.simulate(o, h, l, c, a, k["cum_funding"].values.astype(float), sig, 1, 2.0, 2.0, 0.0, 48, 0.0007)
    return pd.DataFrame({"symbol": sym, "entry_ts": ts[ei], "exit_ts": cts[xi], "ret": ret, "R": rr})


if __name__ == "__main__":
    fb = S.flush_trades(); fb = fb[pd.to_datetime(fb.entry_ts) >= "2024-07-01"]
    jobs = [(s, list(pd.to_datetime(g.entry_ts).values)) for s, g in fb.groupby("symbol")]
    with ProcessPoolExecutor(8) as ex:
        parts = [p for p in ex.map(_one, jobs) if p is not None]
    t = pd.concat(parts, ignore_index=True)
    t["stop_frac"] = (t.ret / t.R).where(t.R.abs() > 1e-9); t["stop_frac"] = t.stop_frac.fillna(t.stop_frac.median()).clip(0.005, 0.5)
    t["n_event"] = 10
    m = S.momentum_daily()
    out = dict(binance_signal_trades=int(len(fb)), executed_on_hl=int(len(t)), events=int(t.entry_ts.nunique()),
               ev_avgR_hl=round(float(t.groupby("entry_ts").R.mean().mean()), 3), ev_avgR_bn=round(float(fb.groupby("entry_ts").R.mean().mean()), 3),
               wr_hl=round(float((t.R > 0).mean()) * 100, 1))
    df = S.simulate(mom=m, fl=t, use_mom=False); df = df[df.index >= H.START]
    out["flush_only_300"] = H.window_stats(df, 300)
    json.dump(out, open(os.path.join(ta.OUT, "flush_cross.json"), "w")); print(out)
