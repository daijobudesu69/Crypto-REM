"""Status TAHAN: posisi RMF ditutup di luar bot (manual, likuidasi, ADL, delisting)
-> Telegram saat itu juga, tidak ada pembelian sampai pemilik mengaktifkan kembali,
jual sesuai aturan tetap jalan. Keputusan pemilik 2026-10-05."""
import dataclasses
import datetime as dt
import os

import yaml

from fakes import FakeInfo, FakeKlines, FakeTrader, universe_candles
from rmf import control, jobs, notify, store

D1 = dt.datetime(2026, 10, 4, 0, 5, tzinfo=dt.timezone.utc)


class AcctInfo(FakeInfo):
    """FakeInfo + clearinghouseState yang membaca posisi bursa tiruan."""
    trader = None

    def clearinghouse(self, user):
        return {"assetPositions": [{"position": {"coin": c, "szi": str(s)}} for c, s in self.trader.pos.items()]}


def setup(cfg):
    lcfg = dataclasses.replace(cfg, execution=dataclasses.replace(
        cfg.execution, master_address="0xM", account_address="0xM", agent_address="0xAGENT",
        agent_valid_until="2027-01-03"))
    full = universe_candles(end_day="2026-10-04")
    info = AcctInfo({k: v[v.ts <= "2026-10-03"].reset_index(drop=True) for k, v in full.items()})
    t = FakeTrader(mids={c: float(df["close"].iloc[-1]) for c, df in full.items()})
    info.trader = t
    return lcfg, info, t, full


def ctx(cfg, info, now, t, mode="live", resume=""):
    return jobs.Ctx(cfg=cfg, info=info, klines=FakeKlines({}),
                    ctrl=control.Control(momentum=mode, flush="off", resume=resume),
                    outbox=notify.Outbox(now), now=now, trader_factory=lambda: t)


def test_manual_close_sets_hold_and_alerts_immediately(state_dir, cfg):
    lcfg, info, t, _ = setup(cfg)
    jobs.run_momentum(ctx(lcfg, info, D1, t))
    a, b = sorted(t.pos)[:2]
    del t.pos[a]                              # tutup manual penuh
    t.pos[b] = t.pos[b] / 2                   # tutup manual sebagian
    c = ctx(lcfg, info, D1 + dt.timedelta(hours=9), t)
    hold = jobs.watch_external_close(c)
    assert hold and set(hold["coins"]) == {a, b}
    msg = [m["text"] for m in c.outbox.sent]
    assert len(msg) == 1 and "ditutup di luar bot" in msg[0] and a in msg[0] and "→" in msg[0]
    ls = store.load_json("momentum_live.json")
    assert a not in ls["positions"] and ls["positions"][b] == t.pos[b]
    # siklus berikutnya: tidak ada pesan ulang
    c2 = ctx(lcfg, info, D1 + dt.timedelta(hours=9, minutes=10), t)
    assert jobs.watch_external_close(c2) and c2.outbox.sent == [] and c2.outbox.items == []


def test_hold_blocks_all_buys_next_day_but_rules_still_sell(state_dir, cfg):
    lcfg, info, t, full = setup(cfg)
    jobs.run_momentum(ctx(lcfg, info, D1, t))
    gone = sorted(t.pos)[0]
    del t.pos[gone]
    jobs.watch_external_close(ctx(lcfg, info, D1 + dt.timedelta(hours=9), t))
    info.c1d = full
    n_buys = sum(1 for s in t.sent if s["is_buy"])
    out = jobs.run_momentum(ctx(lcfg, info, D1 + dt.timedelta(days=1), t))
    lv = out["live"]
    assert sum(1 for s in t.sent if s["is_buy"]) == n_buys          # tidak ada beli
    assert lv["skipped"] and all("TAHAN" in why for _, why in lv["skipped"])
    assert not lv["errors"]
    assert "TAHAN aktif" in jobs._live_message(lv, ctx(lcfg, info, D1, t))


def test_live_rules_still_sell_while_blocked(cfg):
    from rmf import live
    from rmf import momentum as mom
    lcfg, _, _, _ = setup(cfg)
    c = universe_candles()
    view = mom.market_view(c, {k: {"szDecimals": 2, "isDelisted": False} for k in c}, "2026-10-04", lcfg)
    r16 = next(x for x, rk, _ in view.ranking if rk == 16)
    t = FakeTrader(mids={x: 2.0 for x, _, _ in view.ranking}, positions={r16: 5.0})
    r = live.run_momentum(view, lcfg, t, "live", True, D1, owned=frozenset({r16}),
                          block_reason="TAHAN: posisi ditutup di luar bot")
    assert [s["coin"] for s in t.sent] == [r16] and not t.sent[0]["is_buy"]
    assert r["skipped"] and all(w.startswith("TAHAN") for _, w in r["skipped"])


def test_bot_own_sells_do_not_trigger_hold(state_dir, cfg):
    lcfg, info, t, _ = setup(cfg)
    jobs.run_momentum(ctx(lcfg, info, D1, t))
    jobs.run_momentum(ctx(lcfg, info, D1 + dt.timedelta(hours=9), t, mode="flatten"))
    assert t.pos == {}
    c = ctx(lcfg, info, D1 + dt.timedelta(hours=9, minutes=10), t, mode="flatten")
    assert jobs.watch_external_close(c) is None and c.outbox.items == []


def test_resume_releases_hold_once(state_dir, cfg):
    lcfg, info, t, _ = setup(cfg)
    jobs.run_momentum(ctx(lcfg, info, D1, t))
    del t.pos[sorted(t.pos)[0]]
    jobs.watch_external_close(ctx(lcfg, info, D1 + dt.timedelta(hours=9), t))
    c = ctx(lcfg, info, D1 + dt.timedelta(hours=10), t, resume="2026-10-04T10:00Z")
    assert jobs.watch_external_close(c) is None
    assert any("TAHAN dilepas" in m["text"] for m in c.outbox.sent)
    # TAHAN baru setelah itu: nilai resume LAMA tidak melepasnya
    del t.pos[sorted(t.pos)[0]]
    c2 = ctx(lcfg, info, D1 + dt.timedelta(hours=11), t, resume="2026-10-04T10:00Z")
    assert jobs.watch_external_close(c2)


def test_no_live_state_is_noop(state_dir, cfg):
    lcfg, info, t, _ = setup(cfg)
    c = ctx(lcfg, info, D1, t)
    assert jobs.watch_external_close(c) is None and c.outbox.items == []


def test_resume_wired_through_control(tmp_path):
    p = tmp_path / "bot.yaml"
    p.write_text(control.render("live", "paper", "", "2026-10-05T12:00Z"))
    assert control.read((str(p),)).resume == "2026-10-05T12:00Z"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "control.yml"), encoding="utf-8") as fh:
        wf = fh.read()
    doc = yaml.safe_load(wf)
    assert doc.get("on", doc.get(True))["workflow_dispatch"]["inputs"]["resume"]["type"] == "boolean"
    assert "RESUME: ${{ inputs.resume }}" in wf
    with open(os.path.join(root, "tools", "save_control.sh"), encoding="utf-8") as fh:
        assert "--resume" in fh.read()
