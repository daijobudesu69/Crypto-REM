"""Small-capital reality check: HYPE minimum order 10 USDC does not scale with equity.

Account simulation like strategy_sim.simulate, plus:
  * momentum notional per coin = max(f*equity/N, MIN)   -> effective exposure rises when equity falls
  * flush notional per coin  = max(risk/stop, MIN)      -> forced risk = MIN*stop
  * optional: skip a flush coin when forced risk > reject_x * target risk (MEX-style rule)
  * optional: total gross notional cap (x equity); flush coins beyond the cap are skipped
  * stop trading when equity < MIN (cannot place an order)
Also: funding-income stress (never receive funding) and flush random-pick seeds.

    python small_capital.py  -> results/small_capital.json
"""
import os, json, warnings
import numpy as np, pandas as pd
import ta, strategy_sim as S, buffer_test as BT, xsec

warnings.filterwarnings("ignore")
MIN = 10.0


def mom_series(N, exit_rank, no_fund_income=False):
    if not no_fund_income:
        net, top, _ = BT.run(N, exit_rank)
        return net, top
    # rerun with funding income removed (longs only pay, never receive)
    W = xsec.wide(xsec.panel())
    net, top, _ = BT.run(N, exit_rank)
    O, C, CF = W["open"], W["close"], W["cf"].ffill()
    w = top.div(top.sum(1).replace(0, np.nan), axis=0).fillna(0)
    r = (O.shift(-2) / O.shift(-1) - 1).fillna(0); f = (CF.shift(-1) - CF).fillna(0).clip(lower=0)
    turn = (w - w.shift(1).fillna(0)).abs().sum(1)
    n2 = (w * (r - f)).sum(1) - turn * 0.0007
    return n2[n2.index < C.index[-3]], top


def simulate(start, mom, N, f_mom, fl, r_coin=0.005, cap_event=0.08, reject_x=None, gross_cap=None, start_date="2020-01-01", use_mom=True, use_flush=True):
    days = pd.date_range(start_date, mom.index.max(), freq="D")
    m = mom.reindex(days).fillna(0.0).shift(1).fillna(0.0)
    fl = fl[pd.to_datetime(fl.entry_ts) >= start_date].copy()
    fl["entry_day"] = pd.to_datetime(fl.entry_ts).dt.floor("D"); fl["exit_day"] = pd.to_datetime(fl.exit_ts).dt.floor("D")
    ent = {d: g for d, g in fl.groupby("entry_day")}
    pending, open_n = {}, {}
    eq = start; rows = []; risk_taken = []; skipped = 0; taken = 0
    for d in days:
        if eq < MIN:
            rows.append((d, eq, 0, 0, 0)); continue
        f_eff = max(f_mom, MIN * N / eq) if use_mom else 0.0
        mom_on = m.loc[d] != 0
        pnl_m = eq * f_eff * m.loc[d] if use_mom else 0.0
        pnl_f = sum(pending.pop(d, []))
        open_n = {k: v for k, v in open_n.items() if k[0] >= d}
        if use_flush and d in ent:
            for et, ge in ent[d].groupby("entry_ts"):
                rc = min(r_coin, cap_event / len(ge)); ev_risk = 0.0
                for r in ge.itertuples():
                    target = eq * rc
                    notional = max(target / r.stop_frac, MIN)
                    risk = notional * r.stop_frac
                    if reject_x and risk > reject_x * target:
                        skipped += 1; continue
                    gross = (f_eff * eq if mom_on else 0) + sum(open_n.values())
                    if gross_cap and gross + notional > gross_cap * eq:
                        skipped += 1; continue
                    pending.setdefault(r.exit_day, []).append(risk * r.R)
                    open_n[(r.exit_day, et, r.symbol)] = notional
                    ev_risk += risk; taken += 1
                if ev_risk:
                    risk_taken.append(ev_risk / eq)
        gross_now = (f_eff * eq if (use_mom and mom_on) else 0) + sum(open_n.values())
        eq = max(eq + pnl_m + pnl_f, 0.0)
        rows.append((d, eq, pnl_m, pnl_f, gross_now / max(eq, 1e-9)))
    df = pd.DataFrame(rows, columns=["day", "equity", "pnl_mom", "pnl_flush", "gross_x"]).set_index("day")
    return df, dict(event_risk_max=max(risk_taken) if risk_taken else 0, event_risk_avg=float(np.mean(risk_taken)) if risk_taken else 0,
                    flush_taken=taken, flush_skipped=skipped)


