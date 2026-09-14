# Requirements Document

## Introduction
后端 Phase 7 F7 已实现 `WorkHourEntry` 细粒度工时模型 + 完整 CRUD 端点，但无前端消费者。本需求为其建立前端入口，使审计师能按循环/底稿/程序三级粒度记录工时。

## Glossary
- **WorkHourEntry**: Phase7 细粒度工时条目（work_hour_entries 表），按 user_id+project_id+date+cycle+wp_code+procedure 粒度
- **WeeklyTimesheet**: 现有快速工时填报组件（写 Phase9 的 work_hours 表），按 staff_id+project_id+date 粒度

## Requirements

### Req-1: 细粒度填报弹窗
When 用户在 WeeklyTimesheet 日视图点击项目卡片的"详细填报"按钮，the system shall 打开细粒度工时填报弹窗，支持选择循环→底稿编码→程序描述→小时数→备注。

### Req-2: 循环自动推断
When 用户输入或选择 wp_code，the system shall 自动推断 cycle 字段（取 wp_code 首字母），并允许手动覆盖。

### Req-3: 日合计校验前端提示
When 用户填报的当日工时合计超过 24h，the system shall 在提交前前端拦截并给出警告。

### Req-4: 已提交条目只读
When 工时条目状态为 submitted/approved/rejected，the system shall 禁止编辑和删除。

### Req-5: 批量提交
When 用户选中多条 draft 状态的工时条目并点击"提交审批"，the system shall 调用 batch-submit 端点一次性提交。

### Req-6: 细粒度条目列表
When 用户在项目内查看工时记录，the system shall 按日期倒序展示所有 WorkHourEntry，含状态色标。

### Req-7: 与 WeeklyTimesheet 并存
The system shall 保持 WeeklyTimesheet 不变，细粒度弹窗为可选深度入口。两者写入不同表，互不干扰。

### Req-8: 前端 API 服务封装
The system shall 在 staffApi.ts 新增 WorkHourEntry 相关 API 函数，路径对齐后端端点。

### Req-9: 项目内工时视图
When 用户在项目内导航到工时页面，the system shall 在 `/projects/:projectId/work-hours` 提供独立的细粒度工时管理视图。
