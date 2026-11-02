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


def changes(prev: list[dict], cur: list[dict]) -> dict[str, list[dict]]:
    p = {h["cusip"]: h for h in prev}
    c = {h["cusip"]: h for h in cur}
    out = {"new": [], "added": [], "reduced": [], "sold": []}
    for k, h in c.items():
        if k not in p:
            out["new"].append(h)
        elif p[k]["shares"] > 0 and h["shares"] >= p[k]["shares"] * 1.1:
            out["added"].append({**h, "chg": h["shares"] / p[k]["shares"] - 1})
        elif p[k]["shares"] > 0 and h["shares"] <= p[k]["shares"] * 0.9:
            out["reduced"].append({**h, "chg": h["shares"] / p[k]["shares"] - 1})
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
    for k, f in enumerate(fs):
        start = entry(f["filed"])
        end = entry(fs[k + 1]["filed"]) if k + 1 < len(fs) else today
        if start is None or end is None or start >= end:
            continue
        tot = sum(h["value"] for h in f["holdings"])
        held = [(h["ticker"].upper(), h["value"]) for h in f["holdings"] if h.get("ticker") and h["ticker"].upper() in px]
        pv = sum(v for _, v in held)
        cover.append(pv / tot if tot else 0)
        legs = []
        for t, v in held:
            _, p0 = price_on_or_before(px[t], start)
            if p0 and pv > 0:
                legs.append((t, v / pv, p0))
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
            "coverage": round(sum(cover) / len(cover), 3) if cover else None}


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="site")
    ap.add_argument("--prices", default="data/prices")
    ap.add_argument("--base", default="https://bullpulse.co.uk/")
    ap.add_argument("--src", default=SRC)
    args = ap.parse_args()
    files = sorted(glob.glob(os.path.join(args.src, "*.json")))
    if not files:
        print("no 13F history yet")
        return
    px, ids, names = load_prices(args.prices)
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
    index = []
    for f in files:
        doc = json.load(open(f))
        fs = [x for x in doc.get("filings", []) if x.get("holdings")]
        if not fs:
            continue
        last = fs[-1]
        tot = sum(h["value"] for h in last["holdings"]) or 1
        prev = fs[-2]["holdings"] if len(fs) > 1 else []
        pmap = {h["cusip"]: h for h in prev}
        hold = []
        for h in last["holdings"]:
            t = (h.get("ticker") or "").upper()
            ch = "new" if prev and h["cusip"] not in pmap else ""
            if prev and h["cusip"] in pmap and pmap[h["cusip"]]["shares"] > 0:
                r = h["shares"] / pmap[h["cusip"]]["shares"] - 1
                ch = "added" if r >= 0.1 else "reduced" if r <= -0.1 else ""
            hold.append({"name": names.get(t, h["name"].title()), "filedName": h["name"], "ticker": t, "id": ids.get(t), "w": round(h["value"] / tot, 5),
                         "value": round(h["value"]), "shares": round(h["shares"]), "change": ch,
                         "chg": round(h["shares"] / pmap[h["cusip"]]["shares"] - 1, 3) if h["cusip"] in pmap and pmap[h["cusip"]]["shares"] > 0 else None})
        hold.sort(key=lambda h: -h["w"])
        covered = sum(h["w"] for h in hold if h["id"])
        hist = []
        for k in range(len(fs) - 1, 0, -1):
            c = changes(fs[k - 1]["holdings"], fs[k]["holdings"])
            tk = sum(h["value"] for h in fs[k]["holdings"]) or 1
            tp = sum(h["value"] for h in fs[k - 1]["holdings"]) or 1
            lab = lambda h, t=None: {"name": names.get((h.get("ticker") or "").upper(), h["name"].title()), "ticker": (h.get("ticker") or "").upper(),
                                     "id": ids.get((h.get("ticker") or "").upper()), "w": round(h["value"] / (t or tk), 4), "chg": h.get("chg")}
            hist.append({"period": fs[k]["period"], "filed": fs[k]["filed"], "acc": fs[k]["acc"],
                         "new": [lab(h) for h in c["new"]], "added": [lab(h) for h in c["added"]],
                         "reduced": [lab(h) for h in c["reduced"]], "sold": [lab(h, tp) for h in c["sold"]]})
            if len(hist) >= 12:
                break
        rec = copy_record(doc, px, bench)
        slug = doc["slug"]
        inv = {"slug": slug, "manager": doc["manager"], "firm": doc["firm"], "cik": doc["cik"], "about": doc.get("about", ""),
               "period": last["period"], "filed": last["filed"], "quarters": len(fs), "value": round(tot), "positions": len(hold),
               "covered": round(covered, 3), "holdings": hold, "history": hist, "record": rec,
               "name": doc["manager"]}
        json.dump(inv, open(os.path.join(out_dir, slug + ".json"), "w"), separators=(",", ":"))
        index.append({k: inv[k] for k in ("slug", "manager", "firm", "about", "period", "filed", "quarters", "value", "positions", "covered")} |
                     {"top": [{"name": h["name"], "ticker": h["ticker"], "id": h["id"], "w": h["w"]} for h in hold[:5]],
                      "record": {k: rec[k] for k in ("since", "total", "bench", "cagr", "benchCagr", "maxDD", "coverage")} if rec else None,
                      "latest": hist[0] and {k: len(hist[0][k]) for k in ("new", "added", "reduced", "sold")} if hist else None})
        items = []
        for hst in hist:
            parts = []
            for k, lab in (("new", "New"), ("added", "Added to"), ("reduced", "Reduced"), ("sold", "Sold out of")):
                if hst[k]:
                    parts.append(f"{lab}: " + ", ".join(x["name"] for x in hst[k][:8]) + ("…" if len(hst[k]) > 8 else ""))
            items.append({"filed": hst["filed"], "acc": hst["acc"], "title": f"{doc['manager']}: holdings at {hst['period']}",
                          "text": "; ".join(parts) or "No significant changes."})
        rss(os.path.join(args.site, "feeds", f"investor-{slug}.xml"), args.base, inv, items)
    index.sort(key=lambda x: -x["value"])
    json.dump({"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "investors": index}, open(os.path.join(out_dir, "index.json"), "w"), separators=(",", ":"))
    print(f"::notice::Investor pages: {len(index)}")


if __name__ == "__main__":
    main()
