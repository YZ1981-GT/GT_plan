-- R188: 回滚 V188 —— section_number 恢复 VARCHAR(20)
-- 已有超过 20 字的编号时拒绝回滚（报错退出），不截断：截断会把不同章节压成同一个编号。

DO $$
DECLARE
    too_long integer;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'note_section_instances'
          AND column_name = 'section_number'
          AND character_maximum_length IS NULL
    ) THEN
        SELECT count(*) INTO too_long
        FROM note_section_instances
        WHERE length(section_number) > 20;
        IF too_long > 0 THEN
            RAISE EXCEPTION 'R188 拒绝回滚：note_section_instances 有 % 行 section_number 超过 20 字，恢复 VARCHAR(20) 会截断', too_long;
        END IF;
        ALTER TABLE note_section_instances
            ALTER COLUMN section_number TYPE VARCHAR(20);
    END IF;
END
$$;
