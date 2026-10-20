#!/usr/bin/env bash
# Sync end-of-day prices into data/prices with the library's own indicator-sync tool.
#
# Needs TIINGO_API_KEY. Tiingo's free tier allows about 50 requests an hour, 1,000 a day and
# 500 unique symbols a month, so on the free tier only the first MAX_TICKERS stocks are synced,
# spaced out to respect the hourly limit. Set TIINGO_TIER=power (the paid tier) to sync all.
# UK stocks are skipped until a UK end-of-day source is chosen (provider_ticker is empty).
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
  MAX="${MAX_TICKERS:-220}"; DELAY=75   # 48 requests an hour; 220 tickers take about 4.6 hours
fi

# provider tickers from every universe file, skipping blanks, capped at MAX
mapfile -t TICKERS < <(tail -q -n +2 universe/*.csv | awk -F',' '{print $NF}' | tr -d '\r' | grep -v '^$' | head -n "$MAX")
echo "Syncing ${#TICKERS[@]} tickers (tier: $TIER, delay: ${DELAY}s)"
mkdir -p data/prices
go run "github.com/cinar/indicator/v2/cmd/indicator-sync@${INDICATOR_VERSION}" \
  -source-name tiingo -source-config "$TIINGO_API_KEY" \
  -target-name filesystem -target-config data/prices \
  -days 3650 -delay "$DELAY" "${TICKERS[@]}"
