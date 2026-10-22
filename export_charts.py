"""Export the report's charts as separate PNG files (for slides and posts).

Run:  python export_charts.py      -> writes the 3 images into the charts_ppt folder
Needs the same folder as report.py, goldlens.py and bhav_clean.py, plus your data\\ folder.
"""
import os

import report as R
import goldlens as gl

os.makedirs("charts_ppt", exist_ok=True)
names = iter(["1_snapshot", "2_spread", "3_backtest"])


def save(fig):
    path = os.path.join("charts_ppt", next(names) + ".png")
    fig.savefig(path, dpi=200, facecolor="white", bbox_inches="tight")
    R.plt.close(fig)
    print("Saved", path)
    return path


R.png = save
df, _ = gl.load_days("data")
s = gl.add_zscores(gl.build_spreads(df), lookback=R.LOOKBACK)
res = gl.backtest(s, entry_z=R.ENTRY_Z, exit_z=R.EXIT_Z, min_dte=R.MIN_DTE, min_vol=R.MIN_VOL, cost_bps=R.COST_BPS, lag=R.LAG)
R.fig_snapshot(df)
cnt = s.dropna(subset=["z"]).groupby(["pair", "expiry"]).size()
(pair, expiry) = cnt.idxmax()
R.fig_spread(s, pair, expiry)
R.fig_backtest(res)
