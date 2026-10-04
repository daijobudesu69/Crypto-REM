"""End-to-end offline: siklus momentum harian + event flush 4h + exit, dengan data tiruan."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from fakes import FakeInfo, FakeKlines, meta_for, universe_candles
from rmf import control, jobs, notify, store

SIGNAL_BAR = pd.Timestamp("2026-10-03 20:00", tz="UTC")


def flush_frame(end=SIGNAL_BAR, seed=0):
    rng = np.random.default_rng(seed)
    c = list(100 + rng.normal(0, 0.3, 40)) + [96.0, 99.5]
    v = [100.0] * 41 + [500.0]
    ts = pd.date_range(end=end, periods=len(c), freq="4h")
    c = np.asarray(c)
    return pd.DataFrame({"ts": ts, "open": c, "high": c + 0.5, "low": c - 0.5, "close": c, "volume": v})


@pytest.fixture
def world(monkeypatch):
    c1d = universe_candles()
    spot = [f"S{i:02d}USDT" for i in range(12)]
    c4h = {f"S{i:02d}": flush_frame(seed=i) for i in range(12)}
    meta = meta_for(c1d)
    meta.update({k: {"szDecimals": 1, "maxLeverage": 5, "isDelisted": False, "onlyIsolated": False,
                     "markPx": 99.5, "midPx": 99.5, "dayNtlVlm": 1.0} for k in c4h})
    mids = {c: float(df["close"].iloc[-1]) for c, df in c1d.items()}
    mids.update({k: 99.5 for k in c4h})
    info = FakeInfo(c1d, c4h, meta=meta, mids=mids, funding=0.00001)
    kl = FakeKlines({s: flush_frame(seed=i) for i, s in enumerate(spot)})
    monkeypatch.setattr(jobs, "_symbols", lambda cfg: spot)
    return info, kl


def ctx_at(cfg, info, kl, now, momentum="paper", flush="paper", factory=None):
    return jobs.Ctx(cfg=cfg, info=info, klines=kl, ctrl=control.Control(momentum=momentum, flush=flush),
                    outbox=notify.Outbox(now), now=now, trader_factory=factory)


def test_momentum_day_once(state_dir, cfg, world):
    info, kl = world
    early = dt.datetime(2026, 10, 4, 0, 1, tzinfo=dt.timezone.utc)
    assert jobs.run_momentum(ctx_at(cfg, info, kl, early)) is None          # candle belum final
    now = dt.datetime(2026, 10, 4, 0, 12, tzinfo=dt.timezone.utc)
    c = ctx_at(cfg, info, kl, now)
    out = jobs.run_momentum(c)
    assert out and out["paper"]["positions"] and len(out["paper"]["positions"]) == 10
    assert len([o for o in store.read("orders") if o["side"] == "BUY"]) == 10
    eq = store.read("equity")
    assert len(eq) == 1 and eq[0]["regime_on"] == "1"
    assert any("RMF momentum" in m["text"] for m in c.outbox.items)
    # siklus berikutnya di hari yang sama: tidak ada apa-apa
    assert jobs.run_momentum(ctx_at(cfg, info, kl, now + dt.timedelta(minutes=10))) is None
    assert len(store.read("equity")) == 1


def test_live_without_secret_reports_halt_but_paper_runs(state_dir, cfg, world):
    info, kl = world
    now = dt.datetime(2026, 10, 4, 0, 12, tzinfo=dt.timezone.utc)
    c = ctx_at(cfg, info, kl, now, momentum="live")
    out = jobs.run_momentum(c)
    assert out["paper"] and any("HALT" in e for e in out["live"]["errors"])
    ls = store.load_json("momentum_live.json")
    assert ls.get("last_day") is None and ls["attempts"]["2026-10-04"] == 1


def test_flush_event_then_exit(state_dir, cfg, world):
    info, kl = world
    now = dt.datetime(2026, 10, 4, 0, 5, tzinfo=dt.timezone.utc)
    c = ctx_at(cfg, info, kl, now)
    out = jobs.run_flush(c)
    assert out["event"] and out["n_signals"] == 12
    st = store.load_json("flush_paper.json")
    assert 0 < len(st["book"]["positions"]) <= cfg.flush.max_coins
    assert st["last_bar"] == SIGNAL_BAR.isoformat()
    assert jobs.run_flush(ctx_at(cfg, info, kl, now + dt.timedelta(minutes=10))) is None   # bar sama

    # dua candle berikutnya: candle kedua menembus target
    for k, df in info.c4h.items():
        nxt = pd.DataFrame({"ts": [SIGNAL_BAR + pd.Timedelta(hours=4), SIGNAL_BAR + pd.Timedelta(hours=8)],
                            "open": [99.5, 100.0], "high": [100.0, 130.0], "low": [99.0, 99.8],
                            "close": [99.8, 120.0], "volume": [100.0, 100.0]})
        info.c4h[k] = pd.concat([df, nxt], ignore_index=True)
    later = dt.datetime(2026, 10, 4, 8, 5, tzinfo=dt.timezone.utc)
    out2 = jobs.run_flush(ctx_at(cfg, info, kl, later))
    assert len(out2["exits"]) == len(st["book"]["positions"])
    trades = store.read("flush_trades")
    assert trades and all(t["reason"] == "TP" for t in trades)
    assert all(float(t["r_multiple"]) > 0.8 for t in trades)     # TP 2 ATR = ~1R dikurangi biaya
    assert store.load_json("flush_paper.json")["book"]["positions"] == {}


def test_flush_sizing_uses_combined_equity(state_dir, cfg, world):
    info, kl = world
    jobs.run_momentum(ctx_at(cfg, info, kl, dt.datetime(2026, 10, 4, 0, 3, tzinfo=dt.timezone.utc)))
    out = jobs.run_flush(ctx_at(cfg, info, kl, dt.datetime(2026, 10, 4, 0, 5, tzinfo=dt.timezone.utc)))
    st = store.load_json("flush_paper.json")
    risk = [p["risk_usd"] for p in st["book"]["positions"].values()]
    assert risk and max(risk) <= 2 * cfg.capital_usdc * cfg.flush.risk_pct / 100 + 1e-6
    assert sum(risk) <= cfg.capital_usdc * cfg.flush.max_event_risk_pct / 100 * 1.01
    assert out["opened"]


def test_nothing_before_forward_start(state_dir, cfg, world):
    import dataclasses
    info, kl = world
    late = dataclasses.replace(cfg, forward_start="2026-10-05")
    now = dt.datetime(2026, 10, 4, 12, 0, tzinfo=dt.timezone.utc)
    assert jobs.run_momentum(ctx_at(late, info, kl, now)) is None
    assert jobs.run_flush(ctx_at(late, info, kl, now)) is None
    assert store.read("orders") == []
