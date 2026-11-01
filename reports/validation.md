# BullPulse validation report

Generated 2026-11-01. Price-only composite (50% trend, 50% momentum percentiles within each market); weights fixed in advance. Returns are forward excess returns over the equal-weight average of the same market.

**Caveats.** Each month counts only stocks in their index at the time (point-in-time S&P 500 membership; UK stocks count throughout, as no free history exists). Stocks that left the index and stopped trading have no free prices and are missing (survivorship bias flatters results). News sentiment has no history and is excluded. 3- and 6-month samples overlap; their t-statistics use non-overlapping months only.

## US (209 stocks, 107 month-ends, 2017-11-30 to 2026-09-30)

| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|---|
| 1 month | +0.30% | -0.14% | -0.04% | -0.04% | -0.09% | -0.39% | -0.73 |
| 3 months | +0.02% | +0.09% | +0.08% | -0.05% | -0.14% | -0.16% | -0.14 |
| 6 months | +0.29% | -0.23% | -0.59% | +0.07% | +0.45% | +0.17% | -0.50 |

Q5 beat Q1 in 50% of months (1-month horizon). Top-quintile monthly turnover 36%; estimated net monthly excess return of holding Q5 after costs: -0.16%.

Early trend changes (3299 flags): mean excess return +0.13% at 1 month, +0.29% at 3 months, -0.14% at 6 months.

| Year | Mean monthly Q5 − Q1 |
|---|---|
| 2017 | -2.35% |
| 2018 | -1.17% |
| 2019 | +0.05% |
| 2020 | -1.05% |
| 2021 | -1.79% |
| 2022 | -0.47% |
| 2023 | +0.31% |
| 2024 | +0.77% |
| 2025 | -0.09% |
| 2026 | +0.50% |

## UK (338 stocks, 107 month-ends, 2017-11-30 to 2026-09-30)

| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|---|
| 1 month | -0.11% | -0.45% | -0.31% | +1.05% | -0.17% | -0.06% | -0.13 |
| 3 months | -0.89% | -1.29% | -0.76% | +3.37% | -0.40% | +0.48% | 0.30 |
| 6 months | -1.44% | -2.64% | -1.74% | +3.85% | +2.02% | +3.46% | -0.19 |

Q5 beat Q1 in 58% of months (1-month horizon). Top-quintile monthly turnover 32%; estimated net monthly excess return of holding Q5 after costs: -0.40%.

Early trend changes (6602 flags): mean excess return -0.46% at 1 month, +0.28% at 3 months, +0.86% at 6 months.

| Year | Mean monthly Q5 − Q1 |
|---|---|
| 2017 | +1.23% |
| 2018 | -0.01% |
| 2019 | +0.89% |
| 2020 | +0.09% |
| 2021 | -1.13% |
| 2022 | -0.47% |
| 2023 | -0.29% |
| 2024 | +0.28% |
| 2025 | +0.97% |
| 2026 | -1.41% |

## Fundamentals (US, 208 companies, 2016-10-31 to 2026-09-30)

Rebuilt at each month-end from SEC filings published by then (point in time). Per-share figures are put on today's split basis and prices are adjusted back for later dividends. Higher quintile = more checks passed / cheaper / less growth priced in.

| Measure | Horizon | Q1 | Q3 | Q5 | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|
| Profile (30 checks) | 1 month | +0.31% | -0.00% | +0.03% | -0.29% | -0.95 |
|  | 3 months | +1.15% | -0.28% | -0.24% | -1.39% | -2.04 |
|  | 6 months | +3.41% | -0.69% | -0.83% | -4.24% | -2.73 |
| Price below DCF | 1 month | -0.06% | +0.23% | +0.09% | +0.15% | 0.37 |
|  | 3 months | -0.13% | +0.24% | -0.10% | +0.03% | -0.47 |
|  | 6 months | -0.10% | +0.37% | -0.53% | -0.43% | -0.01 |
| Low implied growth | 1 month | -0.03% | -0.26% | +0.01% | +0.05% | 0.10 |
|  | 3 months | +0.16% | -0.70% | -0.10% | -0.27% | -0.21 |
|  | 6 months | +0.29% | -1.37% | -0.37% | -0.67% | -0.06 |
| Value | 1 month | -0.15% | -0.02% | +0.14% | +0.29% | 0.79 |
|  | 3 months | -0.16% | -0.16% | +0.16% | +0.32% | -0.10 |
|  | 6 months | -0.13% | -0.39% | +0.04% | +0.17% | 0.19 |
| Growth | 1 month | +0.01% | -0.12% | +0.15% | +0.14% | 0.45 |
|  | 3 months | -0.14% | +0.07% | +0.25% | +0.39% | 0.04 |
|  | 6 months | +0.33% | +0.00% | +0.64% | +0.31% | 0.38 |
| Track record | 1 month | +0.15% | -0.01% | -0.05% | -0.20% | -0.71 |
|  | 3 months | +0.72% | +0.07% | -0.05% | -0.78% | -1.25 |
|  | 6 months | +2.08% | -0.57% | -0.02% | -2.11% | -1.63 |
| Health | 1 month | -0.16% | -0.09% | +0.18% | +0.35% | 1.18 |
|  | 3 months | -0.34% | -0.16% | +0.67% | +1.01% | 0.88 |
|  | 6 months | -0.28% | -0.94% | +1.15% | +1.43% | 0.99 |
| Dividends | 1 month | +0.52% | -0.16% | -0.22% | -0.74% | -1.77 |
|  | 3 months | +1.57% | -0.43% | -0.91% | -2.48% | -2.26 |
|  | 6 months | +3.22% | -0.99% | -2.08% | -5.30% | -2.06 |

