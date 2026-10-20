"""Fetch revenue and earnings growth for US stocks from SEC EDGAR (free, official, no key).

For each company with a CIK in the universe, downloads its XBRL "company facts" and computes:
  * rev_growth   year-on-year revenue growth of the latest reported period
  * rev_accel    change in that growth versus the previous quarter (positive = accelerating)
  * eps_growth   year-on-year diluted EPS growth (only when the year-ago EPS was positive)
  * period/asof  the period the figures describe and its end date

Writes data/fundamentals.json. Fundamentals change quarterly, so the nightly job runs this
weekly (or when the file is missing). SEC asks for a descriptive User-Agent with a contact and
at most 10 requests a second; this script makes about 2 a second.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request

OUT = "data/fundamentals.json"
REVENUE = [  # in priority order; companies switch concepts over time (e.g. after ASC 606)
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "RevenuesNetOfInterestExpense",
    "SalesRevenueGoodsNet",
]
EPS = ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"]


def user_agent() -> str:
    contact = os.environ.get("SEC_CONTACT_EMAIL") or "258917638+ptkwcxzd72-rgb@users.noreply.github.com"
    return f"BullPulse research screener (github.com/ptkwcxzd72-rgb/BullPulse) {contact}"


def get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": user_agent(), "Accept-Encoding": "gzip"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return json.loads(data)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(3 * (attempt + 1))
        except Exception:
            time.sleep(3 * (attempt + 1))
    return None


def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def periods(facts: dict, concepts: list[str], unit: str) -> dict[tuple[str, str], float]:
    """(start, end) -> value for duration facts, first concept in priority order wins,
    latest filing wins within a concept."""
    out: dict[tuple[str, str], float] = {}
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for c in concepts:
        rows = gaap.get(c, {}).get("units", {}).get(unit, [])
        best: dict[tuple[str, str], tuple[str, float]] = {}
        for r in rows:
            if "start" not in r or "end" not in r or r.get("val") is None:
                continue
            k = (r["start"], r["end"])
            filed = r.get("filed", "")
            if k not in best or filed > best[k][0]:
                best[k] = (filed, float(r["val"]))
        for k, (_, v) in best.items():
            out.setdefault(k, v)
    return out


def split(p: dict[tuple[str, str], float]):
    q, a = {}, {}
    for (s, e), v in p.items():
        days = (d(e) - d(s)).days
        if 80 <= days <= 100:
            q[e] = v
        elif 350 <= days <= 380:
            a[e] = v
    return q, a


def year_ago(series: dict[str, float], end: str) -> float | None:
    target = d(end) - dt.timedelta(days=365)
    for e, v in series.items():
        if abs((d(e) - target).days) <= 20:
            return v
    return None


def growth(series: dict[str, float], end: str, need_positive: bool = True):
    prev = year_ago(series, end)
    cur = series.get(end)
    if prev is None or cur is None or (need_positive and prev <= 0) or prev == 0:
        return None
    return cur / prev - 1


def analyse(facts: dict) -> dict | None:
    rq, ra = split(periods(facts, REVENUE, "USD"))
    eq, ea = split(periods(facts, EPS, "USD/shares"))
    if not rq and not ra:
        return None
    lq = max(rq) if rq else ""
    la = max(ra) if ra else ""
    out: dict = {}
    if lq and lq >= la:
        g = growth(rq, lq)
        if g is None and la:
            lq = ""
        else:
            out.update(period="quarter", asof=lq, rev_growth=g)
            # acceleration: growth now vs growth of the previous quarter
            earlier = [e for e in rq if (d(lq) - d(e)).days in range(70, 115)]
            if g is not None and earlier:
                g0 = growth(rq, earlier[0])
                if g0 is not None:
                    out["rev_accel"] = g - g0
            eg = growth(eq, lq) if lq in eq else None
            if eg is not None:
                out["eps_growth"] = eg
    if "rev_growth" not in out and la:
        g = growth(ra, la)
        if g is None:
            return None
        out.update(period="year", asof=la, rev_growth=g)
        eg = growth(ea, la) if la in ea else None
        if eg is not None:
            out["eps_growth"] = eg
    if out.get("rev_growth") is None:
        return None
    for k in ("rev_growth", "rev_accel", "eps_growth"):
        if k in out:
            out[k] = round(out[k], 4)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="universe")
    ap.add_argument("--prices", default="data/prices", help="only stocks with a price file ('' = all)")
    ap.add_argument("--max-age-days", type=int, default=7, help="skip if the output is newer than this")
    args = ap.parse_args()

    if os.path.exists(OUT) and args.max_age_days > 0:
        age = (time.time() - os.path.getmtime(OUT)) / 86400
        try:
            fresh = json.load(open(OUT)).get("generated", "")
            age = (dt.datetime.utcnow() - dt.datetime.fromisoformat(fresh.rstrip("Z"))).days
        except Exception:
            pass
        if age < args.max_age_days:
            print(f"fundamentals are {age:.0f} days old; skipping (weekly refresh)")
            return

    have = None
    if args.prices and os.path.isdir(args.prices):
        have = {os.path.splitext(f)[0] for f in os.listdir(args.prices)}
    stocks = []
    for f in sorted(glob.glob(os.path.join(args.universe, "*.csv"))):
        for r in csv.DictReader(open(f, newline="")):
            if r.get("cik") and (have is None or r.get("provider_ticker") in have):
                stocks.append(r)
    print(f"fetching SEC company facts for {len(stocks)} companies")
    result, missing = {}, []
    for i, s in enumerate(stocks):
        facts = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(s['cik']):010d}.json")
        a = analyse(facts) if facts else None
        if a:
            result[f"US-{s['ticker'].replace('.', '')}"] = a
        else:
            missing.append(s["ticker"])
        time.sleep(0.5)
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(stocks)}", flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"generated": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z", "source": "SEC EDGAR company facts",
               "stocks": result}, open(OUT, "w"), indent=0)
    print(f"growth data for {len(result)} companies; none for {len(missing)}: {', '.join(missing[:20])}")
    if stocks and not result:
        sys.exit("SEC returned no usable data")


if __name__ == "__main__":
    main()
