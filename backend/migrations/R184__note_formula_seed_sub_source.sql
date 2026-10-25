-- R184: 回滚 V184——恢复旧 CHECK
DO $$ BEGIN
  ALTER TABLE consol_note_formula DROP CONSTRAINT IF EXISTS ck_consol_note_formula_source;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

ALTER TABLE consol_note_formula
  ADD CONSTRAINT ck_consol_note_formula_source
  CHECK (source IN ('seed', 'manual'));
