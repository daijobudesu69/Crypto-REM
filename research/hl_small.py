"""$100 / $300 on HYPE prices: momentum ranked on HYPE candles, flush = Binance signal executed on HYPE candles. With 10$ order floor."""
import pandas as pd, numpy as np, json, os, warnings
import ta, hl_full as H, small_capital as SC, strategy_sim as S
warnings.filterwarnings("ignore")

if __name__ == "__main__":
    import flush_cross as FC
    from concurrent.futures import ProcessPoolExecutor
    fb = S.flush_trades(); fb = fb[pd.to_datetime(fb.entry_ts) >= "2024-07-01"]
    jobs = [(s, list(pd.to_datetime(g.entry_ts).values)) for s, g in fb.groupby("symbol")]
    with ProcessPoolExecutor(8) as ex:
        t = pd.concat([p for p in ex.map(FC._one, jobs) if p is not None], ignore_index=True)
    t["stop_frac"] = (t.ret / t.R).where(t.R.abs() > 1e-9); t["stop_frac"] = t.stop_frac.fillna(t.stop_frac.median()).clip(0.005, 0.5)
    m10 = H.momentum_hl(10, 15); m5 = H.momentum_hl(5, 8)
    rows = []
    for name, cap, m, N, f, kw in (
        ("300: 10 koin 0,5x + flush", 300, m10, 10, 0.5, {}),
        ("300: 10 koin 0,5x saja", 300, m10, 10, 0.5, dict(use_flush=False)),
        ("100: 10 koin dipaksa 10$ + flush", 100, m10, 10, 0.5, {}),
        ("100: 5 koin 0,5x + flush (tolak>2x, gross<=2x)", 100, m5, 5, 0.5, dict(reject_x=2, gross_cap=2)),
        ("100: 5 koin 0,5x saja", 100, m5, 5, 0.5, dict(use_flush=False)),
        ("100: flush saja (tolak>2x)", 100, m10, 10, 0.5, dict(use_mom=False, reject_x=2)),
    ):
        df, ex_ = SC.simulate(cap, m[m.index >= "2024-06-29"], N, f, t, start_date="2024-07-01", **kw)
        rows.append(dict(variant=name, **SC.st(df, cap), event_risk_max=round(ex_["event_risk_max"], 3)))
        print(rows[-1], flush=True)
    json.dump(rows, open(os.path.join(ta.OUT, "hl_small.json"), "w"))
