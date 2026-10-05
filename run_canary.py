"""Canary RMF: .github/workflows/canary.yml, dijalankan manual saja.

    gh workflow run canary.yml --repo daijobudesu69/Crypto-RMF -f coin=ETH

Beli lalu jual ~10 USDC di akun HYPE sungguhan lewat jalur order yang sama
dengan live (rmf/canary.py), lalu laporkan setiap langkah ke Telegram. Exit 0
hanya kalau semua langkah lolos. Tidak menulis state/.

Ditolak kalau momentum sedang live/manage/flatten: posisi canary yang muncul
sesaat akan dibaca bot live sebagai posisi asing. Jalankan sebelum live, atau
set mode paper dulu.

Env: RMF_AGENT_KEY (kunci privat API wallet, GitHub secret), TELEGRAM_*.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

from rmf import canary, config, control, live, notify


def key_problem(key: str, secret: str) -> str | None:
    if not key:
        return f"secret {secret} kosong"
    if not (key.startswith("0x") and len(key) == 66):
        return (f"secret {secret}: panjang {len(key)}, harus 66 (0x + 64 hex) -- "
                "mungkin yang diisi alamat, bukan private key")
    return None


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    coin = (argv[0] if argv else "ETH").strip()
    cfg = config.load()
    ctrl = control.read()
    if ctrl.live:
        msg = (f"momentum sedang '{ctrl.momentum}': posisi canary akan terbaca sebagai posisi asing oleh bot "
               "live. Set mode paper dulu (control.yml -f momentum=paper), atau jalankan sebelum live.")
        print(f"[canary] BERHENTI: {msg}")
        notify.send_now(f"🚨 <b>RMF CANARY tidak dijalankan</b>\n{notify.esc(msg)}")
        return 2
    key = os.environ.get("RMF_AGENT_KEY", "").strip()
    problem = key_problem(key, cfg.execution.agent_secret)
    if problem:
        print(f"[canary] BERHENTI: {problem}")
        notify.send_now(f"🚨 <b>RMF CANARY berhenti</b>\n{notify.esc(problem)}")
        return 2
    try:
        trader = live.make_trader(cfg, key)
    except Exception as e:  # noqa: BLE001
        # Tipe saja: pesan exception tidak boleh membawa apa pun dari kunci.
        print(f"[canary] BERHENTI: trader tidak bisa dibuat ({type(e).__name__})")
        notify.send_now(f"🚨 <b>RMF CANARY berhenti</b>\ntrader tidak bisa dibuat ({type(e).__name__})")
        return 2
    finally:
        del key
    if coin not in trader.mids():
        print(f"[canary] koin '{coin}' tidak ada di HYPE")
        return 2
    print(f"[canary] {coin} -- akun {cfg.execution.account_address}")
    rep = canary.run(trader, cfg, coin, dt.datetime.now(dt.timezone.utc))
    notify.send_now(canary.message(rep))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("\n".join(f"- {'✅' if ok else '❌'} {n}" + ("" if ok else f" — `{d[:300]}`")
                               for n, ok, d in rep.steps) + "\n")
    print(f"[canary] {'OK' if rep.ok else 'GAGAL'}")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
