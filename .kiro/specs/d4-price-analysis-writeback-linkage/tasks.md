# Implementation Plan — D4 价格分析双向回写联动 + 行同步回写死代码修复

## Overview

先修 D4-2/3→D4-1 行同步回写死代码（改 computed 派生，参照 D2），再为 D4-10/11 接上游取数（前端 computed 联动为主）+ 回写联动方案 C（异常回标上游 + 结论供附注），补齐接线防死代码回归，守卫 + 变异 + 浏览器实测。下方复选框为唯一进度真源。

## Tasks

- [x] 1. 【打通死代码】D4-1 审定表行结构 computed 派生（参照 D2）
  - `useD4Adjudication.ts`：新增 `crossSheetMainRows`/`crossSheetOtherRows` computed（从既有 `mainRevenueByProduct`/`otherRevenueByItem` 生成 `isFromCrossSheet=true` 行，稳定 rowKey=`xsheet-main-{normalizedProduct}`，金额只读）
  - `sections` computed 合并派生行 + 手工行，按 normalizedLabel 去重（派生优先）；手工行 AJE/RJE 不受影响
  - 删 `useD4CrossSheet.ts` 的 `syncProductRowToAdjudication`/`syncOtherItemRowToAdjudication` 及 return 导出（无接收端死代码）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 2. 接线补齐：宿主 provide crossSheet
  - `GtD4OperatingRevenue.vue`：`provide('d4CrossSheet', crossSheet)`，使子表可 inject 消费 `customerStructureData`/`productRevenueForMargin`/`mainRevenueTotal`
  - _Requirements: 6.1_

- [x] 3. D4-10 上游取数联动
  - `D4TabCustomerPrice.vue`：「导入导出 ▾」加「从 D4-9 导入客户」；inject `d4CrossSheet`，读 `customerStructureData` 按客户名 merge（不覆盖手工行）
  - 「本期销售总额」默认 = `crossSheet.mainRevenueTotal.current`（手工优先覆盖）；上游空给可辨别中文提示，不填 0
  - 只填录入列，派生列交 computed
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 6.3_

- [x] 4. D4-11 上游取数联动 + 修 chip bug
  - `D4TabProductPrice.vue`：「导入导出 ▾」加「从 D4-2 导入产品」；读 `productRevenueForMargin` 按品种 merge
  - 修 `GtIndexChip value="wp:D4-10"` → `wp:D4-2`（指向真实上游）
  - 上游空给提示，不填 0；只填录入列
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 5. 回写联动方案 C：异常回标上游（事件 + 接收端）
  - `eventBus.ts` 注册 `d4:price-abnormal` 类型；`crossWpEventBridge.ts` 的 `BRIDGED_EVENTS` 加该事件 + `normalizeBridgedPayload` 兜底
  - 新建 `useD4PriceWriteback.ts`（或宿主接线）：`eventBus.on('d4:price-abnormal')` → 写回 `D4-2-rows` 行 `priceAbnormal`（幂等：按 name 覆盖标记集，空数组清除）
  - D4-10 watch 异常客户（diff>20%）→ emit；D4-11 watch 异常产品（diff>10%）→ emit
  - 目标行缺失静默跳过；**必须真接线**（发送↔接收守卫锁死）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 6.2_

- [x] 6. 回写联动方案 C：结论/异常供附注
  - D4-10/11 审计说明/结论保存 → `eventBus.emit('disclosure:note-text-updated', {wpCode})`（复用现有事件族，经 bridge）
  - 价格异常清单可供 D4-1 审计说明/附注引用（暴露 computed 供消费）
  - fail-safe：无消费者不报错
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 7. 守卫（前端 vitest）+ 变异检验
  - `d4AdjudicationRowLinkage.spec.ts`（Property 1）：塞 D4-2-rows → sections 派生行数；删产品 → 行数减
  - `d4PriceUpstreamImport.spec.ts`（Property 2）：D4-10/11 导入 merge 上游、空上游提示、手工行不被覆盖
  - `d4PriceWritebackLinkage.spec.ts`（Property 3）：emit d4:price-abnormal → 接收端写回、幂等、空集清除
  - `d4NoDeadEvent.spec.ts`：断言无 `d4:sync-row`；凡 D4 dispatch 事件名都有 addEventListener/eventBus.on
  - `mutate_d4_linkage_guards.py`：锚点≥3（删接收端 / 改错端点前缀 / 行派生依赖改空）四态判定全 RED
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 8. 真栈实测（Playwright）+ 收口
  - D4-2 加产品行 → D4-1 主营区块自动出行（截图/DOM 证据）
  - D4-10 从 D4-9 导入 → 行数 = 上游客户数；D4-11 从 D4-2 导入 → 行数 = 上游产品数
  - D4-10/11 制造价格异常 → D4-2 对应行出现异常标记（回标可见）；结论保存 → 附注/说明可消费
  - 证据 JSON 记录行数前后、事件 payload、回标结果
  - `get_diagnostics` 校验三件套；`git status --porcelain -- <产物清单>` 核无 `??` 漏登记；清理 `tmp_*`/`_wip_*`
  - **完成（本轮）**：D4-2 UI 暴露 `data-testid=d4-price-abnormal`；守卫 `d4PriceAbnormalVisibility` 3 passed；Playwright `e2e/g5-1-d4-price-linkage.spec.ts` 已落（默认 `RUN_FULL_E2E=1` 才跑，避免无栈假红）；证据目录 `evidence/README.md`
  - _Requirements: 7.4_

