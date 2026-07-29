# Design Document

## Overview

F2-3~F2-13 存货明细表加「📥 从序时账取数」按钮，复用 K8/K9 `expenseLedgerMonthlyPull` 纯前端游标分页范式，按明细科目名从 `tb_ledger` 归集本期增加(借方)/减少(贷方)+从 `tb_balance` 补期初余额。灰度 `F2_FOUR_TABLE_EXTRACTION_ENABLED` 门控。

## Architecture

### 决策 1：纯前端取数（不新建后端端点）

复用已存在的 `GET /api/projects/{pid}/ledger/entries/{account_code}?year=&page=&page_size=200` 游标分页接口（`ledger_penetration_service.get_ledger_entries`），前端逐页翻完按 `account_name` 分组聚合。同 K8/K9 `expenseLedgerMonthlyPull.ts` 一次性实现。

### 决策 2：共享可复用 helper（不 per-sheet 复制）

新建 `composables/f2DetailLedgerPull.ts`（单一共享 helper）：
- `pullF2DetailFromLedger(projectId, accountCode, year)` → `{rows: [{name, increase, decrease}], total: {increase, decrease}}`
- `pullF2DetailOpening(tbValues, accountCode)` → `{rows: [{name, opening}]}`（从 render 已带的 tb_values 或直接从 f2_extraction.extract 结果取）
- 各 F2DetailSheet 组件统一调此 helper（传自己的 accountCode），不各自写一份

### 决策 3：与既有 composable 行模型对接

各明细表 composable（`useF2Detail*`）已有 `addRow()`/`updateRow(rowKey, field, value)` 或类似接口。helper 返回结果后，由调用方组件按行名匹配已有行（精确→包含→新增），调用 composable 既有接口写入，经正常 save 路径持久化（不绕过）。

### 决策 4：期初数据来源

- **优先**从 render 输出的 `tb_values`（灰度开时含各类别 opening）按 rowKey 取；
- **回退**从 `tb_balance` 取叶子子科目 opening（经 `f2_extraction.extract` 已实现的 `extract_f2_category_values` 间接获取）；
- **最简实现**：render 的 tb_values 已含 opening（按类别聚合），但明细表需**按子科目名拆分**的 opening→只能从序时账相邻的 tb_balance 查询获得。故明细表 opening 直接取序时账同 account_name 对应行在 tb_balance 的 opening_balance。**前端无法直接查 tb_balance**→ 改用后端 render 已输出的 `adjudication_prefill`（灰度开时含各类别 source_codes 叶子码列表），或接受明细表 opening 从序时账推断（opening = closing − increase + decrease，会计恒等式）。
- **最终决策**：明细表 opening **不从四表库取**（宁缺勿造），只取 increase/decrease（序时账直接可得），opening 留审计师手工或从导入补。这与 K8/K9 范式一致（费用明细只取月度发生额不取期初）。

### 决策 5：科目映射

```typescript
const F2_DETAIL_SHEET_ACCOUNT: Record<string, string> = {
  'F2-3': '1401',   // 原材料
  'F2-4': '1402',   // 材料采购在途
  'F2-5': '1403',   // 周转材料
  'F2-6': '1404',   // 自制半成品
  'F2-7': '1405',   // 委托加工物资
  'F2-8': '1406',   // 库存商品
  'F2-9': '1407',   // 发出商品
  'F2-10': '1408',  // 开发产品
  'F2-11': '1409',  // 开发成本
  'F2-12': '1410',  // 合同履约成本
  'F2-13': '1411',  // 消耗性生物资产
}
```

## Components and Interfaces

### 新建 `composables/f2DetailLedgerPull.ts`

```typescript
export interface LedgerPullRow {
  name: string        // 明细科目名（account_name 末段）
  accountCode: string // 科目编码
  increase: number    // Σ debit_amount
  decrease: number    // Σ credit_amount
}

export interface LedgerPullResult {
  rows: LedgerPullRow[]
  totalIncrease: number
  totalDecrease: number
  pagesFetched: number
}

export async function pullF2DetailFromLedger(
  projectId: string,
  accountCode: string,
  year: number | string,
): Promise<LedgerPullResult>
```

### 各 F2DetailSheet 组件改动（additive）

- 工具栏加「📥 从序时账取数」按钮（`v-if="灰度开"` + `:disabled="isReadonly"` + `:loading`）
- 点击→调 `pullF2DetailFromLedger`→ElMessageBox.confirm 预览→按名匹配/追加→composable save

## Data Models

无新增 DB 表/列。取数结果经各明细表 composable 既有 addRow/updateRow 写 checklist_responses。

## Correctness Properties

### Property 1: 按科目名归集
同一 `account_name` 的多笔分录 debit/credit 累加为一行。
**Validates: Requirements 1.2, 5.3**

### Property 2: 手工优先
已有同名行且 increase/decrease 非零时不覆盖。
**Validates: Requirements 1.4**

### Property 3: 追加新行
取数结果含明细表不存在的行名→追加新行。
**Validates: Requirements 1.5**

### Property 4: 取数失败不阻断
API 异常→ElMessage.warning + 返回空结果，不清空既有行。
**Validates: Requirements 1.6**

### Property 5: 科目一一对应
F2-3 只取 1401，F2-8 只取 1406，不混入其他科目。
**Validates: Requirements 5.1, 5.2**

### Property 6: 灰度零回归
`F2_FOUR_TABLE_EXTRACTION_ENABLED=False` 时按钮不显示，明细表行为不变。
**Validates: Requirements 6.1**

### Property 7: 复用序时账端点
不新建后端端点，走 `/ledger/entries/{code}` 游标分页。
**Validates: Requirements 4.1**

## Error Handling

- 序时账端点 404/500 → `ElMessage.warning('序时账取数失败')` + 返回空
- 某页超时 → 中断翻页，用已拉取数据（partial result）
- 无数据 → `ElMessage.info('该科目序时账无数据')`
- 灰度关 → 按钮不渲染，零代码路径触发

## Testing Strategy

- `f2DetailLedgerPull.spec.ts`（vitest）：mock `/ledger/entries` 返回→验证 Property 1/2/3/4/5/7
- 各 F2DetailSheet curl Vite transform 200
- 灰度关时按钮不渲染（Property 6）
