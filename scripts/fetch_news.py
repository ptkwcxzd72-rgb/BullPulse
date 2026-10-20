"""Fetch recent news for every stock in the BullPulse universe.

Sources (both free):
  * Tiingo news API, for US tickers, when TIINGO_NEWS_KEY (or TIINGO_API_KEY) is set and the account has news access.
  * Finnhub company news, for US tickers, when FINNHUB_API_KEY is set (free key, North America only).
  * GDELT DOC 2.0 API (no key), searched by company name. Used for UK stocks, and for US stocks
    when neither Tiingo nor Finnhub news is available.

New articles are appended to data/news/articles.jsonl with score=null; scripts/score_news.py
scores them. Duplicates (same URL) are skipped and articles older than 400 days are pruned.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ARTICLES = "data/news/articles.jsonl"
UA = "BullPulse/1.0 (+https://github.com/ptkwcxzd72-rgb/BullPulse)"
SUFFIXES = r"\b(plc|p\.l\.c\.|inc\.?|incorporated|corp\.?|corporation|co\.?|company|ltd\.?|limited|holdings?|group|sa|nv|ag|the)\b"


def load_universe(path: str) -> list[dict]:
    rows = []
    for f in sorted(glob.glob(os.path.join(path, "*.csv"))):
        with open(f, newline="") as fh:
            rows += list(csv.DictReader(fh))
    return rows


def clean_name(name: str) -> str:
    n = re.sub(r"\(.*?\)", "", name)
    n = re.sub(SUFFIXES, "", n, flags=re.I)
    return re.sub(r"\s+", " ", n).strip(" ,.&")


def get_json(url: str, headers: dict | None = None, tries: int = 3):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8", "replace")
                return json.loads(body) if body.strip().startswith(("{", "[")) else None
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise
            time.sleep(5 * (attempt + 1))
        except Exception:
            time.sleep(5 * (attempt + 1))
    return None


def tiingo_news(stocks: list[dict], key: str, since: dt.date) -> list[dict]:
    by_t = {s["ticker"].lower().replace(".", "-"): s for s in stocks}
    out = []
    tickers = list(by_t)
    for i in range(0, len(tickers), 50):
        batch = ",".join(tickers[i : i + 50])
        url = f"https://api.tiingo.com/tiingo/news?tickers={batch}&startDate={since}&limit=1000"
        data = get_json(url, {"Authorization": f"Token {key}", "Content-Type": "application/json"}) or []
        for a in data:
            for t in a.get("tickers", []):
                s = by_t.get(t.lower())
                if not s:
                    continue
                out.append({
                    "date": a.get("publishedDate", "")[:10], "ticker": s["ticker"].replace(".", ""), "market": s["market"],
                    "headline": a.get("title", "").strip(), "source": a.get("source") or "Tiingo", "url": a.get("url", ""),
                    "rel": 1.0 if len(a.get("tickers", [])) <= 3 else 0.7, "via": "Tiingo"})
        time.sleep(1.5)
    return out


def finnhub_news(stocks: list[dict], key: str, since: dt.date) -> list[dict]:
    """Finnhub company news (free key, about 60 calls a minute; North American companies only)."""
    out = []
    today = dt.date.today()
    for s in stocks:
        sym = s["ticker"].replace(".", "")
        url = (f"https://finnhub.io/api/v1/company-news?symbol={urllib.parse.quote(sym)}"
               f"&from={since}&to={today}&token={key}")
        data = get_json(url) or []
        for a in data if isinstance(data, list) else []:
            ts = a.get("datetime")
            if not ts or not a.get("headline"):
                continue
            related = [r for r in (a.get("related") or "").split(",") if r]
            out.append({
                "date": dt.datetime.utcfromtimestamp(ts).date().isoformat(), "ticker": sym, "market": s["market"],
                "headline": a["headline"].strip(), "source": a.get("source") or "Finnhub", "url": a.get("url", ""),
                "rel": 1.0 if len(related) <= 2 else 0.7, "via": "Finnhub"})
        time.sleep(1.1)  # stay under 60 calls a minute
    return out


def gdelt_news(stocks: list[dict], days: int, pause: float) -> list[dict]:
    out = []
    for k, s in enumerate(stocks):
        name = clean_name(s["name"])
        if len(name) < 4:  # very short names (e.g. "3i", "BP") need the full legal name to avoid noise
            name = s["name"]
        q = f'"{name}" (shares OR stock OR profit OR results OR investors) sourcelang:english'
        url = ("https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode(
            {"query": q, "mode": "ArtList", "format": "json", "maxrecords": 50, "timespan": f"{days}d", "sort": "DateDesc"}))
        data = get_json(url) or {}
        for a in data.get("articles", []):
            title = (a.get("title") or "").strip()
            seen = a.get("seendate", "")
            if not title or len(seen) < 8:
                continue
            in_title = name.lower() in title.lower()
            out.append({
                "date": f"{seen[0:4]}-{seen[4:6]}-{seen[6:8]}", "ticker": s["ticker"].replace(".", ""), "market": s["market"],
                "headline": title, "source": a.get("domain") or "GDELT", "url": a.get("url", ""),
                "rel": 0.9 if in_title else 0.5, "via": "GDELT"})
        if (k + 1) % 50 == 0:
            print(f"  GDELT: {k + 1}/{len(stocks)} companies", flush=True)
        time.sleep(pause)  # GDELT asks clients to keep to roughly one request every few seconds
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="universe")
    ap.add_argument("--days", type=int, default=2, help="look-back window in days")
    ap.add_argument("--gdelt-pause", type=float, default=5.0)
    ap.add_argument("--max-gdelt", type=int, default=0, help="limit GDELT queries (0 = all)")
    ap.add_argument("--prices", default="data/prices", help="only fetch news for stocks with a price file here ('' = all)")
    args = ap.parse_args()

    stocks = load_universe(args.universe)
    if args.prices:
        have = {os.path.splitext(f)[0] for f in os.listdir(args.prices)} if os.path.isdir(args.prices) else set()
        stocks = [s for s in stocks if s.get("provider_ticker") and s["provider_ticker"] in have]
        print(f"{len(stocks)} stocks with price data")
    since = dt.date.today() - dt.timedelta(days=args.days)
    key = (os.environ.get("TIINGO_NEWS_KEY") or os.environ.get("TIINGO_API_KEY") or "").strip()

    fresh: list[dict] = []
    us = [s for s in stocks if s["market"] == "US"]
    gdelt_targets = [s for s in stocks if s["market"] != "US"]
    finnhub_key = os.environ.get("FINNHUB_API_KEY", "").strip()
    us_done = False
    if key and us:
        try:
            got = tiingo_news(us, key, since)
            print(f"Tiingo news: {len(got)} ticker-article pairs")
            fresh += got
            us_done = True
        except urllib.error.HTTPError as e:
            print(f"Tiingo news unavailable (HTTP {e.code})", file=sys.stderr)
    if not us_done and finnhub_key and us:
        try:
            got = finnhub_news(us, finnhub_key, since)
            print(f"Finnhub news: {len(got)} articles")
            fresh += got
            us_done = True
        except urllib.error.HTTPError as e:
            print(f"Finnhub news unavailable (HTTP {e.code})", file=sys.stderr)
    if not us_done:
        print("No US news API available; using GDELT for US stocks too")
        gdelt_targets = stocks
    if args.max_gdelt:
        gdelt_targets = gdelt_targets[: args.max_gdelt]
    got = gdelt_news(gdelt_targets, max(args.days, 1), args.gdelt_pause)
    print(f"GDELT news: {len(got)} articles")
    fresh += got

    os.makedirs(os.path.dirname(ARTICLES), exist_ok=True)
    existing, keys = [], set()
    if os.path.exists(ARTICLES):
        with open(ARTICLES) as fh:
            for line in fh:
                try:
                    a = json.loads(line)
                except json.JSONDecodeError:
                    continue
                existing.append(a)
                keys.add((a["url"], a["ticker"]))
    cutoff = (dt.date.today() - dt.timedelta(days=400)).isoformat()
    added = 0
    for a in fresh:
        k = (a["url"], a["ticker"])
        if not a["url"] or k in keys:
            continue
        keys.add(k)
        a.update({"score": None, "label": "", "conf": 0.0, "event": ""})
        existing.append(a)
        added += 1
    kept = [a for a in existing if a.get("date", "") >= cutoff]
    with open(ARTICLES, "w") as fh:
        for a in sorted(kept, key=lambda a: (a["date"], a["ticker"])):
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"articles: {added} new, {len(kept)} kept")


if __name__ == "__main__":
    main()
