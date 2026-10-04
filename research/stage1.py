"""Stage 1: brute-force event study of every trigger x (0/1/2 filters), free data only.

For each symbol / TF / direction: entry at next bar open, exit h bars later at open, net of
round-trip cost (0.14%) and the real funding paid/received (cost only). Statistics are summed per
calendar year so IS (2020-2024) / OOS (2025-2026) can be derived afterwards.

    python stage1.py 4h [workers]   -> results/event_4h.parquet
"""
import os
for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(v, "1")
import sys, time, warnings
import numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))
import ta

warnings.filterwarnings("ignore")
COST = 0.0014
HORIZONS = {"15m": [4, 16, 48, 96], "1h": [4, 12, 24, 72], "4h": [3, 6, 18, 42], "1d": [1, 3, 7, 14]}
YEARS = list(range(2020, 2027))
OOS_START = 2025


def _work(args):
    sym, tf = args
    warnings.filterwarnings("ignore")
    try:
        k = ta.load(sym, tf)
    except FileNotFoundError:
        return None
    if len(k) < (250 if tf == "1d" else 500):
        return None
    T, S, _ = ta.signals(k, tf, sym)
    tn, sn = list(T), list(S)
    H = HORIZONS[tf]
    o = k["open"].values; cf = k["cum_funding"].values
    n = len(o); year = k["ts"].dt.year.values
    nT, nS, nH = len(tn) + 1, len(sn), len(H)
    res = {}
    for d, sign in ((0, 1.0), (1, -1.0)):
        X = np.zeros((n, nT), np.float32)
        for j, name in enumerate(tn):
            X[:, j] = T[name][d]
        X[:, -1] = 1.0  # "always" = unconditional baseline
        Sm = np.stack([S[name][d] for name in sn], axis=1).astype(np.float32)
        R = np.full((n, nH), np.nan)
        idx = np.arange(n)
        for hi, h in enumerate(H):
            ent = idx + 1; ex = ent + h; ok = ex < n
            r = np.full(n, np.nan); r[ok] = o[ex[ok]] / o[ent[ok]] - 1
            fund = np.full(n, np.nan); fund[ok] = cf[np.minimum(idx[ok] + h, n - 1)] - cf[idx[ok]]
            R[:, hi] = sign * r - COST - sign * fund
        V = np.isfinite(R); R0 = np.where(V, R, 0.0)
        cnt = np.zeros((len(YEARS), nH, nT, nS, nS), np.float32)
        sm = np.zeros_like(cnt); sq = np.zeros_like(cnt); se = np.zeros_like(cnt)
        for yi, y in enumerate(YEARS):
            rows = np.where(year == y)[0]
            if len(rows) < 50:
                continue
            Ry, Vy = R0[rows], V[rows]
            mu = Ry.sum(0) / np.maximum(Vy.sum(0), 1)
            Ey = np.where(Vy, Ry - mu, 0.0)
            Xy, Sy = X[rows], Sm[rows]
            Z = np.concatenate([Xy[:, :, None] * Vy[:, None, :], Xy[:, :, None] * Ry[:, None, :],
                                Xy[:, :, None] * (Ry * Ry)[:, None, :], Xy[:, :, None] * Ey[:, None, :]],
                               axis=2).astype(np.float32).reshape(len(rows), nT * 4 * nH)
            for a in range(nS):
                M = (Z.T @ (Sy * Sy[:, a:a + 1])).reshape(nT, 4, nH, nS).transpose(1, 2, 0, 3)
                cnt[yi, :, :, a, :] = M[0]; sm[yi, :, :, a, :] = M[1]
                sq[yi, :, :, a, :] = M[2]; se[yi, :, :, a, :] = M[3]
            del Z
        res[d] = (cnt, sm, sq, se)
    return sym, tn + ["always"], sn, res


