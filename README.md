# GoldLens: relative pricing across MCX gold futures

Hack in Hills '26, Track: Commodity Derivatives Intelligence.

GoldLens compares the four MCX gold futures (GOLDM, GOLDTEN, GOLDGUINEA, GOLDPETAL) after normalising unit, quote base and purity to Rs per 10 g (999 basis). It flags unusual relative pricing quietly, tests a spread rule with a walk-forward backtest that charges costs, and reports honestly when there is nothing to find.

## Result on real data (1 Sep to 20 Oct 2026, 35 trading days)

| | Rs |
|---|---|
| Gross P&L (before costs) | +662 |
| Costs at an assumed 5 bps per side | 46,558 |
| Net P&L | -45,896 |

19 trades. Gross P&L is close to zero, so on this sample the rule shows **no edge even before costs**. "No persistent edge after costs" is a valid outcome, and we report it rather than tune parameters until it looks profitable. 19 trades over 35 days is a small sample, so this is descriptive, not a statistical claim. The report also includes a cost-sensitivity table and the strategy's correlation to the gold move itself.

## How it avoids the common traps
- Contracts are keyed by **expiry date**, never by a continuous near-month series.
- The date inside each file is checked against the requested date (MCX can return the latest day instead). Mismatched files are rejected.
- z-scores use **only earlier days** (no look-ahead). Signals are filled a day or more later at settlement.
- Costs are charged on the contracts actually held, and positions close before expiry.
- Strategy P&L is shown next to the gold price move, so a rising market is not mistaken for skill.
- Alerts are quiet: nothing is shown unless a spread is unusual, liquid enough and not too close to expiry.

## Files
- `bhav_clean.py`: load and validate one Bhavcopy CSV, keep gold futures, normalise prices.
- `goldlens.py`: spreads, z-scores, backtest, alerts, contract calendar.
- `report.py`: builds `report.html` (alerts, charts, backtest, cost sensitivity, calendar, limits).
- `ingest_downloads.py`: copies downloaded Bhavcopy CSVs into `data/` named by the date inside each file.
- `report.html`: the report generated from the run above.

## Run it yourself (Windows)
1. `pip install pandas numpy matplotlib`
2. Raw MCX data is not included in this repo. On mcxindia.com go to Market Data, then BhavCopy, choose **Date Wise**, instrument **ALL**. For each trading day: pick the date, click **Show**, check the table date, then click the **CSV** icon.
3. `python ingest_downloads.py` (copies the CSVs from Downloads into `data/`).
4. `python report.py`, then open `report.html`.

## Limits
- Settlement price is not a fill price; volume is not liquidity. Thin far-month contracts can show spreads that could not be traded.
- Short sample. GOLDTEN history only starts in 2025.
- The GOLDM purity adjustment (999/995) is an assumption still to be validated against the MCX contract specifications.
- GOLDPETAL is quoted per gram in whole rupees, so its price per 10 g moves in steps of Rs 10.
- Costs are an assumed flat 5 bps per side; real brokerage, exchange fees, taxes and margin funding differ.
- Analysis only. Not investment advice.
