-- V101: 高级查询模块 — 模板项目组分享列（Advanced Query Module · Template Sharing）
--
-- 为 custom_query_templates（V052 起，scope=private/team/public/global 四值模型）
-- 新增 shared_project_ids UUID[] 列，承载 scope=team 的显式项目组分享语义：
-- 仅对 shared_project_ids 中有访问权的项目组成员可见可执行（见 requirements R13.3）。
--
-- 幂等铁律：列补齐用 DO $$ + information_schema.columns 检测列存在性再 ALTER，
-- 列确认存在后再 CREATE INDEX IF NOT EXISTS（禁止裸 CREATE INDEX 于列不确定表），
-- 确保重复运行不报错（避免旧表列不同导致索引报错）。

-- ① 新增模板分享列：shared_project_ids（GIN 可查的项目 ID 数组）
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='custom_query_templates'
                   AND column_name='shared_project_ids') THEN
    ALTER TABLE custom_query_templates
      ADD COLUMN shared_project_ids UUID[] NOT NULL DEFAULT '{}';
    -- shared_project_ids: 显式分享给的项目 ID 集合；scope=team 时生效
  END IF;
END $$;

-- ② 列存在性确认通过后再建 GIN 索引（支持数组包含查询，非裸 CREATE INDEX）
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name='custom_query_templates'
               AND column_name='shared_project_ids') THEN
    CREATE INDEX IF NOT EXISTS idx_cqt_shared_projects
      ON custom_query_templates USING gin (shared_project_ids);
  END IF;
END $$;
