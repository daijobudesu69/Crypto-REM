"""Canary RMF (rmf/canary.py, run_canary.py, canary.yml) terhadap bursa tiruan."""
import dataclasses
import datetime as dt
import os

import yaml

from fakes import FakeTrader
from rmf import canary, config, control, live

NOW = dt.datetime(2026, 10, 5, 13, 0, tzinfo=dt.timezone.utc)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ccfg():
    c = config.load()
    return dataclasses.replace(c, execution=dataclasses.replace(
        c.execution, master_address="0xM", account_address="0xM", agent_address="0xAGENT",
        agent_valid_until="2027-01-03"))


class CanaryTrader(FakeTrader):
    """Bursa tiruan dengan saldo unified: fee 0,045% dipotong dari spot USDC."""

    def __init__(self, usdc=200.0, fail=None, equity_bug=False, **kw):
        super().__init__(mids={"ETH": 4000.0}, sz_decimals=4, **kw)
        self.usdc, self.fail, self.equity_bug = usdc, fail, equity_bug

    def equity_parts(self):
        open_ntl = sum(abs(s) * self._mids[c] for c, s in self.pos.items())
        return {"abstraction": "unifiedAccount",
                # equity_bug: perp state memuat sesuatu yang bukan ekuitas (mis. margin)
                "perp_account_value": open_ntl if self.equity_bug else 0.0,
                "spot_usdc": self.usdc, "spot_usdc_hold": open_ntl, "upnl": 0.0}

    def market(self, coin, is_buy, sz, mid, slippage, reduce_only=False, cloid_hex=None):
        if self.fail == ("buy" if is_buy else "sell"):
            self.sent.append({"coin": coin, "is_buy": is_buy, "sz": sz, "reduce_only": reduce_only, "cloid": cloid_hex})
            return {"error": "Order could not immediately match"}
        self.usdc -= sz * mid * 0.00045
        return super().market(coin, is_buy, sz, mid, slippage, reduce_only, cloid_hex)


def test_happy_path_buys_then_sells_and_reports_all_steps():
    t = CanaryTrader()
    rep = canary.run(t, ccfg(), "ETH", NOW)
    assert rep.ok, rep.steps
    assert t.pos == {}
    buy, sell = t.sent
    assert buy["is_buy"] and not buy["reduce_only"] and buy["sz"] * 4000 >= 10.0
    assert not sell["is_buy"] and sell["reduce_only"] and sell["sz"] == buy["sz"]
    assert all(live.is_bot_cloid(s["cloid"]) for s in t.sent)
    assert len({s["cloid"] for s in t.sent}) == 2
    assert t.lev == [("ETH", 1, True)]                          # cross 1x, sama dengan live
    assert any("posisi terbuka" in x for x in rep.info)
    assert "CANARY OK" in canary.message(rep)


def test_existing_position_refused_without_orders():
    t = CanaryTrader(positions={"ETH": 0.01})
    rep = canary.run(t, ccfg(), "ETH", NOW)
    assert not rep.ok and t.sent == []


def test_wrong_agent_refused_without_orders():
    t = CanaryTrader(agent="0xOTHER")
    rep = canary.run(t, ccfg(), "ETH", NOW)
    assert not rep.ok and t.sent == [] and t.lev == []


def test_failed_sell_is_cleaned_up_and_reported():
    t = CanaryTrader(fail="sell")
    rep = canary.run(t, ccfg(), "ETH", NOW)
    assert not rep.ok
    names = [n for n, ok, _ in rep.steps if not ok]
    assert any("jual reduce-only" in n for n in names)
    assert t.pos != {}               # tiruan tetap menolak jual -> pembersihan juga gagal & dilaporkan
    assert any("pembersihan" in n for n in names)
    assert "CANARY GAGAL" in canary.message(rep)


def test_failed_buy_reported_no_position():
    t = CanaryTrader(fail="buy")
    rep = canary.run(t, ccfg(), "ETH", NOW)
    assert not rep.ok and t.pos == {}
    assert any(ok for n, ok, _ in rep.steps if "tidak ada posisi canary tersisa" in n)


def test_equity_reading_error_is_caught():
    """Kalau perp state ternyata ikut terbaca (mode tidak unified), ekuitas melenceng -> GAGAL."""
    class Default(CanaryTrader):
        def equity_parts(self):
            p = super().equity_parts()
            p["abstraction"] = "default"            # cara baca perp accountValue
            return p
    t = Default(equity_bug=True)
    rep = canary.run(t, ccfg(), "ETH", NOW)
    assert not rep.ok
    assert any("ekuitas" in n and not ok for n, ok, _ in rep.steps)


def test_driver_refuses_while_live_and_bad_key(monkeypatch):
    import run_canary
    sent = []
    monkeypatch.setattr(run_canary.notify, "send_now", lambda t: sent.append(t) or True)
    monkeypatch.setattr(run_canary.control, "read", lambda: control.Control(momentum="live"))
    assert run_canary.main(["ETH"]) == 2 and "tidak dijalankan" in sent[-1]
    monkeypatch.setattr(run_canary.control, "read", lambda: control.Control(momentum="paper"))
    monkeypatch.setenv("RMF_AGENT_KEY", "0x1234")
    assert run_canary.main(["ETH"]) == 2 and "66" in sent[-1]


def test_workflow_uses_agent_secret_and_hides_key():
    cfg = config.load()
    with open(os.path.join(ROOT, ".github", "workflows", "canary.yml"), encoding="utf-8") as fh:
        wf = fh.read()
    assert f"secrets.{cfg.execution.agent_secret}" in wf
    assert "unset KEY_IN" in wf
    doc = yaml.safe_load(wf)
    assert "workflow_dispatch" in doc.get("on", doc.get(True))          # manual saja
    assert "schedule" not in doc.get("on", doc.get(True))
