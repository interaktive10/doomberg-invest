-- 0012: US weekly prices come from Yahoo's chart endpoint, not Stooq (docs/SPEC_ISSUES.md 37). The weekly run records
-- source_health under 'yahoo' now; the 'stooq' row would keep its stale flag forever and with it the banner in the
-- web app and the digest, so it goes. prices_w keeps its rows (their source column says where each came from).
delete from source_health where source = 'stooq';
