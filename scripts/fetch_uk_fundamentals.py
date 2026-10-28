"""Annual-report figures for UK companies, from their ESEF (iXBRL) filings.

UK-listed companies publish their annual reports in machine-readable iXBRL, tagged with IFRS
concepts. filings.xbrl.org (run by XBRL International) collects these and serves each one as
xBRL-JSON, free and without a key. This script:

  1. finds each company's LEI (legal entity identifier): ISIN from the London Stock Exchange's
     instrument data, then LEI from GLEIF's free API (cached in data/uk_ids.json);
  2. downloads the latest three annual reports and keeps only the plain (undimensioned) IFRS
     facts BullPulse uses (cached per filing in data/uk_facts/);
  3. maps the IFRS concepts onto the US-GAAP names that sec_financials.py understands, so the
     UK figures go through exactly the same calculations as the US ones.

UK reports are annual (half-year results are not in ESEF), so growth is year on year and the
"twelve months" figures are the latest financial year. Weekly, like the SEC step.

    python scripts/fetch_uk_fundamentals.py [--universe "universe/uk*.csv"] [--max-age-days 7]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from sec_financials import financials, durations, annual, REVENUE, EPS  # noqa: E402

OUT = "data/fundamentals_uk.json"
IDS = "data/uk_ids.json"
FACTS_DIR = "data/uk_facts"
UA = "BullPulse research (https://github.com/ptkwcxzd72-rgb/BullPulse)"
XBRL = "https://filings.xbrl.org"

# IFRS concept -> the US-GAAP name sec_financials.py reads. Within one target, earlier sources win.
MAP: dict[str, list[str]] = {
    "Revenues": ["Revenue", "RevenueFromContractsWithCustomers"],
    "NetIncomeLoss": ["ProfitLossAttributableToOwnersOfParent"],
    "ProfitLoss": ["ProfitLoss"],
    "OperatingIncomeLoss": ["ProfitLossFromOperatingActivities"],
    "EarningsPerShareDiluted": ["DilutedEarningsLossPerShare", "DilutedEarningsLossPerShareFromContinuingOperations"],
    "EarningsPerShareBasic": ["BasicEarningsLossPerShare", "BasicEarningsLossPerShareFromContinuingOperations"],
    "NetCashProvidedByUsedInOperatingActivities": ["CashFlowsFromUsedInOperatingActivities"],
    "PaymentsToAcquirePropertyPlantAndEquipment": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                                                   "PurchaseOfPropertyPlantAndEquipment",
                                                   "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets"],
    "InterestExpense": ["FinanceCosts", "InterestExpense"],
    "InterestExpenseNonoperating": ["InterestPaidClassifiedAsFinancingActivities", "InterestPaidClassifiedAsOperatingActivities"],
    "PaymentsOfDividendsCommonStock": ["DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities",
                                       "DividendsPaidClassifiedAsFinancingActivities", "DividendsPaid"],
    "CommonStockDividendsPerShareDeclared": ["DividendsRecognisedAsDistributionsToOwnersPerShare"],
    "StockholdersEquity": ["EquityAttributableToOwnersOfParent"],
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": ["Equity"],
    "CashAndCashEquivalentsAtCarryingValue": ["CashAndCashEquivalents"],
    "AssetsCurrent": ["CurrentAssets"],
    "LiabilitiesCurrent": ["CurrentLiabilities"],
    "LongTermDebtNoncurrent": ["NoncurrentPortionOfNoncurrentBorrowings", "LongtermBorrowings"],
    "LongTermDebt": ["Borrowings"],
    "LongTermDebtCurrent": ["CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"],
    "DebtCurrent": ["CurrentPortionOfNoncurrentBorrowings"],
    "ShortTermBorrowings": ["ShorttermBorrowings"],
    "WeightedAverageNumberOfDilutedSharesOutstanding": ["AdjustedWeightedAverageShares", "WeightedAverageShares"],
    "ShareBasedCompensation": ["AdjustmentsForSharebasedPayments"],
    "AllocatedShareBasedCompensationExpense": ["ExpenseFromSharebasedPaymentTransactionsWithEmployees"],
}
WANTED = {c for v in MAP.values() for c in v}
PER_SHARE = {"EarningsPerShareDiluted", "EarningsPerShareBasic", "CommonStockDividendsPerShareDeclared"}


def get_json(url: str, tries: int = 3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            time.sleep(4 * (i + 1) ** 2)
        except Exception:
            time.sleep(4 * (i + 1))
    return None


# ------------------------------------------------------------------ identifiers

def find_lei(ticker: str) -> dict:
    """{'isin', 'lei'} via the LSE instrument record and GLEIF's ISIN mapping."""
    out = {}
    isin = None
    base = ticker.rstrip(".")
    for tidm in dict.fromkeys([base, base + "."]):   # two-letter TIDMs carry a trailing dot (BP., RR.)
        inst = get_json("https://api.londonstockexchange.com/api/gw/lse/instruments/alldata/" + urllib.parse.quote(tidm))
        isin = (inst or {}).get("isin")
        if isin:
            break
    if not isin:
        return out
    out["isin"] = isin
    g = get_json("https://api.gleif.org/api/v1/lei-records?" + urllib.parse.urlencode({"filter[isin]": isin}))
    data = (g or {}).get("data") or []
    if data:
        out["lei"] = data[0]["id"]
        out["legal_name"] = data[0]["attributes"]["entity"]["legalName"]["name"]
    return out


