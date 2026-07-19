# Implementation Plan: 工时细粒度填报前端入口

## Overview
6 个任务组，按依赖关系分 5 波执行。纯前端改动，后端端点已就绪无需修改。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "wave-0", "tasks": ["1"], "description": "API 封装" },
    { "id": "wave-1", "tasks": ["2", "3"], "description": "核心组件（并行）" },
    { "id": "wave-2", "tasks": ["4"], "description": "项目级视图" },
    { "id": "wave-3", "tasks": ["5"], "description": "WeeklyTimesheet 接入" },
    { "id": "wave-4", "tasks": ["6"], "description": "路由注册+验证" }
  ]
}
```

## Tasks

- [x] 1. API 服务封装
  - [x] 1.1 在 apiPaths/collaboration.ts 新增 workHourEntries 路径对象
  - [x] 1.2 在 staffApi.ts 新增 WorkHourEntryRecord 接口 + 6 个 API 函数
  - [x] 1.3 get_diagnostics 验证零错误

- [x] 2. WorkHourEntryDialog 填报弹窗
  - [x] 2.1 新建 components/workhour/WorkHourEntryDialog.vue
  - [x] 2.2 表单：日期/循环(A~S+OTHER)/底稿编码/程序/小时/描述
  - [x] 2.3 wp_code watch 自动推断 cycle
  - [x] 2.4 提交前调 summary 校验 24h
  - [x] 2.5 编辑模式（entryId prop 存在时 GET 回填 + PUT）
  - [x] 2.6 非 draft 只读 + 状态 tag 展示

- [x] 3. WorkHourEntryList 列表组件
  - [x] 3.1 新建 components/workhour/WorkHourEntryList.vue
  - [x] 3.2 el-table 列：日期/循环/底稿/程序/小时/状态tag/操作
  - [x] 3.3 日期范围+状态 el-select 筛选
  - [x] 3.4 el-table-column type=selection + 批量提交按钮
  - [x] 3.5 操作列编辑/删除（非 draft 禁用）

- [x] 4. ProjectWorkHoursView 项目级视图
  - [x] 4.1 新建 views/ProjectWorkHoursView.vue
  - [x] 4.2 顶部汇总卡（总工时/按循环/本周天数）
  - [x] 4.3 嵌入 WorkHourEntryList + 右上角新增按钮

- [x] 5. WeeklyTimesheet 接入
  - [x] 5.1 日视图项目卡片加"📋 详细"按钮
  - [x] 5.2 点击打开 WorkHourEntryDialog（传 projectId + 当前日期）
  - [x] 5.3 Dialog @saved 后不影响 WeeklyTimesheet 数据

- [x] 6. 路由注册 + 集成验证
  - [x] 6.1 router/index.ts 新增 /projects/:projectId/work-hours 路由
  - [x] 6.2 get_diagnostics 全部文件零错误
  - [x] 6.3 Vite transform 3 个新 .vue 全 200

## Notes
- 后端 workhour_entries.py 端点已完整就绪，本 spec 纯前端
- WeeklyTimesheet 写 work_hours 表，WorkHourEntryDialog 写 work_hour_entries 表，两表独立
- 状态色标：draft=#909399 submitted=#409EFF approved=#67C23A rejected=#F56C6C
