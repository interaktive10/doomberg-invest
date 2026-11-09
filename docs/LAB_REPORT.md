# Signal Lab report

**Read this first (BRIEF §7):**

1. No signal set reliably beats the market. The Lab exists to find out, and most signals will fail out of sample. That's useful information, not a bug.
2. **Survivorship bias:** the free US price file may miss delisted companies, so Lab results are an optimistic upper bound.
3. Lab returns exclude dividends (v1), taxes and costs.
4. The reverse DCF is a rough lens (one growth rate, generic discount rates). It ranks expectations; it doesn't value companies.

## Run
- Market: us. Prices: Twelve Data month-end closes (us_month_prices.csv.gz, kept in the database).
- Population: the §1.3 universe as of each month-end: 1478 companies with a structural exclusion (SPAC, fund, royalty/grantor trust, foreign private issuer, no listed common stock or no public common equity) are left out, and each month keeps the companies with a 10-K/10-Q filed in the last 460 days and TTM revenue of at least $50M, as known then (never today's universe flag). Listing status and market cap aren't applied (today's listing would add survivorship bias; market cap is a candidate-stage rule).
- Months: 2010-01 to 2026-10; 2789 companies, 300374 company-months, 69316 events (first fire per company in 12 months).
- Periods (by event month): in-sample 2012-01 to 2018-12, out-of-sample 2019-01 to 2025-12.
- Excess = forward price return minus the equal-weighted mean of the month's population priced at both dates. t (NW) is the Newey-West t-stat of the mean excess (lags = horizon months) with its standard error floored at the plain standard error, so it is never larger than the plain t (docs/SPEC_ISSUES.md 19); lab_results notes keep the unfloored value.

## Signals
| Signal | Horizon | Period | N | Mean excess | Median | Hit rate | P10 | t (NW) |
|---|---|---|---|---|---|---|---|---|
| L1 | 12m | in-sample | 9081 | -8.6% | -9.8% | 37% | -57.8% | -1.32 |
| L1 | 12m | out-of-sample | 13603 | -2.4% | -10.1% | 39% | -67.5% | -0.74 |
| L1 | 24m | in-sample | 9078 | -8.8% | -17.0% | 36% | -75.2% | -1.98 |
| L1 | 24m | out-of-sample | 11322 | -27.3% | -27.4% | 32% | -114.7% | -1.23 |
| L1 | 36m | in-sample | 9077 | -6.5% | -25.5% | 34% | -93.1% | -2.45 |
| L1 | 36m | out-of-sample | 9153 | -70.4% | -46.3% | 28% | -174.6% | -1.45 |
| L2 | 12m | in-sample | 15 | +46.4% | +0.3% | 53% | -41.1% | 1.33 |
| L2 | 12m | out-of-sample | 140 | +34.1% | -5.7% | 47% | -66.9% | 1.57 |
| L2 | 24m | in-sample | 15 | +95.3% | +56.2% | 80% | -41.6% | 2.35 |
| L2 | 24m | out-of-sample | 122 | +89.8% | -16.0% | 47% | -110.8% | 1.86 |
| L2 | 36m | in-sample | 15 | +113.1% | +26.8% | 53% | -44.8% | 2.11 |
| L2 | 36m | out-of-sample | 105 | +96.4% | -39.3% | 39% | -136.6% | 2.17 |
| L3 | 12m | in-sample | 1871 | -9.5% | -7.5% | 39% | -47.1% | -2.00 |
| L3 | 12m | out-of-sample | 3004 | -5.6% | -8.3% | 40% | -57.2% | -1.39 |
| L3 | 24m | in-sample | 1870 | -11.1% | -13.9% | 36% | -63.8% | -2.63 |
| L3 | 24m | out-of-sample | 2552 | -25.5% | -21.3% | 35% | -105.0% | -1.26 |
| L3 | 36m | in-sample | 1869 | -15.7% | -22.6% | 34% | -85.1% | -2.80 |
| L3 | 36m | out-of-sample | 2195 | -32.1% | -41.0% | 29% | -159.4% | -0.99 |
| L4 | 12m | in-sample | 1205 | -6.9% | -6.9% | 40% | -52.1% | -1.32 |
| L4 | 12m | out-of-sample | 2936 | -7.5% | -11.2% | 38% | -66.8% | -1.26 |
| L4 | 24m | in-sample | 1204 | -7.2% | -10.9% | 41% | -70.6% | -1.58 |
| L4 | 24m | out-of-sample | 2315 | -53.1% | -29.5% | 32% | -158.6% | -1.25 |
| L4 | 36m | in-sample | 1204 | -8.0% | -19.0% | 38% | -90.7% | -1.55 |
| L4 | 36m | out-of-sample | 1903 | -117.2% | -51.3% | 27% | -504.5% | -1.35 |
| L5 | 12m | in-sample | 1118 | -8.1% | -12.9% | 39% | -63.8% | -1.27 |
| L5 | 12m | out-of-sample | 1388 | +11.2% | -12.9% | 40% | -70.4% | 3.00 |
| L5 | 24m | in-sample | 1118 | -3.6% | -21.1% | 37% | -84.2% | -0.66 |
| L5 | 24m | out-of-sample | 1156 | -1.5% | -30.7% | 37% | -118.7% | -0.10 |
| L5 | 36m | in-sample | 1118 | +8.8% | -25.9% | 37% | -102.8% | 0.84 |
| L5 | 36m | out-of-sample | 928 | -50.2% | -58.2% | 27% | -177.2% | -1.33 |
| L6 | 12m | in-sample | 7615 | -10.2% | -9.5% | 38% | -55.5% | -1.72 |
| L6 | 12m | out-of-sample | 11347 | -7.0% | -10.9% | 38% | -66.6% | -1.77 |
| L6 | 24m | in-sample | 7613 | -10.3% | -16.1% | 37% | -72.9% | -2.62 |
| L6 | 24m | out-of-sample | 9512 | -36.7% | -28.3% | 31% | -112.1% | -1.47 |
| L6 | 36m | in-sample | 7611 | -9.7% | -24.5% | 35% | -92.6% | -4.34 |
| L6 | 36m | out-of-sample | 7747 | -82.9% | -48.7% | 26% | -170.4% | -1.63 |
| S1 | 12m | in-sample | 0 | – | – | – | – | – |
| S1 | 12m | out-of-sample | 474 | +1.4% | -6.7% | 43% | -62.5% | 0.27 |
| S1 | 24m | in-sample | 0 | – | – | – | – | – |
| S1 | 24m | out-of-sample | 382 | +2.8% | -12.1% | 44% | -102.5% | 0.10 |
| S1 | 36m | in-sample | 0 | – | – | – | – | – |
| S1 | 36m | out-of-sample | 296 | -14.0% | -20.5% | 42% | -144.0% | -0.26 |
| S2 | 12m | in-sample | 98 | -10.1% | -9.3% | 39% | -49.3% | -1.29 |
| S2 | 12m | out-of-sample | 295 | -4.3% | -11.6% | 37% | -64.6% | -0.84 |
| S2 | 24m | in-sample | 98 | -4.0% | -12.9% | 41% | -69.9% | -0.54 |
| S2 | 24m | out-of-sample | 254 | -16.6% | -30.7% | 34% | -102.1% | -1.03 |
| S2 | 36m | in-sample | 98 | +8.9% | -18.1% | 38% | -87.6% | 0.69 |
| S2 | 36m | out-of-sample | 187 | -48.1% | -42.7% | 28% | -190.2% | -1.40 |
| S3 | 12m | in-sample | 1060 | -9.9% | -7.4% | 41% | -60.1% | -1.19 |
| S3 | 12m | out-of-sample | 2135 | +2.0% | -8.9% | 41% | -62.2% | 0.65 |
| S3 | 24m | in-sample | 1060 | -5.3% | -12.1% | 40% | -75.2% | -0.78 |
| S3 | 24m | out-of-sample | 1743 | -12.0% | -17.2% | 37% | -99.9% | -0.64 |
| S3 | 36m | in-sample | 1060 | +4.8% | -18.6% | 39% | -93.1% | 1.18 |
| S3 | 36m | out-of-sample | 1392 | -54.8% | -36.2% | 31% | -144.8% | -1.52 |
| S4 | 12m | in-sample | 601 | -10.6% | -7.1% | 42% | -54.7% | -1.27 |
| S4 | 12m | out-of-sample | 1455 | -11.6% | -11.8% | 35% | -62.6% | -1.64 |
| S4 | 24m | in-sample | 601 | -9.8% | -10.3% | 40% | -67.4% | -1.46 |
| S4 | 24m | out-of-sample | 1243 | -39.1% | -29.5% | 30% | -100.8% | -1.54 |
| S4 | 36m | in-sample | 601 | -10.2% | -21.6% | 37% | -78.7% | -2.64 |
| S4 | 36m | out-of-sample | 975 | -75.9% | -45.0% | 26% | -159.1% | -1.53 |
| S5 | 12m | in-sample | 696 | -11.9% | -7.7% | 38% | -61.2% | -1.72 |
| S5 | 12m | out-of-sample | 1786 | -6.2% | -9.4% | 40% | -66.5% | -1.73 |
| S5 | 24m | in-sample | 696 | -8.9% | -12.6% | 39% | -74.3% | -1.29 |
| S5 | 24m | out-of-sample | 1481 | -28.1% | -25.1% | 33% | -113.1% | -1.16 |
| S5 | 36m | in-sample | 696 | -9.3% | -17.3% | 39% | -89.3% | -1.33 |
| S5 | 36m | out-of-sample | 1190 | -77.3% | -50.5% | 29% | -223.8% | -1.44 |
| S6 | 12m | in-sample | 55 | -17.6% | -19.3% | 29% | -57.4% | -3.62 |
| S6 | 12m | out-of-sample | 184 | +3.8% | -1.0% | 47% | -47.2% | 0.65 |
| S6 | 24m | in-sample | 55 | -21.9% | -28.7% | 25% | -68.6% | -4.05 |
| S6 | 24m | out-of-sample | 161 | -19.5% | -12.1% | 40% | -85.4% | -1.23 |
| S6 | 36m | in-sample | 55 | -36.3% | -44.9% | 20% | -97.8% | -5.00 |
| S6 | 36m | out-of-sample | 135 | -47.5% | -35.0% | 30% | -109.9% | -2.03 |
| S7 | 12m | in-sample | 0 | – | – | – | – | – |
| S7 | 12m | out-of-sample | 0 | – | – | – | – | – |
| S7 | 24m | in-sample | 0 | – | – | – | – | – |
| S7 | 24m | out-of-sample | 0 | – | – | – | – | – |
| S7 | 36m | in-sample | 0 | – | – | – | – | – |
| S7 | 36m | out-of-sample | 0 | – | – | – | – | – |
| S8 | 12m | in-sample | 0 | – | – | – | – | – |
| S8 | 12m | out-of-sample | 0 | – | – | – | – | – |
| S8 | 24m | in-sample | 0 | – | – | – | – | – |
| S8 | 24m | out-of-sample | 0 | – | – | – | – | – |
| S8 | 36m | in-sample | 0 | – | – | – | – | – |
| S8 | 36m | out-of-sample | 0 | – | – | – | – | – |
| S9 | 12m | in-sample | 0 | – | – | – | – | – |
| S9 | 12m | out-of-sample | 2 | -84.1% | -84.1% | 0% | -88.1% | -16.70 |
| S9 | 24m | in-sample | 0 | – | – | – | – | – |
| S9 | 24m | out-of-sample | 0 | – | – | – | – | – |
| S9 | 36m | in-sample | 0 | – | – | – | – | – |
| S9 | 36m | out-of-sample | 0 | – | – | – | – | – |
| S10 | 12m | in-sample | 0 | – | – | – | – | – |
| S10 | 12m | out-of-sample | 0 | – | – | – | – | – |
| S10 | 24m | in-sample | 0 | – | – | – | – | – |
| S10 | 24m | out-of-sample | 0 | – | – | – | – | – |
| S10 | 36m | in-sample | 0 | – | – | – | – | – |
| S10 | 36m | out-of-sample | 0 | – | – | – | – | – |
| S12 | 12m | in-sample | 0 | – | – | – | – | – |
| S12 | 12m | out-of-sample | 0 | – | – | – | – | – |
| S12 | 24m | in-sample | 0 | – | – | – | – | – |
| S12 | 24m | out-of-sample | 0 | – | – | – | – | – |
| S12 | 36m | in-sample | 0 | – | – | – | – | – |
| S12 | 36m | out-of-sample | 0 | – | – | – | – | – |

## Evidence deciles (company-months)
| Signal | Horizon | Period | N | Mean excess | Median | Hit rate | P10 | t (NW) |
|---|---|---|---|---|---|---|---|---|
| EVIDENCE_D1 | 12m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D1 | 12m | out-of-sample | 0 | – | – | – | – | – |
| EVIDENCE_D1 | 24m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D1 | 24m | out-of-sample | 0 | – | – | – | – | – |
| EVIDENCE_D1 | 36m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D1 | 36m | out-of-sample | 0 | – | – | – | – | – |
| EVIDENCE_D2 | 12m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D2 | 12m | out-of-sample | 0 | – | – | – | – | – |
| EVIDENCE_D2 | 24m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D2 | 24m | out-of-sample | 0 | – | – | – | – | – |
| EVIDENCE_D2 | 36m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D2 | 36m | out-of-sample | 0 | – | – | – | – | – |
| EVIDENCE_D3 | 12m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D3 | 12m | out-of-sample | 0 | – | – | – | – | – |
| EVIDENCE_D3 | 24m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D3 | 24m | out-of-sample | 0 | – | – | – | – | – |
| EVIDENCE_D3 | 36m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D3 | 36m | out-of-sample | 0 | – | – | – | – | – |
| EVIDENCE_D4 | 12m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D4 | 12m | out-of-sample | 51575 | +0.4% | -10.4% | 39% | -59.8% | 0.40 |
| EVIDENCE_D4 | 24m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D4 | 24m | out-of-sample | 38893 | -0.3% | -21.7% | 35% | -85.4% | -0.17 |
| EVIDENCE_D4 | 36m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D4 | 36m | out-of-sample | 18103 | -0.3% | -24.2% | 35% | -98.7% | -0.10 |
| EVIDENCE_D5 | 12m | in-sample | 83328 | +1.8% | -7.9% | 40% | -58.2% | 0.43 |
| EVIDENCE_D5 | 12m | out-of-sample | 81392 | +0.9% | -12.2% | 37% | -67.4% | 0.36 |
| EVIDENCE_D5 | 24m | in-sample | 83304 | +1.3% | -13.3% | 38% | -76.1% | 0.39 |
| EVIDENCE_D5 | 24m | out-of-sample | 71836 | +7.2% | -35.6% | 29% | -135.0% | 0.42 |
| EVIDENCE_D5 | 36m | in-sample | 83282 | +0.5% | -21.9% | 36% | -92.2% | 0.32 |
| EVIDENCE_D5 | 36m | out-of-sample | 71840 | +15.1% | -58.8% | 25% | -217.1% | 0.42 |
| EVIDENCE_D6 | 12m | in-sample | 10370 | +0.0% | -20.0% | 26% | -52.3% | 0.00 |
| EVIDENCE_D6 | 12m | out-of-sample | 0 | – | – | – | – | – |
| EVIDENCE_D6 | 24m | in-sample | 10370 | +0.0% | -28.2% | 27% | -73.6% | 0.00 |
| EVIDENCE_D6 | 24m | out-of-sample | 0 | – | – | – | – | – |
| EVIDENCE_D6 | 36m | in-sample | 10370 | +0.0% | -35.6% | 29% | -101.9% | 0.00 |
| EVIDENCE_D6 | 36m | out-of-sample | 0 | – | – | – | – | – |
| EVIDENCE_D7 | 12m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D7 | 12m | out-of-sample | 68 | -3.7% | -9.2% | 35% | -39.1% | -0.92 |
| EVIDENCE_D7 | 24m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D7 | 24m | out-of-sample | 68 | +9.4% | -19.2% | 37% | -53.4% | 0.64 |
| EVIDENCE_D7 | 36m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D7 | 36m | out-of-sample | 68 | +7.5% | -23.4% | 29% | -82.4% | 0.33 |
| EVIDENCE_D8 | 12m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D8 | 12m | out-of-sample | 2071 | -2.2% | -4.8% | 43% | -45.9% | -1.09 |
| EVIDENCE_D8 | 24m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D8 | 24m | out-of-sample | 1888 | -2.5% | -8.0% | 43% | -68.0% | -0.50 |
| EVIDENCE_D8 | 36m | in-sample | 0 | – | – | – | – | – |
| EVIDENCE_D8 | 36m | out-of-sample | 1231 | +6.8% | -9.6% | 43% | -73.5% | 2.32 |
| EVIDENCE_D9 | 12m | in-sample | 3076 | -14.8% | -7.3% | 41% | -73.8% | -1.31 |
| EVIDENCE_D9 | 12m | out-of-sample | 13162 | -3.9% | -10.1% | 40% | -62.3% | -1.29 |
| EVIDENCE_D9 | 24m | in-sample | 3076 | -9.6% | -10.4% | 41% | -81.5% | -1.01 |
| EVIDENCE_D9 | 24m | out-of-sample | 10527 | -19.8% | -25.5% | 33% | -104.0% | -1.39 |
| EVIDENCE_D9 | 36m | in-sample | 3076 | -4.9% | -16.5% | 38% | -84.7% | -1.25 |
| EVIDENCE_D9 | 36m | out-of-sample | 7891 | -58.3% | -44.6% | 28% | -157.7% | -1.67 |
| EVIDENCE_D10 | 12m | in-sample | 9031 | -11.2% | -7.8% | 40% | -59.7% | -1.50 |
| EVIDENCE_D10 | 12m | out-of-sample | 16967 | -2.2% | -8.6% | 40% | -58.1% | -0.68 |
| EVIDENCE_D10 | 24m | in-sample | 9031 | -8.3% | -12.8% | 39% | -73.6% | -1.37 |
| EVIDENCE_D10 | 24m | out-of-sample | 14155 | -20.7% | -23.6% | 34% | -104.5% | -1.10 |
| EVIDENCE_D10 | 36m | in-sample | 9031 | -2.8% | -20.6% | 36% | -88.6% | -0.99 |
| EVIDENCE_D10 | 36m | out-of-sample | 11429 | -54.8% | -40.1% | 30% | -160.9% | -1.29 |

## Gap deciles (company-months)
| Signal | Horizon | Period | N | Mean excess | Median | Hit rate | P10 | t (NW) |
|---|---|---|---|---|---|---|---|---|
| GAP_D1 | 12m | in-sample | 6782 | -11.8% | -8.3% | 40% | -64.3% | -1.32 |
| GAP_D1 | 12m | out-of-sample | 12767 | -0.7% | -7.7% | 41% | -60.7% | -0.14 |
| GAP_D1 | 24m | in-sample | 6778 | -6.6% | -13.5% | 39% | -78.1% | -0.73 |
| GAP_D1 | 24m | out-of-sample | 10593 | -20.6% | -26.5% | 33% | -107.2% | -0.91 |
| GAP_D1 | 36m | in-sample | 6774 | +3.7% | -18.3% | 39% | -89.6% | 0.43 |
| GAP_D1 | 36m | out-of-sample | 8466 | -65.6% | -49.3% | 27% | -167.7% | -1.45 |
| GAP_D2 | 12m | in-sample | 6785 | -11.4% | -5.8% | 42% | -58.3% | -1.26 |
| GAP_D2 | 12m | out-of-sample | 12776 | -5.4% | -8.8% | 39% | -57.3% | -1.11 |
| GAP_D2 | 24m | in-sample | 6780 | -10.2% | -10.8% | 40% | -72.8% | -1.45 |
| GAP_D2 | 24m | out-of-sample | 10594 | -26.7% | -25.6% | 30% | -103.9% | -1.24 |
| GAP_D2 | 36m | in-sample | 6780 | -6.4% | -17.5% | 38% | -85.0% | -2.47 |
| GAP_D2 | 36m | out-of-sample | 8478 | -68.4% | -46.2% | 26% | -160.5% | -1.55 |
| GAP_D3 | 12m | in-sample | 6781 | -10.3% | -5.1% | 44% | -57.6% | -1.13 |
| GAP_D3 | 12m | out-of-sample | 12764 | -5.3% | -8.7% | 39% | -57.0% | -1.31 |
| GAP_D3 | 24m | in-sample | 6780 | -8.6% | -8.2% | 42% | -72.4% | -1.18 |
| GAP_D3 | 24m | out-of-sample | 10572 | -27.6% | -25.4% | 31% | -102.1% | -1.42 |
| GAP_D3 | 36m | in-sample | 6773 | -3.6% | -15.8% | 39% | -83.9% | -1.30 |
| GAP_D3 | 36m | out-of-sample | 8479 | -69.0% | -44.6% | 26% | -159.5% | -1.64 |
| GAP_D4 | 12m | in-sample | 6791 | -10.3% | -4.8% | 43% | -56.4% | -1.17 |
| GAP_D4 | 12m | out-of-sample | 12769 | -6.0% | -9.4% | 39% | -58.1% | -1.54 |
| GAP_D4 | 24m | in-sample | 6789 | -7.4% | -8.5% | 43% | -70.7% | -1.04 |
| GAP_D4 | 24m | out-of-sample | 10587 | -29.0% | -25.5% | 32% | -105.3% | -1.55 |
| GAP_D4 | 36m | in-sample | 6787 | -1.6% | -15.6% | 40% | -83.8% | -0.65 |
| GAP_D4 | 36m | out-of-sample | 8467 | -66.4% | -42.3% | 29% | -164.0% | -1.59 |
| GAP_D5 | 12m | in-sample | 6767 | +6.7% | -5.6% | 42% | -56.9% | 0.54 |
| GAP_D5 | 12m | out-of-sample | 12758 | -4.6% | -9.9% | 39% | -58.9% | -1.99 |
| GAP_D5 | 24m | in-sample | 6767 | +8.3% | -9.0% | 42% | -72.3% | 0.80 |
| GAP_D5 | 24m | out-of-sample | 10573 | -23.5% | -25.9% | 32% | -105.9% | -1.56 |
| GAP_D5 | 36m | in-sample | 6767 | +6.5% | -18.4% | 38% | -86.6% | 1.18 |
| GAP_D5 | 36m | out-of-sample | 8462 | -60.1% | -44.3% | 28% | -164.5% | -1.55 |
| GAP_D6 | 12m | in-sample | 6803 | +32.8% | -7.1% | 40% | -58.7% | 1.16 |
| GAP_D6 | 12m | out-of-sample | 12796 | -1.3% | -10.0% | 39% | -58.9% | -0.64 |
| GAP_D6 | 24m | in-sample | 6802 | +28.0% | -13.0% | 38% | -74.4% | 1.32 |
| GAP_D6 | 24m | out-of-sample | 10615 | -20.1% | -26.1% | 31% | -105.8% | -1.68 |
| GAP_D6 | 36m | in-sample | 6801 | +8.6% | -22.5% | 36% | -89.4% | 0.90 |
| GAP_D6 | 36m | out-of-sample | 8487 | -53.3% | -43.3% | 28% | -164.7% | -1.56 |
| GAP_D7 | 12m | in-sample | 6781 | +52.8% | -8.6% | 39% | -59.5% | 1.12 |
| GAP_D7 | 12m | out-of-sample | 12771 | -4.7% | -11.6% | 38% | -59.3% | -2.29 |
| GAP_D7 | 24m | in-sample | 6777 | +37.1% | -13.3% | 37% | -74.1% | 1.17 |
| GAP_D7 | 24m | out-of-sample | 10579 | -25.8% | -27.7% | 31% | -106.8% | -1.70 |
| GAP_D7 | 36m | in-sample | 6772 | +9.7% | -24.1% | 36% | -91.8% | 0.73 |
| GAP_D7 | 36m | out-of-sample | 8469 | -59.1% | -45.6% | 28% | -161.2% | -1.52 |
| GAP_D8 | 12m | in-sample | 6796 | -12.7% | -8.9% | 39% | -61.3% | -1.49 |
| GAP_D8 | 12m | out-of-sample | 12771 | +8.4% | -11.8% | 37% | -61.9% | 0.76 |
| GAP_D8 | 24m | in-sample | 6792 | -11.5% | -15.0% | 37% | -79.0% | -1.89 |
| GAP_D8 | 24m | out-of-sample | 10592 | -1.0% | -28.4% | 32% | -108.0% | -0.07 |
| GAP_D8 | 36m | in-sample | 6789 | -11.4% | -26.0% | 35% | -97.8% | -2.64 |
| GAP_D8 | 36m | out-of-sample | 8471 | -27.2% | -46.2% | 29% | -163.8% | -0.88 |
| GAP_D9 | 12m | in-sample | 6778 | -2.7% | -9.2% | 39% | -64.8% | -0.70 |
| GAP_D9 | 12m | out-of-sample | 12768 | -2.7% | -12.8% | 37% | -63.1% | -1.21 |
| GAP_D9 | 24m | in-sample | 6777 | -3.5% | -16.3% | 36% | -81.2% | -1.13 |
| GAP_D9 | 24m | out-of-sample | 10588 | -17.9% | -28.7% | 33% | -110.4% | -1.37 |
| GAP_D9 | 36m | in-sample | 6777 | -7.2% | -29.3% | 33% | -99.7% | -2.83 |
| GAP_D9 | 36m | out-of-sample | 8480 | -51.4% | -46.8% | 28% | -167.2% | -1.39 |
| GAP_D10 | 12m | in-sample | 6796 | -8.1% | -12.5% | 37% | -75.0% | -1.00 |
| GAP_D10 | 12m | out-of-sample | 12762 | +12.5% | -13.9% | 39% | -70.9% | 2.19 |
| GAP_D10 | 24m | in-sample | 6796 | -7.8% | -22.8% | 34% | -91.7% | -1.40 |
| GAP_D10 | 24m | out-of-sample | 10594 | +21.2% | -31.3% | 35% | -118.3% | 1.23 |
| GAP_D10 | 36m | in-sample | 6794 | +1.3% | -37.5% | 31% | -110.5% | 0.17 |
| GAP_D10 | 36m | out-of-sample | 8473 | +0.2% | -51.7% | 31% | -174.4% | 0.00 |

## Weight proposals (BRIEF §4.10.5)
Each signal's verdict (the weights PR's too): works, hurts, unproven (not shown, not wrong) or not testable yet. The report is written on every run, also when no weight changes and no weights PR is opened.

| Weight | Verdict | Now | Proposed | Why |
|---|---|---|---|---|
| signals.S1 | unproven | 1.0 | 1.0 | OOS insignificant (mean +0.0135, t_nw 0.27) |
| signals.S2 | unproven | 1.0 | 1.0 | OOS insignificant (mean -0.0426, t_nw -0.84) |
| signals.S3 | unproven | 1.0 | 1.0 | OOS insignificant (mean +0.0200, t_nw 0.65) |
| signals.S4 | unproven | 1.0 | 1.0 | OOS insignificant (mean -0.1163, t_nw -1.64) |
| signals.S5 | unproven | 1.0 | 1.0 | OOS insignificant (mean -0.0623, t_nw -1.73) |
| signals.S6 | unproven | 1.0 | 1.0 | OOS insignificant (mean +0.0380, t_nw 0.65) |
| signals.S7 | not testable yet | 1.0 | 1.0 | not testable yet: no history before 2026 (config/lab.yaml not_testable) |
| signals.S8 | not testable yet | 1.0 | 1.0 | not testable yet: no history before 2026 (config/lab.yaml not_testable) |
| signals.S9 | not testable yet | 1.0 | 1.0 | not testable yet: no history before 2026 (config/lab.yaml not_testable) |
| signals.S10 | not testable yet | 1.0 | 1.0 | not testable yet: no history before 2026 (config/lab.yaml not_testable) |
| signals.S11 | not testable yet | 1.0 | 1.0 | not testable yet: no history before 2026 (config/lab.yaml not_testable) |
| signals.S12 | not testable yet | 1.0 | 1.0 | not testable yet: no history before 2026 (config/lab.yaml not_testable) |
| legacy.L1 | unproven | 0.0 | 0.0 | OOS insignificant (mean -0.0245, t_nw -0.74) |
| legacy.L2 | unproven | 0.0 | 0.0 | OOS insignificant (mean +0.3407, t_nw 1.57) |
| legacy.L3 | unproven | 0.0 | 0.0 | OOS insignificant (mean -0.0565, t_nw -1.39) |
| legacy.L4 | unproven | 0.0 | 0.0 | OOS insignificant (mean -0.0752, t_nw -1.26) |
| legacy.L5 | unproven | 0.0 | 0.0 | OOS mean +0.1120, t_nw 3.00 >= 2, but in-sample mean -0.0811 has the opposite sign |
| legacy.L6 | unproven | 0.0 | 0.0 | OOS insignificant (mean -0.0699, t_nw -1.77) |

Weights change only through a PR with the `human-approved` label (config/weights.yaml is protected).
