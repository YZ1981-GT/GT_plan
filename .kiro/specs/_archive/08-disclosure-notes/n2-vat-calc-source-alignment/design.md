# N2-6 增值税测算表源模板对齐 — 设计

## Overview

把 N2-6 从「自造按月/季税率矩阵」改造为「源模板四段式测算表 + 附加分析区」。

核心设计取向：
1. **纯函数公式引擎与 UI 分离** —— 四段的全部派生列收敛到 `useN2VatSourceEngine.ts`（零依赖 leaf，可单测），组件只做渲染与事件绑定。
2. **派生列不持久化** —— 计税收入 / 应计销项税 / 测算数 / 差异 / 合计全部读时推导，落库只存录入列（平台铁律，避免 D1 那类「派生值存库后用旧分母算错」缺陷）。
3. **跨段引用显式建模** —— `F30`/`F39` 依赖（一）的 `C17`/`C18`，用引擎入参显式传递而非组件内隐式取值，使勾稽可单测。
4. **附加分析区隔离** —— 既有 `useN2VatCalc` 原样保留（键不变、能力不变），只在 UI 上降级并标注；两套口径互不参与对方勾稽。

## Architecture

```
N2TabVatCalc.vue（重写 template，script 增量）
├── （一）申报表核对区   ── DECLARATION_ITEMS(10 固定项)
├── （二）销项测算区     ── 动态行 + 合计 + 待转销项 + 差异结论
├── （三）进项测算区     ── 动态行 + 合计 + 3 调节项 + 差异结论
├── （四）特殊情况检查区 ── SPECIAL_ITEMS(4 固定项)
├── 审计说明 / 审计结论（el-card）
└── 【审计分析·不在源模板】按月/季矩阵  ← 既有 useN2VatCalc 原样
        ↑
        │ 数据层
useN2VatSourceCalc.ts（新增 composable：持久化 + computed 组装）
        └── useN2VatSourceEngine.ts（新增纯函数引擎：全部公式）

useN2CrossSheet.ts（改 adjudicationVsCalcTables → 按 taxType 现算）
```

持久化键（沿用 `saveField(sheet, field)` → `N2-{sheet}-{field}` 规则，sheet='6'）：

| item_id | 内容 | 形状 |
|---------|------|------|
| `N2-6-declaration-rows` | （一）10 固定项的录入列 | `Array<{key, book, declared, reason}>` |
| `N2-6-output-rows` | （二）销项动态行录入列 | `Array<{id, variety, sales, exemptSales, rate}>` |
| `N2-6-output-pending` | （二）待转销项税额期末减期初 | number |
| `N2-6-input-rows` | （三）进项动态行录入列 | `Array<{id, project, amount, rate}>` |
| `N2-6-input-adjust` | （三）三个调节项 | `{deductible, uncertified, retained}` |
| `N2-6-special-rows` | （四）4 固定项金额 | `Array<{key, amount}>` |
| `N2-6-vat-payable` | 应交增值税（供 N2-8） | number（R6：由（一）C17−C18 派生后写入） |
| `N2-6-note` / `N2-6-conclusion` | 审计说明 / 结论 | string（remark） |
| `N2-6-vat-rows` / `N2-6-period-mode` / `N2-6-declared-payable-vat` | 附加分析区（**不动**） | 既有形状 |

## Components and Interfaces

### useN2VatSourceEngine.ts（新增，零依赖纯函数）

