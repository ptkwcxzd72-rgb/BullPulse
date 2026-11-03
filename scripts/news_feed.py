"""The website's news feed: the last three weeks of scored headlines, one file per day.

Reads the headlines gathered and scored each evening (data/news/articles.jsonl) and writes
site/data/news/index.json (the days, with each day's mood and most-mentioned companies) and
site/data/news/<date>.json (that day's headlines). The same story reported for several companies
appears once, tagged with all of them. Headlines link to the original article; no article text
is copied.

    python scripts/news_feed.py [--days 21]
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re

ARTICLES = "data/news/articles.jsonl"
SNAP = "site/data/snapshot.json"


def key(headline: str) -> str:
    return re.sub(r"[^a-z0-9]", "", headline.lower())[:120]


def stock_ids(snap_path: str) -> tuple[dict, dict]:
    """(market, ticker) -> stock id, and id -> short facts for the page."""
    ids, facts = {}, {}
    try:
        for s in json.load(open(snap_path))["stocks"]:
            m = "UK" if s.get("ex") == "LSE" else "US"
            ids[(m, s["t"].upper())] = s["id"]
            facts[s["id"]] = {"n": s["name"], "t": s["t"], "m": m, "sc": s.get("score"), "d": s.get("chg1d"), "sec": s.get("sector")}
    except (OSError, ValueError, KeyError):
        pass
    return ids, facts


def build(rows: list[dict], ids: dict) -> dict[str, list[dict]]:
    """Headlines grouped by day, duplicates merged, most relevant first."""
    days: dict[str, dict[str, dict]] = {}
    for r in rows:
        if not r.get("headline") or r.get("score") is None:
            continue
        d = days.setdefault(r["date"], {})
        k = key(r["headline"])
        sid = ids.get((r.get("market", "US"), (r.get("ticker") or "").upper()))
        it = d.get(k)
        if it is None:
            it = d[k] = {"h": r["headline"].strip(), "s": r.get("source") or "", "u": r.get("url") or "", "m": r.get("market", "US"),
                         "tone": round(r["score"], 2), "lab": r.get("label") or "", "ev": r.get("event") or "Other",
                         "rel": r.get("rel") or 0, "about": [], "also": []}
        if sid:
            (it["about"] if (r.get("rel") or 0) >= 0.5 else it["also"]).append(sid)
        it["rel"] = max(it["rel"], r.get("rel") or 0)
        if it["ev"] == "Other" and r.get("event") and r["event"] != "Other":
            it["ev"] = r["event"]
    out = {}
    for d, items in days.items():
        lst = []
        for it in items.values():
            it["about"] = list(dict.fromkeys(it["about"]))
            it["also"] = [x for x in dict.fromkeys(it["also"]) if x not in it["about"]][:6]
            lst.append(it)
        # most useful first: about a named company, a notable event, then a clear tone
        lst.sort(key=lambda it: (bool(it["about"]), it["ev"] != "Other", it["rel"], abs(it["tone"])), reverse=True)
        # spread companies out: a company's second story waits until other companies have had one
        seen: dict[str, int] = {}
        ranked = []
        for pos, it in enumerate(lst):
            lead = (it["about"] or ["_"])[0]
            n = seen.get(lead, 0)
            seen[lead] = n + 1
            ranked.append((n if lead != "_" else 0, pos, it))
        lst = [it for _, _, it in sorted(ranked, key=lambda x: (min(x[0], 3), x[1]))]
        for it in lst:
            del it["rel"]
        out[d] = lst
    return out


def summary(date: str, items: list[dict], facts: dict) -> dict:
    pos = sum(1 for it in items if it["lab"] == "Positive")
    neg = sum(1 for it in items if it["lab"] == "Negative")
    count: dict[str, list] = {}
    for it in items:
        for sid in it["about"]:
            c = count.setdefault(sid, [0, 0.0])
            c[0] += 1
            c[1] += it["tone"]
    top = sorted(count.items(), key=lambda kv: -kv[1][0])[:8]
    ev: dict[str, int] = {}
    for it in items:
        ev[it["ev"]] = ev.get(it["ev"], 0) + 1
    return {"date": date, "n": len(items), "pos": pos, "neg": neg, "uk": sum(1 for it in items if it["m"] == "UK"),
            "top": [{"id": sid, "n": c[0], "tone": round(c[1] / c[0], 2)} for sid, c in top], "events": ev}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--site", default="site")
    args = ap.parse_args()
    if not os.path.exists(ARTICLES):
        print("no news yet")
        return
    rows = [json.loads(l) for l in open(ARTICLES) if l.strip()]
    if not rows:
        return
    last = max(r["date"] for r in rows)
    since = (dt.date.fromisoformat(last) - dt.timedelta(days=args.days - 1)).isoformat()
    ids, facts = stock_ids(os.path.join(args.site, "data", "snapshot.json"))
    days = build([r for r in rows if r["date"] >= since], ids)
    out = os.path.join(args.site, "data", "news")
    os.makedirs(out, exist_ok=True)
    for old in glob.glob(os.path.join(out, "20*.json")):
        if os.path.basename(old)[:10] not in days:
            os.remove(old)
    used = set()
    for d, items in days.items():
        json.dump({"date": d, "items": items}, open(os.path.join(out, d + ".json"), "w"), separators=(",", ":"), ensure_ascii=False)
        for it in items:
            used.update(it["about"]); used.update(it["also"])
    index = {"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "days": [summary(d, days[d], facts) for d in sorted(days, reverse=True)],
             "stocks": {sid: facts[sid] for sid in sorted(used) if sid in facts}}
    json.dump(index, open(os.path.join(out, "index.json"), "w"), separators=(",", ":"), ensure_ascii=False)
    print(f"::notice::News feed: {sum(len(v) for v in days.values())} headlines over {len(days)} days")


if __name__ == "__main__":
    main()
