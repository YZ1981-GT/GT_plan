-- R187: 回滚 V187 附注内容模板与正文批量应用
-- 按外键依赖反序删除；历史数据会永久丢失，仅用于开发回滚。

DROP TABLE IF EXISTS note_text_batch_applications;
ALTER TABLE IF EXISTS note_content_templates
    DROP CONSTRAINT IF EXISTS fk_nct_current_version;
DROP TABLE IF EXISTS note_content_template_versions;
DROP TABLE IF EXISTS note_content_templates;
