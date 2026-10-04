"""Why does RMF on HYPE candles lag Binance? Split HL universe into coins also in the Binance top150 vs HL-only."""
import pandas as pd, numpy as np, json, os, warnings
import ta, hl_full as H, strategy_sim as S
warnings.filterwarnings("ignore")

if __name__ == "__main__":
    bn = set(s[:-4] for s in ta.universe()) | {"kPEPE", "kSHIB", "kBONK", "kFLOKI"}
    hl = H.hl_universe(); ov = [c for c in hl if c in bn]; only = [c for c in hl if c not in bn]
    out = {"n_hl": len(hl), "n_overlap": len(ov), "hl_only": only}
    orig = H.hl_universe
    for name, uni, thr in (("overlap", ov, 10), ("overlap thr7", ov, 7), ("HL-only", only, 4), ("all HL", hl, 10)):
        H.hl_universe = lambda u=uni: u
        mh = H.momentum_hl(); fh = H.flush_hl(min_coins=thr); fh = fh[pd.to_datetime(fh.entry_ts) >= H.START]
        df = S.simulate(f_mom=0.5, mom=mh[mh.index >= "2024-06-29"], fl=fh); df = df[df.index >= H.START]
        dm = S.simulate(f_mom=0.5, mom=mh[mh.index >= "2024-06-29"], fl=fh, use_flush=False); dm = dm[dm.index >= H.START]
        rec = dict(universe=name, events=int(fh.entry_ts.nunique()), ev_avgR=round(float(fh.groupby("entry_ts").R.mean().mean()), 3),
                   rmf=H.window_stats(df, 300), mom_only=H.window_stats(dm, 300))
        out.setdefault("rows", []).append(rec); print(rec, flush=True)
    H.hl_universe = orig
    json.dump(out, open(os.path.join(ta.OUT, "hl_diag.json"), "w"))
