-- R210: 回滚 V210（projecttype 枚举值 enterprise_income_tax_settlement）
--
-- ⚠ PG 枚举值一经加入**不可物理移除**（无 ALTER TYPE ... DROP VALUE）。
-- 强行移除需重建类型并改写所有依赖列，风险远大于收益，故本回滚为**空操作**。
-- 同款处置先例见 R109（userrole / projectuserrole 补 eqcr 的回滚说明）。
--
-- 回滚语义：仅由 MigrationRunner.rollback_to() 删除 schema_version 登记行，
-- 使该版本可被重新应用（ADD VALUE IF NOT EXISTS 幂等，重复应用无副作用）。
-- 残留的枚举 label 不影响旧代码：ORM 不认的值只在读到该值的行时才报错，
-- 而回滚场景下不应再有新行写入该类型。

-- 无 DDL（PG 枚举值不可移除）。
SELECT 1;
