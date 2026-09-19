# Requirements Document

## Introduction

本 spec 承接「函证模块二次复盘」的**修正结论**（2026-07-26 逐行读码实证）。用户初始设想为「把两个有价值的孤儿 composable（`useConfirmationDispatch` + `useFraudSignalCollector`）正式接线做完」，但深入分析后**修正了前提**：

- **`useConfirmationDispatch` 不是"待接线的价值孤儿"，而是"该退役的死脚手架"**：它属于 `dispatch_records` 机制（后端 `dispatch_service.py` + `dispatch_records.py` 路由 + `dispatch_models.py`/V093 表全建，前端 `useConfirmationDispatch`[生产半边] + `useDownstreamDispatch`[消费半边] + `dispatchApi.ts`），但**生产端与消费端两个 composable 均零组件消费者**（grep 实证，排除测试后仅注释引用）→ 该机制**端到端从未被采用**。盲目接线 = 复活一条与平台主流「`importFromSummary` 直接读汇总表」并行的废弃路径。
- **它本意要解决的真需求（D0-1 → 下游 D0-4/D0-7 带入）是真实存在的缺口，但正确解法不是 dispatch_records**：平台已有自包含通用读取器 `coordination/importFromSummary.ts`（`wp-id-by-code → render-config → 筛 confirmation-v1 rows`，**无需任何 per-cycle 后端**），且已备好精确过滤器 `defaultDiffFilter`（差异≠0，供 D0-4）/`defaultElectronicReplyFilter`（电子回函，供 D0-7）。而 D0-4 差异调节表与 D0-7 可靠性验证表的「从 D0-1 带入」按钮当前是**桩**（`GtConfirmationDiffReconcile.executeD01Import` = `console.log` 占位；`GtConfirmationReliability.executeD01Import` = `ElMessage.info('待跨底稿引用 API 接入后启用')`）——审计师点击无效，且这是**共享组件**（`diffReconcile/`、`reliability/`），影响全部 7 个函证循环（D0/E0/F0/G0/H0/K0/L0）。
- **`useFraudSignalCollector` 确是有价值的孤儿**：舞弊信号从 D0-2（企查查红旗）/D0-3（跟函控制失败）/D0-7（回函不可靠）自动汇集到 D0-8 舞弊风险检查表——`GtConfirmationFraudRisk.handleAutoFill` 注释明写「dispatch persistence 接入后将从后端读取实际信号」，当前用规则预填，`useFraudSignalCollector` 零上游 emit + D0-8 不消费它。

因此本 spec 的实际交付 = ①**补齐 D0-4/D0-7「从 D0-1 带入」真实接线**（复用现成通用读取器，惠及 7 循环，零新后端）②**退役死脚手架** dispatch_records（删前端孤儿 + 测试，后端标 deprecated/休眠保留不删表）③**接通舞弊信号自动汇集** D0-2/D0-3/D0-7 → D0-8 并落库（`useFraudSignalCollector` 从孤儿变 live）。

**红线**：所有既有已工作路径零回归——`importFromSummary`（K05/K06/L05/H05 替代程序的「从 X0-1 带入未回函」经后端 `unreplied-entities` 端点）、`confirmation-v1` 格式、撤回状态机（`_REVERSAL_TARGETS`）、覆盖率单一真源（`_inject_confirmation_population` + `useConfirmationData.coverageMetrics`）、附件/OCR/人工匹配队列（`list_match_queue`）均不得改动语义。

## Glossary

- **X0-1 函证结果汇总表**：各循环函证枢纽底稿（D0-1/E0-1/…/L0-1），`confirmation-v1` 格式，编制真源。
- **D0-4 / X0-4 差异调节表**：`diffReconcile/` 共享组件，`diff-reconcile-v1` 格式，登记回函不符（差异≠0）项。
- **D0-7 / X0-7 可靠性验证表**：`reliability/` 共享组件，验证电子回函（传真/电子邮件）可靠性。
- **D0-8 / X0-8 舞弊风险检查表**：`fraudRisk/` 共享组件，19 条舞弊迹象预置检查项。
- **通用汇总读取器**：`coordination/importFromSummary.ts`，跨底稿读 X0-1 的 `confirmation-v1` 行（`wp-id-by-code → render-config`），提供 `filterSummaryRows` + 三个过滤器（`defaultUnrepliedFilter`/`defaultDiffFilter`/`defaultElectronicReplyFilter`）。
- **dispatch_records 机制**：`cross-workpaper-dispatch-persistence` feature 的死脚手架（后端 V093 表 + 路由 + service；前端 `useConfirmationDispatch`/`useDownstreamDispatch`/`dispatchApi.ts`），两端零组件消费者。
- **舞弊信号（Fraud Signal）**：上游底稿检出的异常迹象（地址聚类/号段相邻/撞员工名单/同寄件人/回函不可靠/控制失败/回函率异常低），映射到 D0-8 对应检查项。
- **7 循环**：使用共享 confirmation-* 组件的 D0/E0/F0/G0/H0/K0/L0 函证枢纽。

