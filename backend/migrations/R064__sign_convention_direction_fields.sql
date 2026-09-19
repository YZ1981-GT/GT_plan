-- R064: 回滚符号约定方向字段
-- 对应 V064__sign_convention_direction_fields.sql

-- 1. Drop direction_override table
DROP TABLE IF EXISTS direction_override;

-- 2. tb_aux_ledger: 移除发生方向和来源
ALTER TABLE tb_aux_ledger DROP COLUMN IF EXISTS entry_direction;
ALTER TABLE tb_aux_ledger DROP COLUMN IF EXISTS entry_direction_source;

-- 3. tb_ledger: 移除发生方向和来源
ALTER TABLE tb_ledger DROP COLUMN IF EXISTS entry_direction;
ALTER TABLE tb_ledger DROP COLUMN IF EXISTS entry_direction_source;

-- 4. tb_aux_balance: 移除方向字段
ALTER TABLE tb_aux_balance DROP COLUMN IF EXISTS opening_direction;
ALTER TABLE tb_aux_balance DROP COLUMN IF EXISTS opening_direction_source;
ALTER TABLE tb_aux_balance DROP COLUMN IF EXISTS closing_direction;
ALTER TABLE tb_aux_balance DROP COLUMN IF EXISTS closing_direction_source;
ALTER TABLE tb_aux_balance DROP COLUMN IF EXISTS sign_convention_version;
ALTER TABLE tb_aux_balance DROP COLUMN IF EXISTS sign_anomaly_flags;

-- 5. tb_balance: 移除方向字段
ALTER TABLE tb_balance DROP COLUMN IF EXISTS opening_direction;
ALTER TABLE tb_balance DROP COLUMN IF EXISTS opening_direction_source;
ALTER TABLE tb_balance DROP COLUMN IF EXISTS closing_direction;
ALTER TABLE tb_balance DROP COLUMN IF EXISTS closing_direction_source;
ALTER TABLE tb_balance DROP COLUMN IF EXISTS sign_convention_version;
ALTER TABLE tb_balance DROP COLUMN IF EXISTS sign_anomaly_flags;
