"""Turn SEC XBRL company facts into the financial figures behind the BullPulse Fundamentals
Profile and DCF. Pure functions, no network; used by fetch_fundamentals.py.

Flows (revenue, earnings, cash flow) are reported for different durations: full years,
quarters and year-to-date periods. ttm() rebuilds the trailing twelve months from whatever
the company filed: the latest fiscal year, or fiscal year + current year-to-date − prior
year-to-date. Balance-sheet items are point-in-time ("instant") facts; latest() takes the newest.
"""
from __future__ import annotations

import datetime as dt

REVENUE = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
           "RevenueFromContractWithCustomerIncludingAssessedTax", "RevenuesNetOfInterestExpense", "SalesRevenueGoodsNet"]
NET_INCOME = ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]
OP_INCOME = ["OperatingIncomeLoss"]
EPS = ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "EarningsPerShareBasic"]
OCF = ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]
CAPEX = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]
INTEREST = ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"]
DIV_PAID = ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"]
DPS = ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"]
EQUITY = ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
CASH = ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]
ASSETS_CUR = ["AssetsCurrent"]
LIAB_CUR = ["LiabilitiesCurrent"]
DEBT_LT = ["LongTermDebtNoncurrent", "LongTermDebt"]
DEBT_ST = ["LongTermDebtCurrent", "DebtCurrent", "ShortTermBorrowings"]
SHARES = ["WeightedAverageNumberOfDilutedSharesOutstanding"]
SBC = ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"]
TAX_RATE = 0.21   # US federal rate, used to put interest back on an after-tax basis


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _rows(facts: dict, concept: str, unit: str, taxonomy: str = "us-gaap") -> list[dict]:
    return facts.get("facts", {}).get(taxonomy, {}).get(concept, {}).get("units", {}).get(unit, [])


class Periods(dict):
    """(start, end) -> value, plus .annual_keys: the periods reported as fiscal years in a 10-K
    (some companies, such as Amazon, also file trailing-twelve-month columns in 10-Qs)."""
    annual_keys: set


def durations(facts: dict, concepts: list[str], unit: str = "USD") -> Periods:
    """(start, end) -> value. First concept in priority order wins; latest filing wins within one."""
    out = Periods()
    out.annual_keys = set()
    for c in concepts:
        best: dict[tuple[str, str], tuple[str, float]] = {}
        for r in _rows(facts, c, unit):
            if "start" in r and "end" in r and r.get("val") is not None:
                k = (r["start"], r["end"])
                if k not in best or r.get("filed", "") > best[k][0]:
                    best[k] = (r.get("filed", ""), float(r["val"]))
                if str(r.get("form", "")).startswith(("10-K", "20-F", "40-F")):
                    out.annual_keys.add(k)
        for k, (_, v) in best.items():
            out.setdefault(k, v)
    return out


def instants(facts: dict, concepts: list[str], unit: str = "USD", taxonomy: str = "us-gaap") -> dict[str, float]:
    """end date -> value for point-in-time facts."""
    out: dict[str, float] = {}
    for c in concepts:
        best: dict[str, tuple[str, float]] = {}
        for r in _rows(facts, c, unit, taxonomy):
            if "start" not in r and r.get("val") is not None:
                if r["end"] not in best or r.get("filed", "") > best[r["end"]][0]:
                    best[r["end"]] = (r.get("filed", ""), float(r["val"]))
        for k, (_, v) in best.items():
            out.setdefault(k, v)
    return out


def latest(series: dict[str, float]) -> tuple[str, float] | None:
    if not series:
        return None
    e = max(series)
    return e, series[e]


def annual(p: dict[tuple[str, str], float]) -> dict[str, float]:
    """fiscal-year end date -> value for ~12-month durations reported in annual reports
    (any ~12-month duration when the filing form isn't known)."""
    keys = getattr(p, "annual_keys", None)
    return {e: v for (s, e), v in p.items() if 350 <= (_d(e) - _d(s)).days <= 380 and (not keys or (s, e) in keys)}


