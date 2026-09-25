-- 0005 (M4): what the weekly scoring run needs beyond §3.
--   1. corp_events kind 'acquisition' (US 8-K item 2.01), so R4 can tell dilution from an acquisition (§1.5).
--   2. shortlists: the weekly focus list (§4.8.6), which also carries the 12-week novelty rule.
--   3. company_metrics: the latest screener metrics per company (one row each, overwritten weekly).
--   4. The screener API (§6 "Screener", M4): screener_v, one row per company for the latest scored week, and
--      screen(spec jsonb), a fixed set of optional filters the web app calls as an RPC with service_role.

alter table corp_events drop constraint corp_events_kind_check;
alter table corp_events add constraint corp_events_kind_check check (kind in ('auditor_change','late_filing',
  'spinoff','demerger','reorganization','rights_issue','index_change','announcement','acquisition'));

create table shortlists (week_end date not null, company_id uuid not null references companies on delete cascade,
  rank int not null check (rank >= 1), evidence numeric not null, gap numeric, primary key (week_end, company_id));
create index shortlists_company on shortlists (company_id, week_end);

create table company_metrics (company_id uuid primary key references companies on delete cascade,
  week_end date not null, metrics jsonb not null default '{}');

alter table shortlists enable row level security;
alter table company_metrics enable row level security;

create view screener_v with (security_invoker = true) as
  with latest as (select max(week_end) as week_end from scores)
  select c.id as company_id, c.market, c.name, c.ticker, c.nse_symbol, c.sector, c.industry, c.capex_desk,
         s.week_end, s.evidence, s.gap, s.families, s.bucket, s.weights_version,
         coalesce((select array_agg(v.signal_id order by v.signal_id) from signal_values v
                    where v.company_id = s.company_id and v.week_end = s.week_end and v.fired), '{}') as fired_signals,
         coalesce((select array_agg(r.flag_id order by r.flag_id) from redflag_values r
                    where r.company_id = s.company_id and r.week_end = s.week_end
                      and r.inputs->>'status' = 'fired'), '{}') as red_flags,
         exists (select 1 from redflag_values r where r.company_id = s.company_id and r.week_end = s.week_end
                    and r.hard and r.inputs->>'status' = 'fired') as hard_flag,
         (select (x.inputs->>'score')::numeric from context_values x
           where x.company_id = s.company_id and x.week_end = s.week_end and x.metric_id = 'C1') as c1,
         (select (x.inputs->>'score')::numeric from context_values x
           where x.company_id = s.company_id and x.week_end = s.week_end and x.metric_id = 'C2') as c2,
         (select (x.inputs->>'score')::numeric from context_values x
           where x.company_id = s.company_id and x.week_end = s.week_end and x.metric_id = 'C3') as c3,
         (select (x.inputs->>'score')::numeric from context_values x
           where x.company_id = s.company_id and x.week_end = s.week_end and x.metric_id = 'C4') as c4,
         coalesce(m.metrics, '{}') as metrics
    from scores s
    join latest l on s.week_end = l.week_end
    join companies c on c.id = s.company_id
    left join company_metrics m on m.company_id = s.company_id;

-- One metric filter: {"metric": "<key in metrics>", "op": ">=|<=|>|<", "value": <number>}. A company without the
-- metric doesn't pass.
create or replace function screen_metric_ok(p_metrics jsonb, p_filter jsonb)
returns boolean
language sql
immutable
set search_path = public
as $$
  select coalesce(case p_filter->>'op'
    when '>=' then (p_metrics->>(p_filter->>'metric'))::numeric >= (p_filter->>'value')::numeric
    when '<=' then (p_metrics->>(p_filter->>'metric'))::numeric <= (p_filter->>'value')::numeric
    when '>' then (p_metrics->>(p_filter->>'metric'))::numeric > (p_filter->>'value')::numeric
    when '<' then (p_metrics->>(p_filter->>'metric'))::numeric < (p_filter->>'value')::numeric
  end, false)
$$;

-- The spec (pipeline/screener.py ScreenSpec is the contract; every key optional): market, capex_desk, sector,
-- buckets[], min_evidence, min_gap, signals_any[], families_all[], exclude_hard_flags, metrics[], limit.
create or replace function screen(p jsonb)
returns setof screener_v
language sql
stable
security invoker
set search_path = public
as $$
  select s.* from screener_v s
   where (p->>'market' is null or s.market = p->>'market')
     and (p->>'capex_desk' is null or s.capex_desk = (p->>'capex_desk')::boolean)
     and (p->>'sector' is null or s.sector = p->>'sector')
     and (p->'buckets' is null or s.bucket in (select jsonb_array_elements_text(p->'buckets')))
     and (p->>'min_evidence' is null or s.evidence >= (p->>'min_evidence')::numeric)
     and (p->>'min_gap' is null or s.gap >= (p->>'min_gap')::numeric)
     and (p->'signals_any' is null or s.fired_signals && array(select jsonb_array_elements_text(p->'signals_any')))
     and (p->'families_all' is null or s.families @> array(select jsonb_array_elements_text(p->'families_all')))
     and (not coalesce((p->>'exclude_hard_flags')::boolean, false) or not s.hard_flag)
     and not exists (select 1 from jsonb_array_elements(coalesce(p->'metrics', '[]'::jsonb)) f
                      where not screen_metric_ok(s.metrics, f))
   order by s.evidence desc, s.gap desc nulls last, s.company_id
   limit least(coalesce((p->>'limit')::int, 500), 2000)
$$;

revoke all on screener_v from anon, authenticated;
grant select on screener_v to service_role;
revoke all on function screen(jsonb) from public;
revoke all on function screen_metric_ok(jsonb, jsonb) from public;
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on function screen(jsonb) from anon, authenticated;
    revoke all on function screen_metric_ok(jsonb, jsonb) from anon, authenticated;
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant execute on function screen(jsonb) to service_role;
    grant execute on function screen_metric_ok(jsonb, jsonb) to service_role;
  end if;
end $$;
