"""Quarterly US holdings of well-known investors, from their SEC Form 13F filings.

Managers of more than $100m in US-listed shares must file Form 13F within 45 days of each quarter
end, listing their long positions. This keeps every 13F filed since 2015 by the investors below,
one JSON file each (data/history/13f/<slug>.json), and maps each holding's CUSIP to a ticker
(OpenFIGI's free mapping API, cached in data/history/cusip_map.json; issuer-name matching against
the universe when that fails).

Only new filings are downloaded, so a run after the first takes seconds. 13F shows long US
positions only: no short positions, bonds, cash or non-US shares, and it is up to 45 days old.

    python scripts/fetch_13f.py [--since 2015-01-01]
"""
from __future__ import annotations

import argparse
import csv
import glob
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

OUT = "data/history/13f"
MAP = "data/history/cusip_map.json"

# slug, manager, firm, SEC CIK (or [(cik, first period, last period), ...] when the firm changed
# the entity it files under), a line about the investor. CIKs checked against Equibles' curated
# superinvestor list and the SEC's filer records.
INVESTORS = [
    ("buffett", "Warren Buffett", "Berkshire Hathaway", 1067983, "Long-term value investing in large, durable businesses."),
    ("ackman", "Bill Ackman", "Pershing Square", [(1336528, "", "2026-03-31"), (2026053, "2026-04-01", "9999")], "A handful of large, simple, high-quality companies, sometimes as an activist."),
    ("terry-smith", "Terry Smith", "Fundsmith", 1569205, "Buy good companies, don't overpay, do nothing. US holdings of the UK fund manager."),
    ("nick-train", "Nick Train", "Lindsell Train", 1484150, "Very long holding periods in a few quality brands. US holdings of the UK fund manager."),
    ("klarman", "Seth Klarman", "Baupost Group", 1061768, "Deep value with a margin of safety."),
    ("akre", "Chuck Akre", "Akre Capital Management", 1112520, "Compounders: good businesses, good managers, good reinvestment."),
    ("tepper", "David Tepper", "Appaloosa", [(1006438, "", "2015-12-31"), (1656456, "2016-01-01", "9999")], "Opportunistic, often buying what others are selling."),
    ("druckenmiller", "Stanley Druckenmiller", "Duquesne Family Office", 1536411, "Macro-driven, concentrated bets that change quickly."),
    ("li-lu", "Li Lu", "Himalaya Capital Management", 1709323, "Very concentrated long-term value investing."),
    ("hohn", "Chris Hohn", "TCI Fund Management", 1647251, "A few dominant, high-margin businesses held for years. UK-based."),
    ("russo", "Tom Russo", "Gardner Russo & Quinn", 860643, "Global consumer brands with the capacity to reinvest."),
    ("kantesaria", "Dev Kantesaria", "Valley Forge Capital Management", 1697868, "A very small number of toll-road-like businesses."),
    ("dorsey", "Pat Dorsey", "Dorsey Asset Management", 1671657, "Companies with durable competitive advantages (economic moats)."),
    ("gayner", "Thomas Gayner", "Markel Group", 1096343, "Profitable businesses with good management at fair prices, held for decades."),
    ("burry", "Michael Burry", "Scion Asset Management", 1649339, "Contrarian and concentrated; changes positions often."),
    # added November 2026
    ("nygren", "Bill Nygren", "Harris Associates (Oakmark Funds)", 813917, "Value investing in businesses priced well below their worth, held patiently."),
    ("laffont", "Philippe Laffont", "Coatue Management", 1135730, "Technology and growth companies, from a 'Tiger cub' hedge fund."),
    ("greenblatt", "Joel Greenblatt", "Gotham Asset Management", 1510387, "Systematic value: good businesses at cheap prices, held in very many names."),
    ("halvorsen", "Andreas Halvorsen", "Viking Global Investors", 1103804, "Fundamental stock-picking across sectors, from a 'Tiger cub' hedge fund."),
    ("sundheim", "Dan Sundheim", "D1 Capital Partners", 1747057, "Concentrated growth and quality stock-picking."),
    ("dalio", "Ray Dalio", "Bridgewater Associates", 1350694, "Macro investing; the 13F shows only its US share holdings."),
    ("coleman", "Chase Coleman", "Tiger Global Management", 1167483, "Technology and internet growth companies."),
    ("mandel", "Stephen Mandel", "Lone Pine Capital", 1061165, "Growth and quality stock-picking, from a 'Tiger cub' hedge fund."),
    ("icahn", "Carl Icahn", "Icahn Capital", 921669, "Activist: large stakes in companies he pushes to change."),
    ("soros", "George Soros", "Soros Fund Management", 1029160, "Macro investing; the 13F shows only its US share holdings."),
    ("sequoia", "Ruane, Cunniff & Goldfarb", "Sequoia Fund", [(728014, "", "2017-12-31"), (1720792, "2018-01-01", "9999")], "Concentrated quality investing; the firm behind the Sequoia Fund."),
    ("marks", "Howard Marks", "Oaktree Capital Management", 949509, "Credit and distressed investing; the 13F shows only its US shares."),
    ("valueact", "Mason Morfit", "ValueAct Capital", 1418814, "Constructive activism: large stakes and board seats in a few companies."),
    ("abrams", "David Abrams", "Abrams Capital Management", 1358706, "Patient, concentrated value investing."),
    ("loeb", "Dan Loeb", "Third Point", 1040273, "Event-driven and activist investing."),
    ("greenberg", "Glenn Greenberg", "Brave Warrior Advisors", 1553733, "Concentrated, research-heavy value investing."),
    ("starboard", "Jeff Smith", "Starboard Value", 1517137, "Activist: pushes under-performing companies to improve."),
    ("peltz", "Nelson Peltz", "Trian Fund Management", 1345471, "Activist: a few large consumer and industrial companies."),
    ("einhorn", "David Einhorn", "Greenlight Capital", [(1079114, "", "2023-12-31"), (1489933, "2024-01-01", "9999")], "Value investing long, with well-known short positions (not shown in 13F)."),
    ("mclemore", "Samantha McLemore", "Patient Capital Management", 1854794, "Contrarian value with a long horizon."),
    ("rochon", "François Rochon", "Giverny Capital", 1641864, "Quality companies held for many years. Canada-based."),
    ("watsa", "Prem Watsa", "Fairfax Financial Holdings", 915191, "Value investing through an insurance group. Canada-based."),
    ("berkowitz", "Bruce Berkowitz", "Fairholme Capital Management", 1056831, "Extremely concentrated, contrarian value."),
    ("weitz", "Wally Weitz", "Weitz Investment Management", 883965, "Value investing in quality businesses."),
    ("tweedy", "Tweedy, Browne", "Tweedy, Browne Company", 732905, "Classic Graham-style value investing."),
    ("bloomstran", "Chris Bloomstran", "Semper Augustus Investments", 1115373, "Concentrated quality value."),
    ("miller", "Bill Miller", "Miller Value Partners", 1135778, "Contrarian value that also buys out-of-favour growth."),
    ("vinall", "Robert Vinall", "RV Capital", 1766596, "A few owner-led businesses held for the long term. Switzerland-based."),
    ("pabrai", "Mohnish Pabrai", "Dalal Street (Pabrai Funds)", 1549575, "A few deep-value bets: 'heads I win, tails I don't lose much'."),
    ("chou", "Francis Chou", "Chou Associates", 1389403, "Deep value and special situations. Canada-based."),
    ("spier", "Guy Spier", "Aquamarine Capital", [(1404599, "", "2022-06-30"), (1953324, "2022-07-01", "9999")], "A small, rarely changed portfolio of quality companies."),
]

