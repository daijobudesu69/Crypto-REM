"""Free-data-only signal library (no OI, no funding, no long/short ratio, no premium as signals).

Data lake: C:\\Crypto data\\backtest data and more\\data  (read-only, never re-downloaded here).
All values at row t use only information available at the CLOSE of bar t (bar ts = open time).
Entries happen at the OPEN of bar t+1.

Funding is loaded ONLY as a cost (cum_funding) for PnL, never as a signal.

Every trigger / state carries a data tag (DATA_TAG) describing whether it can be reproduced
live for free:
    ohlcv      - candles only (free on every exchange, incl. Hyperliquid API/websocket)
    taker      - taker buy volume (free in Binance klines; on Hyperliquid you must record it
                 yourself from the free trades websocket - not in HL candles)
    cross      - cross-section of all coins' candles (free, but you must poll ~150 coins)
    macro      - free external API (alternative.me Fear & Greed, DefiLlama stablecoins)
"""
import os, sys
import numpy as np, pandas as pd
from numba import njit

LAKE = r"C:\Crypto data\backtest data and more"
DATA = os.path.join(LAKE, "data")
sys.path.append(os.path.join(LAKE, "research"))  # append: local modules win over same-named lake ones
import features as F  # reuse indicator helpers (ema, rsi, atr, adx, _smc, _supertrend, session_vwap, ...)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
TF_DELTA = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}
BPD = {"15m": 96, "1h": 24, "4h": 6, "1d": 1}
HL_MAP = {"1000PEPEUSDT": "kPEPE", "1000SHIBUSDT": "kSHIB", "1000BONKUSDT": "kBONK", "1000FLOKIUSDT": "kFLOKI"}

PAID_EXCLUDED = ["oi_usd", "funding_rate (as signal)", "global_ls / top_pos_ls", "premium index"]


def universe():
    return list(pd.read_csv(os.path.join(DATA, "universe", "binance_um_top150.csv"))["symbol"])


def _ns(s):
    return pd.Series(s).astype("datetime64[ns, UTC]")


def load(symbol, tf, venue="binance"):
    """Candles + cumulative funding (COST ONLY)."""
    if venue == "binance":
        k = pd.read_parquet(os.path.join(DATA, "binance", "um", "klines", tf, f"{symbol}.parquet"))
        fpath = os.path.join(DATA, "binance", "um", "funding", f"{symbol}.parquet")
    else:
        k = pd.read_parquet(os.path.join(DATA, "hyperliquid", "candles", tf, f"{symbol}.parquet"))
        fpath = os.path.join(DATA, "hyperliquid", "funding", f"{symbol}.parquet")
    if "n_bars" in k:
        full = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}[tf]
        k = k[(k["n_bars"] >= 0.8 * full) | (k.index == k.index[-1])]
    k = k.reset_index(drop=True)
    k["ts"] = _ns(k["ts"])
    k["close_time"] = k["ts"] + pd.Timedelta(TF_DELTA[tf])
    k["cum_funding"] = 0.0
    if os.path.exists(fpath):
        f = pd.read_parquet(fpath)[["ts", "funding_rate"]].dropna().sort_values("ts")
        f["cum"] = f["funding_rate"].cumsum()
        f["ts"] = _ns(f["ts"])
        m = pd.merge_asof(pd.DataFrame({"t": k["close_time"]}), f.rename(columns={"ts": "t"})[["t", "cum"]],
                          on="t", direction="backward")
        k["cum_funding"] = m["cum"].fillna(0).values
    if "taker_buy_volume" not in k:
        k["taker_buy_volume"] = np.nan
    return k


# ------------------------------------------------------------------ context (cross-section + macro)
_CTX = {}


