"""Diagnostik live HANYA BACA. Jalankan sekali setelah API wallet dan subaccount
diisi di config.yaml, SEBELUM menyalakan momentum: live.

    RMF_AGENT_KEY=0x... python tools/check_live.py      (Git Bash)
    $env:RMF_AGENT_KEY="0x..."; python tools/check_live.py   (PowerShell)

Mengecek: kunci menghasilkan alamat agent di config, agent terdaftar di akun
utama dan belum kedaluwarsa, saldo subaccount terbaca (dan dengan metode apa),
posisi yang sudah ada. TIDAK mengirim order apa pun.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rmf import config, live  # noqa: E402


def main() -> int:
    cfg = config.load()
    key = os.environ.get("RMF_AGENT_KEY", "").strip()
    if not key:
        print("RMF_AGENT_KEY kosong")
        return 2
    if not (key.startswith("0x") and len(key) == 66):
        print("RMF_AGENT_KEY harus PRIVATE KEY API wallet: 0x + 64 hex (66 karakter), bukan alamat (42)")
        return 2
    try:
        t = live.make_trader(cfg, key)
        live.verify_agent(t, cfg, dt.datetime.now(dt.timezone.utc))
        print(f"✓ agent {t.agent_address} terdaftar di {cfg.execution.master_address}")
        parts = t.equity_parts()
        eq, how = live.equity_from_parts(parts)
        print(f"✓ ekuitas akun {cfg.execution.account_address}: {eq:.2f} USDC ({how})")
        # Semua komponen, untuk dicocokkan dengan UI HYPE di hari live pertama
        # (cara baca ekuitas mode unified belum pernah diuji dengan posisi terbuka).
        print("  komponen: " + ", ".join(f"{k}={v}" for k, v in parts.items()))
        pos = t.positions()
        print(f"✓ posisi: {pos or 'tidak ada'}")
        if eq < cfg.capital_usdc * 0.9:
            print(f"⚠️ ekuitas di bawah {cfg.capital_usdc} USDC yang direncanakan")
        return 0
    except live.Halt as e:
        print(f"✗ {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"✗ gagal: {type(e).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