ERRORS: list[str] = []


def ua() -> str:
    return f"BullPulse research {os.environ.get('SEC_CONTACT_EMAIL', '').strip()}"


def get(url: str, data: bytes | None = None, headers: dict | None = None, tries: int = 4):
    for i in range(tries):
        try:
            h = {"User-Agent": ua(), "Accept-Encoding": "identity"}
            h.update(headers or {})
            req = urllib.request.Request(url, data=data, headers=h)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(3 * (i + 1) ** 2)
        except Exception:
            time.sleep(3 * (i + 1))
    ERRORS.append(url)
    return None


def ranges(cik) -> list[tuple[int, str, str]]:
    return cik if isinstance(cik, list) else [(cik, "", "9999")]


def all_filings(cik, since: str) -> list[dict]:
    """Filings from every entity the investor has filed under, each within its period range."""
    out = []
    for c, lo, hi in ranges(cik):
        for f in filings(c, since):
            if lo <= (f["period"] or f["filed"]) <= hi:
                out.append(dict(f, cik=c))
        time.sleep(0.2)
    return sorted(out, key=lambda f: (f["filed"], f["acc"]))


def filings(cik: int, since: str) -> list[dict]:
    """13F-HR filings (and amendments) since a date, oldest first."""
    raw = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    if not raw:
        return []
    d = json.loads(raw)
    tables = [d.get("filings", {}).get("recent", {})]
    for f in d.get("filings", {}).get("files", []):   # older filings live in extra pages
        if f.get("filingTo", "9999") >= since:
            x = get("https://data.sec.gov/submissions/" + f["name"])
            if x:
                tables.append(json.loads(x))
            time.sleep(0.2)
    out = []
    for t in tables:
        for k, form in enumerate(t.get("form", [])):
            if form in ("13F-HR", "13F-HR/A") and t["filingDate"][k] >= since:
                out.append({"acc": t["accessionNumber"][k], "form": form, "filed": t["filingDate"][k], "period": t.get("reportDate", [""] * (k + 1))[k]})
    return sorted(out, key=lambda f: (f["filed"], f["acc"]))


