# Implementation Plan: confirmation-module-coordination

## Overview

函证模块横切协同层实现——为已建 9 �?D0 表抽取统一协同：函证主数据 SSOT + 状态机 + 统一枚举 + 共享 UI Kit + 跨表导航 + D0-1 分发。增量实现，不阻塞单表先行�? Sprint：统一枚举+主数�?�?状态机+看板 �?共享 UI Kit+导航 �?D0-1 分发+9 表接入回归�?

依赖�? 个组�?spec（D0-1~D0-8 + D0-4b）的基础组件先行；复�?cross_wp_references / EventBus / GtGridSheet 网格美化�?

## Tasks

### Sprint 1：统一枚举 + 函证主数�?SSOT

- [x] 1.1 后端 `system_dicts` 建立 `confirmation_dicts` 命名空间：归�?confirmation_subject/method/reply_method/send_result/followup_scenario/diff_type/sampling_method/reply_reliability_conclusion/status/yes_no/yes_no_na，去重统一
  - _需�?3.1, 3.2, 3.3, 3.4_
- [x] 1.2 新增 `useConfirmationMaster.ts`：ConfirmationMaster 类型 + getByIndex/listAll（经 cross_wp_references 解析 D0-1 SSOT�? upsert（D0-1/D0-2 写入�?
  - _需�?1.1, 1.2, 1.3; 属�?P1_
- [x] 1.3 下游只读派生：D0-3/D0-4/D0-4b/D0-5/D0-6/D0-7/D0-8 getByIndex 取主数据，不持久化副�?+ 缺失降级手工
  - _需�?1.4, 1.5, 1.6; 属�?P1/P7_
- [x] 1.4 useConfirmationMaster + confirmation_dicts 单测：SSOT 解析/upsert/下游派生/缺失降级/枚举去重
  - _属�?P1/P3/P7_

### Sprint 2：函证状态机 + D0-1 状态看�?

- [x] 2.1 后端 `confirmation_status` 枚举�?2 态）�?confirmation_dicts；主数据�?confirmation_status 字段
  - _需�?2.1, 2.3_
- [x] 2.2 新增 `useConfirmationStatus.ts`：statusOf/transition（事件驱动）/distribution/stalled
  - _需�?2.2, 2.5; 属�?P2_
- [x] 2.3 状态流转接 EventBus：各�?WORKPAPER_SAVED �?transition（D0-2核实/D0-1发函回函/D0-3跟函/D0-7验证/D0-4差异/D0-5-6替代/D0-8舞弊�?
  - _需�?2.2_
- [x] 2.4 D0-1 看板展示状态分布（各状态计�?占比�? 停滞预警
  - _需�?2.4, 2.5_
- [x] 2.5 useConfirmationStatus 单测：流�?+ distribution 计数 + 停滞
  - _属�?P2_

### Sprint 3：共�?UI Kit + 跨表导航�?

- [x] 3.1 新增 `confirmationTheme.ts`：STATUS_COLORS（绿/�?红）/ AMOUNT_FORMAT / GRID_BEAUTY / AUTO_FETCH_MARK 统一常量
  - _需�?4.2, 4.3, 4.4, 4.5; 属�?P4_
- [x] 3.2 新增共享组件 `ConfirmationStatusBadge.vue` / `ConfirmationDashboard.vue` / `ConfirmationToolbar.vue`（slot 化复用）
  - _需�?4.1, 4.6, 4.7_
- [x] 3.3 新增 `ConfirmationNavBar.vue`：本笔函证相关底稿导航条（按状态点�?D0-2|D0-1|D0-3|D0-7|D0-4|D0-4b|D0-5/6|D0-8 + 跳转定位�?
  - _需�?5.1, 5.2, 5.3, 5.4; 属�?P5_
- [x] 3.4 9 组件接入 ConfirmationKit（替换各自看�?徽章/配色/金额格式为共享层�?
  - _需�?4.1; 属�?P4_
- [x] 3.4b 交互能力基线统一审计与补齐：核对 9 表全部表�?子表/清单具备 编辑/右键/useCellSelection(选区/复制/粘贴/求和)/增删/导入导出/键盘导航；补 D0-4b 子表 useCellSelection、D0-8 selection+导入；只读一致守�?
  - _需�?8; 属�?P8_
- [x] 3.5 UI Kit + 导航�?spec：配�?金额/网格一�?+ 导航点亮跳转 + 交互基线一�?
  - _属�?P4/P5/P8_

### Sprint 4：D0-1 枢纽分发 + 全模块回�?

- [x] 4.1 D0-1 �?分发到下�?动作：差异≠0→D0-4 / 未回函→D0-5或D0-6(按科�? / 电子回函→D0-7 + 标记已分�?
  - _需�?6.1, 6.3, 6.4_
- [x] 4.2 分发与下�?�?D0-1 带入"统一去重逻辑（双向等价）
  - _需�?6.2; 属�?P6_
- [x] 4.3 全模块回归：9 组件接入共享层零回归（render-config 冒烟 + �?spec 单测�?
  - _需�?7.1, 7.2_
- [x] 4.4 Playwright 端到端：D0-1 分发→下游出现行→各表导航条跳转定位→主数据一处改多处同步→状态机流转→D0-1 看板状态分布更新→0 error
  - _需求全部_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1.1", "1.2"] },
    { "wave": 2, "tasks": ["1.3", "1.4"] },
    { "wave": 3, "tasks": ["2.1", "2.2"] },
    { "wave": 4, "tasks": ["2.3", "2.4", "2.5"] },
    { "wave": 5, "tasks": ["3.1", "3.2"] },
    { "wave": 6, "tasks": ["3.3", "3.4"] },
    { "wave": 7, "tasks": ["3.5", "4.1", "4.2"] },
    { "wave": 8, "tasks": ["4.3", "4.4"] }
  ]
}
```

## Notes

- **�?spec 是横切协同层，不是新业务底稿**�? 张表组件已分�?spec 化，�?spec 统一其共享基础（主数据/状�?枚举/UI/导航/分发）�?
- **实施顺序**：建�?9 张表的基础组件（至�?D0-1/D0-2）先落地，再实施本协同层（SSOT 依赖 D0-1 承载主数据）。协同层增量，不阻塞单表先行�?
- **四维改进对应**：①实用�?SSOT 不漂�?状态机看全�?②使用方�?跨表导航�?D0-1 分发（从中心出发）③美观=ConfirmationKit 统一配色/金额/网格 ④联�?confirm_index 主键贯穿+主数据单�?状态流转�?
- **v3.0 愿景预留**：未来可在协同层之上�?函证总览驾驶�?（按 confirm_index 聚合 9 表全景），本 spec 已打好主数据/状�?导航地基�?
- 9 张表需各补一�?函证模块协同"需求，引用�?spec �?SSOT/状�?枚举/UI/导航/分发决策�?
- 铁律：增量不破坏既有 spec；EventBus publish 只传 EventPayload；组�?props 不可变；改动�?Playwright 实测�?
