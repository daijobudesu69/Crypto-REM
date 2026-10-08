"""Universe bulanan (rolling_monthly) dan buku paper pembanding (compare_rolling), offline."""
import dataclasses
import datetime as dt
import os
import shutil

import numpy as np
import pytest

from fakes import FakeInfo, daily, meta_for, universe_candles
from rmf import book as bk
from rmf import config, control, jobs, notify, store
from rmf import momentum as mom


def with_rolling(cfg, **kw):
    return dataclasses.replace(cfg, universe=dataclasses.replace(cfg.universe, compare_rolling=True, **kw))


def ctx_at(cfg, info, now, momentum="paper"):
    return jobs.Ctx(cfg=cfg, info=info, klines=None, ctrl=control.Control(momentum=momentum, flush="off"),
                    outbox=notify.Outbox(now), now=now)


def at(day, hh=0, mm=12):
    return dt.datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:00+00:00")


def texts(c):
    return [m["text"] for m in c.outbox.sent] + [m["text"] for m in c.outbox.items]


# --------------------------------------------------------------------------- #
#  aturan keanggotaan (fungsi murni)
# --------------------------------------------------------------------------- #
def test_hysteresis_entry_and_exit():
    ranked = [f"R{i:03d}" for i in range(1, 251)]              # R001 = volume terbesar
    members = ["R160", "R200", "R201", "R210", "R002"]
    new, ins, outs = mom.refresh_members(members, ranked, top_n=150, exit_rank=200)
    assert "R160" in new and "R200" in new                       # anggota di 151..200 tetap
    assert "R170" not in new                                     # non-anggota di 151..200 tidak masuk
    assert "R201" in outs and "R210" in outs                     # anggota > 200 keluar
    assert "R001" in ins and "R150" in ins and "R002" not in ins  # non-anggota <= 150 masuk
    assert new == sorted(new)                                    # urut volume (pemecah seri)
    assert len(new) == 152


def test_member_without_data_or_delisted_or_excluded_leaves(cfg):
    c = {f"K{i}": daily(np.ones(70), "2026-10-03", vol=1e6 - i) for i in range(5)}
    c["USDE"] = daily(np.ones(70), "2026-10-03", vol=1e12)
    c["DEAD"] = daily(np.ones(70), "2026-10-03", vol=1e12)
    meta = meta_for(c, delisted={"DEAD"})
    meta["GONE"] = meta["K0"]                                    # ada di meta, tanpa candle
    ranked = mom.volume_ranked(c, meta, cfg)
    assert ranked == ["K0", "K1", "K2", "K3", "K4"]
    new, _, outs = mom.refresh_members(["DEAD", "USDE", "GONE", "K4"], ranked, 150, 200)
    assert set(outs) == {"DEAD", "USDE", "GONE"} and new == ranked


def test_monthly_refresh_once_per_month_and_idempotent(cfg):
    c = {f"K{i}": daily(np.ones(70), "2026-10-03", vol=1e6 - i) for i in range(6)}
    meta = meta_for(c)
    small = with_rolling(cfg, top_n=2, exit_rank=4)
    st0 = {"members": ["K5", "K3"], "last_refresh": None, "log": []}
    st1, e1 = mom.rolling_update(st0, c, meta, "2026-10-08", small)
    assert e1 == ["2026-10-08", ["K0", "K1"], ["K5"]]
    assert st1["members"] == ["K0", "K1", "K3"] and st1["last_refresh"] == "2026-10-08"
    # bulan sama: tidak dihitung ulang walau volume berubah total
    c2 = {k: daily(np.ones(70), "2026-10-20", vol=1.0 + i) for i, k in enumerate(c)}
    st2, e2 = mom.rolling_update(st1, c2, meta, "2026-10-21", small)
    assert e2 is None and st2 == st1
    st3, e3 = mom.rolling_update(st1, c2, meta, "2026-11-01", small)
    assert e3 is not None and st3["last_refresh"] == "2026-11-01"
    assert st3["members"] == ["K5", "K4", "K3"] and len(st3["log"]) == 2
    assert mom.rolling_update(st3, c, meta, "2026-11-30", small)[1] is None


def test_rolling_monthly_universe_filters_members(cfg):
    c = universe_candles(n_coins=5)
    rcfg = dataclasses.replace(cfg, universe=dataclasses.replace(cfg.universe, mode="rolling_monthly"))
    u = mom.select_universe(c, meta_for(c, delisted={"C02"}), rcfg, members=["C03", "C02", "USDT", "C00", "NODATA"])
    assert u == ["C03", "C00"]


