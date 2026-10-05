"""Job harian momentum dan job 4h flush. Dipanggil run_cycle.py setiap siklus.

Keduanya idempoten: state mencatat hari / bar terakhir yang sudah diproses,
jadi watcher yang mengecek tiap 10 menit hanya bekerja sekali per hari / bar.
Semua akses jaringan lewat objek `ctx` supaya tes bisa memakai data tiruan.
"""
from __future__ import annotations

import datetime as dt
import os
import traceback
from dataclasses import dataclass, field

import pandas as pd

from . import book as bk
from . import control as ctl
from . import flush as fl
from . import live
from . import momentum as mom
from . import notify, stoprules, store
from .config import path_in_repo

DAY_MS = 86_400_000
H4 = pd.Timedelta(hours=4)


@dataclass
class Ctx:
    cfg: object
    info: object                       # rmf.hype.InfoClient (atau tiruan)
    klines: object                     # rmf.binance.KlineClient (atau tiruan)
    ctrl: ctl.Control
    outbox: notify.Outbox
    now: dt.datetime
    trader_factory: object = None      # () -> trader; None = live tidak tersedia
    _meta: dict | None = None
    log: list = field(default_factory=list)

    def meta(self) -> dict:
        if self._meta is None:
            self._meta = self.info.meta()
        return self._meta

    def say(self, msg: str) -> None:
        print(msg)
        self.log.append(msg)


def utc_day(now: dt.datetime) -> pd.Timestamp:
    return pd.Timestamp(now).tz_convert("UTC").tz_localize(None).normalize()


def started(cfg, now: dt.datetime) -> bool:
    return not cfg.forward_start or utc_day(now) >= pd.Timestamp(cfg.forward_start)


