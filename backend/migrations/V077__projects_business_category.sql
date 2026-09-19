-- V077: projects 表新增 business_category（业务分类 A1~A8/B1~B6/C）
ALTER TABLE projects ADD COLUMN IF NOT EXISTS business_category VARCHAR(10) DEFAULT 'C';
