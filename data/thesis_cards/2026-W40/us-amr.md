# Alpha Metallurgical Resources, Inc. (AMR) — 2026-W40

Two directors, one also a major holder through related entities, bought heavily in August and September 2026 while revenue was still falling and the operating margin was negative. The order book has risen from a low base and the company holds net cash. This reads as a bet on a coal-cycle turn; the fundamental evidence is thin.

## Facts
- Trailing-twelve-month revenue was $2.065 billion, 12.9% below a year earlier [m:revenue_ttm] [m:revenue_ttm_yoy].
- The trailing-twelve-month operating margin was -2.2% [m:op_margin_ttm].
- Cash was $307.6 million against total debt of $3.0 million at 2026-06-30 [m:cash:2026-06-30] [m:total_debt:2026-06-30].
- Remaining performance obligations rose to $124.4 million at 2026-06-30 from $35.9 million a year earlier [m:rpo:2026-06-30] [m:rpo:2025-06-30].
- The order-book signal S1 fired at strength 1.0, with RPO covering 6.0% of trailing revenue against 1.5% a year earlier [s:S1].
- A reporting group led by director Michael Gorzynski, with MG Capital Management and Continental General entities, bought 10,000 shares for $2.09 million on 2026-08-21 [m:insider:a51f2291-513f-46aa-a0ac-d6181cec84d4].
- Director Kenneth S. Courtis bought on several days between 2026-08-21 and 2026-09-08, including 9,935 shares for $2.10 million on 2026-08-21 [m:insider:3baa18f6-ebb6-4ec3-87b0-8980fdb08d58].
- The insider signal S7 fired at strength 1.0: 2 insiders bought a combined 12.6 million worth of stock [s:S7].

## Why it may be mispriced
- Two directors bought heavily while the trailing operating margin was negative [s:S7] [m:op_margin_ttm].
- The trailing one-year return was 1.1%, at the 44.4th percentile of the 409-company comparison set, so the stock has not run up [c:C3].

## Inferences
- Inference: the insider buying is the strongest evidence here; revenue is shrinking and the business is loss-making, so the buyers look to be betting on a turn rather than reacting to one.
- Inference: RPO is a small share of revenue, so S1 at full strength overstates how much future revenue is contracted.
- Inference: the evidence-growth input to C2 leans on the same RPO jump, so the expectations gap and the order-book signal are not independent evidence.
- Inference: at this margin and the floor sales-to-capital ratio C2 uses, the reverse DCF values growth negatively, so its comparison of implied and evidence growth reads backwards here and is not evidence of mispricing.

## Assumptions
- Assumption: coal prices and volumes stop falling within the next few quarters.
- Assumption: the company keeps its net cash while it waits for the cycle, rather than spending it on a large acquisition.
- Assumption: the large holder's buying is a view on value; a push for control or a change in capital allocation would be a different thesis.

## Risks
- RPO covers a small share of revenue, so the order-book signal can swing on a few contracts [s:S1] [m:rpo:2026-06-30].
- C1 puts EV/sales at the 69.5th percentile of the company's own 363-week history: the stock is not cheap against itself [c:C1].
- Operating losses: the June 2026 quarter's operating loss was $10.5 million [m:op_income:2026-06-30].
- Free cash flow can't be checked because capital expenditure is missing from the pack, so R6 is unknown [s:R6].
- C2 is unreliable here (see the inferences) and news attention (C4) is missing, so the Gap score rests mainly on C1, which is unfavourable, and C3 [c:C2] [c:C4] [c:gap].

## Kill criteria
| Metric | Condition | Check after | Why |
|---|---|---|---|
| `m:rpo_yoy` | < 0 | 2026-11-20 | An order book shrinking year over year removes the fundamental half of the evidence. |
| `m:op_margin_ttm` | < -0.05 | 2026-11-20 | Losses wider than 5% of revenue would mean the cycle is still turning down. |
| `m:net_debt` | > 0 | 2026-11-20 | Losing the net cash cushion while loss-making changes the risk of waiting for a turn. |

## Read next
- [Alpha Metallurgical Resources: 10-Q and 10-K filings on EDGAR](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001704715&type=10-Q&dateb=&owner=include&count=40)
- [Alpha Metallurgical Resources: insider (Form 4) filings on EDGAR](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001704715&type=4&dateb=&owner=include&count=40)
