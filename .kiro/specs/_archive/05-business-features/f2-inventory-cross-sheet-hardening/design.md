# Design Document

## Overview

F2 存货底稿跨底稿勾稽与智能取数加固设计。在既有 F2 模块（4 主入口 + 114 composable）上做**加法增强**，不改架构。核心是三条可复用管线：后端 render 预填、跨底稿 pull 纯函数、EventBus 联动。

## Architecture

### 架构总览

本设计在既有 F2 模块（4 主入口 + 114 composable）上做**加法增强**，不改架构。核心是三条可复用管线：

```
┌─────────────────────────────────────────────────────────────────┐
│ 管线 A：后端 render 预填（无依赖，基础设施）                        │
│   _f2_inventory_main.py.render()                                  │
│     ├─ _load_project_context → +bs_date +related_parties (照 H2)   │
│     └─ _build_adjudication_prefill(ctx) → tb_balance 1401~1471 分类 │
│           → responses/tb_values 供 useF2Adjudication seed          │
├─────────────────────────────────────────────────────────────────┤
│ 管线 B：跨底稿 pull 纯函数（复用 h1CipH2Pull 范式）                 │
│   f2D4CostPull.ts / f2LedgerPostOutbound.ts / f2NrvPricePull.ts    │
│     resolveWpId(pid,code) + loadResponseItem / ledger/entries      │
│     + extractXxx(纯函数) + buildXxxReconcile(容差)                  │
├─────────────────────────────────────────────────────────────────┤
│ 管线 C：EventBus 联动（复用 crossWpEventBridge）                    │
│   F2 减值 → emit('impairment:calculated') → K11                    │
│   F2 异常 → emit('risk:identified' 或既有风险事件) → B50            │
└─────────────────────────────────────────────────────────────────┘
```

## 关键技术锚点（实测确认）

| 锚点 | 位置 | 现状 |
|------|------|------|
| F2 主 render | `backend/app/routers/wp_render_strategies/_f2_inventory_main.py` | project_context 仅 client_name/audit_year/applicable_standards，**无 bs_date/related_parties/TB 预填** |
| H2 范式参考 | `_h2_construction_in_progress.py` | 有 `_fetch_tb_data`（tb_balance + trial_balance）+ `related_parties` + bs_date，直接照搬 |
| 跨底稿 pull 范式 | `frontend/.../composables/h1CipH2Pull.ts` | `resolveWpId` 经 `/api/custom-query/wp-id-by-code` + `loadResponseItem` 经 `/api/workpapers/{id}/checklist-responses` + 纯函数 extract + `buildReconcile` 容差 |
| F2 内部勾稽 | `useF2CrossSheet.ts` | 仅算 F2 明细→审定，**无跨模块 pull** |
| 明细表 | `useF2DetailSheet.ts` | 有 `postPeriodQty/Amt` 列（无自动取数）、库龄段、`netAmt=closingAmt−impairmentProvision`、`isLongTermRow` |
| FormData | `useF2FormData.ts` | `saveImmediate`/`debouncedSave`/`writebackTrialBalance`/`saveItemsFromEvent` 齐全 |
| 期后取数范式 | D2 `importPostPaymentFromLedger` | 序时账 `ledger/entries` 端点 + 名称归集 + ElMessageBox 预览确认 |
| 减值事件 | `crossWpEventBridge.BRIDGED_EVENTS` | `impairment:calculated` 已在桥（H1/H3/I1 生产，K11 消费）|
| F2 减值 composable | `useF2Impairment`/`useF2ImpairmentTest`/`useF2ImpairmentReversal`/`useF2ObsoleteInventory` | 计算齐全，未 emit 事件 |
| 引导弹窗范式 | `F2PurchaseVoucherDialog.vue`（F2-33）| 5 分组卡片 + 实时勾稽 + OCR，已 gold |
| 监盘 | `GtF2StocktakeBundle` F2-24/F2-25 | `F2TabStocktakeReconcile`/`F2TabStocktakeSampleResult`，两表数据孤立 |
| 截止 | `useF2CutoffSheet` + `useCutoffAutoSampling` | 有自动取数+跨期标注，无三流日期列/跨模块面板 |

## Components and Interfaces

### 管线 A — 后端 render 预填（Req 1, 2）

**A1. `_load_project_context` 扩展**（照 H2 逐字范式）：
```python
project_ctx = {
    "client_name": ..., "audit_year": ..., "applicable_standards": ...,
    "bs_date": f"{audit_year}-12-31",         # 新增
    "related_parties": [],                     # 新增
}
# related_party_registry 查询（try/except 优雅降级返回 []）
```

**A2. `_build_adjudication_prefill(ctx)`**（照 J1/D5 范式）：
- 查 `tb_balance` where account_code LIKE '1401%'..'1412%','1471%'（用 `get_active_filter`）。
- 优先三级明细 → 退二级 → 退一级，按 code 段映射到 `F2_CATEGORIES` rowKey。
- 资产类 opening/closing 直取（存货借方为正），跌价准备 1471 为备抵取绝对值。
- 输出结构对齐前端 `useF2Adjudication` 期望字段（`F2-adjudication-data` 缺失时才 seed）。
- 返回 `tb_values`（各 rowKey 期初/期末未审）加入 render dict。

