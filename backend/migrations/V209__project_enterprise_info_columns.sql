-- V209: projects 表新增企业信息 6 列（税审建项向导）
--
-- 来源：代码改动清单（对比 6cc85dc35）「三、建项向导」。原清单编号为 V205，
-- 但本仓库 V205__fix_export_schema_drift / V206__consol_scope_version_auto_record
-- 已占用该号段（MigrationRunner 按 version 数字去重，撞号会抛 RuntimeError），
-- 故顺延至 V209。
--
-- 设计要点：
-- 1. 全部可空，存量零回填 —— 历史项目不要求补录企业信息。
-- 2. 刻意用专列而非 JSONB：N5-6 等税审底稿按列查询取数，JSONB 需 ->> 转换
--    且无法建普通索引。
-- 3. 幂等：ADD COLUMN IF NOT EXISTS（可重复执行）。
-- 4. 三层一致：ORM backend/app/models/core.py Project + Schema
--    backend/app/models/audit_platform_schemas.py 同步。

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS legal_representative VARCHAR(100);

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS special_industry_type VARCHAR(32);

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS small_micro_enterprise_type VARCHAR(32);

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS tax_incentive_type VARCHAR(64);

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS branch_institution_type VARCHAR(32);

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS overseas_income_credit_method VARCHAR(32);

COMMENT ON COLUMN projects.legal_representative IS '法定代表人';
COMMENT ON COLUMN projects.special_industry_type IS '特殊行业类型：金融/保险/银行/证券';
COMMENT ON COLUMN projects.small_micro_enterprise_type IS '小微企业类型';
COMMENT ON COLUMN projects.tax_incentive_type IS '税收优惠类型';
COMMENT ON COLUMN projects.branch_institution_type IS '总分机构类型';
COMMENT ON COLUMN projects.overseas_income_credit_method IS '境外所得抵免方式';
