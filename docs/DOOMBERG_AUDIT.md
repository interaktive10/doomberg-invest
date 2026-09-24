# Doomberg audit (old repo → Doomberg Invest)

**Source:** `interaktive10/Doomberg` @ `480c1a3` (only commit on the default branch; read-only clone). **Audited:** 2026-09-24 for BRIEF §8 M0.
**References:** every `path:line` points into that commit. Line numbers were checked with `cat -n`, `grep -n` or `sed -n`.
**Manzoor's action (BRIEF §11.2):** read §5 and confirm which `L*` rules go into the Signal Lab. Until the Lab says otherwise, they all start at weight 0 (`config/weights.yaml → legacy`).

---

## 1. Overview

**What Doomberg was.** It was an **alert-only** decision-support app for Manzoor's own intraday trading: Indian index options on Groww, plus crypto perps. It never placed orders.
- Stack: FastAPI, SQLite and a vanilla-JS dashboard, running 24/7 on an Oracle VM in Mumbai.
- It was built on an audit of his own broker fills. The loss was about ₹1 crore over 24 months. The audit concluded the losses were **behavioral** (averaging down, capitulation flips, adding capital mid-loss, fees from churn) and **not directional** (`CLAUDE.md:3-5`, `CLAUDE.md:10-20`, `AGENT_BRIEF.md:14-22`).
- The trading desk was decommissioned on 2026-07-23. After that, **Long Bets** was the only live surface: a slow-money watchlist reviewed twice a week (`doomberg/longbets_review.py:3-6`).

**What carries over is the method, not the code.** These principles held up in the old repo, and the new brief already encodes each one:

| Old principle (source) | Where it lives in Doomberg Invest |
|---|---|
| Alert-only; never place, modify or cancel orders (`CLAUDE.md:88`) | Guard bans broker SDKs and order identifiers (BRIEF Appendix E); no execution anywhere |
| No TA indicators; signals come from *commitments*, not opinions (`CLAUDE.md:90-92`) | Evidence score is price-free (BRIEF §1.2.3); signals are filings, orders, insider buying, ownership |
| Structure beats willpower: assume the user will try to bend the rules in a drawdown (`CLAUDE.md:93-94`) | Weights and thresholds sit in protected paths behind a label (Appendix D); 4-week minimum before a position (§11.9) |
| Measure, then size: shadow first, n ≥ 30, positive lower bound after costs (`CLAUDE.md:95-96`, `doomberg/shadow/engine.py:22-23`, `:281-298`) | Signal Lab: a weight changes only on out-of-sample evidence (§4.10) |
| Honesty: if the data contradicts the belief, say so with numbers (`CLAUDE.md:97-98`) | Lab caveats printed verbatim (§7); a "priced-in" bucket instead of silence (§1.7) |
| The benchmark is "not trading" (₹0), never a flattering baseline (`PLAYBOOK.md:8-12`) | Lab measures excess vs the equal-weighted universe, not raw return (§4.10.1) |
| Disconfirmers written *before* falling in love (`doomberg/data/LONGBETS_PROCESS.md:23`) | Kill criteria are mandatory, observable, metric-based (§4.9) |
| The finder and the approver must not be the same session (`LONGBETS_PROCESS.md:64-65`, `longbets_review.py:14-16`) | Routine writes cards; Manzoor accepts (Research → Thesis); reviewer thread ≠ build thread (§10) |
| Rule edits take effect after 24h; config changes weekend-only (`PLAYBOOK.md:51-52`) | Weight changes only through a labelled PR, reviewed quarterly (§4.10.5, §11.8) |
| The graveyard is the discipline: never silently delete (`LONGBETS_PROCESS.md:41-43`, `doomberg/server.py:893-897`) | `dismissed`/`closed` states with a required reason and post-mortem (§1.8, §4.9) |
| The LLM judges real data; it doesn't recall from memory (`longbets_review.py:151-159`, `:184-189`) | Evidence packs are the only fact source; `validate.py` rejects uncited numbers (§4.9, Appendix F) |

