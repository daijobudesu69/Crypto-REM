import dataclasses
import datetime as dt

import pytest

from fakes import FakeTrader, meta_for, universe_candles
from rmf import live
from rmf import momentum as mom

NOW = dt.datetime(2026, 10, 4, 0, 5, tzinfo=dt.timezone.utc)


@pytest.fixture
def lcfg(cfg):
    ex = dataclasses.replace(cfg.execution, master_address="0xMASTER", account_address="0xSUB",
                             agent_address="0xAGENT", agent_valid_until="2027-03-30")
    return dataclasses.replace(cfg, execution=ex)


@pytest.fixture
def view(cfg):
    c = universe_candles()
    return mom.market_view(c, meta_for(c), "2026-10-04", cfg)


def mids(view):
    return {c: 2.0 for c, _, _ in view.ranking}


def test_wrong_key_halts_before_any_order(lcfg, view):
    t = FakeTrader(agent="0xOTHER", mids=mids(view))
    with pytest.raises(live.Halt):
        live.run_momentum(view, lcfg, t, "live", False, NOW)
    assert t.sent == []


def test_unregistered_or_expired_agent_halts(lcfg, view):
    with pytest.raises(live.Halt):
        live.run_momentum(view, lcfg, FakeTrader(registered=False, mids=mids(view)), "live", False, NOW)
    late = NOW.replace(year=2027, month=4)
    with pytest.raises(live.Halt):
        live.run_momentum(view, lcfg, FakeTrader(mids=mids(view)), "live", False, late)


def test_live_buys_top10_cross_and_min_size(lcfg, view):
    t = FakeTrader(mids=mids(view))
    r = live.run_momentum(view, lcfg, t, "live", False, NOW)
    assert not r["errors"]
    assert sorted(t.pos) == sorted(c for c, rk, _ in view.ranking if rk <= 10)
    assert all(s["sz"] * 2.0 >= 10.0 for s in t.sent)          # minimum order 10 USDC
    assert all(cross for _, _, cross in t.lev)
    assert all(live.is_bot_cloid(s["cloid"]) for s in t.sent)


def test_rerun_same_day_is_idempotent(lcfg, view):
    t = FakeTrader(mids=mids(view))
    live.run_momentum(view, lcfg, t, "live", False, NOW)
    n = len(t.sent)
    r = live.run_momentum(view, lcfg, t, "live", False, NOW, attempt=1)
    assert len(t.sent) == n and r["orders"] == []


def test_sell_rank_above_15_reduce_only(lcfg, view):
    r16 = next(c for c, rk, _ in view.ranking if rk == 16)
    r12 = next(c for c, rk, _ in view.ranking if rk == 12)
    t = FakeTrader(mids=mids(view), positions={r16: 5.0, r12: 5.0})
    live.run_momentum(view, lcfg, t, "live", False, NOW)
    sell = [s for s in t.sent if not s["is_buy"]]
    assert [s["coin"] for s in sell] == [r16] and sell[0]["reduce_only"] and sell[0]["sz"] == 5.0
    assert r12 in t.pos


def test_manage_and_breaker_never_buy(lcfg, view):
    for mode, block in (("manage", False), ("live", True)):
        t = FakeTrader(mids=mids(view))
        r = live.run_momentum(view, lcfg, t, mode, block, NOW)
        assert not any(s["is_buy"] for s in t.sent) and r["skipped"]


def test_flatten_closes_everything(lcfg, view):
    t = FakeTrader(mids={**mids(view), "ZZZ": 1.0}, positions={"C00": 3.0, "ZZZ": -2.0})
    live.run_momentum(view, lcfg, t, "flatten", False, NOW)
    assert t.pos == {}
    assert all(s["reduce_only"] for s in t.sent)


def test_failed_buy_reported_not_raised(lcfg, view):
    top = next(c for c, rk, _ in view.ranking if rk == 1)
    t = FakeTrader(mids=mids(view), fail_buy={top})
    r = live.run_momentum(view, lcfg, t, "live", False, NOW)
    assert any(top in e for e in r["errors"]) and top not in t.pos and len(t.pos) == 9


def test_only_isolated_coin_uses_isolated_1x(lcfg, view):
    top = next(c for c, rk, _ in view.ranking if rk == 1)
    t = FakeTrader(mids=mids(view))
    live.run_momentum(view, lcfg, t, "live", False, NOW, only_isolated=frozenset({top}))
    assert (top, 1, False) in t.lev


def test_px_rounding_rules():
    assert live.round_px(1.234567, 2) == 1.2346          # 5 angka signifikan
    assert live.round_px(0.000123456, 0) == 0.000123     # maks 6 - szDecimals desimal
    assert live.ioc_px(100.0, True, 2, 0.01) == 101.0
