import numpy as np
import pandas as pd
import pytest

from fakes import daily, meta_for, universe_candles
from rmf import indicators as ind
from rmf import momentum as mom


def test_regime_and_top10(cfg):
    c = universe_candles(btc_bull=True)
    v = mom.market_view(c, meta_for(c), "2026-10-04", cfg)
    assert v.regime_on and v.last_close_day == "2026-10-03"
    rb = mom.rebalance(v, [], cfg)
    assert len(rb.buys) == 10 and rb.sells == []
    assert rb.buys == [x[0] for x in v.ranking[:10]]


def test_regime_off_sells_everything(cfg):
    c = universe_candles(btc_bull=False)
    v = mom.market_view(c, meta_for(c), "2026-10-04", cfg)
    assert not v.regime_on
    rb = mom.rebalance(v, ["C00", "C05"], cfg)
    assert rb.buys == [] and {s for s, _ in rb.sells} == {"C00", "C05"}


def test_buffer_keeps_rank_up_to_15(cfg):
    c = universe_candles()
    v = mom.market_view(c, meta_for(c), "2026-10-04", cfg)
    r = {x[1]: x[0] for x in v.ranking}
    held = [r[12], r[15], r[16]]
    rb = mom.rebalance(v, held, cfg)
    assert r[12] in rb.target and r[15] in rb.target
    assert [s for s, _ in rb.sells] == [r[16]]
    assert len(rb.target) == 10                  # 2 dipegang + 8 baru dari peringkat 1..10
    assert all(v.ranks()[b] <= 10 for b in rb.buys)


def test_short_history_not_eligible(cfg):
    c = universe_candles()
    c["NEW"] = daily(np.linspace(1, 50, 30), "2026-10-03")      # 30 hari, naik 50x
    v = mom.market_view(c, meta_for(c), "2026-10-04", cfg)
    assert "NEW" not in v.ranks()


def test_missing_last_candle_not_eligible(cfg):
    c = universe_candles()
    c["C00"] = c["C00"].iloc[:-1]               # kasus INIT di data lake 2026-10-03
    v = mom.market_view(c, meta_for(c), "2026-10-04", cfg)
    assert "C00" not in v.ranks()


def test_universe_excludes_stable_delisted_and_caps_top_n(cfg):
    c = universe_candles(n_coins=5)
    c["USDE"] = daily(np.ones(90), "2026-10-03", vol=1e12)
    c["DEAD"] = daily(np.linspace(1, 9, 90), "2026-10-03", vol=1e12)
    u = mom.select_universe(c, meta_for(c, delisted={"DEAD"}), cfg)
    assert "USDE" not in u and "DEAD" not in u


def test_btc_candle_must_be_final(cfg):
    c = universe_candles(end_day="2026-10-02")
    with pytest.raises(ValueError):
        mom.market_view(c, meta_for(c), "2026-10-04", cfg)


def test_order_size_respects_minimum():
    assert mom.order_size(10.0, 3.33, 0, 10) * 3.33 >= 10.05
    sz = mom.order_size(12.0, 0.1234, 1, 10)
    assert sz * 0.1234 >= 10.05 and round(sz, 1) == sz
    assert mom.order_size(50, 2.0, 2, 10) == 25.0


def test_per_coin_usd(cfg):
    assert mom.per_coin_usd(200, cfg) == 10
    assert mom.per_coin_usd(150, cfg) == 10           # minimum order HYPE
    assert mom.per_coin_usd(400, cfg) == 20


def _research_hold(C, btc, cfg, N=10, exit_rank=15, L=14):
    """Salinan loop research/hl_full.py::momentum_hl (tanpa kolom open)."""
    age = C.notna().cumsum()
    el = (age >= 60) & C.notna() & (age >= L + 30)
    bull = (btc > pd.Series(ind.ema(btc.values, 50), btc.index)).values
    rank = (C / C.shift(L) - 1).where(el).rank(axis=1, ascending=False, method="first").values
    hold = np.zeros(rank.shape, bool)
    cur = np.zeros(rank.shape[1], bool)
    for i in range(len(rank)):
        if not bull[i]:
            cur[:] = False
        else:
            rk = rank[i]
            cur = cur & (rk <= exit_rank)
            free = N - cur.sum()
            if free > 0:
                cand = np.where((~cur) & (rk <= N))[0]
                cand = cand[np.argsort(rk[cand])][:free]
                cur[cand] = True
        hold[i] = cur
    return pd.DataFrame(hold, index=C.index, columns=C.columns)