def ctx(tf):
    """Series keyed by bar close time: breadth (share of coins > own EMA50), BTC 1-day return,
    per-coin 7-day-return percentile rank (wide), Fear & Greed, stablecoin 30d growth."""
    if tf in _CTX:
        return _CTX[tf]
    p = os.path.join(OUT, f"ctx_{tf}.parquet"); pr = os.path.join(OUT, f"rank_{tf}.parquet")
    if not os.path.exists(p):
        build_ctx(tf)
    c = pd.read_parquet(p); r = pd.read_parquet(pr)
    _CTX[tf] = (c, r)
    return _CTX[tf]


def build_ctx(tf):
    bpd = BPD[tf]
    closes, above = {}, {}
    for s in universe():
        fp = os.path.join(DATA, "binance", "um", "klines", tf, f"{s}.parquet")
        if not os.path.exists(fp):
            continue
        k = pd.read_parquet(fp, columns=["ts", "close"])
        t = _ns(k["ts"]).values + pd.Timedelta(TF_DELTA[tf])
        cl = pd.Series(k["close"].values.astype(float), index=t)
        cl = cl[~cl.index.duplicated()]
        closes[s] = cl
        e = pd.Series(F.ema(cl.values, 50), index=cl.index)
        above[s] = (cl > e).astype(float).where(e.notna())
    C = pd.DataFrame(closes).sort_index()
    A = pd.DataFrame(above).reindex(C.index)
    n = A.notna().sum(1)
    breadth = (A.sum(1) / n).where(n >= 20)
    ret7 = C / C.shift(7 * bpd, fill_value=np.nan) - 1  # bars are aligned on the union index
    # use only coins with a value; ffill limit to avoid stale prices of halted coins
    ret7 = ret7.where(C.notna())
    rank = ret7.rank(axis=1, pct=True)
    btc = C["BTCUSDT"]
    out = pd.DataFrame({"breadth": breadth, "btc_ret1d": btc / btc.shift(bpd) - 1,
                        "btc_ret7d": btc / btc.shift(7 * bpd) - 1})
    # macro (daily value assumed known only at the END of its day -> shift 1 day)
    fg = pd.read_parquet(os.path.join(DATA, "macro", "fear_greed.parquet"))
    fg = pd.Series(fg["fear_greed"].values.astype(float), index=_ns(fg["ts"]).values + pd.Timedelta("1D")).sort_index()
    sc = pd.read_parquet(os.path.join(DATA, "macro", "stablecoin_mcap.parquet"))
    sc = pd.Series(sc["stablecoin_mcap_usd"].values.astype(float), index=_ns(sc["ts"]).values + pd.Timedelta("1D")).sort_index()
    sc30 = sc / sc.shift(30) - 1
    idx = pd.DataFrame({"t": out.index})
    for name, ser in (("fear_greed", fg), ("fg_ma30", fg.rolling(30).mean()), ("stable_30d", sc30)):
        m = pd.merge_asof(idx, ser.rename("v").rename_axis("t").reset_index(), on="t", direction="backward")
        out[name] = m["v"].values
    out.index.name = "t"
    out.reset_index().to_parquet(os.path.join(OUT, f"ctx_{tf}.parquet"), index=False)
    rank.astype("float32").rename_axis("t").reset_index().to_parquet(os.path.join(OUT, f"rank_{tf}.parquet"), index=False)


def _map_ctx(k, tf, symbol):
    c, r = ctx(tf)
    left = pd.DataFrame({"t": k["close_time"].dt.tz_convert(None).values.astype("datetime64[ns]")})
    cc = c.copy(); cc["t"] = cc["t"].values.astype("datetime64[ns]")
    m = pd.merge(left, cc, on="t", how="left")
    if symbol in r.columns:
        rr = r[["t", symbol]].copy(); rr["t"] = rr["t"].values.astype("datetime64[ns]")
        m["rank7"] = pd.merge(left, rr, on="t", how="left")[symbol].values
    else:
        m["rank7"] = np.nan
    return m


