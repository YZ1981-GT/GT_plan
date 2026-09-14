# Design Document: F5 营业成本专属HTML精美组件

## Overview

F5营业成本专属组件`f5-cost-of-sales`。覆盖1个xlsx源模板(183KB)/9有效sheet。科目6401营业成本（借方/损益类）。独立组件，el-tabs模式(9个tab)。

核心架构：
- componentType `f5-cost-of-sales`，主入口 GtF5CostOfSales.vue
- **el-tabs模式**：9 sheets用tabs
- 每个sheet独立子组件 + composable
- 宽表拆分：F5-2(24列→2区段Tab上半年/下半年+合计)
- 损益类公式：审定=未审+AJE+RJE；变动=本期-上期（无期初期末概念）
- F5-7成本倒轧表：结构化验证（期初+购入-期末-其他=投入+人工+制造=完工=营业成本）
- F5-6数量核对：销售量vs结转量差异分析
- EventBus联动：publish substantive:adjudicated(accountCode='6401')
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useF5ImportExport) + AI(5 section)

## Architecture

### sheetName分发模式 + el-tabs组织

```
sheetName → regex提取编码 → v-if匹配 → 子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

el-tabs 9 tabs:
├── F5A  实质性程序表 (a-program-console)
├── F5-1 审定表 (损益类：本期+上期)
├── F5-2 主营业务成本月度明细 (24列→2区段Tab)
├── F5-3 其他业务成本明细
├── F5-4 调整分录
├── F5-5 与上年度比较分析表
├── F5-6 销售数量与结转成本数量核对 (81行)
├── F5-7 成本倒轧表 (结构化逻辑验证)
└── F5-8 重大调整核查表
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtF5CostOfSales.vue                     # 主入口 sheetName v-if分发 + el-tabs
├── f5-cost-of-sales/
│   ├── F5TabAdjudication.vue               # F5-1 审定表（损益类本期+上期）
│   ├── F5TabMonthlyDetail.vue              # F5-2 月度明细(24列→2区段Tab)
│   ├── F5TabOtherCost.vue                  # F5-3 其他业务成本明细
│   ├── F5TabAdjustment.vue                 # F5-4 调整分录
│   ├── F5TabComparison.vue                 # F5-5 与上年度比较分析表
│   ├── F5TabQuantityRecon.vue              # F5-6 数量核对(81行)
│   ├── F5TabCostRollforward.vue            # F5-7 成本倒轧表(结构化)
│   └── F5TabMajorAdjustment.vue            # F5-8 重大调整核查表
├── composables/
│   ├── useF5FormulaEngine.ts               # F5公式引擎(审定/倒轧/毛利率/数量差异/波动系数)
│   ├── useF5FormData.ts                    # 数据加载/保存/selfLoad
│   ├── useF5Adjudication.ts               # F5-1审定表逻辑(损益类)
│   ├── useF5MonthlyDetail.ts              # F5-2月度明细逻辑(2区段)
│   ├── useF5OtherCost.ts                  # F5-3其他业务成本逻辑
│   ├── useF5Comparison.ts                 # F5-5比较分析逻辑
│   ├── useF5QuantityRecon.ts              # F5-6数量核对逻辑
│   ├── useF5CostRollforward.ts            # F5-7成本倒轧逻辑
│   ├── useF5MajorAdjustment.ts            # F5-8重大调整逻辑
│   ├── useF5ImportExport.ts               # 导入导出composable
│   └── useF5DualMode.ts                    # 双模式OO切换

backend/app/routers/wp_render_strategies/
├── _f5_cost_of_sales.py                    # render策略+注册RENDERER_DISPATCH
├── _f5_cost_of_sales_import_export.py      # 导入导出3端点
└── _f5_cost_of_sales_ai.py                 # AI生成5 section
```

