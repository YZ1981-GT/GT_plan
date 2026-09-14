-- R072 rollback: 恢复 doc_type 为 VARCHAR(20)
-- 注意: rollback 后 doc_type > 20 字符的行将无法更新/插入

ALTER TABLE word_export_task
    ALTER COLUMN doc_type TYPE VARCHAR(20);
