"""Copy MCX Bhavcopy CSVs from your Downloads folder into data\\ and name them YYYY-MM-DD.csv.

You download many days from mcxindia.com/market-data/bhavcopy (Date Wise, CSV icon). Files keep odd names.
This script opens each CSV in Downloads, reads the trading date inside it, and copies it to data\\<date>.csv.
It COPIES (your Downloads files stay), skips non-Bhavcopy files, and skips days you already have.

Run:  python ingest_downloads.py            (uses your Downloads folder)
      python ingest_downloads.py D:\\some\\other\\folder
"""
import csv
import glob
import os
import shutil
import sys
from datetime import datetime


def file_date(path):
    """Trading date inside a Bhavcopy CSV, or None if it is not one."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            r = csv.reader(f)
            head = [h.strip().lower() for h in next(r)]
            if head[:3] != ["date", "instrument name", "symbol"]:
                return None
            row = next(r)
        return datetime.strptime(row[0].strip(), "%d %b %Y").date()
    except Exception:
        return None


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.expanduser("~"), "Downloads")
    os.makedirs("data", exist_ok=True)
    copied, have, skipped = [], [], 0
    for path in sorted(glob.glob(os.path.join(src, "*.csv"))):
        d = file_date(path)
        print("%-45s -> %s" % (os.path.basename(path)[:45], d if d else "(not a Bhavcopy file)"))
        if d is None:
            skipped += 1
            continue
        target = os.path.join("data", d.strftime("%Y-%m-%d") + ".csv")
        if os.path.exists(target):
            have.append(d)
            continue
        shutil.copyfile(path, target)
        copied.append(d)
    days = sorted(os.path.basename(p)[:10] for p in glob.glob(os.path.join("data", "????-??-??.csv")))
    print("Copied %d new day(s), %d already in data\\, %d non-Bhavcopy CSV(s) ignored." % (len(copied), len(have), skipped))
    print("data\\ now has %d trading day(s)%s" % (len(days), (": %s to %s" % (days[0], days[-1])) if days else "."))


if __name__ == "__main__":
    main()
