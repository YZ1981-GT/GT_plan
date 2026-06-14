-- R077: 回滚 projects.business_category
ALTER TABLE projects DROP COLUMN IF EXISTS business_category;
