# US fixtures (BRIEF Appendix fixtures, §8 M2)

All SEC data is public domain. Fetched once with `scripts/fetch_fixtures.py` (needs `SEC_USER_AGENT`); tests never
touch the network. Don't hand-edit fetched files: re-fetch, or regenerate from the scripts named below.

| Dir | Fixture | What | Made by |
|---|---|---|---|
| `companyfacts/`, `submissions/` | F-US | 8 real companies: AAPL, MSFT, NVDA, CAT, ORCL, PWR, JBL, GEV. Companyfacts trimmed to the `config/signals.yaml` xbrl_map concepts; submissions trimmed to the forms M2 reads (older-filings pages merged into `recent`) | `fetch_fixtures.py f-us` |
| `expected/` | F-US | Expected quarters (8 each) for AAPL, MSFT, CAT from SEC `frame` tags and hand arithmetic (Q4 = FY − Q1 − Q2 − Q3), checked against the published 10-K/10-Q figures | `expected/derive_expected.py` (doesn't import pipeline code) |
| `form4/` | F-F4 | 10 real Form 4 submissions (`.txt`, SGML header + XML): Geron's 2025-02-27 cluster (3 buys), Artivion, Solaris (a 4/A), Marriott Vacations (purchases); AMD, Arista and Take-Two (10b5-1 checkbox; option exercise; gifts, sales, awards); ADI 2022 (10b5-1 only in a footnote) | `fetch_fixtures.py f-f4` |
| `form4/synthetic/` | F-F4 | Synthetic insider cluster for a made-up issuer (CIK 0009999901): 2 unplanned buys ≥ $25k within 60 days totalling $274k, a checkbox-planned buy, a footnote-planned joint filing, a small buy and a sale | `form4/synthetic/generate.py` |
| `13f/` | F-13F | A slice of the 01dec2024–28feb2025 Form 13F data set: 200 seeded 13F-HR filers, 15 RESTATEMENT and 5 NEW HOLDINGS amendments (with the originals they amend), 5 13F-NT notices; holdings kept for the CUSIPs whose majority issuer name is one of ~60 names (F-US, capex desk, others, ETF/ADR noise), filers' mislabels included | `fetch_fixtures.py f-13f` |
| `13f/expected_*.csv` | F-13F | Holder counts per CUSIP (period 2024-12-31) and a hand-reviewed CUSIP → company sample (66 rows) | `13f/derive_expected.py` (doesn't import pipeline code) |
| `events/` | M2-04 | EDGAR daily master indexes for 2025-03-03/04 (25 noise rows each + 5 companies), submissions for 4 of them (NT 10-K ×3, an 8-K 4.01), GE Vernova's Form 10 (spin-off parent) | `fetch_fixtures.py f-events` |
