-- R211: 回滚 V211（users.full_name / parent_partner_id / dept_id）。
ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_parent_partner;
DROP INDEX IF EXISTS idx_users_parent_partner;
ALTER TABLE users DROP COLUMN IF EXISTS full_name;
ALTER TABLE users DROP COLUMN IF EXISTS parent_partner_id;
ALTER TABLE users DROP COLUMN IF EXISTS dept_id;