def st(df, start):
    e = df.equity; r = e.pct_change().fillna(0)
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    dd = (e / e.cummax() - 1).min()
    mo = e.resample("ME").last(); mo = pd.concat([pd.Series([start], [mo.index[0] - pd.offsets.MonthEnd(1)]), mo]).pct_change().dropna()
    return dict(final=round(float(e.iloc[-1]), 1), cagr=round(float((max(e.iloc[-1], 1e-9) / start) ** (1 / yrs) - 1) * 100, 1), maxdd=round(float(dd) * 100, 1),
                worst_month=round(float(mo.min()) * 100, 1), worst_day=round(float(r.min()) * 100, 1), gross_max=round(float(df.gross_x.max()), 2),
                gross_avg=round(float(df.gross_x[df.gross_x > 0].mean()), 2), min_equity=round(float(e.min()), 1))


if __name__ == "__main__":
    out = {}
    fl = S.flush_trades()
    m10, _ = mom_series(10, 15); m5, _ = mom_series(5, 8); m3, _ = mom_series(3, 5)
    cfg = {
        "300 desain (10 koin 0,5x + flush)": (300, m10, 10, 0.5, {}),
        "100 desain dipaksa (10 koin -> 1,0x, flush floor 10$)": (100, m10, 10, 0.5, {}),
        "100 desain dipaksa + tolak risiko >2x + gross <=2x": (100, m10, 10, 0.5, dict(reject_x=2, gross_cap=2)),
        "100: 5 koin 0,5x + flush (tolak >2x, gross <=2x)": (100, m5, 5, 0.5, dict(reject_x=2, gross_cap=2)),
        "100: 5 koin 0,5x, tanpa flush": (100, m5, 5, 0.5, dict(use_flush=False)),
        "100: 3 koin 0,3x, tanpa flush": (100, m3, 3, 0.3, dict(use_flush=False)),
        "100: 10 koin 1,0x, tanpa flush": (100, m10, 10, 1.0, dict(use_flush=False)),
        "100: flush saja (tolak >2x)": (100, m10, 10, 0.5, dict(use_mom=False, reject_x=2)),
        "100: flush saja (floor, tanpa tolak)": (100, m10, 10, 0.5, dict(use_mom=False)),
    }
    res = []
    for name, (cap, ms, N, f, kw) in cfg.items():
        for sd in ("2020-01-01", "2022-01-01", "2025-01-01"):
            df, ex = simulate(cap, ms, N, f, fl, start_date=sd, **kw)
            row = dict(variant=name, start=sd, **st(df, cap), **ex)
            res.append(row); print(row, flush=True)
    out["variants"] = res
    # funding-income stress (300 design)
    m10nf, _ = mom_series(10, 15, no_fund_income=True)
    for nm, ms in (("dengan funding riil", m10), ("tanpa pemasukan funding", m10nf)):
        for sd in ("2020-01-01", "2025-01-01", "2026-01-01"):
            df, _ = simulate(300, ms, 10, 0.5, fl, start_date=sd)
            out.setdefault("funding", []).append(dict(case=nm, start=sd, **st(df, 300)))
    print(out["funding"])
    # flush random-pick seeds
    base = pd.read_parquet(os.path.join(ta.OUT, "breadth_trades_4h_sl2_tp2.parquet"))
    base = base[base.name == "L bb_revert+volhigh"].copy()
    base["n_event"] = base.groupby("entry_ts")["R"].transform("size"); base = base[base.n_event >= 10]
    base["stop_frac"] = (base.ret / base.R).where(base.R.abs() > 1e-9); base["stop_frac"] = base.stop_frac.fillna(base.stop_frac.median()).clip(0.005, 0.5)
    seeds = []
    for seed in range(1, 21):
        t = base.assign(rnd=np.random.default_rng(seed).random(len(base)))
        t = t[t.groupby("entry_ts")["rnd"].rank() <= 15]
        ev = t.groupby("entry_ts").R.mean()
        df, _ = simulate(300, m10, 10, 0.5, t)
        seeds.append(dict(seed=seed, ev_avgR=round(float(ev.mean()), 3), final=st(df, 300)["final"], maxdd=st(df, 300)["maxdd"]))
    out["seeds"] = seeds
    s = pd.DataFrame(seeds); print(s.describe().round(3))
    json.dump(out, open(os.path.join(ta.OUT, "small_capital.json"), "w"), default=str)
