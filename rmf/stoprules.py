"""Aturan berhenti yang disepakati sebelum forward test (HANDOVER_RMF.md §1).

  1. DD > 40% dari puncak ekuitas
  2. 9 bulan BERTURUT-TURUT return bulanan kalah dari basket "beli semua koin"
     (sleeve momentum 1x vs basket bobot sama 1x, seperti di riset)
  3. setelah 6 bulan: return 6 bulan di bawah persentil 5 return 6 bulan
     simulasi HYPE (ambang di config: stop_rules.six_month_floor_pct)

Fungsi di sini murni: menerima deret ekuitas harian dan indeks basket, lalu
mengembalikan status. Bot hanya menandai + alarm; keputusan berhenti di user.
Jangan menilai dari 3 bulan saja: di backtest 29% periode 3 bulan rugi.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Status:
    days: int = 0
    equity: float = 0.0
    peak: float = 0.0
    dd_pct: float = 0.0
    months_behind_streak: int = 0
    monthly: list = field(default_factory=list)     # [(bulan, strat%, basket%)]
    ret_6m_pct: float | None = None
    breaches: list = field(default_factory=list)    # teks pelanggaran
    dd_breached: bool = False


def sleeve_index(equity: pd.Series, exposure: pd.Series) -> pd.Series:
    """Indeks sleeve momentum di 1x: return harian akun / eksposur (gross/ekuitas)
    hari sebelumnya. Hari tanpa posisi (filter BTC OFF) = 0. Sama dengan cara riset
    membandingkan strategi 1x dengan basket 1x (research/xsec_hl.py)."""
    eq = equity.astype(float)
    x = exposure.reindex(eq.index).astype(float).shift(1)
    r = (eq / eq.shift(1) - 1).where(x > 1e-9, 0.0) / x.where(x > 1e-9, 1.0)
    return (1 + r.fillna(0.0)).cumprod()


def evaluate(equity: pd.Series, bench_index: pd.Series, cfg, exposure: pd.Series | None = None) -> Status:
    """equity, bench_index: Series harian (index tanggal) yang sejajar.
    exposure: gross/ekuitas per hari. Kalau ada, aturan 9 bulan membandingkan
    sleeve 1x dengan basket 1x; kalau tidak, ekuitas akun apa adanya."""
    r = cfg.stop_rules
    st = Status()
    eq = equity.dropna()
    if eq.empty:
        return st
    st.days = len(eq)
    st.equity = float(eq.iloc[-1])
    st.peak = float(eq.cummax().iloc[-1])
    st.dd_pct = (st.equity / st.peak - 1) * 100 if st.peak > 0 else 0.0
    if st.dd_pct < -r.max_drawdown_pct:
        st.dd_breached = True
        st.breaches.append(f"DD {st.dd_pct:.1f}% melewati batas -{r.max_drawdown_pct:g}%")

    # Bulanan: hanya bulan yang sudah LENGKAP (bulan berjalan tidak dihitung).
    strat = sleeve_index(eq, exposure) if exposure is not None else eq
    df = pd.DataFrame({"strat": strat, "bench": bench_index.reindex(eq.index).ffill()}).dropna()
    if len(df) >= 2:
        idx = pd.DatetimeIndex(df.index)
        last_month = idx[-1].to_period("M")
        ends = df.groupby(idx.to_period("M")).last()
        starts = df.iloc[[0]].copy()
        starts.index = [idx[0].to_period("M") - 1]
        series = pd.concat([starts, ends])
        rets = series.pct_change().dropna()
        rets = rets[rets.index < last_month]
        streak = 0
        for per, row in rets.iterrows():
            st.monthly.append((str(per), round(row["strat"] * 100, 2), round(row["bench"] * 100, 2)))
            streak = streak + 1 if row["strat"] < row["bench"] else 0
        st.months_behind_streak = streak
        if streak >= r.underperform_months:
            st.breaches.append(f"{streak} bulan berturut-turut kalah dari basket beli semua koin")

    start = pd.Timestamp(eq.index[0])
    six = start + pd.DateOffset(months=r.review_after_months)
    if pd.Timestamp(eq.index[-1]) >= six:
        base = float(eq.iloc[0])
        at6 = eq[eq.index <= six]
        st.ret_6m_pct = (float(at6.iloc[-1]) / base - 1) * 100 if base > 0 else None
        if st.ret_6m_pct is not None and st.ret_6m_pct < r.six_month_floor_pct:
            st.breaches.append(f"return {r.review_after_months} bulan {st.ret_6m_pct:+.1f}% < "
                               f"{r.six_month_floor_pct:+g}% (persentil 5 simulasi HYPE; hanya 5% "
                               f"jendela 6 bulan di simulasi yang lebih buruk)")
    return st