## Requirements

### Requirement 1: D0-4 差异调节表「从 D0-1 带入」接线（un-stub，惠及 7 循环）

**User Story:** 作为审计助理，我在差异调节表点「从 D0-1 带入」时，希望系统真的从对应循环的 X0-1 汇总表拉取不符（差异≠0）的行并填入，而不是弹占位提示或什么都不发生。

#### Acceptance Criteria

1. WHEN 用户在 D0-4/X0-4 点击「从 D0-1 带入」 THEN 系统 SHALL 经通用读取器 `filterSummaryRows(projectId, {对应循环}0-1, defaultDiffFilter)` 拉取 X0-1 中差异≠0 的行，并调用现有 `useD01DiffImport.fetchAndImport(rows)` 映射入表（不新造映射逻辑）。
2. WHEN 拉取到的行的 `confirm_index` 已存在于当前 D0-4 THEN 系统 SHALL 按 `confirm_index` 去重跳过（复用 `useD01DiffImport` 既有去重）。
3. WHERE 循环码由 `wpCode` 派生（D0-4→D0-1、F0-4→F0-1、…、L0-4→L0-1） THE 系统 SHALL 正确解析目标汇总底稿编码。
4. IF 找不到 X0-1 汇总底稿或其无 `confirmation-v1` 数据 THEN 系统 SHALL 给出明确提示（「未找到 X0-1 / X0-1 暂无差异数据」），不静默、不抛错崩溃。
5. WHEN 只读态（`readonly=true`） THEN 「从 D0-1 带入」按钮 SHALL 不可用。
6. THE 接线 SHALL 仅在共享组件 `diffReconcile/` 一处改动，自动惠及全部 7 循环，且**不新增任何后端端点**。

### Requirement 2: D0-7 可靠性验证表「从 D0-1 带入电子回函」接线（un-stub，惠及 7 循环）

**User Story:** 作为审计助理，我在可靠性验证表点「从 D0-1 带入电子回函」时，希望系统真的筛出 X0-1 中回函方式为传真/电子邮件的行并为每条创建验证记录。

#### Acceptance Criteria

1. WHEN 用户在 D0-7/X0-7 点击「从 D0-1 带入电子回函」 THEN 系统 SHALL 经 `filterSummaryRows(projectId, {对应循环}0-1, defaultElectronicReplyFilter)` 拉取电子回函行并映射为可靠性验证行（函证索引号/被询证单位/回函方式/回函日期）。
2. WHEN 目标行的 `confirm_index` 已存在 THEN 系统 SHALL 去重跳过。
3. IF 找不到汇总底稿或无电子回函行 THEN 系统 SHALL 明确提示，不静默。
4. WHEN 只读态 THEN 按钮 SHALL 不可用。
5. THE 接线 SHALL 仅改共享组件 `reliability/` 一处，惠及 7 循环，零新后端；且 SHALL 移除既有占位提示 `'从 D0-1 带入功能待跨底稿引用 API 接入后启用'`。

### Requirement 3: 退役死脚手架 dispatch_records（前端删除，后端休眠）

**User Story:** 作为维护者，我希望删除从未被采用的 dispatch_records 前端脚手架，消除「存在但零消费」的认知噪声，同时不破坏已建后端资产的可回滚性。

#### Acceptance Criteria

