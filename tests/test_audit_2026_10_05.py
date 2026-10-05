"""Tes regresi audit infrastruktur 2026-10-05 (docs/audit/AUDIT_2026-10-05.md).

Setiap tes memakai nomor temuan (F1..F8) supaya bisa ditelusuri dari laporan.
"""
import dataclasses
import datetime as dt
import re

import pandas as pd
import pytest

from fakes import FakeInfo, FakeKlines, FakeTrader, meta_for, universe_candles
from rmf import config, control, jobs, live, notify, store
from rmf import momentum as mom

D1 = dt.datetime(2026, 10, 4, 0, 12, tzinfo=dt.timezone.utc)


def ctx_at(cfg, info, now, momentum="paper", factory=None, kl=None):
    return jobs.Ctx(cfg=cfg, info=info, klines=kl or FakeKlines({}),
                    ctrl=control.Control(momentum=momentum, flush="off"),
                    outbox=notify.Outbox(now), now=now, trader_factory=factory)


def live_cfg(cfg, **kw):
    ex = dataclasses.replace(cfg.execution, master_address="0xM", account_address="0xM",
                             agent_address="0xAGENT", agent_valid_until="2027-01-03", **kw)
    return dataclasses.replace(cfg, execution=ex)


def two_day_world():
    """Hari 1 (4 Okt) memakai candle s/d 3 Okt; hari 2 (5 Okt) s/d 4 Okt."""
    full = universe_candles(end_day="2026-10-04")
    day1 = {k: v[v.ts <= "2026-10-03"].reset_index(drop=True) for k, v in full.items()}
    return full, day1


def flaky(info, victim):
    real = info.candles

    def candles(coin, *a, **k):
        if coin == victim:
            raise RuntimeError("timeout")
        return real(coin, *a, **k)
    return candles


# --------------------------------------------------------------------------- #
#  F1 — candle satu koin gagal tidak boleh menjual posisinya
# --------------------------------------------------------------------------- #
def test_f1_fetch_failure_retries_instead_of_selling(state_dir, cfg):
    full, day1 = two_day_world()
    info = FakeInfo(day1)
    held = jobs.run_momentum(ctx_at(cfg, info, D1))["paper"]["positions"]
    victim = held[0]
    info.c1d = full
    info.candles = flaky(info, victim)
    d2 = D1 + dt.timedelta(days=1)
    with pytest.raises(jobs.DataIncomplete, match=victim):
        jobs.run_momentum(ctx_at(cfg, info, d2))
    paper = store.load_json("momentum_paper.json")
    assert victim in paper["book"]["positions"] and paper["last_day"] == "2026-10-04"   # tidak trading

    # data pulih di siklus berikutnya -> hari 2 jalan normal, posisi tidak dijual karena data
    info.candles = FakeInfo(full).candles
    out = jobs.run_momentum(ctx_at(cfg, info, d2 + dt.timedelta(minutes=10)))
    assert not any(f["coin"] == victim and "tidak eligible" in f["reason"] for f in out["paper"]["fills"])


def test_f1_gives_up_after_retry_window_with_alarm(state_dir, cfg):
    full, day1 = two_day_world()
    info = FakeInfo(day1)
    victim = jobs.run_momentum(ctx_at(cfg, info, D1))["paper"]["positions"][0]
    info.c1d = full
    info.candles = flaky(info, victim)
    late = dt.datetime(2026, 10, 5, jobs.FETCH_RETRY_UNTIL_H, 0, 1, tzinfo=dt.timezone.utc)
    c = ctx_at(cfg, info, late)
    out = jobs.run_momentum(c)
    assert out["paper"] is not None                         # perilaku lama setelah batas waktu
    assert any("data candle tidak lengkap" in m["text"] for m in c.outbox.sent + c.outbox.items)


def test_f1_btc_failure_still_raises_immediately(state_dir, cfg):
    info = FakeInfo(universe_candles())
    info.candles = flaky(info, "BTC")
    with pytest.raises(RuntimeError, match="timeout"):
        jobs.run_momentum(ctx_at(cfg, info, D1))


# --------------------------------------------------------------------------- #
#  F2 — order beli yang timeout tapi terisi tetap milik RMF
# --------------------------------------------------------------------------- #
class TimeoutAfterFill(FakeTrader):
    victim = None

    def market(self, coin, is_buy, sz, mid, slippage, reduce_only=False, cloid_hex=None):
        r = super().market(coin, is_buy, sz, mid, slippage, reduce_only, cloid_hex)
        if is_buy and coin == self.victim:
            raise TimeoutError("read timeout")          # terisi di bursa, respons hilang
        return r


