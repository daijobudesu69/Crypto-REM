"""Q1 audit 2026-10-05: batas risiko event flush — tanpa hard cap (riset) vs hard cap 8% (bot).

Riset (small_capital.simulate): risiko per koin = min(0,5%, 8% / n koin); koin yang
dipaksa minimum order 10 USDC boleh berisiko sampai 2x target (reject_x=2), dan total
event TIDAK dipotong -> maks 11% di simulasi 200 -> 410,6.
Bot (rmf/flush.py::size_event): sama, tapi koin ditolak kalau total risiko event
akan melewati 8% ekuitas (urutan alfabet, sama dengan urutan grup di riset).

Simulasi akun, trade, dan momentum diambil APA ADANYA dari modul riset; satu-satunya
perbedaan varian B adalah satu baris pengecekan cap. Varian A harus mereproduksi
angka flush_spot.json (200 -> 410,6 / 321,2) dulu sebelum hasil B dipercaya.

    python q1_event_cap.py   -> results/q1_event_cap.json
"""
import json
import os
import warnings

import numpy as np
import pandas as pd

import flush_spot as FS
import hl_full as H
import small_capital as SC
import ta

warnings.filterwarnings("ignore")


def simulate(start, mom, N, f_mom, fl, r_coin=0.005, cap_event=0.08, reject_x=None, gross_cap=None,
             start_date="2020-01-01", use_mom=True, use_flush=True, hard_cap=False):
    """Salinan SC.simulate (baris demi baris) + opsi hard_cap. hard_cap=False == SC.simulate."""
    MIN = SC.MIN
    days = pd.date_range(start_date, mom.index.max(), freq="D")
    m = mom.reindex(days).fillna(0.0).shift(1).fillna(0.0)
    fl = fl[pd.to_datetime(fl.entry_ts) >= start_date].copy()
    fl["entry_day"] = pd.to_datetime(fl.entry_ts).dt.floor("D"); fl["exit_day"] = pd.to_datetime(fl.exit_ts).dt.floor("D")
    ent = {d: g for d, g in fl.groupby("entry_day")}
    pending, open_n = {}, {}
    eq = start; rows = []; risk_taken = []; skipped = 0; taken = 0; capped = 0; ev_capped = 0
    for d in days:
        if eq < MIN:
            rows.append((d, eq, 0, 0, 0)); continue
        f_eff = max(f_mom, MIN * N / eq) if use_mom else 0.0
        mom_on = m.loc[d] != 0
        pnl_m = eq * f_eff * m.loc[d] if use_mom else 0.0
        pnl_f = sum(pending.pop(d, []))
        open_n = {k: v for k, v in open_n.items() if k[0] >= d}
        if use_flush and d in ent:
            for et, ge in ent[d].groupby("entry_ts"):
                rc = min(r_coin, cap_event / len(ge)); ev_risk = 0.0; hit = False
                for r in ge.itertuples():
                    target = eq * rc
                    notional = max(target / r.stop_frac, MIN)
                    risk = notional * r.stop_frac
                    if reject_x and risk > reject_x * target:
                        skipped += 1; continue
                    if hard_cap and ev_risk + risk > cap_event * eq + 1e-9:      # <- satu-satunya beda (bot)
                        skipped += 1; capped += 1; hit = True; continue
                    gross = (f_eff * eq if mom_on else 0) + sum(open_n.values())
                    if gross_cap and gross + notional > gross_cap * eq:
                        skipped += 1; continue
                    pending.setdefault(r.exit_day, []).append(risk * r.R)
                    open_n[(r.exit_day, et, r.symbol)] = notional
                    ev_risk += risk; taken += 1
                if ev_risk:
                    risk_taken.append(ev_risk / eq)
                ev_capped += hit
        gross_now = (f_eff * eq if (use_mom and mom_on) else 0) + sum(open_n.values())
        eq = max(eq + pnl_m + pnl_f, 0.0)
        rows.append((d, eq, pnl_m, pnl_f, gross_now / max(eq, 1e-9)))
    df = pd.DataFrame(rows, columns=["day", "equity", "pnl_mom", "pnl_flush", "gross_x"]).set_index("day")
    rt = np.array(risk_taken)
    return df, dict(event_risk_max=round(float(rt.max()) * 100, 2) if len(rt) else 0,
                    events=len(rt), events_over_8=int((rt > 0.08 + 1e-9).sum()),
                    flush_taken=taken, flush_skipped=skipped, coins_cut_by_cap=capped, events_cut_by_cap=ev_capped)


def pick(t_all, seed, max_coins=15):
    t = t_all.copy()
    t["rnd"] = np.random.default_rng(seed).random(len(t))
    return t[t.groupby("entry_ts")["rnd"].rank() <= max_coins]


if __name__ == "__main__":
    SC.MIN = 10
    t_all, _ = FS.spot_flush(max_coins=10**9)          # semua trade event, belum dipilih acak
    m10 = H.momentum_hl(10, 15)
    out = {"definition": __doc__.strip().splitlines()[0], "runs": [], "seeds": []}

    # 1) reproduksi + perbandingan di seed riset (1)
    t1 = pick(t_all, 1)
    for name, kw in (("momentum + flush spot (tolak>2x, gross<=2x)", dict(reject_x=2, gross_cap=2)),
                     ("flush spot saja (tolak>2x)", dict(use_mom=False, reject_x=2))):
        for sd in ("2024-07-01", "2025-01-01"):
            for cap in (False, True):
                df, ex = simulate(200, m10, 10, 0.5, t1, start_date=sd, hard_cap=cap, **kw)
                if not cap:   # harus identik dengan fungsi riset aslinya
                    ref, _ = SC.simulate(200, m10, 10, 0.5, t1, start_date=sd, **kw)
                    assert np.allclose(ref.equity.values, df.equity.values), "salinan simulate menyimpang"
                r = dict(variant=name, start=sd[:7], cap="8% hard (bot)" if cap else "tanpa cap (riset)",
                         **SC.st(df, 200), **ex)
                out["runs"].append(r); print(r, flush=True)

    # 2) ketahanan: 20 seed pemilihan acak, varian utama
    for seed in range(1, 21):
        ts = pick(t_all, seed)
        row = {"seed": seed}
        for cap in (False, True):
            df, ex = simulate(200, m10, 10, 0.5, ts, start_date="2024-07-01", hard_cap=cap, reject_x=2, gross_cap=2)
            s = SC.st(df, 200)
            k = "cap8" if cap else "nocap"
            row.update({f"{k}_final": s["final"], f"{k}_cagr": s["cagr"], f"{k}_maxdd": s["maxdd"],
                        f"{k}_worst_month": s["worst_month"], f"{k}_risk_max": ex["event_risk_max"],
                        f"{k}_events_over_8": ex["events_over_8"]})
        out["seeds"].append(row); print(row, flush=True)
    s = pd.DataFrame(out["seeds"])
    out["seed_summary"] = {c: dict(mean=round(float(s[c].mean()), 2), min=round(float(s[c].min()), 2),
                                   max=round(float(s[c].max()), 2)) for c in s.columns if c != "seed"}
    out["seed_cap_better_final"] = int((s.cap8_final > s.nocap_final).sum())
    out["seed_cap_better_dd"] = int((s.cap8_maxdd > s.nocap_maxdd).sum())
    print(json.dumps(out["seed_summary"], indent=1))
    json.dump(out, open(os.path.join(ta.OUT, "q1_event_cap.json"), "w"), indent=1, default=str)
