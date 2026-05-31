-- V039: disclosure_notes 附注级穿透 provenance（consol-phase3-frontend-drilldown / Phase 3 / T6）
--
-- 设计要点（design.md §三组件3 / §四.4.1 / 需求 2.1 / 属性 T6 / ADR-CONSOL-302）：
-- 1. 附注级穿透要反查"该合并章节由哪些子公司哪些章节汇总而来"，需在 disclosure_notes
--    增 provenance 字段。V2 generate_full_consol_notes 汇总每章节时写入
--    consolidation_breakdown（哪些子公司贡献多少），穿透端点直接读，无需重算。
-- 2. source_project_id：该附注章节的来源合并母项目 id（穿透跳转/溯源用）。
-- 3. consolidation_breakdown：JSONB provenance，形如
--    {"by_company": [{company_code, company_name, section_title, amount}], "computed_at": "..."}
--    与 Phase 0 consol_trial.consolidation_breakdown（V034）provenance 形态对称。
-- 4. 三层一致铁律：本迁移 + ORM DisclosureNote.Mapped 字段 + service 读写齐全，
--    drift detector 0 漂移（属性 T6）。
-- 5. GIN 索引（软删除过滤）支撑 provenance 查询，类比 V034 consol_trial 的
--    idx_consol_trial_breakdown。
--
-- 全部 ALTER / CREATE INDEX 均幂等（ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS），
-- 重复执行不抛 DuplicateColumn/DuplicateTable，不中断 D6 管线。
--
-- D6 迁移系统说明：D6 MigrationRunner 启动时按目录扫描 V*.sql 执行（每条 SQL 独立事务）。
-- 本平台无法本地起 Docker/PG，幂等实测待 start-dev.bat 由用户验证。

ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS source_project_id UUID;
ALTER TABLE disclosure_notes ADD COLUMN IF NOT EXISTS consolidation_breakdown JSONB;

CREATE INDEX IF NOT EXISTS idx_disclosure_notes_consol_breakdown
  ON disclosure_notes USING gin (consolidation_breakdown) WHERE is_deleted = false;