**The honest read.** Long Bets was a well-run *process* on top of an unmeasured *signal*.
- Its idea sources were Yahoo's public screens (`doomberg/longbets_screen.py:39-46`) plus LLM judgment.
- Its only scoreboard was price change since the seed date (`longbets_review.py:102-108`).
- Nothing was point-in-time. Nothing was tested against history. Nothing checked whether a pattern had beaten a baseline. Doomberg Invest keeps the process and replaces the signal layer with one that can be tested (§4.10).

## 2. Data sources used

| Source | What for | Where | Status in Doomberg Invest |
|---|---|---|---|
| Groww Trade API (₹499/mo, TOTP auth) | live positions, orders, margin, option chain | `doomberg/brokers/groww_client.py:22`, `:33-43`; read-only GETs `:78-121` | **Not ported.** Broker connection, paid, and out of scope (BRIEF §1.2.1) |
| NSE option-chain v3 (free, cookie session) | NIFTY OI/IV ladder | `doomberg/brokers/nse_feed.py:23-24`, `:36-62` | Not ported (intraday). The **access pattern** is reused (§4 below) |
| BSE derivatives API (free) | SENSEX chain | `doomberg/brokers/bse_feed.py:25-27`, `:35-57` | Not ported. Header lessons reused for the BSE fallback (§4.3) |
| NSE archives: participant-wise OI CSV | FII/retail positioning flag | `doomberg/brokers/nse_participants.py:20`, `:41-62` | Not ported (derivatives positioning). The `nsearchives` walk-back pattern informs bhavcopy loading |
| Bybit v5 public, Deribit public | crypto price, OI, funding, options | `doomberg/brokers/crypto_feed.py`, `doomberg/brokers/deribit_feed.py` | Not ported (crypto, intraday) |
| Yahoo Finance: predefined screener, v8 chart, v1 search (unauthenticated, undocumented) | Long Bets discovery, prices, sector, USD/INR | `doomberg/longbets_screen.py:35`, `:39-46`, `:163-173`, `:179-193`; `longbets_review.py:73-86`; `doomberg/brokers/market_feed.py:42-48` | **Not ported.** Undocumented, rate-limited (401/429 per `longbets_screen.py:15-21`), and against the free-and-within-terms rule (§1.2.6). Replaced by SEC, NSE, BSE, Stooq and GDELT |
| Hermes (own VPS news brief, key in query string) | news digest | `doomberg/brokers/news_feed.py:48-58`; hosts `doomberg/config.py:41-42` | Not ported. GDELT gives attention (C4) instead |
| Telegram Bot API | alarms to user and "referee" | `doomberg/notify/telegram.py:32`; `doomberg/server.py:1902-1930` | Not ported. The digest is a GitHub issue (§4.12) |
| LLMs: Nous `stepfun/step-3.7-flash:free` (default), Gemini 2.5 Flash-Lite, Anthropic Haiku 4.5, OpenAI gpt-4.1-nano, DeepSeek, local Ollama | judgment, Long Bets discovery and tagging | `doomberg/judgment/brain.py:80-93`; env `doomberg/config.py:26-37` | Free tiers only (Gemini, Groq, OpenRouter). Anthropic and OpenAI endpoints are **banned** at runtime (Appendix E) |
| Own broker exports (Zerodha, Groww, CoinDCX) | the loss audit | `analysis/scripts/*`, `CLAUDE.md:10-13` | Not ported (private data) |

## 3. Long-term / investing logic (every rule, with thresholds)

