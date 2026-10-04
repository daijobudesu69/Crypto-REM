"""Indikator yang dipakai bot. Rumusnya disalin dari helper riset
(`backtest data and more/research/features.py`) supaya angka live sama dengan
backtest. Jangan diganti ke library lain: EMA/ATR versi lain memberi angka
berbeda di desimal kecil, dan itu cukup untuk menggeser ranking atau sinyal.
"""
import numpy as np
import pandas as pd


def ema(x, n):
    """EMA span n, adjust=False, min_periods=n (sama dengan features.ema)."""
    return pd.Series(np.asarray(x, float)).ewm(span=n, adjust=False, min_periods=n).mean().values


def sma(x, n):
    return pd.Series(np.asarray(x, float)).rolling(n, min_periods=n).mean().values


def rolling_std(x, n):
    """Std sampel (ddof=1), sama dengan pandas rolling().std() di riset."""
    return pd.Series(np.asarray(x, float)).rolling(n).std().values


def atr(h, l, c, n=14):
    """ATR Wilder (ewm alpha=1/n), sama dengan features.atr."""
    h, l, c = (np.asarray(a, float) for a in (h, l, c))
    pc = np.roll(c, 1)
    pc[0] = np.nan
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().values


def cross_up(a, b):
    """True di bar i kalau a[i] > b[i] dan a[i-1] <= b[i-1]."""
    a = np.asarray(a, float)
    b = np.broadcast_to(np.asarray(b, float), a.shape)
    pa, pb = np.roll(a, 1), np.roll(b, 1)
    out = (a > b) & (pa <= pb)
    if len(out):
        out[0] = False
    return out


def bb_lower(c, n=20, k=2.0):
    return sma(c, n) - k * rolling_std(c, n)
