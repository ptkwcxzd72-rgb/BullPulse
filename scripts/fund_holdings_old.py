"""The S&P 400 and 600 funds' holdings before N-PORT (2009 to mid-2019), from their N-Q quarterly
schedules and N-CSR / N-CSRS shareholder reports: HTML schedules of investments listing each
holding's name, shares and value (no tickers or CUSIPs). Written like scripts/fund_holdings.py,
to data/history/fund_holdings/<fund>/<period>.csv, with names to be matched to tickers later.

    python scripts/fund_holdings_old.py --probe     # print the structure of a few filings
    python scripts/fund_holdings_old.py [--max 20]
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import fund_holdings as H  # noqa: E402

FORMS = ["N-Q", "N-CSR", "N-CSRS"]
SINCE = "2009-01-01"


def text_of(doc: str) -> str:
    doc = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", doc)
    doc = re.sub(r"(?i)</(td|th)>", " | ", doc)
    doc = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", doc)
    doc = re.sub(r"<[^>]+>", " ", doc)
    doc = html.unescape(doc).replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", doc))


def documents(cik: str, adsh: str) -> list[tuple[str, int]]:
    idx = H.get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/index.json")
    items = json.loads(idx or b"{}").get("directory", {}).get("item", [])
    return [(i["name"], int(i.get("size") or 0)) for i in items if i["name"].lower().endswith((".htm", ".html", ".txt"))]


HEADINGS = {"ijh": r"s&p mid-?cap etf", "ijr": r"s&p small-?cap etf"}
FUND_LINE = re.compile(r"(?im)^[ \t]*(?:ishares[ \t]+)?(?:core[ \t]+)?([^|\n]{3,80}?(?:etf|fund))[ \t]*$")
NUM = re.compile(r"^\$?\s*\(?[\d,]+(\.\d+)?\)?$")
HEAD_JUNK = re.compile(r"(?i)^(\(percentages.*|[a-z]+ \d{1,2}, \d{4}|schedule of investments.*|\(unaudited\)|\(continued\))$")
STOP = re.compile(r"(?i)^(total common stocks|short-term|money market|total investments|other assets|net assets)")


def clean_name(n: str) -> str:
    n = re.sub(r"\s+", " ", n).strip()
    n = re.sub(r"(\s*\([a-z]\))+$", "", n)            # footnotes (a)(b)
    n = re.sub(r"\s+[a-z](,[a-z])*$", "", n)            # footnotes a,b (older layout)
    return n.strip(" ,")


def sections(text: str, fund: str) -> list[str]:
    """The pages of one fund's schedule: from each of its headings to the next fund's heading."""
    target = re.compile(HEADINGS[fund], re.I)
    heads = [(m.start(), bool(target.fullmatch(re.sub(r"(?i)^(ishares\s+)?(core\s+)?", "", m.group(1).strip()))))
             for m in FUND_LINE.finditer(text)]
    out = []
    for k, (pos, mine) in enumerate(heads):
        if mine:
            end = heads[k + 1][0] if k + 1 < len(heads) else len(text)
            out.append(text[pos:end])
    return out


def holdings(section: str) -> list[dict]:
    """(name, shares, value) rows of a schedule page: a name cell followed by two numbers."""
    toks = [t.strip() for t in section.split("|")]
    toks = [t for t in toks if t]
    rows, k = [], 0
    while k < len(toks):
        t = toks[k]
        if STOP.match(t):
            break
        if not NUM.match(t) and t != "$" and "%" not in t and len(t) > 2 and not t.lower().startswith(("security", "shares", "value", "common stocks")):
            nums = []
            j = k + 1
            while j < len(toks) and len(nums) < 2 and (NUM.match(toks[j]) or toks[j] == "$"):
                if toks[j] != "$":
                    nums.append(float(toks[j].strip("$() ").replace(",", "")))
                j += 1
            if len(nums) == 2 and nums[0] > 0 and nums[1] > 0:
                # a name can wrap onto two lines; a page heading can share the cell
                lines = [x for x in t.split("\n") if x.strip() and not FUND_LINE.match(x) and not HEAD_JUNK.match(x.strip())]
                rows.append({"name": clean_name(" ".join(lines)), "shares": nums[0], "value_usd": nums[1]})
                k = j
                continue
        k += 1
    return rows


def period_of(filed: str) -> str:
    """The quarter-end a schedule is for: the last quarter-end at least 45 days before filing."""
    import datetime as dt
    d = dt.date.fromisoformat(filed) - dt.timedelta(days=45)
    for y in (d.year, d.year - 1):
        for m, day in ((12, 31), (9, 30), (6, 30), (3, 31)):
            q = dt.date(y, m, day)
            if q <= d:
                return q.isoformat()
    return ""


def probe() -> None:
    """Print the lines that look like fund headings in a few older filings."""
    sid = H.series_ids(["IJH"])
    fs = [f for f in H.filings(sid["IJH"], "N-Q") if "2009-01-01" <= f["date"] < "2019-06-01"]
    for f in fs[::5]:
        docs = documents(f["cik"], f["adsh"])
        big = max(docs, key=lambda d: d[1])[0] if docs else ""
        raw = H.get(f"https://www.sec.gov/Archives/edgar/data/{f['cik']}/{f['adsh'].replace('-', '')}/{big}")
        t = text_of((raw or b"").decode("utf-8", "ignore"))
        heads = sorted({m.group(0).strip()[:90] for m in re.finditer(r"(?im)^[^|\n]*(mid|small)[- ]?cap[^|\n]*$", t)})
        print(f"== {f['date']} {big} ({len(t)} chars): {heads[:25]}")
        k = t.lower().find("midcap 400") if "midcap 400" in t.lower() else t.lower().find("mid-cap")
        print("   ", repr(t[k: k + 700]))


MIN_ROWS = {"ijh": 300, "ijr": 450}
NPORT_FROM = "2019-09-30"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--max", type=int, default=20, help="filings to read this run (each is up to 30 MB)")
    a = ap.parse_args()
    if not H.contact():
        print("::warning::SEC_CONTACT_EMAIL is not set.")
        return 0
    if a.probe:
        probe()
        return 0
    done_path = os.path.join(H.OUT, "read_old.json")
    done = json.load(open(done_path)) if os.path.exists(done_path) else {}
    sid = H.series_ids([f.upper() for f in HEADINGS])
    todo = {}
    for fund in HEADINGS:
        for form in FORMS:
            for f in H.filings(sid[fund.upper()], form):
                per = period_of(f["date"])
                if SINCE <= per < NPORT_FROM and f["adsh"] not in done:
                    todo.setdefault(f["adsh"], dict(f, period=per, form=form))
    read = 0
    for adsh, f in sorted(todo.items(), key=lambda kv: kv[1]["period"]):
        if read >= a.max:
            break
        docs = documents(f["cik"], adsh)
        if not docs:
            continue
        big = max(docs, key=lambda d: d[1])[0]
        raw = H.get(f"https://www.sec.gov/Archives/edgar/data/{f['cik']}/{adsh.replace('-', '')}/{big}")
        read += 1
        text = text_of((raw or b"").decode("utf-8", "ignore"))
        got = []
        for fund in HEADINGS:
            path = os.path.join(H.OUT, fund, f"{f['period']}.csv")
            if os.path.exists(path):
                continue
            seen, rows = set(), []
            for sec in sections(text, fund):
                for r in holdings(sec):
                    if r["name"] not in seen:
                        seen.add(r["name"])
                        rows.append(r)
            if len(rows) < MIN_ROWS[fund]:
                continue
            tot = sum(r["value_usd"] for r in rows)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", newline="") as fh:
                w = csv.DictWriter(fh, ["name", "cusip", "isin", "ticker", "shares", "value_usd", "pct"])
                w.writeheader()
                for r in rows:
                    w.writerow({"name": r["name"], "cusip": "", "isin": "", "ticker": "", "shares": r["shares"],
                                "value_usd": r["value_usd"], "pct": round(100 * r["value_usd"] / tot, 6)})
            got.append(f"{fund} {len(rows)}")
        done[adsh] = f"{f['form']} {f['period']}: " + (", ".join(got) or "nothing new")
        print(f"  {f['form']} {f['period']}: {', '.join(got) or 'no new schedule'}")
    json.dump(done, open(done_path, "w"), indent=0, sort_keys=True)
    print(f"::notice::Fund holdings before N-PORT: {read} filings read; {len(todo) - read} left")
    return 0


if __name__ == "__main__":
    sys.exit(main())
