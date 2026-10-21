"""GoldLens engine: cross-contract spreads, look-ahead-free z-scores, walk-forward backtest with costs.

Uses bhav_clean.py (one Bhavcopy file -> clean gold futures rows, Rs per 10 g on a 999 basis).

What it does
  * Keys every contract by expiry date (no continuous near-month series).
  * Pairs GOLDGUINEA and GOLDPETAL against GOLDTEN for the SAME expiry; spread = (A - B) / B in percent.
  * z-score of each spread uses ONLY earlier days (shifted rolling window), so there is no look-ahead.
  * Backtest: signal at the close of day t, trade at the settlement of day t + 1 + extra lag (default 1 extra day),
    equal grams on both legs (gold-neutral), costs in bps of traded notional charged on the contracts actually held,
    positions forced flat before expiry, open positions unwound (and charged) at the end of the data.
  * Reports strategy P&L separately from gold's own price move (beta / correlation to gold).

Everything here is an ANALYSIS of settlement prices, not a claim of tradeable profit. All parameters are assumptions.
"""
import glob
import os
import re

import numpy as np
import pandas as pd

from bhav_clean import load_bhav, per_10g_999

PAIRS = [("GOLDGUINEA", "GOLDTEN"), ("GOLDPETAL", "GOLDTEN")]


# ----------------------------------------------------------------------------- data
def load_days(folder="data"):
    """Load every data\\YYYY-MM-DD.csv. Returns (DataFrame of all days, list of (file, reason) skipped)."""
    frames, skipped = [], []
    for path in sorted(glob.glob(os.path.join(folder, "*.csv"))):
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", os.path.basename(path))
        if not m:
            skipped.append((path, "no YYYY-MM-DD in file name"))
            continue
        ddmmyyyy = "%s/%s/%s" % (m.group(3), m.group(2), m.group(1))
        try:
            frames.append(per_10g_999(load_bhav(path, ddmmyyyy)))
        except Exception as e:
            skipped.append((path, str(e)))
    if not frames:
        raise ValueError("No usable Bhavcopy files in %s\\ . Skipped: %s" % (folder, skipped))
    return pd.concat(frames, ignore_index=True), skipped


def build_spreads(df, pairs=PAIRS):
    """One row per (pair, expiry, date) where both legs have a settlement price."""
    px = df.pivot_table(index=["date", "expiry_date"], columns="symbol", values="close_per10g")
    vol = df.pivot_table(index=["date", "expiry_date"], columns="symbol", values="volume_lots")
    parts = []
    for a, b in pairs:
        if a not in px.columns or b not in px.columns:
            continue
        t = pd.DataFrame({"price_a": px[a], "price_b": px[b], "vol_a": vol[a], "vol_b": vol[b]})
        t = t.dropna(subset=["price_a", "price_b"]).reset_index()
        t["pair"] = "%s-%s" % (a, b)
        parts.append(t)
    if not parts:
        raise ValueError("Need GOLDTEN plus GOLDGUINEA or GOLDPETAL in the data to build spreads.")
    s = pd.concat(parts, ignore_index=True).rename(columns={"expiry_date": "expiry"})
    s["spread"] = s["price_a"] - s["price_b"]
    s["spread_pct"] = 100.0 * s["spread"] / s["price_b"]
    s["dte"] = (s["expiry"] - s["date"]).dt.days
    return s.sort_values(["pair", "expiry", "date"]).reset_index(drop=True)


def add_zscores(s, lookback=20, min_obs=10):
    """z of spread_pct vs the previous `lookback` days of the same pair+expiry (today excluded)."""
    s = s.copy()
    g = s.groupby(["pair", "expiry"])["spread_pct"]
    mean = g.transform(lambda x: x.shift(1).rolling(lookback, min_periods=min_obs).mean())
    std = g.transform(lambda x: x.shift(1).rolling(lookback, min_periods=min_obs).std())
    s["z"] = (s["spread_pct"] - mean) / std.replace(0, np.nan)
    return s


