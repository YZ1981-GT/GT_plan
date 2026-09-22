# Requirements — D4 价格分析双向回写联动（D4-10/11）+ 行同步回写死代码修复

## 背景与目标

D4 营业收入循环存在两处联动缺陷，本 spec 一并解决：

1. **D4-2/3 行同步回写是死代码**：`useD4CrossSheet.ts` 的 `syncProductRowToAdjudication` / `syncOtherItemRowToAdjudication` 发 `d4:sync-row` CustomEvent，但全代码库**无任何接收端**（grep 实证仅两处发送）。`useD4Adjudication.ts` 的 `sections` 只遍历自己的 `dynamicRows`，D4-2 明细产品行不会自动成为 D4-1 审定表行——「D4-2 增删产品行 → D4-1 审定表联动」从未打通。参照 D2 范式（`useD2CrossSheet` 的共享 reactive store + computed 派生链，非行同步事件）修复。

2. **D4-10（重要客户销售价格分析）/ D4-11（产品销售价格分析）完全孤立**：纯手工录入，无上游取数、无回写联动。D4-10 的「本期销售总额」tooltip 已写明"数据来源: D4-9 或 D4-2 合计"但从未联动；D4-11 组件的 `GtIndexChip value="wp:D4-10"` 指错（应为 D4-11）。

**上游取数走公式管理/联动引擎；回写采用方案 C（异常回标上游 + 结论供附注）。**

## 术语

- **上游取数**：D4-10 从 D4-9 客户结构 / D4-2 主营明细导入客户/产品行与金额；D4-11 从 D4-2 主营明细导入产品行与金额。
- **回写联动**：D4-10/11 识别的异常定价客户/产品 → 回标上游 D4-9/D4-2 对应行；价格分析结论/异常清单 → 汇入 D4 附注/审计说明供下游消费。
- **行同步回写（打通）**：D4-2/D4-3 明细行增删 → D4-1 审定表按 computed 自动派生对应行（D2 范式）。

## Requirements

### Requirement 1: D4-2/3 → D4-1 行同步回写打通（参照 D2）

**User Story:** 作为审计助理，我在 D4-2 主营明细增删产品行后，希望 D4-1 审定表自动出现/移除对应审定行，无需手工添加。

#### Acceptance Criteria

1. WHEN D4-2 明细存在产品行 THEN D4-1 审定表主营区块 SHALL 自动派生对应审定行（按产品名，computed 自 `D4-2-rows`），无需手工「添加产品行」。
2. WHEN D4-3 明细存在项目行 THEN D4-1 审定表其他区块 SHALL 自动派生对应审定行（按项目名，computed 自 `D4-3-rows`）。
3. WHEN D4-2/D4-3 删除某行 THEN D4-1 对应自动派生行 SHALL 同步消失（下一次 computed 重算）。
4. THE 自动派生行 SHALL 标记 `isFromCrossSheet=true`（浅蓝背景、金额列只读），与手工行区分；手工行仍可自由增删编辑，且手工行 AJE/RJE 编辑 SHALL NOT 被派生逻辑覆盖。
5. THE `useD4CrossSheet.ts` 的死代码 `syncProductRowToAdjudication` / `syncOtherItemRowToAdjudication`（发 `d4:sync-row` 无接收端）SHALL 被删除或改造为真实生效的接线，不留发了无人听的 CustomEvent。
6. WHEN 自动派生行与手工行同名 THEN 系统 SHALL 去重（同名归一，以派生行金额为准，避免重复行）。

### Requirement 2: D4-10 上游取数（从 D4-9/D4-2）

**User Story:** 作为审计助理，我打开 D4-10 客户价格分析时，希望能一键从 D4-9 客户结构导入重要客户行并自动带出本期销售总额，而非全手工录入。

#### Acceptance Criteria

1. THE D4-10 SHALL 在主表工具栏提供「从上游导入」入口（并入现有「导入导出 ▾」或平铺按钮，`:disabled="isReadonly"`，loading 防重复）。
2. WHEN 点击导入 THEN 系统 SHALL 从 D4-9 客户结构数据（`customerStructureData`，派生自 `D4-2-rows`）取重要客户行，按客户名 merge 进 D4-10 明细（客户名/销售金额），已存在的客户行不覆盖手工改过的值。
3. THE D4-10「本期销售总额」SHALL 由公式自动取（`WP('D4-2','合计')` 或等价联动），替换当前纯手工 `el-input-number`；仍允许手工覆盖（手工优先）。
4. WHEN 上游 D4-9/D4-2 无数据 THEN 系统 SHALL 给可辨别中文提示（如「D4-2 主营明细为空，请先编制 D4-2」），不静默填 0 或造数据。
5. THE 导入 SHALL 只填录入列（客户名/金额/数量），派生列（占比等）交前端 computed 重算。

### Requirement 3: D4-11 上游取数（从 D4-2）

**User Story:** 作为审计助理，我打开 D4-11 产品价格分析时，希望能一键从 D4-2 主营明细导入产品行并带出销售金额。

#### Acceptance Criteria

