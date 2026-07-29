# Design Document

## Overview

本 spec 完成三件事，全部 additive + 前端为主 + 复用既有能力（零新后端端点、零新表、零迁移）：

- **R1/R2 un-stub「从 D0-1 带入」**：D0-4 差异调节表、D0-7 可靠性验证表的带入按钮当前是桩（`console.log` / `ElMessage.info('待跨底稿引用 API 接入后启用')`）。接到**已存在**的通用跨底稿读取器 `coordination/importFromSummary.ts`（`fetchConfirmationSummaryRows`/`filterSummaryRows` + 现成过滤器 `defaultDiffFilter`/`defaultElectronicReplyFilter`）。因 diffReconcile/reliability 是共享组件，一处改动惠及全部 7 循环。
- **R3 退役死脚手架 dispatch_records**：`useConfirmationDispatch`（生产半边）+`useDownstreamDispatch`（消费半边）两端零组件消费者，`dispatchApi.ts` 仅它们消费。删前端三者 + 单测 + `coordination/index.ts` 导出；后端 `dispatch_service.py`/路由/`dispatch_models.py`/V093 表**保留不删**（避破坏性 DDL），docstring 标 DEPRECATED。
- **R4 舞弊信号自动汇集变 live + 落库**：D0-8 `handleAutoFill` 当前是硬编码规则预填（不读上游、不用 `useFraudSignalCollector`）。改为：D0-8 经读取器拉取上游底稿数据（D0-7 reliability-v1 / D0-3 followup-v1 / D0-1 confirmation-v1）→ 用 `useFraudSignalCollector` 的 `addXxx` 计算信号 → `exportForD08()` 填入检查项（手工优先）→ 汇集结果随 D0-8 持久化到 `checklist_responses`（跨会话可读）。fail-open：上游不可读时降级为现有规则预填。

**红线（零回归）**：`importFromSummary`（K05/K06/L05/H05 经后端 `{cycle}/unreplied-entities` 带入未回函，WIRED）、`confirmation-v1`/`diff-reconcile-v1`/`reliability-v1`/`fraud-risk-d08-v1` 格式、撤回状态机 `_REVERSAL_TARGETS`、覆盖率单一真源、`list_match_queue` 附件匹配 —— 均不改语义。未触发新功能时既有行为逐字节等价。

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  coordination/importFromSummary.ts  (既有通用读取器，本 spec 复用)   │
│  - fetchConfirmationSummaryRows(pid, X0-1)   → confirmation-v1 rows │
│  - filterSummaryRows(pid, X0-1, filterFn)                          │
│  - fetchWorkpaperHtmlRows(pid, wpCode, format) → 任意底稿 rows       │
│  - defaultDiffFilter / defaultElectronicReplyFilter               │
└──────────────┬──────────────────────────┬─────────────────────────┘
               │ R1                        │ R2                  ┌── R4
               ▼                           ▼                     ▼
   ┌───────────────────┐      ┌───────────────────┐   ┌──────────────────────┐
   │ D0-4 diffReconcile │      │ D0-7 reliability   │   │ D0-8 fraudRisk        │
   │ confirmD01Import   │      │ confirmImportD01   │   │ handleAutoFill        │
   │ → filterSummaryRows│      │ → filterSummaryRows│   │ → fetch D0-7/D0-3/D0-1│
   │   (defaultDiff)    │      │   (electronicReply)│   │ → useFraudSignalCollector
   │ → useD01DiffImport │      │ → mapReliabilityRow│   │   .addXxx / exportForD08
   │   .fetchAndImport  │      │ → data.importRows  │   │ → 填 items(手工优先)  │
   └───────────────────┘      └───────────────────┘   │ → 持久化 checklist_responses
                                                        └──────────────────────┘

  R3: 删 useConfirmationDispatch / useDownstreamDispatch / dispatchApi + 测试
      后端 dispatch_records 标 DEPRECATED 休眠（不删表）
```

**循环码派生**：各共享组件的 `wpCode`（如 `D0-4`/`F0-7`/`L0-8`）→ 汇总底稿码 `{cycle}0-1`（`wpCode.split('-')[0] + '-1'`），保证 F0-4 带入 F0-1、L0-7 带入 L0-1，不硬编码 D0。

## Components and Interfaces

### R1 — D0-4 diffReconcile 带入（`GtConfirmationDiffReconcile.vue`）

现状：`useD01DiffImport` 已实例化（`existingIndexes` + `onImport: data.importRows`），`fetchAndImport(d01Rows)` 内部 `mapD01Row` 已过滤（is_replied ∧ 差异≠0）+ 去重。缺口仅在 `confirmD01Import` 未拉取 d01Rows（TODO/console.log）。

改动（仅 `confirmD01Import`）：
```
async confirmD01Import():
  showD01ImportDialog = false
  if !projectId: ElMessage.warning('缺少项目上下文'); return
  summaryCode = wpCode.split('-')[0] + '-1'         // D0-4→D0-1
  res = await filterSummaryRows(projectId, summaryCode, defaultDiffFilter)
  if res == null: ElMessage.warning(`未找到 ${summaryCode} 函证汇总底稿`); return
  if res.rows.length == 0: ElMessage.info(`${summaryCode} 暂无不符项`); return
  d01Import.fetchAndImport(res.rows)                 // 内部再过滤+去重+映射
  ElMessage.success(`已从 ${summaryCode} 带入 ${d01Import.lastImportCount} 条差异`)
