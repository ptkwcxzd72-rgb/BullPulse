"""Daily prices for companies that were in the S&P 400 or 600 but are not in the universe today
(taken over, moved down or out, or delisted), so the backtests can include them.

Each past member comes from the funds' quarterly holdings (data/history/fund_holdings), which
give its name, CUSIP, often its ticker, and its shares and dollar value at each quarter-end, so
its quarter-end price is known without any other source. For a holding with no ticker, the ticker
is found from SEC records: the company's CIK from the SEC's list of every name it has filed
under, then the trading symbol on the cover page of its last 10-K or 10-Q (tagged since 2019).

Daily prices then come from Yahoo Finance (most companies still trade under some listing), or
from Tiingo, which keeps delisted shares, within its free tier's 500 different tickers a month.
A price series is kept only if it agrees with the quarter-end prices in the filings: tickers are
reused, and a series that belongs to a different company would otherwise slip in. Written to
data/prices_departed/<ticker>.csv in the format of data/prices (total-return closes), and kept in
the price store. Progress and the reasons for misses are in data/history/departed.json.

    python scripts/departed.py [--budget-min 30] [--tiingo 150]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import gzip
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
import build_membership as BM  # noqa: E402
import sync_uk_prices as UK  # noqa: E402

OUT = "data/prices_departed"
STATE = "data/history/departed.json"
HOLD = "data/history/fund_holdings"
START = "2008-01-01"
SPLITS = [2, 3, 4, 5, 1.5, 0.5, 1 / 3, 0.25, 0.2, 10, 0.1, 1 / 1.5]
NAME_JUNK = re.compile(r"\b(INC|CORP|CORPORATION|CO|COMPANY|LTD|PLC|HOLDINGS?|HLDGS?|GROUP|THE|NEW|CLASS [A-Z]|CL [A-Z]|COM|LLC|LP|NV|SA)\b\.?")


def sec_get(url: str, as_json: bool = True):
    req = urllib.request.Request(url, headers={"User-Agent": f"BullPulse research screener {os.environ.get('SEC_CONTACT_EMAIL', '')}",
                                               "Accept-Encoding": "gzip"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                b = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    b = gzip.decompress(b)
            time.sleep(0.15)
            return json.loads(b) if as_json else b.decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None


simple = BM.simple


def past_members(universe: set[str]) -> dict[str, dict]:
    """Every holding not in today's universe: key (ticker, else CUSIP) -> {name, cusip, ticker,
    prices: {quarter-end: value / shares}}."""
    out: dict[str, dict] = {}
    files = sorted(glob.glob(os.path.join(HOLD, "*", "*.csv")))
    cmap = BM.cusip_tickers(files)
    nmap = BM.name_tickers(files, cmap)
    for f in files:
        d = os.path.basename(f)[:10]
        for r in csv.DictReader(open(f, newline="")):
            c = (r.get("cusip") or "")[:9]
            t = BM.ticker_of(r, cmap, nmap)
            if t in universe:
                continue
            # older schedules give names only
            key = t or c or ("name:" + BM.simple(r["name"]))
            if not key:
                continue
            e = out.setdefault(key, {"name": r["name"], "cusip": c, "ticker": t, "prices": {}})
            try:
                sh, v = float(r["shares"]), float(r["value_usd"])
                if sh > 0 and v > 0:
                    e["prices"][d] = v / sh
            except (TypeError, ValueError):
                pass
    return out


def cik_by_name() -> dict[str, list[str]]:
    """Simplified company name -> CIKs, from every name in the SEC's EDGAR records."""
    txt = sec_get("https://www.sec.gov/Archives/edgar/cik-lookup-data.txt", as_json=False) or ""
    out: dict[str, list[str]] = {}
    for line in txt.splitlines():
        m = re.match(r"^(.*):(\d{10}):$", line.strip())
        if m:
            out.setdefault(simple(m.group(1)), []).append(str(int(m.group(2))))
    return out


def symbol_on_cover(page: str) -> str:
    """The first trading symbol on an XBRL cover page (R1.htm): the cell after 'Trading Symbol'."""
    m = re.search(r"Trading Symbol.{0,200}?<td[^>]*>\s*([A-Za-z][A-Za-z.\-]{0,6})\s*<", page, re.S)
    return BM.norm(m.group(1)) if m else ""


def cover_ticker(cik: str) -> str:
    """The trading symbol on the cover page of the company's latest 10-K or 10-Q."""
    sub = sec_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json") or {}
    if sub.get("tickers"):
        return BM.norm(sub["tickers"][0])
    rec = sub.get("filings", {}).get("recent", {})
    for j, form in enumerate(rec.get("form", [])):
        if form in ("10-K", "10-Q"):
            acc = rec["accessionNumber"][j].replace("-", "")
            page = sec_get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/R1.htm", as_json=False) or ""
            return symbol_on_cover(page)
    return ""


