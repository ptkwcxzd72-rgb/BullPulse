"""Investor pages for the website, from the 13F history (scripts/fetch_13f.py) and the prices.

For each investor: the latest holdings and weights, what changed each quarter, and the honest
record of a copy portfolio that buys each filing's holdings (weighted by reported value) on the
first close after the filing was published, and holds them until the next filing. Holdings without
a price here are left out, and the share of the portfolio covered is reported. Also an RSS feed
per investor, so people can follow new filings in a feed reader.

    python scripts/investors.py [--site site] [--prices data/prices]
Writes site/data/investors/index.json, site/data/investors/<slug>.json, site/feeds/investor-<slug>.xml.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import glob
import json
import math
import os
import re
from xml.sax.saxutils import escape

SRC = "data/history/13f"


def load_prices(prices: str) -> tuple[dict[str, tuple[list[str], list[float]]], dict[str, str], dict[str, str]]:
    """US ticker -> (dates, closes), ticker -> stock id, ticker -> company name."""
    out, ids, names = {}, {}, {}
    for f in glob.glob("universe/us*.csv"):
        for r in csv.DictReader(open(f, newline="")):
            p = os.path.join(prices, (r.get("provider_ticker") or "") + ".csv")
            if not os.path.exists(p):
                continue
            d, c = [], []
            for row in csv.DictReader(open(p, newline="")):
                try:
                    d.append(row["Date"][:10]); c.append(float(row["Close"]))
                except (KeyError, ValueError):
                    continue
            if d:
                t = r["ticker"].upper()
                out[t] = (d, c)
                ids[t] = "US-" + t.replace(".", "")
                names[t] = r["name"]
    return out, ids, names


def price_on_or_after(series, day: str):
    d, c = series
    k = bisect.bisect_left(d, day)
    return (d[k], c[k]) if k < len(d) else (None, None)


def price_on_or_before(series, day: str):
    d, c = series
    k = bisect.bisect_right(d, day) - 1
    return (d[k], c[k]) if k >= 0 else (None, None)


SPLITS = [2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 40, 50, 100]


def split_factor(prev: dict, cur: dict) -> float:
    """How many new shares each old share became, when a stock split (or reverse split) explains
    the change in share count better than buying or selling does: the reported price per share
    moved by about the same factor the other way. 1 when there was no split."""
    try:
        r = cur["shares"] / prev["shares"]
        move = (cur["value"] / cur["shares"]) / (prev["value"] / prev["shares"])
    except (KeyError, ZeroDivisionError, TypeError):
        return 1.0
    if r <= 0 or move <= 0 or abs(math.log(move)) < 0.45:
        return 1.0
    best, err = 1.0, abs(math.log(move))
    for k in SPLITS:
        for f in (k, 1 / k):
            e = abs(math.log(move * f))
            if e < err:
                best, err = f, e
    return best if err < 0.3 else 1.0


def share_change(prev: dict, cur: dict) -> float | None:
    """Change in shares held, allowing for splits."""
    if not prev.get("shares"):
        return None
    return cur["shares"] / (prev["shares"] * split_factor(prev, cur)) - 1


def changes(prev: list[dict], cur: list[dict]) -> dict[str, list[dict]]:
    p = {h["cusip"]: h for h in prev}
    c = {h["cusip"]: h for h in cur}
    out = {"new": [], "added": [], "reduced": [], "sold": []}
    for k, h in c.items():
        if k not in p:
            out["new"].append(h)
            continue
        ch = share_change(p[k], h)
        if ch is not None and ch >= 0.1:
            out["added"].append({**h, "chg": ch})
        elif ch is not None and ch <= -0.1:
            out["reduced"].append({**h, "chg": ch})
    for k, h in p.items():
        if k not in c:
            out["sold"].append(h)
    for v in out.values():
        v.sort(key=lambda h: -h["value"])
    return out


def copy_record(doc: dict, px: dict, bench) -> dict | None:
    """Follow each filing from the first close after it was published until the first close after
    the next one; month-end values. Holdings without a price here are left out (coverage reported)."""
    fs = [f for f in doc["filings"] if f.get("holdings")]
    if not fs or not bench:
        return None
    cal = bench[0]                       # trading days
    def entry(filed: str):               # first trading day after the filing date
        k = bisect.bisect_right(cal, filed)
        return cal[k] if k < len(cal) else None
    today = cal[-1]
    points, value, bvalue, cover = [], 1.0, 1.0, []
    contrib: dict[str, dict] = {}
    for k, f in enumerate(fs):
        start = entry(f["filed"])
        end = entry(fs[k + 1]["filed"]) if k + 1 < len(fs) else today
        if start is None or end is None or start >= end:
            continue
        tot = sum(h["value"] for h in f["holdings"])
        held = []                        # holdings with a price on the day we would buy them
        for h in f["holdings"]:
            t = (h.get("ticker") or "").upper()
            if t in px:
                d0, p0 = price_on_or_before(px[t], start)
                if p0 and d0 and (dt.date.fromisoformat(start) - dt.date.fromisoformat(d0)).days <= 10:
                    held.append((t, h["value"], p0))
        pv = sum(v for _, v, _ in held)
        cover.append(pv / tot if tot else 0)
        legs = [(t, v / pv, p0) for t, v, p0 in held] if pv > 0 else []
        if not legs:
            continue
        _, b0 = price_on_or_before(bench, start)
        if not points:
            points.append([start, 1.0, 1.0])
        stops = [d for d in month_ends(start, end)] + [end]
        v0, bv0 = value, bvalue
        for day in stops:
            v = 0.0
            for t, w, p0 in legs:
                _, p = price_on_or_before(px[t], day)
                v += w * (p / p0 if p else 1)
            value = v0 * v
            _, bp = price_on_or_before(bench, day)
            bvalue = bv0 * (bp / b0 if bp and b0 else 1)
            points.append([day, round(value, 5), round(bvalue, 5)])
        for t, w, p0 in legs:          # what each holding added over this filing's period
            _, p = price_on_or_before(px[t], end)
            r = (p / p0 - 1) if p else 0.0
            c = contrib.setdefault(t, {"pts": 0.0, "from": start, "to": end, "growth": 1.0, "wsum": 0.0, "n": 0})
            c["pts"] += v0 * w * r
            c["to"] = end
            c["growth"] *= 1 + r
            c["wsum"] += w
            c["n"] += 1
    if len(points) < 3:
        return None
    seen = {}
    for p in points:
        seen[p[0]] = p
    points = [seen[k] for k in sorted(seen)]
    yrs = (dt.date.fromisoformat(points[-1][0]) - dt.date.fromisoformat(points[0][0])).days / 365.25
    cagr = lambda g: round(g ** (1 / yrs) - 1, 4) if yrs > 0.5 and g > 0 else None
    peak, dd = 0, 0
    for p in points:
        peak = max(peak, p[1]); dd = min(dd, p[1] / peak - 1)
    return {"since": points[0][0], "points": points, "total": round(points[-1][1] - 1, 4), "bench": round(points[-1][2] - 1, 4),
            "cagr": cagr(points[-1][1]), "benchCagr": cagr(points[-1][2]), "maxDD": round(dd, 4),
            "coverage": round(sum(cover) / len(cover), 3) if cover else None, "contrib": contrib}


def month_ends(start: str, end: str) -> list[str]:
    """Calendar month-ends strictly between two dates."""
    out, cur = [], dt.date.fromisoformat(start)
    while True:
        me = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
        if me.isoformat() >= end:
            return out
        if me.isoformat() > start:
            out.append(me.isoformat())
        cur = me + dt.timedelta(days=1)


def rss(path: str, base: str, inv: dict, items: list[dict]) -> None:
    link = f"{base}investors.html?i={inv['slug']}"
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>',
           f"<title>{escape(inv['manager'])} ({escape(inv['firm'])}): 13F filings on BullPulse</title>", f"<link>{escape(link)}</link>",
           f'<atom:link href="{escape(base)}feeds/investor-{inv["slug"]}.xml" rel="self" type="application/rss+xml"/>',
           f"<description>New quarterly holdings filed with the SEC by {escape(inv['firm'])}. From public filings; not affiliated with or endorsed by the investor.</description>"]
    for it in items:
        pub = dt.datetime.fromisoformat(it["filed"]).strftime("%a, %d %b %Y 12:00:00 +0000")
        out.append(f"<item><title>{escape(it['title'])}</title><link>{escape(link)}</link><guid isPermaLink=\"false\">13f-{inv['slug']}-{it['acc']}</guid><pubDate>{pub}</pubDate><description>{escape(it['text'])}</description></item>")
    out.append("</channel></rss>")
    open(path, "w").write("\n".join(out) + "\n")


CLASS = re.compile(r"\s*\((?:class|series|cl)\s+[a-z]\)|\s+(?:class|cl)\s+[a-z]$", re.I)


def company(name: str) -> str:
    """A company's name without the share class, so GOOG and GOOGL count as one company."""
    return CLASS.sub("", name or "").strip()


