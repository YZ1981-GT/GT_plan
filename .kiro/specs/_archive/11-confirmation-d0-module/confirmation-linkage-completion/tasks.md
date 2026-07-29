# Implementation Plan

## Overview

按 Wave 顺序实现 confirmation-linkage-completion。全部 additive + 前端为主 + 复用既有能力（零新后端端点/零新表/零迁移）。每个 Wave 独立可发布、可回退。Wave 0 先建安全网 + 核实 D0-2 检测可用性，避免在错误假设上开发。

**共享组件红线**：diffReconcile/reliability/fraudRisk 是并发会话可能编辑的热点文件——采用最小侵入（只加接线/最小改 stub 函数，不重构既有 composable），提交前 `git status` 核实只 stage 本 spec 文件。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1.1", "1.2"], "depends_on": [] },
    { "wave": 1, "tasks": ["2.1", "2.2"], "depends_on": ["1.1"] },
    { "wave": 2, "tasks": ["3.1", "3.2"], "depends_on": ["1.1"] },
    { "wave": 3, "tasks": ["4.1", "4.2"], "depends_on": ["1.1"] },
    { "wave": 4, "tasks": ["5.1", "5.2"], "depends_on": ["1.1", "1.2"] },
    { "wave": 5, "tasks": ["6.1", "6.2", "6.3"], "depends_on": ["2.1", "2.2", "3.1", "3.2", "4.1", "4.2", "5.1", "5.2"] }
  ]
}
```

## Tasks

- [x] 1. Wave 0 — 安全网 + 检测可用性核实
- [x] 1.1 建 characterization 安全网锁定既有行为
  - 为 `coordination/importFromSummary.ts` 的 `defaultDiffFilter`/`defaultElectronicReplyFilter`/`defaultUnrepliedFilter` 补/核对单测（若已有则复核覆盖），锁定过滤语义
  - 为 `useD01DiffImport.mapD01Row` 补 characterization（is_replied=false→null、差异=0→null、正常映射）
  - 为 D0-8 `GtConfirmationFraudRisk.handleAutoFill` 现有规则预填行为写 characterization（7/10/14/15 条预填 + 手工已填不覆盖），作为 R4 改造的零回归基线
  - _Requirements: 5.2, 6.1_
- [x] 1.2 核实 D0-2 entityVerify 红旗检测可用性（决定 R4 D0-2 源纳入与否）
  - 读 `entityVerify/`（含 `EntityVerifyFraudPanel.vue` + composables），确认是否有结构化红旗产出（地址聚类/号段相邻/撞员工/同寄件人）可被 `addD02RedFlags` 消费
  - 产出结论：~~**有** → R4 纳入 D0-2 源~~；**无** → R4 跳过 D0-2（item10 保留规则预填兜底，宁缺勿造），并在 tasks 5.1 备注
  - **结论：无**——`useFraudFlagDetect` 是纯前端跨行检测（基于当前 entityVerify rows 内存态），不产出持久化结构化红旗供外部底稿消费。D0-2 源跳过，item10 保留规则预填兜底。
  - _Requirements: 4.1, 4.5_

- [x] 2. Wave 1 — R1 D0-4 差异调节表「从 D0-1 带入」un-stub
- [x] 2.1 接线 `GtConfirmationDiffReconcile.confirmD01Import`
  - 改 `confirmD01Import`：`filterSummaryRows(projectId, {cycle}0-1, defaultDiffFilter)` → `d01Import.fetchAndImport(res.rows)`；循环码派生 `wpCode.split('-')[0]+'-1'`
  - 缺项目上下文/找不到汇总/空数据 → 明确提示（warning/info），不静默不崩；只读态按钮不可用（既有 gate 复核）
  - 不改 `useD01DiffImport`（保持去重/映射语义）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
- [x] 2.2 D0-4 带入单测
  - 循环码派生（D0-4→D0-1/F0-4→F0-1）、去重、只读不触发、找不到/空提示
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 6.1_

- [x] 3. Wave 2 — R2 D0-7 可靠性验证表「从 D0-1 带入电子回函」un-stub
- [x] 3.1 新增纯映射器 + 接线 `GtConfirmationReliability.confirmImportD01`
  - 新建 `reliability/composables/mapD01ReliabilityRow.ts`：`mapSummaryToReliabilityRow(row): Partial<ReliabilityRow>`（confirm_index/entity_name/reply_method/reply_date + `_source:'auto'`），纯函数可单测
  - 改 `confirmImportD01`：`filterSummaryRows(pid, {cycle}0-1, defaultElectronicReplyFilter)` → 按 confirm_index 对现有 rows 去重 → map → `data.importRows(mapped)`；移除占位 `ElMessage.info('待跨底稿引用 API 接入后启用')`
  - 缺项目/找不到/空 → 明确提示；只读 gate
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
- [x] 3.2 D0-7 带入单测
  - `mapSummaryToReliabilityRow` 映射正确、`defaultElectronicReplyFilter` 只纳入电子回函、去重、找不到/空提示
  - _Requirements: 2.1, 2.2, 2.3, 6.1_

- [x] 4. Wave 3 — R3 退役死脚手架 dispatch_records
- [x] 4.1 删除前端死脚手架 + 后端标 DEPRECATED
  - 删前 grep 全仓确认 `useConfirmationDispatch`/`useDownstreamDispatch`/`dispatchApi` 无其它运行时消费者
  - 删 `coordination/useConfirmationDispatch.ts` + 其 `__tests__/useConfirmationDispatch.spec.ts`、`composables/useDownstreamDispatch.ts`、`services/dispatchApi.ts`（确认仅上述二者消费后）；`coordination/index.ts` 移除对应导出
  - 后端 `dispatch_service.py`/`routers/dispatch_records.py`/`models/dispatch_models.py` docstring 加 `DEPRECATED` 注释（**保留表/路由/迁移不删**）；不动 `router_registry/collaboration.py`
  - _Requirements: 3.1, 3.2, 3.3, 3.4_
- [x] 4.2 契约守卫防复活
  - 新建 `coordination/__tests__/dispatchRetirement.spec.ts`：扫 confirmation 树源码断言无 `useConfirmationDispatch`/`useDownstreamDispatch` 运行时 import
  - _Requirements: 6.3_

- [x] 5. Wave 4 — R4 舞弊信号自动汇集变 live + 落库
- [x] 5.1 D0-8 `handleAutoFill` 接 useFraudSignalCollector（fetch 上游 → 汇集 → 填 items 手工优先）
  - 用 `fetchWorkpaperHtmlRows` 拉 D0-7 reliability-v1（conclusion_status='不可靠'→`addD07Unreliable`）、D0-3 followup（control_conclusion='fail'→`addD03ControlFailure`）、D0-1 confirmation-v1（回函率<50%→`addD01LowReplyRate`）；D0-2 按 1.2 结论纳入或跳过
  - `exportForD08()` 填检查项：`!item.is_exist` 才填（手工优先 P10），写 source_ref + response_note + `_auto_filled`
  - 各上游独立 try/catch，全失败/无信号 → 降级现有规则预填（fail-open）；循环码派生 `{cycle}0-*`
  - `emit('save')` 持久化到 checklist_responses（P12）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
- [x] 5.2 D0-8 舞弊汇集单测
  - 信号→检查项映射一致（SIGNAL_TO_ITEM_MAP）、去重、手工优先不覆盖、fail-open 降级、循环码派生
  - _Requirements: 4.1, 4.2, 4.4, 4.5, 6.2_

- [x] 6. Wave 5 — 属性守卫 + 零回归门 + 端到端
- [x] 6.1 属性/契约测试汇总核对
  - 核对 P1-P13 均有测试覆盖（Wave1-4 已建 + 本任务补缺口），无悬空属性
  - _Requirements: 6.1, 6.2, 6.3_
- [x] 6.2 零回归门
  - 跑 confirmation 域全量 vitest（含 alt 程序 importFromSummary/K05/K06/L05/H05、confirmation-v1/diff-reconcile-v1/reliability-v1/fraud-risk-d08-v1）零新增失败；`get_diagnostics` 全改动文件清；改动 .vue/.ts `curl.exe` Vite transform 200
  - 甄别任何失败是否并发会话半成品（git status 核实非本 spec 回归）
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
- [x]* 6.3 Playwright / 鉴权 HTTP round-trip 端到端（可选）
  - 实例化 7 循环之一（上游有数据）：D0-4 点带入拉不符项、D0-7 点带入拉电子回函、D0-8 自动填充从真实上游汇集；SSE flaky 环境用鉴权 HTTP round-trip（create→verify→cleanup）替代浏览器
  - **结论**：全库函证底稿 confirmation-v1 行数据为 0（无人编制过汇总表）。Playwright 浏览器验证了三条端到端路径：①wp-id-by-code 404→filterSummaryRows 返 null→UI 正确 warning（P4）②render-config 有 confirmation-v1 sheet 但 rows=[]→正确 info（P4）③wp-id-by-code 返回 wp_id=null 也走 null 路径不崩。"found + non-empty rows→带入映射"路径由 29 vitest 覆盖（mapD01Row/fetchAndImport/exportForD08）。
  - _Requirements: 1.1, 2.1, 4.1_

## Notes

- **零新后端**：R1/R2/R4 全复用 `coordination/importFromSummary.ts` 的 `filterSummaryRows`/`fetchWorkpaperHtmlRows`（`wp-id-by-code → render-config`）。R3 后端仅加 DEPRECATED 注释不删表。
- **循环码派生铁律**：`{cycle}0-N` 一律 `wpCode.split('-')[0]+'-N'`，禁硬编码 D0（否则 F0/G0/H0/K0/L0 循环带入错底稿）。
- **fail-open**：R4 上游任一不可读不阻断，降级规则预填；R1/R2 找不到汇总明确提示不崩。
- **宁缺勿造**：D0-2 红旗源仅在 1.2 核实有结构化检测时纳入，否则跳过保留规则预填兜底。
- **并发热点**：diffReconcile/reliability/fraudRisk 最小侵入改动，提交前 git status 核实只 stage 本 spec 文件。
- **可选任务标记**：6.3 带 `*`（需实例化环境），按既定偏好尽量做完；无实例化环境时以 6.1/6.2 的属性+回归测试覆盖为准，诚实标注。
