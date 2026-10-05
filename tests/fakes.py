"""Data dan bursa tiruan untuk tes offline."""
from __future__ import annotations

import numpy as np
import pandas as pd

DAY = pd.Timedelta(days=1)


def daily(closes, end_day: str, vol=1000.0) -> pd.DataFrame:
    """Candle 1d yang berakhir di end_day (inklusif)."""
    closes = np.asarray(closes, float)
    end = pd.Timestamp(end_day, tz="UTC")
    ts = pd.date_range(end=end, periods=len(closes), freq="D")
    return pd.DataFrame({"ts": ts, "open": closes, "high": closes * 1.01, "low": closes * 0.99,
                         "close": closes, "volume": vol})


def universe_candles(end_day="2026-10-03", n_coins=25, days=90, seed=0, btc_bull=True):
    """BTC + n koin dengan tren berbeda. Koin Cn naik makin kencang untuk n kecil."""
    rng = np.random.default_rng(seed)
    out = {}
    btc = np.linspace(60_000, 90_000, 400) if btc_bull else np.linspace(90_000, 60_000, 400)
    out["BTC"] = daily(btc, end_day, vol=1e6)
    for i in range(n_coins):
        drift = 0.02 - i * 0.0012
        r = drift + rng.normal(0, 0.01, days)
        out[f"C{i:02d}"] = daily(10 * np.exp(np.cumsum(r)), end_day, vol=1e5 * (n_coins - i))
    return out


def meta_for(candles: dict, delisted=(), only_iso=()) -> dict:
    return {c: {"szDecimals": 2, "maxLeverage": 5, "isDelisted": c in delisted, "onlyIsolated": c in only_iso,
                "markPx": _last(df), "midPx": _last(df), "dayNtlVlm": 1.0}
            for c, df in candles.items()}


def _last(df):
    return float(df["close"].iloc[-1]) if len(df) else None


class FakeInfo:
    """Pengganti rmf.hype.InfoClient."""

    def __init__(self, candles_1d: dict, candles_4h: dict | None = None, meta=None, mids=None, funding=0.0):
        self.c1d = candles_1d
        self.c4h = candles_4h or {}
        self._meta = meta or meta_for(candles_1d)
        self._mids = mids or {c: float(df["close"].iloc[-1]) for c, df in candles_1d.items()}
        self.funding_rate = funding
        self.calls = {"candles": 0}

    def meta(self):
        return self._meta

    def all_mids(self):
        return dict(self._mids)

    def candles(self, coin, interval, start_ms, end_ms=None, include_open=False):
        self.calls["candles"] += 1
        src = self.c1d if interval == "1d" else self.c4h
        df = src.get(coin)
        if df is None:
            raise RuntimeError("no data")
        return df[df["ts"] >= pd.Timestamp(start_ms, unit="ms", tz="UTC")].reset_index(drop=True)

    def funding_history(self, coin, start_ms, end_ms=None):
        # seperti HYPE: satu funding per jam bulat di dalam [start, end]
        end = end_ms or start_ms
        first = -(-start_ms // 3_600_000) * 3_600_000
        return [(t, self.funding_rate) for t in range(first, end + 1, 3_600_000)]


class FakeKlines:
    def __init__(self, frames: dict):
        self.frames = frames

    def klines(self, symbol, interval="4h", limit=60):
        df = self.frames.get(symbol)
        if df is None:
            return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
        return df.tail(limit).reset_index(drop=True)


class FakeTrader:
    """Bursa tiruan untuk rmf.live.run_momentum."""

    def __init__(self, agent="0xAGENT", registered=True, equity=200.0, positions=None, mids=None,
                 fail_buy=(), sz_decimals=2):
        self.agent_address = agent
        self.registered = registered
        self._equity = equity
        self.pos = dict(positions or {})
        self._mids = mids or {}
        self.fail_buy = set(fail_buy)
        self.sent = []
        self.lev = []
        self.sz = sz_decimals

    def agents(self):
        return [{"address": self.agent_address, "validUntil": 4_102_444_800_000}] if self.registered else []

    def sz_decimals(self, coin):
        return self.sz

    def mids(self):
        return dict(self._mids)

    def positions(self):
        return {c: {"szi": s, "entry_px": 1.0, "unrealized": 0.0, "cross": True} for c, s in self.pos.items()}

    def equity(self):
        return self._equity, "fake"

    def set_leverage(self, coin, leverage, cross):
        self.lev.append((coin, leverage, cross))
        return {"ok": True}

    def market(self, coin, is_buy, sz, mid, slippage, reduce_only=False, cloid_hex=None):
        self.sent.append({"coin": coin, "is_buy": is_buy, "sz": sz, "reduce_only": reduce_only, "cloid": cloid_hex})
        if is_buy and coin in self.fail_buy:
            return {"error": "Insufficient margin"}
        delta = sz if is_buy else -sz
        self.pos[coin] = round(self.pos.get(coin, 0.0) + delta, 8)
        if self.pos[coin] == 0:
            del self.pos[coin]
        return {"filled": {"totalSz": str(sz), "avgPx": str(mid), "oid": 1}}
