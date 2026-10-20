# BullPulse

BullPulse is a free, open-source, end-of-day stock screener for UK and US shares. It is built for people who hold positions for weeks to months.

Every weekday night it ranks each stock on three factors, as percentiles within its own market:

| Factor | Weight | What it measures |
| --- | --- | --- |
| Trend | 40% | Price vs its 200-day average, the 50/200-day golden cross, and the Super Trend state |
| Momentum | 40% | 12-month return, excluding the latest month |
| Sentiment | 20% | 30-day news tone: headlines scored by FinBERT, weighted by relevance |

For each stock, the website shows the score and the reasons behind it, linked price, news-tone, RSI and volume charts, and a statistical upside/downside range. It also lists the signals for and against the stock, and flags early trend changes.

> **Not investment advice.** BullPulse is a research tool. Scores summarise past prices and news; they are not forecasts or recommendations to buy or sell. Backtested results are hypothetical.

## How it works

```
Tiingo EOD prices ──► indicator-sync ──► data/prices/*.csv ─┐
GDELT / Tiingo news ─► fetch_news.py ─► score_news.py ──────┤
                         (FinBERT)                          ▼
                                    cmd/screener (Go + cinar/indicator)
                                                │
                                   site/data/*.json ──► GitHub Pages website
```

- Indicators and strategy states come from [cinar/indicator](https://github.com/cinar/indicator) v2.1.44: SMA, RSI, MACD, Bollinger Bands, ATR, OBV, Golden Cross and Super Trend.
- [`cmd/screener`](cmd/screener) computes the factors, percentile ranks and the early-trend flags, then writes `site/data/snapshot.json` plus one JSON file per stock.
- [`cmd/validate`](cmd/validate) is the out-of-sample check. At each month-end it sorts stocks into quintiles by score and measures their 1-, 3- and 6-month forward returns against the market. It also estimates trading costs, including the 0.5% UK stamp duty. Results feed the website's track-record table and [`reports/validation.md`](reports/validation.md).
- [`site/`](site) is a static page with no server. It shows fictional demo data until the first nightly run publishes real data.

## Running cost: free

| Part | Service | Cost |
| --- | --- | --- |
| Nightly jobs | GitHub Actions (public repository) | Free |
| Website | GitHub Pages | Free |
| Prices | Tiingo free tier | Free, with limits (see below) |
| News | GDELT DOC API (no key); Tiingo news if your plan includes it | Free |
| Sentiment | FinBERT (`ProsusAI/finbert`), run on CPU inside the nightly job | Free |

## Setup

1. **Add your Tiingo key.** Go to Settings → Secrets and variables → Actions → *New repository secret*. Name it `TIINGO_API_KEY` and paste your token. The same token is used for prices and news.
2. **Optional variables** (on the same page, *Variables* tab):
   - `TIINGO_TIER`: set to `free` (the default) or `power` (Tiingo's paid tier).
   - `MAX_TICKERS`: how many stocks to sync. The default is 220 on the free tier and all stocks on `power`.
3. **Turn on Pages.** Go to Settings → Pages → *Build and deployment* → Source: **GitHub Actions**.
4. **First run.** Go to Actions → *Nightly update* → *Run workflow*, and set the news window to 30 days. The first price sync downloads up to 10 years of history per stock.
5. **Validation.** Run Actions → *Validate score* once the price history is in place. After that it runs on the 1st of each month.

### Data limits to know about

- **Tiingo free tier.** It allows about 50 requests an hour, 1,000 a day and 500 unique symbols a month. The nightly job therefore syncs 220 US stocks, about 4.6 hours at 75 seconds per request, to stay inside GitHub's 6-hour job limit. For the full S&P 500, use Tiingo's paid tier and set `TIINGO_TIER=power`.
- **UK prices.** No free automated source has been chosen yet. Stooq blocks automated downloads, and Tiingo's UK coverage is unconfirmed. `universe/uk.csv` lists the FTSE 100 (as of 1 Oct 2026) with an empty `provider_ticker` column. Fill that column, and add a matching `asset.Repository` adapter if the source is not Tiingo, to switch the UK on.
- **Survivorship bias.** The universe uses today's index members, so backtests leave out companies that were later removed from the index. Validation results are flattered by this.

## Universe

- `universe/us.csv`: S&P 500 constituents from [datasets/s-and-p-500-companies](https://github.com/datasets/s-and-p-500-companies).
- `universe/uk.csv`: FTSE 100 constituents.

Columns: `ticker,name,sector,market,provider_ticker`. `provider_ticker` is the symbol used by the price source and the file name in `data/prices`.

## Run locally

```bash
# prices (needs TIINGO_API_KEY in your environment)
TIINGO_TIER=free MAX_TICKERS=20 scripts/sync_prices.sh

# news + sentiment
pip install --index-url https://download.pytorch.org/whl/cpu torch && pip install -r requirements.txt
python scripts/fetch_news.py --days 30
python scripts/score_news.py

# rank, validate, view
go run ./cmd/screener
go run ./cmd/validate
python -m http.server -d site 8000   # open http://localhost:8000
```

Keep keys in a `.env` file. It is listed in `.gitignore`, so it is never committed.

## Licence

GNU AGPL v3, the same licence as the cinar/indicator library BullPulse is built on. If you run a modified version as a public service, you must publish its source code.
