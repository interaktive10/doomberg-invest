# DOOMBERG — Long-term investing research app (US + India)
**Builder: Claude Code Projects (cloud threads) · Thread model: Opus 5.5 · Thread effort: High · Running cost: $0**

Doomberg is a private, single-user research app for long-term investing. It covers all sectors, US and India. It finds companies where the **evidence of fundamental change is strong but the market's attention and expectations haven't caught up**, and turns each one into a thesis card with cited evidence, kill criteria and review dates. (The Capex Desk, which tracked AI and infrastructure capex, was deleted: SPEC_ISSUES 52.)

The app tests its own signals against history before trusting them, keeps a decision journal, and runs on free resources only.

This document is the complete spec. It replaces the Capex Ledger brief. Build it as written. Where it says DEFAULT, use that. If something is truly missing, choose the simplest option that passes the done conditions and log one line in `docs/DECISIONS.log`.

**Not financial advice.** The app surfaces research candidates. It doesn't know Manzoor's full financial situation, and every decision and all sizing are his.

---

## 0. How to run this build (Manzoor)

### 0.1 Repo
1. Create a **private** GitHub repo `doomberg-invest` and install the Claude GitHub App on it **and** on the old `doomberg` repo (read access is enough for the audit).
2. Put this document in the repo:
   ```bash
   mkdir -p ~/Projects && cd ~/Projects && git clone git@github.com:<you>/doomberg-invest.git && cd doomberg-invest
   mkdir -p docs && mv ~/Downloads/doomberg-invest-brief.md docs/BRIEF.md
   git add -A && git commit -m "docs: add build brief" && git push
   ```

### 0.2 Cloud environment (claude.ai/code → environment selector → **Add cloud environment**)
- **Name:** `doomberg-invest`
- **Network access:** **Custom**, and tick **Also include default list of common package managers**. Allowed domains (for fixture downloads during the build):
  ```
  www.sec.gov
  data.sec.gov
  efts.sec.gov
  www.nseindia.com
  nsearchives.nseindia.com
  archives.nseindia.com
  www.bseindia.com
  api.bseindia.com
  ```
- **Environment variables:**
  ```
  SEC_USER_AGENT=Doomberg personal research <your-email>
  MOCK_EXTERNALS=true
  ```
  No keys go here. Build threads use fixtures, mocks and cassettes. Live runs use GitHub Actions secrets.
- **Setup script:** empty. The SessionStart hook (Appendix C) installs everything.

### 0.3 Claude Code project (claude.ai/code → Projects → **New project**)
- **Name:** `Doomberg Invest`
- **Goal:** `Build docs/BRIEF.md to M9 with every verify check PASS or BLOCKED.`
- **Context:** the repo `doomberg-invest`.
- **Settings → General:**
  - Thread model **Opus 5.5**, Thread effort **High**
  - Coordinator: Opus 5.5, effort Low (default)
- **Settings → Environment:** the `doomberg-invest` environment.
- **Settings → Memory → Project instructions:** Appendix B verbatim.

### 0.4 First message to the project (paste verbatim)
```
Start one thread for M0 in docs/BRIEF.md §8. It must first create CLAUDE.md, .claude/settings.json,
.claude/agents/reviewer.md and scripts/session_start.sh exactly as in Appendix A and C. Then it adds the old
`doomberg` repository to itself read-only and writes docs/DOOMBERG_AUDIT.md per §8 M0 before building the rest of
M0. Open a draft PR. When the PR is ready, start a review thread for it per §10. Don't start M1 until I merge M0.
After that, at most two build threads at a time, in the order given in §8.
```

