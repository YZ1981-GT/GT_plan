# Design Document

## Overview
将 `work_hours`(Phase9) 数据迁移到 `work_hour_entries`(Phase7) 并统一前后端消费路径。迁移后 `work_hour_entries` 成为工时唯一真源，`work_hours` 保留为只读历史表。

## Architecture
```
统一前:
  WeeklyTimesheet → /api/staff/{id}/work-hours → work_hours (Phase9)
  WorkHourEntryDialog → /api/projects/{id}/workhours → work_hour_entries (Phase7)
  审批 → /api/workhours → work_hours
  预算 → work_hours

统一后:
  WeeklyTimesheet → /api/projects/{id}/workhours/batch-quick → work_hour_entries
  WorkHourEntryDialog → /api/projects/{id}/workhours → work_hour_entries (不变)
  审批 → /api/workhours → work_hour_entries
  预算 → work_hour_entries
  /api/staff/{id}/work-hours → 兼容层(读 work_hour_entries 转格式)
```

## Components and Interfaces

### V117 迁移脚本
```sql
-- 从 work_hours JOIN staff_members 获取 user_id，INSERT INTO work_hour_entries
-- 状态映射: confirmed→submitted, 其余保留
-- cycle 默认 'OTHER'
-- ON CONFLICT DO NOTHING (幂等,重复迁移不报错)
```

### WeeklyTimesheet 改造
- 不再调 `/api/staff/{id}/work-hours`，改调项目级端点
- 需要知道 user 参与的项目列表（已有 getMyAssignments）
- 新增 `POST /api/projects/{id}/workhours/batch-quick` 端点(简化版 batch: 只需 date+hours+description，cycle 默认 OTHER)
- 读取用 `GET /api/projects/{id}/workhours`(已有，改为不传 status 默认返回全部)

### 审批改造
- `workhour_list.py` 的 `list_workhours_for_approval` 改查 work_hour_entries
- `workhour_approve_service.py` 改操作 work_hour_entries
- 状态映射统一为 4态

### 兼容层
- `/api/staff/{id}/work-hours` GET 改为：staff_id→user_id→查 work_hour_entries→转旧格式返回
- POST/PUT 端点改为代理写入 work_hour_entries

## Data Models
不新增表。work_hour_entries 已满足所有需求。work_hours 保留不动(只读)。

## Correctness Properties

| 属性 | 描述 |
|------|------|
| P1 | 迁移后 work_hour_entries 行数 ≥ 迁移前 work_hours 行数（不丢数据） |
| P2 | WeeklyTimesheet 保存后 work_hour_entries 有对应记录（不写 work_hours） |
| P3 | 审批操作更新的是 work_hour_entries.status，不碰 work_hours |
| P4 | 兼容层返回格式与旧 API 一致（id/staff_id/project_id/work_date/hours/status/...） |
| P5 | 日合计 24h 校验统一在 work_hour_entries 上执行 |

## Error Handling
- V117 迁移幂等(ON CONFLICT DO NOTHING)，重复运行安全
- staff_members.user_id 为 NULL 的记录跳过（无法关联 user）
- 旧端点写入失败时前端提示"请使用新版工时填报"

## Testing Strategy
- V117 迁移后用 SQL 验证行数匹配
- WeeklyTimesheet 保存后 DB 查 work_hour_entries 有记录
- 审批 batch-approve 后 work_hour_entries.status 变更
- 兼容层 GET 返回格式不变(回归测试)
