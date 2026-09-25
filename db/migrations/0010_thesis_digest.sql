-- 0010 (M6): the thesis engine and the weekly digest (BRIEF §4.9, §4.12).
--   1. theses: one generated card (routine or fallback) per company and week, so thesis-ingest.yml can re-run on
--      the same push and upsert (M6-03); manual theses are not limited.
--   2. kill_criteria: `baseline` is the metric's value in the pack the card was written from (the `changes`
--      operator compares with it), `why` is the card's reason, and `triggered_week` dates the trigger for the
--      digest ("theses needing attention").
--   3. digests: the weekly digest's markdown (the GitHub issue body; the web Home screen shows the same).
create unique index theses_generated_week on theses (company_id, created_week) where author in ('routine', 'fallback');

alter table kill_criteria add column baseline numeric;
alter table kill_criteria add column why text;
alter table kill_criteria add column triggered_week date;
create index kill_criteria_thesis on kill_criteria (thesis_id);

create table digests (week_end date primary key, title text not null, body_md text not null, issue_number int,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now());
alter table digests enable row level security;
