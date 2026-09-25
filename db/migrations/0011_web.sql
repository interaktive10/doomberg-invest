-- 0011 (M7): what the web app writes beyond §3 (BRIEF §6, §1.8, §11.9; docs/SPEC_ISSUES.md 28).
--   1. screens: saved screener specs (the same JSON `screen(spec)` takes).
--   2. reviews: a review after a quarterly filing: the pack diff since the last review, and Manzoor's verdict
--      (intact / weakened / broken) with a note.
--   3. candidate_actions: "research" and "dismiss" on the Candidates screen; a dismissal needs a reason.
--   4. app_settings: the discipline rule (a thesis must be >= N weeks old before a start_position entry).
--   5. theses.accepted_at (when a card became a thesis) and dismissed_reason; journal.override_reason (a
--      start_position entry before the discipline window needs one). Private tables stay private: RLS on, no
--      anon/authenticated grants (0002's defaults), service_role only.
--   6. company_series: each company's per-quarter chart series as of its latest scored week, computed by the weekly
--      signals run with the §4.6 definitions (pipeline/signals/weekly.py series_points; M7 review R1-F5).
--   7. llm_use_7d: LLM calls by provider over 7 days, counted in the database like the digest's
--      thesis_repo.llm_use (PostgREST returns at most max_rows rows; M7 review R1-F6).
create table screens (id uuid primary key default gen_random_uuid(), name text unique not null check (length(trim(name)) > 0),
  spec jsonb not null, created_at timestamptz not null default now(), updated_at timestamptz not null default now());
create table reviews (id uuid primary key default gen_random_uuid(), thesis_id uuid not null references theses on delete cascade,
  period_end date, pack_diff jsonb not null default '{}', verdict text check (verdict in ('intact','weakened','broken')),
  note text, created_at timestamptz not null default now(), decided_at timestamptz);
create index reviews_thesis on reviews (thesis_id, created_at desc);
-- One review per thesis and quarter: a page render that creates it twice (two tabs) inserts it once.
create unique index reviews_thesis_period on reviews (thesis_id, period_end);
-- A kill criterion that moves a thesis to Review without a new quarter gets one open review (no quarter) to record a
-- verdict on (M7 review R1-F1).
create unique index reviews_one_open_kill on reviews (thesis_id) where period_end is null and verdict is null;
create table candidate_actions (id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies on delete cascade, week_end date not null,
  action text not null check (action in ('research','dismiss')), reason text,
  created_at timestamptz not null default now(),
  check (action <> 'dismiss' or length(trim(coalesce(reason, ''))) > 0));
create table app_settings (key text primary key, value jsonb not null, updated_at timestamptz not null default now());
insert into app_settings (key, value) values ('position_min_thesis_weeks', '4');

create table company_series (company_id uuid primary key references companies on delete cascade,
  week_end date not null, points jsonb not null, updated_at timestamptz not null default now());

create view llm_use_7d with (security_invoker = true) as
  select provider, count(*)::int as calls, (count(*) filter (where ok))::int as ok,
    (count(*) filter (where not ok and error like '%: 429%'))::int as rate_limited,
    coalesce(sum(tokens_in), 0)::bigint as tokens_in, coalesce(sum(tokens_out), 0)::bigint as tokens_out
  from llm_calls where created_at >= now() - interval '7 days' group by provider;
revoke all on llm_use_7d from anon, authenticated;
grant select on llm_use_7d to service_role;

alter table theses add column accepted_at timestamptz;
alter table theses add column dismissed_reason text;
alter table journal add column override_reason text;

alter table screens enable row level security;
alter table reviews enable row level security;
alter table candidate_actions enable row level security;
alter table app_settings enable row level security;
alter table company_series enable row level security;
