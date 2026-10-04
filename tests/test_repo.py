"""Konsistensi repo: config, control, workflow, dan aturan keamanan yang mudah rusak diam-diam."""
import os
import re

import pytest
import yaml

from rmf import config, control

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def wf(name):
    with open(os.path.join(ROOT, ".github", "workflows", name), encoding="utf-8") as fh:
        return fh.read()


def test_config_matches_handover():
    cfg = config.load()
    assert cfg.universe.mode == "static" and cfg.stop_rules.six_month_floor_pct == -12.5
    assert cfg.benchmark.include_funding
    m, f = cfg.momentum, cfg.flush
    assert (m.n_hold, m.exit_rank, m.lookback_days, m.min_history_days, m.regime_ema) == (10, 15, 14, 60, 50)
    assert (m.gross_exposure, m.min_order_usdc) == (0.5, 10)
    assert (f.min_coins, f.max_coins, f.sl_atr, f.tp_atr, f.max_bars) == (10, 15, 2.0, 2.0, 48)
    assert (f.risk_pct, f.max_event_risk_pct, f.reject_forced_risk_x, f.gross_cap_x) == (0.5, 8.0, 2.0, 2.0)
    assert cfg.capital_usdc == 200 and cfg.stop_rules.max_drawdown_pct == 40
    assert cfg.execution.margin_mode == "cross"


def test_unknown_config_key_rejected():
    with pytest.raises(ValueError):
        config.from_dict({"momentum": {"exit_rnak": 20}})
    with pytest.raises(ValueError):
        config.from_dict({"execution": {"margin_mode": "isolated", "leverage": 5}})


def test_agent_secret_name_matches_workflow(cfg):
    assert f"secrets.{cfg.execution.agent_secret}" in wf("bot.yml")


def test_watcher_loop_guards_every_command():
    """bash -e: exit non-nol tanpa penjaga mengakhiri job sebelum state disimpan."""
    body = wf("bot.yml").split("while :; do", 1)[1].split("done", 1)[0]
    for line in body.splitlines():
        s = line.strip()
        if re.match(r"^(RMF_AGENT_KEY=.*)?(timeout|python|bash)\b", s) and not s.startswith("if "):
            assert "||" in s, f"perintah tanpa penjaga: {s}"


def test_default_control_is_paper():
    c = control.read((os.path.join(ROOT, "control", "bot.yaml"),))
    assert (c.momentum, c.flush, c.problem) == ("paper", "paper", None)


def test_control_off_unquoted_and_garbage(tmp_path):
    p = tmp_path / "bot.yaml"
    p.write_text("momentum: off\nflush: off\n")
    c = control.read((str(p),))
    assert (c.momentum, c.flush) == ("off", "off")
    p.write_text("momentum: yolo\n")
    c = control.read((str(p),))
    assert c.momentum == "paper" and c.problem
    p.write_text("::: not yaml [")
    assert control.read((str(p),)).momentum == "paper"


def test_control_render_roundtrip(tmp_path):
    p = tmp_path / "bot.yaml"
    p.write_text(control.render("live", "off", "2026-10-04T00:00Z"))
    c = control.read((str(p),))
    assert (c.momentum, c.flush, c.breaker_reset) == ("live", "off", "2026-10-04T00:00Z")


def test_control_workflow_options_match_modes():
    doc = yaml.safe_load(wf("control.yml"))
    inputs = doc[True]["workflow_dispatch"]["inputs"] if True in doc else doc["on"]["workflow_dispatch"]["inputs"]
    assert set(inputs["momentum"]["options"]) - {"tetap"} == set(control.MOMENTUM_MODES)
    assert set(inputs["flush"]["options"]) - {"tetap"} == set(control.FLUSH_MODES)


def test_static_universe_is_research_list():
    from rmf import momentum as mom
    u = mom.static_universe(config.load())
    assert len(u) == 150 and len(set(u)) == 150 and u[:3] == ["BTC", "ETH", "HYPE"]
    assert "INIT" in u and "kPEPE" in u


def test_spot_universe_file(cfg):
    with open(config.path_in_repo(cfg.flush.spot_universe_file), encoding="utf-8") as fh:
        syms = [x.strip() for x in fh if x.strip() and not x.startswith("#")]
    assert len(syms) == 150 and all(s.endswith("USDT") for s in syms)


def test_no_secret_values_in_repo():
    pat = re.compile(r"0x[0-9a-fA-F]{64}")
    for d, _, files in os.walk(ROOT):
        if any(x in d for x in (".git", "research", "reports", "__pycache__", ".pytest_cache")):
            continue
        for f in files:
            if f.endswith((".py", ".yml", ".yaml", ".md", ".json", ".txt", ".sh")):
                with open(os.path.join(d, f), encoding="utf-8", errors="ignore") as fh:
                    assert not pat.search(fh.read()), f"kemungkinan private key di {f}"
