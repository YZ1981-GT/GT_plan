# Design Document: F2 计价测试 + 跌价准备测试 + 关联交易专属HTML精美组件

## Overview

F2存货底稿Group 2专属组件`f2-inventory-valuation`。覆盖3个xlsx源模板/13有效sheet（计价方法测试F2-38~F2-40 + 生产成本分析F2-41~F2-44 + 跌价准备NRV测试F2-47~F2-49 + 关联交易F2-52）。独立组件但与`f2-inventory-main`共享公式引擎基础函数(useF2FormulaEngine)并扩展NRV/计价/差异公式。

核心架构：
- componentType `f2-inventory-valuation`，主入口 GtF2InventoryValuation.vue
- **el-tabs模式**：13 sheets适合用tabs，分4个tab-group
- 每个sheet独立子组件 + 独立/共享composable
- 3张计价测试共用通用组件F2ValuationTestSheet.vue（抽样参数区+动态行检查表）
- 扩展公式引擎useF2ValuationFormulaEngine.ts（NRV/跌价/差异/分配/公允性12函数）
- 跨组件数据流：F2-41~F2-43→F2-44成本分配（allResponses computed）
- EventBus联动：impairment:calculated → f2-inventory-main的F2-1跌价区
- 宽表拆分：F2-47(28列)→3区段Tab / F2-49(24列)→2区段Tab
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useF2ValuationImportExport) + AI(6 section)

## Architecture

### sheetName分发模式 + el-tabs组织

GtF2InventoryValuation.vue 接收 `sheetName` prop（完整中文名如"计价方法测试表-平均F2-38"），用正则提取末尾编码(F2-38/F2-47等)，`v-if` 分发到对应子组件。外层采用el-tabs展示4个tab-group目录。

```
sheetName → regex提取编码 → v-if匹配 → 子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

el-tabs 4 groups:
├── 计价方法测试: F2-38 / F2-39 / F2-40
├── 生产成本分析: F2-41 / F2-42 / F2-43 / F2-44
├── 跌价准备:     F2-47 / F2-48 / F2-49
└── 关联交易:     F2-52
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtF2InventoryValuation.vue              # 主入口 sheetName v-if分发 + el-tabs 4 group
├── f2-valuation/
│   ├── valuation-test/
│   │   ├── F2ValuationTestSheet.vue        # 通用计价测试组件(config驱动F2-38/39/40)
│   │   ├── F2TabValuationAvg.vue           # F2-38 加权平均法测试（用通用组件+avg config）
│   │   ├── F2TabValuationFIFO.vue          # F2-39 先进先出法测试（用通用组件+FIFO config）
│   │   └── F2TabValuationStdCost.vue       # F2-40 标准成本差异测试（用通用组件+std config）
│   ├── production-cost/
│   │   ├── F2TabProductionCost.vue         # F2-41 生产成本明细表
│   │   ├── F2TabDirectLabor.vue            # F2-42 直接人工分析表
│   │   ├── F2TabManufacturingOverhead.vue  # F2-43 制造费用明细表
│   │   └── F2TabCostAllocation.vue         # F2-44 生产成本分配
│   ├── impairment/
│   │   ├── F2TabImpairmentTest.vue         # F2-47 跌价准备测试表(28列→3区段Tab)
│   │   ├── F2TabObsoleteInventory.vue      # F2-48 长库龄呆滞超保质期
│   │   └── F2TabImpairmentReversal.vue     # F2-49 跌价转回(24列→2区段Tab)
│   └── related-party/
│       └── F2TabRelatedPurchase.vue        # F2-52 关联采购分析表
├── composables/
│   ├── useF2ValuationFormulaEngine.ts      # 扩展公式引擎12函数(NRV/跌价/差异/分配/公允)（~200行）
│   ├── useF2ValuationFormData.ts           # 数据加载/保存/selfLoad（~180行）
│   ├── useF2ValuationTest.ts               # F2-38~40 通用计价测试逻辑（~250行）
│   ├── useF2ProductionCost.ts              # F2-41~44 生产成本组逻辑（~300行）
│   ├── useF2ImpairmentTest.ts              # F2-47 跌价NRV测试逻辑（~350行）
│   ├── useF2ObsoleteInventory.ts           # F2-48 呆滞存货逻辑（~120行）
│   ├── useF2ImpairmentReversal.ts          # F2-49 跌价转回逻辑（~200行）
│   ├── useF2RelatedPurchase.ts             # F2-52 关联采购逻辑（~180行）
│   ├── useF2ValuationImportExport.ts       # 导入导出composable（~150行）
│   └── useF2ValuationDualMode.ts           # 双模式OO切换（~80行）

backend/app/routers/wp_render_strategies/
├── _f2_valuation.py                        # render策略+注册RENDERER_DISPATCH
├── _f2_valuation_import_export.py          # 导入导出3端点
└── _f2_valuation_ai.py                     # AI生成6 section
```

