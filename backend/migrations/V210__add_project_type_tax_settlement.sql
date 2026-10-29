-- V210: projecttype 枚举补「企业所得税汇算清缴」值
--
-- 来源：代码改动清单（对比 6cc85dc35）「三、建项向导」，原清单编号 V206（已被
-- V206__consol_scope_version_auto_record 占用）故顺延至 V210。
--
-- 背景：ORM ProjectType（backend/app/models/base.py）已含
-- enterprise_income_tax_settlement，且现网库中已有项目行使用该值，但**全仓无迁移
-- 记录该枚举值** —— 新库 / 新部署按迁移建库时会缺这个 label，建项选该类型即 500。
-- 本迁移补齐该缺口（先例：V053 补 capital_verification / tax_audit 同样场景）。
--
-- 事务安全（与 V109 同款论证）：
-- MigrationRunner 把整个文件放在一个事务里逐语句执行。PG 12+ 允许在事务块内
-- ALTER TYPE ... ADD VALUE，限制只是「新值不能在同一事务内被使用」。本迁移
-- 仅添加 label、不写入任何使用该值的数据，故单事务执行安全。
--
-- 幂等：ADD VALUE IF NOT EXISTS（PG 9.3+），可重复执行。

ALTER TYPE projecttype ADD VALUE IF NOT EXISTS 'enterprise_income_tax_settlement';
