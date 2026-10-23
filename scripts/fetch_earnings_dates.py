"""Next results dates for US companies, from Finnhub's earnings calendar (free key).

The calendar is fetched in 10-day windows over the next 100 days (each response is capped),
kept to companies in the universe, and saved as data/earnings.json: {"US-AAPL": "2026-10-30"}.
UK results dates are estimated by the screener from each company's financial year end.

    python scripts/fetch_earnings_dates.py [--universe universe/us.csv]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import time
import urllib.parse
import urllib.request

OUT = "data/earnings.json"


def get(url: str):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "BullPulse"}), timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="universe/us.csv")
    ap.add_argument("--days", type=int, default=100)
    args = ap.parse_args()
    key = os.environ.get("FINNHUB_API_KEY", "").strip()
    if not key:
        print("::warning::Results dates skipped: FINNHUB_API_KEY is not set.")
        return
    want = {r["ticker"].replace(".", ""): "US-" + r["ticker"].replace(".", "") for r in csv.DictReader(open(args.universe, newline=""))}
    today = dt.date.today()
    found: dict[str, str] = {}
    for start in range(0, args.days, 10):
        a, b = today + dt.timedelta(days=start), today + dt.timedelta(days=start + 9)
        d = get("https://finnhub.io/api/v1/calendar/earnings?" + urllib.parse.urlencode({"from": a, "to": b, "token": key})) or {}
        for e in d.get("earningsCalendar") or []:
            sym = (e.get("symbol") or "").replace(".", "").replace("-", "")
            if sym in want and e.get("date"):
                cur = found.get(want[sym])
                if cur is None or e["date"] < cur:
                    found[want[sym]] = e["date"]
        time.sleep(1.1)
    json.dump({"generated": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "next": found}, open(OUT, "w"), indent=0, sort_keys=True)
    print(f"::notice::Results dates for {len(found)} of {len(want)} US companies")


if __name__ == "__main__":
    main()