### F5-2月度明细 2区段Tab设计（24列）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ┌───────────────────────────────┐ ┌───────────────────────────────────┐ │
│ │ 上半年(13列: 品种+1~6月+统计) │ │ 下半年+合计(11列: 7~12月+合计+对比)│ │ ← 2区段Tab
│ └───────────────────────────────┘ └───────────────────────────────────┘ │
│                                                                         │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ el-table (动态品种行，区段间行同步)                                │   │
│ │ 上半年: 品种|1月|2月|3月|4月|5月|6月|合计|占比|月均|最高月|最低月|波动 │   │
│ │ 下半年: 7月|8月|9月|10月|11月|12月|合计|全年合计|上期合计|变动额|变动率│   │
│ └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│ 底部合计：各月合计 / 上半年合计 / 下半年合计 / 全年合计 / 上期合计        │
└─────────────────────────────────────────────────────────────────────────┘
```

### F5-7成本倒轧表 结构化设计

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 蓝色渐变引导区：成本倒轧逻辑说明(4步骤)                                   │
│ ① 材料流转 → ② 成本构成 → ③ 成本结转 → ④ 营业成本                      │
├─────────────────────────────────────────────────────────────────────────┤
│ ┌── ① 材料流转区 ─────────────────────────────────────────────────────┐ │
│ │ 期初原材料(TB取数)  [___________]                                    │ │
│ │ +本期购入           [___________] ← 可编辑                           │ │
│ │ −期末原材料(TB取数)  [___________]                                    │ │
│ │ −其他发出           [___________] ← 可编辑                           │ │
│ │ ═投入生产           [═══════════] ← 公式(虚线+tooltip)              │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── ② 成本构成区 ─────────────────────────────────────────────────────┐ │
│ │ 投入生产(来自①)     [___________]                                    │ │
│ │ +直接人工           [___________] ← 可编辑                           │ │
│ │ +制造费用           [___________] ← 可编辑                           │ │
│ │ ═产品总成本          [═══════════] ← 公式                            │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── ③ 成本结转区 ─────────────────────────────────────────────────────┐ │
│ │ 期初在产品(TB取数)  [___________]                                    │ │
│ │ +产品总成本(来自②)  [___________]                                    │ │
│ │ −期末在产品(TB取数)  [___________]                                    │ │
│ │ ═完工产品成本        [═══════════] ← 公式                            │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── ④ 营业成本区 ─────────────────────────────────────────────────────┐ │
│ │ 期初产成品(TB取数)  [___________]                                    │ │
│ │ +完工产品成本(来自③) [___________]                                    │ │
│ │ −期末产成品(TB取数)  [___________]                                    │ │
│ │ −其他发出           [___________] ← 可编辑                           │ │
│ │ ═本期营业成本        [═══════════] ← 公式                            │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── 校验区 ──────────────────────────────────────────────────────────┐  │
│ │ 审定表营业成本(F5-1取) | 倒轧营业成本 | 差异 | 结论                   │  │
│ │ [显示红色/绿色] 差异>重要性水平 → 红色                                │  │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ 审计结论 textarea + AI按钮 | 编制提示 details折叠                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 数据流

```
F5-1 审定表 ── EventBus(substantive:adjudicated, accountCode='6401') ──→ trial_balance

F5-7 成本倒轧表 ←── trial_balance(1401原材料/1404在产品/1405产成品) ──── 自动取数
F5-7 成本倒轧表 ←── F5-1审定表(营业成本审定数) ──── 校验区取数

F5-6 数量核对 ←── 📎OCR(出库单扫描件) ──── 数量自动识别

F5-8 重大调整 ←── GtVoucherSamplingEngine(科目6401) ──── 抽凭引擎

useVersionTrail ── autoSnapshot on save ──→ 版本快照
```

### EventBus事件

| 事件名 | 发布者 | 消费者 |
|--------|--------|--------|
| `substantive:adjudicated` | F5-1审定表 | trial_balance + F5-7校验区 |
| `disclosure:note-text-updated` | (F5无独立附注) | — |

### 后端AI Section清单

```
cost-analysis / comparison-conclusion / quantity-reconciliation / 
rollforward-evaluation / adjustment-evaluation
```

### 与F3/F4的关键差异

1. **损益类vs负债类**：F5是借方/损益类，无"期初期末"概念，用"本期+上期"对比；F3/F4是贷方/负债类用期初期末
2. **无附注披露sheet**：F5没有独立附注披露tab（营业成本在利润表附注中披露，非单独科目附注）
3. **成本倒轧表**：F5独有的结构化验证逻辑，是核心审计工具
4. **数量核对**：F5独有的非金额维度验证（数量一致性）
5. **月度明细**：F5独有的时间序列分析（12个月波动）
6. **截止测试**：F5不适用（截止测试在F4应付做反向截止）

## Components and Interfaces

### 前端组件接口

```typescript
// GtF5CostOfSales.vue props
interface F5CostOfSalesProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// F5-1 审定表（损益类）
interface IncomeStatementAdjudication {
  mainBusinessRows: AdjudicationRow[]     // 主营业务成本品种行
  otherBusinessRows: AdjudicationRow[]    // 其他业务成本品种行
  mainSubtotal: AdjudicationRow           // 主营小计
  otherSubtotal: AdjudicationRow          // 其他小计
  grandTotal: AdjudicationRow             // 总计
  trialBalanceAmount: number
  variance: number
}

