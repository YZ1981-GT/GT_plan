-- R019: 回滚 V019（删除 v2025-R5 初始版本）
-- 注意：仅删除模板版本行，关联的 workpaper_sheet_classification 行（template_version_id 外键）
-- 在删除前必须先清理或迁移到其他版本

-- 先解除关联（避免外键约束失败）
UPDATE workpaper_sheet_classification
SET template_version_id = NULL
WHERE template_version_id IN (
    SELECT id FROM workpaper_template_version WHERE version = 'v2025-R5'
);

-- 删除 v2025-R5 行
DELETE FROM workpaper_template_version WHERE version = 'v2025-R5';