### 3a. Long Bets: discovery filters (code)
| # | Rule | Threshold | Reference |
|---|---|---|---|
| LB-1 | US market-cap ceiling (hard, code) | ≤ $35B | `doomberg/longbets_screen.py:49`, applied `:108-110` |
| LB-1b | Stated cap rule (prompt/doc): US ≤ ~$25-35B, India ≤ ~₹50,000 cr (~$5-6B); ETFs/crypto exempt; a held name that grows past it is flagged, not killed | — | `longbets_review.py:142`; `LONGBETS_PROCESS.md:26-31`; `doomberg/data/longbets.json:922` |
| LB-2 | Market-cap floor ("un-investable noise") | ≥ $250M | `longbets_screen.py:50`, `:108-110` |
| LB-3 | "Already ripped" exclusion | 52-week change > +80% → drop | `longbets_screen.py:51`, `:111-113`; hard rule 1, `LONGBETS_PROCESS.md:21-22` |
| LB-4 | Near-wipeout exclusion ("broken, not cheap") | 52-week change < −92% → drop | `longbets_screen.py:52`, `:114-116` |
| LB-5 | Never re-propose a known, parked or killed name | set membership | `longbets_screen.py:60-71`, `:105-107`; `longbets_review.py:385-390` |
| LB-6 | Corroboration across screens: rank by the number of screens a name appears on, then by lowest 52-week change | count desc, chg asc | `longbets_screen.py:117-120`, `:137` |
| LB-7 | Idea universes: Yahoo `aggressive_small_caps`, `undervalued_growth_stocks`, `most_shorted_stocks`, `day_losers`, `small_cap_gainers`, `undervalued_large_caps`; 3 screens/run rotated by day, 40 names each | — | `longbets_screen.py:39-46`, `:74-79` |
| LB-8 | Cap bands for filtering | nano < $300M, micro < $2B, small < $10B, mid < $35B, else large | `longbets_screen.py:201-215` |

### 3b. Long Bets: process rules (doc + code)
| # | Rule | Threshold | Reference |
|---|---|---|---|
| LB-9 | Pattern library: **wreckage** = down 70-95%, hated, *surviving* (inflecting FCF, debt falling, buybacks); **theme** = physical demand inflecting while the sector is priced as boring; **narrative** = dormant asset with niche narrative; **scuttlebutt** = own ground truth mapped to a disclosed line item | −70% to −95% (wreckage) | `LONGBETS_PROCESS.md:12-19` |
| LB-10 | Disconfirmers written before adding | mandatory | `LONGBETS_PROCESS.md:23`; stored per entry, e.g. `longbets.json` watchlist `disconfirmers` |
| LB-11 | Verify corporate actions every review (acquisitions, delistings, splits) | every review | `LONGBETS_PROCESS.md:24-25`, `:36-40` |
| LB-12 | Stage discipline: candidate → watch needs verified facts + disconfirmers; watch → act-soon needs a dated catalyst within 2 weeks or extreme dislocation; act-soon > 4 weeks without action decays to watch | 2 weeks; 4 weeks | `LONGBETS_PROCESS.md:44-49` |
| LB-13 | Overnight rule: a new idea can't be promoted in the session that found it; automation only *proposes* | — | `LONGBETS_PROCESS.md:64-65`; `longbets_review.py:14-16`, `:386-417` |
| LB-14 | Automation may kill *candidates* only; watchlist kills are a human act | ≤ 4 kills/run | `longbets_review.py:17-18`, `:145-146`, `:419-428` |
| LB-15 | Sizing: a separate bucket, no leverage, ≤ 10% of the bucket per thesis, every buy manual | 10% | `longbets.json:5`; `LONGBETS_PROCESS.md:7-8` |
| LB-16 | Price flags since seed: ≥ +40% → "re-check the ripped rule"; ≤ −30% → "is the thesis or the market wrong?" | +40% / −30% | `longbets_review.py:45`, `:102-108` |
| LB-17 | Scuttlebutt grading: each observation logged with a falsifiable prediction before the print; 2 consecutive failures from one vantage → stop using it | 2 | `LONGBETS_PROCESS.md:54-57`; log at `longbets.json:905` |
| LB-18 | Review cadence Mon & Thu ≥ 20:00 IST; catch-up if the last review is > 4 days old; hunting Thursdays only, one pattern per week in rotation | 4 days | `longbets_review.py:42-44`, `:449-464`; `LONGBETS_PROCESS.md:59-65` |
| LB-19 | Hunting sources: 52-week-low lists *with positive FCF*, post-crash survivors *with buybacks*, insider-buying clusters, niche narratives, own observations | — | `LONGBETS_PROCESS.md:61-63` |
| LB-20 | LLM grounding: new ideas must be picked **from the screened list** (real numbers attached); at most one India idea from memory, marked `needs_verify` | 0-3 new per run | `longbets_review.py:151-159`, `:184-196`, `:386-417` |
| LB-21 | Controlled theme vocabulary enforced in code (free-text labels broke the filter) | 11 themes | `longbets_review.py:198-201`, `:236-239`, `:309-314`, `:366-371` |
| LB-22 | India practicalities: US names via LRS; crypto 30% flat tax + 1% TDS, no loss offset → higher post-tax bar | — | `LONGBETS_PROCESS.md:74-79` |

