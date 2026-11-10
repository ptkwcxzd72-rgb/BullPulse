"""Repair share counts filed in the wrong units before they reach the backtest.

XBRL filings sometimes state the share count in thousands or millions while tagging it as
units (or the reverse), and UK annual-report extracts mix units and hundreds. One such filing
made Edison International worth about $24,000 trillion in the 2020 panel, Gallagher, Carnival,
Garmin and Packaging Corp similar, and 3i, Admiral, Aviva and M&G a hundred times too large or
small. Because market value also divides free cash flow and dividends into yields, those
signals were wrong in the same months.

A unit error shows as a jump of a whole power of ten (100x or more) between filings, which no
index company's split explains (the largest split handled is 50-for-1). Each company's history is
anchored on its newest filing whose market value is plausible for an index member, and filings
that differ from the anchor's level by a clean power of ten are rescaled; filings still outside
the plausible range are dropped.
"""
from __future__ import annotations

import bisect
import csv
import math
import os

# plausible market values for any filing, in the price's currency (dollars; pounds for UK)
BOUNDS = {"US": (3e8, 8e12), "UK": (2e7, 6e11)}
# stricter ranges for the company's current index, used to choose the filing everything else is
# compared with (3i's two newest UK extracts were both 100x too small, so "the newest" won't do)
INDEX_BOUNDS = {"FTSE 100": (1.5e9, 6e11), "FTSE 250": (1e8, 1.5e10), "S&P 500": (2e9, 8e12)}


def load_closes(path: str) -> tuple[list[str], list[float]]:
    """Dates and closes from a price CSV (Date,...,Close,...), or empty lists."""
    if not os.path.exists(path):
        return [], []
    d, c = [], []
    for r in csv.DictReader(open(path, newline="")):
        try:
            v = float(r["Close"])
        except (KeyError, TypeError, ValueError):
            continue
        if v > 0:
            d.append(r["Date"])
            c.append(v)
    return d, c


def price_on(dates: list[str], closes: list[float], day: str) -> float | None:
    """The last close on or before day (or the first one, for filings before the history)."""
    if not dates:
        return None
    k = bisect.bisect_right(dates, day) - 1
    return closes[max(k, 0)]


def _power_of_ten(r: float) -> int:
    """j if r is within about 40% of 10**j for |j| >= 2, else 0."""
    if r <= 0:
        return 0
    lg = math.log10(r)
    j = round(lg)
    return j if abs(j) >= 2 and abs(lg - j) < 0.15 else 0


def clean_shares(rows: list[dict], price=None, market: str = "US", per_unit: float = 1.0, index: str = "") -> list[str]:
    """Repair rows in place (each with fin.shares and, optionally, split) in date order.

    price(date) -> close on today's split basis, or None; per_unit converts it to the bounds'
    currency (0.01 for pence). Rows that can't be repaired lose their share count (fin.shares is
    removed). Returns notes describing each change."""
    lo, hi = BOUNDS.get(market, BOUNDS["US"])
    notes: list[str] = []
    adj = lambda r: r["fin"]["shares"] * (r.get("split") or 1)

    def cap(r, shares=None):
        p = price(r["date"]) if price else None
        if p is None:
            return None
        return (shares if shares is not None else adj(r)) * p * per_unit

    have = [r for r in rows if r.get("fin", {}).get("shares")]
    if not have:
        return notes
    # the anchor: the newest filing with a market value plausible for the company's index, else
    # for any index member (the newest, without prices)
    anchor = None
    for blo, bhi in (INDEX_BOUNDS.get(index, (lo, hi)), (lo, hi)):
        for r in reversed(have):
            c = cap(r)
            if c is None or blo <= c <= bhi:
                anchor = r
                break
        if anchor is not None:
            break
    if anchor is None:
        anchor = have[-1]
    level = adj(anchor)
    # every filing out by the same factor (Games Workshop's three UK extracts were all 100x too
    # small): if the anchor isn't plausible for its index, take the smallest whole power of ten
    # (100x or more) that makes it so
    ilo, ihi = INDEX_BOUNDS.get(index, (lo, hi))
    c = cap(anchor)
    if c is not None and not ilo <= c <= ihi:
        fits = [j for j in range(-9, 10) if abs(j) >= 2 and ilo <= c / 10 ** j <= ihi]
        if fits:
            level /= 10 ** min(fits, key=abs)

    def rescale(r, ref):
        j = _power_of_ten(adj(r) / ref)
        if j:
            r["fin"]["shares"] = r["fin"]["shares"] / 10 ** j
            notes.append(f"{r.get('id', '')} {r['date']}: share count {'divided' if j > 0 else 'multiplied'} by {10 ** abs(j):,}")

    # Each filing is compared with its neighbour on the anchor's side, not with the anchor itself:
    # over fifteen years buybacks and issues move the count far enough (Assurant's fell from 118m
    # to 51m) that a filing in thousands is no longer a clean power of ten from today's level,
    # while neighbouring filings a quarter apart differ by a few per cent.
    a = have.index(anchor)
    rescale(anchor, level)
    for seq in (range(a - 1, -1, -1), range(a + 1, len(have))):
        ref = adj(anchor)
        for k in seq:
            rescale(have[k], ref)
            # a filing still far from its neighbour (unrepairable, dropped below) isn't followed
            if abs(math.log10(max(adj(have[k]), 1e-9) / ref)) < 1.3:
                ref = adj(have[k])
    for r in have:
        c = cap(r)
        if c is not None and not lo <= c <= hi:
            r["fin"].pop("shares", None)
            notes.append(f"{r.get('id', '')} {r['date']}: share count dropped (market value {c:.3g})")
    return notes
