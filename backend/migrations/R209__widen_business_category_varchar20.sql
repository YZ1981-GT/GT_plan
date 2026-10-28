-- R209: 回滚 V209 — 缩回 VARCHAR(10)
-- 前提：数据长度不超过 10 字符时安全
ALTER TABLE projects
    ALTER COLUMN business_category TYPE VARCHAR(10);