def ttm(p: dict[tuple[str, str], float]) -> tuple[str, float] | None:
    """Trailing twelve months ending at the latest reported period."""
    if not p:
        return None
    end = max(e for _, e in p)
    for (s, e), v in p.items():   # a full year ends on the latest date
        if e == end and 350 <= (_d(e) - _d(s)).days <= 380:
            return end, v
    years = annual(p)
    # year-to-date (or quarter) ending at `end`, the same period a year earlier, and the fiscal year between
    for (s, e), cur in sorted(p.items(), key=lambda kv: -(_d(kv[0][1]) - _d(kv[0][0])).days):
        if e != end:
            continue
        length = (_d(e) - _d(s)).days
        if length >= 350:
            continue
        prior = [v for (s2, e2), v in p.items()
                 if abs((_d(e2) - (_d(e) - dt.timedelta(days=365))).days) <= 20 and abs((_d(e2) - _d(s2)).days - length) <= 15]
        fy = [v for fe, v in years.items() if _d(e) - dt.timedelta(days=365) < _d(fe) < _d(e)]
        if prior and fy:
            return end, fy[-1] + cur - prior[0]
    if years:   # fall back to the latest full year
        fe = max(years)
        return fe, years[fe]
    return None


def cagr(series: dict[str, float], years: int) -> float | None:
    """Compound annual growth between the latest fiscal year and `years` earlier (both positive)."""
    if not series:
        return None
    e = max(series)
    target = _d(e) - dt.timedelta(days=round(365.25 * years))
    old = [v for k, v in series.items() if abs((_d(k) - target).days) <= 30]
    if not old or old[0] <= 0 or series[e] <= 0:
        return None
    return (series[e] / old[0]) ** (1 / years) - 1


def back(series: dict[str, float], years: int) -> float | None:
    """Value about `years` fiscal years before the latest."""
    if not series:
        return None
    target = _d(max(series)) - dt.timedelta(days=round(365.25 * years))
    old = [v for k, v in series.items() if abs((_d(k) - target).days) <= 30]
    return old[0] if old else None


def quarters(p: dict[tuple[str, str], float]) -> dict[str, float]:
    """quarter end -> value for single quarters (about three months). Fourth quarters, which
    companies usually report only inside the full year, are derived as the year minus the
    nine months to the third quarter."""
    q = {e: v for (s, e), v in p.items() if 80 <= (_d(e) - _d(s)).days <= 100}
    for (s, e), fy in p.items():
        if not 350 <= (_d(e) - _d(s)).days <= 380 or e in q:
            continue
        nine = [v for (s2, e2), v in p.items() if s2 == s and 260 <= (_d(e2) - _d(s2)).days <= 285]
        if nine:
            q[e] = fy - nine[0]
    return q


def eps_surprise(eps: dict[tuple[str, str], float]) -> dict:
    """Latest quarter's earnings per share against the same quarter a year earlier (a seasonal
    random walk: the simplest forecast that needs no analysts), and the spread of that change
    over the previous eight quarters, for a standardised surprise."""
    q = quarters(eps)
    ends = sorted(q)
    def year_before(e):
        c = [e2 for e2 in ends if abs((_d(e2) - (_d(e) - dt.timedelta(days=365))).days) <= 20]
        return c[0] if c else None
    diffs = []
    for e in ends:
        b = year_before(e)
        if b is not None:
            diffs.append((e, q[e] - q[b]))
    if not diffs:
        return {}
    out = {"eps_q_end": diffs[-1][0], "eps_q_diff": round(diffs[-1][1], 4)}
    prior = [d for _, d in diffs[-9:-1]]
    if len(prior) >= 4:
        m = sum(prior) / len(prior)
        sd = (sum((x - m) ** 2 for x in prior) / (len(prior) - 1)) ** 0.5
        if sd > 0:
            out["eps_q_sd"] = round(sd, 4)
    return out


