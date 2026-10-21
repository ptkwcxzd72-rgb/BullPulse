# BullPulse validation report

Generated 2026-10-21. Price-only composite (50% trend, 50% momentum percentiles within each market); weights fixed in advance. Returns are forward excess returns over the equal-weight average of the same market.

**Caveats.** The universe is today's index members, so stocks that were delisted or dropped from the index are missing (survivorship bias flatters results). News sentiment has no history and is excluded. 3- and 6-month samples overlap; their t-statistics use non-overlapping months only.

## US (209 stocks, 106 month-ends, 2017-11-30 to 2026-08-31)

| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|---|
| 1 month | +0.06% | -0.18% | -0.13% | -0.08% | +0.33% | +0.27% | 0.50 |
| 3 months | -0.32% | -0.26% | -0.12% | -0.14% | +0.86% | +1.19% | 0.70 |
| 6 months | -0.26% | -1.01% | -1.05% | +0.14% | +2.21% | +2.47% | 0.49 |

Q5 beat Q1 in 53% of months (1-month horizon). Top-quintile monthly turnover 36%; estimated net monthly excess return of holding Q5 after costs: +0.26%.

Early trend changes (3634 flags): mean excess return +0.18% at 1 month, +0.25% at 3 months, +0.00% at 6 months.

| Year | Mean monthly Q5 − Q1 |
|---|---|
| 2017 | -1.74% |
| 2018 | -0.79% |
| 2019 | +0.35% |
| 2020 | +0.05% |
| 2021 | -1.49% |
| 2022 | -0.02% |
| 2023 | -0.02% |
| 2024 | +2.13% |
| 2025 | +0.88% |
| 2026 | +2.43% |

## UK (99 stocks, 106 month-ends, 2017-11-30 to 2026-08-28)

| Horizon | Q1 (lowest) | Q2 | Q3 | Q4 | Q5 (highest) | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|---|
| 1 month | +0.19% | -0.29% | -0.10% | +0.13% | +0.07% | -0.12% | -0.22 |
| 3 months | +0.07% | -0.69% | -0.09% | +0.12% | +0.60% | +0.53% | 0.32 |
| 6 months | -0.08% | -1.65% | -0.24% | +0.30% | +1.73% | +1.81% | 0.43 |

Q5 beat Q1 in 55% of months (1-month horizon). Top-quintile monthly turnover 34%; estimated net monthly excess return of holding Q5 after costs: -0.17%.

Early trend changes (1973 flags): mean excess return -0.12% at 1 month, -0.37% at 3 months, -0.38% at 6 months.

| Year | Mean monthly Q5 − Q1 |
|---|---|
| 2017 | +0.94% |
| 2018 | -0.39% |
| 2019 | +0.58% |
| 2020 | +0.27% |
| 2021 | -1.96% |
| 2022 | -1.69% |
| 2023 | +1.18% |
| 2024 | -0.12% |
| 2025 | +2.33% |
| 2026 | -2.08% |

## Fundamentals (US, 208 companies, 2016-10-31 to 2026-08-31)

Rebuilt at each month-end from SEC filings published by then (point in time). Per-share figures are put on today's split basis and prices are adjusted back for later dividends. Higher quintile = more checks passed / cheaper / less growth priced in.

| Measure | Horizon | Q1 | Q3 | Q5 | Q5 − Q1 | t-stat |
|---|---|---|---|---|---|---|
| Profile (30 checks) | 1 month | +0.32% | -0.01% | +0.03% | -0.29% | -0.94 |
|  | 3 months | +1.15% | -0.27% | -0.24% | -1.39% | -2.02 |
|  | 6 months | +3.37% | -0.63% | -0.81% | -4.19% | -2.62 |
| Price below DCF | 1 month | -0.00% | +0.20% | +0.11% | +0.11% | 0.28 |
|  | 3 months | -0.12% | +0.24% | -0.01% | +0.11% | -0.50 |
|  | 6 months | -0.06% | +0.31% | -0.35% | -0.29% | 0.12 |
| Low implied growth | 1 month | +0.02% | -0.28% | +0.01% | -0.02% | -0.04 |
|  | 3 months | +0.17% | -0.63% | -0.08% | -0.25% | -0.33 |
|  | 6 months | +0.28% | -1.09% | -0.33% | -0.61% | -0.03 |
| Value | 1 month | -0.07% | -0.04% | +0.11% | +0.18% | 0.50 |
|  | 3 months | -0.06% | -0.19% | +0.18% | +0.24% | -0.26 |
|  | 6 months | -0.01% | -0.56% | +0.02% | +0.03% | -0.09 |
| Growth | 1 month | -0.02% | -0.12% | +0.19% | +0.21% | 0.68 |
|  | 3 months | -0.17% | +0.05% | +0.31% | +0.49% | 0.32 |
|  | 6 months | +0.38% | +0.01% | +0.69% | +0.31% | 0.39 |
| Track record | 1 month | +0.14% | -0.02% | -0.03% | -0.17% | -0.58 |
|  | 3 months | +0.72% | +0.07% | -0.03% | -0.75% | -1.15 |
|  | 6 months | +2.07% | -0.57% | +0.02% | -2.05% | -1.44 |
| Health | 1 month | -0.18% | -0.11% | +0.23% | +0.41% | 1.41 |
|  | 3 months | -0.31% | -0.16% | +0.66% | +0.98% | 0.75 |
|  | 6 months | -0.25% | -0.96% | +1.07% | +1.32% | 0.66 |
| Dividends | 1 month | +0.56% | -0.19% | -0.27% | -0.82% | -1.99 |
|  | 3 months | +1.59% | -0.44% | -0.96% | -2.55% | -2.38 |
|  | 6 months | +3.24% | -0.97% | -2.09% | -5.34% | -2.05 |

