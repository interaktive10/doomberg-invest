-- 0008_ownership_versions_price_splits: ownership_q keeps every filed version of a quarter (M4 review R1-F2);
-- prices_w records a split seen only in a split-adjusted source (R1-F6).
--
-- §3 keys ownership_q by (company, quarter_end), so a revised shareholding pattern (or a later 13F data set for the
-- same quarter) replaced the row, and as_of(W) before the revision lost the version that was current at W: signals,
-- R5 and the bucket as of W changed after the fact (§8 M4-02). docs/SPEC_ISSUES.md 8's alternative, as in
-- fundamentals_q: filed_at joins the key and pipeline.db.pit.as_of().ownership() returns, per quarter, the latest
-- version filed by the cutoff (a full row before a promoter-only manual CSV row).
alter table ownership_q drop constraint ownership_q_pkey;
alter table ownership_q add primary key (company_id, quarter_end, filed_at);

-- the display view shows the version as_of() would pick today (same columns, so grants are kept)
create or replace view ownership_display_v with (security_invoker = true) as
  select distinct on (o.company_id, o.quarter_end)
    o.company_id, o.quarter_end, o.filed_at, o.inst_holders, o.inst_pct, o.fii_pct, o.dii_pct, o.promoter_pct,
    o.promoter_pledged_pct, o.source
  from ownership_q o
  order by o.company_id, o.quarter_end, (o.source = 'manual_csv'), o.filed_at desc;

-- A split seen only in a split-adjusted source (M4 review R1-F6). Stooq's history is split-adjusted, so a split
-- leaves no price jump; until a filing reports the post-split share count, price x the pre-split count is off by
-- the ratio. When a fresh download's closes for weeks already stored differ from them by a split ratio, the source
-- re-adjusted its history: the first week on the new basis gets the ratio (new shares per old share). Downloads
-- (upsert_prices) never overwrite it.
alter table prices_w add column split_ratio numeric;
