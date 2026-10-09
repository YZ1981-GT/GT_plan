-- V184: 扩展 consol_note_formula.source CHECK 约束，新增 'seed_sub'（子表种子）
-- spec: note-sub-table-formula-and-cross-check Phase 2

-- 先删旧 CHECK（IF EXISTS：首次部署可能没有该约束名）
DO $$ BEGIN
  ALTER TABLE consol_note_formula DROP CONSTRAINT IF EXISTS ck_consol_note_formula_source;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- 加新 CHECK（含 seed_sub）
ALTER TABLE consol_note_formula
  ADD CONSTRAINT ck_consol_note_formula_source
  CHECK (source IN ('seed', 'seed_sub', 'manual'));
