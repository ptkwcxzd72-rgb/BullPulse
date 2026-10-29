# Index membership history

Used to fix survivorship and look-ahead bias in the backtests and the learning: at each past
month-end, a stock only counts if it was in its index at that date. Without this, a company that
joined the S&P 500 in 2023 after a big rise (say) would appear in the 2018 sample, flattering
every test.

- `sp500_membership.csv`: S&P 500 membership intervals (ticker, start_date, end_date; empty end
  = still a member) from [fja05680/sp500](https://github.com/fja05680/sp500), MIT licence,
  copyright (c) 2019-2020 Farrell J. Aultman. Updated by hand from that repository.
- `sp500_aliases.csv`: ticker changes for companies in the universe (the source records a
  change of symbol as a removal and an addition).

Limits: companies that left the index and stopped trading have no free price history, so they
are still missing from the tests. No free history of FTSE 100/250 membership has been found, so UK
stocks count as members throughout; from now on `data/history/membership.csv` records every
change in the universe files as it happens.
