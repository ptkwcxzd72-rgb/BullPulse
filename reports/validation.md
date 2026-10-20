# BullPulse validation report

Generated 2026-10-20. Price-only composite (50% trend, 50% momentum percentiles within each market); weights fixed in advance. Returns are forward excess returns over the equal-weight average of the same market.

**Caveats.** The universe is today's index members, so stocks that were delisted or dropped from the index are missing (survivorship bias flatters results). News sentiment has no history and is excluded. 3- and 6-month samples overlap; their t-statistics use non-overlapping months only.

## US (40 stocks, 106 month-ends, 2017-11-30 to 2026-08-31)

| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|---|
| 1 month | +0.34% | -0.44% | +0.05% | -0.33% | +0.38% | +0.04% | 0.05 |
| 3 months | +0.26% | -0.51% | -0.27% | -0.74% | +1.25% | +0.99% | 0.73 |
| 6 months | +1.62% | -1.10% | -1.84% | -2.06% | +3.39% | +1.76% | 0.21 |

Q5 beat Q1 in 55% of months (1-month horizon). Top-quintile monthly turnover 36%; estimated net monthly excess return of holding Q5 after costs: +0.31%.

Early trend changes (794 flags): mean excess return -0.12% at 1 month, +0.51% at 3 months, +0.65% at 6 months.

| Year | Mean monthly Q5 − Q1 |
|---|---|
| 2017 | +4.55% |
| 2018 | -2.14% |
| 2019 | -0.98% |
| 2020 | +3.66% |
| 2021 | -2.49% |
| 2022 | -0.64% |
| 2023 | -0.53% |
| 2024 | +2.47% |
| 2025 | -0.35% |
| 2026 | +0.86% |

## Fundamentals (US, 40 companies, 2016-10-31 to 2026-08-31)

Rebuilt at each month-end from SEC filings published by then (point in time). Per-share figures are put on today's split basis and prices are adjusted back for later dividends. Higher quintile = more checks passed / cheaper / less growth priced in.

| Measure | Horizon | Q1 | Q3 | Q5 | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|
| Profile (30 checks) | 1 month | +0.35% | +0.06% | -0.25% | -0.61% | -1.27 |
|  | 3 months | +1.29% | -0.38% | -0.89% | -2.17% | -1.17 |
|  | 6 months | +2.83% | -1.08% | -1.18% | -4.00% | -0.41 |
| Price below DCF | 1 month | +0.27% | -0.23% | -0.11% | -0.38% | -0.72 |
|  | 3 months | +1.12% | -0.82% | -0.63% | -1.75% | -1.77 |
|  | 6 months | +2.79% | -1.03% | -1.79% | -4.58% | -1.72 |
| Low implied growth | 1 month | +0.56% | -0.35% | -0.05% | -0.61% | -0.93 |
|  | 3 months | +1.36% | -1.04% | -0.64% | -2.00% | -1.36 |
|  | 6 months | +2.71% | -2.32% | -2.31% | -5.01% | -1.11 |
| Value | 1 month | +0.53% | +0.08% | -0.68% | -1.20% | -2.08 |
|  | 3 months | +0.99% | +0.42% | -2.00% | -2.99% | -2.02 |
|  | 6 months | +2.30% | +0.27% | -3.57% | -5.86% | -1.39 |
| Growth | 1 month | +0.33% | -0.20% | -0.01% | -0.34% | -0.67 |
|  | 3 months | +0.57% | -1.46% | +0.45% | -0.12% | 0.42 |
|  | 6 months | +0.49% | -2.55% | +1.65% | +1.16% | 0.69 |
| Track record | 1 month | +0.23% | -0.29% | +0.41% | +0.18% | 0.35 |
|  | 3 months | +0.90% | -0.98% | +1.14% | +0.25% | 0.55 |
|  | 6 months | +1.42% | -1.83% | +1.96% | +0.54% | 1.13 |
| Health | 1 month | -0.19% | -0.20% | +0.51% | +0.71% | 1.27 |
|  | 3 months | -0.31% | -0.50% | +1.18% | +1.49% | 1.16 |
|  | 6 months | -0.05% | -1.49% | +3.09% | +3.14% | 1.16 |
| Dividends | 1 month | +0.51% | +0.09% | -0.25% | -0.75% | -1.20 |
|  | 3 months | +1.79% | -0.63% | -0.63% | -2.42% | -1.56 |
|  | 6 months | +4.84% | -0.98% | -2.12% | -6.95% | -2.25 |

