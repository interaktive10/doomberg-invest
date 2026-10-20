# Signal Lab report

**Read this first (BRIEF §7):**

1. No signal set reliably beats the market. The Lab exists to find out, and most signals will fail out of sample. That's useful information, not a bug.
2. **Survivorship bias:** the free US price file may miss delisted companies, so Lab results are an optimistic upper bound.
3. Lab returns exclude dividends (v1), taxes and costs.
4. The reverse DCF is a rough lens (one growth rate, generic discount rates). It ranks expectations; it doesn't value companies.

**No run yet: no Lab prices yet: lab-prices.yml downloads them from Twelve Data into the `lab-data-v1` release (us_month_prices.csv.gz) with no human step.**

`lab-prices.yml` runs Sunday to Thursday in November and December 2026 (about 8 runs of 90 minutes, 650 credits each) and dispatches the first run of `lab.yml` once every ticker is done. That run replaces this file (through a PR) with the statistics per signal, horizon and period, the Evidence and Gap deciles, and the §4.10.5 weight proposals; the weights PR gives each signal one verdict (works, unproven or hurts; S7-S12 not testable yet). The Lab's machinery is checked on the synthetic F-LAB panel (`tests/lab`, `make verify-m8`):

- the planted signal is found out of sample (t_nw ≥ 3);
- the noise signal isn't (|t_nw| < 2);
- moving the planted filings 400 days later removes the effect, because the panel reads point in time.
