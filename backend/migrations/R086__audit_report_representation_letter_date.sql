-- Rollback V086: 删除管理层声明书日期列
ALTER TABLE audit_report DROP COLUMN IF EXISTS representation_letter_date;
