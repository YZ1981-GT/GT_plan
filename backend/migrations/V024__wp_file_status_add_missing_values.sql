-- V024: 补齐 wp_file_status 枚举缺失值
--
-- 问题：PG enum 只有 (draft, edit_complete, review_level1_passed, review_level2_passed, archived)
--      但 ORM (WpFileStatus) 还有 under_review / revision_required / review_passed，多处 service 引用这些值
--      调用 /api/projects/list-with-progress 时 SQL CAST 'review_passed'::wp_file_status 抛
--      asyncpg.exceptions.InvalidTextRepresentationError 导致仪表盘最近项目空白
--
-- 修复：补齐三个缺失枚举值（idempotent：已存在则跳过）
-- 注意：PG 不支持事务内 ALTER TYPE ADD VALUE + 后续使用，必须 commit 后才生效；
--       D6 MigrationRunner 每条 SQL 单独事务，刚 ADD 完即可下次启动可用

DO $body$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = 'wp_file_status' AND e.enumlabel = 'under_review'
    ) THEN
        ALTER TYPE wp_file_status ADD VALUE 'under_review';
    END IF;
END
$body$;

DO $body$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = 'wp_file_status' AND e.enumlabel = 'revision_required'
    ) THEN
        ALTER TYPE wp_file_status ADD VALUE 'revision_required';
    END IF;
END
$body$;

DO $body$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = 'wp_file_status' AND e.enumlabel = 'review_passed'
    ) THEN
        ALTER TYPE wp_file_status ADD VALUE 'review_passed';
    END IF;
END
$body$;
