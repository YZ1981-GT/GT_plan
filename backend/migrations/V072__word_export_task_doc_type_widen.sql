-- V072: word_export_task.doc_type 列宽从 VARCHAR(20) 扩到 VARCHAR(50)
-- 根因: 'financial_report_unadjusted' = 26 字符 > 20 限制 → StringDataRightTruncationError
-- 影响: 全套生成第二步(未审财务报表) 100% 失败

ALTER TABLE word_export_task
    ALTER COLUMN doc_type TYPE VARCHAR(50);
