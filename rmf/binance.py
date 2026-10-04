"""Candle Binance untuk sinyal flush. Data publik, tanpa API key.

  spot    : data-api.binance.vision  -> terjangkau dari rumah user dan runner GitHub
  futures : fapi.binance.com         -> diblokir dari rumah user (timeout) dan dari
            IP AS (HTTP 451). Disiapkan untuk VPS yang lolos tes; lihat docs/SETUP.md.
"""
from __future__ import annotations

import time

import pandas as pd
import requests

URLS = {
    "binance_spot": "https://data-api.binance.vision/api/v3/klines",
    "binance_futures": "https://fapi.binance.com/fapi/v1/klines",
}
MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


class KlineClient:
    def __init__(self, source="binance_spot", timeout=20, session=None, sleep=time.sleep, clock=time.time):
        if source not in URLS:
            raise ValueError(f"sumber tidak dikenal: {source}")
        self.source = source
        self.url = URLS[source]
        self.timeout = timeout
        self.s = session or requests.Session()
        self._sleep, self._clock = sleep, clock

    def klines(self, symbol: str, interval: str = "4h", limit: int = 60) -> pd.DataFrame:
        """Candle yang sudah close saja, urut waktu. DataFrame kosong kalau simbol tidak ada."""
        last = None
        for i in range(3):
            try:
                r = self.s.get(self.url, params={"symbol": symbol, "interval": interval, "limit": limit},
                               timeout=self.timeout)
                if r.status_code == 400:          # simbol tidak ada / delist
                    return frame([], interval, int(self._clock() * 1000))
                if r.status_code in (418, 429):
                    self._sleep(15 * (i + 1))
                    continue
                r.raise_for_status()
                return frame(r.json(), interval, int(self._clock() * 1000))
            except Exception as e:  # noqa: BLE001
                last = e
                self._sleep(2 * (i + 1))
        raise RuntimeError(f"Binance {self.source} {symbol} gagal: {type(last).__name__}")


def frame(rows: list, interval: str, now_ms: int) -> pd.DataFrame:
    cols = ["ts", "open", "high", "low", "close", "volume"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame([r[:6] for r in rows], columns=["t", "open", "high", "low", "close", "volume"])
    out = pd.DataFrame({"ts": pd.to_datetime(df["t"].astype("int64"), unit="ms", utc=True)})
    for c in ["open", "high", "low", "close", "volume"]:
        out[c] = df[c].astype(float)
    done = (df["t"].astype("int64") + MS[interval]).values <= now_ms
    return out[done].reset_index(drop=True)