### 管线 B — 跨底稿 pull 纯函数（Req 3, 4, 10）

**B1. `f2D4CostPull.ts`**（F2→D4 营业成本，Req 3）：
- `pullOperatingCost(projectId, year)`：从 `trial_balance` 取 6401 主营业务成本审定发生额（经既有 project trial-balance 端点或 custom-query），返回 `{ status, operatingCost, message }`。
- `buildCostCarryforwardReconcile(outboundTotal, operatingCost, invBalance, tolPct=0.05)`：纯函数，`diff = outboundTotal − operatingCost`，`matched = |diff| ≤ max(invBalance*tolPct, 1)`。
- 数据源用 TB 口径（稳健，不依赖 D4 底稿内部结构）。

**B2. `f2LedgerPostOutbound.ts`**（期后出库，Req 4，复用 D2 范式）：
- `pullPostPeriodOutbound(projectId, bsYear, accountCode, opts?)`：查 `ledger/entries`（次年 date_from=`{bsYear+1}-01-01` / date_to=默认 6 月末）存货科目贷方，返回 `{ byName: Map, totalAmount, totalQty, unmatchedCount }`。
- `normalizeInvName(name)`：名称规范化（去空白/全角）。
- 纯函数 `aggregateOutboundByName(entries)` 便于单测。

**B3. `f2NrvPricePull.ts`**（NRV 售价参考，Req 10）：
- `pullRecentSalesPrice(projectId, year, itemName?)`：从收入侧序时账 6001 贷方或 D4 明细取近期销售单价，返回参考单价列表。
- 优雅降级（不可得返回空 + status）。

所有 pull 均遵守 `h1CipH2Pull` 结构：`resolveWpId` + `loadResponseItem`/`api.get` + `_silent` + try/catch 返回状态枚举。

### 管线 C — 内部勾稽与联动

**C1. `useF2CrossSheet` 扩展**（Req 3, 11）：
- 新增 `operatingCostReconcile`（消费 B1 pull 结果，computed）。
- 新增 `productionSalesIdentity`：期初+生产入库−销售出库=期末 恒等式 computed（Req 11.1）。
- 新增 `costToPlReconcile`：期初在产品+完工入库−期末在产品 ≈ 营业成本（Req 11.3）。

**C2. F2-1 审定表净额行**（Req 5）：
- `useF2Adjudication` 消费后端 `tb_values` 预填（`F2-adjudication-data` 缺失时 seed）。
- 审定表增"存货净额 = 余额 − 跌价准备(1471)"行（computed，跌价变动自动重算）。

**C3. 明细表期后出库按钮**（Req 4）：
- `useF2DetailSheet` 新增 `importPostPeriodOutbound()`（调 B2 + ElMessageBox 预览 + 填 postPeriodQty/Amt + 只读守卫）。
- `F2DetailSheet.vue` 工具栏加"取期后出库"按钮。

**C4. 减值 → K11**（Req 6）：
- `useF2Impairment`/`useF2ImpairmentTest`/`useF2ImpairmentReversal` 在计算出计提/转回后 `eventBus.emit('impairment:calculated', { wpCode:'F2', accountCode:'1471', amount, ... })`。
- 金额 0 不发。

**C5. 呆滞候选**（Req 7）：
- `useF2ObsoleteInventory` 新增 `importCandidatesFromDetail()`：跨 F2-2~7 读 `-rows`，`isLongTermRow` 过滤，按名称汇总，标"候选"，不覆盖已录。

**C6. 抽盘 → 账面核对回写**（Req 8）：
- `F2TabStocktakeReconcile`/`useF2StocktakeSheet` 新增 `fillActualFromSample()`：读 F2-25 抽盘结果按名称匹配填 F2-24 实盘数 + 未匹配提示。

**C7. 截止三流 + 跨期面板**（Req 9）：
- `useF2CutoffSheet` 行模型加 `inspectDate`/`inboundDate`，`useF2CutoffSheetConfigs` 加列；三日期差异>N天 row-class 标红。
- 新增 `useF2CutoffCrossSheet` 扩展或面板 computed：跨期笔数/金额 + D4/D6 pull（优雅降级提示）。

**C8. NRV 售价参考**（Req 10）：
- `useF2ImpairmentTest` 新增 `pullRecentPrice()`（调 B3），售价列旁"参考"提示，不覆盖手录。

**C9. F2-34 材料领用引导弹窗**（Req 12）：
- 新建 `F2MaterialUsageVoucherDialog.vue`（已存在同名？确认后复用/新建），5 分组卡片（领料单/生产工单/记账凭证/核对项/结论）+ 实时勾稽 + `useF2SubcontractOcr`/`contract-ocr` 复用。
- `F2TabMaterialUsageCheck.vue` 加视图切换（完整表格/逐笔核对）+ 卡片视图 + 操作列"核对"按钮。
- 勾稽纯函数进 `useF2InspectionCheckFormulas`（可单测）。

