"""Satu siklus bot RMF. Dipanggil watcher GitHub Actions tiap ~10 menit,
atau manual / Task Scheduler di PC:   python run_cycle.py

Setiap siklus:
  1. baca control/bot.yaml (mode momentum & flush)
  2. momentum: kalau hari UTC baru sudah mulai dan belum diproses -> buku paper
     (+ live kalau mode live/manage/flatten)
  3. flush: kalau ada candle 4h baru yang close dan belum diproses -> paper
  4. kirim pesan Telegram yang tertunda (outbox), catat state/runs.csv

Exit code 0 = sukses (termasuk "tidak ada yang perlu dikerjakan"), 1 = ada error.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import time
import traceback

from rmf import binance, config, control, hype, jobs, live, notify, store

QUIET_IDLE_MIN = 60     # baris "idle" di runs.csv paling sering 1x per jam


def main(now: dt.datetime | None = None) -> int:
    t0 = time.time()
    now = now or dt.datetime.now(dt.timezone.utc)
    cfg = config.load()
    ctrl = control.read()
    outbox = notify.Outbox(now)
    errors = []

    # Beri tahu sekali saat control/bot.yaml bermasalah atau mode berubah.
    seen = store.load_json("alerts.json", {}) or {}
    if ctrl.problem and seen.get("control_problem") != ctrl.problem:
        outbox.add(f"⚠️ <b>RMF — control/bot.yaml</b>\n{notify.esc(ctrl.problem)}")
    mode_key = f"{ctrl.momentum}/{ctrl.flush}"
    if seen.get("mode") and seen.get("mode") != mode_key:
        outbox.add(f"🔧 <b>RMF — mode sekarang</b>: momentum <b>{ctrl.momentum}</b>, flush <b>{ctrl.flush}</b>")
    if seen.get("control_problem") != ctrl.problem or seen.get("mode") != mode_key:
        seen.update(control_problem=ctrl.problem, mode=mode_key)
        store.save_json("alerts.json", seen)

    key = jobs.agent_key()
    factory = (lambda: live.make_trader(cfg, key)) if key else None
    ctx = jobs.Ctx(cfg=cfg, info=hype.InfoClient(cfg.hype.info_url, cfg.hype.weight_per_minute),
                   klines=binance.KlineClient(cfg.flush.signal_source), ctrl=ctrl, outbox=outbox,
                   now=now, trader_factory=factory)

    res = {}
    for name, fn in (("momentum", jobs.run_momentum), ("flush", jobs.run_flush)):
        try:
            res[name] = fn(ctx)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            msg = f"{name}: {type(e).__name__}: {str(e)[:200]}"
            errors.append(msg)
            _alert_once(outbox, now, f"err_{name}", f"⚠️ <b>RMF — {name} gagal</b>\n<code>{notify.esc(msg)}</code>\n"
                        "<i>Dicoba ulang di siklus berikutnya.</i>")
    live_res = (res.get("momentum") or {}).get("live") or {}
    errors += [f"live: {e}" for e in live_res.get("errors", [])]

    pending = outbox.flush()
    did = {k: bool(v) for k, v in res.items()}
    _log_run(now, ctrl, did, live_res, errors, time.time() - t0)
    if pending:
        print(f"[cycle] {pending} pesan Telegram masih tertahan")
    print(f"[cycle] selesai: momentum={did.get('momentum')} flush={did.get('flush')} errors={len(errors)}")
    return 1 if errors else 0


def _alert_once(outbox, now, key, text, hours=6):
    seen = store.load_json("alerts.json", {}) or {}
    last = seen.get(key)
    if last and (now - dt.datetime.fromisoformat(last)).total_seconds() < hours * 3600:
        return
    outbox.add(text)
    seen[key] = now.isoformat()
    store.save_json("alerts.json", seen)


def _log_run(now, ctrl, did, live_res, errors, dur):
    busy = any(did.values()) or errors
    if not busy and os.environ.get("RMF_QUIET_IDLE") == "1":
        rows = store.read("runs")
        if rows:
            last = dt.datetime.fromisoformat(rows[-1]["time_utc"])
            if (now - last).total_seconds() < QUIET_IDLE_MIN * 60:
                return
    store.append("runs", {"time_utc": now.isoformat(timespec="seconds"),
                          "commit": (os.environ.get("GITHUB_SHA") or "")[:10],
                          "momentum_mode": ctrl.momentum, "flush_mode": ctrl.flush,
                          "momentum": did.get("momentum"), "flush": did.get("flush"),
                          "live": bool(live_res), "errors": " | ".join(errors)[:500],
                          "duration_s": round(dur, 1)}, mirror=False)


if __name__ == "__main__":
    sys.exit(main())
