-- 0009 (M5): text facts and the Capex Desk (BRIEF §4.5, §4.11, §5 P-06/P-07, Appendix F).
--   1. facts: the stored quote is exactly the canonical text between its offsets (V1-QUOTE; the M5-02 invariant), so
--      its length equals the span. facts.withdrawn keeps P-01's withdrawal flag (Appendix F.6).
--   2. announcement_triage: the P-07 result per India announcement (corp_events kind 'announcement'). No row = not
--      triaged yet (deferred items are picked up the next day). Pruned with the announcement.
--   3. capex_memberships: category memberships with their evidence (US: the industry map; India: P-06 quotes). They
--      count only once Manzoor confirms them in the web app (§4.11); a rejection needs a reason.
--   4. capex_inputs: weekly observations of each demand input (EIA planned additions, and the fact-based levels).
--   5. capex_index: the weekly demand index per category (mean z of its inputs' YoY change, direction, input growth).
--   6. capex_briefs: the weekly Capex brief (markdown) that goes into the digest.

alter table facts add constraint facts_quote_span check (char_end - char_start = char_length(quote));
alter table facts add column withdrawn boolean not null default false;
create index facts_document on facts (document_id);
create index facts_type_asof on facts (fact_type, as_of);
create index documents_company on documents (company_id, published_at);
create index documents_status on documents (status);
create index filings_status on filings (status, filed_at);

create table announcement_triage (event_id uuid primary key references corp_events on delete cascade,
  company_id uuid not null references companies on delete cascade, categories text[] not null,
  read_pdf boolean not null, model text not null, created_at timestamptz not null default now());

create table capex_memberships (company_id uuid not null references companies on delete cascade,
  category text not null, source text not null check (source in ('industry_map','p06')),
  status text not null default 'proposed' check (status in ('proposed','confirmed','rejected')),
  evidence text not null, quote text, document_id uuid references documents on delete set null,
  char_start int, char_end int, confidence numeric(3,2),
  proposed_at timestamptz not null default now(), decided_at timestamptz, decision_reason text,
  primary key (company_id, category),
  check (status = 'proposed' or decided_at is not null),
  check (status <> 'rejected' or decision_reason is not null));

create table capex_inputs (input_id text not null, week_end date not null, value numeric,
  detail jsonb not null default '{}', primary key (input_id, week_end));

create table capex_index (category text not null, week_end date not null, value numeric,
  direction text not null check (direction in ('rising','flat','falling')), input_growth numeric,
  inputs jsonb not null default '{}', primary key (category, week_end));

create table capex_briefs (week_end date primary key, body_md text not null,
  created_at timestamptz not null default now());

alter table announcement_triage enable row level security;
alter table capex_memberships enable row level security;
alter table capex_inputs enable row level security;
alter table capex_index enable row level security;
alter table capex_briefs enable row level security;
