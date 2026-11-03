-- V227: attachment_lineage 增加项目归属列 project_id
-- spec formula-hub-integrity-closure（需求 7.1，ADR-FHIC-13，D9）
--
-- 1) 可空列：X1 的顺序是先迁移、后推送代码，其间仍在运行的旧代码写入的行不带该列，非空约束会让旧代码报错。
-- 2) 由 attachments.project_id 回填。
-- 3) 索引 (project_id, target_type, target_ref)：溯源附件查询按 项目 + 目标类型 + 位置引用 取数。
--
-- 不删行、不加外键：回收站的永久删除、批量删除、清空回收站与项目级联删除都会物理删除 attachments 行，
-- 外键会让这些清理报错。不因孤儿失败：附件已不存在的行（孤儿）与迁移后旧代码写入的行 project_id 为空，
-- 查询只认本项目的 project_id，空值行对任何项目都不可见。孤儿与仍为空的行只计数（RAISE NOTICE），
-- 明细由修复工具 backend/scripts/fix/attachment_lineage_orphans.py 逐行列出（--apply 先备份再回填、删孤儿）。
-- 回滚：R227。

ALTER TABLE attachment_lineage ADD COLUMN IF NOT EXISTS project_id UUID;

UPDATE attachment_lineage al
   SET project_id = a.project_id
  FROM attachments a
 WHERE a.id = al.attachment_id
   AND al.project_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_attachment_lineage_project_target
    ON attachment_lineage (project_id, target_type, target_ref);

DO $$
DECLARE
    orphan_rows integer;
    null_rows integer;
BEGIN
    SELECT count(*) INTO orphan_rows
      FROM attachment_lineage al
     WHERE NOT EXISTS (SELECT 1 FROM attachments a WHERE a.id = al.attachment_id);
    SELECT count(*) INTO null_rows
      FROM attachment_lineage
     WHERE project_id IS NULL;
    RAISE NOTICE 'V227 attachment_lineage.project_id: 孤儿 % 行（附件已不存在，保持为空），project_id 仍为空 % 行', orphan_rows, null_rows;
END
$$;
