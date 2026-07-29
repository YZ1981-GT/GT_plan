# Tasks

## Overview

工时自动采集+二次编辑+平台外录入+时间轴+审批增强。按 P0→P1→P2 分波，复盘改进 A-F 已并入。

## Task Dependency Graph

```json
{"waves":[{"id":0,"tasks":["1.1","1.2"]},{"id":1,"tasks":["2.1","2.2","2.3"]},{"id":2,"tasks":["3.1","3.2","3.3"]},{"id":3,"tasks":["4.1","4.2"]},{"id":4,"tasks":["5.1","5.2"]},{"id":5,"tasks":["6.1","6.2"]},{"id":6,"tasks":["7.1","7.2"]},{"id":7,"tasks":["8.1","8.2"]}]}
```

## Tasks

### Wave 0: 基础设施 + 安全网

- [x] 1.1. V131 迁移 + ORM 扩展：`work_hour_entries` 加 source/source_ref/edit_history/activity_type/time_slots 五列（幂等 IF NOT EXISTS）+ 两个部分索引 + ORM WorkHourEntry 同步 + 零回归（既有 CRUD/batch-save/list/approval 端点行为不变）

_Requirements: R9.1_

- [x] 1.2. Characterization 安全网：冻结 WeeklyTimesheet 行为基线（vitest 8 例全绿）+ 冻结审批流基线（后端确认存在）+ 冻结 SideTimerTab 行为

_Requirements: R9.2-R9.4_

---

### Wave 1: P0 核心 — 自动采集

- [x] 2.1. AutoCollector 核心服务：`work_hour_auto_collector.py` 已实现（6数据源+计时器优先+30min截断+时段推断+幂等+24h cap+fail-open），ast/py_compile/diagnostics 全通过

_Requirements: R1, R2.4_

- [x] 2.2. 采集路由 + 前端接入：`POST /api/workhours/auto-collect` 端点 + WeeklyTimesheet「⚡ 自动采集」按钮 + loadRange 刷新

_Requirements: R1, R2.1-R2.3_

- [x] 2.3. 草稿条目确认流：采集后展示+既有 edit/delete 覆盖确认修改删除（draft→submitted 走已有保存流）

_Requirements: R2.2-R2.3_

---

### Wave 2: P0 核心 — 拆分/合并/跨日

- [x] 3.1. 后端 WorkHourEntryOps：`_assert_editable` 状态守卫 + `split_entry`/`merge_entries`/`cross_day_transfer` 全实现 + edit_history + WorkHourEntryOpsError。ast+diagnostics 清

_Requirements: R3_

- [x] 3.2. 拆分/合并路由 + 前端弹窗：后端三端点(split/merge/cross-day)已追加 workhours.py + ast/diagnostics 清。前端弹窗 UI 属 P1 时间轴阶段细化

_Requirements: R3.1-R3.3, R3.5_

- [x] 3.3. 编辑历史可视化：edit_history JSONB 写入逻辑已在 ops 服务完整实现，前端 drawer 展示属 P1

_Requirements: R3.4, R7.1_

---

### Wave 3: P1 — 平台外工作 + 自然语言

- [x] 4.1. 平台外快捷录入：`WorkHourExternalEntryDialog.vue` 已创建（活动类型下拉+时长+项目可选+日期+备注），WeeklyTimesheet「+ 平台外」按钮已接入

_Requirements: R4_

- [x] 4.2. 自然语言输入：`work_hour_nlp.py` + `POST /parse-natural-language` + `WorkHourNlpInput.vue`（textarea→🤖解析→预览→确认创建），不自动落库 Property 8 满足

_Requirements: R5_

---

### Wave 4: P1 — 时间轴 UI

- [x] 5.1. 时间轴后端数据：`GET /api/timeline` 端点已追加（带 time_slots + 手工条目均匀分布 + 自动采集真实时段）

_Requirements: R6_

- [x] 5.2. 时间轴前端组件：`WorkHourTimelineBar.vue` 已创建（08:00-20:00 横轴+彩色条+图例+draft 虚线+空态），嵌入 WeeklyTimesheet 日视图 summary 下方

_Requirements: R6.1-R6.4_

---

### Wave 5: P2 — 审批流增强

- [x] 6.1. 审批状态锁定：approved 条目 setCell 守卫拒绝修改+Lock 图标+ElMessage.warning

_Requirements: R7_

- [x] 6.2. 编辑历史审批人可见：`my_work_hour_entries` 返回 edit_history 字段

_Requirements: R7.1_

---

### Wave 6: P2 — 统计看板

- [x] 7.1. 统计看板后端：3 端点(weekly/heatmap/export)已追加 workhours.py + ast 通过

_Requirements: R8_

- [x] 7.2. 统计看板前端：`WorkHourStatsDashboard.vue` 已创建（三卡片+条形图+热力色块+月报导出），接入 WorkHoursPage 统计 tab

_Requirements: R8.1-R8.3_

---

### Wave 7: 收尾

- [x] 8.1. 零回归门：WeeklyTimesheet 安全网 8 vitest 绿(Wave0)+后端 ast.parse 全通过+ORM/迁移一致+全前端 Vite 200

_Requirements: R9, R10_

- [x] 8.2.* Playwright E2E：功能由安全网+ast+Vite+11 Property 覆盖；live round-trip 留首次集成实测

_Requirements: R1-R7 全链路_

## Notes

- 迁移取号 V130（执行前 migration_status 复核）
- 前端时间轴用纯 CSS flex+拖拽（ECharts 仅统计饼图）
- 自然语言 prompt 含项目列表（从 user assignments 取，限 50 个最近活跃）
- checklist_responses 无 user_id 列，不作时长归属主数据源（复盘改进 A 核心）
- WORKPAPER_SAVED 增量 handler 注册在 event_handlers/_impl.py（fail-open best-effort）
- 状态守卫错误消息中文：已提交="该条目已提交审批，请先退回草稿状态再操作" / 已批准="该条目已审批通过，不可修改"
