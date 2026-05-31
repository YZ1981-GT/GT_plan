-- R039: 回滚 V039 disclosure_notes 附注级穿透 provenance（consol-phase3-frontend-drilldown / T6）
--
-- 回滚顺序：先删 GIN 索引，再删两列（均 IF EXISTS 幂等，重复执行不抛 UndefinedObject）。

DROP INDEX IF EXISTS idx_disclosure_notes_consol_breakdown;

ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS consolidation_breakdown;
ALTER TABLE disclosure_notes DROP COLUMN IF EXISTS source_project_id;