# ------------------------------------------------------------------ extra indicators
@njit(cache=True)
def _psar(h, l, step, mx):
    n = len(h); d = np.ones(n); sar = np.full(n, np.nan)
    if n < 3:
        return d
    up = True; af = step; ep = h[0]; s = l[0]
    for i in range(1, n):
        s = s + af * (ep - s)
        if up:
            s = min(s, l[i - 1], l[i - 2] if i >= 2 else l[i - 1])
            if l[i] < s:
                up = False; s = ep; ep = l[i]; af = step
            elif h[i] > ep:
                ep = h[i]; af = min(af + step, mx)
        else:
            s = max(s, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if h[i] > s:
                up = True; s = ep; ep = h[i]; af = step
            elif l[i] < ep:
                ep = l[i]; af = min(af + step, mx)
        d[i] = 1.0 if up else -1.0; sar[i] = s
    return d


def _flip(x):
    p = np.roll(x, 1); p[0] = x[0]
    return (x == 1) & (p == -1), (x == -1) & (p == 1)


def _period_hl(ts, h, l, rule):
    """previous completed period's high/low (rule 'D' or 'W')."""
    key = ts.dt.floor("D") if rule == "D" else (ts - pd.to_timedelta(ts.dt.dayofweek, unit="D")).dt.floor("D")
    key = key.dt.tz_convert(None) if key.dt.tz is not None else key
    g = pd.DataFrame({"k": key.values, "h": h, "l": l}).groupby("k").agg(hh=("h", "max"), ll=("l", "min"))
    ph = key.map(g["hh"].shift(1)).values; pl = key.map(g["ll"].shift(1)).values
    return ph, pl


def _vwap_month(ts, h, l, c, v):
    tp = (h + l + c) / 3
    key = ts.dt.tz_convert(None).dt.to_period("M").astype(str).values
    df = pd.DataFrame({"k": key, "pv": tp * v, "v": v})
    g = df.groupby("k")
    return g["pv"].cumsum().values / np.where(g["v"].cumsum().values > 0, g["v"].cumsum().values, np.nan)


def htf(k, rule, func):
    return F.htf_series(k, rule, func)


# ------------------------------------------------------------------ signal library
DATA_TAG = {}


def signals(k, tf, symbol=None):
    o, h, l, c, v = (k[x].values.astype(float) for x in ["open", "high", "low", "close", "volume"])
    ts = k["ts"]; n = len(c); bpd = BPD[tf]
    T, S = {}, {}
    tag = DATA_TAG
    nb = lambda x: (x, x)

    def addT(name, pair, t="ohlcv"):
        T[name] = pair; tag[name] = t

    def addS(name, pair, t="ohlcv"):
        S[name] = pair; tag[name] = t

    e8, e9, e13, e20, e21, e34, e50, e55, e200 = (F.ema(c, x) for x in (8, 9, 13, 20, 21, 34, 50, 55, 200))
    s50, s200 = F.sma(c, 50), F.sma(c, 200)
    a14 = F.atr(h, l, c, 14)
    r14, r2 = F.rsi(c, 14), F.rsi(c, 2)
    ad, pdi, mdi = F.adx(h, l, c, 14)
    macd = F.ema(c, 12) - F.ema(c, 26)
    msig = pd.Series(macd).ewm(span=9, adjust=False).mean().values
    mid, sd20 = F.sma(c, 20), pd.Series(c).rolling(20).std().values
    bbu, bbl = mid + 2 * sd20, mid - 2 * sd20
    kcu, kcl = e20 + 1.5 * a14, e20 - 1.5 * a14
    st = F._supertrend(h, l, c, F.atr(h, l, c, 10), 3.0)
    vwd, vsd = F.session_vwap(ts, h, l, c, v, "D")
    vww, _ = F.session_vwap(ts, h, l, c, v, "W")
    vwm = _vwap_month(ts, h, l, c, v)
    vsma = F.sma(v, 20)
    tb = k["taker_buy_volume"].values.astype(float)
    delta = 2 * tb - v
    dz = F.zscore(delta, 100)
    # taker buy share has a persistent venue bias (< 50%) -> work with delta detrended vs its own 200-bar mean
    delta_dt = delta - pd.Series(delta).rolling(200, min_periods=50).mean().values
    cvd = np.nancumsum(np.nan_to_num(delta_dt))
    obv = np.cumsum(np.sign(np.diff(c, prepend=c[0])) * v)
    tp = (h + l + c) / 3
    dtp = np.diff(tp, prepend=np.nan)
    mf = tp * v
    mfi = 100 - 100 / (1 + pd.Series(np.where(dtp > 0, mf, 0)).rolling(14).sum().values /
                       pd.Series(np.where(dtp < 0, mf, 0)).rolling(14).sum().replace(0, np.nan).values)
    ll14, hh14 = pd.Series(l).rolling(14).min().values, pd.Series(h).rolling(14).max().values
    stk = 100 * (c - ll14) / (hh14 - ll14); std_ = F.sma(stk, 3)
    wr = -100 * (hh14 - c) / (hh14 - ll14)
    tps = pd.Series(tp)
    cci = ((tps - tps.rolling(20).mean()) / (0.015 * tps.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True))).values
    bos_u, bos_d, ch_u, ch_d, sw_u, sw_d, fvg_l, fvg_s, ob_l, ob_s, trend = F._smc(o, h, l, c, 2)
    pdh, pdl = _period_hl(ts, h, l, "D")
    pwh, pwl = _period_hl(ts, h, l, "W")
    body = np.abs(c - o); rng = np.maximum(h - l, 1e-12)
    lw = np.minimum(o, c) - l; uw = h - np.maximum(o, c)
    # ichimoku
    tenkan = (pd.Series(h).rolling(9).max() + pd.Series(l).rolling(9).min()).values / 2
    kijun = (pd.Series(h).rolling(26).max() + pd.Series(l).rolling(26).min()).values / 2
    spa = pd.Series((tenkan + kijun) / 2).shift(26).values
    spb = pd.Series((pd.Series(h).rolling(52).max() + pd.Series(l).rolling(52).min()).values / 2).shift(26).values
    ctop, cbot = np.fmax(spa, spb), np.fmin(spa, spb)
    psar = _psar(h, l, 0.02, 0.2)
    # heikin ashi
    hac = (o + h + l + c) / 4
    hao = np.empty(n); hao[0] = (o[0] + c[0]) / 2
    for i in range(1, n):
        hao[i] = (hao[i - 1] + hac[i - 1]) / 2
    hadir = np.where(hac >= hao, 1.0, -1.0)
    ha3 = pd.Series(hadir).shift(1).rolling(3).sum().values

    # ================= triggers =================
    # --- moving averages
    addT("ema_x_9_21", (F.cross_up(e9, e21), F.cross_dn(e9, e21)))
    addT("ema_x_20_50", (F.cross_up(e20, e50), F.cross_dn(e20, e50)))
    addT("ema_x_50_200", (F.cross_up(e50, e200), F.cross_dn(e50, e200)))
    addT("sma_x_50_200", (F.cross_up(s50, s200), F.cross_dn(s50, s200)))
    addT("price_x_ema50", (F.cross_up(c, e50), F.cross_dn(c, e50)))
    addT("price_x_ema200", (F.cross_up(c, e200), F.cross_dn(c, e200)))
    rib_up = (e8 > e13) & (e13 > e21) & (e21 > e34) & (e34 > e55)
    rib_dn = (e8 < e13) & (e13 < e21) & (e21 < e34) & (e34 < e55)
    addT("ma_ribbon_align", (rib_up & ~np.roll(rib_up, 1), rib_dn & ~np.roll(rib_dn, 1)))
    addT("ema20_pullback", ((l <= e20) & (c > e20) & (e20 > e50) & (e50 > e200),
                            (h >= e20) & (c < e20) & (e20 < e50) & (e50 < e200)))
    # --- trend / momentum
    addT("supertrend_flip", _flip(st))
    addT("psar_flip", _flip(psar))
    addT("ha_flip", ((hadir == 1) & (ha3 == -3), (hadir == -1) & (ha3 == 3)))
    addT("donchian_20", (F.cross_up(c, F.rmax(h, 20)), F.cross_dn(c, F.rmin(l, 20))))
    addT("donchian_55", (F.cross_up(c, F.rmax(h, 55)), F.cross_dn(c, F.rmin(l, 55))))
    addT("macd_x", (F.cross_up(macd, msig), F.cross_dn(macd, msig)))
    addT("macd_zero_x", (F.cross_up(macd, 0), F.cross_dn(macd, 0)))
    addT("adx_di_x", (F.cross_up(pdi, mdi) & (ad > 20), F.cross_dn(pdi, mdi) & (ad > 20)))
    addT("ichi_tk_x", (F.cross_up(tenkan, kijun) & (c > ctop), F.cross_dn(tenkan, kijun) & (c < cbot)))
    addT("ichi_kumo_break", (F.cross_up(c, ctop), F.cross_dn(c, cbot)))
    # --- oscillators / mean reversion
    addT("rsi_30_70_rev", (F.cross_up(r14, 30), F.cross_dn(r14, 70)))
    addT("rsi_50_x", (F.cross_up(r14, 50), F.cross_dn(r14, 50)))
    addT("rsi2_extreme", (F.cross_dn(r2, 10), F.cross_up(r2, 90)))
    lo20, hi20 = F.rmin(c, 20), F.rmax(c, 20)
    addT("rsi_divergence", ((c < lo20) & (r14 > F.rmin(r14, 20) + 5), (c > hi20) & (r14 < F.rmax(r14, 20) - 5)))
    addT("stoch_rev", (F.cross_up(stk, std_) & (std_ < 20), F.cross_dn(stk, std_) & (std_ > 80)))
    addT("willr_rev", (F.cross_up(wr, -80), F.cross_dn(wr, -20)))
    addT("cci_rev", (F.cross_up(cci, -100), F.cross_dn(cci, 100)))
    addT("mfi_rev", (F.cross_up(mfi, 20), F.cross_dn(mfi, 80)))
    zc = F.zscore(c, 50)
    addT("zscore_revert", (F.cross_up(zc, -2), F.cross_dn(zc, 2)))
    # --- volatility
    addT("bb_revert", (F.cross_up(c, bbl), F.cross_dn(c, bbu)))
    addT("bb_breakout", (F.cross_up(c, bbu), F.cross_dn(c, bbl)))
    addT("keltner_breakout", (F.cross_up(c, kcu), F.cross_dn(c, kcl)))
    sq = (bbu < kcu) & (bbl > kcl)
    fire = (pd.Series(sq).rolling(6).sum().shift(1).values >= 6) & ~sq
    addT("squeeze_fire", (fire & (c > mid), fire & (c < mid)))
    nr7 = (h - l) <= pd.Series(h - l).rolling(7).min().values
    pnr7 = np.roll(nr7, 1); pnr7[0] = False
    ph, pl = np.roll(h, 1), np.roll(l, 1)
    addT("nr7_breakout", (pnr7 & (c > ph), pnr7 & (c < pl)))
    inside = (h < np.roll(h, 1)) & (l > np.roll(l, 1))
    pin = np.roll(inside, 1); pin[:2] = False
    addT("inside_bar_break", (pin & (c > ph), pin & (c < pl)))
    # --- candles
    pc, po = np.roll(c, 1), np.roll(o, 1)
    addT("engulfing", ((pc < po) & (c > o) & (c >= po) & (o <= pc) & (c < lo20 * 1.03),
                       (pc > po) & (c < o) & (c <= po) & (o >= pc) & (c > hi20 * 0.97)))
    addT("pinbar", ((lw > 2 * body) & (lw > 0.6 * rng) & (l <= F.rmin(l, 10)),
                    (uw > 2 * body) & (uw > 0.6 * rng) & (h >= F.rmax(h, 10))))
    # --- VWAP family
    addT("vwap_x", (F.cross_up(c, vwd), F.cross_dn(c, vwd)))
    addT("vwap_1sd_break", (F.cross_up(c, vwd + vsd), F.cross_dn(c, vwd - vsd)))
    addT("vwap_2sd_revert", (F.cross_up(c, vwd - 2 * vsd), F.cross_dn(c, vwd + 2 * vsd)))
    addT("vwap_week_x", (F.cross_up(c, vww), F.cross_dn(c, vww)))
    addT("vwap_month_x", (F.cross_up(c, vwm), F.cross_dn(c, vwm)))
    addT("vwap_reclaim", ((l < vwd - vsd) & (c > vwd) , (h > vwd + vsd) & (c < vwd)))
    # --- volume
    spike = v > 3 * vsma
    addT("vol_spike_candle", (spike & (c > o) & (body > 0.5 * rng), spike & (c < o) & (body > 0.5 * rng)))
    addT("vol_spike_reversal", (spike & (lw / rng > 0.5), spike & (uw / rng > 0.5)))
    addT("vol_climax", ((v > 4 * vsma) & (l <= F.rmin(l, 20)) & (c > l + 0.4 * rng),
                        (v > 4 * vsma) & (h >= F.rmax(h, 20)) & (c < h - 0.4 * rng)))
    dry = pd.Series(F.sma(v, 5) < 0.6 * F.sma(v, 50)).shift(1).rolling(5).max().values == 1
    addT("vol_dryup_break", (dry & F.cross_up(c, F.rmax(h, 20)) & (v > 1.5 * vsma),
                             dry & F.cross_dn(c, F.rmin(l, 20)) & (v > 1.5 * vsma)))
    addT("obv_break_20", (F.cross_up(obv, F.rmax(obv, 20)), F.cross_dn(obv, F.rmin(obv, 20))))
    addT("delta_surge", (F.cross_up(dz, 2.5), F.cross_dn(dz, -2.5)), "taker")
    addT("delta_absorption", ((c < o) & ((o - c) > 0.5 * a14) & (dz > 1), (c > o) & ((c - o) > 0.5 * a14) & (dz < -1)), "taker")
    addT("cvd_divergence", ((c < lo20) & (cvd > F.rmin(cvd, 20)), (c > hi20) & (cvd < F.rmax(cvd, 20))), "taker")
    d12 = pd.Series(delta_dt).rolling(12).sum().values
    addT("delta_flip", (F.cross_up(d12, 0), F.cross_dn(d12, 0)), "taker")
    # --- SMC / ICT
    addT("smc_bos", (bos_u, bos_d))
    addT("smc_choch", (ch_u, ch_d))
    addT("smc_fvg_retest", (fvg_l, fvg_s))
    addT("smc_ob_retest", (ob_l, ob_s))
    addT("smc_sweep_swing", (sw_u, sw_d))
    addT("sweep_pdh_pdl", ((l < pdl) & (c > pdl), (h > pdh) & (c < pdh)))
    addT("break_pdh_pdl", (F.cross_up(c, pdh), F.cross_dn(c, pdl)))
    addT("sweep_pwh_pwl", ((l < pwl) & (c > pwl), (h > pwh) & (c < pwh)))
    addT("break_pwh_pwl", (F.cross_up(c, pwh), F.cross_dn(c, pwl)))
    hr = ts.dt.hour.values
    if tf in ("15m", "1h"):
        day = ts.dt.floor("D")
        asia = pd.DataFrame({"d": day.values, "h": np.where(hr < 7, h, np.nan), "l": np.where(hr < 7, l, np.nan)})
        ah = asia.groupby("d")["h"].transform("max").values; al = asia.groupby("d")["l"].transform("min").values
        lon = (hr >= 7) & (hr < 17)
        addT("asia_range_break", (lon & F.cross_up(c, ah), lon & F.cross_dn(c, al)))
        addT("asia_range_sweep", (lon & (l < al) & (c > al), lon & (h > ah) & (c < ah)))

    # ================= states (filters) =================
    addS("none", nb(np.ones(n, bool)))
    addS("above_ema200", (c > e200, c < e200))
    addS("ema50_gt_200", (e50 > e200, e50 < e200))
    addS("ribbon_aligned", (rib_up, rib_dn))
    addS("ema200_slope", (e200 > np.roll(e200, 10), e200 < np.roll(e200, 10)))
    d_e20 = htf(k, "1D", lambda x: F.ema(x, 20)); d_c = htf(k, "1D", lambda x: x)
    addS("htf_daily_trend", (d_c > d_e20, d_c < d_e20))
    w_e20 = htf(k, "7D", lambda x: F.ema(x, 20)); w_c = htf(k, "7D", lambda x: x)
    addS("htf_weekly_trend", (w_c > w_e20, w_c < w_e20))
    br = F.btc_regime(k, tf)
    addS("btc_bull_regime", (br == 1, br == -1))
    addS("ichi_cloud_side", (c > ctop, c < cbot))
    addS("above_vwap_d", (c > vwd, c < vwd))
    addS("above_vwap_w", (c > vww, c < vww))
    addS("adx_trending", nb(ad > 25))
    addS("adx_ranging", nb(ad < 20))
    addS("rsi_side", (r14 > 50, r14 < 50))
    addS("rsi_oversold_zone", (r14 < 40, r14 > 60))
    addS("macd_hist_side", (macd > msig, macd < msig))
    addS("supertrend_side", (st == 1, st == -1))
    addS("smc_structure", (trend > 0, trend < 0))
    lo50, hi50 = pd.Series(l).rolling(50).min().values, pd.Series(h).rolling(50).max().values
    posr = (c - lo50) / (hi50 - lo50)
    addS("smc_discount_premium", (posr < 0.5, posr > 0.5))
    addS("volume_high", nb(v > 1.5 * vsma))
    addS("volume_low", nb(v < 0.7 * vsma))
    apct = pd.Series(a14 / c).rolling(200, min_periods=100).rank(pct=True).values
    addS("vol_expanding", nb(apct > 0.7))
    addS("vol_contracting", nb(apct < 0.3))
    addS("taker_flow_side", (d12 > 0, d12 < 0), "taker")
    addS("obv_side", (obv > F.ema(obv, 20), obv < F.ema(obv, 20)))
    addS("sess_asia", nb(hr < 8))
    addS("sess_europe", nb((hr >= 7) & (hr < 13)))
    addS("sess_us", nb((hr >= 13) & (hr < 21)))
    addS("weekend", nb(ts.dt.dayofweek.values >= 5))
    # cross-section + macro (free)
    m = _map_ctx(k, tf, symbol) if symbol is not None else None
    if m is not None:
        b = m["breadth"].values; rk = m["rank7"].values; b1 = m["btc_ret1d"].values
        fg = m["fear_greed"].values; fgm = m["fg_ma30"].values; sc = m["stable_30d"].values
        addS("breadth_side", (b > 0.5, b < 0.5), "cross")
        addS("breadth_extreme", (b < 0.2, b > 0.8), "cross")  # contrarian
        addS("rs_rank_top", (rk > 0.7, rk < 0.3), "cross")    # relative strength momentum
        addS("rs_rank_laggard", (rk < 0.3, rk > 0.7), "cross")  # relative strength reversal
        addS("btc_1d_side", (b1 > 0, b1 < 0), "cross")
        addS("fg_extreme", (fg < 25, fg > 75), "macro")      # contrarian
        addS("fg_trend", (fg > fgm, fg < fgm), "macro")
        addS("stable_growth", (sc > 0.01, sc < 0), "macro")

    clean = lambda d: {nm: (np.nan_to_num(a, nan=0).astype(bool), np.nan_to_num(bb, nan=0).astype(bool)) for nm, (a, bb) in d.items()}
    return clean(T), clean(S), {"atr": a14}