def test_f2_timed_out_fill_stays_owned(state_dir, cfg):
    lcfg = live_cfg(cfg)
    info = FakeInfo(universe_candles())
    t = TimeoutAfterFill(mids=info.all_mids())
    view = mom.market_view(info.c1d, meta_for(info.c1d), "2026-10-04", lcfg)
    t.victim = view.ranking[0][0]
    out = jobs.run_momentum(ctx_at(lcfg, info, D1, momentum="live", factory=lambda: t))
    assert any("TimeoutError" in e for e in out["live"]["errors"])
    ls = store.load_json("momentum_live.json")
    assert t.victim in t.pos and t.victim in ls["positions"]
    # percobaan ulang hari yang sama: tidak HALT, tidak beli dobel
    out2 = jobs.run_momentum(ctx_at(lcfg, info, D1 + dt.timedelta(minutes=10), momentum="live",
                                    factory=lambda: t))
    assert not any("HALT" in e for e in out2["live"]["errors"])
    assert sum(1 for s in t.sent if s["coin"] == t.victim and s["is_buy"]) == 1


def test_f2_really_failed_buy_not_owned(cfg):
    lcfg = live_cfg(cfg)
    c = universe_candles()
    view = mom.market_view(c, meta_for(c), "2026-10-04", lcfg)
    top = view.ranking[0][0]
    t = FakeTrader(mids={x: 2.0 for x, _, _ in view.ranking}, fail_buy={top})
    r = live.run_momentum(view, lcfg, t, "live", False, D1)
    assert top not in r["positions_after"] and len(r["positions_after"]) == 9


# --------------------------------------------------------------------------- #
#  F3 — pesan yang ditolak permanen tidak menahan antrean
# --------------------------------------------------------------------------- #
class Resp:
    def __init__(self, code):
        self.status_code = code


def tg(monkeypatch, responder):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    calls = []

    def post(url, timeout, json):
        calls.append(json)
        return Resp(responder(json))
    monkeypatch.setattr(notify.requests, "post", post)
    return calls


def test_f3_bad_html_falls_back_to_plain_text(state_dir, monkeypatch):
    calls = tg(monkeypatch, lambda j: 400 if j.get("parse_mode") else 200)
    assert notify.send_now("<b>rusak & <i>x</b>")
    assert calls[-1]["text"] == "rusak & x" and "parse_mode" not in calls[-1]


def test_f3_permanent_400_dropped_alarm_behind_it_delivered(state_dir, monkeypatch):
    calls = tg(monkeypatch, lambda j: 400 if "BAD" in j["text"] else 200)
    ob = notify.Outbox(dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc))
    ob.add("BAD")
    ob.add("ALARM DD")
    assert ob.flush() == 0
    assert calls[-1]["text"] == "ALARM DD"


def test_f3_transient_errors_still_retried(state_dir, monkeypatch):
    tg(monkeypatch, lambda j: 429)
    ob = notify.Outbox(dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc))
    ob.add("ALARM DD")
    assert ob.flush() == 1 and store.load_json("outbox.json")[0]["text"] == "ALARM DD"


# --------------------------------------------------------------------------- #
#  F4 + blokir MEX — cek akun harian di run_cycle
# --------------------------------------------------------------------------- #
class AgentsInfo:
    def __init__(self, agents):
        self.agents, self.n = agents, 0

    def post(self, body, weight=20, per_items=None, retries=6):
        assert body["type"] == "extraAgents"
        self.n += 1
        return self.agents


MEX = "0x329e707a50b77bd851d220d53efab0491960e797"


def test_f4_agent_expiry_and_blocked_agent_alarm_once_per_day(state_dir, cfg):
    import run_cycle
    c = dataclasses.replace(cfg, execution=dataclasses.replace(
        cfg.execution, agent_valid_until="2026-10-15", blocked_agents=(MEX,)))
    info = AgentsInfo([{"name": "MEX.bot", "address": MEX}, {"name": "RMF.bot", "address": "0x8551"}])
    now = dt.datetime(2026, 10, 5, 0, 5, tzinfo=dt.timezone.utc)
    ctx = ctx_at(c, info, now)
    run_cycle._account_checks(ctx)
    texts = [m["text"] for m in ctx.outbox.items]
    assert any("kedaluwarsa 10 hari lagi" in t for t in texts)
    assert any("MEX.bot" in t for t in texts) and not any("RMF.bot" in t for t in texts)
    ctx2 = ctx_at(c, info, now + dt.timedelta(minutes=10))
    run_cycle._account_checks(ctx2)
    assert ctx2.outbox.items == [] and info.n == 1           # sekali per hari UTC


def test_f4_quiet_when_far_from_expiry_and_no_blocked_agent(state_dir, cfg):
    import run_cycle
    c = dataclasses.replace(cfg, execution=dataclasses.replace(cfg.execution, blocked_agents=(MEX,)))
    ctx = ctx_at(c, AgentsInfo([{"name": "RMF.bot", "address": c.execution.agent_address}]),
                 dt.datetime(2026, 10, 5, 0, 5, tzinfo=dt.timezone.utc))
    run_cycle._account_checks(ctx)
    assert ctx.outbox.items == []


def test_repo_config_blocks_mex_agent():
    cfg = config.load()
    assert MEX in [a.lower() for a in cfg.execution.blocked_agents]
    assert cfg.execution.agent_address.lower() not in [a.lower() for a in cfg.execution.blocked_agents]


