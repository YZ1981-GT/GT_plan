-- R092: Rollback A13 错报评价自动聚合

ALTER TABLE unadjusted_misstatements DROP COLUMN IF EXISTS prior_year_status;
ALTER TABLE unadjusted_misstatements DROP COLUMN IF EXISTS source_wp_code;
