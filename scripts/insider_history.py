"""Permanent history of US insider dealing, from the SEC's quarterly insider-transaction data sets.

The SEC publishes every Form 3, 4 and 5 filing as quarterly bulk files (tab-separated tables in a
zip), back to 2006. This keeps the open-market purchases (code P) and sales (code S) reported on
Form 4 by insiders of the companies in the universe, one compressed file per quarter:

    data/history/insiders/2024q1.csv.gz
    columns: filed, trade, id, owner, role, title, code, shares, price, value, acc

A finished quarter never changes, so its file is written once; the two most recent quarters are
refreshed each run (the SEC publishes a quarter's file shortly after it ends). The nightly job's
90-day view (fetch_insiders.py) covers the weeks since.

    python scripts/insider_history.py [--from 2015q1] [--universe universe]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import gzip
import io
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

OUT = "data/history/insiders"
URLS = ["https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{q}_form345.zip",
        "https://www.sec.gov/files/datastandardsinnovation/data/insider-transactions-data-sets/{q}_form345.zip"]
COLS = ["filed", "trade", "id", "owner", "role", "title", "code", "shares", "price", "value", "acc"]
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def iso(d: str) -> str:
    """'05-MAR-2024' (or ISO already) -> '2024-03-05'; '' if unreadable."""
    d = (d or "").strip()
    if len(d) == 11 and d[2] == "-" and d[6] == "-":
        m = MONTHS.get(d[3:6].upper())
        return f"{d[7:]}-{m:02d}-{d[:2]}" if m else ""
    return d[:10] if len(d) >= 10 and d[4] == "-" else ""


def quarters(first: str, today: dt.date) -> list[str]:
    y, q = int(first[:4]), int(first[-1])
    out = []
    while (y, q) <= (today.year, (today.month - 1) // 3 + 1):
        out.append(f"{y}q{q}")
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)
    return out


def contact() -> str:
    return os.environ.get("SEC_CONTACT_EMAIL", "").strip()


def download(q: str) -> bytes | None:
    ua = f"BullPulse research {contact()}"
    for tmpl in URLS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(tmpl.format(q=q), headers={"User-Agent": ua, "Accept-Encoding": "identity"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    break           # not at this address (or not published yet): try the other one
                time.sleep(5 * (attempt + 1))
            except Exception:
                time.sleep(5 * (attempt + 1))
    return None


def table(z: zipfile.ZipFile, name: str):
    for n in z.namelist():
        if os.path.basename(n).upper().startswith(name):
            with z.open(n) as f:
                yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter="\t", quoting=csv.QUOTE_NONE)
            return


def parse(raw: bytes, ciks: dict[str, str]) -> list[dict]:
    z = zipfile.ZipFile(io.BytesIO(raw))
    subs = {}
    for r in table(z, "SUBMISSION"):
        cik = (r.get("ISSUERCIK") or "").lstrip("0")
        if cik in ciks and (r.get("DOCUMENT_TYPE") or "").strip() in ("4", "4/A"):
            subs[r["ACCESSION_NUMBER"]] = (iso(r.get("FILING_DATE", "")), ciks[cik])
    owners = {}
    for r in table(z, "REPORTINGOWNER"):
        a = r["ACCESSION_NUMBER"]
        if a in subs and a not in owners:
            owners[a] = ((r.get("RPTOWNERNAME") or "").strip(), (r.get("RPTOWNER_RELATIONSHIP") or "").strip(), (r.get("RPTOWNER_TITLE") or "").strip())
    out = []
    for r in table(z, "NONDERIV_TRANS"):
        a, code = r["ACCESSION_NUMBER"], (r.get("TRANS_CODE") or "").strip()
        if a not in subs or code not in ("P", "S"):
            continue
        try:
            sh, px = float(r.get("TRANS_SHARES") or 0), float(r.get("TRANS_PRICEPERSHARE") or 0)
        except ValueError:
            continue
        if sh <= 0 or px <= 0:
            continue
        filed, sid = subs[a]
        name, role, title = owners.get(a, ("", "", ""))
        out.append({"filed": filed, "trade": iso(r.get("TRANS_DATE", "")) or filed, "id": sid, "owner": name, "role": role,
                    "title": title[:60], "code": code, "shares": round(sh), "price": round(px, 4), "value": round(sh * px), "acc": a})
    out.sort(key=lambda x: (x["filed"], x["id"], x["acc"]))
    return out


def write(path: str, rows: list[dict]) -> None:
    """Gzipped CSV with a fixed timestamp, so an unchanged quarter gives an identical file."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    with open(path + ".tmp", "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0, filename="") as f:
        f.write(buf.getvalue().encode())
    os.replace(path + ".tmp", path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="first", default="2015q1")
    ap.add_argument("--universe", default="universe")
    ap.add_argument("--refresh", type=int, default=2, help="always re-download the newest N quarters")
    args = ap.parse_args()
    if not contact():
        print("::warning::Insider history skipped: SEC_CONTACT_EMAIL is not set.")
        return 0
    ciks = {}
    for f in sorted(glob.glob(os.path.join(args.universe, "*.csv"))):
        for r in csv.DictReader(open(f, newline="")):
            if r.get("market") != "UK" and r.get("cik"):
                ciks[r["cik"].lstrip("0")] = "US-" + r["ticker"].replace(".", "")
    os.makedirs(OUT, exist_ok=True)
    qs = quarters(args.first, dt.date.today())
    fresh = set(qs[-args.refresh:])
    done, missing = 0, []
    for q in qs:
        path = os.path.join(OUT, f"{q}.csv.gz")
        if os.path.exists(path) and q not in fresh:
            continue
        raw = download(q)
        time.sleep(1)
        if raw is None:
            if q != qs[-1]:          # the current quarter isn't published until it ends
                missing.append(q)
            continue
        rows = parse(raw, ciks)
        write(path, rows)
        done += 1
        print(f"  {q}: {len(rows)} purchases and sales", flush=True)
    print(f"::notice::Insider history: {done} quarters written, {len(glob.glob(os.path.join(OUT, '*.csv.gz')))} on file")
    if missing:
        print("::warning::Insider data sets not available for: " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
