"""Watchdog: alarm kalau watcher (bot.yml) berhenti mencatat, dan nyalakan yang baru.

Cron GitHub tidak andal (di Crypto-MEX hanya ~25% jadwal yang benar-benar
jalan), dan watcher pernah mati ~15 jam tanpa ada yang tahu. Watchdog membaca
waktu baris terakhir state/runs.csv (watcher menulis minimal 1x per jam):
  > STALE_MIN menit -> kirim alarm (maks 1x per 3 jam), dan kalau tidak ada run
  bot.yml yang sedang jalan/antre, dispatch run baru lewat GitHub API.

Env: GITHUB_TOKEN, GITHUB_REPOSITORY (otomatis di Actions), TELEGRAM_*.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import requests

from rmf import notify, store

STALE_MIN = 90
ALERT_EVERY_H = 3
WORKFLOW = "bot.yml"


def last_run(now: dt.datetime) -> dt.datetime | None:
    rows = store.read("runs")
    if not rows:
        return None
    return dt.datetime.fromisoformat(rows[-1]["time_utc"])


def gh(method: str, path: str, **kw):
    repo = os.environ["GITHUB_REPOSITORY"]
    tok = os.environ["GITHUB_TOKEN"]
    return requests.request(method, f"https://api.github.com/repos/{repo}{path}", timeout=20,
                            headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}, **kw)


def watcher_active() -> bool | None:
    try:
        n = 0
        for status in ("in_progress", "queued"):
            r = gh("GET", f"/actions/workflows/{WORKFLOW}/runs", params={"status": status, "per_page": 5})
            r.raise_for_status()
            n += r.json().get("total_count", 0)
        return n > 0
    except Exception as e:  # noqa: BLE001
        print(f"[watchdog] tidak bisa membaca status run ({type(e).__name__})")
        return None


def dispatch() -> bool:
    try:
        r = gh("POST", f"/actions/workflows/{WORKFLOW}/dispatches",
               json={"ref": os.environ.get("GITHUB_REF_NAME", "main"), "inputs": {"mode": "loop"}})
        return r.status_code == 204
    except Exception as e:  # noqa: BLE001
        print(f"[watchdog] dispatch gagal ({type(e).__name__})")
        return False


def main(now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    st = store.load_json("watchdog.json", {}) or {}
    last = last_run(now)
    age = None if last is None else (now - last).total_seconds() / 60
    print(f"[watchdog] baris runs.csv terakhir: {last} ({'-' if age is None else f'{age:.0f} menit lalu'})")
    if age is not None and age <= STALE_MIN:
        # Sehat: file hanya ditulis saat status berubah, supaya tidak ada commit tiap 15 menit.
        if st.get("stale_since"):
            notify.send_now(f"✅ <b>RMF watcher hidup lagi</b> (mati sejak {notify.wib(st['stale_since'])})")
            store.save_json("watchdog.json", {})
        return 0
    st.setdefault("stale_since", (last or now).isoformat())
    active = watcher_active() if os.environ.get("GITHUB_TOKEN") else None
    action = "watcher sedang jalan/antre, tidak dispatch"
    if active is False:
        action = "watcher baru dinyalakan" if dispatch() else "GAGAL menyalakan watcher baru"
    print(f"[watchdog] {action}")
    la = st.get("last_alert")
    if not la or (now - dt.datetime.fromisoformat(la)).total_seconds() > ALERT_EVERY_H * 3600:
        notify.send_now(f"🚨 <b>RMF watcher tidak mencatat</b> sejak "
                        f"{notify.wib(last) if last else 'awal'} ({'-' if age is None else f'{age:.0f} menit'})\n"
                        f"{notify.esc(action)}")
        st["last_alert"] = now.isoformat()
    store.save_json("watchdog.json", st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
