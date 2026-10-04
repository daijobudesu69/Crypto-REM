"""Data publik HYPE (Hyperliquid) lewat POST /info. Tidak butuh API key.

Batas resmi 1200 weight/menit per IP. candleSnapshot = 20 + 1 per 60 candle,
fundingHistory = 20 + 1 per 20 baris, allMids = 2. Satu siklus harian mengambil
candle ~200 perp, jadi permintaan diberi jeda (token bucket) supaya tidak kena 429.
"""
from __future__ import annotations

import threading
import time

import pandas as pd
import requests

MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


class InfoClient:
    def __init__(self, url="https://api.hyperliquid.xyz/info", weight_per_minute=1000,
                 timeout=30, session=None, sleep=time.sleep, clock=time.time):
        self.url = url
        self.limit = float(weight_per_minute)
        self.timeout = timeout
        self.s = session or requests.Session()
        self._sleep, self._clock = sleep, clock
        self._lock = threading.Lock()
        self._w, self._t = 0.0, clock()

    # ------------------------------------------------------------------ #
    def _spend(self, weight: float) -> None:
        with self._lock:
            now = self._clock()
            self._w = max(0.0, self._w - (now - self._t) * self.limit / 60)
            self._t = now
            self._w += weight
            over = self._w - self.limit
        if over > 0:
            self._sleep(over * 60 / self.limit)

    def post(self, body: dict, weight: float = 20, per_items: int | None = None, retries: int = 6):
        self._spend(weight)
        last = None
        for i in range(retries):
            try:
                r = self.s.post(self.url, json=body, timeout=self.timeout)
                if r.status_code == 429:
                    self._sleep(10 * (i + 1))
                    continue
                r.raise_for_status()
                js = r.json()
                if per_items and isinstance(js, list):
                    self._spend(len(js) / per_items)
                return js
            except Exception as e:  # noqa: BLE001
                last = e
                self._sleep(2 * (i + 1))
        raise RuntimeError(f"HYPE /info {body.get('type')} gagal: {type(last).__name__}")

    # ------------------------------------------------------------------ #
    def meta(self) -> dict:
        """{coin: {szDecimals, maxLeverage, isDelisted, onlyIsolated, markPx, midPx, dayNtlVlm}}"""
        m, ctx = self.post({"type": "metaAndAssetCtxs"})
        out = {}
        for a, c in zip(m["universe"], ctx):
            out[a["name"]] = {
                "szDecimals": int(a["szDecimals"]),
                "maxLeverage": int(a.get("maxLeverage", 1)),
                "isDelisted": bool(a.get("isDelisted", False)),
                "onlyIsolated": bool(a.get("onlyIsolated", False)),
                "markPx": _f(c.get("markPx")),
                "midPx": _f(c.get("midPx")),
                "dayNtlVlm": _f(c.get("dayNtlVlm")),
            }
        return out

    def all_mids(self) -> dict:
        return {k: float(v) for k, v in self.post({"type": "allMids"}, weight=2).items()}

    def candles(self, coin: str, interval: str, start_ms: int, end_ms: int | None = None,
                include_open: bool = False) -> pd.DataFrame:
        """Candle urut waktu. Default hanya candle yang sudah close."""
        now = int(self._clock() * 1000)
        end = end_ms or now
        rows, start = [], start_ms
        while start < end:
            raw = self.post({"type": "candleSnapshot",
                             "req": {"coin": coin, "interval": interval, "startTime": start, "endTime": end}},
                            per_items=60)
            if not raw:
                break
            rows += raw
            last = raw[-1]["t"]
            if len(raw) < 5000 or last + MS[interval] >= end:
                break
            start = last + MS[interval]
        return candles_frame(rows, interval, now, include_open)

    def funding_history(self, coin: str, start_ms: int, end_ms: int | None = None) -> list:
        """[(time_ms, rate)] — funding per jam HYPE."""
        out, start = [], start_ms
        end = end_ms or int(self._clock() * 1000)
        while start < end:
            raw = self.post({"type": "fundingHistory", "coin": coin, "startTime": start, "endTime": end},
                            per_items=20)
            if not raw:
                break
            out += [(int(r["time"]), float(r["fundingRate"])) for r in raw]
            nxt = int(raw[-1]["time"]) + 1
            if len(raw) < 500 or nxt <= start:
                break
            start = nxt
        return out

    def clearinghouse(self, user: str) -> dict:
        return self.post({"type": "clearinghouseState", "user": user}, weight=2)

    def spot_state(self, user: str) -> dict:
        return self.post({"type": "spotClearinghouseState", "user": user}, weight=2)


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def candles_frame(rows: list, interval: str, now_ms: int, include_open: bool = False) -> pd.DataFrame:
    cols = ["ts", "open", "high", "low", "close", "volume"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    out = pd.DataFrame({"ts": pd.to_datetime(df["t"].astype("int64"), unit="ms", utc=True)})
    for src, dst in [("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"), ("v", "volume")]:
        out[dst] = df[src].astype(float)
    if not include_open:
        out = out[(df["t"].astype("int64") + MS[interval]).values <= now_ms]
    return out.drop_duplicates("ts", keep="last").sort_values("ts").reset_index(drop=True)
