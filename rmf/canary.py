"""Canary: buktikan jalur order live RMF di akun HYPE sungguhan, dengan 1 trade kecil.

Pola dari Crypto-MEX (mex/canary.py), tapi RMF memakai order market (IOC) yang
LANGSUNG terisi, jadi canary ini benar-benar beli lalu jual ~10 USDC (biaya
±0,01 USDC fee + spread). Order MEX-style yang tidak terisi tidak bisa menguji
yang paling penting di RMF:

  1. API wallet terdaftar & belum kedaluwarsa (verify_agent, sama dengan live)
  2. koin tanpa posisi terbuka di akun
  3. ekuitas terbaca sebelum trade (metode + komponennya)
  4. set leverage cross 1x diterima (sama dengan live)
  5. beli IOC ukuran minimum (mom.order_size, sama dengan live) terisi, harga
     fill wajar (<= slippage IOC dari mid)
  6. posisi terlihat di akun dengan ukuran yang sama, cross
  7. ekuitas SAAT POSISI TERBUKA (mode unifiedAccount, audit 2026-10-05 F5)
     tidak melenceng dari sebelum trade
  8. jual reduce-only IOC terisi penuh, posisi hilang
  9. ekuitas setelah trade = sebelum - biaya kecil

Pembersihan selalu jalan: kalau posisi canary masih ada, ditutup reduce-only dan
dilaporkan. Tidak menulis state/, tidak menyentuh posisi RMF.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from . import live
from . import momentum as mom

KIND_CANARY = "0c"
# Toleransi ekuitas: trade 10 USDC beberapa detik hanya memakan fee + spread
# (±0,02 USDC). Selisih > 1 USDC berarti cara baca ekuitas salah (mis. hanya margin).
EQUITY_TOL_USD = 1.0
MAX_COST_USD = 0.5


@dataclass
class Report:
    coin: str
    steps: list = field(default_factory=list)      # (nama, ok, detail)
    info: list = field(default_factory=list)       # baris info tambahan (komponen ekuitas)

    def add(self, name, ok, detail=""):
        self.steps.append((name, bool(ok), str(detail)))
        print(f"  [{'OK' if ok else 'GAGAL'}] {name}" + (f" -- {detail}" if detail else ""))
        return bool(ok)

    @property
    def ok(self) -> bool:
        return bool(self.steps) and all(s[1] for s in self.steps)


_STEP = {"buy": 1, "sell": 2, "cleanup": 3}


def _cloid(coin: str, what: str, now: dt.datetime) -> str:
    """cloid berawalan RMF + jenis canary, unik per run (waktu sampai mikrodetik)."""
    return live.cloid(KIND_CANARY, now.isoformat(), coin, _STEP[what])


def run(trader, cfg, coin: str, now: dt.datetime) -> Report:
    rep = Report(coin)
    ex = cfg.execution
    try:
        live.verify_agent(trader, cfg, now)
        rep.add(f"API wallet {ex.agent_address[:10]}… terdaftar dan berlaku", True)
    except live.Halt as e:
        rep.add("API wallet terdaftar dan berlaku", False, e)
        return rep
    if coin in trader.positions():
        rep.add("koin tanpa posisi terbuka", False, f"ada posisi {coin}; canary tidak mau trading di koin ini")
        return rep
    rep.add("koin tanpa posisi terbuka", True)

    filled = 0.0
    try:
        p0 = trader.equity_parts()
        eq0, how = live.equity_from_parts(p0)
        rep.add(f"ekuitas terbaca: {eq0:.2f} USDC ({how})", eq0 > cfg.momentum.min_order_usdc, p0)
        rep.info.append("sebelum: " + _parts(p0))

        lv = trader.set_leverage(coin, ex.leverage, ex.margin_mode == "cross")
        rep.add(f"set leverage {ex.margin_mode} {ex.leverage}x diterima", "error" not in lv, lv)

        mid = trader.mids()[coin]
        sz = mom.order_size(cfg.momentum.min_order_usdc, mid, trader.sz_decimals(coin), cfg.momentum.min_order_usdc)
        st = trader.market(coin, True, sz, mid, ex.ioc_slippage, cloid_hex=_cloid(coin, "buy", now))
        filled, px = live._fill(st)
        rep.add(f"beli IOC {sz:g} {coin} (±{sz * mid:.2f} USDC) terisi", filled > 0 and "error" not in st, st)
        if filled > 0:
            rep.add(f"harga fill {px:g} wajar (mid {mid:g}, batas {ex.ioc_slippage:.0%})",
                    0 < px <= mid * (1 + ex.ioc_slippage), px)

            pos = trader.positions().get(coin)
            rep.add(f"posisi terlihat di akun: {filled:g} {coin}, cross",
                    pos is not None and abs(pos["szi"] - filled) < 1e-9 and pos.get("cross", True), pos)

            p1 = trader.equity_parts()
            eq1, how1 = live.equity_from_parts(p1)
            rep.info.append("posisi terbuka: " + _parts(p1))
            rep.add(f"ekuitas saat posisi terbuka {eq1:.2f} USDC ≈ sebelum ({how1})",
                    abs(eq1 - eq0) <= EQUITY_TOL_USD, f"selisih {eq1 - eq0:+.4f}")

            st = trader.market(coin, False, filled, trader.mids()[coin], ex.ioc_slippage, reduce_only=True,
                               cloid_hex=_cloid(coin, "sell", now))
            sold, spx = live._fill(st)
            rep.add(f"jual reduce-only IOC {filled:g} {coin} terisi penuh",
                    abs(sold - filled) < 1e-9 and "error" not in st, st)
    except Exception as e:  # noqa: BLE001
        rep.add("langkah canary berjalan tanpa error", False, f"{type(e).__name__}: {e}")
    finally:
        _cleanup(trader, cfg, coin, rep, now)
    try:
        p2 = trader.equity_parts()
        eq2, _ = live.equity_from_parts(p2)
        rep.info.append("sesudah: " + _parts(p2))
        if filled > 0:
            cost = eq0 - eq2
            rep.add(f"biaya trade {cost:.4f} USDC (fee + spread)", -EQUITY_TOL_USD <= cost <= MAX_COST_USD, cost)
    except Exception as e:  # noqa: BLE001
        rep.add("ekuitas terbaca setelah trade", False, f"{type(e).__name__}: {e}")
    return rep


def _parts(p: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in p.items())


def _cleanup(trader, cfg, coin, rep, now):
    """Posisi canary yang tersisa (jual gagal / error di tengah) ditutup reduce-only."""
    try:
        p = trader.positions().get(coin)
        if p:
            st = trader.market(coin, p["szi"] < 0, abs(p["szi"]), trader.mids()[coin], cfg.execution.ioc_slippage,
                               reduce_only=True, cloid_hex=_cloid(coin, "cleanup", now))
            left = trader.positions().get(coin)
            rep.add("pembersihan: posisi canary tersisa ditutup", not left, f"{p['szi']:g} {coin}: {st}")
        else:
            rep.add("tidak ada posisi canary tersisa", True)
    except Exception as e:  # noqa: BLE001
        rep.add("cek posisi setelah canary", False, f"{type(e).__name__}: {e} -- CEK POSISI {coin} DI HYPE")


def message(rep: Report) -> str:
    from .notify import esc
    head = ("✅ <b>RMF CANARY OK</b>: jalur order live terbukti di akun HYPE"
            if rep.ok else "🚨 <b>RMF CANARY GAGAL</b>: jangan nyalakan live dulu")
    lines = [f"{'✅' if ok else '❌'} {esc(name)}" + ("" if ok else f"\n   <code>{esc(d[:300])}</code>")
             for name, ok, d in rep.steps]
    info = ("\n\n<b>Komponen ekuitas</b> (untuk dicocokkan dengan UI HYPE)\n"
            + "\n".join(f"<code>{esc(x)}</code>" for x in rep.info)) if rep.info else ""
    return f"{head} ({esc(rep.coin)})\n\n" + "\n".join(lines) + info
