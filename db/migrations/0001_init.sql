-- 0001_init: BRIEF §3 data model + Appendix F.2 tables, verbatim (only the order of blocks is arranged
-- so every referenced table exists first). Deviations and additions live in later migrations.

-- ---------------------------------------------------------------- BRIEF §3
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

-- ---------------------------------------------------------------- BRIEF Appendix F.2
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