```
不改 `useD01DiffImport`（`fetchAndImport` 语义/去重/映射保持）。

### R2 — D0-7 reliability 带入（`GtConfirmationReliability.vue` + 新纯映射器）

现状：`confirmImportD01` = `ElMessage.info('待跨底稿引用 API 接入后启用')`。无专用 D01 带入 composable（不同于 D0-4）。`data.importRows(partial[])` 已存在（Excel 导入在用）。

改动：
- 新增纯函数 `mapSummaryToReliabilityRow(row: ConfirmationRow): Partial<ReliabilityRow>`（放 `reliability/composables/mapD01ReliabilityRow.ts`，可单测）：映射 confirm_index/entity_name/reply_method/reply_date + `_source:'auto'`。
- `confirmImportD01` 改为：`filterSummaryRows(pid, {cycle}0-1, defaultElectronicReplyFilter)` → 按 confirm_index 去重（对现有 rows）→ `map(mapSummaryToReliabilityRow)` → `data.importRows(mapped)`；空/找不到明确提示；移除占位 `ElMessage.info`。

### R3 — 退役 dispatch_records 死脚手架

前端删除（grep 全仓确认无其它 import 后）：
- `coordination/useConfirmationDispatch.ts` + `coordination/__tests__/useConfirmationDispatch.spec.ts`
- `composables/useDownstreamDispatch.ts`（`@/composables/`，非 confirmation 目录）
- `services/dispatchApi.ts`（仅上述二者消费 → 一并删；删前再 grep 确认）
- `coordination/index.ts` 移除 `useConfirmationDispatch` 相关导出

后端保留 + 标注（不删表，避免破坏性 DDL、保可回滚）：
- `dispatch_service.py` / `routers/dispatch_records.py` / `models/dispatch_models.py` 顶部 docstring 加 `DEPRECATED: cross-workpaper-dispatch-persistence 未被前端采用，由 coordination/importFromSummary.ts 取代；表 dispatch_records/V093 休眠保留，待运维决定是否清理。`
- 路由保留注册（不动 `router_registry/collaboration.py`，避免影响其它注册顺序）。

契约守卫（防复活）：新增 `coordination/__tests__/dispatchRetirement.spec.ts` — 断言全 confirmation 树无 `useConfirmationDispatch`/`useDownstreamDispatch` 运行时 import（用 `import.meta.glob` 扫源码文本或 fs 读取，参照既有 guard 模式）。

### R4 — 舞弊信号自动汇集（`GtConfirmationFraudRisk.vue`）

数据获取（复用 `fetchWorkpaperHtmlRows(pid, wpCode, format)`，零新后端）：
- **D0-7 不可靠**：`fetchWorkpaperHtmlRows(pid, {cycle}0-7, 'reliability-v1')` → rows.filter(conclusion_status==='不可靠') → 每条 `collector.addD07Unreliable(confirm_index, entity_name)`
- **D0-3 控制失败**：`fetchWorkpaperHtmlRows(pid, {cycle}0-3, followup format)` → rows.filter(control_conclusion==='fail') → `collector.addD03ControlFailure(confirm_index, entity_name)`
- **D0-1 低回函率**：`fetchConfirmationSummaryRows(pid, {cycle}0-1)` → 计算 replied/sent；<阈值(50%) → `collector.addD01LowReplyRate(rate)`
- **D0-2 红旗**：Wave 0 核实 entityVerify 是否有结构化红旗产出。**有** → 消费并 `addD02RedFlags`；**无**（当前疑似无自动检测）→ 该源跳过（宁缺勿造），item10 保留规则预填兜底。

填入 D0-8（手工优先）：
```
signals = collector.exportForD08()   // Map<itemNo, {exists,index_refs,note}>
for (itemNo, sig) of signals:
  item = items.find(seq === itemNo)
  if item && !item.is_exist:          // 手工已填不覆盖（P10）
    item.is_exist = '待核实'
    item.source_ref = sig.index_refs.join(',') || sourceLabel
    item.response_note = sig.note      // 信号描述填入说明
    item._auto_filled = true