### 3c. Validation / process rules from the trading side (method, not strategy)
| # | Rule | Threshold | Reference |
|---|---|---|---|
| PV-1 | Prove-first gate: MEASURING below n = 30; also MEASURING with < 5 losses (loss tail unsampled); PROVEN only if the lower bound mean − 1.645·SE > 0 after costs; else NO EDGE → kill candidate | n ≥ 30, losses ≥ 5, z = 1.6449 | `doomberg/shadow/engine.py:22-23`, `:262`, `:265-298` |
| PV-2 | Auto-bench: a NO EDGE strategy opens no new trades | — | `engine.py:60-78` |
| PV-3 | Inverse test: would the opposite trade have worked? (inv = −net − 2·fee) | — | `engine.py:301-310` |
| PV-4 | Lab discipline: n < 15 → "keep measuring", no tuning; a failure mode counts only at ≥ 3 recurrences; at most one **pre-registered** variant per strategy, run *alongside* the champion ("in-place edits destroy the sample") | 15; 3; 1 | `doomberg/judgment/pressure.py:168-176` |
| PV-5 | Challenger replay must beat the champion's expectancy; a missing result counts as a reject (an earlier bug auto-approved these) | — | `doomberg/server.py:2946-2961`; `doomberg/shadow/replay.py:37-40`, `:76` |
| PV-6 | Pre-register parameters; changing them restarts the clock; verdicts only at the pre-registered n; control arms; pessimistic fills | — | `PLAYBOOK.md:143-148` |
| PV-7 | Regime-study verdict needs ≥ 5 days in each arm; ratio ≥ 1.25 CONFIRMED, ≤ 0.85 INVERTED, else measuring | 5; 1.25; 0.85 | `doomberg/quant/regime_study.py:76-85` |
| PV-8 | Quarter-Kelly only after measured stats (n ≥ 30, LB > 0): f = (p(b+1) − 1)/b, sized at 0.25·f | 0.25 | `doomberg/judgment/dossier.py:103-105`, `:120-123` |
| PV-9 | Rolling expectancy per setup, auto-retire when 20-trade expectancy < 0; win rate alone is uninformative | 20 | `IMPROVEMENTS.md:66-69` |

## 4. What's reusable as code

The stack is different (SQLite, FastAPI and `requests` there; Postgres, GitHub Actions and `httpx` here), so **no module is copied as-is**. Reused as **patterns**:

1. **NSE session handling** (for `pipeline/net/nse.py`, M3):
   - Browser user agent plus `Referer` (`nse_feed.py:19-20`, `:36-43`).
   - Cookie warm-up on an NSE page, re-warmed every 600 s. A forced warm **rebuilds the session** to drop flagged cookies (`nse_feed.py:45-53`).
   - One retry after a re-warm on 401/403 (`nse_feed.py:55-62`).
   - NSE tolerates about 3-4 requests per minute per IP (`nse_feed.py:67-69`). That backs the brief's 1 request per 3 s limit (already in `pipeline/net/http.py`).
