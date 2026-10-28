-- V214: 查询模板软删除（spec advanced-query-linkage-closure 任务 25；R9.5，ADR-AQL-11，design §8）。
--
-- 删除模板改为软删、进回收站（作者与 admin 可见、可恢复、可彻底删除）；原先 DELETE 直接硬删、无法找回。
--   - is_deleted / deleted_at 与 ORM SoftDeleteMixin 一致：新列带默认值 / 可空，存量行即「未删除」，旧代码照常读写。
--   - idx_cqt_live_updated：模板列表按「未删 + 最近修改」取候选。
--   - ck_custom_query_templates_scope：scope 只许 TemplateScopeAdapter 接受的六个值（规范值 private / team / project /
--     public，历史 global / personal 读取兼容）。旧库若由 scripts/_ensure_custom_query_tables.py 建表，同名约束只认
--     4 个值（没有 project / personal），「指定项目共享」一保存就违反约束 ⇒ 按定义换成新约束（只放宽，不收紧）。
-- 共享开发库本表 0 行：加列 / 建索引 / 加约束瞬时完成。
ALTER TABLE custom_query_templates ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT false;
ALTER TABLE custom_query_templates ADD COLUMN IF NOT EXISTS deleted_at timestamptz NULL;
CREATE INDEX IF NOT EXISTS idx_cqt_live_updated ON custom_query_templates (is_deleted, updated_at DESC);
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'custom_query_templates'::regclass AND conname = 'ck_custom_query_templates_scope'
          AND pg_get_constraintdef(oid) NOT LIKE '%''project''%'
    ) THEN
        ALTER TABLE custom_query_templates DROP CONSTRAINT ck_custom_query_templates_scope;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'custom_query_templates'::regclass AND conname = 'ck_custom_query_templates_scope'
    ) THEN
        ALTER TABLE custom_query_templates ADD CONSTRAINT ck_custom_query_templates_scope
            CHECK (scope IN ('private', 'team', 'project', 'public', 'global', 'personal'));
    END IF;
END $$;
