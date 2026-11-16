-- R160: 回滚 V160（底稿行名映射及版本链）。
DO $$
BEGIN
    IF (to_regclass('public.workpaper_row_name_mapping_target') IS NOT NULL AND EXISTS (SELECT 1 FROM workpaper_row_name_mapping_target LIMIT 1))
       OR (to_regclass('public.workpaper_row_name_mapping') IS NOT NULL AND EXISTS (SELECT 1 FROM workpaper_row_name_mapping LIMIT 1)) THEN
        RAISE EXCEPTION 'R160 拒绝回滚：底稿行名映射/确认版本链存在';
    END IF;
END $$;
DROP TABLE IF EXISTS workpaper_row_name_mapping_target;
DROP TABLE IF EXISTS workpaper_row_name_mapping;