### 通用组件设计

**F2ValuationTestSheet.vue** — 3张计价测试通用组件

通过`config`prop传入差异配置：加权平均/先进先出/标准成本差异的列定义和公式差异。共享核心逻辑：
- 抽样参数区（6字段横排固定区域）
- 动态行检查表（凭证核对模式）
- 公式自动计算 + 差异高亮
- 合计行 + 超差异统计
- 导入导出

```typescript
interface ValuationTestConfig {
  sheetCode: string                // 'F2-38' | 'F2-39' | 'F2-40'
  method: 'weighted-avg' | 'fifo' | 'standard-cost'
  columns: ColumnDef[]             // 差异列定义
  formulaType: string              // 公式类型标识
  thresholdRate: number            // 差异率阈值(1%/1%/5%)
}
```

### F2-47跌价准备测试 3区段Tab设计

F2-47是本组件最复杂的sheet（28列），拆为3区段Tab：

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 抽样参数区（固定顶部，6字段横排）                                          │
│ [总体金额] [样本量] [抽样方法▾] [置信水平] [重要性水平] [跌价余额]          │
├─────────────────────────────────────────────────────────────────────────┤
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                     │
│ │ 基础信息(10列)│ │ NRV测算(10列) │ │ 跌价结论(8列) │  ← 3区段Tab       │
│ └──────────────┘ └──────────────┘ └──────────────┘                     │
│                                                                         │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ el-table (动态行)                                                 │   │
│ │ 序号|类别|品名|规格|数量|单位成本|账面成本|库龄|存放地点|状态       │   │ ← 基础信息区段
│ │ ──────────────────────────────────────────────────────────────── │   │
│ │ 估计售价|至完工成本|销售费用|销售税金|NRV|单位NRV|差额|应计提|结论 │   │ ← NRV测算区段
│ │ ──────────────────────────────────────────────────────────────── │   │
│ │ 已计提|应补提|应转回|调整后|与企业差异|差异原因|审计建议|索引      │   │ ← 跌价结论区段
│ └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│ ┌─────────────────────────────────────────────────────┐                │
│ │ 底部汇总：合计账面|合计NRV|合计应计提|合计已计提|净差异│                │
│ │ 测试结论 textarea + AI按钮                           │                │
│ └─────────────────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────────────┘
```

### F2-49跌价转回 2区段Tab设计

```
┌──────────────────────────────────────────────────────────────┐
│ ┌─────────────────────┐ ┌─────────────────────────┐         │
│ │ 上期跌价情况(12列)   │ │ 本期NRV+转回判定(12列)  │ ← 2区段Tab │
│ └─────────────────────┘ └─────────────────────────┘         │
│                                                              │
│ el-table (动态行，行同步)                                     │
│                                                              │
│ 底部汇总：转回笔数/转回总额/超限笔数                          │
│ 审计说明 textarea + AI按钮                                    │
└──────────────────────────────────────────────────────────────┘
```

### 数据流

```
F2-41 生产成本明细 ──────┐
F2-42 直接人工分析 ──────┼── allResponses computed ──→ F2-44 成本分配（自动取总额）
F2-43 制造费用明细 ──────┘