### 0.5 Free accounts (all $0, no card; needed from M2 on; details in §11)
| Account | Used for |
|---|---|
| Supabase (free) | Database, auth |
| Vercel Hobby (personal, non-commercial) or Cloudflare Pages | Web app |
| Google AI Studio | Gemini API free-tier key |
| Groq | Free-tier key |
| OpenRouter | Free models; optional fallback |
| Twelve Data | Free API key (US weekly prices; the Signal Lab's history) |

GitHub Actions free minutes run the pipeline. The weekly thesis-writing routine runs on the Claude plan you already have, so there's no API spend.

---

## 1. Product and method

### 1.1 Where a patient individual can still have an edge
Screens everyone runs (low P/E, high ROE, momentum, RSI and chart patterns, analyst upgrades, "AI stocks" lists) are crowded; by the time they fire, the move is usually priced. Doomberg looks for four other kinds of edge instead:
1. **Inflections, not levels.** Second derivatives: backlog accelerating faster than revenue, returns on *new* capital rising from a low base, margins turning, balance sheets finishing repair. Static screens only catch these after they're obvious.
2. **Processing edge.** The facts are public but costly to read: footnotes, remaining performance obligations, capacity commitments, supplier and customer links, and Indian exchange filings that few people parse.
3. **Corroboration.** A candidate needs at least two *independent* evidence families to agree, for example fundamentals + insider buying, or backlog + text evidence. One signal alone is noise.
4. **Neglect and structure.** Low and rising institutional ownership, low news attention, spin-offs, demergers, holding-company discounts: places where selling or neglect isn't about fundamentals.

The app then asks one question: **is this already priced in?** Candidates are generated **without looking at price**. Price, valuation and attention are added afterwards as a separate score, so "great company, already priced" is its own bucket, not a buy idea.

### 1.2 Design principles (long-term by design)
1. **Weekly cadence:**
   - end-of-day/weekly prices only
   - no intraday data, no price alerts, no execution or broker connections
   - one weekly digest; kill-criteria hits are reported in it
2. **Thesis-first:**
   - every idea becomes a thesis card with "what must be true", kill criteria and review dates
   - every position change is logged with a reason
   - reviews happen after each quarterly filing
3. **Evidence before price:** the Evidence score never uses price. Price enters only in the Gap score.
4. **Honest testing:**
   - a signal earns weight only through out-of-sample results in the Signal Lab (§4.10)
   - cliché signals, including any from the old Doomberg, stay context-only unless they prove themselves there
5. **Grounded text:** every fact from filings text carries an exact quote at stored offsets (Appendix F). Thesis cards separate **facts** (cited) from **inferences** and **assumptions** (labeled).
6. **Free data, personal use:** free sources are used within their terms for private use. Nothing is published or redistributed.
7. **Privacy:** journal and position data never leave Supabase and never go to any LLM (enforced in code, §2.6).

### 1.3 Universes (`config/universe_us.yaml`, `config/universe_in.yaml`; rebuilt monthly)
- **US:**
  - SEC filers of 10-K/10-Q with common stock listed on NYSE or Nasdaq (from the submissions `exchanges` field)
  - excludes funds, SPACs (SIC 6770), trusts and ADRs/20-F filers (v1)
  - minimum TTM revenue $50M
  - market cap ≥ $300M applied only at the candidate stage (it needs price)
- **India:**
  - NSE equity series `EQ` (from NSE's securities list)
  - excludes SME, and anything on the ASM/GSM surveillance lists
  - candidate stage: market cap ≥ ₹500 crore (price × shares from shareholding filings)
  - **paused** (SPEC_ISSUES 46): the India code and stored data stay, but no schedule fetches India and the weekly run scores the US only; SPEC_ISSUES 46 says how to restart it
- **Capex seed:** the Capex Ledger's US and India names (Appendix H, resolved in M0; unresolved names in `docs/UNIVERSE_ISSUES.md`) are flagged `companies.capex_desk`. The Capex Desk that read them was deleted (SPEC_ISSUES 52).

### 1.4 Evidence signals (price-free; formulas in §4.6)
| ID | Family | Signal | Markets |
|---|---|---|---|
| S1 | Fundamentals | Order-book acceleration: RPO/backlog growth beats revenue growth, and coverage rises | US (XBRL + text), IN (text) |
| S2 | Fundamentals | Incremental-ROIC inflection: returns on new capital ≥ 15% while trailing ROIC is still modest but rising | US, IN |
| S3 | Fundamentals | Operating-leverage onset: growth accelerating, margins expanding, opex growing slower than revenue | US, IN |
| S4 | Fundamentals | Earnings-quality inflection: cash conversion up, accruals down | US, IN |
| S5 | Fundamentals | Capital discipline: FCF-funded share count reduction, or dilution stopping after dilution years | US, IN |
| S6 | Fundamentals | De-risking complete: leverage from ≥ 3× to ≤ 1.5×, coverage ≥ 5× | US, IN |
| S7 | Behavior | Insider conviction: clustered open-market buying (US Form 4 code P, not 10b5-1); promoter market purchases or pledge release (IN) | US, IN |
| S8 | Behavior | Discovery: low-but-rising institutional ownership (13F holder count; FII+DII %) | US, IN |
| S9 | Text | Verified text facts: order/customer wins, committed capacity additions, price increases, lead-time extensions, new segments, removed material weakness or going-concern language | US, IN |
| S10 | Structural | Special situations: spin-offs/demergers (≤ 18 months), post-reorganization, holding-company structures, rights issues | US, IN |
| S12 | Cycle | Cycle position: the sector underinvested for 3 years (capex ≤ D&A), demand turning, text evidence of tightness | US, IN |

There is no S11: capex propagation was deleted with the Capex Desk (SPEC_ISSUES 52). Without EIA it could never fire.

### 1.5 Red flags (`R*`; hard ones exclude, soft ones subtract)
| ID | Rule | Type |
|---|---|---|
| R1 | Sloan accruals ≥ 10% of assets, or CFO/NI < 0.5 with positive NI | soft |
| R2 | Receivables growth − revenue growth ≥ 20 pp YoY, both for the latest quarter (India: the latest half-year end, as its receivables are half-yearly) against the same quarter a year earlier (SPEC_ISSUES 47) | soft |
| R3 | Auditor change (8-K Item 4.01) in the last 12 months; NT 10-K/10-Q; going-concern or material-weakness language (verified text) | hard |
| R4 | Share count +10% YoY without an acquisition | soft |
| R5 | India: promoter pledge ≥ 20% of promoter holding; on ASM/GSM; related-party revenue ≥ 10% of revenue (when disclosed) | hard (pledge, ASM/GSM), soft (RPT) |
| R6 | FCF < 0 and net debt rising for 4 straight quarters (unless S1 fires) | soft |

### 1.6 Context metrics (candidate stage only; these use price — §4.7)
| ID | Metric | What it tells you |
|---|---|---|
| C1 | Valuation percentile vs the company's own 10-year history (EV/Sales, EV/EBIT) | Cheap or rich vs itself |
| C2 | **Expectations gap:** evidence-based growth minus reverse-DCF implied growth (null unless ROIC beats the discount rate) | Has the market priced the change? |
| C3 | Run-up: 12-month return percentile in its universe (≥ 90th = "already ran"; null with a comparison group under 30) | Late or early |

### 1.7 Scores and buckets (§4.8)
- **Evidence score (0–100):**
  - weighted signal strengths
  - at most 2 signals count per family
  - **≥ 60 requires at least 2 families**
  - initial weights are equal; the Signal Lab proposes changes, and Manzoor approves them
- **Gap score (0–100):** C1–C3, equal weights initially.
- **Buckets:**
  | Bucket | Rule |
  |---|---|
  | **Candidate** | Evidence ≥ 60, Gap ≥ 50, no hard red flags |
  | **Priced-in** | Evidence ≥ 60, Gap < 50 |
  | **Early** | Evidence 40–59 with ≥ 2 families, Gap ≥ 50 (watch for corroboration) |
  | **Excluded** | Any hard red flag |
- **Weekly focus:** at most **10 new candidates** a week (not seen in the last 12 weeks), ranked by Evidence then Gap. Focus beats volume.

### 1.8 Thesis workflow and journal (§4.9)
**States:** Research → Thesis → Position → Review → Closed.
- **Research:** a card was generated. Manzoor reads it and decides whether to pursue it.
- **Thesis:** he accepts the card. It gets monitoring, kill criteria and review dates.
- **Position:** a manual journal entry (date, action, optional % of portfolio, reason). No broker link.
- **Review:** after each quarterly filing the app evaluates the kill criteria. He records intact / weakened / broken.
- **Closed:** requires a post-mortem (what happened vs the thesis; what the signals said).

### 1.9 Text fact types (Appendix F extraction)
The Capex Ledger types, plus general types:
| fact_type | Definition |
|---|---|
| `capex_guidance`, `capex_reported`, `backlog`, `rpo`, `lead_time`, `capacity_addition`, `commitment_lease`, `commitment_purchase`, `commitment_ppa`, `financing`, `customer_concentration`, `supply_link`, `utility_load`, `risk_factor_change` | Defined in Appendix F.1 (kept in `pipeline/facts/types.py`) |
| `order_win` | A stated order or contract win with value, customer or segment |
| `customer_win` | A new named customer or program |
| `price_increase` | A stated price increase or pricing action |
| `new_segment` | A new reportable segment or business line |
| `governance_flag` | Auditor change, material weakness, going concern, restatement (added or removed) |
| `export_exposure` | A stated export share or overseas order book (India: US/data-center exports) |

### 1.10 Capex Desk (deleted)
- **Deleted** in the overhaul (SPEC_ISSUES 52): the upstream demand index, the category map, the cross-border map (P-06), the S11 propagation signal, the weekly Capex brief and the Capex Desk screen. Without EIA, S11 could never fire.
- **Kept:** the counterparty links the text run writes (Appendix F.2), the capex tables and Manzoor's capex memberships (no migration).


---

## 2. Architecture ($0)

### 2.1 Components
```
GitHub Actions (free minutes, cron) ──▶ pipeline/ (Python 3.12, uv, Polars on the runner)
  daily   : SEC events (Form 4, 8-K items, NT filings), NSE/BSE announcements, thesis and stage-name filings → text facts
  weekly  : SEC bulk companyfacts → fundamentals · NSE bhavcopy + shareholding + PIT + results XBRL
            → signals → red flags → candidate prices (Twelve Data) → context (C1–C3) → scores/buckets
            → evidence packs → thesis queue file → digest issue
  quarterly: 13F data sets · universe rebuild
        │ writes compact tables                          ▲ raw bulk files stay on the runner / Actions cache
        ▼                                                │
Supabase free (Postgres + Auth) ◀── web/ (Next.js on Vercel Hobby or Cloudflare Pages, single user)
        ▲
Claude Code routine (weekly, on Manzoor's existing plan): reads data/thesis_queue/<week>.json from the repo,
writes thesis cards to data/thesis_cards/, runs `make thesis-validate`, pushes its branch
→ workflow `thesis-ingest.yml` validates again and upserts into Supabase.
Fallback, if no routine output by Monday 06:00 UTC: Gemini free tier writes the cards in Actions.
```

### 2.2 Stack (pin versions in lockfiles; record them in `docs/VERSIONS.md`)
- **Pipeline:**
  - Python 3.12 (uv)
  - `polars`, `httpx`, `pydantic` 2, `psycopg[binary]` 3, `pypdfium2`, `rapidfuzz`, `scipy` (root finding, stats), `pyyaml`
  - `pytest`, `ruff`, `mypy`
  - the packages nothing imported were removed (SPEC_ISSUES 52): SEC, NSE and XBRL parsing, Newey-West and the LLM calls are this repo's own code
- **LLM clients:** plain HTTPS calls (no SDK) to Gemini, Groq and OpenRouter, the last **only** at the OpenRouter base URL in `config/quotas.yaml`. No Anthropic or OpenAI paid endpoints at runtime (guard, Appendix E).
- **Web:**
  - Node 22, pnpm 9, Next.js 15, React 19, TypeScript strict
  - Tailwind 4, shadcn/ui, `@supabase/ssr`, zod
  - Recharts (fundamentals charts)
  - Playwright, Vitest, `@axe-core/playwright`
- **Dev and test database:** the pre-installed PostgreSQL 16 in cloud sessions. Production: Supabase free.

### 2.3 Repo layout
```
doomberg-invest/
  CLAUDE.md README.md Makefile .env.example pyproject.toml uv.lock
  .claude/{settings.json,agents/reviewer.md}  .github/workflows/*.yml  .github/CODEOWNERS
  config/ universe_us.yaml universe_in.yaml capex_seed.yaml signals.yaml weights.yaml redflags.yaml
          context.yaml quotas.yaml guards.yaml terms.yaml subject_keys.yaml sectors.yaml
  db/migrations/*.sql
  pipeline/
    net/ (http.py allowlist+rate limits+cache, sec.py, nse.py, bse.py, twelvedata.py)
    us/ (fundamentals.py, events.py, form4.py, thirteenf.py, specials.py)
    india/ (bhavcopy.py, securities.py, shareholding.py, pit.py, pledges.py, results_xbrl.py, announcements.py, manual_import.py)
    prices/ (bars.py, benchmarks.py, source.py, splits.py)
    facts/ (Appendix F: extract, ground, numbers, periods, verify1)
    signals/ (s01_orderbook.py … s12_cycle.py, redflags.py, context.py, reverse_dcf.py, scores.py, buckets.py)
    thesis/ (evidence_pack.py, queue.py, validate.py, render.py, ingest.py, fallback_writer.py, kill_criteria.py)
    lab/ (panel.py, pit.py, evaluate.py, report.py, legacy_doomberg.py)
    llm/ (router.py, providers/, prompts/P-0X.yaml, cassettes/, privacy.py)
    digest/ (weekly.py, github_issue.py)
    db/ (migrate.py, repo.py, pit.py (as_of helper), size_guard.py)
  web/ app/… components/ lib/ e2e/
  data/ thesis_queue/ thesis_cards/           # small JSON/MD, public-data only
  scripts/ guard.py guard_hook.py session_start.sh fetch_fixtures.py make_synthetic.py verify.py
  fixtures/ tests/ docs/
```

### 2.4 Secrets and configuration
- **GitHub Actions secrets:**
  - `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
  - `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY` (optional)
  - `TWELVEDATA_API_KEY`
  - `SEC_USER_AGENT`
  - `GH_ISSUES_TOKEN`: none needed; the workflow's `GITHUB_TOKEN` with `issues: write` suffices
- **Web env:** `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` (server only), `APP_ALLOWED_EMAIL`.
- **Mocks:** every external client has a real implementation and a mock. `MOCK_EXTERNALS=true` in cloud sessions.

### 2.5 Schedules and the minutes budget (GitHub Actions, UTC)
| Workflow | Schedule | Target runtime |
|---|---|---|
| `daily.yml` | `13 1 * * 2-6` | ≤ 8 min |
| `weekly.yml` | `7 2 * * 6` (Saturday) | ≤ 45 min |
| `thesis-fallback.yml` | `0 6 * * 1` | ≤ 10 min, only if no cards |
| `thesis-ingest.yml` | on push touching `data/thesis_cards/**` | ≤ 3 min |
| `quarterly.yml` | `0 3 20 1,4,7,10 *` | ≤ 60 min |
| `lab.yml` | manual | ≤ 90 min |
| `ci.yml` | PRs only (no push to `main`; a label change doesn't re-run it) | — |
| `protected.yml` | PRs, label changes included: the `protected` job (Appendix D) | — |
| `web.yml` | PRs touching the web app or a file its tests pin; Supabase, build and Playwright only when `web/**`, `db/migrations/**`, `supabase/**`, `scripts/seed_e2e.py`, `scripts/e2e_report.py` or `web.yml` change | — |
| `record-cassettes.yml` | manual | — |
| `live-smoke.yml` | manual | — |

- **Budget:** ≤ **1,200 minutes/month** including CI (the free private-repo allowance is 2,000; keep headroom).
- **Enforcement:** `scripts/verify.py` estimates monthly minutes from the last 4 runs and fails M9 above budget.
- **Concurrency:** one pipeline run at a time.

### 2.6 LLM on free tiers (`pipeline/llm/router.py`, `config/quotas.yaml`)
| Task | Primary | Fallbacks |
|---|---|---|
| Fact extraction P-01, entities P-02, announcement triage P-07 | Gemini Flash-Lite/Flash (free tier) | Groq free (Llama 3.3 70B class) → OpenRouter `:free` models |
| Thesis cards P-04 | **Claude Code routine** (weekly; existing plan) | Gemini Flash (free) in `thesis-fallback.yml` |
| Claim support P-05 | Gemini Flash | Groq |

**Router rules:**
- **Quotas:** per-provider daily request and token budgets in `config/quotas.yaml`, with values set from each provider's console in M0 (limits are per project and change; never hard-code "known" numbers).
- **On 429 or quota exhaustion:** fall back to the next provider. When all are exhausted, the item stays `deferred` and the next day's run picks it up.
- **Work order:** text work is prioritized: theses, research entries and positions, then the stage names (§4.5).
- **No paid endpoints:** `api.anthropic.com` and `api.openai.com` are banned in runtime code (guard). There is no credit card on any provider, so nothing can bill by accident.
- **Privacy (`llm/privacy.py`):** the router accepts only `EvidencePack`/`DocumentChunk` types built from public data. Journal, positions and notes can't be passed (a typed API plus a unit test). Free tiers may use inputs to improve their services, and that's acceptable only for public filings.
- **Grounding:** every text fact passes Appendix F grounding. Thesis cards pass `thesis/validate.py` (§4.9). Free-model errors are caught there, not trusted.

### 2.7 Data sources (all free; personal use; fragility noted)
| Data | Source | Cadence | Notes |
|---|---|---|---|
| US fundamentals | SEC bulk `companyfacts.zip` (nightly) + `submissions.zip`, parsed by this repo's own code | weekly | Point-in-time from filing acceptance dates |
| US events | EDGAR daily index / submissions: Form 4, 8-K items (4.01 auditor, 1.01, 2.02, 2.03), NT 10-K/10-Q, Form 10-12B (spin-offs) | daily | SEC fair access: user agent, ≤ 8 req/s |
| US ownership | SEC Form 13F data sets | quarterly | Holder counts per CUSIP → mapped to companies |
| US prices | Twelve Data weekly bars (free key), **candidate set + benchmarks only** (≤ 400 symbols/week; ^spx asked as SPY) | weekly | Free plan: 8 credits a minute, 800 a day (1 req/8 s); manual CSV import fallback (SPEC_ISSUES 38) |
| US prices, Signal Lab | Twelve Data daily closes (monthly if the free plan's daily history doesn't reach 2010), downloaded by `lab-prices.yml` with **no human step**: resumable, ≤ 650 credits and 90 minutes a run, Sunday to Thursday → month-end bars in the private GitHub release `lab-data-v1` | once (November 2026) | Survivorship bias warning (§7) |
| India prices | NSE CM-UDiFF Common Bhavcopy (daily file; use the Friday file) | weekly | BSE bhavcopy fallback |
| India securities list, ASM/GSM lists | NSE reports | weekly | |
| India fundamentals | NSE corporate filings: financial results (XBRL), shareholding patterns, insider trading (PIT), pledged data, announcements | weekly (announcements daily) | NSE site needs session cookies and polite rates (≤ 1 req/3 s); BSE fallback; **manual CSV import** from the pages' own "Download (.csv)" when blocked |

- **Staleness is visible:** each source has a health row. Stale beyond its SLA (US weekly 8 days; India weekly 10 days) → a banner in the app and the digest.

### 2.8 Storage budget (Supabase free: 500 MB database)
- **Store:**
  - `fundamentals_q` as one **wide row per company-quarter** (about 5,000 US + 2,000 IN companies × 60 quarters ≈ 420k rows ≈ 150 MB with indexes)
  - weekly prices for India (all EQ) and US candidates/benchmarks only
  - signals, scores, facts, theses, journal
- **Don't store:** raw bulk files. They live on the runner, with the Actions cache for incremental runs. The Signal Lab panel is kept as Parquet in a release asset.
- **Guard:** `db/size_guard.py` fails the weekly run above 400 MB and prunes old `signal_values` (keeps 3 years; the lab keeps its own Parquet).
- **Keep-alive:** Supabase free projects pause after inactivity; the daily workflow keeps the project active.

---

## 3. Data model (`db/migrations/0001_init.sql`)
```sql
create table companies (id uuid primary key default gen_random_uuid(), market text not null check (market in ('us','in')),
  name text not null, cik text unique, ticker text, isin text unique, nse_symbol text unique, bse_code text,
  sector text, industry text, sic text, fiscal_year_end text, in_universe boolean not null default true,
  capex_desk boolean not null default false, excluded_reason text, updated_at timestamptz not null default now());
create table fundamentals_q (company_id uuid references companies on delete cascade, period_end date not null,
  fiscal_label text not null, filed_at timestamptz not null,           -- point-in-time availability
  revenue numeric, op_income numeric, net_income numeric, pretax_income numeric, tax_expense numeric,
  cfo numeric, capex numeric, da numeric, interest_expense numeric, total_assets numeric, cash numeric,
  total_debt numeric, equity numeric, receivables numeric, inventory numeric, deferred_revenue numeric,
  rpo numeric, diluted_shares numeric, shares_outstanding numeric, currency text not null,
  source text not null check (source in ('sec_xbrl','nse_xbrl','bse_xbrl','manual')),
  primary key (company_id, period_end, filed_at));
create table prices_w (company_id uuid references companies on delete cascade, week_end date not null,
  close numeric not null, adj_close numeric, volume numeric, source text not null, primary key (company_id, week_end));
create table benchmarks_w (symbol text not null, week_end date not null, close numeric not null, primary key (symbol, week_end));
create table ownership_q (company_id uuid references companies on delete cascade, quarter_end date not null,
  inst_holders int, inst_pct numeric, fii_pct numeric, dii_pct numeric, promoter_pct numeric,
  promoter_pledged_pct numeric, source text not null, primary key (company_id, quarter_end));
create table insider_events (id uuid primary key default gen_random_uuid(), company_id uuid references companies on delete cascade,
  event_date date not null, filed_at timestamptz not null, person text not null, role text,
  kind text not null check (kind in ('open_market_buy','open_market_sell','promoter_buy','promoter_sell','pledge_created','pledge_released','other')),
  shares numeric, value numeric, currency text, planned boolean not null default false, source_url text not null);
create table corp_events (id uuid primary key default gen_random_uuid(), company_id uuid references companies on delete cascade,
  event_date date not null, kind text not null check (kind in ('auditor_change','late_filing','spinoff','demerger',
  'reorganization','rights_issue','index_change','announcement')), detail jsonb not null default '{}', source_url text not null);
-- sources / filings / documents / facts / diffs / risk_changes / entities / links: see Appendix F.2
create table signal_values (company_id uuid references companies on delete cascade, week_end date not null,
  signal_id text not null, fired boolean not null, strength numeric not null check (strength between 0 and 1),
  inputs jsonb not null, primary key (company_id, week_end, signal_id));
create table redflag_values (company_id uuid references companies on delete cascade, week_end date not null,
  flag_id text not null, hard boolean not null, inputs jsonb not null, primary key (company_id, week_end, flag_id));
create table context_values (company_id uuid references companies on delete cascade, week_end date not null,
  metric_id text not null, value numeric, pct numeric, inputs jsonb not null, primary key (company_id, week_end, metric_id));
create table scores (company_id uuid references companies on delete cascade, week_end date not null,
  evidence numeric not null, gap numeric, families text[] not null,
  bucket text not null check (bucket in ('candidate','priced_in','early','excluded','none')),
  weights_version text not null, primary key (company_id, week_end));
create table theses (id uuid primary key default gen_random_uuid(), company_id uuid not null references companies on delete cascade,
  state text not null check (state in ('research','thesis','position','review','closed','dismissed')),
  card_md text not null, card_json jsonb not null, evidence_pack jsonb not null, author text not null check (author in ('routine','fallback','manual')),
  validation jsonb not null, created_week date not null, next_review date, updated_at timestamptz not null default now());
create table kill_criteria (id uuid primary key default gen_random_uuid(), thesis_id uuid not null references theses on delete cascade,
  metric text not null, operator text not null check (operator in ('<','<=','>','>=','==','changes')),
  threshold numeric, check_after date not null, status text not null default 'ok' check (status in ('ok','triggered','unknown')),
  last_value numeric, last_checked date);
create table journal (id uuid primary key default gen_random_uuid(), thesis_id uuid references theses on delete set null,
  entry_date date not null, action text not null check (action in ('note','start_position','add','trim','exit','review')),
  portfolio_pct numeric, reason text not null, created_at timestamptz not null default now());   -- PRIVATE: never sent to LLMs
create table postmortems (thesis_id uuid primary key references theses on delete cascade, what_happened text not null,
  thesis_right boolean, signals_right jsonb, lessons text not null, created_at timestamptz not null default now());
create table lab_results (id uuid primary key default gen_random_uuid(), run_at timestamptz not null default now(),
  signal_id text not null, market text not null, horizon_m int not null, period text not null check (period in ('in_sample','out_of_sample')),
  n int not null, excess_mean numeric, excess_median numeric, hit_rate numeric, p10 numeric, t_nw numeric, notes text);
create table weights_versions (version text primary key, weights jsonb not null, reason text not null,
  approved_by text, approved_at timestamptz);
create table source_health (source text primary key, last_success timestamptz, last_error text, stale boolean not null default false);
create table runs (id uuid primary key default gen_random_uuid(), kind text not null, started_at timestamptz not null default now(),
  finished_at timestamptz, status text not null default 'running', stats jsonb not null default '{}', error text);
create table llm_calls (id uuid primary key default gen_random_uuid(), run_id uuid references runs, prompt_id text not null,
  provider text not null, model text not null, ok boolean not null, tokens_in int, tokens_out int, latency_ms int,
  error text, created_at timestamptz not null default now());
```
- **Access:** RLS on every table with no anon/authenticated policies. All access goes through server code: pipeline, Next.js route handlers and server actions. Only `APP_ALLOWED_EMAIL` can sign in.
- **Point-in-time rule:** any computation "as of week W" may use only rows with `filed_at` ≤ W's end. A shared helper enforces it and a test tries to cheat.


---

## 4. Pipelines (exact behaviour)
**Notation:**
- `q` = the latest quarter available as of week W (point-in-time)
- `TTM(x)` = sum of the last 4 quarters for flow items
- `g(x) = x_q / x_{q-4} − 1`, computed only if `x_{q-4} > 0`
- `clip(v, a, b)` limits v to the range [a, b]

All thresholds live in `config/signals.yaml` (a protected path) with the defaults below.

### 4.1 US fundamentals (`pipeline/us/fundamentals.py`)
1. **Download:** weekly, get `companyfacts.zip` and `submissions.zip` on the runner (SEC user agent). Use the Actions cache for incremental diffs.
2. **Concepts:** map us-gaap concepts to `fundamentals_q` columns with ordered fallbacks (`config/signals.yaml → xbrl_map`):
   - revenue: `Revenues` → `RevenueFromContractWithCustomerExcludingAssessedTax` → `SalesRevenueNet`
   - op_income: `OperatingIncomeLoss`
   - cfo: `NetCashProvidedByUsedInOperatingActivities`
   - capex: `PaymentsToAcquirePropertyPlantAndEquipment`
   - da: `DepreciationDepletionAndAmortization` → `DepreciationAndAmortization`
   - rpo: `RevenueRemainingPerformanceObligation`
   - diluted_shares: `WeightedAverageNumberOfDilutedSharesOutstanding`
   - shares_outstanding: `dei:EntityCommonStockSharesOutstanding`
   - and so on for the remaining columns
3. **Quarterizing:**
   - 10-Q values with ~3-month duration are quarters
   - Q4 flow = FY (10-K) − Q1 − Q2 − Q3 when all exist
   - YTD values are differenced
   - instants (balance sheet) are taken as reported
4. **Point-in-time:**
   - each row carries the filing's acceptance timestamp
   - restatements create a new row with a later `filed_at`; the old row stays
   - reads use the helper `as_of(W)`
5. **Sanity checks:**
   - revenue ≥ 0
   - shares > 0
   - |Q4 derived| ≤ 3× the average of Q1–Q3; beyond that → flagged, the metric is left null, and the reason is logged

### 4.2 US events and ownership (`pipeline/us/events.py`, `form4.py`, `thirteenf.py`, `specials.py`)
- **Form 4:**
  - non-derivative transactions with code **P** only
  - value = shares × price
  - `planned = true` when the Rule 10b5-1 checkbox is marked, or a footnote mentions 10b5-1
  - roles come from the reporting-owner relationship
- **8-K item codes:** 4.01 → `auditor_change`; 1.01/2.03 kept for text extraction on capex-desk companies. NT 10-K / NT 10-Q → `late_filing`.
- **Spin-offs:** Form 10-12B registrations that become effective → `spinoff`, linked to the parent via name/CIK mention (manual confirmation queue in the web app).
- **13F** (quarterly data sets):
  - count distinct filers per CUSIP
  - map CUSIP → company by issuer-name fuzzy match (rapidfuzz ≥ 92) against the universe, plus `config/cusip_overrides.yaml`
  - unmapped CUSIPs are logged

### 4.3 India (`pipeline/india/*`)
**Paused** (SPEC_ISSUES 46): no workflow runs these steps and the weekly scoring run scores the US only. The code and the stored India data stay as described below; SPEC_ISSUES 46 says how to restart it.
- **Securities and prices:**
  - the NSE securities list gives the EQ-series universe, ISINs and symbols
  - the weekly Friday **CM-UDiFF Common Bhavcopy** is parsed by column names (`TckrSymb`, `ISIN`, `SctySrs`, `ClsPric`, `TtlTradgVol`, …)
  - rows are kept by session/series rules (final session, EQ); unknown columns → a warning, never a crash
  - fallback: the BSE bhavcopy
- **Surveillance:** the ASM/GSM lists → hard red flag R5.
- **Financial results:** XBRL results filings (Ind AS) mapped to the `fundamentals_q` columns (`config/signals.yaml → ind_as_map`: revenue from operations, profit before tax, tax, profit after tax, finance costs, depreciation, …).
  - balance sheet and cash flow are **half-yearly** in India
  - signals use the latest available half-year instants and CFO, with TTM P&L; each signal records which periods it used
- **Shareholding patterns** (quarterly): promoter %, FII/FPI %, DII %, promoter pledged % → `ownership_q`.
- **Insider trading (PIT) and SAST:** promoter/promoter-group market purchases and sales → `insider_events`. Pledge creation and release events → `insider_events`.
- **Announcements** (daily RSS/listing) → `corp_events(kind='announcement')` with the PDF link. For the capex desk and the candidate shortlist, P-07 triages them, and relevant PDFs go through Appendix F extraction.
- **Access rules:**
  - browser-like headers; get session cookies from the NSE home page first
  - ≤ 1 request per 3 s; exponential backoff; cache
  - 3 consecutive blocks → mark `source_health.stale` and switch to BSE, then to `manual_import.py`, which accepts the CSVs Manzoor downloads from the NSE pages' own **Download (.csv)** buttons into `imports/` (via the web upload screen)

### 4.4 Prices (`pipeline/prices/*`, weekly)
- **India:** all EQ closes from the bhavcopy → `prices_w`.
- **US:** only the **candidate set** (Evidence ≥ 40 this week or last) plus theses/positions plus benchmarks (`^spx`, sector ETFs in `config/context.yaml`).
  - Twelve Data weekly bars (`time_series`, `interval=1week`), 1 request per 8 s, ≤ 400 symbols/week; ^spx is asked as SPY, the ETF that tracks it (SPEC_ISSUES 38)
  - failures → `stale` plus manual CSV import
- **Adjustments:** splits and bonuses are detected from price discontinuities, confirmed with the share-count change, and recorded in `prices_w.adj_close`. Unconfirmed jumps → flagged, never silently adjusted.

### 4.5 Text facts
Appendix F (carried over from the Capex Ledger brief): fetch → canonical text → P-01 extraction → exact-quote grounding → number, unit and period checks → verify-1 → diffs.
- **Scope, in priority order** (each newest first; SPEC_ISSUES 50):
  1. theses, research entries and positions: their 10-K, 10-Q and 8-K filings of the last 400 days
  2. the stage names (Evidence ≥ 40 in the latest scored week) with filings still queued or nothing read in 100 days: their latest 10-Q or 10-K and their 8-Ks with item 2.02, 7.01 or 8.01, of the last 120 days
- **Queue:** queued filings that no company in scope reads are marked `skipped`; a new thesis's come back within its 400 days. SEC submissions are read only for names new to the scope and names in the daily EDGAR index the SEC step reads.
- **Daily limits:** set by `config/quotas.yaml`; daily.yml starts no document after 6 minutes.

### 4.6 Signals (`pipeline/signals/*`; each returns fired, strength and inputs, stored in `signal_values`)
**Shared definitions:**
- **Tax rate:** `t = clip(TTM(tax)/TTM(pretax), 0.10, 0.35)`, defaulting to 0.21 (US) / 0.25 (IN) when pretax ≤ 0.
- **NOPAT:** `TTM(op_income) × (1 − t)`.
- **Invested capital:** `IC = total_debt + equity − cash`, floored at `0.05 × total_assets`. `ROIC = NOPAT / mean(IC over the last 4 quarters)`.
- **OPM** = `TTM(op_income)/TTM(revenue)`. **ND** = total_debt − cash. **FCF** = `TTM(cfo) − TTM(capex)`.

| ID | Fires when (all conditions) | Strength |
|---|---|---|
| S1 | ob = rpo (US) or the latest verified `backlog` fact; `g(ob) − g(TTM revenue) ≥ 0.10` in each of the last 2 quarters; `ob/TTM(revenue)` above its year-ago value and ≥ 0.25 (SPEC_ISSUES 42) | `clip((g(ob) − g(rev))/0.30, 0, 1)` |
| S2 | `IncROIC = ΔNOPAT_12q / ΔIC_12q` (only if ΔIC_12q > 0.05 × IC 12q ago) ≥ 0.15; `0.03 ≤ ROIC ≤ 0.12`; ROIC up ≥ 0.03 vs 8 quarters ago | `0.5 + 0.5 × clip((IncROIC − 0.15)/0.25, 0, 1)` |
| S3 | Quarterly revenue YoY growth rose in each of the last 2 quarters; OPM up ≥ 0.01 vs 4 quarters ago; `g(TTM opex) < g(TTM revenue)` with opex = revenue − op_income | `clip(ΔOPM/0.05, 0, 1)` |
| S4 | NI > 0; `CCR = TTM(cfo)/TTM(net_income) ≥ 1.0` and up ≥ 0.2 YoY; Sloan `(TTM NI − TTM CFO)/mean(total_assets 4q) < 0.05` and falling YoY; TTM CFO up YoY (SPEC_ISSUES 41); TTM NI ≥ 0.9 × TTM NI a year earlier; never for SIC 6000–6411 (banks, lenders, brokers, insurers; REITs at 6798 are scored) (SPEC_ISSUES 47) | `clip((CCR − 1)/0.5, 0, 1)` |
| S5 | (A) diluted shares YoY ≤ −2%, FCF > 0, and ND not up > 10% YoY; **or** (B) share growth ≥ +5% in each of the 2 prior years and ≤ 0% in the latest year | A: `clip(−Δshares/0.06, 0, 1)`; B: 0.6 |
| S6 | Max of `ND / TTM(op_income + da)` over quarters q−8…q−4 ≥ 3.0; current ≤ 1.5; `TTM(op_income)/TTM(interest)` ≥ 5 | 0.8 |
| S7 | **US:** ≥ 2 distinct insiders with unplanned code-P buys of ≥ $25k each within 60 days, total ≥ $250k; a filer whose only role is 10% owner is not counted, a joint "director; 10% owner" filing is (SPEC_ISSUES 49). **IN:** promoter-group market purchases ≥ ₹2 crore within 90 days, **or** promoter pledged % down ≥ 5 pp QoQ | `min(1, 0.5 + 0.1 × (n − 2) + 0.1 × log2(total/threshold))` (IN pledge path: 0.6) |
| S8 | **US:** 13F holder count ≤ 40th percentile within its revenue-size decile, **and** holders up ≥ 15% QoQ in each of the last 2 quarters. **IN:** FII + DII ≤ 15% and up ≥ 2 pp over 2 quarters | `clip(growth/0.5, 0, 1)` (IN: `clip(Δpp/6, 0, 1)`) |
| S9 | ≥ 1 verified fact in the last 2 quarters of types `order_win`, `customer_win`, `capacity_addition` (with a named counterparty or commitment), `price_increase`, `lead_time` (longer than before), `new_segment`, or `governance_flag` (removal) | `min(1, 0.4 × count)` |
| S10 | Spin-off/demerger ≤ 18 months ago; reorganization ≤ 24 months; listed in `config/holdcos.yaml`; rights issue ≤ 6 months | 0.6 (config) |
| S12 | The company's sector (`config/sectors.yaml`) is flagged: median capex/da ≤ 1.0 in each of the last 3 fiscal years; median revenue YoY growth > 0 in the last 2 quarters after ≤ 0 before; ≥ 2 verified `price_increase` or longer-`lead_time` facts in the sector in 2 quarters; **and** the company fires S2 or S6 | 0.6 |

There is no S11 (SPEC_ISSUES 52).

**Red flags** (`redflags.py`) implement §1.5 with the same shared definitions. Missing inputs never fire a flag; they're recorded as `unknown`.

### 4.7 Context metrics (`context.py`, `reverse_dcf.py`; candidate stage; they use price)
- **EV** = price × shares_outstanding + total_debt − cash (INR for India, USD for US).
- **C1:** EV/Sales_TTM and EV/EBIT_TTM (EBIT > 0) percentile vs the company's own weekly history (up to 10 years, point-in-time fundamentals). Score = `100 − mean(percentiles)`.
- **C2** (reverse DCF, 10 years plus terminal):
  - revenue₀ = TTM revenue
  - margin `m = max(OPM_TTM, median OPM over 5 years)`, floored at 0.02
  - tax t as above
  - sales-to-capital `S2C = median(Δrevenue/ΔIC)` over 5 years, clipped to [0.5, 4], default 1.5
  - `FCFF_t = rev_t × m × (1 − t) − Δrev_t / S2C`
  - discount rate: 9% US / 12% IN; terminal growth: 2.5% US / 4.5% IN (`config/context.yaml`)
  - solve for the constant growth `g*` over 10 years that makes PV = EV (`scipy.optimize.brentq` on [−0.20, 0.60]; no root → null)
  - evidence growth: `g_e = 0.4 × clip(g(ob), −0.2, 0.6) [if ob ≥ 0.25 × TTM revenue] + 0.3 × 3-year revenue CAGR + 0.3 × TTM revenue YoY`, capped to [−0.10, 0.40] (weights renormalize without ob; SPEC_ISSUES 42, 43)
  - C2 is null when `m × (1 − t) × S2C ≤ discount rate`: growth lowers PV there, so g* reads backwards (SPEC_ISSUES 43)
  - C2 is null when ROIC (§4.6) is unknown or ≤ the discount rate: a business that doesn't earn its cost of capital has no expectations gap to read (SPEC_ISSUES 48)
  - `C2 = g_e − g*`. Score = `clip(50 + 250 × C2, 0, 100)`
- **C3:** 52-week return percentile within the market's candidate set plus a benchmark sample. Score = `100 − pct`. `already_ran` if pct ≥ 90. Null when that comparison group has fewer than 30 members (`c3_runup.min_population`; SPEC_ISSUES 48).
- There is no C4: the GDELT news-attention percentile was deleted (SPEC_ISSUES 48).

### 4.8 Scores and buckets (`scores.py`, `buckets.py`)
1. **Families:** Fundamentals {S1–S6}, Behavior {S7, S8}, Text {S9}, Structural {S10}, Cycle {S12}.
2. **Family contribution:** `min(1, sum of the top 2 (weight_s × strength_s) in the family)`.
3. **Evidence:**
   - `raw = Σ_family W_f × contribution_f` (W_f = 1 by default, from `config/weights.yaml`)
   - `Evidence = 100 × min(1, raw / 2.0)`
   - if fewer than 2 families fired → `Evidence = min(Evidence, 55)`
   - each soft red flag subtracts 10, floored at 0
4. **Gap:** the mean of the available C1–C3 scores (needs ≥ 2, else null → bucket `none`).
5. **Bucket:** per §1.7.
6. **Weekly shortlist:** top 10 new candidates, both markets combined, ranked by Evidence then Gap, excluding any seen in the last 12 weeks.
7. **Provenance:** every score row stores the `weights_version`.

### 4.9 Thesis engine (`pipeline/thesis/*`)
**Evidence pack** (JSON; public data only):
- identifiers
- the last 12 quarters of key metrics
- fired signals with inputs, red flags, context metrics with their inputs (including reverse-DCF assumptions)
- ≤ 20 verified facts (quote + URL + fact id)
- ownership and insider events
- capex links
- candidate kill-criteria metrics (from the fundamentals/ownership/signal columns)
- the next expected filing window

Every item has a stable id (`m:…` metrics, `f:…` facts, `s:…` signals, `c:…` context).

**Weekly flow:**
1. `weekly.yml` writes `data/thesis_queue/{YYYY}-W{WW}.json` (≤ 10 packs) and commits it to `main` with the Actions bot.
2. **Routine** (Appendix G), Sunday 06:00 IST: reads the queue, writes one `data/thesis_cards/{week}/{company}.json` + `.md` per pack following P-04, runs `make thesis-validate WEEK=…`, fixes failures (≤ 2 attempts per card), then commits and pushes its branch.
3. `thesis-ingest.yml` (on push touching `data/thesis_cards/**`) re-validates and upserts `theses` (state `research`, author `routine`) and `kill_criteria`.
4. **Fallback:** `thesis-fallback.yml`, Monday 06:00 UTC. If no cards were ingested for the week, it generates them with Gemini (P-04), validates, and upserts with author `fallback`.

**Validation (`validate.py`; the card is rejected if any rule fails):**
- the JSON schema (P-04) is valid
- every sentence in `facts` and `why_mispriced` cites ≥ 1 pack id
- every number in those sentences equals a pack value (normalized) or a delta computed by code from cited values
- sentences in `assumptions` and `inferences` start with "Assumption:" / "Inference:". Numbers there are allowed but must be marked `(assumed)`
- each kill criterion references a real metric id, a valid operator and threshold, and a `check_after` date after the next filing window
- hype words (`config/terms.yaml → hype`: "multibagger", "can't lose", "guaranteed", "sure shot", "rocket", "to the moon") → reject

**Kill criteria:** evaluated whenever new `fundamentals_q`, `ownership_q` or `signal_values` rows arrive for the company. Triggered → the thesis moves to `review` and appears in the digest.

**Reviews:** after each new quarterly filing for a thesis or position company, the web app creates a review with the pack diff since the last review. Manzoor marks intact / weakened / broken and can add a journal entry.

**Closing** requires a post-mortem.

### 4.10 Signal Lab (`pipeline/lab/*`; `lab.yml`, manual; US first)
1. **Panel:**
   - month-end dates from 2010 onward
   - features computed **point-in-time** (filings accepted ≤ the date) with exactly the same code as the live signals (import, don't copy)
   - prices from the Twelve Data download (`lab-prices.yml`, `pipeline/lab/price_history.py`) in the private release `lab-data-v1` → month-end closes (the current, incomplete month dropped)
   - forward total price returns (dividends not included in v1; noted) at 12, 24 and 36 months
   - excess return vs the equal-weighted universe average at the same date
2. **Events:** the first fire of each signal per company within a rolling 12 months.
3. **Statistics per signal × horizon × period:**
   - N, mean and median excess, hit rate (excess > 0), 10th percentile, Newey-West t-stat (lags = horizon months)
   - periods: **in-sample** 2012–2018, **out-of-sample** 2019–2025 (config)
   - the same statistics for Evidence and Gap score deciles
4. **Legacy signals:** Doomberg's long-term rules (from `docs/DOOMBERG_AUDIT.md`) are implemented as `L1…Ln` in `legacy_doomberg.py` and evaluated identically.
5. **Weight proposals:**
   - OOS mean excess > 0 **and** `t_nw ≥ 2` **and** the same sign in-sample → weight 1.5
   - OOS insignificant → 1.0
   - OOS negative with `t_nw ≤ −2` → 0
   - legacy signals start at 0 and become live only by this rule
   - proposals open a PR that edits `config/weights.yaml` (a protected path; needs the `human-approved` label)
6. **Report:** `docs/LAB_REPORT.md` plus a Lab screen, with the caveats from §7 printed at the top.
7. **India lab:** enabled after 8 quarters of collected India data (config flag).

### 4.11 Capex Desk (deleted)
Deleted in the overhaul with S11, P-06, `config/categories.yaml` and the Capex brief (§1.10, SPEC_ISSUES 52).

### 4.12 Weekly digest (`pipeline/digest/*`)
- **Where:** a GitHub issue in the private repo, "Doomberg weekly — {week}", created by `weekly.yml` (GitHub notifies Manzoor by email for free). The same content appears on the web Home screen.
- **Sections:**
  - new candidates (≤ 10, one line each: families fired, Evidence, Gap, link)
  - theses needing attention (kill criteria triggered, reviews due)
  - source health and staleness
  - LLM quota use
  - Lab notes, if a new run happened
- **No price-move content:** no "top gainers" or similar lists.

---

## 5. Prompts (P-01 and P-02 carried over verbatim in Appendix F; the new prompts are below; P-03 is not called, SPEC_ISSUES 50; P-06 was deleted with the Capex Desk, SPEC_ISSUES 52)
### P-04 THESIS_CARD · routine (Opus 5.5 via Claude Code) or Gemini Flash (fallback) · temp 0.3
**System:**
```
You write a long-term investment research card from an evidence pack. The pack is the only source of facts.
Separate what is known from what is assumed. Every sentence in "facts" and "why_mispriced" must cite pack ids like
[f:…], [m:…], [s:…], [c:…], and every number must match the pack exactly. Put your reasoning in "inferences"
(each starting with "Inference:") and the things that must hold for the thesis in "assumptions" (each starting
with "Assumption:"; mark any number you choose with "(assumed)"). Kill criteria must be observable: a metric id from
the pack, an operator, a threshold, and a check-after date after the next filing window. Write plainly. No hype,
no certainty words, no price targets.
```
**User:** `EVIDENCE PACK:` followed by `{{pack_json}}`

**Schema:**
```
{summary: str(≤60 words), facts: [{text, cites:[str]}](3–8), why_mispriced: [{text, cites:[str]}](1–4),
 inferences: [str](1–5), assumptions: [str](2–5), risks: [{text, cites:[str]}](2–5),
 kill_criteria: [{metric_id, operator: enum[<,<=,>,>=,==,changes], threshold: number|null, check_after: date,
                  why: str}](2–4),
 read_next: [{title, url}](1–3)}
```

### P-05 CLAIM_SUPPORT
Carried over from the Capex Ledger brief (Appendix F). Used by `validate.py` on the `facts` and `why_mispriced` sentences when a number check alone can't confirm support.

### P-07 ANNOUNCEMENT_TRIAGE · Gemini Flash-Lite (free) · temp 0
**System:**
```
Classify one Indian exchange announcement title and summary. Return the categories that apply and whether the full
PDF should be read for facts. Categories: order_win, capacity_expansion, customer_win, fund_raise, rights_issue,
demerger, acquisition, pledge_change, auditor_change, management_change, results, credit_rating, other.
Return only JSON.
```
**Schema:** `{categories: [enum[...]], read_pdf: bool}`

---

## 6. Web app (`web/`, single user)
| Screen | Content |
|---|---|
| **Home** | The digest for this week; the stale-data banner (the only screen with it: sec, twelvedata, sec_13f) |
| **Candidates** | Tabs: Candidate · Early · Priced-in. Filters: market, sector, family, show dismissed. One row per company: Evidence with its change since the previous scored week, Gap, why it's here (fired signals), red flags, NEW (first week in that bucket in 12 weeks). Actions: open card, research, dismiss (reason required; it holds until a new signal or family fires or Evidence moves 10 or more) |
| **Company** | The latest scored week's Evidence, Gap, bucket and families under the name; fundamentals charts (revenue, OPM, ROIC and incremental ROIC, CCR, shares, ND/EBITDA, RPO/backlog); verified facts with quotes and links; insiders; events; reverse DCF (C2 inputs and implied growth); thesis link. Tables with no rows are left out |
| **Theses** | Needs you (cards to accept or dismiss, reviews to decide), Watching (theses and positions), Closed (closed and dismissed, folded); each row: Evidence at the card's week and now, kill criteria n of m triggered, next review. Thesis page: the card, kill criteria in words with their status, review history, journal entries; each form opens from its button and is left out when it can't be used |
| **Journal** | Private entries and post-mortems (never sent to any LLM) |
| **Signal Lab** | The price download's progress (the lab_prices runs row); each signal's verdict (works / unproven / hurts, §4.10.5; S7–S12 not testable yet) with the weight in use (weights_versions); results by signal, horizon and period; score deciles; open proposals |
| **Settings** | Source health for the US sources; the discipline weeks (§11.9); LLM calls and rate-limited calls per provider over 7 days. Universes, quotas and weights live in config/ and change through PRs |

- No screen but Home has a KPI ribbon or the stale banner; the footer carries the research-only line once.
- **Deleted** (SPEC_ISSUES 52): the Screener screen (its filter builder, saved screens and CSV export; the screener API, M4-05, stays) and the Capex Desk screen. `/screener` redirects to Candidates and `/capex` to Home (307).
- **Auth:** Supabase magic link for `APP_ALLOWED_EMAIL` only.
- **Quality:** responsive at 390 px; axe 0 serious issues.


---

## 7. Honest limits (print the first four at the top of the Signal Lab screen and in every Lab report)
1. No signal set reliably beats the market. The Lab exists to find out, and most signals will fail out of sample. That's useful information, not a bug.
2. **Survivorship bias:** the free US price file may miss delisted companies, so Lab results are an optimistic upper bound.
3. Lab returns exclude dividends (v1), taxes and costs.
4. The reverse DCF is a rough lens (one growth rate, generic discount rates). It ranks expectations; it doesn't value companies.
5. **Free sources break:** NSE/BSE access and Twelve Data's free plan can change or block. Staleness banners and manual imports keep the app usable.
6. **India:** balance sheets and cash flows are half-yearly, and XBRL quality varies. Signals record which periods they used.
7. **Free LLM quotas vary:** text coverage can lag in results season, and deferred items catch up.
8. **13F** data is quarterly and ~45 days old.
9. Personal use only. Not financial advice.

---

## 8. Milestones and done conditions
- **Done** means all of these:
  - `make verify-mN` exits 0
  - every check is PASS or BLOCKED(key|human)
  - CI is green
  - the review thread APPROVES (§10)
  - Manzoor merges
- **Every milestone** re-runs the earlier milestones' verify targets.
- **Order:** M0 → M1 → (M2 ∥ M3) → M4 → (M5 ∥ M7-shell) → M6 → M7 → M8 → M9. At most 2 build threads at a time.

### M0 — Bootstrap, Doomberg audit, guardrails
**Tasks:**
- Appendix A and C files, repo layout (§2.3), Makefile, CI, guard + hook + protected paths (Appendix D, E)
- `config/*` with this brief's defaults
- universe seed snapshots: SEC `company_tickers.json` + exchanges; the NSE securities list
- capex seed resolution (Appendix H)
- `docs/QUOTAS.md`: how to read each free provider's live limits; Manzoor fills in the values
- **`docs/DOOMBERG_AUDIT.md`** (read-only on the old repo), with sections:
  1. overview
  2. data sources used
  3. long-term/investing logic: every rule and formula with its thresholds and `file:line` references
  4. what's reusable as code
  5. which rules are cliché and become Lab-only `L*` signals
  6. trading/execution parts (not ported)
  7. gaps

**Done:**
| Check | Condition |
|---|---|
| M0-01 | Fresh cloud session: `make setup && make test` green |
| M0-02 | `make guard` passes, and fails on each seeded case (broker SDK import, `anthropic` import in `pipeline/`, a paid runtime domain, an order-placement identifier, journal data passed to `llm/`) |
| M0-03 | The hook exits 2 on an edit adding `import kiteconnect` |
| M0-04 | The audit exists with every section; each claimed rule has a `file:line`. Old repo not attachable → BLOCKED(human) |
| M0-05 | US universe ≥ 3,000 listed filers; India EQ ≥ 1,500 (the capex seed was resolved in M0, or listed in `docs/UNIVERSE_ISSUES.md`; its resolver went with the Capex Desk, SPEC_ISSUES 52) |
| M0-06 | `test_config_matches_brief.py`: every default in §4.6–4.8 equals the config value |
| M0-07 | Protected-path check fails without the `human-approved` label (synthetic diff) |

### M1 — Data layer
**Tasks:** migrations (§3 + Appendix F tables), `as_of` helper, repositories, `size_guard.py`, seed scripts.

**Done:**
| Check | Condition |
|---|---|
| M1-01 | Migrations run from zero twice |
| M1-02 | Rows filed after W are invisible to `as_of(W)` (a test tries to cheat) |
| M1-03 | RLS: queries as `anon` fail (local roles mirror Supabase) |
| M1-04 | Projected size for 7,000 companies × 60 quarters < 400 MB (estimator test) |
| M1-05 | Guard passes on the migrations |

### M2 — US data
**Tasks:** companyfacts/submissions ingestion, quarterizing, restatements, Form 4, 8-K items, NT filings, spin-offs, 13F holder counts (§4.1–4.2).

**Done:**
| Check | Condition |
|---|---|
| M2-01 | F-US (8 real companies) quarterized values equal the expected CSVs for 3 hand-checked companies, including Q4 derivation |
| M2-02 | A restatement creates a new row; `as_of` returns the right version |
| M2-03 | Form 4: code P only; `planned` via the checkbox and via a footnote; derivatives excluded (F-F4) |
| M2-04 | 8-K 4.01 and NT detection |
| M2-05 | 13F counts correct on F-13F; CUSIP mapping ≥ 90% on the sample |
| M2-06 | US weekly run on fixtures < 10 min in CI |

### M3 — India data
**Tasks:** §4.3 in full, including BSE fallback and manual import.

**Done:**
| Check | Condition |
|---|---|
| M3-01 | The UDiFF bhavcopy parser works on F-IN and tolerates unknown columns |
| M3-02 | 3 real results XBRL files map to the expected `fundamentals_q` rows; half-yearly balance-sheet/cash-flow handling tested |
| M3-03 | Shareholding and pledge % extracted from 3 real XBRL files |
| M3-04 | Promoter purchases detected from the PIT sample |
| M3-05 | 3 simulated 403s → `stale`, then BSE fallback, then a manual CSV import produces rows |
| M3-06 | ≤ 1 request per 3 s enforced |

### M4 — Signals, red flags, prices, context, scores, screener API
**Done:**
| Check | Condition |
|---|---|
| M4-01 | Every signal (S1–S10, S12) and R1–R6: a true case, a false case, and a just-below-threshold case on F-SYNQ, all passing |
| M4-02 | Signals as of W are identical whether or not later filings exist |
| M4-03 | Reverse DCF recovers a known g within ±0.1 pp from a synthetic EV; monotonic; null when there's no root |
| M4-04 | Twelve Data and bhavcopy weekly ingestion; split detection needs share-count confirmation |
| M4-05 | Evidence/Gap/bucket math, including the 2-family cap, soft-flag penalties and the 12-week novelty rule |
| M4-06 | Context percentiles C1 and C3 (C3 null below a comparison group of 30); no GDELT client (SPEC_ISSUES 48) |

### M5 — Text facts and Capex Desk
**Done:**
| Check | Condition |
|---|---|
| M5-01 | F-SYN planted facts: recall ≥ 95%, precision ≥ 98% with cassettes. No cassettes → BLOCKED(key), with mock-based structure tests passing |
| M5-02 | 100% grounding invariant on stored verified facts |
| M5-03 | Router: a 429 falls back to the next provider; all exhausted → `deferred`; picked up the next day (simulated clock) |
| M5-04 | Passing journal/post-mortem objects to the router raises `PrivacyViolation` |
| M5-05 | Retired with the Capex Desk (SPEC_ISSUES 52); was: demand index and direction on synthetic inputs |
| M5-06 | Retired with the Capex Desk (SPEC_ISSUES 52); was: P-06 ungrounded categories dropped; memberships count only after confirmation |
| M5-07 | Retired with the Capex Desk (SPEC_ISSUES 52); was: S11 rules on a synthetic graph |

### M6 — Thesis engine and digest
**Done:**
| Check | Condition |
|---|---|
| M6-01 | Pack schema, stable ids, public-data-only check |
| M6-02 | `validate.py` rejects F-CARD's bad cards (uncited fact, mismatched number, unlabeled inference, invalid kill criterion, hype word) and accepts the good one |
| M6-03 | Ingest logic (synthetic push event) upserts idempotently |
| M6-04 | Fallback runs only when the week has no cards (time-travel test) |
| M6-05 | A new fundamentals row triggers a kill criterion → `review` + a digest entry |
| M6-06 | Digest issue body snapshot (mock GitHub API) |

### M7 — Web app
**Done:**
| Check | Condition |
|---|---|
| M7-01 | Playwright: allowlist login; candidates → company → thesis → journal entry → review → close with a post-mortem |
| M7-02 | The web app makes no LLM calls at all (network assertion) |
| M7-03 | axe 0 serious; 390 px layouts |

### M8 — Signal Lab
**Done:**
| Check | Condition |
|---|---|
| M8-01 | F-LAB planted signal detected (`t_nw ≥ 3` out of sample); noise signal `|t_nw| < 2` |
| M8-02 | Leak test: moving `filed_at` later removes the planted effect |
| M8-03 | Report prints the §7 caveats verbatim |
| M8-04 | The proposal PR touches only `config/weights.yaml` and needs the label |
| M8-05 | The Lab's prices come from Twelve Data with no human step (`lab-prices.yml`, resumable); a real run is blocked, with the download's reason, until they are complete |

### M9 — Operations, hardening, live smoke
**Done:**
| Check | Condition |
|---|---|
| M9-01 | actionlint clean; a full dry-run week on fixtures and cassettes in CI |
| M9-02 | Estimated Actions minutes ≤ 1,200/month |
| M9-03 | Size-guard test |
| M9-04 | Weekly `pg_dump` → private release asset (keep 8), plus a restore test |
| M9-05 | Live smoke with free keys: US weekly on a 300-company subset + India bhavcopy + one text document extraction + 2 fallback thesis cards → report. BLOCKED(key) until keys exist |
| M9-06 | RUNBOOK, VERSIONS and QUOTAS docs complete |

---

## 9. Fixtures, tests, verify harness
| Fixture | Contents |
|---|---|
| F-US | SEC companyfacts JSON for 8 real companies (public domain) + expected quarterized CSVs for 3 |
| F-F4 | 10 real Form 4 XMLs (including 10b5-1 checkbox cases) + a synthetic insider cluster |
| F-13F | A small slice of one 13F data set |
| F-IN | 1 UDiFF bhavcopy, the NSE securities list, the ASM/GSM lists, 3 results XBRL, 3 shareholding XBRL, a PIT CSV, an announcements feed sample. Fetched once by `scripts/fetch_fixtures.py`; if NSE blocks it, Manzoor downloads them (BLOCKED(human)) |
| F-PX | Synthetic weekly series for 10 symbols, as the manual import's CSV and as Twelve Data's answers |
| F-SYNQ | Synthetic quarterly series: true, false and boundary cases per signal and red flag |
| F-SYN | `scripts/make_synthetic.py` (seed 7): 12 fictional-company documents with planted facts and a ground-truth JSON (4 press releases, 4 10-Q-style HTML documents, 2 risk-factor versions, 2 investor-presentation PDFs) |
| F-LAB | Synthetic panel: 500 companies × 60 months, one planted signal, one noise signal |
| F-CARD | 1 good and 5 bad thesis cards |
| Cassettes | P-01, P-02, P-05, P-07 and fallback P-04, recorded by `record-cassettes.yml` with free keys; hash manifest |

**`scripts/verify.py`:**
- a registry of `Check(id, milestone, description, command, requires)`
- writes `docs/VERIFY_REPORT.md`
- statuses: PASS, FAIL, BLOCKED(key:NAME), BLOCKED(human:WHAT)
- exits non-zero on any FAIL
- tests never use the network except `fetch_fixtures.py`, run once

---

## 10. Review loop (Claude Code native; same shape as before)
1. **Build thread:** branch `mN-<slug>` → draft PR → runs `make verify-mN` plus the earlier targets and pastes the summary → marks the PR ready when CI is green.
2. **Coordinator:** starts a review thread:
   ```
   Review PR #{{n}} ({{milestone}}) as the reviewer defined in .claude/agents/reviewer.md.
   Post one GitHub review. Do not push commits.
   ```
3. **Reviewer** (Appendix C): re-runs everything, traces 5 items end to end, runs the adversarial suite, and posts findings (P0–P3 with evidence, a §ref and an acceptance command) plus a verdict.
4. **Build thread:** fixes each finding with a regression test, or answers `DISPUTE: <evidence>`.
5. **Rounds:** at most 3 per PR, then Waiting on you. Manzoor merges.
6. **Final review** after M9: a full review of `main` → `docs/READY.md` (verdict, BLOCKED items, top 5 risks).

**Severity:**
| Level | Meaning |
|---|---|
| P0 | Look-ahead leak, journal data reaching an LLM, a paid endpoint or broker/execution code, a guard bypass, data loss, secret exposure |
| P1 | Spec deviation or bug in signals, scores, facts, theses or access control |
| P2 | Real defect with a workaround |
| P3 | Nit |

**Protected paths:** see Appendix D.

---

## 11. Human tasks (Manzoor)
1. **Setup:** 0.1–0.3 (about 45 min).
2. **After M0:** read `docs/DOOMBERG_AUDIT.md` (15 min) and confirm which old rules go into the Lab.
3. **Free accounts and keys** (0.5) by M2/M5. Add the GitHub secrets, and copy the live quota values from each console into `config/quotas.yaml`.
4. **M3:** if NSE blocks the fixture fetch, download the sample files by hand from the NSE pages.
5. **M8:** nothing to download: `lab-prices.yml` fetches the Lab's prices from Twelve Data into the private release `lab-data-v1` (November 2026) and starts the first Lab run itself.
6. **After M6:** create the weekly routine (Appendix G).
7. **Weekly** (about 30 min, weekend):
   - read the digest
   - open at most 3 cards
   - accept or dismiss them (with reasons)
   - do the reviews that are due
8. **Quarterly:** check the universe rebuild. After a Lab run (the first in November 2026, later ones by hand): approve or reject its weight proposals.
9. **Default discipline** (configurable in Settings): a thesis must be ≥ 4 weeks old before a `start_position` journal entry (an override needs a written reason). This is long-term investing on purpose.

---

## Appendix A — `CLAUDE.md` (create verbatim)
```markdown
# Doomberg Invest — repo guide for Claude Code
Spec: docs/BRIEF.md (read §1, §2, §4 and your milestone in §8 before any change). Build as written; don't redesign.
Ambiguity → DEFAULT, else the simplest option that passes; log one line in docs/DECISIONS.log.
Spec problems → docs/SPEC_ISSUES.md; keep building as written.

## Commands
make setup | make test | make lint | make type | make guard | make migrate-dev | make verify-mN | make fixtures
make thesis-validate WEEK=YYYY-Www | Web: cd web && pnpm test && pnpm e2e

## Hard rules (guard and CI enforce; never weaken or work around)
- $0 running cost: free tiers only; no paid endpoints (api.anthropic.com, api.openai.com) in runtime code; no credit
  cards anywhere.
- Research tool: no broker SDKs, no order placement, no intraday data, no price alerts.
- Point-in-time: read fundamentals/ownership/events only through as_of(); never use data filed after the as-of date.
- Journal, positions and post-mortems never go to any LLM (llm/privacy.py).
- Every text fact is grounded by exact quote at stored offsets; thesis cards pass thesis/validate.py.
- Evidence score never uses price. Weights change only through a PR with the human-approved label.

## Conventions
Python 3.12 typed, pydantic for every JSON contract, ruff+mypy clean; polars/duckdb for bulk data; SQL only in
db/migrations; UTC; numeric types for money and ratios; tests offline with fixtures and cassettes (never hand-edit
cassettes); every external client has a mock (MOCK_EXTERNALS=true in cloud sessions).

## Workflow
One milestone per thread, branch mN-<slug>, draft PR "[MN] …". Run make verify-mN plus earlier verify targets and
paste the summary in the PR. Fix review findings with a regression test each. Never merge, never force-push.
```

## Appendix B — Project instructions (paste into Project settings → Memory → Project instructions)
```text
This project builds Doomberg Invest in the doomberg-invest repository exactly as docs/BRIEF.md specifies, milestone
by milestone (§8, M0 → M9). The brief is the spec; don't redesign it.

How threads work
- One milestone per thread. Branch from main as mN-<slug>. Draft PR titled "[MN] <title>".
- Before calling work done: run `make verify-mN` and the earlier verify targets; paste the summary lines in the PR
  body and in your final message. CI must be green.
- When a build PR is ready, start a separate review thread: "Review PR #<n> (<milestone>) as the reviewer defined
  in .claude/agents/reviewer.md. Post one GitHub review. Do not push commits." Max 3 review rounds, then ask me.
- At most two build threads at a time, in the order of §8. The M0 thread may add the old `doomberg` repository to
  itself read-only for the audit; no other thread uses it.
- Never merge, force-push, change required CI checks, or edit protected paths (Appendix D) without asking me.

Hard rules (the guard enforces them)
- $0 running cost: free tiers only; no paid APIs in runtime code; nothing that needs a credit card.
- Research tool only: no broker SDKs, order placement, intraday data or price alerts.
- Point-in-time data access through as_of(); no look-ahead.
- Journal, positions and post-mortems never go to any LLM.

When something is missing
- If you can't reach something you need (a repository, a secret, a domain, a file), say exactly what is missing in
  your first message and stop that part. Use mocks only where the brief says MOCK_EXTERNALS; never mock around a
  missing requirement to make a check pass.
- Ask me before adding dependencies not listed in BRIEF §2.2 (small dev tools excepted) or creating any account.

Reporting
- Final message per thread: what changed, verify summary lines, BLOCKED items with the human action, next step.
  Ten lines max.
```

## Appendix C — Claude Code files (create verbatim)
### `.claude/settings.json`
```json
{
  "permissions": {
    "deny": [
      "Bash(gh pr merge:*)",
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      "Bash(pip install anthropic:*)",
      "Bash(uv add anthropic:*)",
      "Bash(uv add kiteconnect:*)",
      "Bash(uv add alpaca-py:*)"
    ]
  },
  "hooks": {
    "SessionStart": [
      { "matcher": "startup|resume",
        "hooks": [ { "type": "command", "command": "bash \"$CLAUDE_PROJECT_DIR\"/scripts/session_start.sh" } ] }
    ],
    "PostToolUse": [
      { "matcher": "Edit|Write|MultiEdit",
        "hooks": [ { "type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR\"/scripts/guard_hook.py" } ] }
    ]
  }
}
```
Check the permission-rule syntax against the current Claude Code docs. The CI guard is the real enforcement.

### `scripts/session_start.sh`
```bash
#!/bin/bash
# Cloud sessions only; idempotent; fast. DATABASE_URL defaults live in the Makefile and pipeline/settings.py.
if [ "$CLAUDE_CODE_REMOTE" != "true" ]; then exit 0; fi
cd "$CLAUDE_PROJECT_DIR" || exit 0
service postgresql start >/dev/null 2>&1 || true
su postgres -c "psql -tc \"select 1 from pg_roles where rolname='doom'\" | grep -q 1 || psql -c \"create role doom login password 'doom' superuser\"" >/dev/null 2>&1 || true
su postgres -c "psql -tc \"select 1 from pg_database where datname='doom'\" | grep -q 1 || createdb -O doom doom" >/dev/null 2>&1 || true
uv python install 3.12 >/dev/null 2>&1 || true
[ -f pyproject.toml ] && (uv sync --frozen >/dev/null 2>&1 || uv sync >/dev/null 2>&1) || true
[ -f web/pnpm-lock.yaml ] && (cd web && pnpm install --frozen-lockfile >/dev/null 2>&1) || true
[ -f pipeline/db/migrate.py ] && uv run python -m pipeline.db.migrate >/dev/null 2>&1 || true
exit 0
```

### `scripts/guard_hook.py` (behaviour)
1. Read the hook JSON from stdin and take `tool_input.file_path`.
2. Run `scripts/guard.py --paths <file>`.
3. On a violation: print each violation to stderr and `exit 2`. Otherwise `exit 0`.
4. Any internal error → exit 0 with a warning. It must never break the session.

### `.claude/agents/reviewer.md`
```markdown
---
name: reviewer
description: Independent reviewer for Doomberg Invest pull requests. Use when asked to review a PR against docs/BRIEF.md. Read-only; posts one GitHub review with findings.
tools: Read, Grep, Glob, Bash
---
You are the independent reviewer. You re-run everything yourself and trust no claim in the PR.
Scope: the PR's milestone in docs/BRIEF.md §8 plus regressions in earlier milestones.

1. Read BRIEF §1, §2, §4 and the milestone section, then the PR diff.
2. Check out the PR branch. Run: make setup, make guard, make test, make verify-<this milestone> and every earlier
   verify target.
3. Tests are real: open the test behind each done condition. Thresholds equal the brief (§4.6–4.8); no skipped or
   xfail tests; cassettes match their hash manifest; no test-only bypass in guards, validators or as_of();
   protected paths unchanged unless the PR has the human-approved label.
4. Trace 5 random items end to end on fixtures (state your seed): e.g. filing → fundamentals_q row (with filed_at)
   → signal inputs → score → evidence pack → card citation. Every hop must match exactly.
5. Adversarial suite (revert scratch changes afterwards with git checkout/git clean). Run what exists at this
   milestone; mark the rest not applicable:
   a) look-ahead: make a fixture row's filed_at later than W and confirm signals as of W ignore it; try reading
      fundamentals_q without as_of() in a scratch module → guard or test must fail;
   b) add `import kiteconnect` and `import anthropic` under pipeline/ in scratch files → make guard fails;
   c) call a non-allowlisted domain through pipeline/net/http.py → DomainNotAllowed;
   d) pass a journal or post-mortem object to pipeline/llm/router.py → PrivacyViolation;
   e) feed validate.py a card with an uncited fact sentence and one with a wrong number → both rejected;
   f) set one signal input just below its threshold → the signal does not fire;
   g) change config/weights.yaml in a scratch branch without the label → protected check fails.
6. Findings: only spec deviations and real defects, each with severity P0–P3 (BRIEF §10), evidence (command +
   output excerpt or file:line), the BRIEF § reference, and a runnable acceptance command with the expected result.
   Max 20, most severe first. Ideas go in a short "Ideas" list, not in findings.
7. Post exactly one GitHub review: summary, commands run, findings, verdict. APPROVE only with zero open P0/P1;
   otherwise REQUEST_CHANGES. Never push commits, never merge.
```

## Appendix D — Protected paths (CI job `protected`; changes need the `human-approved` label)
- `config/guards.yaml`, `config/signals.yaml`, `config/weights.yaml`, `config/context.yaml`, `config/redflags.yaml`
- `scripts/guard.py`, `tests/guard/**`, `pipeline/llm/privacy.py`, `pipeline/db/pit.py` (the `as_of` helper)
- `.claude/agents/reviewer.md`, `docs/BRIEF.md`

**The check:**
1. `git diff --name-only origin/${{ github.base_ref }}...HEAD`
2. Any protected match without the `human-approved` label → fail, listing the files.

CODEOWNERS covers the same paths. A test runs the check script on synthetic diffs.

## Appendix E — Guard configuration (`config/guards.yaml`; protected)
```yaml
scan_paths: [pipeline, web/app, web/components, web/lib, db, config, scripts, .github]
exclude_paths: [config/guards.yaml, tests/guard/cases, fixtures]
banned_python_packages:        # execution/broker SDKs (out of scope) and paid-only runtime SDKs
  [alpaca-py, alpaca-trade-api, ib_insync, ib-async, ibapi, ccxt, kiteconnect, smartapi-python,
   upstox-python-sdk, fyers-apiv3, dhanhq, breeze-connect, robin_stocks, schwab-py, tda-api, anthropic]
banned_npm_packages: ["@alpacahq/alpaca-trade-api", ccxt, kiteconnect, "@anthropic-ai/sdk", openai]
banned_runtime_domains: [api.anthropic.com, api.openai.com, api.kite.trade, api.upstox.com, api.alpaca.markets,
  paper-api.alpaca.markets, api.dhan.co]
banned_code_identifiers: [place_order, placeOrder, submit_order, submitOrder, market_order, limit_order, stop_loss_order]
openai_client_rule: "OpenAI(...) constructors must set base_url from config/quotas.yaml openrouter.base_url"
pit_rule: "direct SQL/ORM reads of fundamentals_q, ownership_q, insider_events, corp_events outside pipeline/db/pit.py are violations"
privacy_rule: "modules under pipeline/llm/ and pipeline/thesis/evidence_pack.py must not import or reference journal, postmortems, portfolio_pct"
```

## Appendix F — Carried over from the Capex Ledger brief (text facts engine)
These parts of the earlier brief are kept as-is (only the section labels and model lines changed). They define the text-fact engine used by §4.5 and §4.11. In them, "the Desk" means this app's review screens.

### F.1 Capex fact types (carried over; `pipeline/facts/types.py`)
| fact_type | Definition | Example subject_key |
|---|---|---|
| `capex_guidance` | A company's stated expectation for capital expenditures | `capex_guidance:FY2027` |
| `capex_reported` | Reported capital expenditures (XBRL `PaymentsToAcquirePropertyPlantAndEquipment` and text) | `capex_reported:Q2FY2026` |
| `backlog` | Stated backlog/orders (industrial, contractors) | `backlog:total`, `backlog:data_center` |
| `rpo` | Remaining performance obligations (XBRL `RevenueRemainingPerformanceObligation` and text) | `rpo:total`, `rpo:next_12m_pct` |
| `lead_time` | A stated lead time for equipment or capacity | `lead_time:large_power_transformers` |
| `capacity_addition` | New or expanded capacity: MW/GW, factories, square feet, sites, with timing | `capacity:mw:site_<slug>` |
| `commitment_lease` | Leases not yet commenced, data-center leases, lease commitments | `lease_not_commenced:total` |
| `commitment_purchase` | Purchase obligations, capacity/compute purchase commitments, take-or-pay | `purchase_obligations:total` |
| `commitment_ppa` | Power purchase and energy supply agreements (counterparty, MW, term) | `ppa:<counterparty>:<site>` |
| `financing` | Debt, JV or SPV financing tied to AI/data-center infrastructure | `financing:<instrument>:<date>` |
| `customer_concentration` | Stated share of revenue from the largest customers | `customer_concentration:top1` |
| `supply_link` | A named customer/supplier/partner relationship tied to AI infrastructure | `link:<counterparty>` |
| `utility_load` | Utility large-load or data-center pipeline (GW, requests, contracts) | `large_load:pipeline_gw` |
| `risk_factor_change` | Added, removed or modified risk-factor paragraphs on AI, data centers, power or supply chain (§4.5) | `risk:<paragraph_hash>` |


### F.2 Tables (append to `0001_init.sql`)
```sql
create table sources (id uuid primary key default gen_random_uuid(), company_id uuid not null references companies on delete cascade,
  kind text not null check (kind in ('ir_press','ir_presentation','ir_transcript')), url text not null, feed_url text,
  domain text not null, active boolean not null default true, last_checked_at timestamptz, last_error text);
create table filings (id uuid primary key default gen_random_uuid(), company_id uuid not null references companies on delete cascade,
  accession_no text unique not null, form_type text not null, items text[], filed_at timestamptz not null,
  accepted_at timestamptz, period_of_report date, primary_doc_url text not null, index_url text not null,
  status text not null default 'new' check (status in ('new','fetched','normalized','extracted','verified','skipped','failed')),
  created_at timestamptz not null default now());
create table documents (id uuid primary key default gen_random_uuid(), company_id uuid not null references companies on delete cascade,
  filing_id uuid references filings on delete cascade, source_id uuid references sources on delete set null,
  kind text not null check (kind in ('10-K','10-Q','8-K','EX-99.1','EX-99.2','press_release','presentation','transcript','other')),
  url text unique not null, title text, published_at timestamptz not null, sha256 text not null,
  raw_path text not null, text_path text, text_chars int, section_map jsonb not null default '[]', page_map jsonb not null default '[]',
  status text not null default 'fetched' check (status in ('fetched','normalized','extracted','failed','deferred')),
  created_at timestamptz not null default now());
create table facts (id uuid primary key default gen_random_uuid(), company_id uuid not null references companies on delete cascade,
  document_id uuid not null references documents on delete cascade, fact_type text not null, subject text not null,
  subject_key text not null, value_num numeric, value_low numeric, value_high numeric,
  unit text not null check (unit in ('usd','usd_per_year','mw','gw','mwh','sq_ft','months','weeks','years','percent','count','other')),
  currency text, scale_word text, period_label text, period_start date, period_end date, as_of date not null,
  counterparty text, counterparty_entity_id uuid, location text,
  quote text not null check (char_length(quote) between 5 and 600), char_start int not null, char_end int not null,
  section text, page int, xbrl_concept text, xbrl_check text not null default 'na' check (xbrl_check in ('match','mismatch','na')),
  extraction_model text not null, confidence numeric(3,2) not null,
  verification_status text not null check (verification_status in ('verified','needs_review','failed')),
  verification_notes jsonb not null default '{}', superseded_by uuid references facts,
  created_at timestamptz not null default now(), check (char_end > char_start));
create index facts_key on facts (company_id, subject_key, as_of desc);
create table diffs (id uuid primary key default gen_random_uuid(), company_id uuid not null references companies on delete cascade,
  subject_key text not null, prev_fact_id uuid references facts, new_fact_id uuid not null references facts,
  change_kind text not null check (change_kind in ('new','raised','lowered','reaffirmed','widened','narrowed','changed')),
  delta_abs numeric, delta_pct numeric, computed_note text not null, created_at timestamptz not null default now());
create table risk_changes (id uuid primary key default gen_random_uuid(), company_id uuid not null references companies on delete cascade,
  from_document_id uuid references documents, to_document_id uuid not null references documents,
  change_kind text not null check (change_kind in ('added','removed','modified')), text_before text, text_after text,
  similarity numeric(4,3), topic_tags text[] not null, char_start int, char_end int, created_at timestamptz not null default now());
create table entities (id uuid primary key default gen_random_uuid(), name text not null, normalized text unique not null,
  cik text, kind text not null check (kind in ('company','utility','developer','government','other')),
  first_seen_at timestamptz not null default now());
create table links (id uuid primary key default gen_random_uuid(), from_company_id uuid not null references companies on delete cascade,
  to_entity_id uuid not null references entities on delete cascade,
  relation text not null check (relation in ('customer','supplier','partner','lessor','lessee','ppa_counterparty','lender','jv')),
  fact_id uuid not null references facts, first_seen_at timestamptz not null default now(), unique (from_company_id,to_entity_id,relation));
```

### F.3 Fetch and normalize (`ingest/fetch.py`, `normalize/`)
- **Raw storage:** `raw/{cik}/{accession_or_hash}/{filename}`, sha256 dedupe.
- **Canonical text** (all offsets refer to it): Unicode NFC; whitespace runs collapsed to one space inside lines; paragraph breaks kept as `\n\n`. Deterministic, with unit tests.
- **HTML (EDGAR, including inline XBRL):**
  - drop script, style and hidden elements
  - keep headings
  - tables become text rows (`cell | cell | cell`) with row order preserved
  - `section_map`: detect 10-K/10-Q items by heading regexes (Item 1A Risk Factors, Item 7 / Part I Item 2 MD&A, Item 8 notes) and notes by title keywords (Commitments, Contingencies, Leases, Revenue, Debt, Subsequent Events)
- **PDF:** `pypdfium2` text per page; `page_map` = `[{page, char_start, char_end}]`.
- **Press releases and transcripts:** the whole body. Transcripts are split into prepared remarks vs Q&A when headings exist.

### F.4 Extract (`facts/extract.py`, P-01)
1. **Chunk selection:**
   - 10-K/10-Q: MD&A plus the notes named above
   - EX-99.1, press releases and transcripts: the whole document
   - presentations: pages
   - risk factors: not extracted (F.6)
   - chunks ≤ 10k tokens with 400-token overlap; each carries its absolute `char_start`
2. **Prefilter:** a keyword score from `config/terms.yaml` (data center, AI, capacity, backlog, capital expenditures, capex, lead time, MW, GW, megawatt, gigawatt, lease, purchase obligation, power purchase, interconnection, transformer, turbine, cooling, accelerator, GPU, networking, optical, large load, …). Only chunks with a score ≥ 3 go to P-01.
3. **P-01** returns facts, each with a verbatim `quote`.
4. **Grounding** (`facts/ground.py`):
   - find the quote in the chunk text: exact match on canonical text first; else a whitespace/punctuation-insensitive match
   - **no fuzzy matching**: not found → rejected
   - absolute offsets are saved
5. **Numbers** (`facts/numbers.py`):
   - parse from the quote: `$X.Y billion/million/thousand`, bare numbers with a scale word, ranges (`X to Y`, `X–Y`), `approximately`, percents, MW/GW/MWh, months/weeks/years, square feet
   - the model's `value_*` must equal a number parsed from the quote after scaling (tolerance: rounding of the last reported digit), else rejected
   - currency: USD only in v1; anything else → `needs_review`
6. **Periods** (`facts/periods.py`): resolve fiscal periods with the company's `fiscal_year_end` (from submissions JSON). Guidance for periods that already ended at the filing date → `needs_review`.
7. **subject_key:** P-01 proposes one from `config/subject_keys.yaml`, and code validates it. Unknown → `other:<slug>` plus `needs_review`.

### F.5 Verify-1 (`facts/verify1.py`; the fact enters the ledger only if `verified`)
| Check | Rule | On failure |
|---|---|---|
| V1-QUOTE | `canonical_text[char_start:char_end] == quote` (canonical form) | failed (not stored as a ledger fact; logged) |
| V1-NUM | Every numeric field appears in the quote after normalization | failed |
| V1-UNIT | Unit consistent with quote tokens (e.g. "MW" ↔ mw, "$" ↔ usd) | failed |
| V1-TYPE | fact_type allowed; no price fields in facts (prices live in `prices_w`); subject_key valid | failed |
| V1-PERIOD | Period resolvable and plausible | needs_review |
| V1-XBRL | If an XBRL concept maps to the same period: \|value − xbrl\| ≤ 0.5% → `match`; else `mismatch` | needs_review on mismatch |
| V1-CONF | confidence ≥ 0.70 | needs_review below |
| V1-DUP | The same document already has an identical `subject_key` + value | dropped as a duplicate |

`needs_review` facts appear in the web app's review queue (Company page). Manzoor verifies or rejects them (a reason is required). Only verified facts feed diffs, signals, packs and briefs.

### F.6 Diff (`diff/facts_diff.py`)
**Fact diffs:**
- for each new verified fact, compare with the latest earlier verified fact of the same company and `subject_key`
- single values: `raised`/`lowered` if the change is > 0.5%, else `reaffirmed`
- ranges: compare midpoints (raised/lowered/reaffirmed) and widths (`widened`/`narrowed` when the width changes by > 10% and the midpoint is reaffirmed)
- no prior fact → `new`
- `delta_abs`, `delta_pct` and `computed_note` (e.g. `"$38.0B → $45.0B (+18.4%)"`) are computed by code, never by an LLM
- absence of a fact is **not** removal. "Removed" exists only for risk factors, or when a company explicitly withdraws guidance (P-01 `withdrawn` flag + quote)

**Risk-factor diffs:** not made (SPEC_ISSUES 50). Nothing read their `risk_changes` rows, so P-03 is not called; the table stays.


### F.7 Prompts P-01, P-02, P-03 (not called), P-05
### P-01 EXTRACT_FACTS · free-tier router (§2.6) · temp 0
**System:**
```
You extract facts about AI-infrastructure spending, capacity and obligations from one excerpt of a company document.
Extract only facts the excerpt states explicitly. Never calculate, infer, combine, annualize or convert numbers.
For every fact, copy the exact supporting text into "quote": verbatim, at most 60 words, and it must appear exactly
in the excerpt. If a number's meaning depends on nearby words (a unit, a period, "approximately"), include them in
the quote.
Allowed fact types: {{fact_types_with_definitions}}.
Use a subject_key from this vocabulary: {{subject_keys}}. If none fits, use "other:<short-slug>".
Do not extract anything about share prices, stock performance, valuation, analyst views, ratings, share repurchases,
dividends or trading. If the excerpt states that previous guidance is withdrawn, set "withdrawn": true.
Return only the tool call.
```
**User:**
```
COMPANY: {{name}} ({{ticker}}), fiscal year ends {{fye}}
DOCUMENT: {{kind}} · {{title}} · published {{published_at}}
SECTION: {{section}} · excerpt chars {{char_start}}–{{char_end}}
<<<
{{text}}
>>>
```
**Schema:**
```
{facts: [{fact_type: enum[...], subject: str(≤120), subject_key: str,
          value: number|null, value_low: number|null, value_high: number|null,
          unit: enum[usd|usd_per_year|mw|gw|mwh|sq_ft|months|weeks|years|percent|count|other],
          currency: str|null, scale_word: enum[thousand|million|billion|trillion|null],
          period_label: str|null, as_of: str(YYYY-MM-DD)|null,
          counterparty: str|null, location: str|null, withdrawn: bool,
          quote: str, confidence: number(0-1)}]}
```

### P-02 ENTITY_NORMALIZE · free-tier router · temp 0
**System:**
```
Match each counterparty name to at most one candidate from the list, or to none. Use only the names given; never
invent an entity. Treat subsidiaries as the parent only if the name makes that explicit. Return only the tool call.
```
**User:** `NAMES: {{names}}` and `CANDIDATES: {{candidates}}` (candidates come from the SEC company list plus existing entities, via rapidfuzz top 5)

**Schema:**
```
{matches: [{name: str, candidate_id: str|null, kind: enum[company|utility|developer|government|other],
            confidence: number}]}
```

### P-03 RISK_TAGS · not called (SPEC_ISSUES 50: nothing read its `risk_changes` rows); kept for the record
**System:**
```
Tag each risk-factor paragraph with the topics it is about, from the allowed list only. A paragraph can have zero
tags. Do not summarize. Return only the tool call.
```
**User:** `ALLOWED: {{tags}}` and `PARAGRAPHS: {{id_text_list}}`

**Schema:** `{items: [{id: str, tags: [enum[...]]}]}`

### P-05 CLAIM_SUPPORT · free-tier router · temp 0
**System:**
```
Decide whether a sentence is fully supported by the quoted source texts and computed values given. Supported means
every claim in the sentence is stated in a quote or equals a provided computed value. Wording can differ; meaning
cannot. Anything extra, stronger, or interpretive is unsupported. Return only the tool call.
```
**User:** `SENTENCE: {{sentence}}`, then `QUOTES: {{quotes}}`, then `COMPUTED: {{computed}}`

**Schema:** `{supported: bool, unsupported_parts: [str], reason: str(≤40 words)}`

## Appendix G — Weekly thesis routine (create after M6 is merged)
- **How:** create it from the project conversation ("put this on a weekly schedule as a routine") or the Routines page.
- **Settings:** environment `doomberg-invest`; schedule Sunday 00:30 UTC (06:00 IST).
- **Prompt:**
```text
Read docs/BRIEF.md §4.9 and §5 (P-04). Open the newest file in data/thesis_queue/. For each evidence pack in it,
write data/thesis_cards/<week>/<company_key>.json following the P-04 schema, plus a .md rendering with
`uv run python -m pipeline.thesis.render <json>`. Use only the pack. Cite pack ids on every fact and
why-mispriced sentence; label inferences and assumptions; kill criteria per §4.9.
Run `make thesis-validate WEEK=<week>`. Fix failing cards (at most 2 attempts each); if a card still fails,
delete it and list it with reasons in data/thesis_cards/<week>/FAILED.md.
Commit and push your branch. Edit nothing else. Do not open a PR. Final message: cards written, cards failed.
```
- **Fallback:** if the routine hits a plan limit, its turn stops. `thesis-fallback.yml` covers the week on Monday.

## Appendix H — Capex Desk seed (now only `companies.capex_desk`; the desk was deleted, SPEC_ISSUES 52)
- **US (60):** the list from the Capex Ledger brief, carried over unchanged into `config/capex_seed.yaml`:
  - MSFT, GOOGL, AMZN, META, ORCL, CRWV
  - NVDA, AMD, AVGO, MRVL, MU, INTC, ANET
  - DELL, SMCI, HPE, JBL, FLEX
  - GLW, COHR, LITE, CIEN, APH
  - WDC, STX
  - AMAT, LRCX, KLAC
  - GEV, ETN, VRT, HUBB, POWL, NVT, CMI, CAT
  - MOD, TT, JCI
  - BE, FLNC
  - PWR, EME, FIX, MTZ, PRIM, STRL
  - EQIX, DLR, IRM
  - CEG, VST, TLN, NRG, D, SO, AEP, ETR, XEL, NEE, DUK
- **India** (names; M0 resolves NSE symbols; unresolved → `docs/UNIVERSE_ISSUES.md`):
  - **Power and grid equipment:** ABB India, Siemens, Siemens Energy India, Hitachi Energy India, GE Vernova T&D India, CG Power and Industrial Solutions, Bharat Heavy Electricals, Transformers and Rectifiers (India), Voltamp Transformers, Schneider Electric Infrastructure, Apar Industries, Polycab India, KEI Industries, Havells India, KEC International, Kalpataru Projects International, Larsen & Toubro, Thermax, Cummins India, Kirloskar Oil Engines
  - **Power producers and grid:** NTPC, Power Grid Corporation of India, Tata Power, JSW Energy, Adani Energy Solutions
  - **Renewables manufacturing:** Waaree Energies, Premier Energies, Suzlon Energy, Inox Wind
  - **Electronics manufacturing and AI compute:** Dixon Technologies, Kaynes Technology India, Syrma SGS Technology, Netweb Technologies India, E2E Networks
  - **Data centers and connectivity:** Anant Raj, Techno Electric & Engineering, Tata Communications, Bharti Airtel, Sterlite Technologies, HFCL
  - **Cooling:** Blue Star