def test_bot_matches_research_loop_day_by_day(cfg):
    """Rotasi hari demi hari dari bot == loop riset (termasuk rezim ON/OFF dan koin baru)."""
    rng = np.random.default_rng(7)
    days = 160
    end = pd.Timestamp("2026-10-03")
    idx = pd.date_range(end=end, periods=days, freq="D")
    btc_path = 80_000 * np.exp(np.cumsum(np.r_[rng.normal(0.004, 0.02, 70), rng.normal(-0.006, 0.02, 30),
                                                rng.normal(0.006, 0.02, days - 100 + 300)]))
    btc_idx = pd.date_range(end=end, periods=len(btc_path), freq="D")
    btc = pd.Series(btc_path, btc_idx)
    cols = {}
    for i in range(30):
        start = 0 if i < 24 else 40 + 10 * (i - 24)        # 6 koin listing belakangan
        r = rng.normal(0.0, 0.05, days)
        s = pd.Series(5 * np.exp(np.cumsum(r)), idx)
        s.iloc[:start] = np.nan
        cols[f"K{i:02d}"] = s
    C = pd.DataFrame(cols).reindex(btc_idx)
    C.insert(0, "BTC", btc)                      # BTC juga anggota universe riset (riwayat panjang)
    hold = _research_hold(C, btc, cfg)

    def cand_upto(day):
        out = {"BTC": pd.DataFrame({"ts": btc_idx.tz_localize("UTC"), "open": btc.values, "high": btc.values,
                                    "low": btc.values, "close": btc.values, "volume": 1e9})}
        out["BTC"] = out["BTC"][out["BTC"].ts <= day.tz_localize("UTC")]
        for c, s in C.drop(columns="BTC").items():
            s2 = s[(s.index <= day)].dropna()
            out[c] = pd.DataFrame({"ts": s2.index.tz_localize("UTC"), "open": s2.values, "high": s2.values,
                                   "low": s2.values, "close": s2.values, "volume": 1e6})
        return out

    held = []
    checked = 0
    for day in idx[50:]:          # sebelum hari ke-60 belum ada koin eligible
        cand = cand_upto(day)
        v = mom.market_view(cand, meta_for(cand), day + pd.Timedelta(days=1), cfg)
        held = mom.rebalance(v, held, cfg).target
        want = sorted(hold.columns[hold.loc[day].values])
        assert sorted(held) == want, f"beda di {day.date()}"
        checked += 1
    assert checked == 110


def test_static_universe_mode_uses_research_list(cfg):
    import dataclasses
    scfg = dataclasses.replace(cfg, universe=dataclasses.replace(cfg.universe, mode="static"))
    c = universe_candles(n_coins=3)
    for name in ("ETH", "SOL", "INIT", "NOTINLIST"):
        c[name] = daily(np.linspace(1, 2, 90), "2026-10-03")
    u = mom.select_universe(c, meta_for(c, delisted={"SOL"}), scfg)
    assert u == ["BTC", "ETH", "INIT"]          # urutan daftar riset, SOL delist, sisanya tidak di daftar


def test_bench_research_definition(cfg):
    """Basket: eligible di close E-2, return open(E-1) -> open(E) dikurangi funding, 1x."""
    c = {}
    for name, o_prev, o_now in (("A", 10.0, 11.0), ("B", 20.0, 19.0)):
        df = daily(np.full(70, 5.0), "2026-10-04")     # 70 candle, termasuk candle hari ini (belum close)
        df.loc[df.index[-2], "open"] = o_prev
        df.loc[df.index[-1], "open"] = o_now
        c[name] = df
    young = daily(np.full(40, 5.0), "2026-10-04")
    c["Y"] = young
    m = mom.bench_members(c, ["A", "B", "Y"], "2026-10-04", 60)
    assert set(m) == {"A", "B"}
    r = mom.bench_return(m, {"A": 0.001})
    assert abs(r - ((0.1 - 0.001) + (-0.05)) / 2) < 1e-12


def test_open_candle_ignored_for_ranking(cfg):
    c = universe_candles(end_day="2026-10-04")         # candle 10-04 = hari ini, belum close
    v_open = mom.market_view(c, meta_for(c), "2026-10-04", cfg)
    c2 = {k: df.iloc[:-1] for k, df in c.items()}
    v_closed = mom.market_view(c2, meta_for(c2), "2026-10-04", cfg)
    assert v_open.ranking == v_closed.ranking and v_open.btc_ema == v_closed.btc_ema
