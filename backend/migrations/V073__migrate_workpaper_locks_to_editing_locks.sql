-- V073: 将 workpaper_editing_locks 存量活跃锁迁入 editing_locks
-- 阶段 1 数据迁移：resource_type='workpaper', resource_id=wp_id::text
-- 只迁 released_at IS NULL 的活跃锁；同 wp_id 多活跃锁取 heartbeat_at 最新
-- 幂等：NOT EXISTS 守护 + uq_editing_locks_active 部分唯一索引兜底
-- 只读源表，不 UPDATE/DELETE workpaper_editing_locks

INSERT INTO editing_locks (
    id,
    resource_type,
    resource_id,
    holder_id,
    holder_name,
    acquired_at,
    heartbeat_at,
    released_at,
    created_at,
    updated_at
)
SELECT
    gen_random_uuid(),
    'workpaper',
    sub.wp_id::text,
    sub.staff_id,
    u.username,
    sub.acquired_at,
    sub.heartbeat_at,
    NULL,
    now(),
    now()
FROM (
    SELECT DISTINCT ON (wel.wp_id)
        wel.wp_id,
        wel.staff_id,
        wel.acquired_at,
        wel.heartbeat_at
    FROM workpaper_editing_locks wel
    WHERE wel.released_at IS NULL
    ORDER BY wel.wp_id, wel.heartbeat_at DESC
) sub
LEFT JOIN users u ON u.id = sub.staff_id
WHERE NOT EXISTS (
    SELECT 1
    FROM editing_locks el
    WHERE el.resource_type = 'workpaper'
      AND el.resource_id = sub.wp_id::text
      AND el.released_at IS NULL
);
