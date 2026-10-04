"""Market-breadth versions of price-only signals (free data):

  1. Basket: trade a signal only when >= N coins fire it on the same bar (event = one basket).
     This is the price-only twin of CLR-1 (which needed OI). Event-level stats, IS/OOS.
  2. Breadth thrust: share of coins above their EMA50 jumps from < lo to > hi within W bars
     -> long an equal-weight basket of all coins (one return per event).

    python breadth.py   -> results/breadth_basket.parquet, results/breadth_thrust.parquet
"""
import os
for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(v, "1")
import sys, itertools, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import ta
import finalists as FN

warnings.filterwarnings("ignore")

LONG_TRIG = ["bb_revert", "rsi_30_70_rev", "rsi2_extreme", "vol_spike_reversal", "vol_climax", "vwap_2sd_revert",
             "zscore_revert", "willr_rev", "cci_rev", "stoch_rev", "pinbar", "smc_sweep_swing", "mfi_rev", "engulfing",
             "rsi_divergence", "sweep_pdh_pdl"]
SHORT_TRIG = ["donchian_20", "bb_breakout", "break_pdh_pdl", "smc_choch", "keltner_breakout", "supertrend_flip",
              "rsi_30_70_rev", "bb_revert", "vol_spike_reversal", "rsi2_extreme"]


def basket():
    out = []
    for tf, ex in (("4h", "sl2_tp2"), ("1h", "sl1.5_tp3"), ("4h", "sl1.5_tp3")):
        specs = [dict(name=f"L {t}", dir="long", trigger=t, state1="none", state2="none", exit=ex) for t in LONG_TRIG]
        specs += [dict(name=f"L {t}+volhigh", dir="long", trigger=t, state1="volume_high", state2="none", exit=ex) for t in LONG_TRIG[:6]]
        specs += [dict(name=f"S {t}", dir="short", trigger=t, state1="none", state2="none", exit=ex) for t in SHORT_TRIG]
        tr = FN.trades(tf, specs)
        tr.to_parquet(os.path.join(ta.OUT, f"breadth_trades_{tf}_{ex}.parquet"), index=False)
        for name, g in tr.groupby("name"):
            g = g.copy(); g["cl"] = g.groupby("entry_ts")["R"].transform("size")
            for thr in (1, 3, 5, 10, 15, 20, 30):
                s = g[g.cl >= thr]
                if len(s) < 30:
                    continue
                ev = s.groupby("entry_ts")["R"].mean(); yr = ev.index.year
                rec = dict(tf=tf, exit=ex, name=name, min_coins=thr, trades=len(s), events=len(ev), avgR_trade=s.R.mean(),
                           ev_avgR=ev.mean(), ev_wr=(ev > 0).mean(),
                           ev_t=ev.mean() / (ev.std() / np.sqrt(len(ev))) if len(ev) > 2 and ev.std() > 0 else np.nan,
                           n_is=int((yr < 2025).sum()), ev_is=ev[yr < 2025].mean(), n_oos=int((yr >= 2025).sum()), ev_oos=ev[yr >= 2025].mean())
                for y in range(2020, 2027):
                    rec[f"y{y}"] = ev[yr == y].mean() if (yr == y).sum() >= 2 else np.nan
                out.append(rec)
        print("basket", tf, ex, flush=True)
    df = pd.DataFrame(out)
    df.to_parquet(os.path.join(ta.OUT, "breadth_basket.parquet"), index=False)
    return df


def thrust():
    out = []
    for tf in ("1d", "4h"):
        bpd = ta.BPD[tf]
        c, _ = ta.ctx(tf)
        c = c.set_index("t")
        # equal-weight basket forward return from next open
        rows = []
        for s in ta.universe():
            fp = os.path.join(ta.DATA, "binance", "um", "klines", tf, f"{s}.parquet")
            if not os.path.exists(fp):
                continue
            k = pd.read_parquet(fp, columns=["ts", "open"])
            rows.append(pd.Series(k["open"].values, index=ta._ns(k["ts"]).dt.tz_convert(None).values, name=s))
        O = pd.concat(rows, axis=1).sort_index()
        O = O[~O.index.duplicated()]
        # bar with close time t -> next open at t
        b = c["breadth"]
        base = {}
        for H in (3, 7, 14, 30):
            fr = (O.shift(-H * bpd) / O - 1).mean(1) - 0.0014
            fr = fr[fr.index >= pd.Timestamp("2020-06-01")]
            base[H] = (fr[fr.index < pd.Timestamp("2025-01-01")].mean(), fr[fr.index >= pd.Timestamp("2025-01-01")].mean())
        for lo, hi, W, H in itertools.product((0.1, 0.2, 0.3), (0.5, 0.6, 0.7), (3, 5, 10), (3, 7, 14, 30)):
            Wb, Hb = W * bpd, H * bpd
            was_low = b.rolling(Wb, min_periods=1).min().shift(1) < lo
            sig = (b > hi) & was_low
            # de-duplicate: one event, then cool-down H days
            ev_t = []; last = None
            for t in b.index[sig.fillna(False).values]:
                if last is None or t >= last + pd.Timedelta(days=H):
                    ev_t.append(t); last = t
            rets = []
            for t in ev_t:
                if t not in O.index:
                    continue
                i = O.index.get_loc(t)
                if i + Hb >= len(O):
                    continue
                r = (O.iloc[i + Hb] / O.iloc[i] - 1).dropna()
                if len(r) >= 10:
                    rets.append((t, r.mean() - 0.0014))
            if len(rets) < 4:
                continue
            e = pd.Series(dict(rets)); yr = e.index.year
            out.append(dict(tf=tf, lo=lo, hi=hi, W=W, H=H, events=len(e), mean=e.mean(), wr=(e > 0).mean(),
                            t=e.mean() / (e.std() / np.sqrt(len(e))) if e.std() > 0 else np.nan,
                            n_is=int((yr < 2025).sum()), mean_is=e[yr < 2025].mean(), n_oos=int((yr >= 2025).sum()), mean_oos=e[yr >= 2025].mean(),
                            base_is=base[H][0], base_oos=base[H][1]))
        print("thrust", tf, flush=True)
    df = pd.DataFrame(out)
    df.to_parquet(os.path.join(ta.OUT, "breadth_thrust.parquet"), index=False)
    return df


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    th = thrust()
    print(th.sort_values("t", ascending=False).head(20).round(4).to_string())
    bk = basket()
    print(bk[(bk.min_coins >= 10) & (bk.n_is >= 10) & (bk.n_oos >= 5)].sort_values("ev_is", ascending=False).head(30).round(3).to_string())