def test_config_defaults_and_validation():
    assert config.Universe().compare_rolling is False                     # default kode: mati
    cfg = config.load()
    assert cfg.universe.mode == "static"                                   # buku utama tetap static
    assert (cfg.universe.top_n, cfg.universe.exit_rank) == (150, 200)
    with pytest.raises(ValueError):
        config.from_dict({"universe": {"mode": "rolling_monthly"}})       # bukan untuk buku utama/live
    with pytest.raises(ValueError):
        config.from_dict({"universe": {"top_n": 150, "exit_rank": 100}})


# --------------------------------------------------------------------------- #
#  buku paper pembanding di job harian
# --------------------------------------------------------------------------- #
@pytest.fixture
def info():
    c = universe_candles()
    return FakeInfo(c, meta=meta_for(c), funding=0.00001)


def test_default_off_writes_no_rolling_files(state_dir, cfg, info):
    cfg = dataclasses.replace(cfg, universe=dataclasses.replace(cfg.universe, compare_rolling=False))
    out = jobs.run_momentum(ctx_at(cfg, info, at("2026-10-04")))
    assert "rolling" not in out
    assert not any("rolling" in f for f in os.listdir(state_dir))


def test_second_book_does_not_touch_main_state(state_dir, tmp_path, cfg, info):
    main_files = ("momentum_paper.json", "momentum_view.json", "equity.csv", "orders.csv", "ranking.csv", "alerts.json")
    off = dataclasses.replace(cfg, universe=dataclasses.replace(cfg.universe, compare_rolling=False))
    c_off = ctx_at(off, info, at("2026-10-04"))
    jobs.run_momentum(c_off)
    ref = tmp_path / "ref"
    shutil.copytree(state_dir, ref)
    shutil.rmtree(state_dir)

    rcfg = with_rolling(cfg)
    c_on = ctx_at(rcfg, info, at("2026-10-04"))
    out = jobs.run_momentum(c_on)
    for f in main_files:
        assert (state_dir / f).read_bytes() == (ref / f).read_bytes(), f
    assert out["rolling"] and len(out["rolling"]["positions"]) == 10
    assert store.load_json("momentum_paper_rolling.json")["last_day"] == "2026-10-04"
    assert len(store.read("equity_rolling")) == 1
    assert {o["book"] for o in store.read("orders_rolling")} == {"paper_rolling"}
    assert all(o["book"] == "paper" for o in store.read("orders"))
    # pesan: buku utama sama persis + baris pembanding + baris refresh (refresh pertama)
    off, on = texts(c_off), texts(c_on)
    assert len(off) == len(on) == 1
    extra = [x for x in on[0].splitlines() if x not in off[0].splitlines()]
    assert len(extra) == 2
    assert extra[0].startswith("  pembanding universe bulanan (paper)") and "vs static" in extra[0]
    assert extra[1].startswith("  universe bulanan diperbarui: masuk")
    # siklus berikutnya di hari yang sama: tidak ada apa pun yang berubah
    snap = {f: (state_dir / f).read_bytes() for f in os.listdir(state_dir) if f != "outbox.json"}
    assert jobs.run_momentum(ctx_at(rcfg, info, at("2026-10-04", 0, 22))) is None
    assert snap == {f: (state_dir / f).read_bytes() for f in os.listdir(state_dir) if f != "outbox.json"}


def test_refresh_only_on_first_cycle_of_month(state_dir, cfg):
    rcfg = with_rolling(cfg, top_n=12, exit_rank=16)
    msgs = {}
    for day in ("2026-10-04", "2026-10-05", "2026-11-01"):
        end = str((dt.date.fromisoformat(day) - dt.timedelta(days=1)))
        c = universe_candles(end_day=end)
        for i in range(25):                         # notional per candle tetap; setelah 10-04 dibalik
            df = c[f"C{i:02d}"]
            q = 1e5 * (25 - i) if day == "2026-10-04" else 1e5 * (i + 1)
            df["volume"] = q / ((df["open"] + df["high"] + df["low"] + df["close"]) / 4)
        cx = ctx_at(rcfg, FakeInfo(c, meta=meta_for(c)), at(day))
        jobs.run_momentum(cx)
        msgs[day] = texts(cx)[0]
    u = store.load_json("universe_rolling.json")
    assert [e[0] for e in u["log"]] == ["2026-10-04", "2026-11-01"]
    assert "universe bulanan diperbarui" in msgs["2026-10-04"] and "universe bulanan diperbarui" in msgs["2026-11-01"]
    assert "universe bulanan diperbarui" not in msgs["2026-10-05"]
    assert "pembanding universe bulanan" in msgs["2026-10-05"]
    # 10-04: anggota awal = daftar riset (BTC tetap, peringkat volume 1), masuk C00..C10.
    # 11-01 (volume dibalik, BTC tetap 1): C24..C14 (peringkat 2..12) masuk; C13..C11
    # (13..15) bukan anggota -> tidak masuk; C10 (16) anggota -> tetap; C09..C00 keluar.
    assert u["log"][0][1] == [f"C{i:02d}" for i in range(11)]
    assert u["members"] == ["BTC"] + [f"C{i:02d}" for i in range(24, 13, -1)] + ["C10"]
    assert u["log"][1][2] == [f"C{i:02d}" for i in range(10)]
    assert len(store.read("equity_rolling")) == 3


