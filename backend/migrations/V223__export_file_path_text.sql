-- V215: export 任务表的 file_path 由 VARCHAR(500) 放宽为 TEXT（对齐 ORM，清掉 schema drift）
--       （号码：实施时现扫本地与 origin 最高均为 V214，本迁移取 V215）
--       （spec runtime-performance-and-reload-hardening-followup 任务 2b）
--
-- ── 为什么 ──────────────────────────────────────────────────────────────────
-- /api/health 的 schema_drift 常驻 4 条 type_mismatch，其中两条是 file_path：
--   export_job_attempts.file_path   ORM=TEXT vs DB=VARCHAR(500)
--   export_job_items_v2.file_path   ORM=TEXT vs DB=VARCHAR(500)
-- V181 建表时写的 VARCHAR(500)，而两张表的 ORM 都声明 sa.Text、写入方写的是交付件绝对/相对
-- 路径（版本化文件名会追加 _v<n>，长度无上界保证）。另两条（error_type / diagnostic_detail）
-- 的对齐方向相反 —— 那两列 DB 的 TEXT 才是对的，改的是 ORM，见 phase13_models.py 的注释。
--
-- 方向按「不让任何现有写入失败」选：VARCHAR(500) → TEXT 是放宽，既有数据与写入方都不受影响
-- （现查两表 file_path 全为 NULL，attempts 3 行 / items 17 行）。
-- 幂等：只在列存在且仍不是 text 时转。回滚见 R215。

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['export_job_attempts', 'export_job_items_v2'] LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = t
              AND column_name = 'file_path' AND udt_name <> 'text'
        ) THEN
            EXECUTE format('ALTER TABLE %I ALTER COLUMN file_path TYPE text', t);
        END IF;
    END LOOP;
END
$$;

COMMENT ON COLUMN export_job_attempts.file_path IS
  '本次 attempt 产出的交付件路径（TEXT：版本化文件名会追加 _v<n>，不设长度上界）';
COMMENT ON COLUMN export_job_items_v2.file_path IS
  '该 item 当前产出的交付件路径（TEXT：与 attempt 同口径）';