# ------------------------------------------------------------------ filings

def list_filings(lei: str) -> list[dict]:
    """Latest annual reports for a LEI, newest first, one per period end (UK copy preferred)."""
    flt = json.dumps([{"name": "entity", "op": "has", "val": {"name": "identifier", "op": "eq", "val": lei}}])
    d = get_json(f"{XBRL}/api/filings?" + urllib.parse.urlencode({"filter": flt, "sort": "-period_end", "page[size]": 20}))
    by_end: dict[str, dict] = {}
    for f in (d or {}).get("data") or []:
        a = f["attributes"]
        if not a.get("json_url") or not a.get("period_end"):
            continue
        cur = by_end.get(a["period_end"])
        if cur is None or (a.get("country") == "GB" and cur.get("country") != "GB"):
            by_end[a["period_end"]] = a
    return [by_end[k] for k in sorted(by_end, reverse=True)]


def _date(s: str) -> str:
    """xBRL-JSON period boundaries are exclusive at midnight: 2025-01-01T00:00:00 ends 2024-12-31."""
    d = dt.datetime.fromisoformat(s[:19])
    if d.hour == 0 and d.minute == 0 and len(s) > 10:
        d -= dt.timedelta(days=1)
    return d.date().isoformat()


def extract(xj: dict) -> list[dict]:
    """Plain IFRS facts we use: no dimensions beyond concept/entity/period/unit."""
    out = []
    for f in (xj or {}).get("facts", {}).values():
        dims = f.get("dimensions", {})
        concept = dims.get("concept", "")
        if not concept.startswith("ifrs-full:") or concept[10:] not in WANTED:
            continue
        if set(dims) - {"concept", "entity", "period", "unit", "language"}:
            continue
        try:
            val = float(f.get("value"))
        except (TypeError, ValueError):
            continue
        per = dims.get("period", "")
        row = {"c": concept[10:], "u": dims.get("unit", ""), "v": val}
        if "/" in per:
            a, b = per.split("/")
            row["s"] = (dt.date.fromisoformat(a[:10])).isoformat()
            row["e"] = _date(b)
        else:
            row["e"] = _date(per)
        out.append(row)
    return out


def filing_facts(f: dict) -> list[dict]:
    """Cached extract of one filing."""
    os.makedirs(FACTS_DIR, exist_ok=True)
    path = os.path.join(FACTS_DIR, f["fxo_id"] + ".json")
    if os.path.exists(path):
        return json.load(open(path))["facts"]
    xj = get_json(XBRL + f["json_url"])
    if xj is None:
        return []
    facts = extract(xj)
    json.dump({"fxo_id": f["fxo_id"], "period_end": f["period_end"], "added": f.get("date_added", "")[:10], "facts": facts},
              open(path, "w"), separators=(",", ":"))
    return facts


def to_companyfacts(filings: list[tuple[str, list[dict]]]) -> tuple[dict, str]:
    """SEC-companyfacts-shaped dict (US-GAAP names) and the reporting currency."""
    ccys: dict[str, int] = {}
    for _, facts in filings:
        for r in facts:
            if r["c"] in MAP["Revenues"] and r["u"].startswith("iso4217:") and "/" not in r["u"]:
                ccys[r["u"][8:]] = ccys.get(r["u"][8:], 0) + 1
    if not ccys:
        for _, facts in filings:
            for r in facts:
                if r["u"].startswith("iso4217:") and "/" not in r["u"]:
                    ccys[r["u"][8:]] = ccys.get(r["u"][8:], 0) + 1
    if not ccys:
        return {}, ""
    ccy = max(ccys, key=ccys.get)
    present = {r["c"] for _, facts in filings for r in facts}
    g: dict = {}
    for target, sources in MAP.items():
        src = next((s for s in sources if s in present), None)
        if src is None:
            continue
        rows = {"USD": [], "USD/shares": [], "shares": []}
        for filed, facts in filings:
            for r in facts:
                if r["c"] != src:
                    continue
                u = r["u"]
                if u == f"iso4217:{ccy}":
                    key = "USD"
                elif u.startswith(f"iso4217:{ccy}/") or (target in PER_SHARE and u.startswith(f"iso4217:{ccy}")):
                    key = "USD/shares"
                elif u.split(":")[-1] == "shares":
                    key = "shares"
                else:
                    continue
                row = {"end": r["e"], "val": r["v"], "filed": filed, "form": "10-K"}
                if "s" in r:
                    row["start"] = r["s"]
                rows[key].append(row)
        units = {k: v for k, v in rows.items() if v}
        if units:
            g[target] = {"units": units}
    # a total "Borrowings" already includes the current part: don't add current debt on top
    if "LongTermDebt" in g and "LongTermDebtNoncurrent" not in g:
        for k in ("LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings"):
            g.pop(k, None)
    return {"facts": {"us-gaap": g}}, ccy


