"""100 USD on Binance (min order 5$) + drawdown dates HYPE vs Binance."""
import pandas as pd, json, os, warnings
import ta, small_capital as SC, strategy_sim as S, hl_full as H
warnings.filterwarnings("ignore")

def dd_info(e):
    dd = e / e.cummax() - 1; t = dd.idxmin(); peak = e[:t].idxmax()
    rec = e[t:][e[t:] >= e[peak]]
    return dict(maxdd=round(float(dd.min()) * 100, 1), peak=str(peak.date()), trough=str(t.date()), recovered=str(rec.index[0].date()) if len(rec) else "belum")

if __name__ == "__main__":
    import flush_cross as FC
    from concurrent.futures import ProcessPoolExecutor
    fb_all = S.flush_trades(); fb = fb_all[pd.to_datetime(fb_all.entry_ts) >= "2024-07-01"]
    jobs = [(s, list(pd.to_datetime(g.entry_ts).values)) for s, g in fb.groupby("symbol")]
    with ProcessPoolExecutor(8) as ex:
        th = pd.concat([p for p in ex.map(FC._one, jobs) if p is not None], ignore_index=True)
    th["stop_frac"] = (th.ret / th.R).where(th.R.abs() > 1e-9); th["stop_frac"] = th.stop_frac.fillna(th.stop_frac.median()).clip(0.005, 0.5)
    mh = H.momentum_hl(10, 15); mb = S.momentum_daily(); mb5 = SC.mom_series(5, 8)[0]
    out = {}
    SC.MIN = 10
    a, _ = SC.simulate(300, mh, 10, 0.5, th, start_date="2024-07-01", reject_x=2, gross_cap=2)
    SC.MIN = 5
    b, _ = SC.simulate(300, mb, 10, 0.5, fb_all, start_date="2024-07-01", reject_x=2, gross_cap=2)
    out["dd_hype"] = dd_info(a.equity); out["dd_binance"] = dd_info(b.equity)
    mo = pd.DataFrame({"hype": a.equity.resample("ME").last().pct_change(), "binance": b.equity.resample("ME").last().pct_change()}).dropna()
    out["monthly_corr"] = round(float(mo.corr().iloc[0, 1]), 2)
    out["up_months_avg"] = {k: round(float(mo[k][mo[k] > 0].mean()) * 100, 1) for k in mo}
    out["down_months_avg"] = {k: round(float(mo[k][mo[k] < 0].mean()) * 100, 1) for k in mo}
    rows = []
    for name, m, N, f, kw in (("10 koin x 5$ (0,5x) + flush", mb, 10, 0.5, dict(reject_x=2, gross_cap=2)),
                              ("10 koin x 5$, tanpa flush", mb, 10, 0.5, dict(use_flush=False)),
                              ("5 koin x 10$ (0,5x) + flush", mb5, 5, 0.5, dict(reject_x=2, gross_cap=2))):
        for sd in ("2020-01-01", "2024-07-01", "2025-01-01"):
            df, ex_ = SC.simulate(100, m, N, f, fb_all, start_date=sd, **kw)
            r = dict(variant=name, start=sd[:7], **SC.st(df, 100), event_risk_max=round(ex_["event_risk_max"] * 100), skipped=ex_["flush_skipped"])
            rows.append(r)
    out["binance_100"] = rows
    json.dump(out, open(os.path.join(ta.OUT, "q_extra.json"), "w"))
    print(json.dumps({k: v for k, v in out.items() if k != "binance_100"}, indent=0))
    for r in rows: print(r["variant"], r["start"], r["final"], r["cagr"], r["maxdd"], r["worst_month"], r["min_equity"], r["event_risk_max"], r["skipped"])