def test_coin_leaving_universe_is_sold_by_existing_rule(state_dir, cfg, info):
    rcfg = with_rolling(cfg)
    members = [c for c in info.c1d if c != "C00"]                 # C00 = koin terkuat
    store.save_json("universe_rolling.json", {"members": members, "last_refresh": "2026-10-01", "log": []})
    b = bk.new_book(200.0)
    bk.buy(b, "C00", 1.0, info.all_mids()["C00"], rcfg.costs, "2026-10-03T00:02:00+00:00")
    store.save_json("momentum_paper_rolling.json", {"book": b, "bench_index": 1.0, "last_day": "2026-10-03",
                                                    "start_day": "2026-10-03", "static_start_equity": 200.0})
    jobs.run_momentum(ctx_at(rcfg, info, at("2026-10-04")))
    sells = [o for o in store.read("orders_rolling") if o["side"] == "SELL"]
    assert [(o["coin"], o["reason"]) for o in sells] == [("C00", "tidak eligible / keluar universe")]
    assert "C00" not in store.load_json("momentum_paper_rolling.json")["book"]["positions"]
    assert "C00" in store.load_json("momentum_paper.json")["book"]["positions"]   # buku utama tetap


class FailingInfo(FakeInfo):
    def __init__(self, *a, fail=(), **kw):
        super().__init__(*a, **kw)
        self.fail = set(fail)

    def candles(self, coin, interval, start_ms, end_ms=None, include_open=False):
        if coin in self.fail:
            raise TimeoutError("timeout")
        return super().candles(coin, interval, start_ms, end_ms, include_open)


def test_static_main_with_rolling_fetch_failure_is_isolated(state_dir, cfg):
    """Buku utama static (daftar riset); koin di luar daftar gagal diambil ->
    buku pembanding menunggu, buku utama dan alarm tidak terpengaruh."""
    scfg = dataclasses.replace(cfg, universe=dataclasses.replace(cfg.universe, mode="static", compare_rolling=True))
    names = mom.static_universe(scfg)[:30]

    def world(day):
        end = str(dt.date.fromisoformat(day) - dt.timedelta(days=1))
        src = universe_candles(end_day=end, n_coins=30)
        c = {"BTC": src["BTC"], **{n: src[f"C{i:02d}"] for i, n in enumerate(names) if n != "BTC"}}
        c["ZZNEW"] = src["C29"]
        return FailingInfo(c, meta=meta_for(c), fail={"ZZNEW"})

    info = world("2026-10-04")
    cx = ctx_at(scfg, info, at("2026-10-04"))
    out = jobs.run_momentum(cx)
    assert out["paper"] and out["rolling"] is None
    assert len(texts(cx)) == 1 and "pembanding" not in texts(cx)[0] and "🚨" not in texts(cx)[0]
    assert store.load_json("momentum_paper_rolling.json") is None
    # data pulih siang hari: buku BARU tidak dibuat di harga siang, menunggu open berikutnya
    info.fail = set()
    assert jobs.run_momentum(ctx_at(scfg, info, at("2026-10-04", 6, 22))) is None
    assert store.load_json("momentum_paper_rolling.json") is None
    cx = ctx_at(scfg, world("2026-10-05"), at("2026-10-05"))
    cx.info.fail = set()
    assert jobs.run_momentum(cx)["rolling"]["start_day"] == "2026-10-05"
    assert "pembanding universe bulanan" in texts(cx)[0]
    # buku yang SUDAH ada: gagal di open -> dikejar siklus berikutnya, tanpa pesan baru
    info = world("2026-10-06")
    assert jobs.run_momentum(ctx_at(scfg, info, at("2026-10-06")))["rolling"] is None
    info.fail = set()
    cx2 = ctx_at(scfg, info, at("2026-10-06", 0, 22))
    assert jobs.run_momentum(cx2) is None
    st = store.load_json("momentum_paper_rolling.json")
    assert st["last_day"] == "2026-10-06" and len(st["book"]["positions"]) == 10
    assert "ZZNEW" in store.load_json("universe_rolling.json")["members"]
    assert texts(cx2) == [] and len(store.read("equity")) == 3 and len(store.read("equity_rolling")) == 2
