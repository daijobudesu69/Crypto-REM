"""Muat config.yaml menjadi dataclass yang divalidasi.

Kunci yang tidak dikenal DITOLAK: salah ketik (mis. `exit_rnak: 20`) tidak boleh
diam-diam diabaikan sementara bot jalan dengan nilai default.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, "config.yaml")


@dataclass(frozen=True)
class Universe:
    mode: str = "static"
    static_file: str = "config/hype_universe.txt"
    top_n: int = 150
    volume_days: int = 30
    exclude: tuple = ("USDC", "USDT", "USDE", "USDH", "FDUSD", "DAI", "PYUSD", "USD1", "PAXG", "XAUT")
    fetch_days: int = 100
    btc_fetch_days: int = 1200
    exit_rank: int = 200             # rolling_monthly: anggota lama tetap selama peringkat volume <= ini
    compare_rolling: bool = False    # buku paper kedua dengan universe rolling_monthly


@dataclass(frozen=True)
class Momentum:
    n_hold: int = 10
    exit_rank: int = 15
    lookback_days: int = 14
    min_history_days: int = 60
    regime_symbol: str = "BTC"
    regime_ema: int = 50
    gross_exposure: float = 0.5
    min_order_usdc: float = 10.0
    run_after_minutes: int = 2


@dataclass(frozen=True)
class Flush:
    signal_source: str = "binance_spot"
    spot_universe_file: str = "config/flush_spot_universe.txt"
    futures_universe_file: str = "config/flush_futures_universe.txt"
    bb_len: int = 20
    bb_k: float = 2.0
    vol_len: int = 20
    vol_mult: float = 1.5
    min_coins: int = 10
    max_coins: int = 15
    atr_len: int = 14
    sl_atr: float = 2.0
    tp_atr: float = 2.0
    max_bars: int = 48
    atr_history_bars: int = 200
    risk_pct: float = 0.5
    max_event_risk_pct: float = 8.0
    reject_forced_risk_x: float = 2.0
    gross_cap_x: float = 2.0


@dataclass(frozen=True)
class Costs:
    taker_fee: float = 0.00045
    paper_slippage: float = 0.00025


@dataclass(frozen=True)
class Benchmark:
    include_funding: bool = True


@dataclass(frozen=True)
class StopRules:
    max_drawdown_pct: float = 40
    underperform_months: int = 9
    review_after_months: int = 6
    six_month_floor_pct: float = -12.5
    expected_cagr_pct: float = 22


@dataclass(frozen=True)
class Hype:
    info_url: str = "https://api.hyperliquid.xyz/info"
    weight_per_minute: int = 1000


@dataclass(frozen=True)
class Execution:
    master_address: str = ""
    account_address: str = ""
    agent_address: str = ""
    agent_secret: str = "HYPE_RMF_AGENT_KEY_66_CHAR"
    agent_valid_until: str = ""
    margin_mode: str = "cross"
    leverage: int = 1
    ioc_slippage: float = 0.01
    max_live_attempts_per_day: int = 6
    blocked_agents: tuple = ()


@dataclass(frozen=True)
class Config:
    capital_usdc: float = 200.0
    forward_start: str = ""          # YYYY-MM-DD (UTC); sebelum tanggal ini bot tidak trading
    universe: Universe = field(default_factory=Universe)
    momentum: Momentum = field(default_factory=Momentum)
    flush: Flush = field(default_factory=Flush)
    costs: Costs = field(default_factory=Costs)
    benchmark: Benchmark = field(default_factory=Benchmark)
    stop_rules: StopRules = field(default_factory=StopRules)
    hype: Hype = field(default_factory=Hype)
    execution: Execution = field(default_factory=Execution)


_SECTIONS = {"universe": Universe, "momentum": Momentum, "flush": Flush, "costs": Costs,
             "benchmark": Benchmark, "stop_rules": StopRules, "hype": Hype, "execution": Execution}


def _build(cls, data: dict, where: str):
    data = data or {}
    if not isinstance(data, dict):
        raise ValueError(f"{where}: harus berupa pasangan kunci: nilai")
    known = {f.name: f for f in fields(cls)}
    unknown = sorted(set(data) - set(known))
    if unknown:
        raise ValueError(f"{where}: kunci tidak dikenal {unknown} (pilih dari {sorted(known)})")
    kw = {}
    for k, v in data.items():
        default = getattr(cls(), k)
        if isinstance(default, tuple) and isinstance(v, list):
            v = tuple(v)
        elif isinstance(default, bool):
            v = bool(v)
        elif isinstance(default, int) and not isinstance(default, bool):
            v = int(v)
        elif isinstance(default, float):
            v = float(v)
        elif isinstance(default, str):
            v = "" if v is None else str(v)
        kw[k] = v
    return cls(**kw)


def from_dict(doc: dict) -> Config:
    doc = dict(doc or {})
    top = {}
    for name, cls in _SECTIONS.items():
        top[name] = _build(cls, doc.pop(name, None), name)
    if "capital_usdc" in doc:
        top["capital_usdc"] = float(doc.pop("capital_usdc"))
    if "forward_start" in doc:
        top["forward_start"] = str(doc.pop("forward_start") or "")
    if doc:
        raise ValueError(f"config: kunci tidak dikenal {sorted(doc)}")
    cfg = Config(**top)
    validate(cfg)
    return cfg


def load(path: str | None = None) -> Config:
    path = path or os.environ.get("RMF_CONFIG") or DEFAULT_PATH
    with open(path, encoding="utf-8") as fh:
        return from_dict(yaml.safe_load(fh) or {})


def validate(cfg: Config) -> None:
    m, f = cfg.momentum, cfg.flush
    if m.exit_rank < m.n_hold:
        raise ValueError("momentum.exit_rank harus >= n_hold")
    if m.min_history_days < m.lookback_days + 1:
        raise ValueError("momentum.min_history_days terlalu kecil untuk lookback_days")
    if cfg.universe.fetch_days < m.min_history_days + 2:
        raise ValueError("universe.fetch_days harus > min_history_days")
    if cfg.universe.mode not in ("static", "rolling"):
        # rolling_monthly hanya untuk buku paper pembanding (compare_rolling), bukan
        # buku utama: view buku utama juga dipakai live.
        raise ValueError("universe.mode: static atau rolling (rolling_monthly hanya lewat compare_rolling)")
    if cfg.universe.exit_rank < cfg.universe.top_n:
        raise ValueError("universe.exit_rank harus >= top_n")
    if f.signal_source not in ("binance_spot", "binance_futures"):
        raise ValueError("flush.signal_source: binance_spot atau binance_futures")
    if cfg.execution.margin_mode not in ("cross", "isolated"):
        raise ValueError("execution.margin_mode: cross atau isolated")
    if cfg.execution.margin_mode == "isolated" and cfg.execution.leverage > 2:
        raise ValueError("isolated > 2x ditolak (lihat HANDOVER_RMF.md §1, crash 10 Okt 2025)")
    if cfg.capital_usdc <= 0:
        raise ValueError("capital_usdc harus > 0")


def path_in_repo(rel: str) -> str:
    return rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