F2-47 跌价NRV测试 ── EventBus(impairment:calculated) ──→ f2-inventory-main F2-1跌价区

F2-38~F2-40 计价测试 ── EventBus(valuation:tested) ──→ F2A程序表自动完成标记
```

### EventBus事件

| 事件名 | 发布者 | 消费者 |
|--------|--------|--------|
| `impairment:calculated` | F2-47 | f2-inventory-main → F2-1审定表跌价区 |
| `valuation:tested` | F2-38/39/40 | F2A程序表自动完成 |
| `cost:analyzed` | F2-41/42/43 | F2-44成本分配取数 |

### 后端AI Section清单

```
valuation-conclusion / impairment-evaluation / reversal-evaluation / 
fairness-evaluation / cost-analysis / labor-analysis
```

### 与f2-inventory-main的关键差异

1. **el-tabs模式**：f2-inventory-main无内部tabs(35 sheet用v-if) → f2-inventory-valuation用el-tabs(13 sheet适合tabs分4 group)
2. **宽表拆分**：f2-inventory-main明细表5区段(期初/增加/减少/期末/库龄) → f2-inventory-valuation F2-47拆3区段(基础/NRV/结论)、F2-49拆2区段(上期/本期)
3. **公式引擎关系**：f2-inventory-valuation 复用 useF2FormulaEngine 的 parseNum/calcSubtotal/calcChangeRate 等基础函数 + 扩展12个NRV/差异/分配函数
4. **通用组件**：f2-inventory-main有2通用(明细表+截止) → f2-inventory-valuation有1通用(计价测试3张)
5. **EventBus方向**：f2-inventory-valuation向f2-inventory-main发布事件(impairment:calculated)，f2-inventory-main消费

## Components and Interfaces

### 前端组件接口

```typescript
// GtF2InventoryValuation.vue props
interface F2InventoryValuationProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// F2ValuationTestSheet.vue props
interface F2ValuationTestSheetProps {
  config: ValuationTestConfig
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  readonly?: boolean
}

// ValuationTestConfig
interface ValuationTestConfig {
  sheetCode: string
  method: 'weighted-avg' | 'fifo' | 'standard-cost'
  columns: ColumnDef[]
  formulaType: string
  thresholdRate: number       // 差异率阈值百分比
}

// 抽样参数区
interface SamplingParameters {
  populationAmount: number    // 总体金额
  sampleSize: number          // 样本量
  samplingMethod: string      // 抽样方法
  confidenceLevel: number     // 置信水平
  tolerableError: number      // 可接受误差
  materialityLevel: number    // 重要性水平
}

// F2-47 跌价测试行
interface ImpairmentTestRow {
  id: string
  seq: number
  // 基础信息区段
  category: string            // 存货类别
  itemName: string            // 品名
  spec: string                // 规格
  qty: number                 // 数量
  unitCost: number            // 单位成本
  bookCost: number            // 账面成本(公式=数量×单位成本)
  agingDays: number           // 库龄
  location: string            // 存放地点
  status: 'normal' | 'obsolete' | 'scrapped'  // 状态
  // NRV测算区段
  estimatedPrice: number      // 估计售价
  completionCost: number      // 至完工估计成本
  sellingExpense: number      // 估计销售费用
  sellingTax: number          // 估计销售税金
  nrv: number                 // 可变现净值(公式)
  unitNrv: number             // 单位NRV(公式)
  nrvDiff: number             // NRV-账面差(公式)
  requiredProvision: number   // 应计提跌价(公式)
  testConclusion: string      // 测试结论(下拉)
  nrvRemark: string           // 备注
  // 跌价结论区段
  existingProvision: number   // 已计提跌价
  additionalProvision: number // 本期应补提(公式)
  reversalAmount: number      // 本期应转回(公式)
  adjustedProvision: number   // 调整后跌价
  companyDiff: number         // 与企业差异(公式)
  diffReason: string          // 差异原因
  auditSuggestion: string     // 审计建议
  indexRef: string            // 索引
}