def financials(facts: dict) -> dict:
    """The raw figures the screener needs. Missing items are simply left out."""
    f: dict = {}
    def put(name, val, nd=4):
        if val is not None:
            f[name] = round(val, nd) if isinstance(val, float) else val

    rev, ni, opi = durations(facts, REVENUE), durations(facts, NET_INCOME), durations(facts, OP_INCOME)
    ocf, capex, intr = durations(facts, OCF), durations(facts, CAPEX), durations(facts, INTEREST)
    sbc = durations(facts, SBC)
    divp, dps, eps = durations(facts, DIV_PAID), durations(facts, DPS, "USD/shares"), durations(facts, EPS, "USD/shares")
    for name, p in (("revenue", rev), ("net_income", ni), ("op_income", opi), ("ocf", ocf), ("capex", capex),
                    ("interest", intr), ("dividends_paid", divp), ("sbc", sbc)):
        t = ttm(p)
        if t:
            put(name + "_ttm", t[1], 0)
            if name == "revenue":
                put("ttm_end", t[0])
    t = ttm(eps);  put("eps_ttm", t[1] if t else None)
    f.update(eps_surprise(eps))
    t = ttm(dps);  put("dps_ttm", t[1] if t else None)

    rev_y, ni_y, eps_y, ocf_y, capex_y, dps_y = (annual(x) for x in (rev, ni, eps, ocf, capex, dps))
    sbc_y, int_y = annual(sbc), annual(intr)
    put("rev_cagr3", cagr(rev_y, 3))
    put("rev_cagr5", cagr(rev_y, 5))
    put("eps_5y_ago", back(eps_y, 5) if back(eps_y, 5) is not None else back(eps_y, 3))
    put("eps_fy", latest(eps_y)[1] if eps_y else None)
    put("dps_3y_ago", back(dps_y, 3))
    put("dps_fy", latest(dps_y)[1] if dps_y else None)
    last3 = [ni_y[k] for k in sorted(ni_y)[-3:]]
    if len(last3) == 3:
        f["profitable_3y"] = all(v > 0 for v in last3)
    # margins now and a year earlier (fiscal years)
    yrs = sorted(set(rev_y) & set(ni_y))
    if len(yrs) >= 2 and rev_y[yrs[-1]] and rev_y[yrs[-2]]:
        put("net_margin_fy", ni_y[yrs[-1]] / rev_y[yrs[-1]])
        put("net_margin_prev_fy", ni_y[yrs[-2]] / rev_y[yrs[-2]])
    # free cash flow history (fiscal years) for the DCF base
    both = sorted(set(ocf_y) & set(capex_y))   # no capital spending reported: no free-cash-flow figures
    fcf = [ocf_y[k] - capex_y.get(k, 0) for k in both[-3:]]
    if fcf:
        put("fcf_avg3", sum(fcf) / len(fcf), 0)
        put("fcf_years", len(fcf))
        # cash flow to the whole business (before interest), after share-based pay, for the DCF:
        # operating cash flow - capex - share-based compensation + after-tax interest
        fcff = [ocf_y[k] - capex_y.get(k, 0) - sbc_y.get(k, 0) + int_y.get(k, 0) * (1 - TAX_RATE) for k in both[-3:]]
        put("fcff_avg3", sum(fcff) / len(fcff), 0)
        sb = [sbc_y[k] for k in both[-3:] if k in sbc_y]
        if sb:
            put("sbc_avg3", sum(sb) / len(sb), 0)

    for name, concepts in (("equity", EQUITY), ("cash", CASH), ("assets_cur", ASSETS_CUR), ("liab_cur", LIAB_CUR)):
        x = latest(instants(facts, concepts))
        put(name, x[1] if x else None, 0)
        if name == "equity" and x:
            put("balance_end", x[0])
    lt, st = latest(instants(facts, DEBT_LT)), latest(instants(facts, DEBT_ST))
    if lt or st:
        put("debt", (lt[1] if lt else 0) + (st[1] if st else 0), 0)
    sh = latest(instants(facts, ["EntityCommonStockSharesOutstanding"], "shares", "dei"))
    if not sh:   # weighted-average diluted shares of the latest period (not summed: shares are not a flow)
        p = durations(facts, SHARES, "shares")
        if p:
            k = max(p, key=lambda se: (se[1], se[0]))
            sh = (k[1], p[k])
    if not sh and ni_y and eps_y:   # last resort: net income / earnings per share of the latest year
        y = max(set(ni_y) & set(eps_y), default=None)
        if y and eps_y[y] and ni_y[y] / eps_y[y] > 0:
            sh = (y, ni_y[y] / eps_y[y])
    put("shares", sh[1] if sh else None, 0)
    return f
