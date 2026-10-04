"""State JSON dan log CSV di folder state/ (di-commit ke repo oleh workflow).

* JSON ditulis atomik (file sementara lalu rename): job yang mati di tengah
  penulisan tidak boleh meninggalkan file setengah jadi.
* CSV append-only. .gitattributes memakai merge=union untuk state/*.csv, jadi
  dua run yang menambah baris bersamaan tidak bentrok saat rebase.
* Setiap baris CSV juga dicerminkan ke Google Sheets kalau dikonfigurasi
  (lihat rmf/sheets.py). Gagal mirror tidak pernah menggagalkan run.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile

from . import sheets
from .config import ROOT

STATE_DIR = os.environ.get("RMF_STATE_DIR") or os.path.join(ROOT, "state")

# Kolom tetap per log. Menambah kolom: tambahkan di AKHIR (file lama dirotasi otomatis).
COLUMNS = {
    "runs": ["time_utc", "commit", "momentum_mode", "flush_mode", "momentum", "flush", "live",
             "errors", "duration_s"],
    "orders": ["time_utc", "book", "strategy", "exec_day", "coin", "side", "qty", "px", "mid",
               "notional", "fee", "pnl", "reason", "status"],
    "equity": ["exec_day", "time_utc", "regime_on", "btc_close", "btc_ema", "paper_equity",
               "paper_gross", "paper_positions", "live_equity", "live_positions", "flush_equity",
               "bench_ret", "bench_index", "paper_peak", "paper_dd_pct", "delay_min", "live_gross"],
    "ranking": ["exec_day", "rank", "coin", "ret_14d_pct", "held_paper", "held_live"],
    "flush_signals": ["bar_utc", "time_utc", "n_signals", "n_symbols", "event", "coins"],
    "flush_trades": ["entry_time", "exit_time", "coin", "signal_bar", "entry_px", "exit_px", "stop",
                     "target", "qty", "notional", "risk_usd", "forced_min", "bars_held", "reason",
                     "pnl_gross", "fees", "funding", "pnl_net", "r_multiple"],
}
# Log yang dicerminkan ke Sheets (runs tidak: terlalu sering).
MIRROR = {"orders", "equity", "flush_trades", "flush_signals"}


def path(name: str) -> str:
    return os.path.join(STATE_DIR, name)


def load_json(name: str, default=None):
    p = path(name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save_json(name: str, data) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=STATE_DIR, prefix=".tmp_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True, default=str)
        fh.write("\n")
    os.replace(tmp, path(name))


def _rotate_if_needed(p: str, cols: list) -> None:
    if not os.path.exists(p):
        return
    with open(p, encoding="utf-8", newline="") as fh:
        head = next(csv.reader(fh), None)
    if head and head != cols:
        base, ext = os.path.splitext(p)
        i = 1
        while os.path.exists(f"{base}.v{i}{ext}"):
            i += 1
        os.replace(p, f"{base}.v{i}{ext}")


def append(log: str, row: dict, mirror: bool = True) -> None:
    cols = COLUMNS[log]
    os.makedirs(STATE_DIR, exist_ok=True)
    p = path(f"{log}.csv")
    _rotate_if_needed(p, cols)
    new = not os.path.exists(p)
    clean = {k: _fmt(row.get(k)) for k in cols}
    with open(p, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow(clean)
    if mirror and log in MIRROR:
        sheets.append(log, cols, clean)


def read(log: str) -> list[dict]:
    p = path(f"{log}.csv")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, float):
        return round(v, 8)
    return v
