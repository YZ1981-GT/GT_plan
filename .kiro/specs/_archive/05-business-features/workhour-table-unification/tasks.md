# Implementation Plan: 工时表统一迁移

## Overview
将 work_hours(Phase9) 数据迁移到 work_hour_entries(Phase7) 并统一全栈消费路径。9 个任务组，7 波执行。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave-0", "tasks": ["1"], "description": "数据迁移 V117" },
    { "id": "wave-1", "tasks": ["2"], "description": "后端 batch-quick 端点" },
    { "id": "wave-2", "tasks": ["3", "4"], "description": "审批改造(并行)" },
    { "id": "wave-3", "tasks": ["5"], "description": "WeeklyTimesheet 改写" },
    { "id": "wave-4", "tasks": ["6"], "description": "统计+预算对齐" },
    { "id": "wave-5", "tasks": ["7"], "description": "兼容层" },
    { "id": "wave-6", "tasks": ["8"], "description": "集成验证" }
  ]
}
```

## Tasks

- [x] 1. V117 数据迁移脚本
  - [x] 1.1 创建 backend/migrations/V117__workhour_data_unification.sql
  - [x] 1.2 INSERT INTO work_hour_entries SELECT ... FROM work_hours JOIN staff_members ON staff_id (获取 user_id)
  - [x] 1.3 状态映射: confirmed→submitted, draft→draft, approved→approved, rejected→rejected
  - [x] 1.4 cycle 默认 'OTHER', date=work_date, 其余字段保留
  - [x] 1.5 ON CONFLICT (wp_id, item_id) DO NOTHING 幂等（按 user_id+project_id+date 唯一约束或简单 DO NOTHING）

- [x] 2. 后端新增 batch-quick 端点
  - [x] 2.1 workhour_entries.py 新增 POST /api/projects/{project_id}/workhours/batch-quick
  - [x] 2.2 Schema: items=[{date, hours, description?}] (cycle 固定 OTHER, 无需 wp_code/procedure)
  - [x] 2.3 upsert 语义: 同 user+project+date+cycle='OTHER' 有记录则更新 hours
  - [x] 2.4 权限: get_current_user (本人操作)
  - [x] 2.5 返回 {created, updated, total}

- [x] 3. 审批列表改造
  - [x] 3.1 workhour_list.py 的 list_workhours_for_approval 改查 work_hour_entries (JOIN projects+users)
  - [x] 3.2 workhours_weekly_summary 改查 work_hour_entries
  - [x] 3.3 状态统一为 draft/submitted/approved/rejected

- [x] 4. 审批服务改造
  - [x] 4.1 workhour_approve_service.py 改操作 WorkHourEntry 模型
  - [x] 4.2 状态转换: submitted→approved (批准) 或 submitted→draft+rejected_reason (退回)
  - [x] 4.3 SOD 守卫保留 (审批人≠被审批人, 通过 user_id 判断)

- [x] 5. WeeklyTimesheet 改写
  - [x] 5.1 loadRange 改调 listEntries(projectId, {start_date, end_date}) 按项目加载
  - [x] 5.2 由于 WeeklyTimesheet 显示多项目，需逐项目调或加跨项目端点
  - [x] 5.3 saveAll 改调 batch-quick 端点(按 projectId 分组提交)
  - [x] 5.4 适配 WorkHourEntryRecord → 现有 recordMap 结构(date 字段名对齐)
  - [x] 5.5 去除对 listWorkHours/createWorkHour/updateWorkHour 的依赖

- [x] 6. 统计+预算对齐
  - [x] 6.1 WorkHourStatsPanel 改用 listEntries 或新增跨项目汇总端点
  - [x] 6.2 workhour_budget.py 改查 work_hour_entries 聚合 actual_hours
  - [x] 6.3 WorkHourService.ai_suggest 返回 cycle 字段

- [x] 7. 兼容层
  - [x] 7.1 workhours.py 的 GET /api/staff/{id}/work-hours 改为从 work_hour_entries 查询
  - [x] 7.2 POST /api/staff/{id}/work-hours 代理写入 work_hour_entries
  - [x] 7.3 PUT /api/work-hours/{id} 代理更新 work_hour_entries
  - [x] 7.4 返回格式保持旧 schema (id/staff_id/project_id/work_date/hours/status/...)

- [x] 8. 集成验证
  - [x] 8.1 get_diagnostics 全文件零错误
  - [x] 8.2 确认 work_hours 表 ORM 标记 deprecated 注释
  - [x] 8.3 确认新数据只写 work_hour_entries

## Notes
- work_hours 表和 ORM 保留不删（向后兼容 + 历史数据可查）
- work_hour_entries 表缺少 staff_id 列——对于 WeeklyTimesheet 场景，通过 user_id 关联 staff_members 获取
- batch-quick 端点与现有 batch-submit 不同：batch-quick 是 upsert 填报，batch-submit 是状态转换(draft→submitted)
- 最终目标：work_hour_entries 是唯一写入真源，work_hours 只读保留
