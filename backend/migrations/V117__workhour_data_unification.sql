-- V117: 工时表统一迁移 — work_hours → work_hour_entries
-- 将 Phase9 work_hours 表的历史数据迁移到 Phase7 work_hour_entries 表
-- work_hour_entries 成为唯一写入真源，work_hours 保留只读
--
-- 幂等：NOT EXISTS 子查询跳过已迁移的行（按 user_id+project_id+date+cycle='OTHER' 判重）
-- 跳过：staff_members.user_id IS NULL 的记录（无法关联 user）
-- 跳过：work_hours.is_deleted = true 的记录
-- 状态映射：confirmed → submitted，其余保留

INSERT INTO work_hour_entries (
    id,
    user_id,
    project_id,
    date,
    hours,
    cycle,
    wp_code,
    procedure,
    description,
    status,
    submitted_at,
    approved_by,
    approved_at,
    rejected_reason,
    created_at,
    updated_at
)
SELECT
    gen_random_uuid(),
    sm.user_id,
    wh.project_id,
    wh.work_date,
    wh.hours,
    'OTHER',
    NULL,
    NULL,
    wh.description,
    CASE wh.status
        WHEN 'confirmed' THEN 'submitted'
        ELSE wh.status
    END,
    CASE WHEN wh.status IN ('confirmed', 'submitted') THEN wh.updated_at ELSE NULL END,
    wh.approved_by,
    wh.approved_at,
    wh.rejected_reason,
    wh.created_at,
    wh.updated_at
FROM work_hours wh
JOIN staff_members sm ON wh.staff_id = sm.id
WHERE wh.is_deleted = false
  AND sm.user_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM work_hour_entries whe
    WHERE whe.user_id = sm.user_id
      AND whe.project_id = wh.project_id
      AND whe.date = wh.work_date
      AND whe.cycle = 'OTHER'
  );

-- 添加注释标记 work_hours 为 deprecated
COMMENT ON TABLE work_hours IS 'DEPRECATED: 已被 work_hour_entries 替代(V117迁移)。保留只读，新数据写入 work_hour_entries。';
