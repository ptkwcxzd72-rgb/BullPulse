"""Point-in-time UK fundamentals from the cached annual-report extracts (data/uk_facts).

For each company, every annual report is replayed in the order it was published: after each
one, the figures are rebuilt from the reports available by then. Output has the same shape as
scripts/fundamentals_history.py (one JSON line per company per filing), with figures in the
reporting currency ("ccy") for the backtest panel to convert at that date's exchange rate.
No network access: it only reads files already fetched by fetch_uk_fundamentals.py.

    python scripts/uk_fundamentals_history.py
Writes data/fundamentals_pit_uk.jsonl (not committed; rebuilt by the monthly validation run).
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from fetch_uk_fundamentals import FACTS_DIR, IDS, growth, to_companyfacts  # noqa: E402
from sec_financials import financials  # noqa: E402

OUT = "data/fundamentals_pit_uk.jsonl"


def main():
    ids = json.load(open(IDS)) if os.path.exists(IDS) else {}
    tickers = [r["ticker"] for f in sorted(glob.glob("universe/uk*.csv")) for r in csv.DictReader(open(f, newline=""))]
    files: dict[str, list[dict]] = {}
    for p in glob.glob(os.path.join(FACTS_DIR, "*.json")):
        try:
            d = json.load(open(p))
        except Exception:
            continue
        files.setdefault(d["fxo_id"][:20], []).append(d)
    n = 0
    with open(OUT, "w") as out:
        for t in tickers:
            lei = (ids.get(t) or {}).get("lei")
            fl = sorted(files.get(lei or "", []), key=lambda d: d.get("added") or d["period_end"])
            for k in range(len(fl)):
                avail = fl[: k + 1]
                date = avail[-1].get("added") or avail[-1]["period_end"]
                facts, ccy = to_companyfacts([(d.get("added") or d["period_end"], d["facts"]) for d in reversed(avail)])
                if not facts:
                    continue
                fin = financials(facts)
                if not fin.get("shares"):
                    continue
                fin["ccy"] = ccy
                g = growth(facts)
                row = {"id": "LSE-" + t.replace(".", ""), "date": date, "fin": fin, "split": 1,
                       **{k2: g[k2] for k2 in ("rev_growth", "rev_accel", "eps_growth") if k2 in g}}
                out.write(json.dumps(row, separators=(",", ":")) + "\n")
                n += 1
    print(f"::notice::UK point-in-time fundamentals: {n} filing snapshots")


if __name__ == "__main__":
    main()
