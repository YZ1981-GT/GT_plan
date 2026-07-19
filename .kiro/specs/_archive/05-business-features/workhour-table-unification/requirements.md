# Requirements Document

## Introduction
当前工时模块有两套并行表：`work_hours`(Phase9, staff_id 关联, 粗粒度) 和 `work_hour_entries`(Phase7, user_id 关联, 细粒度 cycle/wp_code/procedure)。两表独立存储同类数据，导致：日合计无法跨表校验、审批流分裂(3态 vs 4态)、统计口径不一致。本需求将两表统一到 `work_hour_entries` 作为唯一真源。

## Glossary
- **work_hours**: Phase9 表, staff_id+project_id+work_date 粒度, status: draft/confirmed/approved/rejected
- **work_hour_entries**: Phase7 表, user_id+project_id+date+cycle 粒度, status: draft/submitted/approved/rejected
- **WeeklyTimesheet**: 快速填报组件(日/周视图)，当前写 work_hours

## Requirements

### Req-1: 数据迁移
The system shall 提供 V117 SQL 迁移脚本，将 `work_hours` 现有数据迁移到 `work_hour_entries`（staff_id→user_id 通过 staff_members.user_id 关联；work_date→date；cycle 默认 'OTHER'；保留 id/hours/description/status 映射: confirmed→submitted）。

### Req-2: WeeklyTimesheet 改写
The system shall 修改 WeeklyTimesheet 组件，使其读写 `work_hour_entries` 表（通过 workhour_entries 端点），不再使用 Phase9 的 `/api/staff/{id}/work-hours` 端点。

### Req-3: 批量保存对齐
The system shall 将 `/api/staff/{id}/work-hours/batch` 端点改为写入 `work_hour_entries` 表（cycle 默认 'OTHER'，无 wp_code/procedure 时为 null）。

### Req-4: WorkHoursPage 统计源统一
The system shall 修改 WorkHourStatsPanel 从 `work_hour_entries` 端点取数据（通过 listEntries 而非 listWorkHours）。

### Req-5: 审批流统一
The system shall 统一审批状态为 4态（draft/submitted/approved/rejected），`workhour_list.py` 和 `workhour_approve.py` 改为查询 `work_hour_entries` 表。

### Req-6: 旧表保留只读
The system shall 保留 `work_hours` 表及 ORM 模型（不删除），但标记为 deprecated，新数据不再写入。迁移后旧端点返回空并引导到新端点。

### Req-7: 向后兼容
The system shall 保持 `/api/staff/{id}/work-hours` GET 端点可用（作为兼容层，从 work_hour_entries 查询并按旧格式返回），在6个月后可考虑移除。

### Req-8: AI 建议对齐
The system shall 修改 WorkHourService.ai_suggest 生成的建议格式对齐 WorkHourEntry schema（含 cycle 字段）。

### Req-9: 预算对比对齐
The system shall 修改 `workhour_budget.py` 从 `work_hour_entries` 聚合实际工时（替代 work_hours）。