STAKE_FORMS = {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A", "SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A"}
PCT = [re.compile(rb"<[A-Za-z:]*[Pp]ercent[A-Za-z]*>\s*([0-9]+(?:\.[0-9]+)?)\s*%?\s*<"),
       re.compile(rb"PERCENT\s+OF\s+CLASS\s+REPRESENTED\s+BY\s+AMOUNT\s+IN\s+ROW\s*\(?\s*(?:9|11)\s*\)?(?:.|\n){0,400}?([0-9]+(?:\.[0-9]+)?)\s*%", re.I)]


def stake_filings(cik: int, since: str) -> list[dict]:
    """Schedule 13D/13G filings (stakes of 5% or more) where this filer is a reporting person."""
    raw = get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    if not raw:
        return []
    t = json.loads(raw).get("filings", {}).get("recent", {})
    out = []
    for k, form in enumerate(t.get("form", [])):
        if form in STAKE_FORMS and t["filingDate"][k] >= since:
            out.append({"acc": t["accessionNumber"][k], "form": form, "filed": t["filingDate"][k], "cik": cik})
    return out


def stake_detail(cik: int, acc: str) -> dict | None:
    """The subject company (from the filing header) and the percentage owned, where stated."""
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
    hdr = get(base + acc + "-index-headers.html")
    if not hdr:
        return None
    m = re.search(rb"SUBJECT COMPANY:(.*?)(?:FILED BY:|</SUBJECT-COMPANY>|$)", hdr, re.S)
    block = m.group(1) if m else b""
    name = re.search(rb"COMPANY CONFORMED NAME:\s*([^\n<]+)", block)
    sc = re.search(rb"CENTRAL INDEX KEY:\s*(\d+)", block)
    if not name or not sc:
        return None
    out = {"subject": html.unescape(name.group(1).decode("latin-1")).strip(), "subjectCik": int(sc.group(1)), "pct": None}
    idx = get(base + "index.json")
    if idx:
        items = [i["name"] for i in json.loads(idx).get("directory", {}).get("item", [])]
        doc = next((n for n in items if n.lower() == "primary_doc.xml"), None) or \
            next((n for n in items if n.lower().endswith((".htm", ".html", ".txt")) and "index" not in n.lower()), None)
        if doc:
            body = get(base + doc) or b""
            for rx in PCT:
                mm = rx.search(body)
                if mm:
                    try:
                        v = float(mm.group(1))
                        if 0 < v <= 100:
                            out["pct"] = v
                            break
                    except ValueError:
                        pass
    return out


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]


def info_table(cik: int, acc: str) -> tuple[list[dict], str] | None:
    """The holdings in one filing: (rows, amendment type)."""
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
    idx = get(base + "index.json")
    if not idx:
        return None
    items = [i["name"] for i in json.loads(idx).get("directory", {}).get("item", [])]
    xmls = [n for n in items if n.lower().endswith(".xml")]
    amend = ""
    primary = next((n for n in xmls if "primary" in n.lower()), None)
    if primary:
        p = get(base + primary)
        if p:
            m = re.search(rb"<amendmentType>\s*([A-Z ]+)\s*<", p)
            amend = m.group(1).decode().strip() if m else ""
    table = next((n for n in xmls if n != primary and ("info" in n.lower() or "table" in n.lower())), None) or next((n for n in xmls if n != primary), None)
    if not table:
        return None
    raw = get(base + table)
    if not raw:
        return None
    return parse_table(raw), amend


