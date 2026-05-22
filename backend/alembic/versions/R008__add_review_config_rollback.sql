-- R008: 回滚 review_config + WpReviewStatus level3/level4
ALTER TABLE projects DROP COLUMN IF EXISTS review_config;
-- 注意：PostgreSQL 不支持 DROP VALUE from enum，level3/level4 值将保留但不影响功能
