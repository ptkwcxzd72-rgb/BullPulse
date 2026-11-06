# BullPulse validation report

Generated 2026-11-06. Price-only composite (50% trend, 50% momentum percentiles within each market); weights fixed in advance. Returns are forward excess returns over the equal-weight average of the same market.

**Caveats.** Each month counts only stocks in their index at the time (point-in-time S&P 500 membership; UK stocks count throughout, as no free history exists). Stocks that left the index and stopped trading have no free prices and are missing (survivorship bias flatters results). News sentiment has no history and is excluded. 3- and 6-month samples overlap; their t-statistics use non-overlapping months only.

## US (498 stocks, 107 month-ends, 2017-11-30 to 2026-09-30)

| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|---|
| 1 month | +0.30% | -0.06% | -0.11% | -0.13% | -0.01% | -0.31% | -0.61 |
| 3 months | +0.33% | -0.01% | -0.18% | -0.17% | +0.02% | -0.31% | -0.33 |
| 6 months | +0.85% | -0.11% | -0.74% | -0.34% | +0.34% | -0.52% | -0.91 |

Q5 beat Q1 in 51% of months (1-month horizon). Top-quintile monthly turnover 36%; estimated net monthly excess return of holding Q5 after costs: -0.08%.

Early trend changes (8123 flags): mean excess return +0.02% at 1 month, +0.10% at 3 months, -0.18% at 6 months.

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
| 2026 | +0.54% |

## UK (346 stocks, 107 month-ends, 2017-11-30 to 2026-09-30)

| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|---|
| 1 month | -0.06% | -0.49% | -0.31% | +1.03% | -0.17% | -0.11% | -0.24 |
| 3 months | -0.69% | -1.19% | -0.83% | +3.18% | -0.49% | +0.21% | 0.50 |
| 6 months | -1.33% | -2.22% | -0.42% | +5.06% | -1.12% | +0.21% | 0.69 |

Q5 beat Q1 in 56% of months (1-month horizon). Top-quintile monthly turnover 34%; estimated net monthly excess return of holding Q5 after costs: -0.41%.

Early trend changes (6366 flags): mean excess return -0.43% at 1 month, +1.80% at 3 months, +2.31% at 6 months.

| Year | Mean monthly Q5 − Q1 |
|---|---|
| 2017 | +0.89% |
| 2018 | -0.02% |
| 2019 | +0.75% |
| 2020 | -0.43% |
| 2021 | -1.15% |
| 2022 | -0.28% |
| 2023 | +0.03% |
| 2024 | -0.14% |
| 2025 | +1.18% |
| 2026 | -1.43% |

## Fundamentals (US, 497 companies, 2016-11-30 to 2026-09-30)

Rebuilt at each month-end from SEC filings published by then (point in time). Per-share figures are put on today's split basis and prices are adjusted back for later dividends. Higher quintile = more checks passed / cheaper / less growth priced in.

| Measure | Horizon | Q1 | Q3 | Q5 | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|
| Profile (30 checks) | 1 month | +0.29% | -0.12% | +0.04% | -0.25% | -0.97 |
|  | 3 months | +1.13% | -0.44% | -0.14% | -1.27% | -1.50 |
|  | 6 months | +3.34% | -1.06% | -0.44% | -3.78% | -2.72 |
| Price below DCF | 1 month | -0.03% | -0.16% | +0.23% | +0.26% | 0.71 |
|  | 3 months | +0.12% | -0.31% | +0.45% | +0.34% | 0.27 |
|  | 6 months | +0.52% | -0.61% | +0.72% | +0.20% | -0.06 |
| Low implied growth | 1 month | +0.10% | -0.25% | +0.16% | +0.06% | 0.14 |
|  | 3 months | +0.52% | -0.49% | +0.19% | -0.33% | -0.34 |
|  | 6 months | +1.12% | -1.07% | +0.25% | -0.87% | -0.42 |
| Value | 1 month | -0.13% | +0.08% | +0.09% | +0.23% | 0.73 |
|  | 3 months | -0.02% | +0.06% | -0.06% | -0.03% | 0.38 |
|  | 6 months | +0.07% | -0.06% | -0.47% | -0.54% | -0.17 |
| Growth | 1 month | +0.09% | -0.18% | +0.25% | +0.17% | 0.62 |
|  | 3 months | +0.06% | -0.16% | +0.70% | +0.63% | 0.87 |
|  | 6 months | +0.31% | -0.14% | +1.27% | +0.96% | 0.69 |
| Track record | 1 month | +0.12% | -0.12% | +0.05% | -0.07% | -0.28 |
|  | 3 months | +0.65% | -0.32% | -0.00% | -0.65% | -0.57 |
|  | 6 months | +2.28% | -0.88% | -0.10% | -2.38% | -1.50 |
| Health | 1 month | -0.16% | -0.05% | +0.15% | +0.31% | 1.30 |
|  | 3 months | -0.34% | -0.04% | +0.46% | +0.80% | 0.60 |
|  | 6 months | -0.46% | -0.59% | +0.95% | +1.41% | 0.58 |
| Dividends | 1 month | +0.53% | -0.13% | -0.19% | -0.72% | -1.94 |
|  | 3 months | +1.77% | -0.35% | -0.78% | -2.55% | -1.86 |
|  | 6 months | +4.02% | -1.01% | -1.71% | -5.73% | -2.28 |

