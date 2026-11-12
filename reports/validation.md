# BullPulse validation report

Generated 2026-11-12. Price-only composite (50% trend, 50% momentum percentiles within each market); weights fixed in advance. Returns are forward excess returns over the equal-weight average of the same market.

**Caveats.** Each month counts only stocks in their index at the time (point-in-time S&P 500 membership; UK stocks count throughout, as no free history exists). Stocks that left the index and stopped trading have no free prices and are missing (survivorship bias flatters results). News sentiment has no history and is excluded. 3- and 6-month samples overlap; their t-statistics use non-overlapping months only.

## US (498 stocks, 107 month-ends, 2017-11-30 to 2026-09-30)

| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|---|
| 1 month | +0.30% | -0.06% | -0.11% | -0.13% | -0.01% | -0.31% | -0.61 |
| 3 months | +0.33% | -0.01% | -0.18% | -0.17% | +0.02% | -0.31% | -0.33 |
| 6 months | +0.85% | -0.11% | -0.74% | -0.34% | +0.34% | -0.52% | -0.91 |

Q5 beat Q1 in 51% of months (1-month horizon). Top-quintile monthly turnover 36%; estimated net monthly excess return of holding Q5 after costs: -0.08%.

Early trend changes (8125 flags): mean excess return +0.02% at 1 month, +0.10% at 3 months, -0.19% at 6 months.

| Year | Mean monthly Q5 − Q1 |
|---|---|
| 2017 | -1.04% |
| 2018 | -1.01% |
| 2019 | -0.39% |
| 2020 | -0.63% |
| 2021 | -1.74% |
| 2022 | -0.38% |
| 2023 | +0.16% |
| 2024 | +1.09% |
| 2025 | -0.09% |
| 2026 | +0.55% |

## UK (346 stocks, 107 month-ends, 2017-11-30 to 2026-09-30)

| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|---|
| 1 month | +0.23% | -0.23% | -0.06% | -0.02% | +0.07% | -0.16% | -0.35 |
| 3 months | +0.19% | -0.38% | -0.04% | -0.06% | +0.30% | +0.11% | 0.38 |
| 6 months | +0.45% | -0.52% | -0.07% | -0.39% | +0.53% | +0.07% | 0.64 |

Q5 beat Q1 in 56% of months (1-month horizon). Top-quintile monthly turnover 34%; estimated net monthly excess return of holding Q5 after costs: -0.17%.

Early trend changes (6377 flags): mean excess return -0.06% at 1 month, -0.02% at 3 months, -0.40% at 6 months.

| Year | Mean monthly Q5 − Q1 |
|---|---|
| 2017 | +0.82% |
| 2018 | -0.02% |
| 2019 | +0.77% |
| 2020 | -0.43% |
| 2021 | -1.17% |
| 2022 | -0.44% |
| 2023 | +0.02% |
| 2024 | -0.16% |
| 2025 | +1.19% |
| 2026 | -1.80% |

## Fundamentals (US, 497 companies, 2016-11-30 to 2026-09-30)

Rebuilt at each month-end from SEC filings published by then (point in time). Per-share figures are put on today's split basis and prices are adjusted back for later dividends. Higher quintile = more checks passed / cheaper / less growth priced in.

| Measure | Horizon | Q1 | Q3 | Q5 | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|
| Profile (30 checks) | 1 month | +0.30% | -0.10% | +0.04% | -0.26% | -1.01 |
|  | 3 months | +1.15% | -0.42% | -0.13% | -1.28% | -1.49 |
|  | 6 months | +3.44% | -1.07% | -0.42% | -3.87% | -2.81 |
| Price below DCF | 1 month | -0.03% | -0.15% | +0.24% | +0.27% | 0.74 |
|  | 3 months | +0.10% | -0.32% | +0.49% | +0.39% | 0.32 |
|  | 6 months | +0.48% | -0.62% | +0.80% | +0.32% | -0.04 |
| Low implied growth | 1 month | +0.09% | -0.24% | +0.16% | +0.06% | 0.16 |
|  | 3 months | +0.51% | -0.45% | +0.19% | -0.32% | -0.32 |
|  | 6 months | +1.10% | -1.02% | +0.24% | -0.86% | -0.41 |
| Value | 1 month | -0.10% | +0.05% | +0.09% | +0.19% | 0.60 |
|  | 3 months | +0.03% | -0.03% | -0.07% | -0.11% | 0.36 |
|  | 6 months | +0.13% | -0.15% | -0.52% | -0.64% | -0.12 |
| Growth | 1 month | +0.07% | -0.17% | +0.26% | +0.19% | 0.69 |
|  | 3 months | +0.04% | -0.13% | +0.69% | +0.65% | 0.93 |
|  | 6 months | +0.28% | -0.10% | +1.25% | +0.97% | 0.74 |
| Track record | 1 month | +0.12% | -0.12% | +0.05% | -0.08% | -0.30 |
|  | 3 months | +0.66% | -0.32% | -0.00% | -0.66% | -0.56 |
|  | 6 months | +2.30% | -0.89% | -0.09% | -2.40% | -1.50 |
| Health | 1 month | -0.16% | -0.04% | +0.15% | +0.31% | 1.30 |
|  | 3 months | -0.35% | -0.04% | +0.46% | +0.81% | 0.61 |
|  | 6 months | -0.47% | -0.58% | +0.95% | +1.42% | 0.58 |
| Dividends | 1 month | +0.54% | -0.14% | -0.21% | -0.74% | -1.97 |
|  | 3 months | +1.84% | -0.39% | -0.81% | -2.65% | -1.93 |
|  | 6 months | +4.15% | -1.05% | -1.81% | -5.97% | -2.38 |

