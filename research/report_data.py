"""Collect every number for the RMF mobile report -> results/rmf_report.json

Momentum: q=0.1 (top 10%), L=14, BTC>EMA50 filter, 0.5x notional. Flush: >=10 coins, max 15, 0.5%/coin, cap 8%.
"""
import os, sys, json, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import ta, xsec, strategy_sim as S

warnings.filterwarnings("ignore")
SIDE = 0.0007
F_MOM, L, Q, N = 0.5, 14, 0.1, 10


def holdings():
    W = xsec.wide(xsec.panel())
    O, C, QV, CF = W["open"], W["close"], W["qv"], W["cf"].ffill()
    age = C.notna().cumsum()
    el = (age >= 60) & C.notna() & O.shift(-1).notna() & (age >= L + 30)
    btc = C["BTCUSDT"]; e50 = pd.Series(ta.F.ema(btc.values, 50), btc.index)
    bull = btc > e50
    ret14 = (C / C.shift(L) - 1).where(el)
    rk = ret14.rank(axis=1, pct=True)
    import buffer_test
    _, top, _ = buffer_test.run(N, 15, L)
    r = (O.shift(-2) / O.shift(-1) - 1)
    f = (CF.shift(-1) - CF)
    return dict(O=O, C=C, QV=QV, CF=CF, top=top, ret14=ret14, rk=rk, bull=bull, btc=btc, e50=e50, r=r, f=f, el=el)


def stints(H):
    top, r, f, O = H["top"], H["r"].fillna(0), H["f"].fillna(0), H["O"]
    rows = []
    for s in top.columns:
        x = top[s].values
        if not x.any():
            continue
        idx = top.index
        i = 0; n = len(x)
        while i < n:
            if x[i]:
                j = i
                while j + 1 < n and x[j + 1]:
                    j += 1
                gross = np.prod(1 + (r[s].values[i:j + 1] - f[s].values[i:j + 1])) - 1
                fund = f[s].values[i:j + 1].sum()
                rows.append(dict(symbol=s, signal_day=idx[i], entry=idx[i] + pd.Timedelta("1D"), exit=idx[j] + pd.Timedelta("2D"),
                                 days=j - i + 1, ret=gross - 2 * SIDE, funding=fund, ret14_at_entry=H["ret14"][s].iloc[i]))
                i = j + 1
            else:
                i += 1
    return pd.DataFrame(rows)


