-- R022: 回滚 V022（cell_annotations.annotation_type）。
DO $$
BEGIN
    IF to_regclass('public.cell_annotations') IS NOT NULL
       AND EXISTS (SELECT 1 FROM cell_annotations WHERE annotation_type IS NOT NULL AND annotation_type <> 'comment') THEN
        RAISE EXCEPTION 'R022 拒绝回滚：cell_annotations 已保存非默认 annotation_type';
    END IF;
END $$;
DROP INDEX IF EXISTS idx_cell_annotations_type_object;
ALTER TABLE cell_annotations DROP COLUMN IF EXISTS annotation_type;
