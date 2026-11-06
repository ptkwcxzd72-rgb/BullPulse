# BullPulse validation report

Generated 2026-11-06. Price-only composite (50% trend, 50% momentum percentiles within each market); weights fixed in advance. Returns are forward excess returns over the equal-weight average of the same market.

**Caveats.** Each month counts only stocks in their index at the time (point-in-time S&P 500 membership; UK stocks count throughout, as no free history exists). Stocks that left the index and stopped trading have no free prices and are missing (survivorship bias flatters results). News sentiment has no history and is excluded. 3- and 6-month samples overlap; their t-statistics use non-overlapping months only.

## US (209 stocks, 107 month-ends, 2017-11-30 to 2026-09-30)

| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|---|
| 1 month | +0.30% | -0.14% | -0.04% | -0.04% | -0.09% | -0.39% | -0.73 |
| 3 months | +0.02% | +0.09% | +0.08% | -0.05% | -0.14% | -0.16% | -0.04 |
| 6 months | +0.29% | -0.23% | -0.59% | +0.07% | +0.45% | +0.17% | -0.50 |

Q5 beat Q1 in 50% of months (1-month horizon). Top-quintile monthly turnover 36%; estimated net monthly excess return of holding Q5 after costs: -0.16%.

Early trend changes (3303 flags): mean excess return +0.13% at 1 month, +0.29% at 3 months, -0.14% at 6 months.

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

## UK (346 stocks, 107 month-ends, 2017-11-30 to 2026-09-30)

| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|---|
| 1 month | -0.04% | -0.51% | -0.31% | +1.03% | -0.18% | -0.14% | -0.31 |
| 3 months | -0.68% | -1.21% | -0.88% | +3.25% | -0.50% | +0.18% | 0.47 |
| 6 months | -1.33% | -2.32% | -0.44% | +5.19% | -1.12% | +0.21% | 0.85 |

Q5 beat Q1 in 54% of months (1-month horizon). Top-quintile monthly turnover 35%; estimated net monthly excess return of holding Q5 after costs: -0.43%.

Early trend changes (6236 flags): mean excess return -0.40% at 1 month, +1.91% at 3 months, +2.48% at 6 months.

| Year | Mean monthly Q5 − Q1 |
|---|---|
| 2017 | +0.75% |
| 2018 | +0.02% |
| 2019 | +0.63% |
| 2020 | -0.45% |
| 2021 | -1.23% |
| 2022 | -0.21% |
| 2023 | -0.03% |
| 2024 | -0.23% |
| 2025 | +1.20% |
| 2026 | -1.44% |

## Fundamentals (US, 208 companies, 2016-11-30 to 2026-09-30)

Rebuilt at each month-end from SEC filings published by then (point in time). Per-share figures are put on today's split basis and prices are adjusted back for later dividends. Higher quintile = more checks passed / cheaper / less growth priced in.

| Measure | Horizon | Q1 | Q3 | Q5 | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|
| Profile (30 checks) | 1 month | +0.34% | +0.02% | +0.04% | -0.29% | -0.95 |
|  | 3 months | +1.31% | -0.27% | -0.27% | -1.58% | -1.15 |
|  | 6 months | +3.67% | -0.65% | -0.86% | -4.53% | -2.63 |
| Price below DCF | 1 month | +0.03% | +0.23% | +0.04% | +0.02% | 0.04 |
|  | 3 months | +0.04% | +0.20% | -0.20% | -0.24% | -0.15 |
|  | 6 months | +0.11% | +0.29% | -0.64% | -0.74% | -0.60 |
| Low implied growth | 1 month | +0.05% | -0.28% | -0.01% | -0.06% | -0.12 |
|  | 3 months | +0.30% | -0.71% | -0.12% | -0.42% | -0.43 |
|  | 6 months | +0.61% | -1.35% | -0.43% | -1.04% | -0.67 |
| Value | 1 month | -0.07% | +0.01% | +0.09% | +0.15% | 0.41 |
|  | 3 months | -0.01% | -0.06% | +0.07% | +0.08% | 0.54 |
|  | 6 months | +0.18% | -0.23% | -0.09% | -0.27% | -0.26 |
| Growth | 1 month | -0.01% | -0.10% | +0.15% | +0.17% | 0.52 |
|  | 3 months | -0.17% | +0.10% | +0.25% | +0.42% | 0.59 |
|  | 6 months | +0.35% | +0.01% | +0.61% | +0.26% | 0.47 |
| Track record | 1 month | +0.12% | -0.01% | -0.05% | -0.18% | -0.61 |
|  | 3 months | +0.69% | +0.05% | -0.05% | -0.74% | -0.78 |
|  | 6 months | +2.10% | -0.62% | -0.04% | -2.14% | -1.46 |
| Health | 1 month | -0.18% | -0.08% | +0.18% | +0.36% | 1.20 |
|  | 3 months | -0.36% | -0.14% | +0.66% | +1.02% | 0.81 |
|  | 6 months | -0.28% | -0.94% | +1.12% | +1.40% | 0.19 |
| Dividends | 1 month | +0.52% | -0.21% | -0.23% | -0.75% | -1.78 |
|  | 3 months | +1.59% | -0.49% | -0.95% | -2.54% | -1.85 |
|  | 6 months | +3.24% | -1.12% | -2.12% | -5.36% | -2.24 |