```
持久化：汇集后 `data.buildPayload()` 已含 items（含 `_auto_filled`/`source_ref`/note）→ `emit('save')` 存 `checklist_responses`（随 D0-8，跨会话可读，P12）。

fail-open：任一上游 fetch 失败/无数据 → 跳过该源；全部无信号 → 降级为现有规则预填（保留当前 `handleAutoFill` 逻辑作 fallback 分支，P11）。

映射不新增：信号→检查项严格用 `useFraudSignalCollector.SIGNAL_TO_ITEM_MAP`（7=可靠性/10=红旗/14=回函率/15=控制），不在本 spec 加新映射。

## Data Models

无新表、无迁移。舞弊信号不单独持久化为信号实体，而是**汇集后落到 D0-8 检查项**（`items[].is_exist/source_ref/response_note/_auto_filled`），随 D0-8 底稿存 `checklist_responses`（`fraud-risk-d08-v1` 格式既有存储）。`useFraudSignalCollector` 的 `signals` ref 仅在 `handleAutoFill` 内为临时聚合容器（不需跨会话持久化信号本身，持久化的是其对 D0-8 的填充结果）。

## Correctness Properties

### Property 1: D0-4 带入只纳入不符项
`useD01DiffImport.mapD01Row` 对 `is_replied=false` 或 差异=0 的行返回 null（不带入）。**Validates: Requirements 1.1**

### Property 2: 带入按 confirm_index 去重
D0-4/D0-7 带入时，`confirm_index` 已存在于当前表的行被跳过。**Validates: Requirements 1.2, 2.2**

### Property 3: 只读态不触发带入
`readonly=true` 时 D0-4/D0-7 带入按钮不可用/不执行。**Validates: Requirements 1.5, 2.4**

### Property 4: 找不到/空数据明确提示不崩
汇总底稿不存在（reader 返 null）或无符合行 → 返回明确提示，不抛未捕获异常。**Validates: Requirements 1.4, 2.3**

### Property 5: 循环码派生正确
`{cycle}0-1` 由 `wpCode.split('-')[0]+'-1'` 派生（D0-4→D0-1、F0-7→F0-1、L0-8→L0-1），不硬编码 D0。**Validates: Requirements 1.3**

### Property 6: D0-7 只带入电子回函
`defaultElectronicReplyFilter` 仅匹配回函方式含传真/电子邮件的行。**Validates: Requirements 2.1**

### Property 7: 退役后无死脚手架运行时引用
全 confirmation 源码无 `useConfirmationDispatch`/`useDownstreamDispatch` 的运行时 import。**Validates: Requirements 3.1, 3.4, 6.3**

### Property 8: 舞弊信号→检查项映射一致
汇集结果的 itemNo 严格来自 `SIGNAL_TO_ITEM_MAP`（不新增映射）。**Validates: Requirements 4.1, 4.5**

### Property 9: 舞弊信号去重
同 `(confirm_index, signalType)` 不重复产生信号（`addSignal` 既有去重）。**Validates: Requirements 4.1**

### Property 10: D0-8 自动填充手工优先
已填检查项（`is_exist` 非空）不被自动填充覆盖。**Validates: Requirements 4.2**

### Property 11: 舞弊汇集 fail-open
上游不可读/无信号 → 降级规则预填，不阻断不崩。**Validates: Requirements 4.4**

### Property 12: 舞弊填充结果跨会话可读
汇集填入 D0-8 items 后经 `emit('save')` 持久化 `checklist_responses`，重开可读。**Validates: Requirements 4.3**

### Property 13: 零回归
不触发新功能时 D0-4/D0-7/D0-8 行为逐字节等价；`importFromSummary`/格式/撤回状态机/覆盖率/匹配队列不改。**Validates: Requirements 5.2, 5.3**

## Error Handling

- reader 网络错误/404 → `filterSummaryRows`/`fetchWorkpaperHtmlRows` 返 null → 组件层明确提示，不崩。
- R4 各上游 fetch 独立 try/catch，单源失败不影响其它源；全失败降级规则预填。
- 只读态所有带入/自动填充入口 gate。
- 删除前 grep 全仓确认无引用（R3），避免删出编译错误。

## Testing Strategy

- **Wave 0 characterization**（安全网）：锁 `defaultDiffFilter`/`defaultElectronicReplyFilter`/`mapD01Row` 现行为 + D0-8 `handleAutoFill` 规则预填现行为 + 核实 D0-2 entityVerify 红旗检测可用性。
- **单元测试**：`mapSummaryToReliabilityRow` 纯函数（P6）；循环码派生（P5）；去重（P2）；舞弊信号映射/去重/手工优先/fail-open（P8-P11）。
- **契约守卫**：`dispatchRetirement.spec.ts`（P7）。
- **回归**：confirmation 域全量 vitest 零新增失败（P13）。
- **Playwright（可选）**：D0-4/D0-7 点带入真实拉取 + D0-8 自动填充（需实例化 7 循环之一 + 上游有数据；SSE flaky 环境用鉴权 HTTP round-trip 替代）。
