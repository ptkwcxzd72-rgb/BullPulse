# BullPulse validation report

Generated 2026-10-29. Price-only composite (50% trend, 50% momentum percentiles within each market); weights fixed in advance. Returns are forward excess returns over the equal-weight average of the same market.

**Caveats.** Each month counts only stocks in their index at the time (point-in-time S&P 500 membership; UK stocks count throughout, as no free history exists). Stocks that left the index and stopped trading have no free prices and are missing (survivorship bias flatters results). News sentiment has no history and is excluded. 3- and 6-month samples overlap; their t-statistics use non-overlapping months only.

## US (209 stocks, 106 month-ends, 2017-11-30 to 2026-08-31)

| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|---|
| 1 month | +0.26% | -0.15% | -0.05% | -0.05% | -0.02% | -0.28% | -0.54 |
| 3 months | +0.01% | +0.12% | +0.06% | -0.06% | -0.13% | -0.13% | -0.07 |
| 6 months | +0.28% | -0.29% | -0.61% | +0.07% | +0.53% | +0.25% | -0.34 |

Q5 beat Q1 in 51% of months (1-month horizon). Top-quintile monthly turnover 36%; estimated net monthly excess return of holding Q5 after costs: -0.09%.

Early trend changes (3271 flags): mean excess return +0.16% at 1 month, +0.25% at 3 months, -0.14% at 6 months.

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
| 2026 | +1.98% |

## UK (338 stocks, 106 month-ends, 2017-11-30 to 2026-08-28)

| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|---|
| 1 month | -0.14% | -0.47% | -0.31% | +1.07% | -0.14% | +0.01% | 0.02 |
| 3 months | -0.91% | -1.31% | -0.79% | +3.42% | -0.38% | +0.53% | 0.39 |
| 6 months | -1.44% | -2.64% | -1.74% | +3.85% | +2.02% | +3.46% | -0.19 |

Q5 beat Q1 in 58% of months (1-month horizon). Top-quintile monthly turnover 32%; estimated net monthly excess return of holding Q5 after costs: -0.36%.

Early trend changes (6539 flags): mean excess return -0.47% at 1 month, +0.27% at 3 months, +0.87% at 6 months.

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
| 2026 | -0.70% |

## Fundamentals (US, 208 companies, 2016-10-31 to 2026-08-31)

Rebuilt at each month-end from SEC filings published by then (point in time). Per-share figures are put on today's split basis and prices are adjusted back for later dividends. Higher quintile = more checks passed / cheaper / less growth priced in.

| Measure | Horizon | Q1 | Q3 | Q5 | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|
| Profile (30 checks) | 1 month | +0.33% | +0.00% | +0.03% | -0.30% | -0.97 |
|  | 3 months | +1.16% | -0.24% | -0.25% | -1.41% | -2.01 |
|  | 6 months | +3.38% | -0.64% | -0.82% | -4.20% | -2.62 |
| Price below DCF | 1 month | -0.01% | +0.20% | +0.11% | +0.12% | 0.29 |
|  | 3 months | -0.14% | +0.24% | -0.04% | +0.10% | -0.51 |
|  | 6 months | -0.08% | +0.37% | -0.37% | -0.29% | 0.07 |
| Low implied growth | 1 month | +0.02% | -0.26% | +0.00% | -0.02% | -0.05 |
|  | 3 months | +0.17% | -0.62% | -0.08% | -0.25% | -0.33 |
|  | 6 months | +0.28% | -1.06% | -0.31% | -0.59% | -0.01 |
| Value | 1 month | -0.08% | -0.05% | +0.10% | +0.18% | 0.52 |
|  | 3 months | -0.12% | -0.20% | +0.17% | +0.28% | -0.17 |
|  | 6 months | -0.06% | -0.57% | +0.02% | +0.08% | -0.05 |
| Growth | 1 month | -0.02% | -0.13% | +0.19% | +0.22% | 0.70 |
|  | 3 months | -0.17% | +0.05% | +0.31% | +0.49% | 0.32 |
|  | 6 months | +0.38% | +0.01% | +0.69% | +0.31% | 0.39 |
| Track record | 1 month | +0.14% | -0.01% | -0.03% | -0.17% | -0.59 |
|  | 3 months | +0.72% | +0.07% | -0.03% | -0.75% | -1.15 |
|  | 6 months | +2.07% | -0.57% | +0.02% | -2.05% | -1.44 |
| Health | 1 month | -0.18% | -0.11% | +0.24% | +0.41% | 1.43 |
|  | 3 months | -0.31% | -0.16% | +0.66% | +0.98% | 0.75 |
|  | 6 months | -0.25% | -0.96% | +1.07% | +1.32% | 0.66 |
| Dividends | 1 month | +0.56% | -0.19% | -0.27% | -0.83% | -2.01 |
|  | 3 months | +1.59% | -0.45% | -0.96% | -2.56% | -2.39 |
|  | 6 months | +3.24% | -0.96% | -2.10% | -5.35% | -2.08 |

