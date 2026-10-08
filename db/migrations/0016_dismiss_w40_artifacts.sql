-- 0016: Manzoor dismissed the 2026-W40 theses for AMR and PFE (2026-10-08). Both reached the candidate bucket only
-- through the formula problems fixed in SPEC_ISSUES 41-43; the re-score after the fix dropped them. Only cards still
-- in research are touched, so a re-run changes nothing.
update theses t set state = 'dismissed', updated_at = now(),
  dismissed_reason = 'Formula artifact (SPEC_ISSUES 41-43): not a candidate after the fix.'
from companies c
where c.id = t.company_id and c.market = 'us' and c.ticker in ('AMR', 'PFE')
  and t.state = 'research' and t.created_week = '2026-10-02';
