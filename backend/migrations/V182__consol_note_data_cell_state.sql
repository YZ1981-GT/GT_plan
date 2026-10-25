-- V182: 合并附注持久化状态字段（改进 C）
-- 为 consol_note_data 增加 cell_state 和 last_formula_run_id，
-- 与 formula_push 的 FormulaPushState 三态判定对等。
-- cell_state: 'auto'=公式自动刷新 / 'manual'=用户手动编辑 / 'locked'=锁定不覆盖
-- locked_cells: JSONB 存储被锁定的单元格坐标列表 [{row_index, col_index}]
-- last_formula_run_id: 最近一次公式刷新的运行批次 UUID

ALTER TABLE consol_note_data
    ADD COLUMN IF NOT EXISTS cell_state VARCHAR(20) NOT NULL DEFAULT 'auto';

ALTER TABLE consol_note_data
    ADD COLUMN IF NOT EXISTS locked_cells JSONB NOT NULL DEFAULT '[]';

ALTER TABLE consol_note_data
    ADD COLUMN IF NOT EXISTS last_formula_run_id UUID;

ALTER TABLE consol_note_data
    ADD COLUMN IF NOT EXISTS last_formula_value JSONB;

-- CHECK 约束（cell_state 取值集合）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_cnd_cell_state'
    ) THEN
        ALTER TABLE consol_note_data
            ADD CONSTRAINT ck_cnd_cell_state
            CHECK (cell_state IN ('auto', 'manual', 'locked'));
    END IF;
END $$;