// F2-49 跌价转回行
interface ImpairmentReversalRow {
  id: string
  seq: number
  itemName: string
  spec: string
  // 上期跌价情况区段
  priorBookCost: number       // 上期账面成本
  priorNRV: number            // 上期NRV
  priorRequired: number       // 上期应计提
  priorProvision: number      // 上期已计提
  priorAdequacy: string       // 上期跌价充足性
  provisionDate: string       // 计提日期
  provisionReason: string     // 计提原因
  cumulativeProvision: number // 累计计提
  priorRemark: string         // 备注
  // 本期NRV+转回判定区段
  currentBookCost: number     // 本期账面成本
  currentPrice: number        // 本期估计售价
  currentCompletionCost: number  // 本期至完工成本
  currentSellingExpense: number  // 本期销售费用
  currentNRV: number          // 本期NRV(公式)
  currentRequired: number     // 本期应计提(公式)
  shouldReverse: string       // 是否应转回(公式)
  reversalAmount: number      // 转回金额(公式)
  reversalCap: number         // 转回上限(公式=累计计提)
  actualReversal: number      // 实际转回
  reversalReasonability: string  // 转回合理性(下拉)
  auditEvaluation: string     // 审计评价
}

// F2-52 关联采购行
interface RelatedPurchaseRow {
  id: string
  seq: number
  partyName: string           // 关联方名称
  relationship: string        // 关联关系
  itemName: string            // 采购品名
  qty: number                 // 采购数量
  unitPrice: number           // 采购单价
  amount: number              // 采购金额(公式)
  proportion: number          // 占总采购比例(公式)
  pricingMethod: string       // 定价方式(下拉)
  comparablePrice: number     // 可比市场价格
  deviationRate: number       // 差异率(公式)
  nonRelatedPrice: number     // 同类非关联方价格
  nonRelatedDeviation: number // 非关联差异率(公式)
  fairnessConclusion: string  // 公允性结论(下拉)
  auditEvaluation: string     // 审计评价
  indexRef: string            // 索引
  remark: string              // 备注
}

