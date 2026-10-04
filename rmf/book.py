"""Buku paper: posisi perp long tanpa leverage nyata, disimpan sebagai dict JSON.

Model akuntansi perp: membuka posisi tidak mengurangi kas; PnL, fee, dan funding
masuk ke kas saat terjadi. Ekuitas = kas + PnL belum terealisasi.
Harga fill paper = mid +/- slippage, fee = notional x taker fee (config.costs).
"""
from __future__ import annotations


def new_book(capital: float) -> dict:
    return {"cash": float(capital), "start_capital": float(capital), "positions": {},
            "fees": 0.0, "funding": 0.0, "realized": 0.0, "peak_equity": float(capital)}


def unrealized(book: dict, mids: dict) -> float:
    u = 0.0
    for coin, p in book["positions"].items():
        px = mids.get(coin, p.get("last_px", p["entry_px"]))
        u += p["qty"] * (px - p["entry_px"])
    return u


def equity(book: dict, mids: dict) -> float:
    return book["cash"] + unrealized(book, mids)


def gross(book: dict, mids: dict) -> float:
    return sum(p["qty"] * mids.get(c, p.get("last_px", p["entry_px"])) for c, p in book["positions"].items())


def mark(book: dict, mids: dict) -> None:
    """Simpan harga terakhir yang diketahui (dipakai kalau mid koin hilang)."""
    for coin, p in book["positions"].items():
        if coin in mids:
            p["last_px"] = float(mids[coin])
    eq = equity(book, mids)
    book["peak_equity"] = max(float(book.get("peak_equity", eq)), eq)


def buy(book: dict, coin: str, qty: float, mid: float, costs, when: str, extra: dict | None = None) -> dict:
    px = mid * (1 + costs.paper_slippage)
    notional = qty * px
    fee = notional * costs.taker_fee
    p = book["positions"].get(coin)
    if p:  # tambah posisi: harga rata-rata
        tot = p["qty"] + qty
        p["entry_px"] = (p["qty"] * p["entry_px"] + qty * px) / tot
        p["qty"] = tot
    else:
        book["positions"][coin] = {"qty": qty, "entry_px": px, "entry_time": when, "last_px": mid,
                                   "fees": 0.0, "funding": 0.0, **(extra or {})}
        p = book["positions"][coin]
    p["fees"] = p.get("fees", 0.0) + fee
    book["cash"] -= fee
    book["fees"] += fee
    return {"coin": coin, "side": "BUY", "qty": qty, "px": px, "notional": notional, "fee": fee, "pnl": 0.0}


def close(book: dict, coin: str, mid: float, costs, exact_px: float | None = None) -> dict:
    """Tutup seluruh posisi. exact_px = harga exit tertentu (SL/TP flush) sebelum slippage."""
    p = book["positions"].pop(coin)
    base = exact_px if exact_px is not None else mid
    px = base * (1 - costs.paper_slippage)
    notional = p["qty"] * px
    fee = notional * costs.taker_fee
    pnl = p["qty"] * (px - p["entry_px"])
    book["cash"] += pnl - fee
    book["fees"] += fee
    book["realized"] += pnl
    total_fees = p.get("fees", 0.0) + fee
    return {"coin": coin, "side": "SELL", "qty": p["qty"], "px": px, "notional": notional, "fee": fee,
            "pnl": pnl, "net_pnl": pnl - total_fees - p.get("funding", 0.0), "entry_px": p["entry_px"],
            "entry_time": p.get("entry_time"), "position": p}


def charge_funding(book: dict, coin: str, amount: float) -> None:
    """amount > 0 = dibayar (long membayar saat funding positif)."""
    if coin in book["positions"]:
        book["positions"][coin]["funding"] = book["positions"][coin].get("funding", 0.0) + amount
    book["cash"] -= amount
    book["funding"] += amount


def funding_cost(qty: float, px: float, rates: list) -> float:
    """Funding untuk long: qty x harga x jumlah rate per jam."""
    return qty * px * sum(r for _, r in rates)
