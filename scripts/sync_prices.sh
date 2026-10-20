#!/usr/bin/env bash
# Sync end-of-day prices into data/prices with the library's own indicator-sync tool.
#
# Needs TIINGO_API_KEY. Tiingo's free tier allows about 50 requests an hour, 1,000 a day and
# 500 unique symbols a month, so on the free tier only the first MAX_TICKERS stocks are synced,
# spaced out to respect the hourly limit. Set TIINGO_TIER=power (the paid tier) to sync all.
# UK stocks are synced separately by scripts/sync_uk_prices.py.
set -euo pipefail

INDICATOR_VERSION="v2.1.44"
TIER="${TIINGO_TIER:-free}"
if [[ -z "${TIINGO_API_KEY:-}" ]]; then
  echo "::error::TIINGO_API_KEY is not available to this job. Add it under Settings > Secrets and variables > Actions > Secrets as END_OF_DAY_DATA (or TIINGO_API_KEY)."
  exit 1
fi

if [[ "$TIER" == "power" ]]; then
  MAX="${MAX_TICKERS:-10000}"; DELAY=1
else
  MAX="${MAX_TICKERS:-210}"; DELAY=75   # 48 requests an hour; 210 tickers take about 4.4 hours
fi

# provider tickers from every universe file (by header name), skipping blanks, capped at MAX
mapfile -t TICKERS < <(python3 -c '
import csv, glob
for f in sorted(glob.glob("universe/*.csv")):
    for r in csv.DictReader(open(f, newline="")):
        t = (r.get("provider_ticker") or "").strip()
        if t and r.get("market") != "UK": print(t)' | head -n "$MAX")
echo "Syncing ${#TICKERS[@]} tickers (tier: $TIER, delay: ${DELAY}s)"
mkdir -p data/prices

# Tiingo serves split- and dividend-adjusted prices, but new days are appended to stored
# history, which is not re-adjusted. So: (1) re-download any stock the screener flagged
# (split-like jump), and (2) re-download everything once a month. Both cost the same number
# of requests as a normal night (one per stock).
MONTH="$(date -u +%Y-%m)"
if [[ ! -f "data/prices/.refreshed-$MONTH" ]]; then
  echo "Monthly full refresh: re-downloading all price history"
  find data/prices -name '*.csv' -delete
  rm -f data/prices/.refreshed-*
  touch "data/prices/.refreshed-$MONTH"
elif [[ -f data/quality.json ]]; then
  python3 - <<'PY'
import json, os
for t in json.load(open("data/quality.json")).get("resync") or []:
    p = os.path.join("data/prices", f"{t}.csv")
    if os.path.exists(p):
        os.remove(p); print(f"re-downloading {t} (flagged by the data check)")
PY
fi
go run "github.com/cinar/indicator/v2/cmd/indicator-sync@${INDICATOR_VERSION}" \
  -source-name tiingo -source-config "$TIINGO_API_KEY" \
  -target-name filesystem -target-config data/prices \
  -days 3650 -delay "$DELAY" "${TICKERS[@]}"
