# BullPulse

**Live site: [bullpulse.co.uk](https://bullpulse.co.uk/)**

BullPulse is a free, open-source, end-of-day stock screener for UK and US shares. It is built for people who hold positions for weeks to months.

Every weekday night it ranks each stock on three factors, as percentiles within its own market:

| Factor | Weight | What it measures |
| --- | --- | --- |
| Trend | 40% | Price vs its 200-day average, the 50/200-day golden cross, and the Super Trend state |
| Momentum | 40% | 12-month return, excluding the latest month |
| Sentiment | 20% | 30-day news tone: headlines scored by FinBERT, weighted by relevance |

Alongside the score, BullPulse shows:

- **Growth** from company filings (SEC filings in the US, iXBRL annual reports in the UK), and a *growing and turning up* screen.
- **Fundamentals Profile**: 30 pass-or-fail checks, six each for value, growth, track record, financial health and dividends.
- **Fair value (DCF)**: a two-stage discounted cash flow of cash flow to the whole business (after share-based pay, before interest), with net debt subtracted. Visitors can change growth, required return and long-run growth on the page. A **reverse DCF** shows the growth today's price implies. Skipped for banks, insurers and property companies, and when average free cash flow is negative.
- **Insider dealing** (US): open-market buys and sells by directors and officers from SEC Form 4, with a *cluster buying* flag when two or more insiders buy within 90 days.
- **Alerts without accounts**: RSS feeds for every stock and for everything (rank moves, trend changes, new results, insider buying, news bursts). A watchlist can be exported as an OPML feed list for any feed reader.
- **Build your own screen** from 31 fields and six factors, and **test it on past data**: ten years of month-ends rebuilt from point-in-time prices and filings, with dealing costs and UK stamp duty, against the average stock and the FTSE 100 / S&P 500 (total return).
- **Index comparisons**: every stock's one-year return against its index, an index line on its chart, and an index line on the model portfolio.
- **Portfolio**: a model-portfolio builder (weights, limits, risk, past year) and a holdings tracker. Holdings can be typed in or imported from a broker's CSV file; the page shows value, gain or loss split into share price and currency, dividends, sector and market mix, alerts for the companies held and the trades that would bring the holdings back to the model mix. Everything stays in the visitor's browser.
- **Does the score work?** A public page ([score.html](https://bullpulse.co.uk/score.html)) shows the monthly validation as it stands, including where the evidence is weak. Screen backtests are split into an earlier and a later half, to show whether an edge holds up or was fitted to the past.
- **A page for every stock** at `/stock/<id>/` (for example `/stock/lse-ulvr/`), with key figures, a summary and similar companies, listed in `sitemap.xml` so search engines can find them.
- **Context**: each stock's P/E, dividend yield and free-cash-flow yield against its own last five years, and a table of the closest companies in its market and sector.
- **Investment trusts** (92 in the FTSE 350, marked `type=trust` in the universe files) are ranked on trend, momentum and news only: profit-based checks, P/E and the fair-value estimate would mislead for a company valued on its assets.
- **Plain English**: a rule-based summary paragraph on every stock, an explanation of each term on hover, and key dates (next results, last and next ex-dividend).
- **Compare** up to three stocks side by side; every filter, view and comparison is kept in the page link, so screens can be shared. The site installs as an app on phones and works offline with the last data seen.

These extra figures are displayed and screened on, but not added to the composite until the validation shows they help. The monthly validation includes a **point-in-time backtest** of the Fundamentals Profile, DCF and reverse DCF, rebuilt at every month-end from SEC filings as they were published, so the test never uses figures before investors could see them.

For each stock, the website shows the score and the reasons behind it, linked price, news-tone, RSI and volume charts, and a statistical upside/downside range. It also lists the signals for and against the stock, and flags early trend changes. Visitors can keep a watchlist (saved in their own browser), browse a sector heatmap and see the week's biggest rank movers.

> **Not investment advice.** BullPulse is a research tool. Scores summarise past prices and news; they are not forecasts or recommendations to buy or sell. Backtested results are hypothetical.

## How it works

```
SEC EDGAR filings ──► fetch_fundamentals.py, fetch_insiders.py ─┐
UK ESEF reports ───► fetch_uk_fundamentals.py (weekly) ──────────┤
Tiingo EOD prices ──► indicator-sync ──► data/prices/*.csv ──────┤
UK EOD prices, index funds, FX, dividends ► sync_uk_prices.py ───┤
Finnhub results dates ─► fetch_earnings_dates.py ─────────────────┘
GDELT / Tiingo news ─► fetch_news.py ─► score_news.py ──────┤
                         (FinBERT)                          ▼
                                    cmd/screener (Go + cinar/indicator)
                                                │
                                   site/data/*.json ──► GitHub Pages website
```

- Indicators and strategy states come from [cinar/indicator](https://github.com/cinar/indicator) v2.1.44: SMA, RSI, MACD, Bollinger Bands, ATR, OBV, Golden Cross and Super Trend.
- [`cmd/screener`](cmd/screener) computes the factors, percentile ranks and the early-trend flags, then writes `site/data/snapshot.json` plus one JSON file per stock.
- [`cmd/validate`](cmd/validate) is the out-of-sample check. At each month-end it sorts stocks into quintiles by score and measures their 1-, 3- and 6-month forward returns against the market. It also estimates trading costs, including the 0.5% UK stamp duty. Results feed the website's track-record table and [`reports/validation.md`](reports/validation.md).
- **Data checks.** Stocks whose last price is over a week old are left out. Gaps and split-like jumps are flagged on the site, and the stock is re-downloaded the next night. All prices are re-downloaded once a month so split and dividend adjustments stay correct. The report is in `data/quality.json`.
- **Score history.** Every night's scores are appended to `data/history/scores.csv`, and each stock page charts its last 180 days. In a few months this history lets the validation test whether news sentiment adds value.
- **News handling.** Company-specific stories (results, guidance, deals, legal) count more than general coverage. Headlines that don't name the company count at 35%. Bank analyst notes about other companies don't count as news about the bank. The same story syndicated by several outlets counts once.
- **Schedules.** `evening.yml` (17:15 UTC on weekdays, after the London close) fetches UK prices, the index funds (ISF.L for the FTSE 100, SPY for the S&P 500), exchange rates, dividends, filings, insider dealing, results dates and news. `nightly.yml` starts as soon as the evening job finishes (or at 21:15 UTC as a fallback, since GitHub often starts scheduled jobs hours late), waits for the New York close if needed, fetches US prices, ranks everything and publishes the site; `scripts/nightly_guard.py` makes sure only one run a night does the work. `validate.yml` (monthly) rebuilds the point-in-time history, the validation report, `panel.json` (for screen backtests) and `valhist.json` (valuation history).
- **Website data branch.** The generated files (`site/data`, `site/feeds`, `site/stock`, `site/sitemap.xml`, about 35 MB rewritten nightly) are published to the `site-data` branch as a single commit with no history (`scripts/site_data.sh`), so the main branch doesn't grow by megabytes a night. The publishing jobs unpack it into `site/` before deploying. To work on the site locally, run `scripts/site_data.sh pull`.
- **Visitor counts (optional).** Set `GOATCOUNTER` in `site/common.js` to a [GoatCounter](https://www.goatcounter.com) site code to count visits without cookies. Feedback comes in through the GitHub issue form linked in every page's footer.
- [`site/`](site) is a static site with no server.

## How the score learns

`cmd/learn` runs monthly (in `validate.yml`) after the history panel is rebuilt:

- **Outcome:** each stock's return over the next six months against the median of its own sector in its market, so it learns stock selection, not which sector boomed.
- **Signals tested:** trend, momentum, revenue growth, the fundamentals checks, price against fair value, low volatility, short-term reversal, insider buying (US, SEC Form 4 since 2015) and earnings surprises (US, quarterly filings). News sentiment keeps its original 20% until there is enough history (it is recorded permanently from October 2026 in `data/history/news_daily/`).
- **Method:** each month a cross-sectional regression of the outcome rank on the signals' ranks; weights are the average, shrunk towards zero by their own evidence (no weight below t = 2). Walk-forward only: every month is predicted from earlier months whose outcomes were known.
- **Champion and challenger:** the model in use is replaced only when a challenger (learned weights, or weights that depend on whether the market is above its 10-month average) beats it out of sample with a t-statistic above a bar that rises with every kind of challenger ever tried, and does not lose over the last 24 months, which are held back. Every trial is logged in `data/learning/trials.jsonl` and every change in `data/learning/model.json`, which the nightly screener reads.
- **Probabilities:** the model's out-of-sample predictions are calibrated into the chance of beating the sector over six months, shown on every stock.
- **Event studies:** returns against the sector after insider buying and selling, earnings surprises, golden and death crosses, new 52-week highs and (as history builds up) types of news.
- **Live record:** every night's scores and probabilities are kept in `data/history/scores.csv` and `data/history/predictions.csv` and graded after one and six months.
- **Survivorship:** S&P 500 membership history (`universe/history/`) keeps stocks out of months before they joined; universe changes are recorded from now on in `data/history/membership.csv`.

All of it is shown on the [Does the score work?](https://bullpulse.co.uk/score.html) page.

## Running cost: free

| Part | Service | Cost |
| --- | --- | --- |
| Nightly jobs | GitHub Actions (public repository) | Free |
| Website | GitHub Pages | Free |
| Prices | Tiingo free tier | Free, with limits (see below) |
| News | GDELT DOC API (no key); Tiingo news if your plan includes it | Free |
| Sentiment | FinBERT (`ProsusAI/finbert`), run on CPU inside the nightly job | Free |
| Growth data | SEC EDGAR company facts (official, no key) | Free |
| Insider dealing | SEC EDGAR Form 4 filings (official, no key) | Free |
| UK prices | Yahoo Finance public chart endpoint (no key; unofficial) | Free |
| UK fundamentals | filings.xbrl.org ESEF reports, GLEIF and LSE identifiers (no key) | Free |
| Alerts for visitors | RSS feeds published with the site | Free |
| US news and results dates | Finnhub free key (optional; GDELT otherwise) | Free |
| Index benchmarks, FX, dividends | Yahoo Finance public chart endpoint | Free |
| Alerts | A GitHub issue is opened when a nightly or validation run fails (GitHub emails you) | Free |

## Setup

1. **Add your Tiingo keys.** Go to Settings → Secrets and variables → Actions → *New repository secret*. Add `END_OF_DAY_DATA` with the token used for prices and `NEWS_UPDATES` with the token used for news. If there is only one token, add just `END_OF_DAY_DATA`; news falls back to it. (`TIINGO_API_KEY` is also accepted for prices.) Then run Actions → *Check setup* to confirm both keys work.
2. **Growth data and news (optional, free):** add `SEC_CONTACT_EMAIL`, a real email address. SEC requires one in every automated request and refuses GitHub noreply addresses; without it the growth data is skipped. Also add `FINNHUB_API_KEY` (free at finnhub.io) for better US news.
3. **Optional variables** (on the same page, *Variables* tab):
   - `TIINGO_TIER`: set to `free` (the default) or `power` (Tiingo's paid tier).
   - `MAX_TICKERS`: how many stocks to sync. The default is 220 on the free tier and all stocks on `power`.
4. **Turn on Pages.** Go to Settings → Pages → *Build and deployment* → Source: **GitHub Actions**.
5. **First run.** Go to Actions → *Nightly update* → *Run workflow*, and set the news window to 30 days. The first price sync downloads up to 10 years of history per stock.
6. **Validation.** Run Actions → *Validate score* once the price history is in place. After that it runs on the 1st of each month.

### Data limits to know about

- **Tiingo free tier.** It allows about 50 requests an hour, 1,000 a day and 500 unique symbols a month. The nightly job therefore syncs 210 US stocks, about 4.4 hours at 75 seconds per request, to stay inside GitHub's 6-hour job limit. For the full S&P 500, use Tiingo's paid tier and set `TIINGO_TIER=power`.
- **UK prices.** UK prices come from Yahoo Finance's public chart endpoint. It needs no key but is not an official API and could change or stop without notice; the script keeps each stock's previous file whenever a download looks wrong, and a failure never stops the US run. A paid source (for example EODHD) can replace it by writing the same CSV files.
- **UK fundamentals.** UK reports are annual (half-year results are not filed in iXBRL), so UK growth is year on year. Debt uses the IFRS borrowing tags; companies that tag debt with their own extensions show "–" for those checks.
- **Survivorship bias.** The universe uses today's index members, so backtests leave out companies that were later removed from the index. Validation results are flattered by this.

## Universe

- `universe/us.csv`: S&P 500 constituents from [datasets/s-and-p-500-companies](https://github.com/datasets/s-and-p-500-companies).
- `universe/uk.csv`: FTSE 100 constituents; `universe/uk250.csv`: FTSE 250 constituents (both carry an `index` column).

Columns: `ticker,name,sector,market,provider_ticker`. `provider_ticker` is the symbol used by the price source and the file name in `data/prices`.

## Tests

`go test ./...` and `python -m unittest discover tests`. Both run automatically on every push (the *Tests* workflow).

## Run locally

```bash
# prices (needs TIINGO_API_KEY in your environment)
TIINGO_API_KEY=... TIINGO_TIER=free MAX_TICKERS=20 scripts/sync_prices.sh

# news + sentiment
pip install --index-url https://download.pytorch.org/whl/cpu torch && pip install -r requirements.txt
python scripts/fetch_fundamentals.py
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
