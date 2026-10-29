"""Permanent daily record of news tone per stock (data/history/news_daily/YYYY.csv).

The raw articles (data/news/articles.jsonl) are pruned after 400 days to keep the repository
small, so this keeps what the learning needs for ever: for every stock and day with news, how many
relevant articles there were, their relevance-weighted FinBERT tone, and how many fell into each
event category (results, guidance, deals, management, capital, legal). Days still inside the
articles window are rebuilt each run; older days are left exactly as recorded.

    python scripts/news_daily.py
"""
from __future__ import annotations

import collections
import csv
import glob
import json
import os

ARTICLES = "data/news/articles.jsonl"
OUT_DIR = "data/history/news_daily"
CATS = {"Earnings": "results", "Guidance": "guidance", "M&A": "deal", "Management": "management",
        "Capital": "capital", "Legal / regulatory": "legal"}
COLS = ["date", "id", "n", "tone", "weight"] + sorted(set(CATS.values()))


def stock_id(a: dict) -> str:
    t = (a.get("ticker") or "").replace(".", "")
    return ("LSE-" if a.get("market") == "UK" else "US-") + t


def aggregate(articles: list[dict]) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for a in articles:
        if not a.get("date") or not a.get("ticker") or a.get("score") is None:
            continue
        k = (a["date"][:10], stock_id(a))
        r = out.setdefault(k, {"n": 0, "tw": 0.0, "w": 0.0, **{c: 0 for c in CATS.values()}})
        w = float(a.get("rel", 1.0) or 0)
        r["n"] += 1
        r["tw"] += w * float(a["score"])
        r["w"] += w
        c = CATS.get(a.get("event") or "")
        if c:
            r[c] += 1
    return out


def main() -> None:
    if not os.path.exists(ARTICLES):
        print("no articles yet")
        return
    arts = [json.loads(l) for l in open(ARTICLES) if l.strip()]
    agg = aggregate(arts)
    if not agg:
        return
    first = min(d for d, _ in agg)   # days from here on are rebuilt from the articles
    os.makedirs(OUT_DIR, exist_ok=True)
    by_year: dict[str, dict[tuple[str, str], dict]] = collections.defaultdict(dict)
    for path in glob.glob(os.path.join(OUT_DIR, "*.csv")):
        for r in csv.DictReader(open(path, newline="")):
            if r["date"] < first:
                by_year[r["date"][:4]][(r["date"], r["id"])] = r
    for (d, i), r in agg.items():
        by_year[d[:4]][(d, i)] = {"date": d, "id": i, "n": r["n"], "tone": round(r["tw"] / r["w"], 4) if r["w"] else "",
                                  "weight": round(r["w"], 3), **{c: r[c] for c in CATS.values()}}
    rows = 0
    for y, recs in by_year.items():
        with open(os.path.join(OUT_DIR, f"{y}.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            for k in sorted(recs):
                w.writerow(recs[k])
                rows += 1
    print(f"::notice::News history: {rows} stock-days kept")


if __name__ == "__main__":
    main()