QSTEP = {"03": 1, "06": 2, "09": 3, "12": 4}


def qnum(period: str) -> int:
    """Quarter number for a period end (YYYY-MM-DD), so gaps between filings can be seen."""
    return int(period[:4]) * 4 + QSTEP.get(period[5:7], (int(period[5:7]) + 2) // 3)


def positions(f: dict) -> dict[str, dict]:
    """One filing's holdings keyed by ticker (or CUSIP when there is no ticker), so share-class or
    CUSIP changes for the same listed company don't look like a sale and a purchase."""
    out: dict[str, dict] = {}
    for h in f.get("holdings", []):
        k = (h.get("ticker") or "").upper() or h["cusip"]
        a = out.setdefault(k, {"key": k, "ticker": (h.get("ticker") or "").upper(), "name": h["name"], "value": 0.0, "shares": 0.0, "cusip": h["cusip"]})
        a["value"] += h["value"]
        a["shares"] += h.get("shares") or 0
    return out


def turnover(prev: dict[str, dict], cur: dict[str, dict]) -> float | None:
    """Share of the portfolio the manager changed in a quarter: half the sum of the differences
    between this quarter's weights and last quarter's weights moved on by each holding's own price
    change. Money flowing into or out of the fund (which scales every holding alike) and stock
    splits do not count as trading."""
    if not prev or not cur:
        return None
    drift = {}
    for k, a in prev.items():
        b = cur.get(k)
        if b and a["shares"] > 0 and b["shares"] > 0:
            drift[k] = a["shares"] * split_factor(a, b) * b["value"] / b["shares"]
        else:
            drift[k] = a["value"]
    td, tc = sum(drift.values()), sum(h["value"] for h in cur.values())
    if td <= 0 or tc <= 0:
        return None
    return round(sum(abs(cur.get(k, {}).get("value", 0) / tc - drift.get(k, 0) / td) for k in set(drift) | set(cur)) / 2, 6)


def runs(fs: list[dict], maps: list[dict]) -> dict[str, list[tuple[int, int]]]:
    """For each holding, the runs of consecutive filings (by index) it was held in."""
    out: dict[str, list[tuple[int, int]]] = {}
    for k, m in enumerate(maps):
        for key in m:
            r = out.setdefault(key, [])
            if r and r[-1][1] == k - 1:
                r[-1] = (r[-1][0], k)
            else:
                r.append((k, k))
    return out


def yearly(points: list[list]) -> list[dict]:
    """Calendar-year returns of the copy portfolio and the S&P 500 from the month-end points."""
    out, prev = [], points[0]
    ends: dict[str, list] = {}
    for p in points:
        ends[p[0][:4]] = p
    for y in sorted(ends):
        e = ends[y]
        if e is prev:
            continue
        out.append({"year": int(y), "ret": round(e[1] / prev[1] - 1, 4), "bench": round(e[2] / prev[2] - 1, 4),
                    "partial": prev[0][:4] != str(int(y) - 1) or not prev[0][5:].startswith("12") or e is points[-1] and not e[0][5:].startswith("12")})
        prev = e
    return out


def window(points: list[list], years: float) -> dict | None:
    """Annualised return over the last N years, against the S&P 500."""
    end = dt.date.fromisoformat(points[-1][0])
    start = (end - dt.timedelta(days=round(365.25 * years))).isoformat()
    k = bisect.bisect_left([p[0] for p in points], start)
    if k >= len(points) - 1 or (dt.date.fromisoformat(points[k][0]) - dt.date.fromisoformat(start)).days > 45:
        return None
    a, b = points[k], points[-1]
    yrs = (end - dt.date.fromisoformat(a[0])).days / 365.25
    return {"years": years, "ret": round((b[1] / a[1]) ** (1 / yrs) - 1, 4), "bench": round((b[2] / a[2]) ** (1 / yrs) - 1, 4)}


UNCLASSIFIED = "Outside the S&P 500"
MIN_COVER = 0.2      # show a copy record only when at least this share of the portfolio has prices here
STYLE = [  # field, label, higher-is ... (for the sentence), True when a low value ranks high
    ("pe", "Price to earnings", True), ("roe", "Return on equity", False), ("revGrowth", "Revenue growth", False),
    ("divY", "Dividend yield", False), ("mcapBn", "Company size", False), ("mom", "Price momentum", False), ("score", "BullPulse score", False)]


def style(hold: list[dict], snap: dict[str, dict]) -> dict | None:
    """Where the current holdings sit among S&P 500 companies on each measure: the holding-weighted
    average percentile (50 = typical S&P 500 company) and the weighted median value."""
    us = [x for x in snap.values()]
    out, covered = {}, 0.0
    for f, lab, low in STYLE:
        vals = sorted(x[f] for x in us if isinstance(x.get(f), (int, float)) and (f != "pe" or x[f] > 0))
        if len(vals) < 50:
            continue
        pts, wsum = [], 0.0
        for h in hold:
            x = snap.get(h["ticker"])
            v = x.get(f) if x else None
            if not isinstance(v, (int, float)) or (f == "pe" and v <= 0):
                continue
            pct = bisect.bisect_left(vals, v) / len(vals)
            pts.append((v, pct, h["w"]))
            wsum += h["w"]
        if wsum < 0.25:
            continue
        avg = sum(p * w for _, p, w in pts) / wsum
        srt = sorted(pts)
        acc, med = 0.0, srt[-1][0]
        for v, _, w in srt:
            acc += w
            if acc >= wsum / 2:
                med = v
                break
        out[f] = {"label": lab, "pct": round(avg * 100), "median": round(med, 4), "market": round(vals[len(vals) // 2], 4), "low": low, "cover": round(wsum, 3)}
        covered = max(covered, wsum)
    return out or None


def describe(pat: dict, sty: dict | None, rec: dict | None) -> list[str]:
    """Plain-English summary of the pattern, from the numbers only."""
    out = []
    n, t10 = pat["positions"], pat["top10"]
    if n <= 12:
        out.append(f"Very concentrated: {n} holdings, the top ten are {round(t10 * 100)}% of the portfolio.")
    elif t10 >= 0.6:
        out.append(f"Concentrated: {n} holdings, but the top ten are {round(t10 * 100)}% of the portfolio.")
    elif n >= 300:
        out.append(f"Very diversified: {n} holdings; the top ten are only {round(t10 * 100)}%.")
    else:
        out.append(f"{n} holdings; the top ten are {round(t10 * 100)}% of the portfolio.")
    to = pat.get("turnoverYear")
    if to is not None:
        if to < 0.15:
            out.append(f"Trades very little: about {round(to * 100)}% of the portfolio changes in a year.")
        elif to < 0.4:
            out.append(f"Trades moderately: about {round(to * 100)}% of the portfolio changes in a year.")
        else:
            out.append(f"Trades a lot: about {round(min(to, 4) * 100)}% of the portfolio changes in a year.")
    hy = pat.get("holdYears")
    if hy:
        out.append(f"The average holding, by value, has been owned for {'at least ' if pat.get('holdCapped') else ''}{hy:.1f} years.")
    if sty:
        bits = []
        pe, roe, g, mc = sty.get("pe"), sty.get("roe"), sty.get("revGrowth"), sty.get("mcapBn")
        if pe:
            bits.append("cheaper" if pe["pct"] <= 40 else "more expensive" if pe["pct"] >= 60 else "similarly priced")
        if roe:
            bits.append("more profitable" if roe["pct"] >= 60 else "less profitable" if roe["pct"] <= 40 else "")
        if g:
            bits.append("faster-growing" if g["pct"] >= 60 else "slower-growing" if g["pct"] <= 40 else "")
        if mc:
            bits.append("much larger" if mc["pct"] >= 75 else "smaller" if mc["pct"] <= 40 else "")
        bits = [b for b in bits if b]
        if bits:
            out.append("Compared with the typical S&P 500 company, its holdings are " + (", ".join(bits[:-1]) + " and " + bits[-1] if len(bits) > 1 else bits[0]) + ".")
    sec = [x for x in pat.get("sectors") or [] if x["sector"] != UNCLASSIFIED]
    if sec and sec[0]["w"] >= 0.3:
        out.append(f"Big sector bet: {round(sec[0]['w'] * 100)}% in {sec[0]['sector']}.")
    if rec and rec.get("years"):
        ys = [y for y in rec["years"] if not y["partial"]]
        if len(ys) >= 4:
            beat = sum(1 for y in ys if y["ret"] > y["bench"])
            out.append(f"Copying each filing beat the S&P 500 in {beat} of {len(ys)} full years.")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="site")
    ap.add_argument("--prices", default="data/prices")
    ap.add_argument("--base", default="https://bullpulse.co.uk/")
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--profiles", default="data/investor_profiles.json")
    args = ap.parse_args()
    files = sorted(glob.glob(os.path.join(args.src, "*.json")))
    if not files:
        print("no 13F history yet")
        return
    px, ids, names = load_prices(args.prices)
    sector_of = {}
    for f in glob.glob("universe/us*.csv"):
        for r in csv.DictReader(open(f, newline="")):
            sector_of[r["ticker"].upper()] = r.get("sector") or ""
    snap = {}
    try:
        for x in json.load(open(os.path.join(args.site, "data", "snapshot.json")))["stocks"]:
            if x.get("ex") not in ("LSE",) and x.get("id", "").startswith("US-"):
                snap[x["t"].upper()] = x
    except (OSError, ValueError, KeyError):
        pass
    profiles = json.load(open(args.profiles)) if os.path.exists(args.profiles) else {}
    bench = None
    bp = os.path.join(args.prices, "bench-sp500.csv")
    if os.path.exists(bp):
        d, c = [], []
        for row in csv.DictReader(open(bp, newline="")):
            d.append(row["Date"][:10]); c.append(float(row["Close"]))
        bench = (d, c)
    out_dir = os.path.join(args.site, "data", "investors")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(args.site, "feeds"), exist_ok=True)
    nm = lambda t, fallback: names.get(t, fallback.title())
    index, latest_maps, owners = [], {}, {}
    for f in files:
        doc = json.load(open(f))
        fs = [x for x in doc.get("filings", []) if x.get("holdings")]
        if not fs:
            continue
        slug = doc["slug"]
        maps = [positions(x) for x in fs]
        last, cur = fs[-1], maps[-1]
        tot = sum(h["value"] for h in cur.values()) or 1
        prev = maps[-2] if len(maps) > 1 else {}
        rn = runs(fs, maps)
        hold = []
        for k, h in cur.items():
            t = h["ticker"]
            p = prev.get(k)
            chg = share_change(p, h) if p else None
            ch = "new" if prev and not p else ("added" if chg is not None and chg >= 0.1 else "reduced" if chg is not None and chg <= -0.1 else "")
            since_idx = rn[k][-1][0]
            hold.append({"name": nm(t, h["name"]), "filedName": h["name"], "ticker": t, "id": ids.get(t), "w": round(h["value"] / tot, 5),
                         "value": round(h["value"]), "shares": round(h["shares"]), "change": ch, "chg": round(chg, 3) if chg is not None else None,
                         "since": fs[since_idx]["period"], "sinceStart": since_idx == 0, "sector": sector_of.get(t) or "", "_k": k})
        hold.sort(key=lambda h: -h["w"])
        keys = [h.pop("_k") for h in hold]
        covered = sum(h["w"] for h in hold if h["id"])
        # quarter by quarter: what changed (the 20 most recent quarters; long lists trimmed)
        hist = []
        for k in range(len(fs) - 1, 0, -1):
            c = changes(fs[k - 1]["holdings"], fs[k]["holdings"])
            tk = sum(h["value"] for h in fs[k]["holdings"]) or 1
            tp = sum(h["value"] for h in fs[k - 1]["holdings"]) or 1
            lab = lambda h, t=None: {"name": nm((h.get("ticker") or "").upper(), h["name"]), "ticker": (h.get("ticker") or "").upper(),
                                     "id": ids.get((h.get("ticker") or "").upper()), "w": round(h["value"] / (t or tk), 4),
                                     "chg": round(h["chg"], 3) if h.get("chg") is not None else None}
            hist.append({"period": fs[k]["period"], "filed": fs[k]["filed"], "acc": fs[k]["acc"],
                         "counts": {kk: len(c[kk]) for kk in ("new", "added", "reduced", "sold")},
                         "turnover": (lambda v: round(v, 4) if v is not None else None)(turnover(maps[k - 1], maps[k])),
                         "new": [lab(h) for h in c["new"][:25]], "added": [lab(h) for h in c["added"][:25]],
                         "reduced": [lab(h) for h in c["reduced"][:25]], "sold": [lab(h, tp) for h in c["sold"][:25]]})
            if len(hist) >= 20:
                break
        # pattern over time
        conc = []
        for x, m in zip(fs, maps):
            tv = sum(h["value"] for h in m.values()) or 1
            ws = sorted((h["value"] / tv for h in m.values()), reverse=True)
            conc.append({"period": x["period"], "n": len(m), "top10": round(sum(ws[:10]), 4), "top1": round(ws[0], 4) if ws else 0, "value": round(tv)})
        tos = [turnover(maps[k - 1], maps[k]) for k in range(1, len(maps)) if qnum(fs[k]["period"]) - qnum(fs[k - 1]["period"]) == 1]
        tos = [v for v in tos if v is not None]
        to_year = round(sum(tos[-4:]), 4) if len(tos) >= 4 else None
        to_avg = round(sum(tos) / len(tos) * 4, 4) if tos else None
        # how long today's holdings have been held (value-weighted), and how long past positions lasted
        def qspan(a: int, b: int) -> float:
            return (qnum(fs[b]["period"]) - qnum(fs[a]["period"]) + 1) / 4
        hold_years = sum(h["w"] * qspan(rn[k][-1][0], len(fs) - 1) for k, h in zip(keys, hold))
        capped = any(h["sinceStart"] and h["w"] >= 0.05 for h in hold)
        closed = [qspan(a, b) for k, rr in rn.items() for a, b in rr if b < len(fs) - 1]
        closed.sort()
        longest = sorted(({"name": h["name"], "ticker": h["ticker"], "id": h["id"], "since": h["since"], "sinceStart": h["sinceStart"], "w": h["w"],
                           "years": round(qspan(rn[k][-1][0], len(fs) - 1), 1)} for k, h in zip(keys, hold)), key=lambda x: (-x["years"], -x["w"]))[:8]
        # biggest bets by year (last filing of each year)
        byyear = {}
        for x, m in zip(fs, maps):
            byyear[x["period"][:4]] = (x, m)
        bets = []
        for y in sorted(byyear):
            x, m = byyear[y]
            tv = sum(h["value"] for h in m.values()) or 1
            top = sorted(m.values(), key=lambda h: -h["value"])[:3]
            bets.append({"year": int(y), "period": x["period"], "top": [{"name": nm(h["ticker"], h["name"]), "ticker": h["ticker"], "id": ids.get(h["ticker"]), "w": round(h["value"] / tv, 4)} for h in top]})
        # sectors now and earlier (holdings we can classify)
        def sectors(m: dict) -> list[dict]:
            tv = sum(h["value"] for h in m.values()) or 1
            agg: dict[str, float] = {}
            for h in m.values():
                sname = sector_of.get(h["ticker"]) or UNCLASSIFIED
                agg[sname] = agg.get(sname, 0) + h["value"] / tv
            return [{"sector": k, "w": round(v, 4)} for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]
        sec_now = sectors(cur)
        five = next((m for x, m in zip(fs, maps) if qnum(x["period"]) >= qnum(last["period"]) - 20), maps[0])
        five_period = fs[maps.index(five)]["period"]
        rec = copy_record(doc, px, bench)
        rec_note = None
        if rec and (rec["coverage"] or 0) < MIN_COVER:   # too little of the portfolio priced to be fair
            rec_note = {"coverage": rec["coverage"]}
            rec = None
        calls = None
        if rec:
            cb = rec.pop("contrib", {})
            merged: dict[str, dict] = {}
            for t, v in cb.items():
                c = company(names.get(t, t))
                m = merged.get(c)
                row = {"name": c, "ticker": t, "id": ids.get(t), "pts": v["pts"] * 100, "ret": round(v["growth"] - 1, 3),
                       "from": v["from"], "to": v["to"], "avgW": round(v["wsum"] / v["n"], 4)}
                if m is None:
                    merged[c] = row
                else:
                    m["pts"] += row["pts"]
                    m["from"], m["to"] = min(m["from"], row["from"]), max(m["to"], row["to"])
                    if row["avgW"] > m["avgW"]:
                        m.update({k: row[k] for k in ("ticker", "id", "ret", "avgW")})
            rows = list(merged.values())
            for r in rows:
                r["pts"] = round(r["pts"], 1)
            rows.sort(key=lambda r: -r["pts"])
            calls = {"best": [r for r in rows if r["pts"] > 0][:6], "worst": [r for r in reversed(rows) if r["pts"] < 0][:6]}
            rec["years"] = yearly(rec["points"])
            rec["windows"] = [w for w in (window(rec["points"], y) for y in (1, 3, 5, 10)) if w]
        sty = style([h for h in hold if h["ticker"]], snap) if snap else None
        pat = {"positions": len(cur), "top10": conc[-1]["top10"], "top1": conc[-1]["top1"], "turnoverYear": to_year, "turnoverAvg": to_avg,
               "holdYears": round(hold_years, 1), "holdCapped": capped, "closedMedianYears": round(closed[len(closed) // 2], 1) if closed else None,
               "sectors": sec_now, "sectorsThen": sectors(five), "sectorsThenPeriod": five_period, "longest": longest, "bets": bets,
               "concentration": conc, "turnover": [{"period": fs[k]["period"], "v": round(v, 4)} for k, v in ((k, turnover(maps[k - 1], maps[k])) for k in range(1, len(maps))) if v is not None]}
        prof = profiles.get(slug, {})
        inv = {"slug": slug, "manager": doc["manager"], "firm": doc["firm"], "cik": doc["cik"], "about": doc.get("about", ""),
               "period": last["period"], "filed": last["filed"], "first": fs[0]["period"], "quarters": len(fs), "value": round(tot), "positions": len(hold),
               "covered": round(covered, 3), "holdings": hold, "history": hist, "record": rec, "recordNote": rec_note, "calls": calls, "pattern": pat, "style": sty,
               "summary": describe(pat, sty, rec), "profile": prof, "name": doc["manager"]}
        byco: dict[str, dict] = {}
        for h in hold:
            if not h["ticker"]:
                continue
            c = byco.setdefault(company(h["name"]), {"name": company(h["name"]), "ticker": h["ticker"], "id": h["id"], "w": 0.0})
            c["w"] += h["w"]
            if not c["id"] and h["id"]:
                c["id"], c["ticker"] = h["id"], h["ticker"]
        latest_maps[slug] = (inv, byco, hist[0] if hist else None)
        for h in hold:
            if h["id"]:
                owners.setdefault(h["id"], []).append([slug, h["w"], h["change"], last["period"]])
        index.append({k: inv[k] for k in ("slug", "manager", "firm", "about", "period", "filed", "first", "quarters", "value", "positions", "covered")} |
                     {"tags": prof.get("tags", []), "based": prof.get("based"), "note": prof.get("note", ""),
                      "top": [{"name": h["name"], "ticker": h["ticker"], "id": h["id"], "w": h["w"]} for h in hold[:5]],
                      "record": {k: rec[k] for k in ("since", "total", "bench", "cagr", "benchCagr", "maxDD", "coverage")} if rec else None,
                      "spark": [p[1] for p in rec["points"][::max(1, len(rec["points"]) // 40)]] + [rec["points"][-1][1]] if rec else None,
                      "turnover": to_year, "holdYears": pat["holdYears"], "top10": pat["top10"], "recordNote": rec_note,
                      "latest": hist[0]["counts"] if hist else None})
        items = []
        for hst in hist:
            parts = []
            for k, lab in (("new", "New"), ("added", "Added to"), ("reduced", "Reduced"), ("sold", "Sold out of")):
                if hst[k]:
                    parts.append(f"{lab}: " + ", ".join(x["name"] for x in hst[k][:8]) + ("…" if hst["counts"][k] > 8 else ""))
            items.append({"filed": hst["filed"], "acc": hst["acc"], "title": f"{doc['manager']}: holdings at {hst['period']}",
                          "text": "; ".join(parts) or "No significant changes."})
        rss(os.path.join(args.site, "feeds", f"investor-{slug}.xml"), args.base, inv, items)
        inv_path = os.path.join(out_dir, slug + ".json")
        json.dump(inv, open(inv_path, "w"), separators=(",", ":"))
    # how alike the portfolios are (overlap by weight), and what they agree on
    newest = max(qnum(v[0]["period"]) for v in latest_maps.values()) if latest_maps else 0
    for slug, (inv, hm, _) in latest_maps.items():
        sims = []
        for o, (inv2, hm2, _) in latest_maps.items():
            if o == slug:
                continue
            ov = sum(min(h["w"], hm2[t]["w"]) for t, h in hm.items() if t in hm2)
            if ov >= 0.05:
                sims.append({"slug": o, "manager": inv2["manager"], "overlap": round(ov, 3),
                             "shared": [hm[t]["ticker"] for t, _ in sorted(((t, min(h["w"], hm2[t]["w"])) for t, h in hm.items() if t in hm2), key=lambda kv: -kv[1])[:4]]})
        sims.sort(key=lambda x: -x["overlap"])
        inv["similar"] = sims[:5]
        json.dump(inv, open(os.path.join(out_dir, slug + ".json"), "w"), separators=(",", ":"))
    recent = {s: v for s, v in latest_maps.items() if qnum(v[0]["period"]) >= newest - 1}
    held: dict[str, dict] = {}
    for slug, (inv, hm, h0) in recent.items():
        for t, h in hm.items():
            a = held.setdefault(t, {"ticker": h["ticker"], "name": h["name"], "id": h["id"], "holders": [], "wsum": 0.0, "buyers": [], "sellers": []})
            a["holders"].append(slug)
            a["wsum"] += h["w"]
        if h0 and h0["period"] == inv["period"]:
            for kind, lst in (("buyers", h0["new"] + h0["added"]), ("sellers", h0["sold"] + h0["reduced"])):
                for h in lst:
                    if h["ticker"]:
                        c = company(h["name"])
                        a = held.setdefault(c, {"ticker": h["ticker"], "name": c, "id": h["id"], "holders": [], "wsum": 0.0, "buyers": [], "sellers": []})
                        if slug not in a[kind]:
                            a[kind].append(slug)
    rows = list(held.values())
    for r in rows:
        r["avgW"] = round(r.pop("wsum") / len(r["holders"]), 4) if r["holders"] else 0
    consensus = {
        "owned": [r for r in sorted(rows, key=lambda r: (-len(r["holders"]), -r["avgW"])) if len(r["holders"]) >= 3][:15],
        "bought": [r for r in sorted(rows, key=lambda r: (-len(r["buyers"]), -len(r["holders"]))) if len(r["buyers"]) >= 2][:12],
        "sold": [r for r in sorted(rows, key=lambda r: (-len(r["sellers"]), -len(r["holders"]))) if len(r["sellers"]) >= 2][:12],
        "investors": len(recent)}
    index.sort(key=lambda x: -x["value"])
    json.dump({"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "investors": index, "consensus": consensus},
              open(os.path.join(out_dir, "index.json"), "w"), separators=(",", ":"))
    json.dump(owners, open(os.path.join(out_dir, "owners.json"), "w"), separators=(",", ":"))
    print(f"::notice::Investor pages: {len(index)}")


if __name__ == "__main__":
    main()