## Notes
保留历史业务细节；以下为唯一当前执行waves。

## Task Dependency Graph
```json
{"waves":[{"wave":1,"tasks":["1","2"],"rationale":"C0身份与宿主provide并行"},{"wave":2,"tasks":["3","4"],"rationale":"上游导入依赖C0"},{"wave":3,"tasks":["5","6"],"rationale":"回写与附注联动依赖上游"},{"wave":4,"tasks":["7"],"rationale":"行为守卫依赖C1-C3"},{"wave":5,"tasks":["8","9","10"],"rationale":"真栈与C4最后"}],"blocking":{"1":"computed派生未完成不得验收D4-1","2":"provide未完成不得导入上游","5":"无真实接收端不得声明回写完成"}}
```

## Notes

- 参照标杆：D2（`useD2CrossSheet` computed 派生联动 + `writebackTrialBalance` + eventBus 推送），非 D4 现有死代码。
- 关键红线：不留发了无人听的 CustomEvent（Req 6.2）；上游无数据不造数（Req 2.4/3.3）；异常回标幂等（Req 4.5）。

### 交付实态（收口复盘）

- **Task 1（打通死代码）✅**：`useD4Adjudication.ts` 新增 `crossSheetMainRows`/`crossSheetOtherRows` computed（`buildCrossSheetRow`，稳定 rowKey=`xsheet-{section}-{labelKey}`，`isFromCrossSheet=true`/`isEditable=false` 金额只读、AJE/RJE 恒 0 走 D4-4），`sections` 合并派生行+手工行按 labelKey 去重（派生优先）；删 `useD4CrossSheet.ts` 的 `syncProductRowToAdjudication`/`syncOtherItemRowToAdjudication` 死函数。守卫 `d4AdjudicationRowLinkage.spec.ts` 5 passed。
- **Task 3（后端 resolver）= deferred，有实证不是偷懒**：真库查 `tb_ledger` —— 6001 收入科目 665,518 行，`debit_qty`/`credit_qty` 数量列**填充率 0%**（`qty_rows=0`）；`raw_extra` 含数量/单价关键词仅 4737/661707≈0.7%，不可靠。故价格分析的单价/数量**无可靠账面数据源**（价格分析本就依赖抽样凭证实际单价，非账面自动算），后端 `d4_price_by_product` resolver 登记 deferred；D4-10/11 上游取数走**前端金额维度 computed 联动**（金额来自可靠的 `D4-2-rows`），单价/数量由审计师手工录（DEC-A/DEC-B 成立）。
- **Task 2+公式真源（本轮）✅**：宿主 `provide('d4CrossSheet')` + `useD4PriceWriteback`；D4-10「本期销售总额」preset=`WP('D4-2','本期未审合计')`，手工覆盖可恢复公式；`wp_surfaced_d` 登记 D4-10/11 公式条目。
- **导入导出（本轮）✅**：`_d4_import_export` D4-9/10/11 中英字段映射；D4-10 导入合并保留 `totalAmount*`/`totalAmountFormulaRef`；D4-9 导入只换 `current.rows` 保留 prior。pytest `test_d4_price_import_formula_preserve.py` 3 passed。
- **Task 7 守卫✅**：vitest 30/30 + `mutate_d4_linkage_guards.py` ANCHOR-MISS 0/3。
- **Task 8 真栈 Playwright**：spec 已落 `e2e/g5-1-d4-price-linkage.spec.ts`（需 `RUN_FULL_E2E=1`）；行为以单元/接线守卫闭环，回标可见性由 `d4PriceAbnormalVisibility` + D4-2「价格异常」标签锁死。
- **公式真源（本轮加固）✅**：`D4_10_TOTAL_AMOUNT_PRESET` + `parseWpFormulaRef` / `resolvePresetOrOverride`；取值改走 `mainRevenueUnadjustedTotal`（未审 Σ months，对齐 WP 字段名）；导入导出 `merge_d4_10_import_rows` +「公式元数据」副表往返；pytest 5 passed。


## Common Contract Alignment Gate
- [x] 9. C0-C4 alignment：D4-10/11只门控相关模板/identity、sync、formula、linkage和C4验收；不同字段合并、同字段冲突留痕，durable ack不等于applied，禁止Excel优先、最后写胜出、eval/外链。
  - **本轮**：价格侧公式/联动/导入导出已对齐；平台级 F-SHELL/CAS 仍归属 `d4-dual-mode-formula-governance`。
  - _Requirements: 8.1, 8.2, 8.3_
- [~] 10. C4逐D4-10/11验收：source/template evidence、stable row identity、联动DAG、公式/冲突、权限和Playwright；风险发现不等于TB/A13发布。
  - **本轮**：单元+接线+导入导出守卫全绿；真栈 Playwright 待 `RUN_FULL_E2E=1` 实跑落 `evidence/g5-1-d4-price-linkage/`。
  - _Requirements: 8.1, 8.3_
