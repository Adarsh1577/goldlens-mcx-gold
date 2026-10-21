"""GoldLens chart: how different are the gold contracts for the same expiry?

Reads every data\\YYYY-MM-DD.csv (the date in the file name is the trading date), uses bhav_clean.py,
and writes PNG charts into the charts\\ folder.

  Figure 1 (always): latest day.  Left = normalised price (Rs per 10 g, 999 basis) by expiry.
                     Right = premium of GOLDGUINEA and GOLDPETAL over GOLDTEN, same expiry.
  Figure 2 (if 2+ days): that premium over time for one expiry.

Run:  python chart_snapshot.py
Needs: pip install pandas matplotlib   (bhav_clean.py must be in the same folder)

These are SETTLEMENT prices, not tradeable fills; thin contracts are shown with their volume.
"""
import glob
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from bhav_clean import load_bhav, per_10g_999

# categorical slots 1-4 of the validated reference palette, assigned in fixed order per contract
COLORS = {"GOLDTEN": "#2a78d6", "GOLDPETAL": "#eb6834", "GOLDGUINEA": "#1baf7a", "GOLDM": "#eda100"}
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e1", "#ffffff"


def load_all(folder="data"):
    frames = []
    for path in sorted(glob.glob(os.path.join(folder, "*.csv"))):
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", os.path.basename(path))
        if not m:
            print("skip (no YYYY-MM-DD in name):", path)
            continue
        ddmmyyyy = "%s/%s/%s" % (m.group(3), m.group(2), m.group(1))
        try:
            frames.append(per_10g_999(load_bhav(path, ddmmyyyy)))
        except Exception as e:                      # keep going, but say why a day was skipped
            print("SKIPPED %s: %s" % (path, e))
    if not frames:
        sys.exit("No usable files in %s\\" % folder)
    return pd.concat(frames, ignore_index=True)


def premiums(day):
    """Premium of GOLDGUINEA / GOLDPETAL over GOLDTEN for matching expiry dates."""
    p = day.pivot_table(index="expiry_date", columns="symbol", values="close_per10g")
    v = day.pivot_table(index="expiry_date", columns="symbol", values="volume_lots")
    out = pd.DataFrame(index=p.index)
    for s in ["GOLDGUINEA", "GOLDPETAL"]:
        if s in p and "GOLDTEN" in p:
            out[s + "-GOLDTEN"] = p[s] - p["GOLDTEN"]
            out[s + " vol"] = v[s]
    if "GOLDTEN" in v:
        out["GOLDTEN vol"] = v["GOLDTEN"]
    return out.dropna(subset=[c for c in out.columns if "-GOLDTEN" in c], how="all")


def style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=10)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def fig_snapshot(df, outdir):
    day_ts = df["date"].max()
    day = df[df["date"] == day_ts]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5.2), facecolor=SURFACE, gridspec_kw={"width_ratios": [1.15, 1]})

    for sym in ["GOLDTEN", "GOLDPETAL", "GOLDGUINEA", "GOLDM"]:
        d = day[day["symbol"] == sym].sort_values("expiry_date")
        if d.empty:
            continue
        a1.plot(d["expiry_date"], d["close_per10g"], color=COLORS[sym], linewidth=2, marker="o", markersize=5,
                markeredgecolor=SURFACE, markeredgewidth=1.5, label=sym)
    style(a1)
    a1.set_title("Same gold, different contracts: normalised price by expiry", loc="left", color=INK, fontsize=12, pad=12)
    a1.set_ylabel("Rs per 10 g (999 basis)", color=INK2, fontsize=10)
    a1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: "{:,.0f}".format(x)))
    a1.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    a1.legend(frameon=False, fontsize=10, labelcolor=INK2, loc="upper left")

    pr = premiums(day)
    labels = [d.strftime("%d %b %y") for d in pr.index]
    x = range(len(pr))
    w = 0.38
    for k, sym in enumerate(["GOLDGUINEA", "GOLDPETAL"]):
        col = sym + "-GOLDTEN"
        if col not in pr:
            continue
        pos = [i + (k - 0.5) * (w + 0.04) for i in x]
        a2.bar(pos, pr[col], width=w, color=COLORS[sym], label=sym + " minus GOLDTEN")
    a2.set_xticks(list(x))
    a2.set_xticklabels(labels, rotation=30, ha="right")
    style(a2)
    a2.axhline(0, color=INK2, linewidth=0.8)
    a2.set_title("Premium over GOLDTEN, same expiry (Rs per 10 g)", loc="left", color=INK, fontsize=12, pad=12)
    a2.legend(frameon=False, fontsize=10, labelcolor=INK2, loc="upper left")

    fig.text(0.01, 0.01, "Source: MCX Bhavcopy settlement prices, %s. Settlement is not a fill price; volume is not liquidity. "
             "Purity adjustment (999/purity) is an assumption." % day_ts.strftime("%d %b %Y"), color=INK2, fontsize=8.5)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    path = os.path.join(outdir, "snapshot_%s.png" % day_ts.strftime("%Y-%m-%d"))
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    return path, pr


def fig_over_time(df, outdir):
    days = sorted(df["date"].unique())
    if len(days) < 2:
        return None
    # the nearest expiry that has all three contracts on the most days
    best, best_n = None, 0
    for e, g in df.groupby("expiry_date"):
        n = g.groupby("date")["symbol"].apply(lambda s: {"GOLDTEN", "GOLDGUINEA", "GOLDPETAL"} <= set(s)).sum()
        if n > best_n:
            best, best_n = e, n
    if best is None or best_n < 2:
        return None
    sub = df[df["expiry_date"] == best]
    p = sub.pivot_table(index="date", columns="symbol", values="close_per10g").sort_index()
    fig, ax = plt.subplots(figsize=(9, 4.6), facecolor=SURFACE)
    for sym in ["GOLDGUINEA", "GOLDPETAL"]:
        ax.plot(p.index, p[sym] - p["GOLDTEN"], color=COLORS[sym], linewidth=2, marker="o", markersize=5,
                markeredgecolor=SURFACE, markeredgewidth=1.5, label=sym + " minus GOLDTEN")
    style(ax)
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.set_title("Premium over GOLDTEN, %s contract (Rs per 10 g)" % pd.Timestamp(best).strftime("%d %b %Y"),
                 loc="left", color=INK, fontsize=12, pad=12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.legend(frameon=False, fontsize=10, labelcolor=INK2, loc="upper left")
    fig.text(0.01, 0.01, "Source: MCX Bhavcopy settlement prices. Not a tradeable-edge claim.", color=INK2, fontsize=8.5)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    path = os.path.join(outdir, "premium_over_time.png")
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)
    return path


if __name__ == "__main__":
    os.makedirs("charts", exist_ok=True)
    data = load_all("data")
    p1, table = fig_snapshot(data, "charts")
    print("Saved", p1)
    t = table.copy()
    pd.set_option("display.width", 200)
    print(t.round(1).to_string())
    p2 = fig_over_time(data, "charts")
    print("Saved", p2 if p2 else "(need 2+ days of data for the over-time chart)")
