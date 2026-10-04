"""200 vs 300 USD, floor = venue minimum order (HYPE 10$, Binance ~5$). Window 2024-07 -> 2026-10 and full 2020+ (Binance)."""
import pandas as pd, json, os, warnings
import ta, small_capital as SC, strategy_sim as S, hl_full as H
warnings.filterwarnings("ignore")

if __name__ == "__main__":
    import flush_cross as FC
    from concurrent.futures import ProcessPoolExecutor
    fb_all = S.flush_trades(); fb = fb_all[pd.to_datetime(fb_all.entry_ts) >= "2024-07-01"]
    jobs = [(s, list(pd.to_datetime(g.entry_ts).values)) for s, g in fb.groupby("symbol")]
    with ProcessPoolExecutor(8) as ex:
        th = pd.concat([p for p in ex.map(FC._one, jobs) if p is not None], ignore_index=True)
    th["stop_frac"] = (th.ret / th.R).where(th.R.abs() > 1e-9); th["stop_frac"] = th.stop_frac.fillna(th.stop_frac.median()).clip(0.005, 0.5)
    mh = H.momentum_hl(10, 15); mb = S.momentum_daily()
    rows = []
    for venue, m, fl, mn, sd in (("HYPE (sinyal flush Binance)", mh, th, 10, "2024-07-01"), ("Binance", mb, fb_all, 5, "2024-07-01"), ("Binance", mb, fb_all, 5, "2020-01-01")):
        SC.MIN = mn
        for cap in (200, 300):
            df, ex_ = SC.simulate(cap, m[m.index >= "2019-12-30"], 10, 0.5, fl, start_date=sd, reject_x=2, gross_cap=2)
            r = dict(venue=venue, start=sd[:4], cap=cap, **SC.st(df, cap), event_risk_max=round(ex_["event_risk_max"] * 100), skipped=ex_["flush_skipped"])
            rows.append(r); print(r, flush=True)
    json.dump(rows, open(os.path.join(ta.OUT, "cap_compare.json"), "w"))
