-- R206: 回滚 V206（树版本自动记录）。
-- 自动记录的版本（confirmed_by 为空）无法满足旧的 NOT NULL 约束，回滚时删除；回滚后未确认的合并项目重新受旧确认门约束。

ALTER TABLE consol_scope_confirmations DROP CONSTRAINT IF EXISTS ck_consol_scope_confirmation_mode;
ALTER TABLE consol_scope_confirmations DROP COLUMN IF EXISTS confirmation_mode;
DELETE FROM consol_scope_confirmations WHERE confirmed_by IS NULL;
ALTER TABLE consol_scope_confirmations ALTER COLUMN confirmed_by SET NOT NULL;