1. WHEN 复盘确认 `useConfirmationDispatch` 与 `useDownstreamDispatch` 均零组件消费者（仅注释/自身测试引用） THEN 系统 SHALL 删除这两个前端 composable 及其单元测试文件，并从 `coordination/index.ts` 移除对应导出。
2. WHERE `dispatchApi.ts` 在删除上述二者后无任何其它消费者 THE 系统 SHALL 一并删除 `dispatchApi.ts`；IF 仍有消费者则保留并记录。
3. THE 后端 `dispatch_service.py`/`dispatch_records.py` 路由/`dispatch_models.py`/V093 表 SHALL **保留不删**（删表是破坏性 DDL），但 SHALL 在路由/service docstring 标注 `DEPRECATED: cross-workpaper-dispatch-persistence 未被采用，由 importFromSummary 取代`，供后续运维决定是否清理。
4. THE 删除 SHALL 不影响任何其它模块（删除前 grep 全仓确认无 import）。

### Requirement 4: 舞弊信号自动汇集 D0-2/D0-3/D0-7 → D0-8（useFraudSignalCollector 变 live）

**User Story:** 作为审计助理，我在 D0-8 舞弊风险检查表点「自动填充」时，希望系统把 D0-2 企查查红旗、D0-3 跟函控制失败、D0-7 回函不可靠等上游信号自动汇集到对应检查项，而不是纯规则预填。

#### Acceptance Criteria

1. WHEN 上游底稿检出舞弊迹象（D0-2 地址聚类/号段相邻/撞员工/同寄件人、D0-3 控制检查存在否定项、D0-7 回函验证为不可靠、D0-1 回函率异常低） THEN 系统 SHALL 经 `useFraudSignalCollector` 的对应 `addXxx` 方法产生信号（复用现有映射 `SIGNAL_TO_ITEM_MAP`，不新造信号类型）。
2. WHEN 用户在 D0-8 点「自动填充」 THEN 系统 SHALL 用 `useFraudSignalCollector.exportForD08()` 的结果填入对应检查项（存在=是/索引号/说明），替代当前纯规则预填；且 SHALL 保留人工已填内容不被覆盖（手工优先）。
3. WHERE 舞弊信号当前为纯前端内存态（刷新即丢） THE 系统 SHALL 将汇集后的信号随 D0-8 底稿持久化（存 `checklist_responses`，与 D0-8 现有数据同存储），跨会话可读。
4. IF 上游底稿数据不可读或无信号 THEN D0-8「自动填充」SHALL 降级为现有规则预填（fail-open，不阻断）。
5. THE 信号来源与 D0-8 检查项的映射 SHALL 与 `useFraudSignalCollector.SIGNAL_TO_ITEM_MAP` 严格一致，不在本 spec 新增映射关系（若源模板要求新映射，须单独确认后加）。

### Requirement 5: 零回归与增量可回退

**User Story:** 作为维护者，我希望本 spec 的每项改动 additive、可独立回退，且不破坏任何既有已工作路径。

#### Acceptance Criteria

1. THE R1/R2（D0-4/D0-7 接线）、R3（退役）、R4（舞弊汇集）SHALL 各自独立可发布、可回退。
2. WHEN 用户未触发新功能（不点带入/不点自动填充） THEN 既有 D0-4/D0-7/D0-8 行为 SHALL 逐字节等价当前。
3. THE 既有 `importFromSummary`（K05/K06/L05/H05 替代程序的 unreplied-entities 带入）、`confirmation-v1` 格式、`_REVERSAL_TARGETS` 撤回状态机、覆盖率单一真源、`list_match_queue` 附件匹配 SHALL 不改动语义。
4. WHERE 共享组件（diffReconcile/reliability/fraudRisk）在并发会话活跃编辑中 THE 改动 SHALL 采用最小侵入（只加接线不重构），并在提交前 `git status` 核实只 stage 本 spec 文件。

### Requirement 6: 正确性属性可测

**User Story:** 作为维护者，我希望关键正确性属性有生成式/契约测试守卫，防漂移。

#### Acceptance Criteria

1. THE D0-4/D0-7 带入的过滤器（`defaultDiffFilter`/`defaultElectronicReplyFilter`）与去重 SHALL 有单元测试锁定（差异=0 不带入、已存在 confirm_index 去重、只读不触发）。
2. THE 舞弊信号汇集 SHALL 有测试锁定（信号→检查项映射、去重、手工优先不覆盖、fail-open 降级）。
3. THE 退役后 SHALL 有契约守卫：grep 全仓无 `useConfirmationDispatch`/`useDownstreamDispatch` 运行时 import（防误引用复活）。