2. **BSE API headers:** `Origin` **and** `Referer` = bseindia.com are both required. Numbers arrive as comma-formatted strings, and `""` means untraded (`bse_feed.py:35-39`, `:66-75`). This applies directly to the BSE fallback in §4.3.
3. **Stale beats nothing:** on failure, serve the last good copy and mark it stale (`nse_feed.py:127-136`, `bse_feed.py:136-137`, `market_feed.py:77/94`). This maps to `source_health.stale` plus banners (§2.7).
4. **Walk back to the last available business day** for archive files (`nse_participants.py:46-62`, up to 6 days). Use this for "the Friday bhavcopy" when Friday is a holiday. Fix the old bug: it used the local date, not IST (`nse_participants.py:46-47`).
5. **Atomic JSON writes:** temp file, then `os.replace`, with explicit permissions (`longbets_review.py:440-444`). Use this for the `data/thesis_queue/` and `data/thesis_cards/` writers.
6. **JSON salvage:** take the first valid object via `raw_decode`, not a greedy regex (`doomberg/judgment/brain.py:58-72`). The new router uses pydantic schemas first and this only as a fallback.
7. **Reasoning-model budget lesson:** free "reasoner" models spend the whole `max_tokens` on thinking and return empty content. Use several small calls, not one large one, and keep the budget comfortably above reasoning plus answer (`longbets_review.py:253-263`, `:323-327`). This goes into `config/quotas.yaml` per-prompt budgets (M5).
8. **Controlled vocabulary enforced in code**, never only in the prompt (`longbets_review.py:366-371`). Same idea as the `subject_key` validation in Appendix F.4.7.
9. **Prove-first statistics** (`engine.py:265-298`): the mean − 1.645·SE lower bound and the minimum-losses guard can be a secondary readout next to Newey-West t in `lab/evaluate.py`. It doesn't replace the §4.10 rules.

## 5. Cliché rules → Lab-only `L*` signals

These are the old Long Bets filters that everyone runs (BRIEF §1.1). Several also use **price**, so they can never feed the Evidence score directly (§1.2.3).
- They are implemented in `pipeline/lab/legacy_doomberg.py` (M8) and evaluated exactly like S1-S12.
- Weight 0 until they pass §4.10.5.
- Manzoor confirms this list (§11.2).

| ID | Rule | Old source | Uses price? | Lab definition (point-in-time, month-end) |
|---|---|---|---|---|
| L1 | Not-ripped / not-broken band | LB-3, LB-4 | yes | 12-month return in (−92%, +80%] |
| L2 | Wreckage survivor | LB-9 wreckage | yes | 52-week drawdown from high in [−95%, −70%] **and** TTM FCF > 0 **and** net debt down YoY |
| L3 | Cheap and still growing (`undervalued_growth_stocks`) | LB-7 | yes | trailing P/E in the bottom tercile of the universe **and** revenue YoY > 0 |
| L4 | Near 52-week low with positive FCF | LB-19, LB-7 `day_losers` | yes | price within 10% of the 52-week low **and** TTM FCF > 0 |
| L5 | Small-cap momentum (`small_cap_gainers`, `aggressive_small_caps`) | LB-7 | yes | market cap < $2B **and** 12-month return in the top decile |
| L6 | Size ceiling (mid-cap-and-under) | LB-1, LB-1b, LB-2 | yes | $250M ≤ market cap ≤ $35B (US); ≤ ₹50,000 cr (IN) |

**Not ported as signals:**
- "Multi-screen corroboration" (LB-6) is already the corroboration principle: ≥ 2 families (§1.1.3, §4.8).
- "Insider-buying clusters" (LB-19) is S7.
- "Most shorted" (LB-7) has no free short-interest source in the brief's §2.7, so it is listed in §7 as a gap.

## 6. Trading / execution parts (not ported)

None of these enter Doomberg Invest (BRIEF §1.2.1). I checked: **the old repo never placed orders.**
- There are zero hits for `place_order|modify_order|cancel_order|/order/create|/order/modify|/order/cancel`.
- The Groww client exposes GETs only (`groww_client.py:78-121`).
- `/api/orders` reads history only (`server.py:725`).

