-- R182: 回滚 V182
ALTER TABLE consol_note_data DROP COLUMN IF EXISTS last_formula_value;
ALTER TABLE consol_note_data DROP COLUMN IF EXISTS last_formula_run_id;
ALTER TABLE consol_note_data DROP COLUMN IF EXISTS locked_cells;
ALTER TABLE consol_note_data DROP CONSTRAINT IF EXISTS ck_cnd_cell_state;
ALTER TABLE consol_note_data DROP COLUMN IF EXISTS cell_state;