```ts
/** （一）差异 = 账面 − 申报表 */
export function calcDeclarationDiff(book: number, declared: number): number

/** （二）计税收入 D = 销售额 B − 免税扣除 C */
export function calcTaxableRevenue(sales: number, exemptSales: number): number

/** （二）应计销项税 F = 计税收入 D × 税率 E */
export function calcOutputTax(taxableRevenue: number, rate: number): number

/** （三）测算数 F = 发生额 D × 税率 E */
export function calcInputTax(amount: number, rate: number): number

/**
 * （二）差异（源模板 F30 = C17 − F28 − F29）
 * @param bookOutputTax （一）第 6 项「销项税额」账面数据 C17
 * @param outputTaxTotal （二）应计销项税合计 F28
 * @param pendingOutputTax （二）待转销项税额期末减期初 F29
 */
export function calcOutputVariance(bookOutputTax: number, outputTaxTotal: number, pendingOutputTax: number): number

/**
 * （三）差异（源模板 F39 = F35 − F36 − F37 − F38 − C18）
 * @param inputTaxTotal （三）测算数合计 F35
 * @param adjust 三调节项 {deductible F36, uncertified F37, retained F38}
 * @param bookInputTax （一）第 7 项「进项税额」账面数据 C18
 */
export function calcInputVariance(
  inputTaxTotal: number,
  adjust: { deductible: number; uncertified: number; retained: number },
  bookInputTax: number,
): number

/** R6：应交增值税口径 = （一）销项税额账面 C17 − 进项税额账面 C18 */
export function calcVatPayableFromDeclaration(bookOutputTax: number, bookInputTax: number): number
```

### useN2VatSourceCalc.ts（新增 composable）

```ts
export function useN2VatSourceCalc(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}): {
  // （一）
  declarationRows: ComputedRef<N2VatDeclarationRow[]>   // 含 diff 派生
  bookOutputTax: ComputedRef<number>                     // C17，供（二）
  bookInputTax: ComputedRef<number>                      // C18，供（三）
  updateDeclaration(key: string, field: 'book' | 'declared' | 'reason', v: any): Promise<void>
  // （二）
  outputRows: ComputedRef<N2VatOutputRow[]>              // 含 taxableRevenue/outputTax 派生
  outputTotal: ComputedRef<N2VatOutputTotal>
  pendingOutputTax: ComputedRef<number>
  outputVariance: ComputedRef<N2VatVariance>             // {diff, isMatch}
  addOutputRow(variety: string): Promise<void>
  removeOutputRow(id: string): Promise<void>
  updateOutputRow(id: string, field: N2VatOutputEditable, v: any): Promise<void>
  setPendingOutputTax(v: number): Promise<void>
  // （三）
  inputRows / inputTotal / inputAdjust / inputVariance / addInputRow / removeInputRow / updateInputRow / setInputAdjust
  // （四）
  specialRows: ComputedRef<N2VatSpecialRow[]>
  updateSpecialRow(key: string, amount: number): Promise<void>
  // R6
  syncVatPayable(): Promise<void>                        // 写 N2-6-vat-payable
}
```

固定项清单常量（逐字取源模板，供守卫比对）：

```ts
export const N2_VAT_DECLARATION_ITEMS = [
  { key: 'taxable-sales', label: '1.按适用税率征税销售额' },
  { key: 'deemed-sales', label: '2.视同销售' },
  { key: 'simplified', label: '3.按简易征收办法征税货物' },
  { key: 'export-refund', label: '4.免、抵、退办法出口销售额' },
  { key: 'exempt-sales', label: '5.免税销售额' },
  { key: 'output-tax', label: '6.销项税额' },        // ← C17
  { key: 'input-tax', label: '7.进项税额' },          // ← C18
  { key: 'input-transfer-out', label: '8.进项税额转出' },
  { key: 'export-refundable', label: '9.免、抵、退应退税额' },
  { key: 'other', label: '10.其他' },
] as const

export const N2_VAT_SPECIAL_ITEMS = [
  { key: 'deemed-sales', label: '视同销售' },
  { key: 'large-input-transfer', label: '大额进项税转出' },
  { key: 'financial-goods', label: '转让金融商品应交增值税额' },
  { key: 'withholding', label: '代扣代缴增值税额' },
] as const
```

### useN2CrossSheet.ts（改造）

