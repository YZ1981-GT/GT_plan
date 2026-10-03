-- V177：合并附注按企业树 node_key 隔离
--
-- 旧 API 不带 node_key 时继续使用 node_key IS NULL 的项目级兼容行；
-- 新 API 带 node_key 时按节点独立存储，避免不同企业节点共享同一附注数据。
-- 所有 DDL 幂等，可重复执行；回滚见 R177。

ALTER TABLE consol_note_data
    ADD COLUMN IF NOT EXISTS node_key VARCHAR(100);

-- V041 的 UNIQUE(project_id, year, section_id) 会阻止同一章节为多个节点保存数据。
-- 约束名称由 PostgreSQL 按 V041 的列名自动生成；同时兼容已被人工改名的环境。
ALTER TABLE consol_note_data
    DROP CONSTRAINT IF EXISTS consol_note_data_project_id_year_section_id_key;

-- 历史项目级行保持一章节一行；NULL 不参与节点级索引。
CREATE UNIQUE INDEX IF NOT EXISTS uq_cnd_legacy_project_year_section
    ON consol_note_data (project_id, year, section_id)
    WHERE node_key IS NULL;

-- 节点数据按项目、年度、章节、节点唯一。
CREATE UNIQUE INDEX IF NOT EXISTS uq_cnd_project_year_section_node
    ON consol_note_data (project_id, year, section_id, node_key)
    WHERE node_key IS NOT NULL;

COMMENT ON COLUMN consol_note_data.node_key IS
    '企业树节点键；NULL 表示 V041 项目级兼容行，非 NULL 时按节点隔离';
