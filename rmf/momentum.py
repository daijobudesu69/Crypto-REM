"""Rotasi momentum harian — logika murni, tanpa jaringan.

Disalin dari `research/hl_full.py::momentum_hl` dan `research/buffer_test.py`
(versi final N=10, keluar > 15), lalu dipecah supaya satu hari bisa diputuskan
dari posisi yang BENAR-BENAR dipegang (bukan posisi model), karena di live order
bisa gagal.

Urutan satu hari (dieksekusi setelah candle harian D-1 close, di open hari D):
  1. filter rezim: close BTC (D-1) > EMA50 close BTC. Kalau tidak -> jual semua.
  2. eligible: koin di universe dengan >= 60 candle harian dan close D-1 ada.
  3. peringkat: return 14 hari = close(D-1) / close(D-15) - 1, tertinggi = 1.
  4. jual yang peringkatnya > 15 (atau tidak eligible lagi).
  5. isi slot kosong sampai 10 dengan peringkat 1..10 yang belum dipegang.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators as ind


@dataclass
class View:
    """Gambaran pasar satu hari: rezim + peringkat semua koin eligible.

    Disimpan ke state/momentum_view.json supaya percobaan ulang live di hari
    yang sama memakai peringkat yang SAMA dengan buku paper, tanpa fetch ulang.
    """
    exec_day: str                 # tanggal UTC hari eksekusi (open hari ini)
    last_close_day: str           # candle harian terakhir yang dipakai
    regime_on: bool
    btc_close: float
    btc_ema: float
    ranking: list                 # [(coin, rank, ret)] eligible saja, urut rank
    universe_size: int = 0
    bench_ret: float = 0.0        # return basket "beli semua koin" open(E-1) -> open(E), 1x
    bench_n: int = 0              # jumlah koin di basket

    def ranks(self) -> dict:
        return {c: int(r) for c, r, _ in self.ranking}

    def to_dict(self) -> dict:
        return {**self.__dict__, "ranking": [[c, int(r), float(x)] for c, r, x in self.ranking]}

    @classmethod
    def from_dict(cls, d: dict) -> "View":
        d = dict(d)
        d["ranking"] = [tuple(x) for x in d["ranking"]]
        return cls(**d)


@dataclass
class Rebalance:
    target: list
    sells: list = field(default_factory=list)   # [(coin, alasan)]
    buys: list = field(default_factory=list)    # [coin] urut peringkat


def naive_day(x) -> pd.Timestamp:
    """Tanggal UTC tanpa zona waktu (00:00)."""
    t = pd.Timestamp(x)
    if t.tzinfo is not None:
        t = t.tz_convert("UTC").tz_localize(None)
    return t.normalize()


def qv30(df: pd.DataFrame, days: int = 30) -> float:
    """Volume notional N hari terakhir, rumus sama dengan builder universe riset."""
    if df is None or df.empty:
        return 0.0
    t = df.tail(days)
    return float((t["volume"] * (t["open"] + t["high"] + t["low"] + t["close"]) / 4).sum())


def static_universe(cfg) -> list:
    from .config import path_in_repo
    with open(path_in_repo(cfg.universe.static_file), encoding="utf-8") as fh:
        return [x.strip() for x in fh if x.strip() and not x.startswith("#")]


def select_universe(candles: dict, meta: dict, cfg) -> list:
    """Koin universe yang masih hidup, urut volume (urutan ini memecah seri peringkat).

    static : daftar riset (config/hype_universe.txt), dikurangi yang delist / tanpa data.
    rolling: top-N perp belum delist, tanpa stablecoin, urut volume 30 hari.
    """
    u = cfg.universe
    if u.mode == "static":
        return [c for c in static_universe(cfg)
                if c in candles and c in meta and not meta[c].get("isDelisted")]
    rows = []
    for coin, df in candles.items():
        m = meta.get(coin, {})
        if m.get("isDelisted") or coin in u.exclude:
            continue
        rows.append((coin, qv30(df, u.volume_days)))
    rows.sort(key=lambda x: -x[1])
    return [c for c, _ in rows[: u.top_n]]


def closed_only(candles: dict, last_day: pd.Timestamp) -> dict:
    """Buang candle yang belum close (tanggal > last_day)."""
    out = {}
    for c, df in candles.items():
        if df is None or df.empty:
            out[c] = df
            continue
        d = pd.DatetimeIndex(df["ts"]).tz_convert(None).normalize()
        out[c] = df[d <= last_day].reset_index(drop=True)
    return out


def close_panel(candles: dict, coins: list, last_day: pd.Timestamp) -> pd.DataFrame:
    """Tabel close harian (index = tanggal UTC kontinu, kolom = koin, urut universe)."""
    cols = {}
    for c in coins:
        df = candles.get(c)
        if df is None or df.empty:
            continue
        s = pd.Series(df["close"].values.astype(float), index=pd.DatetimeIndex(df["ts"]).tz_convert(None).normalize())
        cols[c] = s[~s.index.duplicated(keep="last")]
    if not cols:
        return pd.DataFrame()
    p = pd.DataFrame(cols)
    p = p[p.index <= last_day]
    if p.empty:
        return p
    full = pd.date_range(p.index.min(), last_day, freq="D")
    return p.reindex(full)[[c for c in coins if c in p.columns]]


def regime(btc: pd.DataFrame, last_day: pd.Timestamp, ema_len: int) -> tuple[bool, float, float]:
    s = pd.Series(btc["close"].values.astype(float), index=pd.DatetimeIndex(btc["ts"]).tz_convert(None).normalize())
    s = s[~s.index.duplicated(keep="last")]
    s = s[s.index <= last_day]
    if s.empty or s.index[-1] != last_day:
        raise ValueError(f"candle BTC untuk {last_day.date()} belum ada; data belum final")
    e = ind.ema(s.values, ema_len)
    close, ema_v = float(s.iloc[-1]), float(e[-1])
    if not np.isfinite(ema_v):
        return False, close, ema_v
    return close > ema_v, close, ema_v


def rank_coins(panel: pd.DataFrame, lookback: int, min_hist: int) -> pd.DataFrame:
    if panel.empty or len(panel) < lookback + 1:
        return pd.DataFrame(columns=["coin", "rank", "ret"])
    age = panel.notna().sum()
    last = panel.iloc[-1]
    prev = panel.iloc[-1 - lookback]
    need = max(min_hist, lookback + 30)          # riset: age >= 60 dan age >= L + 30
    ok = (age >= need) & last.notna() & prev.notna()
    ret = (last / prev - 1)[ok]
    # method="first": seri diurutkan menurut urutan kolom (urutan universe), sama dengan riset
    rk = ret.rank(ascending=False, method="first")
    out = pd.DataFrame({"coin": ret.index, "rank": rk.values.astype(int), "ret": ret.values})
    return out.sort_values("rank").reset_index(drop=True)


def bench_members(candles: dict, universe: list, exec_day, min_hist: int) -> dict:
    """Anggota basket untuk periode open(E-1) -> open(E), dengan E = hari eksekusi.

    Definisi riset (xsec_hl.py): eligible di close t = E-2 (>= min_hist candle dan
    close ada), return r = open(t+2) / open(t+1) - 1. Butuh candle hari ini
    (include_open) untuk open(E). Return {coin: (open E-1, open E)}.
    """
    e = naive_day(exec_day)
    d1, d2 = e - pd.Timedelta(days=1), e - pd.Timedelta(days=2)
    out = {}
    for c in universe:
        df = candles.get(c)
        if df is None or df.empty:
            continue
        d = pd.DatetimeIndex(df["ts"]).tz_convert(None).normalize()
        o = pd.Series(df["open"].values.astype(float), d)
        cl = pd.Series(df["close"].values.astype(float), d)
        if (d <= d2).sum() < min_hist or d2 not in cl.index or not np.isfinite(cl.get(d2, np.nan)):
            continue
        if d1 in o.index and e in o.index and o[d1] > 0 and np.isfinite(o[e]):
            out[c] = (float(o[d1]), float(o[e]))
    return out


def bench_return(members: dict, funding: dict | None = None) -> float:
    """Rata-rata bobot sama (open E / open E-1 - 1 - funding), eksposur 1x."""
    funding = funding or {}
    r = [b / a - 1 - funding.get(c, 0.0) for c, (a, b) in members.items()]
    return float(np.mean(r)) if r else 0.0


def market_view(candles: dict, meta: dict, exec_day, cfg, funding: dict | None = None) -> View:
    """candles boleh memuat candle hari ini yang belum close (dipakai hanya untuk
    open basket); peringkat dan rezim hanya memakai candle sampai exec_day - 1."""
    m = cfg.momentum
    exec_day = naive_day(exec_day)
    last_day = exec_day - pd.Timedelta(days=1)
    if m.regime_symbol not in candles:
        raise ValueError(f"candle {m.regime_symbol} tidak ada")
    closed = closed_only(candles, last_day)
    on, btc_c, btc_e = regime(closed[m.regime_symbol], last_day, m.regime_ema)
    universe = select_universe(closed, meta, cfg)
    panel = close_panel(closed, universe, last_day)
    ranking = rank_coins(panel, m.lookback_days, m.min_history_days)
    members = bench_members(candles, universe, exec_day, m.min_history_days)
    return View(exec_day=str(exec_day.date()), last_close_day=str(last_day.date()), regime_on=bool(on),
                btc_close=btc_c, btc_ema=btc_e,
                ranking=[(c, int(r), float(x)) for c, r, x in ranking[["coin", "rank", "ret"]].itertuples(index=False)],
                universe_size=len(universe), bench_ret=bench_return(members, funding),
                bench_n=len(members))


def rebalance(view: View, held: list, cfg) -> Rebalance:
    """Aturan buffer: jual peringkat > exit_rank, isi slot dengan peringkat 1..n_hold."""
    m = cfg.momentum
    rk = view.ranks()
    held = list(dict.fromkeys(held))
    if not view.regime_on:
        return Rebalance(target=[], sells=[(c, "filter BTC OFF") for c in held])
    sells, keep = [], []
    for c in held:
        r = rk.get(c)
        if r is None:
            sells.append((c, "tidak eligible / keluar universe"))
        elif r > m.exit_rank:
            sells.append((c, f"peringkat {r} > {m.exit_rank}"))
        else:
            keep.append(c)
    free = m.n_hold - len(keep)
    buys = []
    for c, r, _ in view.ranking:
        if free <= 0 or r > m.n_hold:
            break
        if c not in keep:
            buys.append(c)
            free -= 1
    return Rebalance(target=keep + buys, sells=sells, buys=buys)


def per_coin_usd(equity: float, cfg) -> float:
    """Ekuitas x 0,5 / 10, minimal 10 USDC (minimum order HYPE)."""
    m = cfg.momentum
    return max(equity * m.gross_exposure / m.n_hold, m.min_order_usdc)


def order_size(usd: float, px: float, sz_decimals: int, min_usd: float) -> float:
    """Ukuran koin dibulatkan ke szDecimals, dan notional tidak pernah < minimum.

    Dibulatkan ke terdekat; kalau hasilnya jatuh di bawah minimum (+0,5% buffer
    untuk pergerakan harga sampai order masuk), dibulatkan ke ATAS.
    """
    if px <= 0:
        raise ValueError("harga harus > 0")
    q = 10 ** sz_decimals
    sz = round(usd / px * q) / q
    floor_usd = min_usd * 1.005
    if sz * px < floor_usd:
        sz = math.ceil(floor_usd / px * q - 1e-9) / q
    return sz
