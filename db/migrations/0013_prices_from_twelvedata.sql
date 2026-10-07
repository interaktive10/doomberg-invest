-- 0013: US weekly prices come from Twelve Data, not Yahoo (docs/SPEC_ISSUES.md 38): Yahoo answered GitHub's runners
-- 429 from the first request (2026-10-07), which left its source_health row stale. The weekly run records
-- 'twelvedata' now; the 'yahoo' row would keep the banner up in the web app and the digest, so it goes.
delete from source_health where source = 'yahoo';
