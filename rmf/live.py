"""Eksekusi live momentum di subaccount HYPE.

Hanya jalan kalau control/bot.yaml berisi `momentum: live` (atau manage/flatten)
DAN secret API wallet tersedia. Yang menyalakan live adalah user sendiri.

Desain (pelajaran dari Crypto-MEX):
  * Executor tidak pernah memutuskan sendiri. Peringkat & rezim berasal dari View
    yang sama dengan buku paper; posisi yang dipegang dibaca dari bursa, jadi
    menjalankan ulang di hari yang sama aman (hasilnya konvergen, tidak dobel beli).
  * SDK resmi diimpor malas (lazy): eth-account memuat DLL native yang bisa
    diblokir Windows, dan tes offline tidak boleh bergantung padanya.
  * Setiap order membawa cloid berawalan "RMF" supaya order bot bisa dibedakan
    dari order manual.
  * Kunci API wallet tidak pernah dicetak. Error dilaporkan dengan tipe saja.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math

from . import momentum as mom

MAINNET = "https://api.hyperliquid.xyz"
BOT_PREFIX = "0x524d46"          # "RMF"
KIND_BUY, KIND_SELL = "01", "02"
HTTP_TIMEOUT = 20.0


class Halt(Exception):
    """Jangan sentuh akun sama sekali (kunci salah, agent kedaluwarsa, config kosong)."""


def cloid(kind: str, day: str, coin: str, attempt: int = 0) -> str:
    h = hashlib.sha256(f"{day}|{coin}|{kind}|{attempt}".encode()).hexdigest()
    return BOT_PREFIX + kind + h[:24]


def is_bot_cloid(c) -> bool:
    return isinstance(c, str) and c.lower().startswith(BOT_PREFIX)


def round_px(px: float, sz_decimals: int) -> float:
    """Aturan tick perp HYPE: <= 5 angka signifikan dan <= 6 - szDecimals desimal."""
    return round(float(f"{px:.5g}"), 6 - sz_decimals)


def ioc_px(mid: float, is_buy: bool, sz_decimals: int, slippage: float) -> float:
    return round_px(mid * (1 + slippage if is_buy else 1 - slippage), sz_decimals)


def round_sz_down(sz: float, d: int) -> float:
    q = 10 ** d
    return math.floor(sz * q + 1e-9) / q


def order_status(resp) -> dict:
    """Status pertama dari respons order HYPE, atau {'error': ...}.

    HYPE menjawab {"status":"ok","response":{"data":{"statuses":[...]}}} dan
    menaruh kegagalan per order DI DALAM statuses walau status luar "ok".
    """
    if not isinstance(resp, dict) or resp.get("status") != "ok":
        return {"error": f"respons ditolak: {str(resp)[:200]}"}
    st = (((resp.get("response") or {}).get("data") or {}).get("statuses")) or []
    if not st:
        return {"ok": True}
    return st[0] if isinstance(st[0], dict) else {"ok": st[0]}


# --------------------------------------------------------------------------- #
#  Adapter SDK — satu-satunya bagian yang berbicara dengan SDK Hyperliquid
# --------------------------------------------------------------------------- #
class HypeTrader:
    def __init__(self, agent_key: str, master: str, account: str, base_url: str = MAINNET,
                 timeout: float = HTTP_TIMEOUT):
        import eth_account
        from hyperliquid.exchange import Exchange
        from hyperliquid.info import Info

        wallet = eth_account.Account.from_key(agent_key)
        self.agent_address = wallet.address
        self.master, self.account = master, account
        self.info = Info(base_url, skip_ws=True, timeout=timeout)
        # vault_address = subaccount: order ditandatangani API wallet milik akun
        # utama, dieksekusi atas nama subaccount RMF.
        vault = account if account.lower() != master.lower() else None
        self.exchange = Exchange(wallet, base_url, account_address=master, vault_address=vault, timeout=timeout)
        self._sz = {u["name"]: int(u["szDecimals"]) for u in self.info.meta()["universe"]}

    def agents(self) -> list:
        return self.info.extra_agents(self.master)

    def sz_decimals(self, coin: str) -> int:
        return self._sz[coin]

    def mids(self) -> dict:
        return {k: float(v) for k, v in self.info.all_mids().items()}

    def positions(self) -> dict:
        out = {}
        for ap in self.info.user_state(self.account).get("assetPositions", []):
            p = ap["position"]
            szi = float(p["szi"])
            if szi:
                out[p["coin"]] = {"szi": szi, "entry_px": float(p["entryPx"]),
                                  "unrealized": float(p.get("unrealizedPnl") or 0),
                                  "cross": p["leverage"]["type"] == "cross"}
        return out

    def abstraction(self) -> str | None:
        """Mode akun HYPE (mis. 'unifiedAccount', 'portfolioMargin', 'default'); None = tidak terbaca."""
        try:
            r = self.info.post("/info", {"type": "userAbstraction", "user": self.account})
            return r if isinstance(r, str) else None
        except Exception:  # noqa: BLE001
            return None

    def equity_parts(self) -> dict:
        st = self.info.user_state(self.account)
        usdc = hold = 0.0
        for b in self.info.spot_user_state(self.account).get("balances", []):
            if b["coin"] == "USDC":
                usdc, hold = float(b["total"]), float(b.get("hold") or 0)
        return {"abstraction": self.abstraction(),
                "perp_account_value": float((st.get("marginSummary") or {}).get("accountValue") or 0),
                "spot_usdc": usdc, "spot_usdc_hold": hold,
                "upnl": sum(float(ap["position"].get("unrealizedPnl") or 0) for ap in st.get("assetPositions", []))}

    def equity(self) -> tuple[float, str]:
        """(ekuitas USDC, metode); lihat equity_from_parts."""
        return equity_from_parts(self.equity_parts())

    def set_leverage(self, coin: str, leverage: int, cross: bool) -> dict:
        return order_status(self.exchange.update_leverage(leverage, coin, is_cross=cross))

    def market(self, coin: str, is_buy: bool, sz: float, mid: float, slippage: float,
               reduce_only: bool = False, cloid_hex: str | None = None) -> dict:
        from hyperliquid.utils.types import Cloid
        px = ioc_px(mid, is_buy, self.sz_decimals(coin), slippage)
        return order_status(self.exchange.order(
            coin, is_buy, sz, px, {"limit": {"tif": "Ioc"}}, reduce_only=reduce_only,
            cloid=Cloid.from_str(cloid_hex) if cloid_hex else None))


UNIFIED = ("unifiedAccount", "portfolioMargin")


def equity_from_parts(p: dict) -> tuple[float, str]:
    """Mode unified / portfolio margin: dokumentasi HYPE menyatakan semua saldo ada
    di spot clearinghouse dan perp state "not meaningful", jadi perp accountValue
    TIDAK dipakai walau > 0 (audit 2026-10-05 F5). Mode biasa: perp accountValue
    (sudah termasuk uPnL). Mode tidak terbaca: cara lama (perp kalau > 0).
    Belum diverifikasi dengan posisi terbuka: bandingkan dengan UI HYPE di hari
    live pertama (tools/check_live.py mencetak semua komponennya)."""
    mode = p.get("abstraction")
    av = p["perp_account_value"]
    if mode in UNIFIED or (mode is None and av <= 0):
        return p["spot_usdc"] + p["upnl"], f"spot USDC + uPnL ({mode or 'mode tidak terbaca'})"
    return av, f"perp accountValue ({mode or 'mode tidak terbaca'})"


def make_trader(cfg, agent_key: str):
    ex = cfg.execution
    if not (ex.master_address and ex.account_address and ex.agent_address):
        raise Halt("execution.master_address / account_address / agent_address di config.yaml belum diisi")
    return HypeTrader(agent_key, ex.master_address, ex.account_address)


# --------------------------------------------------------------------------- #
#  Logika executor — diuji dengan trader tiruan (tests/test_live.py)
# --------------------------------------------------------------------------- #
def verify_agent(trader, cfg, now: dt.datetime) -> None:
    ex = cfg.execution
    if trader.agent_address.lower() != ex.agent_address.lower():
        raise Halt(f"kunci di secret menghasilkan {trader.agent_address}, bukan agent {ex.agent_address}")
    if ex.agent_valid_until:
        until = dt.date.fromisoformat(ex.agent_valid_until)
        if now.date() > until:
            raise Halt(f"API wallet kedaluwarsa sejak {until} — buat yang baru, ganti secret")
    now_ms = int(now.timestamp() * 1000)
    for a in trader.agents():
        if str(a.get("address", "")).lower() == ex.agent_address.lower():
            vu = a.get("validUntil")
            if vu and int(vu) < now_ms:
                raise Halt("API wallet terdaftar tapi sudah kedaluwarsa di HYPE")
            return
    raise Halt(f"API wallet {ex.agent_address} tidak terdaftar di akun {ex.master_address}")


def _fill(st: dict) -> tuple[float, float]:
    f = st.get("filled") if isinstance(st, dict) else None
    if not f:
        return 0.0, 0.0
    return float(f.get("totalSz", 0) or 0), float(f.get("avgPx", 0) or 0)


def run_momentum(view: mom.View, cfg, trader, mode: str, block_entries: bool, now: dt.datetime,
                 attempt: int = 0, only_isolated=frozenset(), owned=frozenset(), journal=None) -> dict:
    """Samakan posisi akun RMF dengan aturan momentum hari ini.

    mode: live (jual + beli) | manage (jual saja) | flatten (tutup posisi milik RMF)
    block_entries: True kalau circuit breaker DD aktif (beli ditahan).
    only_isolated: koin yang di HYPE hanya boleh isolated (dipasang isolated 1x).
    owned: koin yang dibuka RMF sendiri (dari state). Posisi lain di akun = ASING:
           live/manage berhenti (Halt) tanpa order, flatten hanya menutup milik RMF.
           Akun ini dulu dipakai MEX; pengaman ini mencegah RMF menjual posisi MEX.
    journal(coin): dipanggil SEBELUM tiap order beli, supaya koin itu tercatat milik
           RMF walaupun job mati sebelum state hasil order tersimpan.
    """
    verify_agent(trader, cfg, now)
    ex = cfg.execution
    res = {"orders": [], "errors": [], "skipped": []}
    pos = trader.positions()
    foreign = sorted(c for c in pos if c not in owned)
    if foreign and mode != "flatten":
        raise Halt(f"akun berisi posisi yang bukan dibuka RMF: {', '.join(foreign)}. Tutup/pindahkan dulu "
                   "(mis. posisi MEX), RMF butuh akun khusus")
    mids = trader.mids()
    eq, how = trader.equity()
    res.update(equity_before=eq, equity_method=how)
    if foreign:
        res["errors"].append(f"posisi asing tidak disentuh: {', '.join(foreign)}")
    pos = {c: p for c, p in pos.items() if c in owned}
    held = [c for c, p in pos.items() if p["szi"] > 0]

    if mode == "flatten":
        sells = [(c, "flatten") for c in pos]
        buys = []
    else:
        rb = mom.rebalance(view, held, cfg)
        sells = rb.sells
        buys = rb.buys if (mode == "live" and not block_entries) else []
        if rb.buys and not buys:
            res["skipped"] = [(c, "breaker DD aktif" if block_entries else f"mode {mode}") for c in rb.buys]

    for coin, why in sells:
        p = pos[coin]
        is_buy = p["szi"] < 0
        sz = abs(p["szi"])
        mid = mids.get(coin)
        if not mid:
            res["errors"].append(f"{coin}: mid tidak ada, jual ditunda")
            continue
        try:
            st = trader.market(coin, is_buy, sz, mid, ex.ioc_slippage, reduce_only=True,
                               cloid_hex=cloid(KIND_SELL, view.exec_day, coin, attempt))
        except Exception as e:  # noqa: BLE001
            res["errors"].append(f"{coin}: jual gagal ({type(e).__name__})")
            continue
        fsz, fpx = _fill(st)
        if "error" in st or fsz <= 0:
            res["errors"].append(f"{coin}: jual tidak terisi ({str(st.get('error', st))[:120]})")
        res["orders"].append({"coin": coin, "side": "SELL", "qty": fsz, "px": fpx, "mid": mid,
                              "reason": why, "status": "filled" if fsz > 0 else "failed"})

    # Koin yang ordernya SUDAH dikirim (atau mungkin terkirim). Order yang
    # timeout bisa tetap terisi di bursa; tanpa ini posisinya dianggap asing di
    # percobaan berikutnya dan live berhenti (audit 2026-10-05 F2).
    tried = set()
    if buys:
        usd = mom.per_coin_usd(eq, cfg)
        for coin in buys:
            mid = mids.get(coin)
            if not mid:
                res["errors"].append(f"{coin}: mid tidak ada, beli dilewati")
                continue
            try:
                d = trader.sz_decimals(coin)
                sz = mom.order_size(usd, mid, d, cfg.momentum.min_order_usdc)
                if journal:
                    journal(coin)
                tried.add(coin)
                if coin in only_isolated:
                    lv = trader.set_leverage(coin, 1, False)
                else:
                    lv = trader.set_leverage(coin, ex.leverage, ex.margin_mode == "cross")
                if "error" in lv:
                    res["errors"].append(f"{coin}: set leverage gagal ({str(lv['error'])[:120]})")
                    continue
                st = trader.market(coin, True, sz, mid, ex.ioc_slippage,
                                   cloid_hex=cloid(KIND_BUY, view.exec_day, coin, attempt))
            except Exception as e:  # noqa: BLE001
                res["errors"].append(f"{coin}: beli gagal ({type(e).__name__})")
                continue
            fsz, fpx = _fill(st)
            if "error" in st or fsz <= 0:
                res["errors"].append(f"{coin}: beli tidak terisi ({str(st.get('error', st))[:120]})")
            res["orders"].append({"coin": coin, "side": "BUY", "qty": fsz, "px": fpx, "mid": mid,
                                  "reason": f"peringkat {view.ranks().get(coin)}",
                                  "status": "filled" if fsz > 0 else "failed"})
    try:
        res["equity_after"], _ = trader.equity()
        after = {c: p for c, p in trader.positions().items() if c in owned or c in tried}
        res["positions_after"] = {c: p["szi"] for c, p in after.items()}
        res["gross_after"] = sum(abs(p["szi"]) * mids.get(c, p["entry_px"]) for c, p in after.items())
    except Exception as e:  # noqa: BLE001
        res["errors"].append(f"baca akun setelah order gagal ({type(e).__name__})")
    return res
