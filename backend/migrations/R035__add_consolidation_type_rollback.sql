-- R035: 回滚 consolidation_type 列（原编号 R028，随 V028→V035 重编号同步改为 R035）
ALTER TABLE projects DROP COLUMN IF EXISTS consolidation_type;