1. THE D4-11 SHALL 在主表工具栏提供「从上游导入」入口（并入「导入导出 ▾」，`:disabled="isReadonly"`，loading 防重复）。
2. WHEN 点击导入 THEN 系统 SHALL 从 D4-2 主营明细（`productRevenueForMargin`，派生自 `D4-2-rows`）取产品行，按品种 merge 进 D4-11 明细（品种/销售金额），不覆盖手工改过的值。
3. WHEN 上游 D4-2 无数据 THEN 系统 SHALL 给可辨别中文提示，不静默填 0。
4. THE D4-11 组件的 `GtIndexChip value="wp:D4-10"` bug SHALL 修正为 `wp:D4-11` 应有的正确交叉引用（指向其真实上游 D4-2）。
5. THE 导入 SHALL 只填录入列，派生列（与定价差异/与市价差异）交前端 computed 重算。

### Requirement 4: 回写联动方案 C — 异常回标上游

**User Story:** 作为现场经理，我希望 D4-10/11 中标记为价格异常的客户/产品，能在上游 D4-9/D4-2 对应行看到异常标记，形成审计追溯闭环。

#### Acceptance Criteria

1. WHEN D4-10 某客户行的「与均价差异」或「与市场差异」绝对值超过阈值（默认 20%）THEN 系统 SHALL 将该客户标记为价格异常，并经联动写回 D4-9 客户结构对应行的异常标记（或 remark）。
2. WHEN D4-11 某产品行的「与定价差异」或「与市价差异」绝对值超过阈值（默认 10%）THEN 系统 SHALL 将该产品标记为价格异常，并联动写回 D4-2 主营明细对应行的异常标记。
3. THE 异常回标 SHALL 经 eventBus（非裸 `window.dispatchEvent`），且接收端 SHALL 真实存在并消费（不得再制造死代码）。
4. WHEN 上游行找不到对应客户/产品 THEN 系统 SHALL 静默跳过该条回标（不报错、不造行）。
5. THE 异常回标 SHALL 幂等：同一异常重复触发不重复标记、取消异常时标记应随之清除或更新。

### Requirement 5: 回写联动方案 C — 结论供附注/审计说明

**User Story:** 作为业务合伙人，我希望 D4-10/11 的价格分析结论与异常清单能汇入 D4 附注/审计说明，供下游披露消费。

#### Acceptance Criteria

1. WHEN D4-10/11 审计说明或结论保存 THEN 系统 SHALL 经 eventBus 发布联动事件（复用 `substantive:adjudicated` / `disclosure:note-text-updated` 现有事件族），使 D4 附注/审计说明区可消费。
2. THE D4-10/11 的价格异常清单 SHALL 可供 D4-1 审计说明或附注引用（如"存在 N 个价格异常客户/产品，详见 D4-10/D4-11"）。
3. THE 结论汇入 SHALL 走既有跨底稿事件桥（`crossWpEventBridge`），不新造平行传输通道。
4. IF 上游附注消费方不存在 THEN 事件发布 SHALL 不报错（fail-safe），但发送端与接收端接线关系必须在守卫中锁死。

### Requirement 6: 接线补齐（防死代码回归）

#### Acceptance Criteria

1. THE 宿主 `GtD4OperatingRevenue.vue` SHALL provide `d4CrossSheet`（或等价联动数据）给子表消费，使 `useD4CrossSheet` 的聚合数据不再是未接线死代码。
2. THE 凡新增的 `window.dispatchEvent(new CustomEvent('d4:...'))` 或 eventBus emit SHALL 有对应的、真实生效的接收端。
3. WHERE 公式管理适用（D4-10 本期销售总额等单标量）THE 取数 SHALL 经公式管理体系（`WP()` 公式 + render seed），不硬编码取数逻辑。

### Requirement 7: 守卫与验证

#### Acceptance Criteria

1. THE 前端守卫（vitest）SHALL 断言：D4-2 加行后 D4-1 派生行数变化（行为，非字符串存在）；导入按钮点击真发请求到字面量正确的端点 URL；异常回标事件真被接收端消费。
2. THE 变异检验 SHALL 覆盖：删接收端 → 打红；改错端点循环前缀 → 打红；把行派生 computed 依赖改错 → 打红。四态判定（RED/GREEN/ANCHOR-MISS/WRONG-TEST），GREEN 即守卫缺陷。
3. THE 后端守卫 SHALL 断言 resolver 归集正确（若新增 resolver）。
4. THE 真栈 Playwright 实测 SHALL 验证：D4-2 加产品行→D4-1 出行；D4-10/11 导入→行数对齐上游；异常回标可见；结论进附注。证据落 evidence JSON。

## 非目标

- 不改 D4-10/11 的 OnlyOffice 在线编辑模式（仅结构化视图联动）。
- 不新增账龄相关逻辑（价格分析无账龄）。
- 不改 D4-1 审定表的四表库预填（`adjudication_prefill`）既有机制，仅补行结构 computed 派生。


### Requirement 8 — 统一治理边界与里程碑
1. C0模板/identity、C1sync、C2formula、C3linkage、C4逐表验收必须有独立证据；D4-10/11逻辑编码与物理sheet/变体分开。
2. 公式key使用wp_id，preset_version仅为定义版本；preset升级保留custom，删除custom恢复preset，缺失/损坏/stale/blocked分态，schema白名单禁eval和外链。
3. 不同字段自动合并，同字段保留三方冲突轨迹；durable ack不等于applied；联动同步不是TB/A13，发布需显式确认。
4. 只门控价格分析相关平台产物，不等待全平台77项。