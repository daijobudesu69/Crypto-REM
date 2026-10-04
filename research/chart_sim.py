"""Chart for the 300 USDT simulation -> reports/strategy_300usdt.png"""
import os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mt
import ta

SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10, "axes.edgecolor": AXIS,
                     "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED, "axes.facecolor": SURF,
                     "figure.facecolor": SURF, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
                     "axes.spines.top": False, "axes.spines.right": False})

out = pd.read_pickle(os.path.join(ta.OUT, "sim_variants.pkl"))
main = out["A 0.5x + B"]; mom = out["A momentum 1x"]; fl = out["B flush basket"]

fig, axs = plt.subplots(3, 1, figsize=(12, 12), gridspec_kw={"height_ratios": [3, 1.4, 1.6]}, sharex=True)
fig.suptitle("Strategi RMF (Rotasi Momentum + Flush Basket) — modal awal 300 USDT, 2020 → 2026-10", x=0.06, ha="left",
             fontsize=14, color=INK, fontweight="bold")
fig.text(0.06, 0.945, "Backtest Binance perp, biaya 0,07%/sisi + funding riil. Garis putus = mulai out-of-sample (2025). Skala log.",
         color=INK2, fontsize=10)

ax = axs[0]
for df, c, lw, lab in ((mom, ORANGE, 1.6, "Momentum saja (1x)"), (fl, AQUA, 1.6, "Flush basket saja"), (main, BLUE, 2.4, "RMF: momentum 0,5x + flush")):
    ax.plot(df.index, df.equity, color=c, lw=lw)
    ax.annotate(f"{lab}\n{df.equity.iloc[-1]:,.0f} USDT", (df.index[-1], df.equity.iloc[-1]), xytext=(8, 0),
                textcoords="offset points", va="center", fontsize=9.5, color=INK, fontweight="bold" if c == BLUE else "normal")
ax.set_yscale("log")
ax.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, p: f"{v:,.0f}"))
ax.set_ylabel("Ekuitas (USDT, log)")
ax.axhline(300, color=AXIS, lw=1)

ax = axs[1]
for df, c, lab in ((mom, ORANGE, "Momentum saja"), (main, BLUE, "RMF")):
    dd = (df.equity / df.equity.cummax() - 1) * 100
    if c == BLUE:
        ax.fill_between(dd.index, dd, 0, color=BLUE, alpha=0.18, lw=0)
    ax.plot(dd.index, dd, color=c, lw=1.4 if c == ORANGE else 2)
    i = dd.idxmin()
    ax.annotate(f"{lab} terdalam {dd.min():.0f}%", (i, dd.min()), xytext=(6, -4), textcoords="offset points", fontsize=9, color=INK2)
ax.set_ylabel("Drawdown (%)")
ax.set_ylim(-75, 3)

ax = axs[2]
mo = main.equity.resample("ME").last()
mo = pd.concat([pd.Series([300.0], [mo.index[0] - pd.offsets.MonthEnd(1)]), mo]).pct_change().dropna() * 100
ax.bar(mo.index, mo.values, width=22, color=np.where(mo.values >= 0, BLUE, RED), edgecolor=SURF, linewidth=0.5)
ax.axhline(0, color=AXIS, lw=1)
ax.set_ylabel("Return bulanan RMF (%)")
for k in mo.nlargest(2).index.tolist() + mo.nsmallest(2).index.tolist():
    ax.annotate(f"{mo[k]:+.0f}%", (k, mo[k]), xytext=(0, 4 if mo[k] > 0 else -12), textcoords="offset points", ha="center", fontsize=8.5, color=INK2)

for a in axs:
    a.axvline(pd.Timestamp("2025-01-01"), color=MUTED, lw=1, ls="--")
axs[0].text(pd.Timestamp("2025-01-10"), axs[0].get_ylim()[0] * 1.3, "OOS →", color=MUTED, fontsize=9)
axs[2].xaxis.set_major_locator(matplotlib.dates.YearLocator())
axs[2].xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%Y"))
plt.subplots_adjust(left=0.07, right=0.83, top=0.92, bottom=0.04, hspace=0.12)
p = os.path.join(os.path.dirname(ta.HERE), "reports", "strategy_300usdt.png")
plt.savefig(p, dpi=130)
print(p)
