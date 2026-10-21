"""GoldLens report: builds ONE html page (report.html) from your data\\ folder. Double-click it to open.

Run:  python report.py
Needs: pip install pandas numpy matplotlib   (bhav_clean.py and goldlens.py in the same folder)

Sections: quiet alert box, today's contract snapshot, spread history, walk-forward backtest (costs, gold separated),
cost sensitivity, contract lifecycle calendar, and the limits of the analysis.
"""
import base64
import html
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import goldlens as gl

COLORS = {"GOLDTEN": "#2a78d6", "GOLDPETAL": "#eb6834", "GOLDGUINEA": "#1baf7a", "GOLDM": "#eda100"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e5e1"
ENTRY_Z, EXIT_Z, MIN_DTE, MIN_VOL, COST_BPS, LAG, LOOKBACK = 2.0, 0.5, 10, 50, 5.0, 1, 20


def png(fig):
    b = io.BytesIO()
    fig.savefig(b, format="png", dpi=150, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def fig_snapshot(df):
    day = df[df["date"] == df["date"].max()]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for sym in ["GOLDTEN", "GOLDPETAL", "GOLDGUINEA", "GOLDM"]:
        d = day[day["symbol"] == sym].sort_values("expiry_date")
        if len(d):
            ax.plot(d["expiry_date"], d["close_per10g"], color=COLORS[sym], lw=2, marker="o", ms=5, mec="white", label=sym)
    style(ax)
    ax.set_ylabel("Rs per 10 g (999 basis)", color=INK2, fontsize=9)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: "{:,.0f}".format(x)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2, loc="upper left")
    return png(fig)


def fig_spread(s, pair, expiry):
    t = s[(s["pair"] == pair) & (s["expiry"] == expiry)].sort_values("date")
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 4.6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    col = COLORS[pair.split("-")[0]]
    a1.plot(t["date"], t["spread_pct"], color=col, lw=2)
    style(a1)
    a1.set_ylabel("spread, % of GOLDTEN", color=INK2, fontsize=9)
    a2.plot(t["date"], t["z"], color=INK2, lw=1.5)
    for y in (ENTRY_Z, -ENTRY_Z):
        a2.axhline(y, color="#c0392b", lw=0.8, ls="--")
    a2.axhline(0, color=GRID, lw=0.8)
    style(a2)
    a2.set_ylabel("z (past data only)", color=INK2, fontsize=9)
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    return png(fig)


def fig_backtest(res):
    d = res["daily"].groupby("date")[["gross", "cost", "net"]].sum().sort_index()
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot(d.index, d["gross"].cumsum(), color="#2a78d6", lw=2, label="gross (before costs)")
    ax.plot(d.index, d["net"].cumsum(), color="#eb6834", lw=2, label="net (after costs)")
    ax.axhline(0, color=INK2, lw=0.8)
    style(ax)
    ax.set_ylabel("cumulative Rs", color=INK2, fontsize=9)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: "{:,.0f}".format(x)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2, loc="best")
    return png(fig)


def table(df, fmt=None):
    fmt = fmt or {}
    h = "<table><tr>" + "".join("<th>%s</th>" % html.escape(str(c)) for c in df.columns) + "</tr>"
    for _, r in df.iterrows():
        h += "<tr>" + "".join("<td>%s</td>" % html.escape(fmt.get(c, lambda v: str(v))(r[c])) for c in df.columns) + "</tr>"
    return h + "</table>"


def money(v):
    return "{:,.0f}".format(v)


