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

## Model portfolios

`site/models.html`: seven rule-based strategies (`site/models-core.js`: BullPulse score leaders, momentum, quality, value, growth, steady compounders, all-rounder) with rules fixed in advance. `scripts/models.js` (nightly, node) runs each through the Strategy Lab engine in three markets with dealing costs, stamp duty and currency, trading only on the scheduled date (quarterly, and yearly for comparison), from December 2017 when every measure has a year of history. It reports the whole period, the last two years separately, a resampled range of outcomes, the market's worst falls, how often to trade, and how each strategy did in the 24 past months most like today (index trend, volatility, breadth, dispersion). Tonight's portfolios are picked by the same code with reasons and news context; "this month's" and "this year's" picks are what most strategies agree on, weighted by record and fit. Each month's portfolios are stored in `data/history/models/` and followed forward, never edited. A builder runs the engine in the browser. Limits shown on the page: news has no history to test, and companies that left the indexes are missing (survivorship). Model output for everyone, not personal advice.

`site/generator.html`: the portfolio generator. Choose an aim (growth, income, steadier, balanced) and limits (market, number of stocks, most in one stock and one sector, rebalancing, weighting, sectors and companies to leave out, leaving out what you already hold). `site/generator-core.js` picks the stocks: only signals with history choose them (trend, momentum, revenue growth, fundamentals, value, dividend yield, volatility, as percentile ranks within the eligible stocks); news tone and the learning model's estimate only break near-ties and appear as warnings, with investor ownership shown for information. It skips a second share class of the same company and shares that moved almost in step with one already chosen over two years, then enforces the stock and sector limits on the money. The same picker runs inside the Strategy Lab engine at every month-end since December 2017, so any settings are backtested exactly as they would have been used; `scripts/generator.js` (nightly) does this for each aim in each market and stores tonight's ready-made portfolios in `data/generator.json`, and other settings are tested in the browser. The page works out whole shares for an amount with dealing costs, stamp duty and currency fees, and can add the result to My holdings, open it in the Strategy Lab, download a CSV or a rebalance reminder, and show what to buy and sell since the last time. `tests/js/generator_test.js` checks the limits, exclusions, filters, near-duplicates and share arithmetic.

The generator's settings come from a review done in November 2026 to a protocol fixed before the results were seen. Seven ways of building the portfolio were compared in 12 cells (four aims × UK, US and both), stocks only, with dealing costs: the original 20 stocks rebalanced quarterly; 30 stocks held for a year (the standard settings); an index-aware build (the 50 largest eligible companies weighted by market value and tilted towards the score); sector-neutral ranking; equal risk contribution from a shrunk covariance matrix; a trend filter; and 50 stocks. The choice used only signal months up to September 2024; a change could replace the standard settings only if its information ratio (excess return over the index divided by tracking error) was higher in at least 8 of the 12 cells without deepening the average worst fall by more than 2 points. The two years after were then opened once. In the earlier years the 30-stock yearly settings beat the original in 11 of 12 cells and cut trading from about 210% to 90% a year, so they were adopted. No other change passed: the index-aware build had the best average (information ratio −0.04 against −0.20, a shallower worst fall and 56% trading) but was better in only 4 cells, so it is offered as an option; it also did best in the two later years (0.18 against −0.06, better in 8 of 12). Against 100 random portfolios of the same size from the same eligible stocks, the growth and income picks beat 65–87% of them in the earlier years, while the steady and balanced picks in the US and combined markets beat only 1–30%. That is evidence the ranking adds little, so the page recommends an index-fund core and shows these figures rather than claiming skill. UK company accounts in the panel start in 2024, so the earlier UK growth, income and balanced cells held only a handful of stocks and carry little information. The nightly script reruns the same comparisons on current data (`review` in `data/generator.json`), and the page shows a risk check for each portfolio: beta and tracking error from 36 months of returns, active share against the FTSE 100 or S&P 500 by market value, the share of risk from each sector and stock, an effective number of holdings, and the portfolio's lean on each signal.

A mean-variance optimiser was added in November 2026 (`weighting: "opt"`): expected returns follow Grinold's rule (the aim's own past IC over the 36 known months × volatility × standardised score) against the shrunk covariance, so with no past skill it becomes the lowest-risk mix. It is in the nightly review; over 2017–2026 it trailed the standard settings in most aims and markets, so it is offered, not adopted. Stock pages also show the Altman Z-score (the 1968 model for Industrials and Materials, Z″ otherwise; not for financials or property) and the Beneish M-score from the two latest annual reports, described as statistical screens rather than findings, and, once a `GEMINI_API_KEY` secret exists, up to three points from the notes of the latest 10-K or 10-Q (`scripts/notes_alerts.py`), each kept only if its quotation is in the filing word for word.

