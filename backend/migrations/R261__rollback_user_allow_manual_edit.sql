-- R261: 回滚 V261 账号「允许修改」开关
ALTER TABLE users DROP COLUMN IF EXISTS allow_manual_edit;