**C10. F2 异常 → B50**（Req 13）：
- 呆滞/减值异常/毛利率异常 computed 触发 → eventBus 风险信号（复用既有风险事件名，若无则 `risk:identified`）。

## Data Models

### 后端 render 输出扩展（`_f2_inventory_main.py`）

```python
{
  "categories": F2_CATEGORIES,
  "project_context": {
    "client_name": str, "audit_year": str, "applicable_standards": str,
    "bs_date": str,            # 新增 "{audit_year}-12-31"
    "related_parties": [str],  # 新增 从 related_party_registry
  },
  "responses_snapshot": {...},
  "tb_values": {               # 新增 各 rowKey 期初/期末未审
    "raw-materials": {"opening": float, "closing": float}, ...
  },
  "adjudication_prefill": {...},  # 新增 仅无持久化时输出
  "adjudication_blocks": ["gross", "impairment", "net"],
}
```

### 跨底稿 pull 返回结构（复用 h1CipH2Pull 状态枚举）

```typescript
interface PullResult<T> {
  status: 'ok' | 'wp_missing' | 'empty' | 'error'
  message: string
  data: T            // operatingCost / byName / priceList 等
}
interface Reconcile {
  left: number; right: number; diff: number
  matched: boolean; tolerance: number
}
```

## Correctness Properties

以下属性用 Property-Based / 契约测试保障：

**Property 1:** (Req 1) 预填期末合计 == tb_balance 存货科目期末汇总（借正贷负口径）。

**Property 2:** (Req 1) 存在持久化数据时预填不覆盖（幂等：二次渲染不变用户值）。

**Property 3:** (Req 2) related_parties 查询失败 → 返回 [] 且不抛异常。

**Property 4:** (Req 3) `buildCostCarryforwardReconcile` matched ⟺ |diff| ≤ 容差；diff 符号正确。

**Property 5:** (Req 4) `aggregateOutboundByName` 归集金额 == 输入贷方合计；名称规范化幂等。

**Property 6:** (Req 5) 净额行 == 余额 − 跌价准备，跌价变动后重算正确。

**Property 7:** (Req 6) 金额=0 不 emit；金额≠0 emit 一次且 payload 含 accountCode=1471。

**Property 8:** (Req 7) 候选仅含 isLongTermRow=true 行；不覆盖已录判断。

**Property 9:** (Req 8) 抽盘→账面按名称匹配填入；未匹配计数正确。

**Property 10:** (Req 9) 三日期差异 > 阈值 ⟺ 标红；跨期笔数=跨期行数。

**Property 11:** (Req 11) 产销存恒等式差异 == 期初+入−出−期末；成本勾稽 diff 计算正确。

**Property 12:** (Req 12) 材料领用勾稽状态与核对项一致（任一不符 ⟺ 异常）；弹窗保存回写行不丢字段。

## Task Dependency Graph（waves）

```
Wave 0（基础设施，无依赖）：Task 1（render bs_date/related_parties）, Task 2（TB 预填）
Wave 1（跨底稿 pull 纯函数，依赖无）：Task 3（f2D4CostPull）, Task 4（f2LedgerPostOutbound）, Task 5（f2NrvPricePull）
Wave 2（内部勾稽扩展，依赖 W0/W1）：Task 6（审定预填消费+净额行）, Task 7（明细期后出库按钮）, Task 8（CrossSheet 成本/产销存勾稽）
Wave 3（联动）：Task 9（减值→K11）, Task 10（呆滞候选）
Wave 4（监盘+截止）：Task 11（抽盘→核对回写）, Task 12（截止三流+跨期面板）
Wave 5（NRV+材料领用）：Task 13（NRV 售价参考）, Task 14（F2-34 引导弹窗）
Wave 6（风险信号）：Task 15（F2 异常→B50）
Wave 7（验证）：Task 16（前端 vitest）, Task 17（后端 pytest）, Task 18（Playwright E2E）
```

## Error Handling

- 跨底稿 pull：`wp_missing`/`empty`/`error` 状态明确提示，不崩溃。
- 后端 render：所有新增查询 try/except + warning 日志，不阻断主渲染。
- 事件：桥接层再入守卫已在 `crossWpEventBridge`，F2 只需 emit。
- 只读态：所有取数/回写按钮在 isReadonly 时禁用。
- ref 契约：新组件 props 解包 + toRef 重包，避免 ref-unwrap 崩溃。

## Testing Strategy

- **前端 vitest**：跨底稿 pull 纯函数（f2D4CostPull/f2LedgerPostOutbound/f2NrvPricePull）+ CrossSheet/Adjudication/ObsoleteInventory/Stocktake/Cutoff/InspectionCheckFormulas，覆盖 P1-P12。
- **后端 pytest**：`_build_adjudication_prefill`（P1/P2）+ related_parties 降级（P3），真实 PG16。
- **Playwright E2E**：已实例化 F2 项目 round-trip（审定预填/期后出库/减值→K11/截止三流/材料领用弹窗），0 console error。
- **不假绿**：标记完成前测试真实通过 + 关键路径 Playwright 实测。