interface AdjudicationRow {
  id: string
  item: string
  // 本期
  currentUnadjusted: number
  currentAJE: number
  currentRJE: number
  currentAdjusted: number       // 公式=未审+AJE+RJE
  // 上期
  priorUnadjusted: number
  priorAJE: number
  priorRJE: number
  priorAdjusted: number         // 公式=未审+AJE+RJE
  indexRef: string
}

// F5-2 月度明细行
interface MonthlyDetailRow {
  id: string
  product: string               // 品种
  // 上半年区段
  month1: number
  month2: number
  month3: number
  month4: number
  month5: number
  month6: number
  halfYear1Total: number        // 公式=1~6月SUM
  halfYear1Ratio: number        // 占比(公式)
  halfYear1Avg: number          // 月均(公式)
  halfYear1Max: number          // 最高月
  halfYear1Min: number          // 最低月
  coeffOfVariation: number      // 波动系数(公式)
  // 下半年区段
  month7: number
  month8: number
  month9: number
  month10: number
  month11: number
  month12: number
  halfYear2Total: number        // 公式=7~12月SUM
  yearTotal: number             // 公式=上半年+下半年
  priorYearTotal: number        // 上期合计
  changeAmount: number          // 变动额(公式)
  changeRate: number            // 变动率(公式)
}

// F5-6 数量核对行
interface QuantityReconRow {
  id: string
  seq: number
  product: string
  spec: string
  unit: string
  salesQty: number              // 销售数量
  costQty: number               // 结转成本数量
  qtyVariance: number           // 数量差异(公式)
  varianceRate: number          // 差异率(公式)
  varianceReason: string        // 差异原因分类(下拉)
  openingInventory: number      // 期初库存
  currentProduction: number     // 本期产量
  currentPurchase: number       // 本期采购
  availableForSale: number      // 可供销售量(公式)
  closingInventory: number      // 期末库存
  theoreticalCostQty: number    // 理论结转量(公式)
  theoreticalVariance: number   // 理论差异(公式)
}

// F5-7 成本倒轧表数据
interface CostRollforwardData {
  // 材料流转区
  openingMaterial: number       // 期初原材料(TB)
  purchase: number              // 本期购入(编辑)
  closingMaterial: number       // 期末原材料(TB)
  otherIssue1: number           // 其他发出(编辑)
  materialInput: number         // =投入生产(公式)
  // 成本构成区
  directLabor: number           // 直接人工(编辑)
  overhead: number              // 制造费用(编辑)
  totalProductionCost: number   // =产品总成本(公式)
  // 成本结转区
  openingWIP: number            // 期初在产品(TB)
  closingWIP: number            // 期末在产品(TB)
  finishedGoodsCost: number     // =完工产品成本(公式)
  // 营业成本区
  openingFG: number             // 期初产成品(TB)
  closingFG: number             // 期末产成品(TB)
  otherIssue2: number           // 其他发出(编辑)
  cogs: number                  // =本期营业成本(公式)
  // 校验区
  adjudicatedCOGS: number       // 审定表营业成本(F5-1取)
  rollforwardVariance: number   // =差异(公式)
  conclusion: string            // 结论
}

