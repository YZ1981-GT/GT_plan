-- V243：合并附注来源投影（consolidation-run-and-workpaper-lifecycle-closure 批 5 / ADR-CRW-005）
--
-- 整章级快速投影：source_mode 是最后一个写入方的分类，格级所有权仍以
-- data.manual_cells / locked_cells / _detail_provenance / _subtree_provenance / last_formula_value 为准。
-- source_operation_id/source_revision 只有 operation 触发的写入才带值。

ALTER TABLE consol_note_data
    ADD COLUMN IF NOT EXISTS source_mode VARCHAR(30),
    ADD COLUMN IF NOT EXISTS source_operation_id UUID,
    ADD COLUMN IF NOT EXISTS source_revision INTEGER,
    ADD COLUMN IF NOT EXISTS source_digest CHAR(64);

CREATE INDEX IF NOT EXISTS ix_cnd_source_mode
    ON consol_note_data (project_id, year, source_mode)
    WHERE source_mode IS NOT NULL;

COMMENT ON COLUMN consol_note_data.source_mode IS
    '章节级来源投影: detail_mapping / subtree_aggregate / formula / manual / mixed';
COMMENT ON COLUMN consol_note_data.source_operation_id IS
    '最后一次 operation 触发的写入批次（手工保存为 NULL）';
COMMENT ON COLUMN consol_note_data.source_digest IS
    '最后一次写入的内容摘要（SHA-256，用于变化检测）';
