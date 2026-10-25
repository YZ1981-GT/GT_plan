-- R177：回滚 V177
-- 注意：删除 node_key 前必须确认不存在多个节点行，否则恢复项目级唯一键会失败。

DROP INDEX IF EXISTS uq_cnd_project_year_section_node;
DROP INDEX IF EXISTS uq_cnd_legacy_project_year_section;

ALTER TABLE consol_note_data
    DROP CONSTRAINT IF EXISTS consol_note_data_project_id_year_section_id_key;

ALTER TABLE consol_note_data
    ADD CONSTRAINT consol_note_data_project_id_year_section_id_key
    UNIQUE (project_id, year, section_id);

ALTER TABLE consol_note_data
    DROP COLUMN IF EXISTS node_key;
