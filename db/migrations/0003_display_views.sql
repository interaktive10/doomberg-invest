-- 0003_display_views: read-only views for the web app (docs/SPEC_ISSUES.md 6).
--
-- The guard's pit_rule allows reads of fundamentals_q, ownership_q, insider_events and corp_events only inside
-- pipeline/db/pit.py, and web/lib is scanned. The Company page still has to chart them. These views are the web's
-- only door to those tables. They are for DISPLAY of the latest known values, never for computation:
--   - pipeline/ and scripts/ must not read *_display_v (tests/db/test_display_views.py enforces it);
--   - signals, scores, packs and the Lab read through pipeline.db.pit.as_of() only.
-- security_invoker = true: a view runs with the caller's rights, so RLS and the anon/authenticated revokes still
-- apply (a default, owner-rights view would let PostgREST's anon role read around RLS on Supabase).

create view fundamentals_display_v with (security_invoker = true) as
  select distinct on (f.company_id, f.period_end)
    f.company_id, f.period_end, f.fiscal_label, f.filed_at,
    f.revenue, f.op_income, f.net_income, f.pretax_income, f.tax_expense, f.cfo, f.capex, f.da, f.interest_expense,
    f.total_assets, f.cash, f.total_debt, f.equity, f.receivables, f.inventory, f.deferred_revenue, f.rpo,
    f.diluted_shares, f.shares_outstanding, f.currency, f.source
  from fundamentals_q f
  order by f.company_id, f.period_end, f.filed_at desc;

create view ownership_display_v with (security_invoker = true) as
  select o.company_id, o.quarter_end, o.filed_at, o.inst_holders, o.inst_pct, o.fii_pct, o.dii_pct, o.promoter_pct,
         o.promoter_pledged_pct, o.source
  from ownership_q o;

create view insider_events_display_v with (security_invoker = true) as
  select e.id, e.company_id, e.event_date, e.filed_at, e.person, e.role, e.kind, e.shares, e.value, e.currency,
         e.planned, e.source_url
  from insider_events e;

create view corp_events_display_v with (security_invoker = true) as
  select e.id, e.company_id, e.event_date, e.filed_at, e.kind, e.detail, e.source_url
  from corp_events e;

revoke all on fundamentals_display_v, ownership_display_v, insider_events_display_v, corp_events_display_v
  from anon, authenticated;
grant select on fundamentals_display_v, ownership_display_v, insider_events_display_v, corp_events_display_v
  to service_role;