def main():
    df, skipped = gl.load_days("data")
    s = gl.add_zscores(gl.build_spreads(df), lookback=LOOKBACK)
    res = gl.backtest(s, entry_z=ENTRY_Z, exit_z=EXIT_Z, min_dte=MIN_DTE, min_vol=MIN_VOL, cost_bps=COST_BPS, lag=LAG)
    sm = gl.summarize(res)
    sens = gl.cost_sensitivity(s, entry_z=ENTRY_Z, exit_z=EXIT_Z, min_dte=MIN_DTE, min_vol=MIN_VOL, lag=LAG)
    last, alerts = gl.todays_alerts(s, ENTRY_Z, MIN_DTE, MIN_VOL)
    cal = gl.contract_calendar(df)
    ndays = df["date"].nunique()

    # alert box: quiet by default
    if alerts.empty:
        alert_html = ("<div class='box quiet'><b>No alerts on %s.</b> No spread is unusual enough (|z| &ge; %.1f, past %d days only) "
                      "with enough volume and time to expiry. Silence is the normal state.</div>" % (last.strftime("%d %b %Y"), ENTRY_Z, LOOKBACK))
    else:
        rows = alerts[["pair", "expiry", "spread", "spread_pct", "z", "dte"]].copy()
        rows["expiry"] = rows["expiry"].dt.strftime("%d %b %Y")
        alert_html = ("<div class='box alert'><b>%d alert(s) on %s.</b> Unusual vs the past %d days. A flag to look at, not a trade instruction.</div>%s"
                      % (len(alerts), last.strftime("%d %b %Y"), LOOKBACK,
                         table(rows, {"spread": lambda v: "%.0f" % v, "spread_pct": lambda v: "%.3f" % v, "z": lambda v: "%.2f" % v})))

    # spread history: the pair+expiry with the most z-scored days
    cnt = s.dropna(subset=["z"]).groupby(["pair", "expiry"]).size()
    if len(cnt):
        (pair, expiry), n = cnt.idxmax(), cnt.max()
        spread_img = "<img src='%s'>" % fig_spread(s, pair, expiry)
        spread_note = "%s, expiry %s (%d scored days)." % (pair, expiry.strftime("%d %b %Y"), n)
    else:
        spread_img, spread_note = "", "Not enough history yet to score spreads (needs about %d trading days)." % 10

    verdict = ("Net P&L is %s Rs over %d trades; gross was %s Rs and costs %s Rs. " %
               (money(sm["net_pnl"]), sm["trades"], money(sm["gross_pnl"]), money(sm["costs"])))
    if sm["trades"] == 0:
        verdict = "No trades triggered with these rules on this data. "
    elif sm["trades"] < 20:
        verdict += ("Only %d trades, far too few to conclude anything either way. This shows the pipeline works, "
                    "not whether a persistent edge exists. " % sm["trades"])
    elif sm["net_pnl"] <= 0:
        verdict += "No persistent edge after costs on this sample, which is a valid outcome. "
    else:
        verdict += "Positive here, but this is a short in-sample window: treat it as a hypothesis, not proof. "
    gold_txt = ("Correlation of strategy P&L to the gold price move on active days: %.2f (beta %.1f Rs per Rs move)." %
                (sm["corr_to_gold"], sm["beta_to_gold"])) if not np.isnan(sm["corr_to_gold"]) else \
        "Too few active days to measure how much P&L is just gold moving."

    page = """<!doctype html><html><head><meta charset='utf-8'><title>GoldLens report</title>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<style>
body{font:15px/1.5 system-ui,Segoe UI,Arial;color:#0b0b0b;max-width:900px;margin:24px auto;padding:0 16px}
h1{margin:0 0 4px} h2{margin:32px 0 6px;font-size:18px} .sub{color:#52514e;margin:0 0 16px}
.box{padding:12px 14px;border-radius:8px;border:1px solid #e6e5e1;margin:12px 0}
.quiet{background:#f6f6f3}.alert{background:#fff4e5;border-color:#eda100}
table{border-collapse:collapse;width:100%%;font-size:13px;margin:8px 0}th,td{border-bottom:1px solid #e6e5e1;padding:5px 8px;text-align:right}
th:first-child,td:first-child{text-align:left} img{max-width:100%%} .small{color:#52514e;font-size:12.5px}
</style></head><body>
<h1>GoldLens</h1><p class='sub'>Relative pricing across MCX gold futures. %d trading days, %s to %s. Source: MCX Bhavcopy settlement prices.</p>
%s
<h2>1. Same gold, different contracts</h2><p class='small'>Normalised to Rs per 10 g (999 basis), latest day.</p><img src='%s'>
<h2>2. Spread history</h2><p class='small'>%s Spread = (A - GOLDTEN) / GOLDTEN. z-score uses only earlier days.</p>%s
<h2>3. Walk-forward backtest</h2>
<p>%s%s</p><img src='%s'>
<p class='small'>Rules: enter when |z| &ge; %.1f, exit at |z| &le; %.1f or %d days before expiry; signal at the close, filled %d day(s) later at settlement;
equal grams on both legs; cost %.0f bps of notional per side on contracts actually held; min volume %d lots per leg. Hit rate %s, max drawdown %s Rs.</p>
<h2>4. How much do costs matter?</h2>%s
<h2>5. Contract lifecycle calendar</h2><p class='small'>Days to expiry counted from %s.</p>%s
<h2>6. Limits</h2><ul class='small'>
<li>Settlement price is not a fill price; volume is not liquidity. Thin far-month contracts can show spreads you could never trade.</li>
<li>Sample is %d trading days, so results are descriptive, not statistically strong. GOLDTEN history only starts in 2025.</li>
<li>The GOLDM purity adjustment (999/995) is an assumption to validate against MCX contract specs.</li>
<li>GOLDPETAL is quoted per gram in whole rupees, so its price per 10 g moves in steps of Rs 10; small spreads are partly rounding.</li>
<li>Costs are an assumed flat %.0f bps; real brokerage, exchange fees, taxes and margin funding differ.</li>
<li>Analysis only. Not investment advice.</li></ul>
%s
</body></html>""" % (
        ndays, df["date"].min().strftime("%d %b %Y"), df["date"].max().strftime("%d %b %Y"), alert_html,
        fig_snapshot(df), html.escape(spread_note), spread_img,
        verdict, gold_txt, fig_backtest(res),
        ENTRY_Z, EXIT_Z, MIN_DTE, LAG + 1, COST_BPS, MIN_VOL,
        ("%.0f%%" % (100 * sm["hit_rate"])) if not np.isnan(sm["hit_rate"]) else "n/a", money(sm["max_drawdown"]),
        table(sens, {"cost_bps_per_side": lambda v: "%.0f" % v, "trades": lambda v: "%.0f" % v, "gross_pnl": money, "costs": money, "net_pnl": money}),
        df["date"].max().strftime("%d %b %Y"),
        table(cal.assign(expiry_date=cal["expiry_date"].dt.strftime("%d %b %Y"), first_seen=cal["first_seen"].dt.strftime("%d %b"),
                         last_seen=cal["last_seen"].dt.strftime("%d %b")).rename(columns={"expiry_date": "expiry"})),
        ndays, COST_BPS,
        ("<p class='small'>Files skipped: %s</p>" % html.escape("; ".join("%s (%s)" % (p, r) for p, r in skipped))) if skipped else "")
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(page)
    print("Wrote report.html with %d trading days. Open it by double-clicking." % ndays)


if __name__ == "__main__":
    main()
