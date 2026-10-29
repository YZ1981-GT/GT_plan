-- R209: 回滚 V209（projects 企业信息 6 列）
--
-- 全部为 additive 可空列，删除即可完全还原。
-- ⚠ 执行会丢失已录入的企业信息数据，仅用于回退部署。

ALTER TABLE projects DROP COLUMN IF EXISTS legal_representative;
ALTER TABLE projects DROP COLUMN IF EXISTS special_industry_type;
ALTER TABLE projects DROP COLUMN IF EXISTS small_micro_enterprise_type;
ALTER TABLE projects DROP COLUMN IF EXISTS tax_incentive_type;
ALTER TABLE projects DROP COLUMN IF EXISTS branch_institution_type;
ALTER TABLE projects DROP COLUMN IF EXISTS overseas_income_credit_method;

-- schema_version 记录由 MigrationRunner.rollback_to() 统一删除
-- （DELETE FROM schema_version WHERE version > :target），本文件不自行维护。
