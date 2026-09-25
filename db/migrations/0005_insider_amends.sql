-- Review R2-F7 (M2): a Form 4/A amends one earlier Form 4, named by its filing date (dateOfOriginalSubmission). The
-- link lets readers replace the original's trades with the amendment's even when the amendment corrects a trade date
-- (pipeline/signals/insiders.latest_versions). Null for original filings and for India's disclosures.
alter table insider_events add column amends date;