During the review, two errors were found and fixed. UK prices were partly price-only, and dividends were compounded on scaled closes, which overstated older dividends (Legal & General's 2018–23 growth was 2.06 instead of 1.40). The generator's index returns were also computed after cutting the months before the first purchase, so the index's first month absorbed all its earlier growth: about 27% for the UK, where accounts start in 2024. That made every comparison look worse for the stocks, including the figures previously on the live page.

## News

`site/news.html` shows the last three weeks of headlines about the ranked companies, each with its FinBERT tone (positive, negative or neutral), event type and the companies it is about, with their score and day's move. Filter by market, tone, topic, search, your watchlist and holdings, or the investors you follow; scroll for older days. Built nightly by `scripts/news_feed.py` from `data/news/articles.jsonl` (duplicates merged; headlines link to the publisher, no article text is copied).

## Strategy Lab, forward tracking and investors

- **Strategy Lab** (`site/lab.html`, engine in `site/lab-engine.js`): pick stocks or follow a rule (conditions, a ranking blend, top N with a holding buffer), weight them (equal, by score, lower risk or your own), rebalance monthly, quarterly, yearly, on drift or never, optionally sell below the 200-day average, add money monthly, measure in pounds or dollars, ISA/SIPP or a general account, with commission, spread, currency fees and stamp duty. On a general account it charges UK capital gains tax at each tax year's allowance and rate (by the date of each sale, losses carried forward) and dividend tax above the dividend allowance (the pre-2016 tax-credit rates before that), for a basic, higher or additional-rate taxpayer; US dividends lose 15% withholding tax in either account, credited against UK dividend tax on a general account. Dividend yields come from the company's figures, else its market's median that month, and the share estimated is reported. A **factor check** regresses each backtest's monthly returns (in dollars, above cash) on the Fama–French five factors and momentum and on the three-factor model (Kenneth French's data library: US factors, or European ones for UK portfolios, downloaded monthly by `scripts/fetch_factors.py`), showing alpha with a Newey–West t and 95% range, the loadings and R². It runs on the month-end history panel, so every month uses only what was known then and stocks count only while in their index. Results: value against S&P 500 and FTSE 100 funds and the average stock with the same money, risk measures, a bootstrapped range of outcomes, earlier/later halves, and the last 24 months hidden until the strategy is locked. Up to three strategies can be compared, and any can be shared as a link.
- **Forward tracking:** "Start tracking from today" freezes a strategy with tonight's picks and prices and follows it with real month-end prices (`site/data/monthly.json`, written nightly). Kept in the browser and shareable as a link.
- **Investors** (`site/investors.html`): 46 well-known investors' quarterly SEC Form 13F filings since 2015 (`scripts/fetch_13f.py`; CUSIPs mapped to tickers with OpenFIGI; a manager can have several SEC identifiers over time; `investors.yml` backfills new managers). For each: a profile written from linked public sources (`data/investor_profiles.json`), latest holdings with how long each has been owned, quarter-by-quarter changes (allowing for stock splits), patterns over time (concentration, turnover measured from weight changes so fund flows don't count, holding periods, sectors, biggest bets each year, style against S&P 500 companies, similar investors), the best and worst calls for a follower, and the record of copying each filing from the first close after it was published, year by year (`scripts/investors.py`). The list page shows what the investors agree on (most owned, bought and sold) and searches by ticker; stock pages show which investors own them (`data/investors/owners.json`). Stakes of 5% or more (Schedule 13D/13G, filed within days) are shown from 2023 on, and holdings outside the S&P 500 are priced from Yahoo Finance for the copy records (`scripts/fetch_13f_prices.py`; each ticker is checked against the price filed, so old tickers reused by other companies are left out). Nightly checks flag overdue filings, unmatched holdings, jumps in reported size and stale prices, on each investor page and in a GitHub issue. Follow any investor to get an RSS feed of new filings. Built from public filings; not affiliated with or endorsed by the investors.

## How the score learns

`cmd/learn` runs monthly (in `validate.yml`) after the history panel is rebuilt:

- **Outcome:** each stock's return over the next six months against the median of its own sector in its market, so it learns stock selection, not which sector boomed.
- **Signals tested:** trend, momentum, revenue growth, the fundamentals checks, price against fair value, low volatility, short-term reversal, insider buying (US, SEC Form 4 since 2015) and earnings surprises (US, quarterly filings). News sentiment keeps its original 20% until there is enough history (it is recorded permanently from October 2026 in `data/history/news_daily/`).
- **Method:** each month a cross-sectional regression of the outcome rank on the signals' ranks; weights are the average, shrunk towards zero by their own evidence (no weight below t = 2). Walk-forward only: every month is predicted from earlier months whose outcomes were known.
- **Champion and challenger:** the model in use is replaced only when a challenger (learned weights, or weights that depend on whether the market is above its 10-month average) beats it out of sample with a t-statistic above a bar that rises with every kind of challenger ever tried, and does not lose over the last 24 months, which are held back. Every trial is logged in `data/learning/trials.jsonl` and every change in `data/learning/model.json`, which the nightly screener reads.
- **Probabilities:** the model's out-of-sample predictions are calibrated into the chance of beating the sector over six months, shown on every stock.
- **Event studies:** returns against the sector after insider buying and selling, earnings surprises, golden and death crosses, new 52-week highs and (as history builds up) types of news.
- **Live record:** every night's scores and probabilities are kept in `data/history/scores.csv` and `data/history/predictions.csv` and graded after one and six months.
- **More challengers (November 2026):** separate weights for each market, and the signals passing the pre-registered signal-study rule (natural horizon, Newey–West t ≥ 2 or 3 without a published record, same sign in both halves), selected walk-forward from the months known at each date and weighted by mean IC × (1 − 1/t²). Candidates added: share issuance, gross profitability, accruals, asset growth, the Altman Z-score and the Beneish M-score. Over 2012–2026 none beat the original recipe by enough, and the original recipe itself showed almost no skill against the sector (IC 0.7%, t 0.3).
- **Survivorship:** S&P 500 membership history (`universe/history/`) keeps stocks out of months before they joined; universe changes are recorded from now on in `data/history/membership.csv`.

All of it is shown on the [Does the score work?](https://bullpulse.co.uk/score.html) page.

## Running cost: free

| Part | Service | Cost |
| --- | --- | --- |
| Nightly jobs | GitHub Actions (public repository) | Free |
| Website | GitHub Pages | Free |
| Prices | Tiingo free tier, the rest of the S&P 500 from Yahoo Finance | Free, with limits (see below) |
| News | GDELT DOC API (no key); Tiingo news if your plan includes it | Free |
| Sentiment | FinBERT (`ProsusAI/finbert`), run on CPU inside the nightly job | Free |
| Growth data | SEC EDGAR company facts (official, no key) | Free |
| Insider dealing | SEC EDGAR Form 4 filings (official, no key) | Free |
| UK prices | Yahoo Finance public chart endpoint (no key; unofficial) | Free |
| UK fundamentals | filings.xbrl.org ESEF reports, GLEIF and LSE identifiers (no key) | Free |
| Alerts for visitors | RSS feeds published with the site | Free |
| Factor returns | Kenneth French's data library (monthly) | Free |
| Notes alerts | Google Gemini API free tier (optional `GEMINI_API_KEY` secret; points are kept only when their quotation is found word for word in the filing) | Free, with daily limits |
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

- **Tiingo free tier.** It allows about 50 requests an hour, 1,000 a day and 500 unique symbols a month. The nightly job therefore syncs the first 210 US stocks from Tiingo, about 4.4 hours at 75 seconds per request, and `scripts/sync_us_yahoo.py` fills the rest of the S&P 500 from Yahoo's public chart endpoint after the New York close (total return, the same file format). Until November 2026 the rest was simply missing, so the US universe was 209 stocks, mostly names from A to F, without Microsoft, Nvidia, Meta, JPMorgan and most of the index; every US screen, backtest and model portfolio before then was drawn from that partial list. With Tiingo's paid tier (`TIINGO_TIER=power`) Tiingo covers everything and the Yahoo fill does nothing.
- **UK prices.** UK prices come from Yahoo Finance's public chart endpoint. It needs no key but is not an official API and could change or stop without notice; the script keeps each stock's previous file whenever a download looks wrong, and a failure never stops the US run. A paid source (for example EODHD) can replace it by writing the same CSV files.
- **UK fundamentals.** UK reports are annual (half-year results are not filed in iXBRL), so UK growth is year on year. Debt uses the IFRS borrowing tags; companies that tag debt with their own extensions show "–" for those checks.
- **Total return.** Prices include reinvested dividends so that returns compare fairly with the index funds. Yahoo adjusts many London listings only for splits, and some for an odd event but not their regular dividends; `dividends_missing()` compares the adjustment made with the one the listed dividends imply and adds them when most are missing. Until November 2026 the check missed partly adjusted listings (Legal & General, British American Tobacco and others) and the history panel built on 1 November held the FTSE 100 without dividends, which understated UK income and the FTSE by several points a year.
- **Market values in the history** come from reported share counts on today's split-adjusted prices, with later splits detected from jumps in the share count; reverse splits such as GE's 1-for-8 were missing until November 2026.
- **Share counts in the wrong units.** Filings sometimes state the share count in thousands or millions (Edison International's 2020 filing made it worth about $24,000 trillion; Gallagher, Carnival, Garmin and Packaging Corp similar), and UK report extracts mix units and hundreds (3i, Admiral, Aviva, M&G, Games Workshop, Vodafone). Since market value also divides cash flow and dividends into yields, those signals were wrong too. `scripts/pit_clean.py` now anchors each company's history on a filing whose market value fits its index and undoes jumps of a whole power of ten; the live UK figures get the same repair, and `fund.PlausibleShares` blanks any market value impossible for the company's index (Berkshire B, Fox and Erie, whose filings give one share class's count). Free-cash-flow yields beyond 100% and dividend yields above 30% are left blank as artefacts.
- **Pounds versus pence.** Yahoo's history for a few London shares jumps by exactly 100x between two days (Baltic Classifieds, Mears, Rose); `fix_unit_steps()` puts the older stretch on the newest basis, since re-downloading returns the same history.
- **Data-quality checks.** `scripts/data_quality.py` runs every night on the prices (coverage, stale files) and every month on the history panel. The panel check covers each index against a market-value-weighted copy built from its own members, market values that jump without the price, implausible returns and implausible yields. A failure stops the publish and opens an issue; the monthly report is in `reports/data_quality.md`. Once the share counts were repaired, the S&P 500 copy tracked the index within 1.3% a year. It led by 1.5% a year, which estimates the survivorship bias below.
- **History before 2017.** The live price files hold about ten years and are rewritten as dividends re-base total-return prices. `scripts/archive_prices.py` therefore downloads 2008 to early 2017 once per stock into `data/prices_archive` (Yahoo, with the same adjustments), and `core.LoadLong` joins it on the live basis by the median price ratio over the overlap, ignoring it if the ratios disagree by over 2%. The SEC's XBRL filings start in 2009 for large companies. `cmd/panel` builds 18 years into `panel_full.json` (research and nightly scripts); the website's `panel.json` keeps the last ten years so its download doesn't grow. Stocks listed after 2008 simply start later, and membership history keeps each stock out of the months before it joined the S&P 500.
- **Signal study.** `scripts/signal_study.js` (monthly, `reports/signal_study.md`) measures each signal's information coefficient: the rank correlation, within sectors, with the next 1, 3, 6 and 12 months' returns against the stock's sector-and-size group, with Newey-West t-statistics for the overlapping windows. A signal enters the alpha model only with the expected sign, t ≥ 2 at its natural horizon (t ≥ 3 without a long published record) and the same sign in both halves of the period. The rule was fixed before the results were seen. Candidate signals (gross profitability, accruals, asset growth, net share issuance, industry momentum, momentum per unit of risk) are kept in `panel_research.json` until they pass.
- **Survivorship bias.** The universe uses today's index members, so backtests leave out companies that were later removed from the index. Validation results are flattered by this; the benchmark check above puts it at about 1.5 points a year for the US since 2017.

## Universe

- `universe/us.csv`: S&P 500 constituents from [datasets/s-and-p-500-companies](https://github.com/datasets/s-and-p-500-companies).
- `universe/uk.csv`: FTSE 100 constituents; `universe/uk250.csv`: FTSE 250 constituents (both carry an `index` column).

Columns: `ticker,name,sector,market,provider_ticker`. `provider_ticker` is the symbol used by the price source and the file name in `data/prices`.

## Tests

`go test ./...` and `python -m unittest discover tests`. Both run automatically on every push (the *Tests* workflow).

## Run locally

```bash
# the stored daily prices (kept in the price-store release, not in git)
gh release download price-store --pattern 'prices*.tar.gz' --dir /tmp/ps && tar -xzf /tmp/ps/prices.tar.gz -C data && tar -xzf /tmp/ps/prices_archive.tar.gz -C data

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