def growth(facts: dict) -> dict:
    """Year-on-year growth from the annual figures (UK reports are annual)."""
    out: dict = {}
    rev = annual(durations(facts, REVENUE))
    ys = sorted(rev)
    if len(ys) >= 2 and rev[ys[-2]] > 0:
        out["rev_growth"] = round(rev[ys[-1]] / rev[ys[-2]] - 1, 4)
        out["asof"], out["period"] = ys[-1], "year"
        if len(ys) >= 3 and rev[ys[-3]] > 0:
            out["rev_accel"] = round(out["rev_growth"] - (rev[ys[-2]] / rev[ys[-3]] - 1), 4)
    eps = annual(durations(facts, EPS, "USD/shares"))
    es = sorted(eps)
    if len(es) >= 2 and eps[es[-2]] > 0:
        out["eps_growth"] = round(eps[es[-1]] / eps[es[-2]] - 1, 4)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="universe/uk*.csv", help="UK universe files (glob)")
    ap.add_argument("--max-age-days", type=int, default=7)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--budget-min", type=float, default=10, help="stop after this many minutes; the rest continues next run")
    args = ap.parse_args()
    t0 = time.time()

    import glob
    rows = [r for f in sorted(glob.glob(args.universe)) for r in csv.DictReader(open(f, newline="")) if (r.get("type") or "") != "trust"]  # trusts: asset-based, checks do not apply
    if os.path.exists(OUT) and args.max_age_days > 0:
        try:
            old = json.load(open(OUT))
            age = (dt.datetime.utcnow() - dt.datetime.fromisoformat(old["generated"].rstrip("Z"))).days
            covered = len(set(old.get("stocks", {})) & {"LSE-" + r["ticker"].replace(".", "") for r in rows})
            if age < args.max_age_days and old.get("complete", True) and covered >= 0.7 * len(rows):
                print(f"UK fundamentals are {age} days old; skipping (weekly refresh)")
                return
        except Exception:
            pass

    ids = json.load(open(IDS)) if os.path.exists(IDS) else {}
    if args.limit:
        rows = rows[: args.limit]
    prev = json.load(open(OUT)).get("stocks", {}) if os.path.exists(OUT) else {}
    out, missing, complete = {}, [], True
    for r in rows:
        t = r["ticker"]
        if time.time() - t0 > args.budget_min * 60:
            complete = False
            key = "LSE-" + t.replace(".", "")
            if key in prev:
                out[key] = prev[key]
            continue
        if not ids.get(t, {}).get("lei"):
            ids[t] = {**ids.get(t, {}), **find_lei(t)}
            time.sleep(0.5)
        lei = ids[t].get("lei")
        if not lei:
            missing.append(f"{t} (no LEI)")
            continue
        fl = list_filings(lei)[:3]
        if not fl:
            missing.append(f"{t} (no ESEF filings)")
            continue
        got = [(f.get("date_added", "")[:10] or f["period_end"], filing_facts(f)) for f in fl]
        facts, ccy = to_companyfacts(got)
        if not facts:
            missing.append(f"{t} (no usable figures)")
            continue
        fin = financials(facts)
        fin["ccy"] = ccy
        entry = {**growth(facts), "fin": fin, "source": "ESEF annual report", "lei": lei}
        out["LSE-" + t.replace(".", "")] = entry
        time.sleep(0.3)
    json.dump(ids, open(IDS, "w"), indent=1, sort_keys=True)
    json.dump({"generated": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "complete": complete, "stocks": out}, open(OUT, "w"), separators=(",", ":"))
    print(f"::notice::UK annual-report figures for {len(out)} of {len(rows)} companies" + ("" if complete else " (time budget reached; the rest continues next run)"))
    if missing:
        print("::warning::No UK figures for: " + ", ".join(missing[:40]))


if __name__ == "__main__":
    main()