# --------------------------------------------------------------------------- #
#  F5 — ekuitas mode unified
# --------------------------------------------------------------------------- #
def parts(mode, av, usdc, upnl):
    return {"abstraction": mode, "perp_account_value": av, "spot_usdc": usdc, "spot_usdc_hold": 0.0,
            "upnl": upnl}


def test_f5_unified_ignores_perp_account_value():
    eq, how = live.equity_from_parts(parts("unifiedAccount", 37.0, 200.0, -3.0))
    assert eq == 200.0 and "spot" in how                 # spot sudah memuat uPnL
    assert live.equity_from_parts(parts("portfolioMargin", 5.0, 100.0, 1.0))[0] == 100.0


def test_f5_matches_real_canary_2026_10_05():
    """Angka asli canary di akun RMF (0,11 HYPE @ 92,176, fee 0,004562 per sisi).
    Saat posisi terbuka perp accountValue = margin (10,13925), dan spot USDC sudah
    turun sebesar fee + |uPnL|. Ekuitas yang benar = spot saja."""
    before = parts("unifiedAccount", 0.0, 127.521479, 0.0)
    opened = parts("unifiedAccount", 10.13925, 127.516807, -0.00011)
    after = parts("unifiedAccount", 0.0, 127.512245, 0.0)
    fee = 0.004562
    e0, e1, e2 = (live.equity_from_parts(x)[0] for x in (before, opened, after))
    assert abs((e0 - e1) - (fee + 0.00011)) < 1e-9             # = fee + kerugian belum terealisasi
    assert abs(e2 - (e0 - 2 * fee - 0.00011)) < 1e-9           # = closedPnl -0,00011
    assert abs(e1 - 127.516807) < 1e-12


def test_f5_standard_and_unknown_modes():
    assert live.equity_from_parts(parts("default", 210.0, 0.0, 5.0)) == (210.0, "perp accountValue (default)")
    assert live.equity_from_parts(parts(None, 0.0, 127.5, 0.0))[0] == 127.5
    assert live.equity_from_parts(parts(None, 50.0, 127.5, 0.0))[0] == 50.0


# --------------------------------------------------------------------------- #
#  F6 — siklus terakhir watcher selesai sebelum timeout job
# --------------------------------------------------------------------------- #
def test_f6_last_cycle_fits_job_timeout():
    import os
    with open(os.path.join(config.ROOT, ".github", "workflows", "bot.yml"), encoding="utf-8") as fh:
        wf = fh.read()
    timeout_min = int(re.search(r"timeout-minutes:\s*(\d+)", wf).group(1))
    cycle_s = int(re.search(r"timeout -k (\d+) (\d+) python run_cycle.py", wf).group(2))
    kill_s = int(re.search(r"timeout -k (\d+) ", wf).group(1))
    budget = int(re.search(r"CYCLE_BUDGET=\$\(\( (\d+) \+ (\d+) \+ (\d+) \)\)", wf).group(0).split("(( ")[1]
                 .split(" ))")[0].replace(" ", "").split("+")[0])
    assert budget >= cycle_s
    m = re.search(r"DEADLINE=\$\(\( \$\(date \+%s\) \+ (\d+)\*60 - CYCLE_BUDGET \)\)", wf)
    assert m, "DEADLINE harus memperhitungkan CYCLE_BUDGET"
    assert int(m.group(1)) + 5 <= timeout_min                 # sisa >= 5 menit untuk checkout/pip
    assert cycle_s + kill_s <= 1500 + 30 + 120


# --------------------------------------------------------------------------- #
#  F7 — catatan hari kemarin yang terputus tidak tertimpa hari baru
# --------------------------------------------------------------------------- #
def test_f7_stale_pending_record_finished_before_new_day(state_dir, cfg, monkeypatch):
    full, day1 = two_day_world()
    info = FakeInfo(day1)
    real = jobs._record_day
    monkeypatch.setattr(jobs, "_record_day", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("mati")))
    with pytest.raises(RuntimeError):
        jobs.run_momentum(ctx_at(cfg, info, D1))
    assert store.load_json("momentum_paper.json")["pending_record"]["exec_day"] == "2026-10-04"
    monkeypatch.setattr(jobs, "_record_day", real)
    info.c1d = full
    jobs.run_momentum(ctx_at(cfg, info, D1 + dt.timedelta(days=1)))   # siklus berikutnya = hari baru
    days = [r["exec_day"] for r in store.read("equity")]
    assert days == ["2026-10-04", "2026-10-05"]
    assert store.load_json("momentum_paper.json").get("pending_record") is None


# --------------------------------------------------------------------------- #
#  F8 — run_status menilai flush di bar yang diminta
# --------------------------------------------------------------------------- #
def test_f8_run_status_uses_requested_bar():
    import run_status
    bar = pd.Timestamp("2026-10-04 16:00", tz="UTC")
    ts = pd.date_range(end=bar + pd.Timedelta(hours=4), periods=30, freq="4h")
    df = pd.DataFrame({"ts": ts, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0})
    ctx = type("C", (), {"klines": FakeKlines({"XUSDT": df})})()
    k = run_status._k(ctx, "XUSDT", bar)
    assert k is not None and pd.Timestamp(k["ts"].iloc[-1]) == bar
