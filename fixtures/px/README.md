# F-PX (BRIEF §9): weekly prices, synthetic stand-ins

`make_px.py` generates ten synthetic series (fixed seeds) in two formats:

- `<symbol>_w.csv`: the manual price import's weekly CSV (`imports/us_prices/`, read by `pipeline/prices/bars.py`;
  `Date,Open,High,Low,Close,Volume`, the format Stooq's weekly CSV had, a bar dated at its week's last trading day, no
  Volume column for the ^spx index).
- `twelvedata/<SYMBOL>.json`: the same series as Twelve Data's `time_series` answers them (`interval=1week`), which
  the weekly run asks since 2026-10 (docs/SPEC_ISSUES.md 38): newest first, each bar dated at its week's Monday,
  prices as decimal strings. `SPY.json` carries the ^spx series (the client asks SPY for the S&P 500);
  `not_found.json`, `minute_credits.json` and `bad_key.json` are three of its error answers.
- `twelvedata/daily_*.json`: hand-made in the shape of Twelve Data's `interval=1day` answer, which the Signal Lab's
  price history asks (docs/SPEC_ISSUES.md 51): `daily_AAPL.json` holds a few days of 2010 and of 2026-09/10 (newest
  first, so the month-end close and the incomplete current month can be checked), and `daily_day_credits.json` is
  the answer once the day's 800 credits are spent.

`jbl` carries an unadjusted 2:1 drop in week 150 for the unconfirmed-jump test. Twelve Data is the only price source
(docs/SPEC_ISSUES.md 52) and needs a key the build container doesn't have, so the series are synthetic.