// ColumnDef (复用f2-inventory-main定义)
interface ColumnDef {
  key: string
  label: string
  width?: number
  type: 'number' | 'text' | 'select' | 'date' | 'index' | 'formula'
  formula?: string
  editable?: boolean
  options?: string[]
}
```

### 后端接口

```python
# _f2_valuation.py
def render_f2_valuation(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='f2-inventory-valuation'和sheets配置"""

# _f2_valuation_import_export.py
POST /api/workpapers/{wp_id}/f2-valuation/export-template?sheet={code}
POST /api/workpapers/{wp_id}/f2-valuation/export-data?sheet={code}
POST /api/workpapers/{wp_id}/f2-valuation/import-data?sheet={code}  # multipart/form-data

# _f2_valuation_ai.py
POST /api/workpapers/F2-valuation/ai/{section}
# section: valuation-conclusion/impairment-evaluation/reversal-evaluation/
#          fairness-evaluation/cost-analysis/labor-analysis
```

## Data Models

### 计价测试数据模型（通用）

```typescript
interface ValuationTestRow {
  id: string
  seq: number
  itemName: string            // 品名
  // 加权平均法专用字段
  openingQty?: number
  openingAmount?: number
  purchaseQty?: number
  purchaseAmount?: number
  weightedAvgPrice?: number   // 公式
  issueQty?: number
  auditIssueAmount?: number   // 公式
  companyIssueAmount?: number
  // 先进先出法专用字段
  batchNo?: string
  inDate?: string
  inQty?: number
  inPrice?: number
  inAmount?: number
  fifoPrice?: number          // FIFO序应发单价
  auditFifoAmount?: number    // 公式
  companyFifoAmount?: number
  // 标准成本差异专用字段
  stdPrice?: number
  stdQty?: number
  stdCost?: number            // 公式
  actPrice?: number
  actQty?: number
  actCost?: number            // 公式
  priceVariance?: number      // 公式
  qtyVariance?: number        // 公式
  totalVariance?: number      // 公式
  allocationMethod?: string
  allocationRatio?: number
  // 通用字段
  varianceAmount?: number     // 差异额(公式)
  varianceRate?: number       // 差异率(公式)
  voucherNo?: string          // 凭证编号
  checkResult?: string        // 核对结果
  remark?: string
}
```

### 生产成本数据模型

```typescript
interface ProductionCostRow {
  id: string
  productName: string
  directMaterial: PeriodData   // 直接材料
  directLabor: PeriodData      // 直接人工
  overhead: PeriodData         // 制造费用
  total: PeriodData            // 合计(公式)
  remark?: string
}

interface PeriodData {
  opening: number              // 期初
  currentInput: number         // 本期投入
  completedTransfer: number    // 完工转出
  ending: number               // 期末(公式=期初+投入-转出)
}

interface DirectLaborRow {
  id: string
  department: string           // 部门/产品
  jobType: string              // 工种
  headcount: number            // 人数
  workHours: number            // 出勤工时
  hourlyRate: number           // 工资率
  calculatedLabor: number      // 计算人工费(公式)
  actualLabor: number          // 实际人工费
  variance: number             // 差异(公式)
  varianceRate: number         // 差异率(公式)
  overtimeHours: number        // 加班工时
  overtimeRate: number         // 加班费率
  overtimePay: number          // 加班费
  socialInsurance: number      // 社保
  housingFund: number          // 公积金
  totalLabor: number           // 合计(公式)
  proportion: number           // 占比(公式)
  remark?: string
}

interface OverheadRow {
  id: string
  expenseItem: string          // 费用项目
  currentAmount: number        // 本期发生额
  priorAmount: number          // 上期发生额
  changeAmount: number         // 变动额(公式)
  changeRate: number           // 变动率(公式)
  budgetAmount: number         // 预算数
  budgetVariance: number       // 预算差异(公式)
  budgetVarianceRate: number   // 预算差异率(公式)
  allocationBasis: string      // 分配基准
  allocationRate: number       // 分配率
  productA: number             // 产品A分配额
  productB: number             // 产品B分配额
  productC: number             // 产品C分配额
  allocationTotal: number      // 分配合计(公式)
  isReasonable: string         // 是否合理
  remark?: string
}

interface CostAllocationRow {
  id: string
  productName: string
  allocationBasis: string      // 分配基准
  basisQty: number             // 基准数量
  basisRatio: number           // 基准占比(公式)
  materialAlloc: number        // 直接材料分配(公式)
  laborAlloc: number           // 直接人工分配(公式)
  overheadAlloc: number        // 制造费用分配(公式)
  totalAlloc: number           // 合计分配(公式)
  companyAlloc: number         // 企业分配额
  variance: number             // 差异(公式)
  varianceRate: number         // 差异率(公式)
  evaluation: string           // 审计评价
  methodChanged: string        // 分配方法变更
  changeNote: string           // 变更说明
  remark?: string
}
```

## Error Handling

1. **selfLoad失败**：render-config返回404/500时显示错误卡片+重试按钮
2. **公式计算异常**：parseNum兜底（NaN/Infinity→0），除零保护
3. **NRV计算负值**：NRV<0时显示0（不存在负的可变现净值），应计提=全额账面成本
4. **跨组件EventBus传递失败**：impairment:calculated发布后5秒无消费确认→toast提示手动检查F2-1
5. **导入格式错误**：后端返回详细错误列表（行号/字段/原因）
6. **区段Tab切换**：切换时保持行选中状态，不丢失编辑数据
7. **AI生成超时**：30秒超时→取消请求+提示"生成超时，请重试"
8. **虚拟滚动边界**：行数0不启用；F2-38计价测试94行启用虚拟滚动
9. **转回上限校验**：转回金额>累计计提时自动截断+红色警告

## Testing Strategy

### 前端PBT测试

| 测试文件 | 覆盖Property | 框架 |
|----------|-------------|------|
| useF2ValuationFormulaEngine.pbt.spec.ts | P1~P3, P7~P10 | vitest + fast-check |
| useF2ValuationVariance.pbt.spec.ts | P4, P6 | vitest + fast-check |
| useF2ImpairmentReversal.pbt.spec.ts | P5, P8 | vitest + fast-check |

### 后端测试

| 测试文件 | 覆盖范围 |
|----------|----------|
| test_f2_valuation_import_export_pbt.py | 导入导出round-trip正确性 |
| test_f2_valuation.py | render策略+注册契约 |

### 集成测试

- sheetName分发正确性（13个编码→对应组件）
- NRV公式链（售价→扣减→NRV→跌价→EventBus→F2-1）
- 计价差异计算全链路（3种计价方法）
- 成本分配取数链（F2-41/42/43→F2-44）
- 宽表区段Tab切换（F2-47三区段/F2-49两区段）
- 导入导出round-trip

## Correctness Properties

### Property 1: NRV公式
∀ price, completionCost, sellingExpense, tax ∈ ℝ≥0: calcNRV(price, completionCost, sellingExpense, tax) === price - completionCost - sellingExpense - tax
**Validates: Requirements 13.1, 9.5**

### Property 2: 跌价计提公式
∀ bookCost, nrv ∈ ℝ≥0: calcImpairmentProvision(bookCost, nrv) === Math.max(0, bookCost - nrv)
**Validates: Requirements 13.2, 9.6**

### Property 3: 加权平均单价
∀ openAmt, inAmt ∈ ℝ, openQty, inQty ∈ ℝ>0: calcWeightedAvgPrice(openAmt, inAmt, openQty, inQty) === (openAmt+inAmt)/(openQty+inQty)
**Validates: Requirements 13.3, 2.4**

### Property 4: 标准成本差异恒等
∀ stdPrice, stdQty, actPrice, actQty ∈ ℝ: calcPriceVariance(actPrice, stdPrice, actQty) + calcQuantityVariance(actQty, stdQty, stdPrice) === calcTotalVariance(actPrice, actQty, stdPrice, stdQty)
**Validates: Requirements 13.5, 13.6, 13.7, 4.5, 4.6, 4.7**

### Property 5: 跌价转回金额约束
∀ provision, required, cap ∈ ℝ≥0: 0 ≤ calcReversalAmount(provision, required, cap) ≤ cap
**Validates: Requirements 13.8, 11.5, 11.6**

### Property 6: 分配比例合计=100%
∀ quantities: number[] (all>0): |SUM(quantities.map(q => calcAllocationRatio(q, SUM(quantities)))) - 100| < 1e-10
**Validates: Requirements 13.9, 8.2**

### Property 7: 公允性差异率公式
∀ relatedPrice ∈ ℝ, comparablePrice ∈ ℝ\{0}: calcFairnessDeviation(relatedPrice, comparablePrice) === (relatedPrice-comparablePrice)/comparablePrice×100
**Validates: Requirements 13.10, 12.4**

### Property 8: 超保质期判定幂等
∀ ageDays, shelfDays ∈ ℤ≥0: isExpired(ageDays, shelfDays) 结果确定且幂等（同输入多次调用同结果）
**Validates: Requirements 13.11, 10.2**

### Property 9: NRV≥0时无需计提
∀ bookCost, nrv ∈ ℝ≥0 WHERE nrv ≥ bookCost: calcImpairmentProvision(bookCost, nrv) === 0
**Validates: Requirements 13.2, 9.6**

### Property 10: 计价差异可加性
∀ actPrice, actQty, stdPrice, stdQty ∈ ℝ: calcTotalVariance(actPrice, actQty, stdPrice, stdQty) === calcPriceVariance(actPrice, stdPrice, actQty) + calcQuantityVariance(actQty, stdQty, stdPrice)
**Validates: Requirements 13.5, 13.6, 13.7**
