-- R036: 回滚 consol_trial.is_stale 列（原编号 R029，随 V029→V036 重编号同步改为 R036）
DROP INDEX IF EXISTS idx_consol_trial_stale;
ALTER TABLE consol_trial DROP COLUMN IF EXISTS is_stale;
