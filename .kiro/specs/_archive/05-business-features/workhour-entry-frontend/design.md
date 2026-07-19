# Design Document

## Overview
为 Phase7 WorkHourEntry 细粒度工时端点建立前端入口。包含填报弹窗、条目列表、项目级视图三个核心组件，以及 API 封装和路由注册。

## Architecture
```
WeeklyTimesheet (Phase9 快速填报, 不变)
    └─ 日视图项目卡片 → "📋 详细" → WorkHourEntryDialog

ProjectWorkHoursView (新建, /projects/:projectId/work-hours)
    ├─ WorkHourEntryList (el-table + 筛选 + 批量提交)
    ├─ WorkHourEntryDialog (填报/编辑弹窗)
    └─ 汇总卡片 (按循环/底稿统计)
```

## Components and Interfaces

### WorkHourEntryDialog.vue
- 路径: `components/workhour/WorkHourEntryDialog.vue`
- Props: `projectId: string`, `entryId?: string`, `date?: string`, `modelValue: boolean`
- Emits: `update:modelValue`, `saved`
- 功能: 创建/编辑工时条目表单 + 24h 前端校验 + cycle 自动推断

### WorkHourEntryList.vue
- 路径: `components/workhour/WorkHourEntryList.vue`
- Props: `projectId: string`
- 功能: 条目列表 + 日期/状态筛选 + 批量选择提交 + 操作(编辑/删除)

### ProjectWorkHoursView.vue
- 路径: `views/ProjectWorkHoursView.vue`
- 路由: `/projects/:projectId/work-hours`
- 功能: 汇总卡 + WorkHourEntryList + 新增按钮

### staffApi.ts 扩展
```typescript
interface WorkHourEntryRecord { id: string; user_id: string; project_id: string; date: string; hours: number; cycle: string; wp_code?: string; procedure?: string; description?: string; status: string; rejected_reason?: string; }
function listEntries(projectId: string, params?: { start_date?: string; end_date?: string }): Promise<WorkHourEntryRecord[]>
function createEntry(projectId: string, payload: { date: string; hours: number; cycle?: string; wp_code?: string; procedure?: string; description?: string }): Promise<WorkHourEntryRecord>
function updateEntry(projectId: string, entryId: string, payload: Partial<EntryCreate>): Promise<WorkHourEntryRecord>
function deleteEntry(projectId: string, entryId: string): Promise<void>
function batchSubmitEntries(projectId: string, entryIds: string[]): Promise<{ submitted_count: number }>
function getEntrySummary(projectId: string, period?: string): Promise<{ by_day: Record<string,number>; by_cycle: Record<string,number>; total: number }>
```

## Data Models
复用后端已有 WorkHourEntry ORM（不新增表/迁移），前端只需 TypeScript 接口对齐。

## Correctness Properties

| 属性 | 描述 |
|------|------|
| P1 | 24h 校验双重保障：前端计算剩余可用 + 后端 422 兜底 |
| P2 | 非 draft 条目前端禁用 + 后端 422 双重 |
| P3 | batchSubmit 只影响当前用户 draft 条目 |
| P4 | cycle 自动推断可被手动覆盖，覆盖后 wp_code 变化不再回填 |
| P5 | Dialog saved 后父组件刷新列表 |

## Error Handling
- API 错误统一走 `handleApiError`
- 24h 超限前端用 ElMessage.warning 拦截，不发请求
- 非 draft 编辑/删除前端灰化按钮，后端 422 兜底
- 网络失败保留表单数据不清空

## Testing Strategy
- get_diagnostics 零错误
- Vite transform 3 个新 .vue 全 200
- 手动 Playwright 验证：创建→列表显示→编辑→批量提交→状态变色
