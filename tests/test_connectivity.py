"""Cek jaringan sungguhan: dijalankan terpisah (CI job 'connectivity', boleh gagal).

    python -m pytest -q tests/test_connectivity.py -s
"""
import time

import requests

from rmf import binance, hype


def test_hype_info_reachable():
    c = hype.InfoClient()
    meta = c.meta()
    assert "BTC" in meta and meta["BTC"]["szDecimals"] >= 0
    df = c.candles("BTC", "1d", int(time.time() * 1000) - 10 * 86_400_000)
    assert len(df) >= 8


def test_binance_spot_reachable():
    df = binance.KlineClient("binance_spot").klines("BTCUSDT", "4h", 30)
    assert len(df) >= 25


def test_binance_futures_report_only():
    """Hanya laporan: fapi diblokir dari rumah user dan dari IP AS (451). Tidak gagal."""
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/time", timeout=10)
        print(f"\n[fapi.binance.com] HTTP {r.status_code}")
    except Exception as e:  # noqa: BLE001
        print(f"\n[fapi.binance.com] tidak terjangkau: {type(e).__name__}")
