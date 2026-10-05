import numpy as np
import pandas as pd

from rmf import flush as fl


def bars4h(closes, vols=None, start="2026-09-01"):
    c = np.asarray(closes, float)
    ts = pd.date_range(start, periods=len(c), freq="4h", tz="UTC")
    v = np.full(len(c), 100.0) if vols is None else np.asarray(vols, float)
    return pd.DataFrame({"ts": ts, "open": c, "high": c * 1.002, "low": c * 0.998, "close": c, "volume": v})


def flush_series(volume_spike=True):
    """Turun tajam menembus BB bawah, lalu candle terakhir naik kembali ke dalam band."""
    rng = np.random.default_rng(1)
    c = list(100 + rng.normal(0, 0.3, 40))
    c += [96.0]                              # tutup di bawah BB bawah
    c += [99.5]                              # tutup kembali di atas BB bawah
    v = [100.0] * 41 + [500.0 if volume_spike else 100.0]
    return bars4h(c, v)


def test_signal_requires_cross_and_volume(cfg):
    assert fl.signal_at_last(flush_series(True), cfg)
    assert not fl.signal_at_last(flush_series(False), cfg)
    assert not fl.signal_at_last(flush_series(True).iloc[:-1], cfg)   # masih di bawah band
    assert not fl.signal_at_last(None, cfg)


def test_hype_names():
    assert fl.hype_name("PEPEUSDT") == "kPEPE"
    assert fl.hype_name("1000PEPEUSDT") == "kPEPE"
    assert fl.hype_name("1000BONKUSDT") == "kBONK"
    assert fl.hype_name("SOLUSDT") == "SOL"


def test_pick_is_deterministic_and_capped():
    coins = [f"X{i}" for i in range(25)]
    bar = pd.Timestamp("2026-09-16 20:00", tz="UTC")
    a = fl.pick(coins, bar, 15)
    assert len(a) == 15 and a == fl.pick(list(reversed(coins)), bar, 15)
    assert fl.pick(coins[:5], bar, 15) == sorted(coins[:5])


def test_size_event_rules(cfg):
    # ekuitas 200: risiko target 1 USDC/koin. stop 2xATR.
    cands = [
        ("WIDE", 1.0, 0.03),     # stop 6% -> notional 16,7 -> diterima
        ("TIGHT", 1.0, 0.002),   # stop 0,4% -> notional 250 -> diterima tapi gross besar
        ("SUPERWIDE", 1.0, 0.15),  # stop 30% -> notional 3,3 < 10 -> paksa 10 -> risiko 3 > 2x1 -> tolak
        ("DEAD", 1.0, 0.0001),   # ATR < 0,05% harga -> tolak
    ]
    plans, rej = fl.size_event(cands, 200.0, 0.0, cfg)
    names = [p.coin for p in plans]
    assert "WIDE" in names and "TIGHT" in names
    assert {c for c, _ in rej} == {"SUPERWIDE", "DEAD"}
    w = next(p for p in plans if p.coin == "WIDE")
    assert abs(w.risk_usd - 1.0) < 1e-9 and abs(w.stop - 0.94) < 1e-12 and abs(w.target - 1.06) < 1e-12


def test_size_event_forced_min_within_2x_accepted(cfg):
    plans, rej = fl.size_event([("MID", 1.0, 0.08)], 200.0, 0.0, cfg)   # stop 16%: 6,25 -> 10, risiko 1,6
    assert plans and plans[0].forced_min and abs(plans[0].risk_usd - 1.6) < 1e-9


def test_size_event_gross_cap(cfg):
    # gross yang sudah terpakai 390 dari batas 400 (2x200)
    plans, rej = fl.size_event([("A", 1.0, 0.03)], 200.0, 390.0, cfg)
    assert not plans and "gross" in rej[0][1]


def test_size_event_total_risk_not_capped_like_research(cfg):
    """Q1 audit 2026-10-05: 15 koin yang dipaksa minimum order (risiko 1,6 USDC
    masing-masing, <= 2x target) semuanya diterima walau total 24 USDC = 12% > 8%,
    sama dengan small_capital.simulate (tanpa hard cap)."""
    cands = [(f"C{i:02d}", 1.0, 0.08) for i in range(15)]
    plans, rej = fl.size_event(cands, 200.0, 0.0, cfg)
    assert len(plans) == 15 and not rej
    assert abs(sum(p.risk_usd for p in plans) - 24.0) < 1e-9


def test_size_event_target_is_min_of_coin_and_event_share(cfg):
    """Risiko per koin = min(0,5%, 8% / n). n <= 15 -> 0,5%; n = 20 -> 0,4%."""
    p15, _ = fl.size_event([(f"C{i:02d}", 1.0, 0.01) for i in range(15)], 200.0, 0.0, cfg)
    assert all(abs(p.risk_usd - 1.0) < 1e-9 for p in p15)
    p20, _ = fl.size_event([(f"C{i:02d}", 1.0, 0.01) for i in range(20)], 1000.0, 0.0, cfg)
    assert all(abs(p.risk_usd - 4.0) < 1e-9 for p in p20)         # 1000 x 8% / 20


def _pos(entry_bar, stop=95.0, target=105.0):
    return {"entry_bar": entry_bar.isoformat(), "stop": stop, "target": target, "last_bar": None, "bars_held": 0}


def test_exit_sl_tp_gap_and_time():
    b = bars4h([100] * 60)
    e = b.ts.iloc[0]
    # TP
    b2 = b.copy(); b2.loc[3, "high"] = 106
    ex, p = fl.check_exit(_pos(e), b2, 48)
    assert ex["reason"] == "TP" and ex["exit_px"] == 105 and p["bars_held"] == 4
    # SL dan TP di bar yang sama -> SL dulu (konservatif, sama dengan backtest)
    b3 = b.copy(); b3.loc[2, "high"] = 106; b3.loc[2, "low"] = 94
    ex, _ = fl.check_exit(_pos(e), b3, 48)
    assert ex["reason"] == "SL" and ex["exit_px"] == 95
    # gap open di bawah stop -> keluar di open
    b4 = b.copy(); b4.loc[5, ["open", "low"]] = [90, 89]
    ex, _ = fl.check_exit(_pos(e), b4, 48)
    assert ex["reason"] == "SL (gap)" and ex["exit_px"] == 90
    # batas 48 candle
    ex, p = fl.check_exit(_pos(e), b, 48)
    assert ex["reason"].startswith("waktu") and p["bars_held"] == 48


def test_exit_incremental_does_not_recount():
    b = bars4h([100] * 10)
    e = b.ts.iloc[0]
    ex, p = fl.check_exit(_pos(e), b.iloc[:4], 48)
    assert ex is None and p["bars_held"] == 4
    ex, p = fl.check_exit(p, b, 48)            # bar 0-3 tidak dihitung ulang
    assert ex is None and p["bars_held"] == 10
