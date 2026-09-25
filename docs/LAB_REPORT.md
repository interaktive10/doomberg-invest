# Signal Lab report

**Read this first (BRIEF §7):**

1. No signal set reliably beats the market. The Lab exists to find out, and most signals will fail out of sample. That's useful information, not a bug.
2. **Survivorship bias:** the free US price file may miss delisted companies, so Lab results are an optimistic upper bound.
3. Lab returns exclude dividends (v1), taxes and costs.
4. The reverse DCF is a rough lens (one growth rate, generic discount rates). It ranks expectations; it doesn't value companies.

**No run yet: BLOCKED(human: the Stooq bulk file d_us_txt.zip is not attached to the `lab-data` release; download it once from stooq.com (it has a CAPTCHA) and attach it, BRIEF §2.7).**

The first run of `lab.yml` replaces this file (through a PR) with the statistics per signal, horizon and period, the Evidence and Gap deciles, and the §4.10.5 weight proposals. The Lab's machinery is checked on the synthetic F-LAB panel (`tests/lab`, `make verify-m8`):

- the planted signal is found out of sample (t_nw ≥ 3);
- the noise signal isn't (|t_nw| < 2);
- moving the planted filings 400 days later removes the effect, because the panel reads point in time.
