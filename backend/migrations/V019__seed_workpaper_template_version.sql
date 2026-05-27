-- V019: 初始化 workpaper_template_version 表（v2025-R5 当前版本）
-- 配套迁移：V018 建表，V019 插数据
-- 幂等：ON CONFLICT DO NOTHING
-- 关联 spec: workpaper-html-renderer (task 1.1)

-- 插入 v2025-R5 当前版本（致同 2025 修订版第 5 次）
INSERT INTO workpaper_template_version (id, version, release_date, source, is_current, created_at)
VALUES (
    gen_random_uuid(),
    'v2025-R5',
    '2025-01-01',
    '致同总所',
    TRUE,
    NOW()
)
ON CONFLICT (version) DO NOTHING;

-- 确保只有一行 is_current = TRUE（如已存在多条则将其他设为 FALSE）
UPDATE workpaper_template_version
SET is_current = FALSE
WHERE version != 'v2025-R5' AND is_current = TRUE;