`adjudicationVsCalcTables` 去掉 `adjudicationKeys` per-tax 映射，改为：
读 `N2-1-adjudication-rows` → 按 `_normalizeTaxNameForN4(row.taxType)` 建 Map →
用 `_adjRowEndAudited(row)`（#2 已建的现算 helper）取审定期末 → 与 `TAX_CALC_TABLE_MAP` 逐税种比对。

## Data Models

### 1. （一）申报表核对行

```ts
interface N2VatDeclarationRow {
  key: string        // 固定项 key（不可变）
  label: string      // 源模板逐字行名（不可变）
  book: number       // 账面数据 C（录入）
  declared: number   // 纳税申报表数据 D（录入）
  diff: number       // 差异 E = C − D（派生，不落库）
  reason: string     // 原因 F（录入）
}
```

### 2. （二）销项测算行

```ts
interface N2VatOutputRow {
  id: string
  variety: string        // 品种（录入，新增时 prompt）
  sales: number          // 销售额 B（录入）
  exemptSales: number    // 免税/扣除销售额 C（录入）
  taxableRevenue: number // 计税收入 D = B − C（派生）
  rate: number           // 税率 E（录入）
  outputTax: number      // 应计销项税 F = D × E（派生）
}
```

合计（源模板 R28，**无税率列合计**）：`{sales, exemptSales, taxableRevenue, outputTax}`。

### 3. （三）进项测算行与调节项

```ts
interface N2VatInputRow {
  id: string
  project: string   // 项目（录入）
  amount: number    // 购进货物/固定资产及接受劳务发生额 D（录入）
  rate: number      // 税率 E（录入）
  inputTax: number  // 测算数 F = D × E（派生）
}
interface N2VatInputAdjust {
  deductible: number   // 待抵扣进项税额期末减期初 F36
  uncertified: number  // 待认证进项税额期末减期初 F37
  retained: number     // 增值税留抵税额期末减期初 F38
}
```

### 4. 差异结论

```ts
interface N2VatVariance {
  diff: number      // 源模板公式结果
  isMatch: boolean  // |diff| <= 0.01
  formula: string   // 展示用公式文字（源模板原文，供 tooltip 溯源）
}
```

## Correctness Properties

### Property 1: 固定项清单与源模板逐字一致
（一）10 项与（四）4 项的 `label` 数组必须与源模板 R12~R21 / R42~R45 单元格文本逐字相等（含序号前缀与全角标点），数量与顺序不得变动，且不提供增删接口。

**Validates: Requirements 1.1, 1.5, 4.1, 4.2, 8.1**

### Property 2: 派生列恒等式成立且不落库
对任意录入值，`taxableRevenue == sales − exemptSales`、`outputTax == taxableRevenue × rate`、`inputTax == amount × rate`、`diff == book − declared` 恒成立；且持久化形状（`_currentRaw` 物化字段集）不含任何派生列键。

**Validates: Requirements 1.3, 2.3, 3.3, 8.2, 8.3**

### Property 3: 跨段差异公式与源模板一致
`outputVariance.diff == bookOutputTax − outputTaxTotal − pendingOutputTax`（源模板 F30），
`inputVariance.diff == inputTaxTotal − deductible − uncertified − retained − bookInputTax`（源模板 F39）；
其中 `bookOutputTax`/`bookInputTax` 必须来自（一）第 6/7 项的账面列，不得来自附加分析区。

**Validates: Requirements 2.6, 3.5, 8.2**

### Property 4: 附加分析区完全隔离
附加分析区的既有键（`N2-6-vat-rows`/`N2-6-period-mode`/`N2-6-declared-payable-vat`）读写不变；
其数值变化不影响（二）（三）任何差异结论；两区数值不一致不产生任何异常提示。

**Validates: Requirements 5.1, 5.3, 5.4**

