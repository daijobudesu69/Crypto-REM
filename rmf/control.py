"""Kendali mode bot, dibaca SETIAP siklus dari control/bot.yaml.

Diubah lewat workflow control.yml (atau edit file di main). Watcher menarik
origin tiap siklus (tools/refresh_state.sh menyalin versi origin ke CACHE),
jadi perubahan berlaku <= ~10 menit, bukan menunggu job berikutnya.

momentum:
  off      tidak melakukan apa-apa (buku paper juga berhenti)
  paper    hanya buku paper (DEFAULT, aman)
  live     buku paper + eksekusi live di subaccount (jual + beli)
  manage   buku paper + live hanya JUAL sesuai aturan (rem: tanpa beli baru)
  flatten  buku paper + tutup SEMUA posisi live tiap siklus sampai mode diganti
flush:
  off | paper           (live flush belum ada: sinyal futures butuh VPS)
breaker_reset: nilai BARU apa pun = puncak ekuitas live di-reset ke ekuitas sekarang.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import yaml

from .config import ROOT

MOMENTUM_MODES = ("off", "paper", "live", "manage", "flatten")
FLUSH_MODES = ("off", "paper")
PATH = os.path.join(ROOT, "control", "bot.yaml")
CACHE = os.path.join(ROOT, ".rmf_control_origin.yaml")   # ditulis refresh_state.sh, di-gitignore
LIVE_MODES = ("live", "manage", "flatten")


@dataclass
class Control:
    momentum: str = "paper"
    flush: str = "paper"
    breaker_reset: str = ""
    problem: str | None = None

    @property
    def live(self) -> bool:
        return self.momentum in LIVE_MODES


def _norm(v) -> str:
    # YAML 1.1 membaca `off` tanpa kutip sebagai boolean False.
    if v is False:
        return "off"
    return str(v or "").strip().lower()


def read(paths=None) -> Control:
    paths = paths or (CACHE, PATH)
    p = next((x for x in paths if os.path.exists(x)), None)
    if p is None:
        return Control(problem="control/bot.yaml tidak ada; dipakai paper/paper")
    try:
        with open(p, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        if not isinstance(doc, dict):
            raise ValueError("bukan pasangan kunci: nilai")
    except Exception as e:  # noqa: BLE001
        # File rusak tidak boleh membuka posisi baru. Fallback paper = akun live
        # tidak disentuh sama sekali sampai file diperbaiki (momentum tidak punya
        # stop di bursa, jadi tidak ada yang perlu dijaga per siklus).
        return Control(problem=f"control/bot.yaml tidak bisa dibaca ({type(e).__name__}); dipakai paper/paper")
    c = Control(momentum=_norm(doc.get("momentum", "paper")), flush=_norm(doc.get("flush", "paper")),
                breaker_reset=str(doc.get("breaker_reset") or "").strip())
    probs = []
    if c.momentum not in MOMENTUM_MODES:
        probs.append(f"momentum '{c.momentum}' tidak dikenal")
        c.momentum = "paper"
    if c.flush not in FLUSH_MODES:
        probs.append(f"flush '{c.flush}' tidak dikenal")
        c.flush = "paper"
    c.problem = "; ".join(probs) or None
    return c


def render(momentum: str, flush: str, breaker_reset: str) -> str:
    if momentum not in MOMENTUM_MODES or flush not in FLUSH_MODES:
        raise ValueError("mode tidak dikenal")
    return f"""\
# Kendali bot RMF. Dibaca watcher SETIAP siklus (~10 menit).
# Ubah lewat workflow (PowerShell / CMD / Git Bash):
#   gh workflow run control.yml -f momentum=live
#   gh workflow run control.yml -f momentum=flatten      # tutup semua posisi live
#   gh workflow run control.yml -f reset_breaker=true
#
# momentum: off | paper | live | manage | flatten
#   paper   hanya buku paper (default)
#   live    paper + live di subaccount (jual + beli)
#   manage  paper + live hanya jual (tanpa beli baru)
#   flatten paper + tutup semua posisi live tiap siklus
# flush:    off | paper
momentum: "{momentum}"
flush: "{flush}"
breaker_reset: "{breaker_reset}"
"""
