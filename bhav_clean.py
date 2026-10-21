"""GoldLens starter (v2): load and sanity-check one MCX Bhavcopy CSV for gold futures.

Matches the real CSV from mcxindia.com/market-data/bhavcopy (Date Wise, CSV icon):
  Date,Instrument Name,Symbol,Expiry Date,Option Type,Strike Price,Open,High,Low,Close,
  Previous Close,Volume(Lots),Volume(In 000's),Value(Lacs),Open Interest(Lots)
  e.g. "12 Oct 2026","FUTCOM","ALUMINI      ","30OCT2026","-","0","333.45",...

Checks from the Hack in Hills brief:
  * the Date inside the file must equal the date you asked for (MCX may silently return the latest day)
  * request dates are DD/MM/YYYY
  * Symbol values are space-padded
  * contracts are keyed by expiry date, never by a continuous near-month series
Only futures (FUTCOM) are kept; options (OPTFUT) are dropped.

Run:  python bhav_clean.py data\\2026-10-12.csv 12/10/2026
"""
import re
import sys
from datetime import datetime

import pandas as pd

GOLD = ["GOLDM", "GOLDTEN", "GOLDGUINEA", "GOLDPETAL"]

# Contract mechanics from the brief: (grams the price is quoted for, purity)
SPEC = {
    "GOLDM": (10, 995),
    "GOLDTEN": (10, 999),
    "GOLDGUINEA": (8, 999),
    "GOLDPETAL": (1, 999),
}


def _norm(c):
    return re.sub(r"[^a-z0-9]", "", str(c).lower())


# normalised file header -> our column name
COLS = {
    "date": "date", "instrumentname": "instrument", "symbol": "symbol", "expirydate": "expiry_date",
    "open": "open", "high": "high", "low": "low", "close": "close", "previousclose": "prev_close",
    "volumelots": "volume_lots", "openinterestlots": "open_interest_lots",
}


def load_bhav(path, requested_ddmmyyyy):
    """Return a clean gold-futures DataFrame for one trading day. Raises if the file's date != requested."""
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    raw.columns = [_norm(c) for c in raw.columns]
    missing = [c for c in COLS if c not in raw.columns]
    if missing:
        raise ValueError("Columns not found %s. Columns in file: %s" % (missing, list(raw.columns)))
    df = raw[list(COLS)].rename(columns=COLS).copy()

    df["symbol"] = df["symbol"].str.strip().str.upper()
    df["instrument"] = df["instrument"].str.strip().str.upper()
    df["date"] = pd.to_datetime(df["date"].str.strip(), format="%d %b %Y")
    df["expiry_date"] = pd.to_datetime(df["expiry_date"].str.strip(), format="%d%b%Y")

    asked = datetime.strptime(requested_ddmmyyyy, "%d/%m/%Y")
    returned = df["date"].dropna().unique()
    if len(returned) != 1 or pd.Timestamp(returned[0]) != pd.Timestamp(asked):
        raise ValueError("Date mismatch: asked %s but file contains %s" % (requested_ddmmyyyy, list(returned)))

    fut = df[df["instrument"] == "FUTCOM"]
    gold = fut[fut["symbol"].isin(GOLD)].copy()
    if gold.empty:
        found = sorted(s for s in fut["symbol"].unique() if "GOLD" in s)
        raise ValueError("No futures rows for %s. GOLD-like futures symbols in this file: %s" % (GOLD, found))

    for c in ["open", "high", "low", "close", "prev_close", "volume_lots", "open_interest_lots"]:
        gold[c] = pd.to_numeric(gold[c], errors="coerce")      # blanks -> NaN
    return gold.sort_values(["symbol", "expiry_date"]).reset_index(drop=True)


def per_10g_999(df, adjust_purity=True):
    """Close price converted to Rs per 10 g of 999 gold.

    ASSUMPTION TO VALIDATE (do not present as fact): the purity adjustment uses 999/purity.
    Check it against the MCX contract specifications before relying on it.
    """
    out = df.copy()
    grams = out["symbol"].map(lambda s: SPEC[s][0])
    purity = out["symbol"].map(lambda s: SPEC[s][1])
    out["close_per10g"] = out["close"] * 10.0 / grams
    if adjust_purity:
        out["close_per10g"] = out["close_per10g"] * 999.0 / purity
    return out


if __name__ == "__main__":
    f, d = sys.argv[1], sys.argv[2]
    g = per_10g_999(load_bhav(f, d))
    print(g[["symbol", "expiry_date", "close", "close_per10g", "volume_lots", "open_interest_lots"]].to_string(index=False))
