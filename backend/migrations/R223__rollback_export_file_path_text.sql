-- R215：回滚 V215 — file_path 由 TEXT 收回 VARCHAR(500)
--
-- 🔴 收窄是有损操作：若回滚时已存在长度 > 500 的路径，ALTER 会直接失败（22001）。
-- 这是有意的 —— 静默截断交付件路径会让下载指向不存在的文件。遇到失败请先清理超长路径。
-- 幂等：只在列存在且当前是 text 时收回。

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['export_job_attempts', 'export_job_items_v2'] LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = t
              AND column_name = 'file_path' AND udt_name = 'text'
        ) THEN
            EXECUTE format('ALTER TABLE %I ALTER COLUMN file_path TYPE varchar(500)', t);
        END IF;
    END LOOP;
END
$$;
