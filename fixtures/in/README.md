# India fixtures — F-IN (BRIEF Appendix fixtures, §8 M3)

Real NSE/BSE files, fetched with `scripts/fetch_fixtures.py f-in` (patient: NSE's CDN refuses bursts from data-centre
IPs, so the fetcher cools down and retries). Tests never touch the network. Don't hand-edit fetched files.

| Path | What |
|---|---|
| `bhavcopy/BhavCopy_NSE_CM_…_20260605_F_0000.csv.zip` | NSE CM-UDiFF common bhavcopy, Friday 2026-06-05 (M3-01) |
| `bhavcopy/BhavCopy_BSE_CM_…_20260605_F_0000.CSV` | BSE's bhavcopy for the same day, same format (the fallback, M3-05) |
| `securities/EQUITY_L.csv`, `asm.json`, `gsm.json` | NSE securities list (EQ universe) and the ASM/GSM surveillance lists (2026-09-25) |
| `results/KEI_FY2026Q{2,3,4}_consolidated.xml` | KEI Industries' integrated-filing results XBRL (SEBI `in-capmkt` taxonomy): Q2 and Q4 carry the half-yearly balance sheet and cash flow (M3-02) |
| `results/KEI_FY2026Q3_standalone.xml`, `KEI_FY2027Q1_standalone*.xml` | the consolidated-vs-standalone rule, and an original + revision |
| `results/legacy_VSTTILLERS_FY2025Q3.xml` | a legacy results filing (`in-bse-fin` taxonomy, before integrated filing) |
| `results/index_KEI.json` | NSE's integrated-filing listing for KEI (creation times = filed_at) |
| `results/expected_KEI.csv` | expected fundamentals_q rows, from `results/derive_expected.py` (doesn't import pipeline code) |
| `shareholding/SHP_{KEI,JSWSTEEL,JPPOWER}_2026-06-30.xml`, `index.json` | shareholding patterns: none / 11.6% / 73% of the promoter holding pledged (M3-03) |
| `pit/pit.json`, `pit/pit.csv` | NSE's insider-trading index (API `corporates-pit-gg` and the page's CSV): 2,865 disclosures, May–Sep 2026 |
| `pit/disclosures/*.xml` | 17 disclosure XBRLs (every 170th of the index): promoter market purchases and sales, gifts, transfers, conversions, ESOPs, a director's sale (M3-04) |
| `pit/Insider_Trading.xml` | the insider-trading RSS feed |
| `announcements/announcements.json` | 20 corporate announcements (2026-09-25) |
| `announcements/announcements_2026-09-19.csv` | the announcements page's "Download (.csv)" for Saturday 2026-09-19 (185 rows): the manual import (review F4) |
| `shareholding/shareholding_page.csv` | the shareholding page's CSV (quarter 2026-06-30), trimmed by the fetcher to KEI, JSW Steel, JP Power, Bhageria and every 100th row (27 rows) |