// F5-5 比较分析行
interface ComparisonRow {
  id: string
  product: string
  currentRevenue: number
  currentCost: number
  currentGrossProfit: number    // 公式
  currentGrossMargin: number    // 公式
  priorRevenue: number
  priorCost: number
  priorGrossProfit: number      // 公式
  priorGrossMargin: number      // 公式
  revenueChange: number         // 公式
  revenueChangeRate: number     // 公式
  costChange: number            // 公式
  costChangeRate: number        // 公式
  marginChange: number          // 毛利率变动(公式)
  changeReason: string
  auditEvaluation: string
  remark: string
}
```

### 后端接口

```python
# _f5_cost_of_sales.py
def render_f5_cost_of_sales(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='f5-cost-of-sales'和sheets配置"""

# _f5_cost_of_sales_import_export.py
POST /api/workpapers/{wp_id}/f5/export-template?sheet={code}
POST /api/workpapers/{wp_id}/f5/export-data?sheet={code}
POST /api/workpapers/{wp_id}/f5/import-data?sheet={code}  # multipart/form-data

# _f5_cost_of_sales_ai.py
POST /api/workpapers/{wp_id}/f5/ai/{section}
# section: cost-analysis/comparison-conclusion/quantity-reconciliation/
#          rollforward-evaluation/adjustment-evaluation
```

## Data Models

### F5-3 其他业务成本行

```typescript
interface OtherCostRow {
  id: string
  seq: number
  costItem: string
  currentAmount: number
  priorAmount: number
  changeAmount: number          // 公式
  changeRate: number            // 公式
  proportion: number            // 占比(公式)
  correspondingRevenue: number
  costRate: number              // 公式
  revenueRecognitionTiming: string
  costRecognitionTiming: string
  matchingReasonability: string
  auditEvaluation: string
  remark: string
}
```

### F5-8 重大调整行

```typescript
interface MajorAdjustmentRow {
  id: string
  seq: number
  adjustmentDate: string
  adjustmentItem: string
  adjustmentAmount: number
  adjustmentReason: string
  approvalBasis: string
  voucherNo: string
  auditEvaluation: string
}
```

## Error Handling

1. **selfLoad失败**：render-config返回404/500时显示错误卡片+重试按钮
2. **公式计算异常**：parseNum兜底（NaN/Infinity→0），除零保护（收入=0时毛利率显示'N/A'）
3. **成本倒轧TB取数失败**：显示"未获取到{科目名}余额"提示，允许手工填写
4. **F5-7校验区F5-1未完成**：审定表营业成本为0时显示"请先完成F5-1审定表"
5. **月度数据全零**：波动系数=0（非NaN），不触发高亮
6. **数量核对销售量为0**：差异率显示'N/A'而非Infinity
7. **区段Tab切换**：切换时保持行选中状态
8. **导入格式错误**：后端返回详细错误列表
9. **品种行动态增删**：新增品种需ElMessageBox.prompt输入品种名称确认

## Testing Strategy

### 前端PBT测试

| 测试文件 | 覆盖Property | 框架 |
|----------|-------------|------|
| useF5FormulaEngine.pbt.spec.ts | P1~P10 | vitest + fast-check |

### 后端测试

| 测试文件 | 覆盖范围 |
|----------|----------|
| test_f5_cost_of_sales_pbt.py | 成本倒轧/毛利率/数量差异 |
| test_f5_cost_of_sales.py | render策略+注册契约 |

### 集成测试

- sheetName分发正确性（9个sheet→对应组件）
- 损益类审定公式链（未审+AJE+RJE=审定，本期/上期独立计算）
- F5-7成本倒轧全链路（材料→成本构成→结转→营业成本→校验）
- F5-6数量核对（销售量vs结转量+理论结转量）
- F5-2两区段Tab行同步+月度合计校验
- F5-5毛利率计算+变动高亮
- EventBus(substantive:adjudicated)传递
- F5-7从TB自动取数（1401/1404/1405）
- 导入导出round-trip

## Correctness Properties

### Property 1: 损益类审定公式
∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
**Validates: Requirements 11.1, 3.3**

### Property 2: 成本倒轧恒等
∀ opening, purchase, closing, other ∈ ℝ≥0: calcCostRollforward(opening, purchase, closing, other) === opening + purchase - closing - other
**Validates: Requirements 11.5, 9.2**

### Property 3: 毛利率公式
∀ revenue ∈ ℝ>0, cost ∈ ℝ≥0: calcGrossMargin(revenue, cost) === (revenue-cost)/revenue × 100
**Validates: Requirements 11.4, 7.3**

### Property 4: 完工成本恒等
∀ wipOpening, totalCost, wipClosing ∈ ℝ≥0: calcFinishedGoodsCost(wipOpening, totalCost, wipClosing) === wipOpening + totalCost - wipClosing
**Validates: Requirements 11.7, 9.4**

### Property 5: 营业成本倒轧全链非负合理性
∀ fgOpening, finishedCost, fgClosing, other ∈ ℝ≥0 WHERE fgOpening+finishedCost ≥ fgClosing+other: calcCOGS(fgOpening, finishedCost, fgClosing, other) ≥ 0
**Validates: Requirements 11.8, 9.5**

### Property 6: 数量差异公式
∀ salesQty, costQty ∈ ℝ: calcQuantityVariance(salesQty, costQty) === salesQty - costQty
**Validates: Requirements 11.9, 8.2**

### Property 7: 变动率公式
∀ current, prior ∈ ℝ, prior≠0: calcChangeRate(current, prior) === (current-prior)/prior × 100
**Validates: Requirements 11.3, 7.4**

### Property 8: 波动系数非负
∀ values[] ∈ ℝ[] (length≥2, all≥0, mean>0): calcCoeffOfVariation(values) ≥ 0
**Validates: Requirements 11.11, 4.7**

### Property 9: 月度合计恒等
∀ months[12] ∈ ℝ: SUM(months[0..5]) + SUM(months[6..11]) === SUM(months[0..11])
**Validates: Requirements 4.2, 4.3, 4.4**

### Property 10: 借贷平衡恒等
∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
**Validates: Requirements 11.12, 6.2**
