# Embecta Corp. (EMBC) — 2026-W40

Embecta earns high margins and returns on capital, but revenue is shrinking, debt is heavy and equity is negative. The stock fell about 60% over the trailing year and four officers and directors bought on the same day in August 2026. This is a leveraged value case: the equity is a thin slice of the enterprise value.

## Facts
- Trailing-twelve-month revenue was $1.019 billion, 7.6% below a year earlier [m:revenue_ttm] [m:revenue_ttm_yoy].
- Revenue in the quarter ended 2026-06-30 was $271.7 million, down 8.1% year over year [m:revenue:2026-06-30] [m:revenue_q_yoy].
- The trailing operating margin was 21.9% and ROIC was 28.3% [m:op_margin_ttm] [m:roic].
- Net debt was $1.24 billion and shareholders' equity was -$612.7 million at 2026-06-30 [m:net_debt] [m:equity:2026-06-30].
- Total debt rose to $1.455 billion at 2026-06-30 from $1.326 billion at 2026-03-31 [m:total_debt:2026-06-30] [m:total_debt:2026-03-31]. Over the same quarter, shares outstanding fell to 56.66 million from 59.33 million [m:shares_outstanding:2026-06-30] [m:shares_outstanding:2026-03-31].
- Cash conversion was 1.99, up from 1.61 a year earlier, and S4 fired at strength 1.0 [s:S4].
- On 2026-08-12 chief executive Devdatt Kurdikar bought 30,000 shares for $140,937 and director Robert J. Hombach bought 45,000 shares for $223,848 [m:insider:ee85cce1-215e-453d-b21c-601787a3cb23] [m:insider:1a6e7c98-9d8d-476c-821d-f12d13f10e0f].
- The chief financial officer and the chief legal officer bought 20,000 shares each the same day, and S7 fired at strength 0.82 with 4 insiders [m:insider:eb63bed3-4997-46f3-ab46-12a890dbc429] [m:insider:ed2f15e5-9078-48b9-b84f-1e4d33583ba3] [s:S7].

## Why it may be mispriced
- The trailing one-year return was -60.5%, at the 2nd percentile of the 409-company comparison set [c:C3].
- C1 puts EV/EBIT of 6.98 at the 16.4th percentile and EV/sales of 1.53 around the 10th percentile of the company's own 237-week history [c:C1].

## Inferences
- Inference: the business earns high returns on capital but is shrinking and carries heavy debt, so small changes in operating results move the equity value a lot.
- Inference: four officers and directors buying on the same day after a large fall suggests they see the decline as overdone.
- Inference: the negative C2 comes from a reverse DCF run at the floor of its sales-to-capital range, which makes any growth look expensive, so it is weak evidence either way.

## Assumptions
- Assumption: the revenue decline slows rather than speeds up.
- Assumption: the company can refinance or reduce its debt on acceptable terms.
- Assumption: the operating margin holds near its current level while revenue declines.

## Risks
- Heavy leverage: net debt of $1.24 billion against negative equity [m:net_debt] [m:equity:2026-06-30].
- Revenue is shrinking year over year [m:revenue_ttm_yoy] [m:revenue_q_yoy].
- C2 is negative: the enterprise value implies 9.2% annual growth against -5.5% from the evidence formula [c:C2].
- Trailing free cash flow can't be computed because one quarter's capital expenditure is missing, so R6 is unknown [s:R6] [m:fcf_ttm].
- Debt rose in the latest quarter while the share count fell [m:total_debt:2026-06-30] [m:shares_outstanding:2026-06-30].

## Kill criteria
| Metric | Condition | Check after | Why |
|---|---|---|---|
| `m:revenue_ttm_yoy` | < -0.12 | 2027-01-05 | A faster decline would mean the base erodes faster than the debt can be paid down. |
| `m:op_margin_ttm` | < 0.15 | 2027-01-05 | The equity case depends on margins holding while revenue falls. |
| `m:net_debt` | > 1400000000 | 2027-01-05 | Rising net debt while revenue falls would leave the equity with little room. |

## Read next
- [Embecta: 10-Q and 10-K filings on EDGAR](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001872789&type=10-Q&dateb=&owner=include&count=40)
- [Embecta: insider (Form 4) filings on EDGAR](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001872789&type=4&dateb=&owner=include&count=40)
