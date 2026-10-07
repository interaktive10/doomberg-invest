# F-PX (BRIEF §9): weekly prices, synthetic stand-ins

`make_px.py` generates ten synthetic series (fixed seeds) in two formats:

- `<symbol>_w.csv`: Stooq's weekly CSV (`Date,Open,High,Low,Close,Volume`, a bar dated at its week's last trading
  day, no Volume column for the ^spx index). It is the format of a manual price import (`imports/us_prices/`).
- `yahoo/<SYMBOL>.json`: the same series as Yahoo's chart endpoint answers them (`v8/finance/chart`,
  `interval=1wk`), which the weekly run asks for US prices since 2026-10 (docs/SPEC_ISSUES.md 37): each bar stamped
  at its week's Monday midnight, New York time, and prices as single-precision values written as doubles. `AAPL.json`
  also carries Yahoo's quirks (a week of nulls, the week in progress twice); `not_found.json` is Yahoo's answer to a
  symbol it doesn't know (with HTTP 404).

`jbl` carries an unadjusted 2:1 drop in week 150 for the unconfirmed-jump test; `no_data.txt` and `limit.txt` are two
answers Stooq gave instead of a CSV.

Neither stooq.com nor Yahoo answers the build container, so the series are synthetic. Where Yahoo answers, `uv run
python scripts/fetch_fixtures.py f-px` writes the real charts over `yahoo/`.
