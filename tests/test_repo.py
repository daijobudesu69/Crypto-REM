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


def test_all_workflows_are_valid_yaml():
    d = os.path.join(ROOT, ".github", "workflows")
    for f in os.listdir(d):
        doc = yaml.safe_load(wf(f))
        assert doc.get("name") and doc.get("jobs"), f
        on = doc.get("on", doc.get(True))
        assert "workflow_dispatch" in on, f"{f}: tanpa workflow_dispatch"


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


def test_watcher_wakes_right_after_candle_close(cfg):
    """Potongan bash watcher dijalankan dengan jam tiruan: bangun 2m10s setelah close 4h."""
    import datetime as dt
    import shutil
    import subprocess
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash tidak ada")
    body = wf("bot.yml")
    snip = body[body.index("            now=$(date +%s)"):body.index('            if [ $(( now + nap )) -ge "$DEADLINE" ]')]
    assert cfg.momentum.run_after_minutes * 60 < 130          # bangun setelah jeda run_after habis

    def nap_at(hhmmss):
        t = int(dt.datetime.fromisoformat(f"2026-10-05T{hhmmss}+00:00").timestamp())
        script = "INTERVAL=600\n" + snip.replace("now=$(date +%s)", f"now={t}") + 'echo "$nap"\n'
        return int(subprocess.run([bash, "-c", script], capture_output=True, text=True, check=True).stdout.strip())

    assert nap_at("23:55:00") == 430        # -> 00:02:10 UTC (07:02:10 WIB), bukan 00:05
    assert nap_at("00:00:16") == 114        # kasus 5 Okt: dulu menunggu sampai 00:10
    assert nap_at("00:02:30") == 600        # sudah lewat: kembali ke interval 10 menit
    assert nap_at("10:00:00") == 600
    assert nap_at("11:57:00") == 310        # candle 4h 12:00 -> 12:02:10


def test_watcher_dispatches_its_successor_only_in_loop_mode(tmp_path):
    """Cron di repo ini hanya terpicu tiap 3-6 jam: watcher loop yang anggaran
    waktunya habis harus menyalakan penggantinya sendiri (gh workflow run)."""
    import shutil
    import subprocess
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash tidak ada")
    body = wf("bot.yml")
    doc = yaml.safe_load(body)
    assert doc["permissions"].get("actions") == "write"
    assert "GH_TOKEN_IN: ${{ secrets.GITHUB_TOKEN }}" in body and "unset GH_TOKEN_IN" in body
    tail = body[body.index('          if [ "${MODE}" = "loop" ] && [ "$chain" = "1" ]'):
                body.index('          echo "[watch] selesai setelah')]
    fake = tmp_path / "gh"
    fake.write_text('#!/usr/bin/env bash\necho "GH $GH_TOKEN $*"\n', newline="\n")
    fake.chmod(0o755)

    d = tmp_path.as_posix()
    if re.match(r"^[A-Za-z]:/", d):                         # Git Bash di Windows: C:/x -> /c/x
        d = "/" + d[0].lower() + d[2:]

    def run(mode, chain):
        script = f'export PATH="{d}:$PATH"\nMODE={mode}\nchain={chain}\ngh_token=tok\n' \
                 'GITHUB_REPOSITORY=o/r\nGITHUB_REF_NAME=main\n' + tail
        return subprocess.run([bash, "-c", script], capture_output=True, text=True, check=True).stdout

    out = run("loop", 1)
    assert "GH tok workflow run bot.yml --repo o/r --ref main -f mode=loop" in out
    assert "GH " not in run("once", 0) and "GH " not in run("loop", 0)
