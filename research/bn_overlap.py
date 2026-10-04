"""Binance simulation restricted to coins that also trade on HYPE (2024-07 -> 2026-10): venue effect vs universe effect."""
import pandas as pd, numpy as np, json, os, warnings
import ta, xsec, buffer_test as BT, strategy_sim as S, hl_full as H
warnings.filterwarnings("ignore")

if __name__ == "__main__":
    hl = set(H.hl_universe())
    mp = {"kPEPE": "1000PEPEUSDT", "kSHIB": "1000SHIBUSDT", "kBONK": "1000BONKUSDT", "kFLOKI": "1000FLOKIUSDT"}
    ov = [s for s in ta.universe() if s[:-4] in hl or any(mp.get(h) == s for h in hl)]
    base_panel = xsec.panel()
    xsec.panel = lambda: base_panel[base_panel.sym.isin(ov)]
    m, _, _ = BT.run(10, 15)
    fb = pd.read_parquet(os.path.join(ta.OUT, "breadth_trades_4h_sl2_tp2.parquet"))
    fb = fb[(fb.name == "L bb_revert+volhigh") & fb.symbol.isin(ov)].copy()
    fb["n_event"] = fb.groupby("entry_ts")["R"].transform("size"); fb = fb[fb.n_event >= 10]
    fb["stop_frac"] = (fb.ret / fb.R).where(fb.R.abs() > 1e-9); fb["stop_frac"] = fb.stop_frac.fillna(fb.stop_frac.median()).clip(0.005, 0.5)
    fb["rnd"] = np.random.default_rng(1).random(len(fb)); fb = fb[fb.groupby("entry_ts")["rnd"].rank() <= 15]
    fb = fb[pd.to_datetime(fb.entry_ts) >= H.START]
    out = {"n_overlap": len(ov), "events": int(fb.entry_ts.nunique()), "ev_avgR": round(float(fb.groupby("entry_ts").R.mean().mean()), 3)}
    for nm, kw in (("rmf", {}), ("mom_only", dict(use_flush=False)), ("flush_only", dict(use_mom=False))):
        df = S.simulate(f_mom=0.5, mom=m[m.index >= "2024-06-29"], fl=fb, **kw); df = df[df.index >= H.START]
        out[nm] = H.window_stats(df, 300)
    # full period 2020+ restricted universe
    df = S.simulate(f_mom=0.5, mom=m, fl=pd.concat([fb])); out["note"] = "full-period uses only post-2024-07 flush; see rmf_2020"
    fb_all = pd.read_parquet(os.path.join(ta.OUT, "breadth_trades_4h_sl2_tp2.parquet"))
    fb_all = fb_all[(fb_all.name == "L bb_revert+volhigh") & fb_all.symbol.isin(ov)].copy()
    fb_all["n_event"] = fb_all.groupby("entry_ts")["R"].transform("size"); fb_all = fb_all[fb_all.n_event >= 10]
    fb_all["stop_frac"] = (fb_all.ret / fb_all.R).where(fb_all.R.abs() > 1e-9); fb_all["stop_frac"] = fb_all.stop_frac.fillna(fb_all.stop_frac.median()).clip(0.005, 0.5)
    fb_all["rnd"] = np.random.default_rng(1).random(len(fb_all)); fb_all = fb_all[fb_all.groupby("entry_ts")["rnd"].rank() <= 15]
    out["rmf_2020"] = H.window_stats(S.simulate(f_mom=0.5, mom=m, fl=fb_all), 300)
    json.dump(out, open(os.path.join(ta.OUT, "bn_overlap.json"), "w")); print(out)
