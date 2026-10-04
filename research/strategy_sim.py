"""Account simulation (300 USDT start) of the proposed free-data strategy:

  Sleeve A  MOMENTUM ROTATION (1d): each day rank coins by 14-day return, hold the top 20% equal weight,
            only while BTC daily close > EMA50; rebalance at the next daily open. Notional = f x equity.
  Sleeve B  FLUSH BASKET (4h, price-only CLR-1 twin): when >= 10 coins on the same 4h close re-enter above the
            lower Bollinger band (20,2) with volume > 1.5x SMA20, long all of them at next open,
            SL 2 ATR / TP 2 ATR / max 48 bars. Risk per coin r of equity, total risk per event capped.

Costs: 0.07%/side on turnover + real funding (cost only).  Data: Binance 2020-01 -> 2026-10.

    python strategy_sim.py  -> results/sim_*.parquet, reports/strategy_300usdt.png
"""
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import ta, xsec_detail

warnings.filterwarnings("ignore")
START = 300.0


Q_MOM = 0.1        # (quantile version, kept for comparison)
N_MOM = 10         # FINAL: fixed 10 coins -> 15 USDT per coin with 300 USDT at 0.5x (HYPE minimum order 10 USDT)
MAX_FLUSH_COINS = 15


EXIT_RANK = 15     # FINAL: buy when rank <= 10, keep until rank > 15 (fewer whipsaw trades, same edge)


def momentum_daily(q=Q_MOM, n_fixed=N_MOM, exit_rank=EXIT_RANK):
    if exit_rank:
        import buffer_test
        net, _, _ = buffer_test.run(n_fixed, exit_rank)
        return net
    _, _, net = xsec_detail.run(L=14, q=q, regime="btc", univ="all", n_fixed=n_fixed)
    return net  # daily return at 1x notional, indexed by signal day t (P&L realised over t+1 open -> t+2 open)


def flush_trades(min_coins=10):
    t = pd.read_parquet(os.path.join(ta.OUT, "breadth_trades_4h_sl2_tp2.parquet"))
    t = t[t.name == "L bb_revert+volhigh"].copy()
    t["n_event"] = t.groupby("entry_ts")["R"].transform("size")
    t = t[t.n_event >= min_coins].copy()
    t["stop_frac"] = (t.ret / t.R).where(t.R.abs() > 1e-9)
    t["stop_frac"] = t["stop_frac"].fillna(t["stop_frac"].median()).clip(0.005, 0.5)
    # cap coins per event (random pick, fixed seed): order size stays above the 10 USDT HYPE minimum
    t["rnd"] = np.random.default_rng(1).random(len(t))
    t = t[t.groupby("entry_ts")["rnd"].rank() <= MAX_FLUSH_COINS]
    return t.sort_values("entry_ts")


def simulate(f_mom=1.0, r_coin=0.005, cap_event=0.08, use_flush=True, use_mom=True, mom=None, fl=None):
    mom = momentum_daily() if mom is None else mom
    fl = flush_trades() if fl is None else fl
    days = pd.date_range("2020-01-01", mom.index.max(), freq="D")
    m = mom.reindex(days).fillna(0.0)
    # P&L of signal day t is realised by day t+2 open -> book it on day t+1
    m = m.shift(1).fillna(0.0)
    fl = fl.copy()
    fl["entry_day"] = pd.to_datetime(fl.entry_ts).dt.floor("D")
    fl["exit_day"] = pd.to_datetime(fl.exit_ts).dt.floor("D")
    ent = {d: g for d, g in fl.groupby("entry_day")}
    pending = {}  # exit_day -> list of pnl
    open_notional = {}
    eq = START; rows = []
    for d in days:
        pnl_m = eq * f_mom * m.loc[d] if use_mom else 0.0
        pnl_f = sum(pending.pop(d, []))
        if use_flush and d in ent:
            g = ent[d]
            for et, ge in g.groupby("entry_ts"):
                rc = min(r_coin, cap_event / len(ge))
                for r in ge.itertuples():
                    risk_usd = eq * rc
                    pending.setdefault(r.exit_day, []).append(risk_usd * r.R)
                    open_notional[(r.exit_day, et, r.symbol)] = risk_usd / r.stop_frac
        notional_f = sum(v for k, v in open_notional.items() if k[0] >= d)
        open_notional = {k: v for k, v in open_notional.items() if k[0] >= d}
        eq = eq + pnl_m + pnl_f
        rows.append((d, eq, pnl_m, pnl_f, (f_mom if (use_mom and m.loc[d] != 0) else 0) * eq + notional_f))
    df = pd.DataFrame(rows, columns=["day", "equity", "pnl_mom", "pnl_flush", "gross_notional"]).set_index("day")
    return df


def stats(df):
    e = df.equity; r = e.pct_change().fillna(0)
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    dd = e / e.cummax() - 1
    under = (dd < 0).astype(int)
    longest = under.groupby((under == 0).cumsum()).sum().max()
    mo = e.resample("ME").last().pct_change().dropna()
    return dict(final=e.iloc[-1], cagr=(e.iloc[-1] / START) ** (1 / yrs) - 1, maxdd=dd.min(), vol_ann=r.std() * np.sqrt(365),
                sharpe=r.mean() / r.std() * np.sqrt(365), worst_day=r.min(), best_day=r.max(), worst_month=mo.min(),
                best_month=mo.max(), pos_months=(mo > 0).mean(), longest_underwater_days=int(longest),
                max_gross_x=(df.gross_notional / df.equity).max(), avg_gross_x=(df.gross_notional / df.equity).mean())


if __name__ == "__main__":
    mom, fl = momentum_daily(), flush_trades()
    variants = {
        "A momentum 1x": dict(f_mom=1.0, use_flush=False),
        "B flush basket": dict(use_mom=False),
        "A 0.5x + B": dict(f_mom=0.5),
        "A 1x + B": dict(f_mom=1.0),
    }
    out = {}
    for k, v in variants.items():
        df = simulate(mom=mom, fl=fl, **v)
        out[k] = df
        df.to_parquet(os.path.join(ta.OUT, f"sim_{k.split()[0]}_{v.get('f_mom', 0)}_{int(v.get('use_flush', True))}.parquet"))
        s = stats(df)
        print(f"{k:38s}", {a: round(b, 3) for a, b in s.items()})
    # correlation between sleeves
    a = out["A 1x + B"]
    pm = a.pnl_mom / a.equity.shift(1); pf = a.pnl_flush / a.equity.shift(1)
    wk = pd.DataFrame({"m": pm, "f": pf}).resample("W").sum()
    print("weekly corr momentum vs flush:", round(wk.corr().iloc[0, 1], 3))
    pd.to_pickle(out, os.path.join(ta.OUT, "sim_variants.pkl"))