def run(tf, workers):
    syms = ta.universe()
    t0 = time.time(); agg = breadth = None; names = None
    with ProcessPoolExecutor(workers) as ex:
        for i, out in enumerate(ex.map(_work, [(s, tf) for s in syms])):
            if out is None:
                continue
            sym, tn, sn, res = out
            if agg is None:
                names = (tn, sn)
                agg = {d: [np.zeros_like(a, dtype=np.float64) for a in res[d]] for d in res}
                shp = res[0][0].shape[1:]
                breadth = {d: {p: [np.zeros(shp), np.zeros(shp)] for p in ("is", "oos")} for d in res}
            assert (tn, sn) == names, sym
            yrs = np.array(YEARS)
            for d in res:
                for j in range(4):
                    agg[d][j] += res[d][j]
                cnt, sm = res[d][0], res[d][1]
                for p, mask in (("is", yrs < OOS_START), ("oos", yrs >= OOS_START)):
                    c = cnt[mask].sum(0); s = sm[mask].sum(0); act = c >= 5
                    breadth[d][p][0] += act; breadth[d][p][1] += act & (s > 0)
            print(f"{i+1}/{len(syms)} {sym} {time.time()-t0:.0f}s", flush=True)
    return names[0], names[1], agg, breadth


def tabulate(tf, tn, sn, agg, breadth):
    H = HORIZONS[tf]; yrs = np.array(YEARS); rows = []
    iu = np.triu_indices(len(sn))
    for d, dname in ((0, "long"), (1, "short")):
        cnt, sm, sq, se = agg[d]
        for hi, h in enumerate(H):
            rec = {}
            for p, mask in (("is", yrs < OOS_START), ("oos", yrs >= OOS_START)):
                c = cnt[mask, hi].sum(0); s = sm[mask, hi].sum(0); q = sq[mask, hi].sum(0); e = se[mask, hi].sum(0)
                mean = s / np.maximum(c, 1); var = q / np.maximum(c, 1) - mean ** 2
                tstat = mean / np.sqrt(np.maximum(var, 1e-12) / np.maximum(c, 1))
                rec[p] = (c[:, iu[0], iu[1]], mean[:, iu[0], iu[1]], tstat[:, iu[0], iu[1]], (e / np.maximum(c, 1))[:, iu[0], iu[1]],
                          breadth[d][p][0][hi][:, iu[0], iu[1]], breadth[d][p][1][hi][:, iu[0], iu[1]])
            ymean = (sm[:, hi] / np.maximum(cnt[:, hi], 1))[:, :, iu[0], iu[1]]
            ycnt = cnt[:, hi][:, :, iu[0], iu[1]]
            for ti, tname in enumerate(tn):
                df = pd.DataFrame({"dir": dname, "h": h, "trigger": tname,
                                   "state1": np.array(sn)[iu[0]], "state2": np.array(sn)[iu[1]]})
                for p in ("is", "oos"):
                    c, m, t, e, ba, bp = (x[ti] for x in rec[p])
                    df[f"n_{p}"] = c.astype(np.int32); df[f"mean_{p}"] = m.astype(np.float32); df[f"t_{p}"] = t.astype(np.float32)
                    df[f"excess_{p}"] = e.astype(np.float32); df[f"sym_{p}"] = ba.astype(np.int16); df[f"sym_pos_{p}"] = bp.astype(np.int16)
                for yi, y in enumerate(YEARS):
                    df[f"y{y}"] = np.where(ycnt[yi, ti] >= 20, ymean[yi, ti], np.nan).astype(np.float32)
                rows.append(df[(df.n_is > 0) | (df.n_oos > 0)])
    out = pd.concat(rows, ignore_index=True)
    out.insert(0, "tf", tf)
    return out


if __name__ == "__main__":
    tf = sys.argv[1]
    os.makedirs(ta.OUT, exist_ok=True)
    tn, sn, agg, breadth = run(tf, int(sys.argv[2]) if len(sys.argv) > 2 else 6)
    df = tabulate(tf, tn, sn, agg, breadth)
    df.to_parquet(os.path.join(ta.OUT, f"event_{tf}.parquet"), index=False)
    print("rows", len(df))
