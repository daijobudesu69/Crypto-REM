"""Tulis ulang control/bot.yaml. Dipanggil tools/save_control.sh (workflow control.yml).

    python tools/set_control.py --momentum live
    python tools/set_control.py --flush off
    python tools/set_control.py --reset-breaker
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmf import control  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--momentum", default="tetap")
    ap.add_argument("--flush", default="tetap")
    ap.add_argument("--reset-breaker", action="store_true")
    a = ap.parse_args()
    cur = control.read((control.PATH,))
    m = cur.momentum if a.momentum == "tetap" else a.momentum
    f = cur.flush if a.flush == "tetap" else a.flush
    if m not in control.MOMENTUM_MODES or f not in control.FLUSH_MODES:
        print(f"[control] mode tidak dikenal: momentum={m} flush={f}")
        return 2
    reset = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ") if a.reset_breaker else cur.breaker_reset
    os.makedirs(os.path.dirname(control.PATH), exist_ok=True)
    with open(control.PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(control.render(m, f, reset))
    print(f"[control] momentum={m} flush={f}" + (" breaker direset" if a.reset_breaker else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