Not ported:
- **Intraday options analytics:** GEX/pin/slam regimes (`doomberg/quant/gamma.py:72-146`), implied density (`quant/implied.py:70-128`), OI positioning shape (`quant/positioning.py:39-95`), coil score (`quant/coil.py:19-41`), vol cone (`quant/vol.py:19-60`).
- **Shadow strategies:** S1 Wall-Break 0DTE (`shadow/stock.py:31-302`), crypto S4-S15 (`shadow/strategies.py:33-317`), pinbar detector (`shadow/pin.py:30-130`), exhaustion score (`quant/exhaustion.py:22-63`).
- **Behavioral guardrails for live trading:**
  - infusion detection (`server.py:650-687`)
  - averaging-down detection (`server.py:785-800`)
  - flip detection (`server.py:735-830`)
  - time cage (`server.py:2133-2149`, `:1745-1750`)
  - Telegram referee (`server.py:1922-1924`)
  - THE LAW capital caps and risk-per-trade (`judgment/dossier.py:90-105`)
- **Recorders and loops:** chain, crypto and ledger recorders, and 14 background loops (`server.py:272`, `:1678`, `:1819`, `:392-406`).
- **The trade-history autopsy** (`analysis/*`): private data.

The one idea that does translate is **friction against the hot state**. The long-term analogs are already in the brief: the 4-week thesis age before `start_position`, with a written override (§11.9); a required reason on every journal entry and dismissal (§1.8, §6); and weights changing only through a labelled PR.

## 7. Gaps (what the old repo didn't have, or did wrong)

1. **No measured edge for any Long Bets rule.**
   - The scoreboard was seed → last price (`longbets_review.py:102-108`).
   - There was no benchmark, no point-in-time data, and no survivorship handling.
   - → Signal Lab (§4.10) with `L1-L6`.
2. **Undocumented data sources.** The Yahoo endpoints return 401 without a crumb and 429 under load (`longbets_screen.py:15-21`). Sector couldn't be fetched per symbol, so the LLM assigned it. → SEC, NSE and BSE primary filings.
3. **LLM-estimated fundamentals.** Market cap came from the model's approximation (`longbets_review.py:168-171`, `:375-380`), and India ideas came "from your own knowledge" with unverified numbers (`:158-159`). → Grounded facts with quotes and offsets (Appendix F); `validate.py` number checks (§4.9).
4. **No India discovery.** Screens were US-only (`longbets_review.py:158`). → NSE universe + S1-S12 + Capex Desk cross-border map.
5. **Disconfirmers were free text** that a human or LLM had to re-read. → Kill criteria are metric id, operator, threshold and check-after date, evaluated by code (§4.9).
6. **"Why ignored" was prose** (`longbets.json:15`, `:60`). → C4 attention (GDELT) and S8 ownership measure neglect.
7. **No short-interest data** for the old `most_shorted_stocks` lane. No free source is listed in BRIEF §2.7 (candidate: FINRA's bi-monthly short-interest files; needs a spec change → `docs/SPEC_ISSUES.md`).
8. **LLM budget counter was in process memory.** It reset on restart and didn't refund failed calls (`doomberg/judgment/brain.py:41-55`). There was no provider fallback on error (`brain.py:258-260`). → `llm_calls` table + router fallback + `deferred` (§2.6).
9. **Date bugs worth not repeating:**
   - The NSE expiry cache was keyed on the UTC date but filtered on the IST date (`nse_feed.py:70`, `:88`, `:108`).
   - The participant-OI walk-back used the local date (`nse_participants.py:46-47`).
   - → UTC everywhere (CLAUDE.md conventions), with explicit IST only for exchange calendars.
10. **Secret hygiene:**
    - A news API key was sent in the URL query string (`news_feed.py:55`).
    - A default dashboard password was hardcoded (`doomberg/config.py:18`).
    - An SSH public key was committed at the repo root (not a secret, but it identifies infrastructure).
    - No real credentials were found in the tracked files or history.
    - → Actions secrets only; `.env` git-ignored; allowlist login (§2.4, §6).
11. **Stale docs vs code:**
    - `brain.py:18` says the default provider is Gemini, but the code defaults to Nous (`brain.py:80-86`).
    - `.env.example:24` names a model the code no longer uses.
    - → `docs/VERSIONS.md` and the verify report are generated or checked, not hand-maintained claims.
