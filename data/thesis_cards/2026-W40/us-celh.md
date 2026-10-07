# Celsius Holdings, Inc. (CELH) — 2026-W40

Celsius more than doubled its quarterly revenue in one step in 2025 and now produces solid free cash flow, yet the stock fell by more than half over the trailing year and institutional holders are thinning. The chief executive and two directors bought in September 2026. Margins are thin and the history is distorted by the step change.

## Facts
- Revenue rose to $739.3 million in the quarter ended 2025-06-30 from $329.3 million in the quarter ended 2025-03-31 [m:revenue:2025-06-30] [m:revenue:2025-03-31].
- Total debt went from 0 at 2024-12-31 to $871.9 million at 2025-06-30 [m:total_debt:2024-12-31] [m:total_debt:2025-06-30].
- Revenue in the quarter ended 2026-06-30 was $817.9 million, 10.6% above the same quarter a year earlier [m:revenue:2026-06-30] [m:revenue_q_yoy].
- Trailing-twelve-month free cash flow was $462.8 million and net debt was $43.6 million [m:fcf_ttm] [m:net_debt].
- Cash conversion was 3.94, up from 1.79 a year earlier, and S4 fired at strength 1.0 [s:S4].
- Chief executive John Fieldly bought 18,000 shares for $493,843 on 2026-09-10 [m:insider:ad9de4ed-30ce-4186-a908-e9eacb8a27a8].
- Director Damon DeSantis bought 20,000 shares for $553,000 on 2026-09-14 and 16,000 shares for $447,200 on 2026-09-15, and director Hal Kravitz bought 12,000 shares for $336,000 on 2026-09-15 [m:insider:5439d105-ef3f-4078-8c0d-d8700d12d5f5] [m:insider:c821fb73-d40f-4cff-aee8-8cfe329e351b] [m:insider:0316ba7c-0cde-4867-9edb-a90991af0f42].
- Institutional holders fell to 572 at 2026-03-31 from 613 at 2025-09-30 [m:inst_holders:2026-03-31] [m:inst_holders:2025-09-30].

## Why it may be mispriced
- The trailing one-year return was -54.4%, at the 4th percentile of the 409-company comparison set [c:C3].
- C1 puts EV/EBIT of 42.5 at the 25.1st percentile of the company's own 517-week history [c:C1].
- S7 fired at strength 0.89 with 3 insiders buying after the fall [s:S7].

## Inferences
- Inference: revenue more than doubled in one quarter while debt and equity rose, which is consistent with an acquisition; the latest quarter's year-over-year growth is the better guide to the combined business.
- Inference: EV/sales sits at the bottom of its own history partly because the revenue base changed, so EV/EBIT is the more useful comparison.
- Inference: institutional holders leaving while insiders buy suggests the market has lost interest faster than management has.

## Assumptions
- Assumption: year-over-year revenue growth stays positive through 2027.
- Assumption: the operating margin recovers from its thin trailing level as one-off costs fade.
- Assumption: free cash flow keeps servicing the debt without new share issuance.

## Risks
- The trailing operating margin is thin, at 5.3% [m:op_margin_ttm].
- Quarterly cash flow is volatile: operating cash flow was -$119.4 million in the December 2025 quarter [m:cfo:2025-12-31].
- Institutional holders are falling, so the shares may stay out of favour [m:inst_holders:2026-03-31].
- C2 found no implied growth rate and C4 is missing, so the Gap score rests on C1 and C3 [c:C2] [c:C4].

## Kill criteria
| Metric | Condition | Check after | Why |
|---|---|---|---|
| `m:revenue_q_yoy` | < 0 | 2026-11-20 | A year-over-year decline on the combined base would end the growth part of the case. |
| `m:fcf_ttm` | < 200000000 | 2026-11-20 | Free cash flow is what makes the debt manageable. |
| `m:op_margin_ttm` | < 0.03 | 2026-11-20 | A margin below 3% would mean costs are not normalising. |

## Read next
- [Celsius Holdings: 10-Q and 10-K filings on EDGAR](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001341766&type=10-Q&dateb=&owner=include&count=40)
- [Celsius Holdings: insider (Form 4) filings on EDGAR](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001341766&type=4&dateb=&owner=include&count=40)