def latest_hype_ranking():
    """Fresh HYPE daily candles (free API) -> today's picks. Falls back to the data lake if offline."""
    import urllib.request
    uni = pd.read_csv(os.path.join(ta.DATA, "universe", "hyperliquid_top150.csv"))
    uni = uni[uni.isDelisted != True]
    end = int(pd.Timestamp.utcnow().timestamp() * 1000); start = end - 90 * 86400 * 1000
    closes, vols = {}, {}
    for coin in uni["name"]:
        body = json.dumps({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1d", "startTime": start, "endTime": end}}).encode()
        try:
            req = urllib.request.Request("https://api.hyperliquid.xyz/info", data=body, headers={"Content-Type": "application/json"})
            d = json.loads(urllib.request.urlopen(req, timeout=15).read())
        except Exception:
            continue
        if not d:
            continue
        t = pd.to_datetime([c["t"] for c in d], unit="ms")
        closes[coin] = pd.Series([float(c["c"]) for c in d], t)
        vols[coin] = pd.Series([float(c["v"]) * float(c["c"]) for c in d], t)
    C = pd.DataFrame(closes).sort_index(); V = pd.DataFrame(vols).sort_index()
    today = pd.Timestamp.utcnow().tz_localize(None).floor("D")
    C = C[C.index < today]; V = V[V.index < today]   # completed daily candles only
    last = C.index[-1]
    # BTC filter needs > 50 days: use lake history + fresh
    bl = pd.read_parquet(os.path.join(ta.DATA, "hyperliquid", "candles", "1d", "BTC.parquet"))
    bs = pd.Series(bl.close.values, ta._ns(bl.ts).dt.tz_convert(None).values)
    bs = pd.concat([bs, C["BTC"]]).groupby(level=0).last().sort_index()
    e = pd.Series(ta.F.ema(bs.values, 50), bs.index)
    # listing age from lake 1d files (>= 60 days)
    age_ok = {}
    for coin in C.columns:
        p = os.path.join(ta.DATA, "hyperliquid", "candles", "1d", f"{coin}.parquet")
        if os.path.exists(p):
            first = ta._ns(pd.read_parquet(p, columns=["ts"]).ts).min().tz_convert(None)
            age_ok[coin] = (last - first).days >= 60
        else:
            age_ok[coin] = False
    r14 = (C.iloc[-1] / C.iloc[-1 - L] - 1)
    vol30 = V.iloc[-30:].mean()
    df = pd.DataFrame({"ret14": r14, "vol30_usd": vol30, "age_ok": pd.Series(age_ok)}).dropna(subset=["ret14"])
    df = df[df.age_ok]
    df = df.sort_values("ret14", ascending=False)
    df["rank"] = np.arange(1, len(df) + 1)
    n_pick = N
    return dict(asof=str(last.date()), btc_close=float(bs.iloc[-1]), btc_ema50=float(e.iloc[-1]), btc_ok=bool(bs.iloc[-1] > e.iloc[-1]),
                n_universe=int(len(df)), n_pick=n_pick,
                table=[dict(coin=i, ret14=round(float(r.ret14) * 100, 1), vol30_musd=round(float(r.vol30_usd) / 1e6, 1), pick=bool(r["rank"] <= N))
                       for i, r in df.head(25).iterrows()])


def main():
    out = {}
    H = holdings()
    top = H["top"]
    # ---------------- simulation
    mom = S.momentum_daily(); fl = S.flush_trades()
    sim = S.simulate(f_mom=F_MOM, mom=mom, fl=fl)
    st = S.stats(sim)
    out["stats"] = {k: float(v) for k, v in st.items()}
    eq = sim.equity
    out["equity"] = [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in eq.resample("W").last().items()]
    dd = eq / eq.cummax() - 1
    out["drawdown"] = [[d.strftime("%Y-%m-%d"), round(float(v) * 100, 1)] for d, v in dd.resample("W").min().items()]
    other = pd.read_pickle(os.path.join(ta.OUT, "sim_variants.pkl"))
    out["equity_mom1x"] = [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in other["A momentum 1x"].equity.resample("W").last().items()]
    out["equity_flush"] = [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in other["B flush basket"].equity.resample("W").last().items()]
    mo = eq.resample("ME").last(); mo = pd.concat([pd.Series([300.0], [pd.Timestamp("2019-12-31")]), mo])
    mret = mo.pct_change().dropna()
    out["monthly"] = {f"{d.year}-{d.month:02d}": round(float(v) * 100, 1) for d, v in mret.items()}
    pm = (sim.pnl_mom.resample("ME").sum()); pf = sim.pnl_flush.resample("ME").sum()
    out["monthly_usd"] = {f"{d.year}-{d.month:02d}": [round(float(pm[d]), 1), round(float(pf[d]), 1), round(float(eq.resample('ME').last()[d]), 1)] for d in pm.index}
    y = eq.resample("YE").last(); y0 = pd.concat([pd.Series([300.0], [pd.Timestamp("2019-12-31")]), y])
    out["yearly"] = [dict(year=int(d.year), ret=round(float(v) * 100, 1), end=round(float(y[d]), 0),
                          dd=round(float(dd[dd.index.year == d.year].min()) * 100, 1),
                          mom_usd=round(float(sim.pnl_mom[sim.index.year == d.year].sum()), 0),
                          flush_usd=round(float(sim.pnl_flush[sim.index.year == d.year].sum()), 0)) for d, v in y0.pct_change().dropna().items()]
    # rolling windows
    roll = {}
    for m in (1, 3, 6, 12):
        rr = eq.resample("ME").last()
        rr = pd.concat([pd.Series([300.0], [pd.Timestamp("2019-12-31")]), rr])
        w = (rr / rr.shift(m) - 1).dropna()
        roll[f"{m}m"] = dict(n=int(len(w)), p_loss=round(float((w < 0).mean()) * 100, 0), median=round(float(w.median()) * 100, 1),
                             worst=round(float(w.min()) * 100, 1), best=round(float(w.max()) * 100, 1),
                             worst_end=str(w.idxmin().date()))
    out["rolling"] = roll
    # start-date sensitivity: start 300 on first day of each quarter, value after 12 months
    starts = []
    for s0 in pd.date_range("2020-01-01", eq.index[-1] - pd.Timedelta("365D"), freq="QS"):
        a = eq[eq.index >= s0].iloc[0]; b = eq[eq.index >= s0 + pd.Timedelta("365D")].iloc[0]
        seg = eq[(eq.index >= s0) & (eq.index <= s0 + pd.Timedelta("365D"))]
        starts.append(dict(start=str(s0.date()), end_usd=round(300 * float(b / a), 0), dd=round(float((seg / seg.cummax() - 1).min()) * 100, 1)))
    out["start_dates"] = starts
    # ---------------- momentum trades
    stn = stints(H)
    stn = stn[stn.signal_day < H["C"].index[-3]]
    stn["month"] = stn.entry.dt.to_period("M").astype(str)
    out["mom_stints"] = dict(n=int(len(stn)), median_days=float(stn.days.median()), mean_days=round(float(stn.days.mean()), 1),
                             wr=round(float((stn.ret > 0).mean()) * 100, 1), avg_ret=round(float(stn.ret.mean()) * 100, 2),
                             median_ret=round(float(stn.ret.median()) * 100, 2),
                             p1day=round(float((stn.days == 1).mean()) * 100, 0), p_ge7=round(float((stn.days >= 7).mean()) * 100, 0),
                             avg_win=round(float(stn.ret[stn.ret > 0].mean()) * 100, 1), avg_loss=round(float(stn.ret[stn.ret <= 0].mean()) * 100, 1),
                             days_hist={str(k): int(v) for k, v in stn.days.clip(upper=15).value_counts().sort_index().items()})
    out["mom_best"] = [dict(coin=r.symbol.replace("USDT", ""), entry=str(r.entry.date()), days=int(r.days), ret=round(r.ret * 100, 1)) for r in stn.nlargest(10, "ret").itertuples()]
    out["mom_worst"] = [dict(coin=r.symbol.replace("USDT", ""), entry=str(r.entry.date()), days=int(r.days), ret=round(r.ret * 100, 1)) for r in stn.nsmallest(10, "ret").itertuples()]
    # per-coin stats
    held_days = top.sum()
    cs = stn.groupby("symbol").agg(stints=("ret", "size"), days=("days", "sum"), wr=("ret", lambda x: (x > 0).mean()),
                                   sum_ret=("ret", "sum"), avg_ret=("ret", "mean")).sort_values("days", ascending=False)
    out["coins_top"] = [dict(coin=s.replace("USDT", ""), stints=int(r.stints), days=int(r.days), wr=round(r.wr * 100), avg=round(r.avg_ret * 100, 1), sum=round(r.sum_ret * 100, 0))
                        for s, r in cs.head(30).iterrows()]
    out["coins_contrib_best"] = [dict(coin=s.replace("USDT", ""), sum=round(r.sum_ret * 100, 0), stints=int(r.stints)) for s, r in cs.nlargest(10, "sum_ret").iterrows()]
    out["coins_contrib_worst"] = [dict(coin=s.replace("USDT", ""), sum=round(r.sum_ret * 100, 0), stints=int(r.stints)) for s, r in cs.nsmallest(10, "sum_ret").iterrows()]
    out["n_coins_ever"] = int((held_days > 0).sum())
    peryear = {}
    for yv in range(2020, 2027):
        sub = stn[stn.entry.dt.year == yv]
        if len(sub):
            g = sub.groupby("symbol").days.sum().nlargest(10)
            peryear[str(yv)] = [f"{s.replace('USDT','')} ({d}h)" for s, d in g.items()]
    out["coins_per_year"] = peryear
    # last 30 days holdings (Binance data)
    last_days = top.index[top.index <= H["C"].index[-1]][-30:]
    out["recent_holdings"] = [dict(day=str(d.date()), btc_ok=bool(H["bull"][d]), coins=[s.replace("USDT", "") for s in top.columns[top.loc[d].values]]) for d in last_days]
    # trades per month (momentum entries / exits, flush trades)
    ent = stn.groupby(stn.entry.dt.to_period("M")).size()
    exi = stn.groupby(stn.exit.dt.to_period("M")).size()
    fl2 = fl.copy(); fl2["m"] = pd.to_datetime(fl2.entry_ts).dt.to_period("M")
    fe = fl2.groupby("m").entry_ts.nunique(); ft = fl2.groupby("m").size()
    active = top.any(axis=1).groupby(top.index.to_period("M")).mean()
    months = pd.period_range("2020-01", "2026-09", freq="M")
    tpm = []
    for m in months:
        tpm.append(dict(m=str(m), mom_in=int(ent.get(m, 0)), mom_out=int(exi.get(m, 0)), fl_ev=int(fe.get(m, 0)), fl_tr=int(ft.get(m, 0)),
                        active=round(float(active.get(m, 0)) * 100)))
    out["trades_per_month"] = tpm
    T = pd.DataFrame(tpm); T["y"] = T.m.str[:4]
    out["trades_per_year"] = [dict(year=y_, mom_in=int(g.mom_in.sum()), mom_orders=int(g.mom_in.sum() + g.mom_out.sum()), fl_ev=int(g.fl_ev.sum()),
                                   fl_tr=int(g.fl_tr.sum()), per_month_mom=round(float(g.mom_in.mean()), 1), per_month_fl=round(float(g.fl_tr.mean()), 1),
                                   active=round(float(g.active.mean()))) for y_, g in T.groupby("y")]
    act = T[T.active > 0]
    out["trades_avg"] = dict(mom_in_all=round(float(T.mom_in.mean()), 1), mom_in_active=round(float(act.mom_in.mean()), 1),
                             mom_orders_all=round(float((T.mom_in + T.mom_out).mean()), 1), fl_tr=round(float(T.fl_tr.mean()), 1),
                             fl_ev=round(float(T.fl_ev.mean()), 2), months_no_flush=int((T.fl_ev == 0).sum()), months_no_mom=int((T.active == 0).sum()),
                             avg_coins_held=round(float(top.sum(1)[top.sum(1) > 0].mean()), 1),
                             min_coins=int(top.sum(1)[top.sum(1) > 0].min()), max_coins=int(top.sum(1).max()))
    # ---------------- flush events
    fl3 = fl.copy()
    fl3["coin"] = fl3.symbol.str.replace("USDT", "")
    evs = []
    for et, g in fl3.groupby("entry_ts"):
        evs.append(dict(t=str(pd.Timestamp(et))[:16], n=int(g.n_event.iloc[0]), taken=len(g), avgR=round(float(g.R.mean()), 2),
                        wins=int((g.R > 0).sum()), coins=sorted(g.coin.tolist()),
                        hold_h=round(float(((pd.to_datetime(g.exit_ts) - pd.to_datetime(g.entry_ts)).dt.total_seconds() / 3600).median()), 0)))
    out["flush_events"] = evs
    out["flush_stats"] = dict(events=len(evs), trades=int(len(fl3)), wr=round(float((fl3.R > 0).mean()) * 100, 1), avgR=round(float(fl3.R.mean()), 2),
                              ev_wr=round(float(np.mean([e["avgR"] > 0 for e in evs])) * 100, 1),
                              median_hold_h=float(((pd.to_datetime(fl3.exit_ts) - pd.to_datetime(fl3.entry_ts)).dt.total_seconds() / 3600).median()),
                              stop_median=round(float(fl3.stop_frac.median()) * 100, 1), stop_p10=round(float(fl3.stop_frac.quantile(.1)) * 100, 1),
                              stop_p90=round(float(fl3.stop_frac.quantile(.9)) * 100, 1),
                              tp_hit=round(float((fl3.R > 0.9).mean()) * 100, 1), sl_hit=round(float((fl3.R < -0.9).mean()) * 100, 1),
                              time_exit=round(float(((fl3.R >= -0.9) & (fl3.R <= 0.9)).mean()) * 100, 1),
                              best=max(evs, key=lambda e: e["avgR"]), worst=min(evs, key=lambda e: e["avgR"]))
    fcoins = fl3.groupby("coin").agg(n=("R", "size"), avgR=("R", "mean")).sort_values("n", ascending=False).head(20)
    out["flush_coins"] = [dict(coin=c, n=int(r.n), avgR=round(float(r.avgR), 2)) for c, r in fcoins.iterrows()]
    # ---------------- costs (approximate, USD)
    w = top.astype(float).div(top.sum(1).replace(0, np.nan), axis=0).fillna(0)
    turn = (w - w.shift(1).fillna(0)).abs().sum(1)
    fee_frac = (turn * SIDE).reindex(sim.index).fillna(0).shift(1).fillna(0)
    fund_frac = (w * H["f"].fillna(0)).sum(1).reindex(sim.index).fillna(0).shift(1).fillna(0)
    eq_prev = sim.equity.shift(1).fillna(300)
    fee_usd = (fee_frac * F_MOM * eq_prev); fund_usd = (fund_frac * F_MOM * eq_prev)
    fl_fee = 0.0014  # per flush trade round trip on notional
    out["costs"] = dict(mom_fee_pct_equity_per_year=round(float(fee_frac.groupby(fee_frac.index.year).sum().mean()) * F_MOM * 100, 1),
                        mom_funding_pct_equity_per_year=round(float(fund_frac.groupby(fund_frac.index.year).sum().mean()) * F_MOM * 100, 1),
                        fee_usd_by_year={str(k): round(float(v), 0) for k, v in fee_usd.groupby(fee_usd.index.year).sum().items()},
                        funding_usd_by_year={str(k): round(float(v), 0) for k, v in fund_usd.groupby(fund_usd.index.year).sum().items()},
                        avg_turnover=round(float(turn[turn > 0].mean()) * 100, 0))
    # ---------------- variants / scenarios
    var = []
    import xsec_detail as X
    for q in (3, 5, 7, 10, 15):
        _, stq, netq = X.run(L=14, regime="btc", univ="all", n_fixed=q)
        for fm in (0.25, 0.5, 0.75, 1.0):
            d = S.simulate(f_mom=fm, mom=netq, fl=fl); s = S.stats(d)
            var.append(dict(q=q, coins=round(stq["avg_coins"], 1), f=fm, final=round(s["final"]), cagr=round(s["cagr"] * 100), dd=round(s["maxdd"] * 100),
                            sharpe=round(s["sharpe"], 2), worst_month=round(s["worst_month"] * 100, 1)))
    out["variants"] = var
    for L_ in (7, 30):
        _, _, n_ = X.run(L=L_, regime="btc", univ="all", n_fixed=N)
        d = S.simulate(f_mom=F_MOM, mom=n_, fl=fl); s = S.stats(d)
        out.setdefault("lookback", []).append(dict(L=L_, final=round(s["final"]), cagr=round(s["cagr"] * 100), dd=round(s["maxdd"] * 100), sharpe=round(s["sharpe"], 2)))
    _, _, n_ = X.run(L=14, regime="none", univ="all", n_fixed=N)
    d = S.simulate(f_mom=F_MOM, mom=n_, fl=fl); s = S.stats(d)
    import buffer_test as BT
    for ex in (10, 15, 20, 30):
        n_, _, ent_ = BT.run(N, ex)
        d = S.simulate(f_mom=F_MOM, mom=n_, fl=fl); s = S.stats(d)
        epm = ent_.groupby(ent_.index.to_period("M")).sum()
        out.setdefault("buffer", []).append(dict(exit_rank=ex, entries_pm=round(float(epm.mean()), 1), final=round(s["final"]), cagr=round(s["cagr"] * 100),
                                                 dd=round(s["maxdd"] * 100), sharpe=round(s["sharpe"], 2)))
    _, _, n_ = X.run(L=14, regime="none", univ="all", n_fixed=N)   # (re)compute: the buffer loop above overwrote d/s
    d = S.simulate(f_mom=F_MOM, mom=n_, fl=fl); s = S.stats(d)
    out["no_btc_filter"] = dict(final=round(s["final"]), cagr=round(s["cagr"] * 100), dd=round(s["maxdd"] * 100), sharpe=round(s["sharpe"], 2))
    _, _, n_ = X.run(L=14, regime="btc", univ="old", n_fixed=N)
    d = S.simulate(f_mom=F_MOM, mom=n_, fl=fl); s = S.stats(d)
    out["old_coins_only"] = dict(final=round(s["final"]), cagr=round(s["cagr"] * 100), dd=round(s["maxdd"] * 100), sharpe=round(s["sharpe"], 2))
    for thr in (15, 20):
        fx = S.flush_trades(min_coins=thr)
        d = S.simulate(f_mom=F_MOM, mom=mom, fl=fx); s = S.stats(d)
        out.setdefault("flush_thr", []).append(dict(min_coins=thr, events=int(fx.entry_ts.nunique()), final=round(s["final"]), cagr=round(s["cagr"] * 100), dd=round(s["maxdd"] * 100)))
    # cost stress: double fees
    X.SIDE = 0.0014
    _, _, n2 = X.run(L=14, regime="btc", univ="all", n_fixed=N)
    X.SIDE = 0.0007
    d = S.simulate(f_mom=F_MOM, mom=n2, fl=fl); s = S.stats(d)
    out["double_cost"] = dict(final=round(s["final"]), cagr=round(s["cagr"] * 100), dd=round(s["maxdd"] * 100))
    # oos-only start
    d = S.simulate(f_mom=F_MOM, mom=mom[mom.index >= "2024-12-30"], fl=fl[pd.to_datetime(fl.entry_ts) >= "2025-01-01"])
    d = d[d.index >= "2025-01-01"]; d["equity"] = d.equity / d.equity.iloc[0] * 300; s = S.stats(d)
    out["oos"] = {k: float(v) for k, v in s.items()}
    # ---------------- latest picks
    try:
        out["hype_today"] = latest_hype_ranking()
    except Exception as e:
        out["hype_today"] = {"error": str(e)}
    lastd = H["C"].index[-1]
    Cc = H["C"]; agec = Cc.notna().cumsum()
    rk_last = (Cc.loc[lastd] / Cc.shift(L).loc[lastd] - 1)[(agec.loc[lastd] >= 60)].dropna().sort_values(ascending=False)
    out["binance_last"] = dict(asof=str(lastd.date()), btc_ok=bool(H["bull"][lastd]), btc=float(H["btc"][lastd]), e50=float(H["e50"][lastd]),
                               top=[dict(coin=s.replace("USDT", ""), ret14=round(float(v) * 100, 1)) for s, v in rk_last.head(15).items()],
                               n_universe=int(rk_last.size))
    # BTC filter history
    b = H["bull"]
    sw = b.astype(int).diff().fillna(0)
    out["btc_filter"] = dict(pct_on=round(float(b.mean()) * 100), switches_per_year=round(float((sw != 0).sum() / ((b.index[-1] - b.index[0]).days / 365.25)), 1),
                             last_switch=str(b.index[sw != 0][-1].date()), on_by_year={str(k): round(float(v) * 100) for k, v in b.groupby(b.index.year).mean().items()})
    json.dump(out, open(os.path.join(ta.OUT, "rmf_report.json"), "w"), default=str)
    print("ok", {k: (len(v) if hasattr(v, "__len__") else v) for k, v in out.items()})


if __name__ == "__main__":
    main()