def yahoo(sym: str):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym.replace('.', '-')}?period1={int(dt.datetime(2008, 1, 1).timestamp())}"
           f"&period2={int(time.time())}&interval=1d&events=div%2Csplit&includeAdjustedClose=true")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UK.UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
    except Exception:
        return None
    missing = UK.dividends_missing(d)
    ccy, bars = UK.parse_chart(d, scale_override=1.0, raw=missing)
    if ccy and ccy != "USD":
        return None
    _, quoted = UK.parse_chart(d, scale_override=1.0, raw=True)
    if bars and missing:
        bars = UK.add_dividends(bars, UK.parse_dividends(d, 1.0))
    return bars, {b[0]: b[4] for b in quoted}


def tiingo(sym: str, key: str):
    url = f"https://api.tiingo.com/tiingo/daily/{sym.lower().replace('.', '-')}/prices?startDate={START}&token={key}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Content-Type": "application/json"}), timeout=60) as r:
            rows = json.load(r)
    except Exception:
        return None
    if not isinstance(rows, list) or not rows:
        return None
    bars = [[x["date"][:10], x.get("adjOpen"), x.get("adjHigh"), x.get("adjLow"), x.get("adjClose"), x.get("adjVolume")] for x in rows if x.get("adjClose")]
    quoted = {x["date"][:10]: x["close"] for x in rows if x.get("close")}
    return bars, quoted


def agrees(quoted: dict[str, float], filed: dict[str, float]) -> tuple[bool, str]:
    """Do the series' quoted closes match the filings' quarter-end prices? Each quarter-end must
    be within 3% after allowing for later stock splits (the filings quote the price of the day)."""
    days = sorted(quoted)
    if not days:
        return False, "no prices"
    checked = bad = 0
    for q, p in filed.items():
        k = max((d for d in days if d <= q), default=None)
        if not k or (dt.date.fromisoformat(q) - dt.date.fromisoformat(k)).days > 6:
            continue
        r = quoted[k] / p
        checked += 1
        if not any(abs(r * s - 1) < 0.03 for s in [1] + SPLITS):
            bad += 1
    if checked < 2:
        return False, f"only {checked} quarter-ends to check"
    return bad <= max(1, checked // 10), f"{checked - bad} of {checked} quarter-ends agree"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget-min", type=float, default=30)
    ap.add_argument("--tiingo", type=int, default=150, help="most different tickers to ask Tiingo for this run")
    a = ap.parse_args()
    stop = time.time() + a.budget_min * 60
    universe = {r["ticker"] for f in glob.glob("universe/*.csv") for r in csv.DictReader(open(f, newline=""))}
    state = json.load(open(STATE)) if os.path.exists(STATE) else {"ids": {}, "status": {}}
    os.makedirs(OUT, exist_ok=True)
    members = past_members(universe)
    names = None
    tkey = os.environ.get("TIINGO_API_KEY", "").strip()
    # Tiingo's free tier allows 500 different tickers a month, and the nightly job uses 210
    month = dt.date.today().strftime("%Y-%m")
    used = state.setdefault("tiingo", {}).get(month, 0)
    room = max(0, min(a.tiingo, 250 - used))
    asked = 0
    for key, e in sorted(members.items(), key=lambda kv: -len(kv[1]["prices"])):
        if time.time() > stop:
            break
        st = state["status"].get(key, {})
        if st.get("ok") or st.get("tries", 0) >= 3:
            continue
        idkey = e["cusip"] or key
        t = e["ticker"] or state["ids"].get(idkey, "")
        if not t and os.environ.get("SEC_CONTACT_EMAIL") and "cik" not in st:
            names = names if names is not None else cik_by_name()
            ciks = names.get(simple(e["name"]), [])
            st["cik"] = ciks[0] if len(ciks) == 1 else ""
            t = cover_ticker(st["cik"]) if st["cik"] else ""
            if t:
                state["ids"][idkey] = t
        if not t:
            st.update(tries=st.get("tries", 0) + 1, why="no ticker found")
            state["status"][key] = st
            continue
        got, why = None, ""
        res = yahoo(t)
        if res:
            ok, why = agrees(res[1], e["prices"])
            got = res if ok else None
        if got is None and tkey and asked < room:
            asked += 1
            res = tiingo(t, tkey)
            if res:
                ok, why = agrees(res[1], e["prices"])
                got = res if ok else None
            time.sleep(1.2)
        if got:
            UK.write_bars(os.path.join(OUT, t.lower().replace(".", "-") + ".csv"), [b for b in got[0] if b[0] >= START])
            st.update(ok=True, ticker=t, why=why)
        else:
            st.update(tries=st.get("tries", 0) + 1, ticker=t, why=why or "no prices from Yahoo or Tiingo")
        state["status"][key] = st
        time.sleep(0.5)
    state["tiingo"] = {month: used + asked}
    json.dump(state, open(STATE, "w"), indent=0, sort_keys=True)
    ok = sum(1 for k in members if state["status"].get(k, {}).get("ok"))
    # share of the funds' past weight now covered, a quarter at a time
    print(f"::notice::Departed members: {ok} of {len(members)} have checked daily prices; Tiingo asked for {asked} this run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