# ----------------------------------------------------------------------------- backtest
def backtest(s, entry_z=2.0, exit_z=0.5, min_dte=10, min_vol=50, cost_bps=5.0, lag=1, grams=80.0):
    """Walk-forward backtest on a spreads table that already has a z column.

    pos = +1: long A (rich-candidate leg) and short B; pos = -1: short A and long B. Equal grams on both legs.
    Decision at close of day i -> held from close of day i + 1 + lag.  P&L is in Rs for `grams` of gold per leg.
    """
    daily_rows, trade_rows = [], []
    units = grams / 10.0                       # prices are Rs per 10 g
    for (pair, expiry), g in s.groupby(["pair", "expiry"]):
        g = g.sort_values("date").reset_index(drop=True)
        n = len(g)
        a, b = g["price_a"].to_numpy(), g["price_b"].to_numpy()
        z, dte = g["z"].to_numpy(), g["dte"].to_numpy()
        ok = (g["vol_a"].to_numpy() >= min_vol) & (g["vol_b"].to_numpy() >= min_vol) & (dte >= min_dte)

        desired = np.zeros(n)
        pos = 0
        for i in range(n):
            if pos == 0:
                if ok[i] and not np.isnan(z[i]):
                    if z[i] >= entry_z:
                        pos = -1                # A looks rich vs B: short A, long B
                    elif z[i] <= -entry_z:
                        pos = 1                 # A looks cheap vs B: long A, short B
            else:
                if dte[i] < min_dte or (not np.isnan(z[i]) and abs(z[i]) <= exit_z):
                    pos = 0
            desired[i] = pos

        held = np.zeros(n)
        for j in range(n):
            i = j - 1 - lag
            held[j] = desired[i] if i >= 0 else 0.0

        pnl = np.zeros(n)
        cost = np.zeros(n)
        gold = np.zeros(n)
        for j in range(1, n):
            pnl[j] = held[j] * ((a[j] - a[j - 1]) - (b[j] - b[j - 1])) * units
            notional_prev = units * (a[j - 1] + b[j - 1])
            cost[j] = abs(held[j] - held[j - 1]) * cost_bps / 1e4 * notional_prev
            gold[j] = (b[j] - b[j - 1])
        final_cost = abs(held[n - 1]) * cost_bps / 1e4 * units * (a[n - 1] + b[n - 1]) if n else 0.0
        if n:
            cost[n - 1] += final_cost

        for j in range(n):
            daily_rows.append((g["date"][j], pair, expiry, held[j], pnl[j], cost[j], gold[j]))

        j = 1
        while j < n:
            if held[j] != 0:
                j0, d = j, held[j]
                while j + 1 < n and held[j + 1] == d:
                    j += 1
                j1 = j
                exit_cost = cost[j1 + 1] if j1 + 1 < n else final_cost
                gross = pnl[j0:j1 + 1].sum()
                c = cost[j0] + exit_cost
                i_sig = j0 - 1 - lag
                trade_rows.append({
                    "pair": pair, "expiry": expiry, "direction": "long A / short B" if d > 0 else "short A / long B",
                    "signal_date": g["date"][i_sig], "entry_date": g["date"][j0 - 1], "exit_date": g["date"][j1],
                    "entry_z": z[i_sig], "gross": gross, "costs": c, "net": gross - c,
                })
            j += 1

    daily = pd.DataFrame(daily_rows, columns=["date", "pair", "expiry", "held", "gross", "cost", "gold_move"])
    daily["net"] = daily["gross"] - daily["cost"]
    trades = pd.DataFrame(trade_rows, columns=["pair", "expiry", "direction", "signal_date", "entry_date", "exit_date",
                                                "entry_z", "gross", "costs", "net"])
    gold_by_date = s.assign(dB=s.groupby(["pair", "expiry"])["price_b"].diff()).groupby("date")["dB"].mean()
    return {"daily": daily, "trades": trades, "gold": gold_by_date,
            "params": dict(entry_z=entry_z, exit_z=exit_z, min_dte=min_dte, min_vol=min_vol, cost_bps=cost_bps, lag=lag, grams=grams)}


def summarize(res, start=None):
    """Headline numbers. `start` limits to dates (and trade entries) on/after that date, e.g. the unseen period."""
    d, t = res["daily"], res["trades"]
    if start is not None:
        d = d[d["date"] >= start]
        t = t[t["entry_date"] >= start]
    per_date = d.groupby("date").agg(net=("net", "sum"), gross=("gross", "sum"), cost=("cost", "sum"), active=("held", lambda x: (x != 0).any()))
    cum = per_date["net"].cumsum()
    mdd = float((cum - cum.cummax()).min()) if len(cum) else 0.0
    out = {
        "days": int(len(per_date)), "trades": int(len(t)),
        "gross_pnl": float(per_date["gross"].sum()), "costs": float(per_date["cost"].sum()), "net_pnl": float(per_date["net"].sum()),
        "hit_rate": float((t["net"] > 0).mean()) if len(t) else float("nan"),
        "max_drawdown": mdd, "beta_to_gold": float("nan"), "corr_to_gold": float("nan"),
    }
    gold = res["gold"].reindex(per_date.index)
    act = per_date["active"].to_numpy() & gold.notna().to_numpy()
    if act.sum() >= 8 and np.std(gold[act]) > 0 and np.std(per_date["net"][act]) > 0:
        x, y = gold[act].to_numpy(dtype=float), per_date["net"][act].to_numpy(dtype=float)
        out["beta_to_gold"] = float(np.polyfit(x, y, 1)[0])
        out["corr_to_gold"] = float(np.corrcoef(x, y)[0, 1])
    return out


def cost_sensitivity(s, bps_list=(0, 2, 5, 10, 20), **kw):
    rows = []
    for bps in bps_list:
        r = summarize(backtest(s, cost_bps=bps, **kw))
        rows.append({"cost_bps_per_side": bps, "trades": r["trades"], "gross_pnl": r["gross_pnl"], "costs": r["costs"], "net_pnl": r["net_pnl"]})
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------- alerts and calendar
def todays_alerts(s, entry_z=2.0, min_dte=10, min_vol=50):
    """Spreads on the latest date that are unusual enough AND tradeable by our rules. Empty = quiet day."""
    last = s["date"].max()
    t = s[s["date"] == last]
    hit = t[(t["z"].abs() >= entry_z) & (t["dte"] >= min_dte) & (t["vol_a"] >= min_vol) & (t["vol_b"] >= min_vol)]
    return last, hit.sort_values("z", key=lambda x: -x.abs())


def contract_calendar(df):
    """Per contract: first and last day seen, days to expiry from the latest date in the data."""
    latest = df["date"].max()
    c = df.groupby(["symbol", "expiry_date"]).agg(first_seen=("date", "min"), last_seen=("date", "max"), days_traded=("date", "nunique")).reset_index()
    c["days_to_expiry"] = (c["expiry_date"] - latest).dt.days
    return c.sort_values(["expiry_date", "symbol"]).reset_index(drop=True)


if __name__ == "__main__":
    df, skipped = load_days("data")
    s = add_zscores(build_spreads(df))
    res = backtest(s)
    print("Days loaded:", df["date"].nunique(), "| skipped files:", len(skipped))
    print(summarize(res))
    print(cost_sensitivity(s).round(0).to_string(index=False))
