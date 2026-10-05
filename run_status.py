"""Lihat keputusan momentum HARI INI tanpa mengubah state apa pun.

    python run_status.py            # rezim BTC, top 15, yang akan dibeli/dijual buku paper
    python run_status.py --flush    # juga hitung sinyal flush di candle 4h terakhir

Butuh ~3 menit (candle 1d semua perp HYPE, dengan jeda rate limit).
"""
from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd

from rmf import binance, config, control, flush as fl, hype, jobs, momentum as mom, notify, store


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flush", action="store_true")
    a = ap.parse_args()
    cfg = config.load()
    now = dt.datetime.now(dt.timezone.utc)
    ctx = jobs.Ctx(cfg=cfg, info=hype.InfoClient(cfg.hype.info_url, cfg.hype.weight_per_minute),
                   klines=binance.KlineClient(cfg.flush.signal_source), ctrl=control.read(),
                   outbox=notify.Outbox(now), now=now)
    day = jobs.utc_day(now)
    v = jobs.fetch_view(ctx, day)
    print(f"Hari eksekusi {v.exec_day} (candle {v.last_close_day}) · universe {v.universe_size} · eligible {len(v.ranking)}")
    print(f"Filter BTC: {'ON' if v.regime_on else 'OFF'}  close {v.btc_close:,.0f}  EMA50 {v.btc_ema:,.0f}")
    print(pd.DataFrame(v.ranking[:15], columns=["coin", "rank", "ret_14d"]).to_string(index=False))
    held = list(((store.load_json("momentum_paper.json") or {}).get("book") or {}).get("positions", {}))
    rb = mom.rebalance(v, held, cfg)
    print(f"\nBuku paper memegang: {held or '-'}")
    print(f"Jual: {rb.sells or '-'}")
    print(f"Beli: {rb.buys or '-'}")
    if a.flush:
        bar = jobs.latest_bar(now, cfg.momentum.run_after_minutes)
        hits = [s for s in jobs._symbols(cfg) if fl.signal_at_last(_k(ctx, s, bar), cfg)]
        print(f"\nFlush candle 4h {bar}: {len(hits)} sinyal (event kalau >= {cfg.flush.min_coins}) {hits}")


def _k(ctx, sym, bar):
    """Candle sampai `bar` saja, seperti jobs.run_flush: data boleh sudah memuat
    candle yang lebih baru (audit 2026-10-05 F8)."""
    k = ctx.klines.klines(sym, "4h", 60)
    if not k.empty:
        k = k[pd.DatetimeIndex(k["ts"]) <= bar]
    return k if (not k.empty and pd.Timestamp(k["ts"].iloc[-1]) == bar) else None


if __name__ == "__main__":
    main()