# =========================================================================== #
#  MOMENTUM (harian)
# =========================================================================== #
def fetch_view(ctx: Ctx, exec_day: pd.Timestamp) -> mom.View:
    cfg = ctx.cfg
    meta = ctx.meta()
    now_ms = int(ctx.now.timestamp() * 1000)
    alive = [c for c, m in meta.items() if not m["isDelisted"]]
    if cfg.universe.mode == "static":
        want = set(mom.static_universe(cfg)) | {cfg.momentum.regime_symbol}
        coins = [c for c in alive if c in want]
    else:
        coins = [c for c in alive if c not in cfg.universe.exclude]
    candles, failed = {}, []
    for c in coins:
        days = cfg.universe.btc_fetch_days if c == cfg.momentum.regime_symbol else cfg.universe.fetch_days
        try:
            # include_open: open candle hari ini dipakai basket (open E-1 -> open E)
            candles[c] = ctx.info.candles(c, "1d", now_ms - days * DAY_MS, include_open=True)
        except Exception as e:  # noqa: BLE001
            if c == cfg.momentum.regime_symbol:
                raise
            failed.append(f"{c} ({type(e).__name__})")
    if failed:
        ctx.say(f"[momentum] candle gagal diambil: {', '.join(failed[:20])}")
    funding = None
    if cfg.benchmark.include_funding:
        day = mom.naive_day(exec_day)
        closed = mom.closed_only(candles, day - pd.Timedelta(days=1))
        members = mom.bench_members(candles, mom.select_universe(closed, meta, cfg), day, cfg.momentum.min_history_days)
        start = int(pd.Timestamp(day - pd.Timedelta(days=1), tz="UTC").value // 10**6)
        end = start + DAY_MS - 1
        funding, miss = {}, 0
        for c in members:
            try:
                funding[c] = sum(r for _, r in ctx.info.funding_history(c, start, end))
            except Exception:  # noqa: BLE001
                miss += 1
        if miss:
            ctx.say(f"[momentum] funding basket gagal untuk {miss} koin (dianggap 0)")
    return mom.market_view(candles, meta, exec_day, cfg, funding)


def _accrue_funding(ctx: Ctx, book: dict, mids: dict) -> float:
    """Funding riil HYPE untuk posisi paper sejak terakhir dihitung."""
    total = 0.0
    now_ms = int(ctx.now.timestamp() * 1000)
    for coin, p in book["positions"].items():
        start = int(p.get("funding_ms") or pd.Timestamp(p["entry_time"]).value // 10**6)
        if now_ms - start < 3_600_000:
            continue
        try:
            rates = ctx.info.funding_history(coin, start + 1, now_ms)
        except Exception as e:  # noqa: BLE001
            ctx.say(f"[momentum] funding {coin} gagal ({type(e).__name__}); dicoba besok")
            continue
        amt = bk.funding_cost(p["qty"], mids.get(coin, p["entry_px"]), rates)
        bk.charge_funding(book, coin, amt)
        p["funding_ms"] = max([t for t, _ in rates], default=start)
        total += amt
    return total


def momentum_due(ctx: Ctx) -> tuple[bool, bool, str]:
    """(paper perlu jalan, live perlu jalan, exec_day)."""
    cfg, now = ctx.cfg, ctx.now
    day = utc_day(now)
    if ctx.ctrl.momentum == "off" or not started(cfg, now):
        return False, False, str(day.date())
    if pd.Timestamp(now).tz_convert("UTC").tz_localize(None) < day + pd.Timedelta(minutes=cfg.momentum.run_after_minutes):
        return False, False, str(day.date())
    paper = store.load_json("momentum_paper.json") or {}
    need_paper = paper.get("last_day") != str(day.date())
    need_live = False
    if ctx.ctrl.live:
        ls = store.load_json("momentum_live.json") or {}
        tries = (ls.get("attempts") or {}).get(str(day.date()), 0)
        if ctx.ctrl.momentum == "flatten":
            need_live = bool(ls.get("positions")) or ls.get("flatten_day") != str(day.date())
        else:
            need_live = ls.get("last_day") != str(day.date()) and tries < cfg.execution.max_live_attempts_per_day
    return need_paper, need_live, str(day.date())


def run_momentum(ctx: Ctx) -> dict | None:
    need_paper, need_live, exec_day = momentum_due(ctx)
    if not (need_paper or need_live):
        return None
    cfg = ctx.cfg
    vdoc = store.load_json("momentum_view.json")
    if vdoc and vdoc.get("exec_day") == exec_day:
        view = mom.View.from_dict(vdoc)
    else:
        view = fetch_view(ctx, pd.Timestamp(exec_day))
        store.save_json("momentum_view.json", view.to_dict())
    mids = ctx.info.all_mids()
    t = ctx.now.isoformat(timespec="seconds")
    delay = (pd.Timestamp(ctx.now).tz_convert("UTC").tz_localize(None) - pd.Timestamp(exec_day)).total_seconds() / 60
    out = {"exec_day": exec_day, "view": view, "delay_min": delay, "paper": None, "live": None}

    paper = store.load_json("momentum_paper.json") or {"book": bk.new_book(cfg.capital_usdc), "bench_index": 1.0}
    if need_paper:
        out["paper"] = _paper_day(ctx, paper, view, mids, t)
    if need_live:
        out["live"] = _live_day(ctx, view, exec_day, t)

    if need_paper:
        _record_day(ctx, paper, view, mids, out, t)
        store.save_json("momentum_paper.json", paper)
    elif out["live"] is not None:
        ctx.outbox.add(_live_message(out["live"], ctx))
    return out


def _paper_day(ctx: Ctx, paper: dict, view: mom.View, mids: dict, t: str) -> dict:
    cfg = ctx.cfg
    b = paper["book"]
    funding = _accrue_funding(ctx, b, mids)
    bk.mark(b, mids)
    eq0 = bk.equity(b, mids)
    rb = mom.rebalance(view, list(b["positions"]), cfg)
    fills, warn = [], []
    for coin, why in rb.sells:
        mid = mids.get(coin) or b["positions"][coin].get("last_px")
        f = bk.close(b, coin, mid, cfg.costs)
        f.update(reason=why)
        fills.append(f)
    usd = mom.per_coin_usd(eq0, cfg)
    meta = ctx.meta()
    for coin in rb.buys:
        mid = mids.get(coin)
        if not mid or coin not in meta:
            warn.append(f"{coin}: mid/meta tidak ada, beli dilewati")
            continue
        qty = mom.order_size(usd, mid, meta[coin]["szDecimals"], cfg.momentum.min_order_usdc)
        f = bk.buy(b, coin, qty, mid, cfg.costs, t, extra={"funding_ms": int(ctx.now.timestamp() * 1000)})
        f.update(reason=f"peringkat {view.ranks().get(coin)}")
        fills.append(f)
    for f in fills:
        store.append("orders", {"time_utc": t, "book": "paper", "strategy": "momentum", "exec_day": view.exec_day,
                                "coin": f["coin"], "side": f["side"], "qty": f["qty"], "px": f["px"],
                                "mid": mids.get(f["coin"]), "notional": f["notional"], "fee": f["fee"],
                                "pnl": f.get("net_pnl", 0.0), "reason": f["reason"], "status": "paper"})
    bk.mark(b, mids)
    paper["last_day"] = view.exec_day
    # basket "beli semua koin" (1x, definisi riset): satu langkah per hari
    if paper.get("bench_day") != view.exec_day:
        paper["bench_index"] = float(paper.get("bench_index", 1.0)) * (1 + view.bench_ret)
        paper["bench_day"] = view.exec_day
    return {"equity_before": eq0, "equity": bk.equity(b, mids), "gross": bk.gross(b, mids), "fills": fills,
            "warn": warn, "funding": funding, "positions": sorted(b["positions"]), "per_coin": usd,
            "skipped_buys": [c for c in rb.buys if c not in b["positions"]]}


def _live_day(ctx: Ctx, view: mom.View, exec_day: str, t: str) -> dict:
    cfg = ctx.cfg
    ls = store.load_json("momentum_live.json") or {}
    attempts = ls.setdefault("attempts", {})
    attempts = {k: v for k, v in attempts.items() if k >= exec_day}     # buang hari lama
    n = attempts.get(exec_day, 0)
    attempts[exec_day] = n + 1
    ls["attempts"] = attempts
    res = {"mode": ctx.ctrl.momentum, "errors": [], "orders": []}
    try:
        if ctx.trader_factory is None:
            raise live.Halt(f"secret API wallet ({cfg.execution.agent_secret}) belum diisi; live tidak bisa jalan")
        trader = ctx.trader_factory()
        eq_now, _ = trader.equity()
        # circuit breaker DD (aturan berhenti #1): tahan beli baru
        if ctx.ctrl.breaker_reset and ctx.ctrl.breaker_reset != ls.get("breaker_reset_seen"):
            ls["peak_equity"] = eq_now
            ls["breaker_reset_seen"] = ctx.ctrl.breaker_reset
            ctx.say(f"[live] breaker di-reset; puncak = {eq_now:.2f}")
        peak = max(float(ls.get("peak_equity") or 0), eq_now)
        ls["peak_equity"] = peak
        dd = (eq_now / peak - 1) * 100 if peak > 0 else 0.0
        block = dd < -cfg.stop_rules.max_drawdown_pct
        only_iso = frozenset(c for c, m in ctx.meta().items() if m.get("onlyIsolated"))
        r = live.run_momentum(view, cfg, trader, ctx.ctrl.momentum, block, ctx.now, attempt=n, only_isolated=only_iso)
        res.update(r)
        res["dd_pct"], res["breaker"] = dd, block
        for o in r["orders"]:
            store.append("orders", {"time_utc": t, "book": "live", "strategy": "momentum", "exec_day": exec_day,
                                    "coin": o["coin"], "side": o["side"], "qty": o["qty"], "px": o["px"],
                                    "mid": o["mid"], "notional": o["qty"] * o["px"], "fee": "",
                                    "pnl": "", "reason": o["reason"], "status": o["status"]})
        ls["positions"] = r.get("positions_after", {})
        ls["last_equity"] = r.get("equity_after", eq_now)
        ls["last_gross"] = r.get("gross_after")
        if ctx.ctrl.momentum == "flatten":
            ls["flatten_day"] = exec_day
        if not r["errors"]:
            ls["last_day"] = exec_day
    except live.Halt as e:
        res["errors"].append(f"HALT: {e}")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        res["errors"].append(f"live gagal: {type(e).__name__}")
    store.save_json("momentum_live.json", ls)
    return res


def _record_day(ctx: Ctx, paper: dict, view: mom.View, mids: dict, out: dict, t: str) -> None:
    cfg = ctx.cfg
    b = paper["book"]
    p = out["paper"]
    lv = out["live"] or {}
    ls = store.load_json("momentum_live.json") or {}
    flush_state = store.load_json("flush_paper.json") or {}
    fb = flush_state.get("book")
    peak = float(b.get("peak_equity", p["equity"]))
    store.append("equity", {
        "exec_day": view.exec_day, "time_utc": t, "regime_on": view.regime_on, "btc_close": view.btc_close,
        "btc_ema": view.btc_ema, "paper_equity": p["equity"], "paper_gross": p["gross"],
        "paper_positions": len(p["positions"]),
        "live_equity": lv.get("equity_after", ls.get("last_equity")) if ctx.ctrl.live else "",
        "live_positions": len(ls.get("positions") or {}) if ctx.ctrl.live else "",
        "flush_equity": bk.equity(fb, mids) if fb else 0.0,
        "bench_ret": view.bench_ret, "bench_index": paper["bench_index"], "paper_peak": peak,
        "paper_dd_pct": (p["equity"] / peak - 1) * 100 if peak else 0.0, "delay_min": round(out["delay_min"], 1),
        "live_gross": lv.get("gross_after", ls.get("last_gross")) if ctx.ctrl.live else ""})
    held_live = set((ls.get("positions") or {}).keys())
    for c, r, x in view.ranking[: max(20, cfg.momentum.exit_rank)]:
        store.append("ranking", {"exec_day": view.exec_day, "rank": r, "coin": c, "ret_14d_pct": round(x * 100, 2),
                                 "held_paper": c in b["positions"], "held_live": c in held_live}, mirror=False)
    out["stop"] = _stop_rules(ctx, paper)
    ctx.outbox.add(daily_message(ctx, view, out, paper, mids))


def _stop_rules(ctx: Ctx, paper: dict) -> dict:
    rows = store.read("equity")
    res = {}
    if not rows:
        return res
    df = pd.DataFrame(rows)
    df["exec_day"] = pd.to_datetime(df["exec_day"])
    df = df.drop_duplicates("exec_day", keep="last").set_index("exec_day").sort_index()
    num = lambda c: pd.to_numeric(df[c], errors="coerce") if c in df else pd.Series(dtype=float)  # noqa: E731
    bench = num("bench_index")
    books = {"paper": (num("paper_equity"), num("paper_gross") / num("paper_equity"))}
    if ctx.ctrl.live:
        le = num("live_equity").dropna()
        if len(le):
            books["live"] = (le, (num("live_gross") / num("live_equity")).reindex(le.index))
    alerted = store.load_json("alerts.json", {}) or {}
    for name, (eq, expo) in books.items():
        st = stoprules.evaluate(eq, bench, ctx.cfg, exposure=expo)
        res[name] = st
        key = f"stop_{name}"
        sig = "|".join(sorted(x.split(" ")[0] for x in st.breaches))
        if st.breaches and alerted.get(key) != sig:
            ctx.outbox.add(f"🚨 <b>RMF — ATURAN BERHENTI tersentuh ({name})</b>\n\n"
                           + "\n".join(f"• {notify.esc(x)}" for x in st.breaches)
                           + "\n\n<i>Bot hanya menandai. Keputusan berhenti di tanganmu. "
                             "Tutup posisi live: gh workflow run control.yml -f momentum=flatten</i>")
        alerted[key] = sig
    store.save_json("alerts.json", alerted)
    return res


def daily_message(ctx: Ctx, view: mom.View, out: dict, paper: dict, mids: dict) -> str:
    """Ringkasan harian, tata letak mengikuti heartbeat Crypto-MEX (sementara,
    format final RMF dibahas nanti)."""
    cfg = ctx.cfg
    p = out["paper"]
    b = paper["book"]
    peak = float(b.get("peak_equity", p["equity"]))
    dd = (p["equity"] / peak - 1) * 100 if peak else 0
    ret = (p["equity"] / float(b.get("start_capital", cfg.capital_usdc)) - 1) * 100
    reg = "ON" if view.regime_on else "OFF (semua dijual, cash)"
    sells = [f"{f['coin']} ({f['reason']}, {f.get('net_pnl', 0):+.2f})" for f in p["fills"] if f["side"] == "SELL"]
    buys = [f["coin"] for f in p["fills"] if f["side"] == "BUY"]
    top = " ".join(c for c, r, _ in view.ranking[: cfg.momentum.n_hold])
    res = " ".join(c for c, r, _ in view.ranking[cfg.momentum.n_hold: cfg.momentum.exit_rank])
    t = pd.Timestamp(ctx.now).tz_convert("UTC").strftime("%Y-%m-%d %H:%M")
    lines = [
        "📊 <b>RMF forward test — momentum harian</b>",
        f"<code>{t} UTC · candle {view.last_close_day} · telat {out['delay_min']:.0f} menit</code>",
        "",
        f"  filter BTC: <b>{reg}</b> ({view.btc_close:,.0f} vs EMA50 {view.btc_ema:,.0f})",
        f"  top {cfg.momentum.n_hold}: {notify.esc(top) or '-'}",
        f"  cadangan {cfg.momentum.n_hold + 1}–{cfg.momentum.exit_rank}: {notify.esc(res) or '-'}",
        "",
        f"  paper: <b>{notify.usd(p['equity'])} USDC</b> ({ret:+.2f}% sejak mulai · DD {dd:+.1f}%)",
        f"  posisi: {len(p['positions'])} · gross {notify.usd(p['gross'])} · {notify.usd(p['per_coin'])}/koin",
    ]
    if sells:
        lines.append("  jual: " + notify.esc("; ".join(sells)))
    if buys:
        lines.append("  beli: " + notify.esc(", ".join(buys)))
    if not sells and not buys:
        lines.append("  tidak ada perubahan posisi")
    for w in p["warn"]:
        lines.append("⚠️ " + notify.esc(w))
    lines.append(f"  basket semua koin ({view.bench_n} koin, 1x): {view.bench_ret * 100:+.2f}% · "
                 f"indeks {paper['bench_index']:.4f}")
    fs = store.load_json("flush_paper.json") or {}
    if fs.get("book"):
        fb = fs["book"]
        lines.append(f"  flush paper: {len(fb['positions'])} posisi · PnL {notify.usd(bk.equity(fb, mids))} USDC")
    st = (out.get("stop") or {}).get("paper")
    if st and st.months_behind_streak:
        lines.append(f"  kalah dari basket {st.months_behind_streak} bulan berturut-turut "
                     f"(batas {cfg.stop_rules.underperform_months})")
    if out["live"] is not None:
        lines += ["", _live_message(out["live"], ctx, short=True)]
    else:
        lines.append(f"  live: mode <b>{ctx.ctrl.momentum}</b>")
    lines += ["", "<i>Pesan ini muncul 1× sehari setelah candle harian close (07:00 WIB). "
                  "Event flush dan alarm dikirim terpisah, hanya kalau ada.</i>"]
    return "\n".join(lines)


def daily_message_from_state(ctx: Ctx) -> str | None:
    """Bangun ulang ringkasan harian terakhir dari state/ (untuk kirim ulang / smoke test)."""
    vdoc = store.load_json("momentum_view.json")
    paper = store.load_json("momentum_paper.json")
    eq = [r for r in store.read("equity") if vdoc and r["exec_day"] == vdoc["exec_day"]]
    if not (vdoc and paper and eq):
        return None
    view, row = mom.View.from_dict(vdoc), eq[-1]
    fills = [{"coin": o["coin"], "side": o["side"], "reason": o["reason"], "net_pnl": float(o["pnl"] or 0)}
             for o in store.read("orders")
             if o["book"] == "paper" and o["strategy"] == "momentum" and o["exec_day"] == view.exec_day]
    equity = float(row["paper_equity"])
    out = {"delay_min": float(row["delay_min"] or 0), "live": None, "paper": {
        "equity": equity, "gross": float(row["paper_gross"]), "fills": fills, "warn": [],
        "positions": list(paper["book"]["positions"]), "per_coin": mom.per_coin_usd(equity, ctx.cfg)}}
    saved_now, ctx.now = ctx.now, dt.datetime.fromisoformat(row["time_utc"])
    try:
        return daily_message(ctx, view, out, paper, {})
    finally:
        ctx.now = saved_now


def _live_message(lv: dict, ctx: Ctx, short: bool = False) -> str:
    head = "" if short else f"🤖 <b>RMF live — {notify.wib(ctx.now)}</b>\n"
    s = (f"{head}<b>Live</b> ({lv.get('mode')}): ekuitas {notify.usd(lv.get('equity_after'))} USDC"
         f" · DD {lv.get('dd_pct', 0):+.1f}% · {len(lv.get('orders', []))} order")
    if lv.get("breaker"):
        s += f"\n🛑 Breaker DD aktif: beli baru ditahan (reset: control.yml -f reset_breaker=true)"
    for o in lv.get("orders", []):
        s += f"\n  {o['side']} {notify.esc(o['coin'])} {o['qty']} @ {o['px']} ({o['status']})"
    for e in lv.get("errors", [])[:10]:
        s += f"\n⚠️ {notify.esc(e)}"
    return s


# =========================================================================== #
#  FLUSH (4h, paper)
# =========================================================================== #
def latest_bar(now: dt.datetime, run_after_min: int) -> pd.Timestamp:
    """Waktu open candle 4h terakhir yang sudah close (UTC, tz-aware)."""
    t = pd.Timestamp(now).tz_convert("UTC") - pd.Timedelta(minutes=run_after_min)
    return t.floor("4h") - H4


def _symbols(cfg) -> list:
    f = cfg.flush
    p = path_in_repo(f.spot_universe_file if f.signal_source == "binance_spot" else f.futures_universe_file)
    with open(p, encoding="utf-8") as fh:
        return [x.strip() for x in fh if x.strip() and not x.startswith("#")]


def run_flush(ctx: Ctx) -> dict | None:
    cfg = ctx.cfg
    if ctx.ctrl.flush == "off" or not started(cfg, ctx.now):
        return None
    bar = latest_bar(ctx.now, cfg.momentum.run_after_minutes)
    st = store.load_json("flush_paper.json") or {"book": bk.new_book(0.0), "last_bar": None, "events": 0}
    if st.get("last_bar") == bar.isoformat():
        return None
    t = ctx.now.isoformat(timespec="seconds")
    out = {"bar": bar.isoformat(), "exits": [], "event": False, "opened": [], "rejected": []}
    out["exits"] = _flush_exits(ctx, st, t)

    # ---- sinyal di bar yang baru close
    sig, n_sym = [], 0
    for sym in _symbols(cfg):
        try:
            k = ctx.klines.klines(sym, "4h", max(cfg.flush.bb_len, cfg.flush.vol_len) + 40)
        except Exception as e:  # noqa: BLE001
            ctx.say(f"[flush] {sym} gagal ({type(e).__name__})")
            continue
        # Data bisa sudah memuat candle yang lebih baru dari `bar` (mis. run tepat
        # setelah close, sebelum jeda run_after habis): nilai sinyal DI bar itu.
        if not k.empty:
            k = k[pd.DatetimeIndex(k["ts"]) <= bar]
        if k.empty or pd.Timestamp(k["ts"].iloc[-1]) != bar:
            continue
        n_sym += 1
        if fl.signal_at_last(k, cfg):
            sig.append(sym)
    event = len(sig) >= cfg.flush.min_coins
    out.update(n_signals=len(sig), n_symbols=n_sym, event=event, signals=sig)
    store.append("flush_signals", {"bar_utc": bar.isoformat(), "time_utc": t, "n_signals": len(sig),
                                   "n_symbols": n_sym, "event": event, "coins": " ".join(sig)},
                 mirror=event)
    if n_sym < 0.8 * len(_symbols(cfg)):
        ctx.say(f"[flush] hanya {n_sym} simbol punya candle {bar}; sumber data bermasalah?")
    if event:
        _flush_event(ctx, st, bar, sig, out, t)
    st["last_bar"] = bar.isoformat()
    store.save_json("flush_paper.json", st)
    return out


def _flush_exits(ctx: Ctx, st: dict, t: str) -> list:
    cfg = ctx.cfg
    b = st["book"]
    done = []
    now_ms = int(ctx.now.timestamp() * 1000)
    for coin in list(b["positions"]):
        p = b["positions"][coin]
        start = pd.Timestamp(p["entry_bar"])
        try:
            bars = ctx.info.candles(coin, "4h", int(start.value // 10**6))
        except Exception as e:  # noqa: BLE001
            ctx.say(f"[flush] candle {coin} gagal ({type(e).__name__}); exit dicek siklus berikutnya")
            continue
        ex, p2 = fl.check_exit(p, bars, cfg.flush.max_bars)
        b["positions"][coin].update(p2)
        if not ex:
            continue
        try:
            rates = ctx.info.funding_history(coin, int(pd.Timestamp(p["entry_time"]).value // 10**6),
                                             min(now_ms, int(pd.Timestamp(ex["exit_time"]).value // 10**6)))
        except Exception:  # noqa: BLE001
            rates = []
        fund = bk.funding_cost(p["qty"], p["entry_px"], rates)
        bk.charge_funding(b, coin, fund)
        f = bk.close(b, coin, ex["exit_px"], cfg.costs, exact_px=ex["exit_px"])
        pos = f["position"]
        fees = pos.get("fees", 0) + f["fee"]
        net = f["pnl"] - fees - fund
        row = {"entry_time": pos["entry_time"], "exit_time": ex["exit_time"], "coin": coin,
               "signal_bar": pos.get("signal_bar"), "entry_px": pos["entry_px"], "exit_px": f["px"],
               "stop": pos["stop"], "target": pos["target"], "qty": pos["qty"], "notional": pos["qty"] * pos["entry_px"],
               "risk_usd": pos["risk_usd"], "forced_min": pos.get("forced_min"), "bars_held": pos.get("bars_held"),
               "reason": ex["reason"], "pnl_gross": f["pnl"], "fees": fees, "funding": fund, "pnl_net": net,
               "r_multiple": net / pos["risk_usd"] if pos.get("risk_usd") else ""}
        store.append("flush_trades", row)
        store.append("orders", {"time_utc": t, "book": "paper", "strategy": "flush", "exec_day": ex["exit_bar"],
                                "coin": coin, "side": "SELL", "qty": pos["qty"], "px": f["px"], "mid": "",
                                "notional": f["notional"], "fee": f["fee"], "pnl": net, "reason": ex["reason"],
                                "status": "paper"})
        done.append(row)
    if done:
        tot = sum(r["pnl_net"] for r in done)
        lines = [f"🌊 <b>RMF flush (paper) — exit {len(done)}</b> · {tot:+.2f} USDC"]
        for r in done:
            rm = r["r_multiple"]
            rtxt = f" ({rm:+.2f}R)" if rm != "" else ""
            lines.append(f"  {notify.esc(r['coin'])}: {r['reason']} · {r['pnl_net']:+.2f} USDC{rtxt}")
        ctx.outbox.add("\n".join(lines))
    return done


def _flush_event(ctx: Ctx, st: dict, bar: pd.Timestamp, sig: list, out: dict, t: str) -> None:
    cfg = ctx.cfg
    b = st["book"]
    meta = ctx.meta()
    names = {}
    for s in sig:
        h = fl.hype_name(s)
        if h in meta and not meta[h]["isDelisted"] and h not in b["positions"]:
            names[h] = s
    chosen = fl.pick(list(names), bar, cfg.flush.max_coins)
    mids = ctx.info.all_mids()
    now_ms = int(ctx.now.timestamp() * 1000)
    cands = []
    for c in chosen:
        try:
            k = ctx.info.candles(c, "4h", now_ms - cfg.flush.atr_history_bars * 4 * 3_600_000)
            a, _ = fl.atr_at(k, bar, cfg.flush.atr_len)
        except Exception as e:  # noqa: BLE001
            ctx.say(f"[flush] ATR {c} gagal ({type(e).__name__})")
            a = float("nan")
        cands.append((c, mids.get(c, float("nan")), a))
    # ekuitas gabungan (momentum paper + PnL flush), seperti simulasi akun di riset
    mp = store.load_json("momentum_paper.json") or {}
    mbook = mp.get("book") or bk.new_book(cfg.capital_usdc)
    eq = bk.equity(mbook, mids) + bk.equity(b, mids)
    gross_used = bk.gross(mbook, mids) + bk.gross(b, mids)
    plans, rej = fl.size_event(cands, eq, gross_used, cfg)
    entry_bar = bar + H4
    late = pd.Timestamp(ctx.now).tz_convert("UTC") - entry_bar > pd.Timedelta(minutes=15)
    for pl in plans:
        qty = pl.notional / pl.entry_px
        f = bk.buy(b, pl.coin, qty, pl.entry_px, cfg.costs, t, extra={
            "entry_bar": entry_bar.isoformat(), "signal_bar": bar.isoformat(), "stop": pl.stop,
            "target": pl.target, "atr": pl.atr, "risk_usd": pl.risk_usd, "forced_min": pl.forced_min,
            # entry telat: candle entry sebagian sudah lewat sebelum masuk, jadi
            # range-nya tidak dipakai untuk SL/TP; dihitung mulai candle berikutnya.
            "last_bar": entry_bar.isoformat() if late else None, "bars_held": 1 if late else 0})
        store.append("orders", {"time_utc": t, "book": "paper", "strategy": "flush", "exec_day": bar.isoformat(),
                                "coin": pl.coin, "side": "BUY", "qty": qty, "px": f["px"], "mid": pl.entry_px,
                                "notional": f["notional"], "fee": f["fee"], "pnl": 0.0,
                                "reason": f"event {len(sig)} koin", "status": "paper"})
    st["events"] = int(st.get("events", 0)) + 1
    out["opened"] = [p.coin for p in plans]
    out["rejected"] = rej
    lines = [f"🌊 <b>RMF flush EVENT (paper)</b> — {len(sig)} koin bersinyal",
             f"<code>candle 4h {notify.wib(bar)} · sumber {cfg.flush.signal_source}</code>",
             f"Ekuitas gabungan {notify.usd(eq)} USDC · risiko {cfg.flush.risk_pct:g}%/koin",
             "Masuk: " + (notify.esc(", ".join(f"{p.coin} ({p.notional:.0f}$)" for p in plans)) or "-")]
    if rej:
        lines.append("Ditolak: " + notify.esc("; ".join(f"{c}: {w}" for c, w in rej)))
    ctx.outbox.add("\n".join(lines))


def agent_key() -> str:
    return os.environ.get("RMF_AGENT_KEY", "").strip()