def parse_table(raw: bytes) -> list[dict]:
    """Rows of a 13F information table (XML); options are left out."""
    rows = []
    for el in ET.fromstring(raw).iter():
        if strip_ns(el.tag) != "infoTable":
            continue
        v = {strip_ns(c.tag): (c.text or "").strip() for c in el.iter()}
        if v.get("putCall"):
            continue   # options, not shares
        try:
            rows.append({"cusip": v.get("cusip", "").upper(), "name": v.get("nameOfIssuer", ""), "class": v.get("titleOfClass", ""),
                         "value": float(v.get("value") or 0), "shares": float(v.get("sshPrnamt") or 0), "type": v.get("sshPrnamtType", "")})
        except ValueError:
            continue
    return rows


def unit(rows: list[dict]) -> float:
    """Dollars per reported value unit. The SEC switched 13F values from thousands to dollars in
    2023, but some managers kept reporting thousands, so the date is not enough: the implied price
    per share (value / shares) decides. Real share prices are dollars to thousands of dollars, so a
    median implied price below $2 means the values are in thousands."""
    px = sorted(r["value"] / r["shares"] for r in rows if r.get("shares") and r["value"] > 0 and r.get("type", "SH") in ("SH", ""))
    if not px:
        return 1.0
    med = px[len(px) // 2]
    return 1000.0 if med < 2 else (0.001 if med > 20000 else 1.0)


BOND = re.compile(r"\b(BOND|BONDS|NOTE|NOTES|DEBT|DBCV|SDCV|DEBENTURE)S?\b", re.I)


def is_bond(h: dict) -> bool:
    """Convertible bonds and notes, which 13F lists by principal amount rather than shares."""
    return bool(h.get("prn")) or bool(BOND.search(h.get("class") or ""))


def aggregate(rows: list[dict], filed: str) -> list[dict]:
    """One line per security; values in dollars."""
    mult = unit(rows)
    agg: dict[str, dict] = {}
    for r in rows:
        a = agg.setdefault(r["cusip"], {"cusip": r["cusip"], "name": r["name"], "class": r["class"], "value": 0.0, "shares": 0.0})
        if r["type"] == "PRN":
            a["prn"] = True
        a["value"] += r["value"] * mult
        a["shares"] += r["shares"] if r["type"] in ("SH", "") else 0
    return sorted(agg.values(), key=lambda a: -a["value"])


def figi(cusips: list[str], cache: dict) -> None:
    """Fill cache[cusip] = ticker via OpenFIGI (free, no key: 25 requests a minute, 10 ids each).
    Companies registered outside the US have CINS codes (starting with a letter), which OpenFIGI
    looks up as ID_CINS; earlier misses for those are retried once ("?" marks a second miss)."""
    todo = [c for c in cusips if c and (c not in cache or (cache[c] == "" and c[0].isalpha()))]
    for k in range(0, len(todo), 10):
        batch = todo[k:k + 10]
        body = json.dumps([{"idType": "ID_CINS" if c[0].isalpha() else "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in batch]).encode()
        raw = get("https://api.openfigi.com/v3/mapping", data=body, headers={"Content-Type": "application/json"}, tries=2)
        if raw is None:
            break
        try:
            res = json.loads(raw)
        except ValueError:
            break
        for c, r in zip(batch, res):
            data = r.get("data") or []
            eq = [x for x in data if x.get("marketSector") == "Equity"] or data
            t = (eq[0].get("ticker") or "") if eq else ""
            cache[c] = t or ("?" if c[0].isalpha() and c in cache else "")
        time.sleep(2.6)


NORM = re.compile(r"\b(INC|CORP|CORPORATION|CO|COMPANY|LTD|PLC|HLDGS?|HOLDINGS?|GROUP|CL [A-Z]|NEW|DEL|THE|COM|SHS|ORD|NV|SA|AG|LP|LLC)\b\.?")


def norm(name: str) -> str:
    n = re.sub(r"[^A-Z0-9 ]", " ", name.upper())
    return re.sub(r"\s+", " ", NORM.sub(" ", n)).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2015-01-01")
    ap.add_argument("--only", default="", help="comma-separated slugs (testing)")
    ap.add_argument("--budget", type=float, default=75, help="minutes; stop starting new investors after this")
    ap.add_argument("--stakes-since", default="2023-01-01", help="first date for Schedule 13D/13G filings")
    args = ap.parse_args()
    if not os.environ.get("SEC_CONTACT_EMAIL"):
        print("::warning::13F filings skipped: SEC_CONTACT_EMAIL is not set.")
        return 0
    os.makedirs(OUT, exist_ok=True)
    T0 = time.time()
    cache = json.load(open(MAP)) if os.path.exists(MAP) else {}
    # issuer names in the universe, for when OpenFIGI has no answer
    names = {}
    for f in glob.glob("universe/us*.csv"):
        for r in csv.DictReader(open(f, newline="")):
            names[norm(r["name"])] = r["ticker"]
    new_total = 0
    for slug, manager, firm, cik, about in INVESTORS:
        if args.only and slug not in args.only.split(","):
            continue
        path = os.path.join(OUT, slug + ".json")
        if time.time() - T0 > args.budget * 60:
            print(f"::warning::13F: time budget reached; {slug} and later investors wait for the next run")
            break
        doc = json.load(open(path)) if os.path.exists(path) else {"slug": slug, "manager": manager, "firm": firm, "filings": []}
        main_cik = ranges(cik)[-1][0]
        doc.update({"manager": manager, "firm": firm, "cik": main_cik, "ciks": [c for c, _, _ in ranges(cik)], "about": about})
        have = {f["acc"] for f in doc["filings"]}
        for f in all_filings(cik, args.since):
            if f["acc"] in have:
                continue
            got = info_table(f["cik"], f["acc"])
            time.sleep(0.3)
            if not got:
                continue
            rows, amend = got
            if f["form"] == "13F-HR/A" and amend != "RESTATEMENT":
                continue   # "new holdings" amendments add a few lines; restatements replace the filing
            f["holdings"] = aggregate(rows, f["filed"])
            f["amendment"] = amend
            doc["filings"] = [x for x in doc["filings"] if not (f["form"] == "13F-HR/A" and x["period"] == f["period"])]
            doc["filings"].append(f)
            new_total += 1
        for x in doc["filings"]:
            m = unit(x.get("holdings", []))
            if m != 1.0:
                for h in x["holdings"]:
                    h["value"] *= m
        doc["filings"].sort(key=lambda x: (x["period"], x["filed"]))
        # one filing per quarter: the latest (a restatement replaces the original)
        byq = {}
        for x in doc["filings"]:
            byq[x["period"]] = x
        doc["filings"] = [byq[k] for k in sorted(byq)]
        # stakes of 5% or more (Schedule 13D/13G), filed within days rather than 45 days after the quarter
        own = {c for c, _, _ in ranges(cik)}
        st_have = {x["acc"] for x in doc.get("stakes", [])} | set(doc.get("stakesSkipped", []))
        skipped = list(doc.get("stakesSkipped", []))
        stakes = list(doc.get("stakes", []))
        for c, lo, hi in ranges(cik):
            if hi < args.stakes_since:
                continue
            for sf in stake_filings(c, args.stakes_since):
                if sf["acc"] in st_have or time.time() - T0 > args.budget * 60:
                    continue
                det = stake_detail(c, sf["acc"])
                time.sleep(0.25)
                st_have.add(sf["acc"])
                if det and det["subjectCik"] in own:
                    skipped.append(sf["acc"])   # a filing about the investor's own company, not a stake it holds
                    continue
                if not det:
                    st_have.discard(sf["acc"])  # try again next run
                    continue
                stakes.append({**sf, **det})
        doc["stakes"] = sorted(stakes, key=lambda x: (x["filed"], x["acc"]), reverse=True)
        doc["stakesSkipped"] = sorted(set(skipped))
        cus = sorted({h["cusip"] for x in doc["filings"] for h in x.get("holdings", [])})
        figi(cus, cache)
        for x in doc["filings"]:
            for h in x.get("holdings", []):
                t = cache.get(h["cusip"], "").strip("?") or ("" if is_bond(h) else names.get(norm(h["name"]), ""))
                h["ticker"] = t.replace("/", ".")
        json.dump(doc, open(path, "w"), separators=(",", ":"))
        json.dump(cache, open(MAP, "w"), separators=(",", ":"), sort_keys=True)   # keep progress if the step is stopped
        print(f"  {slug}: {len(doc['filings'])} quarters", flush=True)
    json.dump(cache, open(MAP, "w"), separators=(",", ":"), sort_keys=True)
    print(f"::notice::13F: {new_total} new filings")
    for e in ERRORS[:5]:
        print(f"::warning::Request failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
