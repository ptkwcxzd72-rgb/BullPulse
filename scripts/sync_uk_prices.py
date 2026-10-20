"""Sync end-of-day prices for the UK universe (FTSE 100) into data/prices.

Source: Yahoo Finance's public chart endpoint, which needs no key. It is not an official API,
so this script is polite (one request a second, backs off on errors) and conservative: a stock
keeps its previous file whenever a download looks wrong. Prices are written in pence (GBX),
split- and dividend-adjusted, in the same CSV layout as cinar/indicator's file repository, so the
screener treats UK and US stocks identically.

It also saves the GBP exchange rates the fundamentals need (data/fx.json): UK companies often
report in US dollars or euros while their shares trade in pence.

    python scripts/sync_uk_prices.py [--universe universe/uk.csv] [--out data/prices]
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
import urllib.request

UA = "Mozilla/5.0 (compatible; BullPulse research; +https://github.com/ptkwcxzd72-rgb/BullPulse)"
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d&events=div%2Csplit&includeAdjustedClose=true"


def yahoo_symbol(ticker: str) -> str:
    """LSE ticker as Yahoo spells it: BT.A -> BT-A.L, RR. -> RR.L."""
    return ticker.strip().rstrip(".").replace(".", "-") + ".L"


def get_json(url: str, tries: int = 4) -> dict | None:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(5 * (i + 1) ** 2)   # 429 or 5xx: back off
        except Exception:
            time.sleep(5 * (i + 1))
    return None


FX: dict = {"GBP": 1.0}   # GBP per unit of currency, filled by main() before prices are parsed


def parse_chart(d: dict) -> tuple[str, list[list]]:
    """(currency, rows of [date, open, high, low, close, volume]) adjusted for splits and dividends."""
    res = (d or {}).get("chart", {}).get("result") or []
    if not res:
        return "", []
    r = res[0]
    ccy = r.get("meta", {}).get("currency", "")
    ts = r.get("timestamp") or []
    q = (r.get("indicators", {}).get("quote") or [{}])[0]
    adj = ((r.get("indicators", {}).get("adjclose") or [{}])[0]).get("adjclose") or [None] * len(ts)
    scale = {"GBp": 1.0, "GBX": 1.0, "GBP": 100.0}.get(ccy)
    if scale is None and ccy in FX:   # a few FTSE 100 lines are quoted in dollars or euros: convert to pence
        scale = FX[ccy] * 100
    if scale is None:
        return ccy, []
    out, seen = [], set()
    for i, t in enumerate(ts):
        o, h, lo, c, v = (q.get(k, [None] * len(ts))[i] for k in ("open", "high", "low", "close", "volume"))
        if None in (o, h, lo, c) or c <= 0:
            continue
        day = dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat()
        if day in seen:          # Yahoo sometimes repeats the live day
            continue
        seen.add(day)
        f = (adj[i] / c) if adj[i] else 1.0
        out.append([day, round(o * f * scale, 4), round(h * f * scale, 4), round(lo * f * scale, 4), round(c * f * scale, 4), int(v or 0)])
    return ccy, out


def looks_sane(rows: list[list], old_path: str) -> str:
    """Empty string if fine, otherwise the reason to keep the old file."""
    if len(rows) < 260:
        return f"only {len(rows)} days of history"
    last = dt.date.fromisoformat(rows[-1][0])
    if (dt.date.today() - last).days > 10:
        return f"latest price is from {last}"
    if os.path.exists(old_path):
        with open(old_path) as f:
            old = list(csv.reader(f))[1:]
        if len(old) > len(rows) + 30:
            return f"history shrank from {len(old)} to {len(rows)} days"
    return ""


def fx_rates() -> dict:
    """Units of GBP per one unit of each reporting currency."""
    out = {"GBP": 1.0}
    for ccy in ("USD", "EUR"):
        d = get_json(CHART.format(sym=f"GBP{ccy}%3DX", rng="5d"))
        try:
            px = [p for p in d["chart"]["result"][0]["indicators"]["quote"][0]["close"] if p]
            out[ccy] = round(1 / px[-1], 6)
        except Exception:
            print(f"::warning::Could not fetch the GBP/{ccy} exchange rate")
        time.sleep(1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="universe/uk.csv")
    ap.add_argument("--out", default="data/prices")
    ap.add_argument("--pause", type=float, default=1.0)
    ap.add_argument("--limit", type=int, default=0, help="only the first N stocks (testing)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    rows = list(csv.DictReader(open(args.universe, newline="")))
    if args.limit:
        rows = rows[: args.limit]
    FX.update(fx_rates())
    ok, kept, failed = 0, [], []
    for r in rows:
        name = (r.get("provider_ticker") or "").strip()
        if not name:
            continue
        path = os.path.join(args.out, name + ".csv")
        ccy, bars = parse_chart(get_json(CHART.format(sym=yahoo_symbol(r["ticker"]), rng="10y")))
        why = "no data" if not bars and not ccy else (f"quoted in {ccy}, not pence" if not bars else looks_sane(bars, path))
        if why:
            (kept if os.path.exists(path) else failed).append(f"{r['ticker']} ({why})")
        else:
            tmp = path + ".tmp"
            with open(tmp, "w", newline="") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
                w.writerows(bars)
            os.replace(tmp, path)
            ok += 1
        time.sleep(args.pause)
    os.makedirs("data", exist_ok=True)
    json.dump({"generated": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "to_gbp": FX}, open("data/fx.json", "w"), indent=1)
    print(f"::notice::UK prices: {ok} of {len(rows)} updated; {len(kept)} kept their previous file; {len(failed)} missing")
    for k in kept[:10]:
        print(f"::warning::Kept previous prices for {k}")
    if failed:
        print("::warning::No UK prices for: " + ", ".join(failed[:30]))
    if ok == 0 and rows:
        sys.exit("no UK prices could be downloaded")


if __name__ == "__main__":
    main()