### Property 5: N2-6 → N2-8 联动键不断裂且口径来自源模板段
`N2-6-vat-payable` 仍被写入且可被 `useN2CrossSheet.vatToSurtax` 读到；
其值等于 `calcVatPayableFromDeclaration(bookOutputTax, bookInputTax)`；（一）无数据时为 0 且不回退到附加分析区。

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 6: per-tax 交叉验证无恒零项且无双真源
`adjudicationVsCalcTables` 6 个税种在 `N2-1-adjudication-rows` 提供对应 taxType 行后均取到非 0 审定值；
源码中不再出现 `N2-1-{tax}-audited` 字面量；全仓不新增 per-tax 写入点。

**Validates: Requirements 7.1, 7.2, 7.4, 7.5, 8.4**

### Property 7: 组件解构键集是 composable 返回键集的子集
`N2TabVatCalc.vue` 对 `useN2VatSourceCalc` / `useN2VatCalc` 的解构键集必须全部存在于对应 composable 的返回对象，
防止再现「解构不存在的返回值 → 运行时 TypeError 而四层验证全绿」的缺陷。

**Validates: Requirements 8.5**

## Error Handling

| 场景 | 处理 |
|------|------|
| 录入非数字/空值 | `parseNum` 归 0（含 `Number.isFinite` 守卫，拒绝 `Infinity`/`1e400`，避免整表 NaN） |
| 税率录入百分数形态（13 vs 0.13） | UI 用 `el-select` 预置 6 档（13%/9%/6%/5%/3%/免税）并以小数存储；自定义税率经 `el-input-number` 限 0~1 |
| 新增行未输入品种/项目名 | `ElMessageBox.prompt` 取消或空名时不创建行（平台铁律：动态行需命名先行） |
| 保存失败 | `catch` 后 `ElMessage.error` 明确提示，**禁止纯 `catch {}` 静默吞**（否则数据丢了无人发现） |
| 同批次重复 item_id | 走 `saveField` 单键保存；若改用 `saveBatch` 必须按 itemId 去重（后端整批拒绝会丢全批数据） |
| （一）无数据时（二）（三）差异 | `bookOutputTax`/`bookInputTax` 为 0，差异退化为 `−合计` 形态，正常展示不报错；`isMatch` 仅在 `|diff|<=0.01` 为真 |
| 除零 | 本表无比率列，无需除零保护；若后续加税负率须复用既有 `calcVatBurdenRate` |

## Testing Strategy

分三层，全部落在 `composables/__tests__/`：

1. **纯函数层 `n2VatSourceEngine.spec.ts`** —— 覆盖 Property 2 / 3：
   - 逐公式定值断言（含负数、0、大额）
   - 跨段公式 `F30`/`F39` 用源模板语义数据算例
   - PBT（hypothesis 风格 fast-check，`max_examples` 保持低）：恒等式 `taxableRevenue + exemptSales == sales`；生成器收敛到金额域（**禁用无界 float，`fc.float({noNaN:true})` 仍会生成 ±Infinity**）

2. **契约层 `n2VatSourceContract.spec.ts`** —— 覆盖 Property 1 / 2（不落库）/ 4 / 7：
   - 固定项 `label` 数组 vs 源模板字面量逐字比对（数组字面量写死在测试内，改动必须双改）
   - 源码正则断言 `_currentRaw` 物化字段不含派生键
   - 断言附加分析区三个键在新代码中未被改写
   - 解构键集 ⊆ 返回键集（脚本化比对，防运行时崩溃复现）

3. **联动层 扩展 `n2CrossSheetContract.spec.ts`** —— 覆盖 Property 5 / 6：
   - 喂 6 个税种的 `N2-1-adjudication-rows` 行，断言 `adjudicationVsCalcTables` 6 项全部非 0（反假绿）
   - 断言源码无 `N2-1-{tax}-audited` 字面量
   - `N2-6-vat-payable` 口径断言（源模板段派生，非附加区）

**实测（Property 全覆盖后）**：Playwright/chrome-devtools 驱动 + postgres 只读比对落库，
验四段渲染、公式实时派生、差异结论、N2-6→N2-8 联动、6 项交叉验证取数；测试数据用后复原。
