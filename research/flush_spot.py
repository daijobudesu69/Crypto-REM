"""Flush signal from Binance SPOT 4h candles (reachable from the user's home network via data-api.binance.vision),
executed on HYPE 4h candles. Plus the 200 USD HYPE account simulation.   python flush_spot.py -> results/flush_spot.json"""
import os, json, warnings
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
import ta, small_capital as SC, hl_full as H
import trade_sim as TS

warnings.filterwarnings("ignore")
SPOT = os.path.join(ta.DATA, "binance", "spot", "klines", "4h")
K = {"PEPE": "kPEPE", "SHIB": "kSHIB", "BONK": "kBONK", "FLOKI": "kFLOKI"}


def _spot_sig(fn):
    warnings.filterwarnings("ignore")
    k = pd.read_parquet(os.path.join(SPOT, fn))
    if "n_bars" in k:
        k = k[(k.n_bars >= 4) | (k.index == k.index[-1])].reset_index(drop=True)  # spot 4h built from 1h bars
    c, v = k.close.values.astype(float), k.volume.values.astype(float)
    bbl = ta.F.sma(c, 20) - 2 * pd.Series(c).rolling(20).std().values
    sig = ta.F.cross_up(c, bbl) & (v > 1.5 * ta.F.sma(v, 20))
    t = ta._ns(k.ts).dt.tz_convert(None).values
    base = fn.replace("USDT.parquet", "")
    return pd.DataFrame({"coin": K.get(base, base), "bar": t[sig]})


def _exec(args):
    coin, bars = args
    warnings.filterwarnings("ignore")
    try:
        k = ta.load(coin, "4h", "hl")
    except FileNotFoundError:
        return None
    o, h, l, c = (k[x].values.astype(float) for x in ["open", "high", "low", "close"])
    a = ta.F.atr(h, l, c, 14); ts = k["ts"].dt.tz_convert(None).values; cts = k["close_time"].dt.tz_convert(None).values
    pos = {t: i for i, t in enumerate(ts)}
    sig = np.zeros(len(c), bool)
    for b in bars:
        i = pos.get(np.datetime64(b))
        if i is not None:
            sig[i] = True          # spot signal bar == HL bar with same open time -> entry next HL open
    ei, xi, ret, rr = TS.simulate(o, h, l, c, a, k["cum_funding"].values.astype(float), sig, 1, 2.0, 2.0, 0.0, 48, 0.0007)
    return pd.DataFrame({"symbol": coin, "entry_ts": ts[ei], "exit_ts": cts[xi], "ret": ret, "R": rr})


def spot_flush(min_coins=10, max_coins=15, start="2024-07-01", seed=1):
    with ProcessPoolExecutor(8) as ex:
        sigs = pd.concat([s for s in ex.map(_spot_sig, sorted(os.listdir(SPOT)))], ignore_index=True)
    cnt = sigs.groupby("bar").size()
    ev_bars = set(cnt[cnt >= min_coins].index)
    sigs = sigs[sigs.bar.isin(ev_bars) & (sigs.bar >= pd.Timestamp(start) - pd.Timedelta("4h"))]
    jobs = [(c, list(g.bar.values)) for c, g in sigs.groupby("coin")]
    with ProcessPoolExecutor(8) as ex:
        t = pd.concat([p for p in ex.map(_exec, jobs) if p is not None], ignore_index=True)
    t = t[pd.to_datetime(t.entry_ts) >= start]
    t["stop_frac"] = (t.ret / t.R).where(t.R.abs() > 1e-9); t["stop_frac"] = t.stop_frac.fillna(t.stop_frac.median()).clip(0.005, 0.5)
    t["rnd"] = np.random.default_rng(seed).random(len(t)); t = t[t.groupby("entry_ts")["rnd"].rank() <= max_coins]
    return t, cnt


if __name__ == "__main__":
    out = {}
    t, cnt = spot_flush()
    ev = t.groupby("entry_ts").R.mean()
    out["spot_flush"] = dict(events=int(len(ev)), trades=int(len(t)), ev_avgR=round(float(ev.mean()), 3), ev_wr=round(float((ev > 0).mean()) * 100, 1),
                             trade_wr=round(float((t.R > 0).mean()) * 100, 1),
                             ev_t=round(float(ev.mean() / (ev.std() / np.sqrt(len(ev)))), 2))
    for thr in (8, 12, 15):
        tt, _ = spot_flush(min_coins=thr); e2 = tt.groupby("entry_ts").R.mean()
        out.setdefault("thr", []).append(dict(min_coins=thr, events=int(len(e2)), ev_avgR=round(float(e2.mean()), 3)))
    print(out, flush=True)
    m10 = H.momentum_hl(10, 15)
    SC.MIN = 10
    for name, kw in (("200: 10 koin x 10$ + flush spot (tolak>2x, gross<=2x)", dict(reject_x=2, gross_cap=2)),
                     ("200: 10 koin x 10$, tanpa flush", dict(use_flush=False)),
                     ("200: flush spot saja (tolak>2x)", dict(use_mom=False, reject_x=2))):
        for sd in ("2024-07-01", "2025-01-01"):
            df, ex_ = SC.simulate(200, m10, 10, 0.5, t, start_date=sd, **kw)
            r = dict(variant=name, start=sd[:7], **SC.st(df, 200), event_risk_max=round(ex_["event_risk_max"] * 100), skipped=ex_["flush_skipped"])
            out.setdefault("sim200", []).append(r); print(r, flush=True)
            if sd == "2024-07-01" and "flush spot (tolak" in name:
                y = df.equity.resample("YE").last(); y0 = pd.concat([pd.Series([200.0], [pd.Timestamp("2024-06-30")]), y])
                out["yearly_main"] = {str(k.year): round(float(v) * 100, 1) for k, v in y0.pct_change().dropna().items()}
                mo = df.equity.resample("ME").last(); mo = pd.concat([pd.Series([200.0], [pd.Timestamp("2024-06-30")]), mo]).pct_change().dropna()
                out["monthly_main"] = {f"{k.year}-{k.month:02d}": round(float(v) * 100, 1) for k, v in mo.items()}
    json.dump(out, open(os.path.join(ta.OUT, "flush_spot.json"), "w"))
