# Design Document: G1 交易性金融资产专属HTML精美组件

## Overview

G1交易性金融资产专属组件`g1-trading-financial-assets`。覆盖1个xlsx源模板(153KB)/16有效sheet。科目1501交易性金融资产（借方/资产类）。**最复杂的投资科目底稿**。sheetName v-if dispatch模式（16 sheets > 12 threshold）。

核心架构：
- componentType `g1-trading-financial-assets`，主入口 GtG1TradingFinancialAssets.vue
- **sheetName v-if dispatch模式**：16 sheets用v-if分发（不用el-tabs）
- 子目录分组：core/ + valuation/ + classification/ + inspection/
- 宽表拆分：G1-2(35列→5区段Tab) / G1-9(21列→2区段) / G1-5(18列→2区段) / G1-4(21列→2区段) / G1-12(18列→2区段)
- 借方科目公式：期末未审 = 期初审定 + 借方 - 贷方
- EventBus联动：publish substantive:adjudicated(accountCode='1501')
- 特色：公允价值Level1-3测试(Level条件启用列) + SPPI分析 + 业务模式分类 + 证券监盘+倒轧 + 衍生工具核查
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useG1ImportExport, 10张表) + AI(8 section)

## Architecture

### sheetName分发模式 + 子目录组织

GtG1TradingFinancialAssets.vue 接收 `sheetName` prop，用正则提取编码(G1A/G1-1~G1-14/附注)，`v-if` 分发到对应子组件。

```
sheetName → regex提取编码 → v-if匹配 → 子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

16 sheets 子目录分组:
├── core/
│   ├── G1-1  审定表（98行多层结构）
│   ├── G1-2  明细表（35列→5区段Tab）
│   ├── G1-3  调整分录
│   ├── 附注披露(上市)（198行超长）
│   └── 附注披露(国企)
├── valuation/
│   ├── G1-6  公允价值测试表（Level1-3条件启用）
│   └── G1-7  第三层次调节表
├── classification/
│   ├── G1-8  业务模式分析（叙述式）
│   ├── G1-9  分类适当性检查（21列→2区段）
│   └── G1-10 合同现金流量特征（80行叙述式）
└── inspection/
    ├── G1-4  结存表（21列→2区段）
    ├── G1-5  收益测算表（18列→2区段）
    ├── G1-11 有价证券监盘表
    ├── G1-12 盘点倒轧表（18列→2区段）
    ├── G1-13 检查表（抽凭引擎集成）
    └── G1-14 衍生金融工具核查表
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtG1TradingFinancialAssets.vue              # 主入口 sheetName v-if分发
├── g1-trading-financial-assets/
│   ├── core/
│   │   ├── G1TabAdjudication.vue               # G1-1 审定表（多层结构）
│   │   ├── G1TabDetail.vue                     # G1-2 明细表(35列→5区段Tab)
│   │   ├── G1TabAdjustment.vue                 # G1-3 调整分录
│   │   ├── G1TabDisclosureListed.vue           # 附注披露(上市)(198行)
│   │   └── G1TabDisclosureSOE.vue              # 附注披露(国企)
│   ├── valuation/
│   │   ├── G1TabFairValueTest.vue              # G1-6 公允价值测试(Level1-3)
│   │   └── G1TabLevel3Reconciliation.vue       # G1-7 第三层次调节表
│   ├── classification/
│   │   ├── G1TabBusinessModel.vue              # G1-8 业务模式分析
│   │   ├── G1TabClassification.vue             # G1-9 分类适当性(21列→2区段)
│   │   └── G1TabSPPI.vue                       # G1-10 合同现金流量特征
│   └── inspection/
│       ├── G1TabInventory.vue                  # G1-4 结存表(21列→2区段)
│       ├── G1TabIncomeCalc.vue                 # G1-5 收益测算(18列→2区段)
│       ├── G1TabSecuritiesCount.vue            # G1-11 有价证券监盘表
│       ├── G1TabCountReconciliation.vue        # G1-12 盘点倒轧(18列→2区段)
│       ├── G1TabVoucherCheck.vue               # G1-13 检查表(抽凭引擎)
│       └── G1TabDerivativeCheck.vue            # G1-14 衍生金融工具核查表
├── composables/
│   ├── useG1FormulaEngine.ts                   # G1公式引擎(12个纯函数)
│   ├── useG1FormData.ts                        # 数据加载/保存/selfLoad
│   ├── useG1Adjudication.ts                    # G1-1审定表逻辑(多层结构)
│   ├── useG1Detail.ts                          # G1-2明细表逻辑(5区段)
│   ├── useG1Inventory.ts                       # G1-4结存表逻辑
│   ├── useG1IncomeCalc.ts                      # G1-5收益测算逻辑
│   ├── useG1FairValueTest.ts                   # G1-6公允价值测试逻辑(Level条件)
│   ├── useG1Level3.ts                          # G1-7第三层次调节逻辑
│   ├── useG1Classification.ts                  # G1-9分类适当性逻辑(2区段)
│   ├── useG1SecuritiesCount.ts                 # G1-11监盘逻辑
│   ├── useG1CountReconciliation.ts             # G1-12盘点倒轧逻辑
│   ├── useG1VoucherCheck.ts                    # G1-13检查表逻辑(抽凭)
│   ├── useG1DerivativeCheck.ts                 # G1-14衍生工具逻辑
│   ├── useG1ImportExport.ts                    # 导入导出composable(10张表)
│   └── useG1DualMode.ts                        # 双模式OO切换

backend/app/routers/wp_render_strategies/
├── _g1_trading_financial_assets.py             # render策略+注册RENDERER_DISPATCH
├── _g1_trading_financial_assets_import_export.py  # 导入导出3端点(10张表)
└── _g1_trading_financial_assets_ai.py          # AI生成8 section
```

### G1-2明细表 5区段Tab设计（35列）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│ │基础信息7列│ │持有明细7列│ │公允价值7列│ │ 损益7列  │ │审定调整7列│ Tab │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘     │
│                                                                         │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ el-table (动态行，区段间行同步)                                    │   │
│ │ 基础信息: 序号|品种|代码|类型|市场|取得日|初始成本                  │   │
│ │ 持有明细: 期初数量|买入|卖出|期末数量|期初成本|增加成本|减少成本     │   │
│ │ 公允价值: 单位公允|期末公允|来源Level|期初公允|变动|累计变动|报价日   │   │
│ │ 损益:     处置收入|处置成本|已实现损益|利息股利|收益合计|变动损益|备注 │   │
│ │ 审定调整: 期末成本|未审|AJE|RJE|审定|差异|索引                      │   │
│ └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│ 底部合计：按投资类型分类小计 + 总计                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### G1-6 公允价值测试表设计（Level条件启用）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 证券名称 | 代码 | 持仓数量 | 期末账面值 | Level层级[下拉1/2/3]          │
├─────────────────────────────────────────────────────────────────────────┤
│ ┌── Level 1 (市场报价) ──────── 当Level=1时启用 ────────────────────┐ │
│ │ 报价日期 | 报价来源 | 报价值 | 计算市值(公式) | 差异(公式)          │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── Level 2 (可观察输入) ──── 当Level=2时启用 ────────────────────┐ │
│ │ 可观察输入描述 | 估值方法 | 估值结果 | 差异(公式)                  │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── Level 3 (不可观察输入) ── 当Level=3时启用 ────────────────────┐ │
│ │ 不可观察输入 | 估值假设 | 估值结果 | 差异(公式)                    │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ 结论 | 备注                                                              │
├─────────────────────────────────────────────────────────────────────────┤
│ 统计：Level1笔数 / Level2笔数 / Level3笔数 / 差异超阈值笔数             │
│ 审计结论 textarea + AI按钮                                               │
└─────────────────────────────────────────────────────────────────────────┘
```

### 数据流

```
G1-1 审定表 ── EventBus(substantive:adjudicated, accountCode='1501') ──→ 附注披露 + trial_balance

G1-13 检查表 ←── GtVoucherSamplingEngine(科目1501) ──── 抽凭引擎

G1-13 检查表 ←── 📎OCR(凭证扫描件) ──── 凭证信息自动识别

G1-2 明细表 ── 公允价值数据 ──→ G1-6 公允价值测试表
G1-11 监盘表 ── 监盘日数据 ──→ G1-12 倒轧表

useVersionTrail ── autoSnapshot on save ──→ 版本快照
```

### EventBus事件

| 事件名 | 发布者 | 消费者 |
|--------|--------|--------|
| `substantive:adjudicated` | G1-1审定表 | 附注披露组件 + trial_balance |
| `disclosure:note-text-updated` | 附注披露 | 附注模块 |

### 后端AI Section清单

```
adjudication-summary / fair-value-conclusion / sppi-analysis /
business-model-conclusion / counting-conclusion / voucher-check-conclusion /
derivative-conclusion / overall-opinion
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtG1TradingFinancialAssets.vue props
interface G1TradingFinancialAssetsProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// G1-2 明细表行（35列分5区段）
interface TradingDetailRow {
  id: string
  seq: number
  // 基础信息(7列)
  securityName: string
  securityCode: string
  investType: 'stock' | 'fund' | 'bond' | 'derivative' | 'other'
  market: string
  acquisitionDate: string
  initialCost: number
  // 持有明细(7列)
  openingQuantity: number
  boughtQuantity: number
  soldQuantity: number
  closingQuantity: number       // 公式=期初+买入-卖出
  openingCost: number
  addedCost: number
  reducedCost: number
  // 公允价值(7列)
  unitFairValue: number
  closingFairValue: number      // 公式=期末数量×单位公允
  fairValueSource: '1' | '2' | '3'
  openingFairValue: number
  fairValueChange: number       // 公式=期末公允-期初公允
  cumulativeFVChange: number
  quoteDate: string
  // 损益(7列)
  disposalProceeds: number
  disposalCost: number
  realizedGain: number          // 公式=处置收入-处置成本
  dividendIncome: number
  totalIncome: number           // 公式=已实现+股利
  fvChangeInPL: number
  remark: string
  // 审定调整(7列)
  closingCost: number           // 公式=期初成本+增加-减少
  unadjusted: number
  aje: number
  rje: number
  adjusted: number              // 公式=未审+AJE+RJE
  variance: number
  indexRef: string
}

// G1-6 公允价值测试行
interface FairValueTestRow {
  id: string
  seq: number
  securityName: string
  securityCode: string
  holdingQuantity: number
  bookValue: number
  level: '1' | '2' | '3'
  // Level 1
  l1QuoteDate: string
  l1QuoteSource: string
  l1QuoteValue: number
  l1MarketValue: number         // 公式=持仓×报价
  l1Diff: number                // 公式=计算市值-账面
  // Level 2
  l2InputDesc: string
  l2ValuationMethod: string
  l2ValuationResult: number
  l2Diff: number                // 公式=估值结果-账面
  // Level 3
  l3Input: string
  l3Assumptions: string
  l3ValuationResult: number
  l3Diff: number                // 公式=估值结果-账面
  conclusion: string
  remark: string
}

// G1-11 证券监盘行
interface SecuritiesCountRow {
  id: string
  seq: number
  securityName: string
  securityCode: string
  securityType: string
  bookedQuantity: number
  countedQuantity: number
  countDiff: number             // 公式=盘点-账面
  diffReason: string
  custodian: string
  countDate: string
}

// G1-14 衍生工具核查行
interface DerivativeCheckRow {
  id: string
  seq: number
  instrumentName: string
  instrumentType: 'option' | 'futures' | 'swap' | 'forward'
  notionalAmount: number
  term: string
  counterparty: string
  margin: number
  isHedging: string
  accountingAppropriateness: 'appropriate' | 'inappropriate' | 'needs-review'
  complianceConclusion: string
}
```

### 后端接口

```python
# _g1_trading_financial_assets.py
def render_g1_trading_financial_assets(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='g1-trading-financial-assets'和sheets配置"""

# _g1_trading_financial_assets_import_export.py
POST /api/workpapers/{wp_id}/g1/export-template?sheet={code}
POST /api/workpapers/{wp_id}/g1/export-data?sheet={code}
POST /api/workpapers/{wp_id}/g1/import-data?sheet={code}  # multipart/form-data
# sheet codes: G1-2/G1-3/G1-4/G1-5/G1-6/G1-7/G1-11/G1-12/G1-13/G1-14

# _g1_trading_financial_assets_ai.py
POST /api/workpapers/{wp_id}/g1/ai/{section}
# section: adjudication-summary/fair-value-conclusion/sppi-analysis/
#          business-model-conclusion/counting-conclusion/voucher-check-conclusion/
#          derivative-conclusion/overall-opinion
```

## Data Models

### G1-1 审定表数据模型（多层结构）

```typescript
interface G1AdjudicationData {
  categories: AdjudicationCategory[]   // 投资品种分组
  totalRow: AdjudicationTotals
  trialBalanceAmount: number
  variance: number
}

interface AdjudicationCategory {
  categoryName: string                 // 股票/基金/债券/衍生/其他
  expanded: boolean
  subRows: AdjudicationSubRow[]        // 成本/公允变动/处置损益
  subtotal: AdjudicationTotals
}

interface AdjudicationSubRow {
  id: string
  item: string                         // 成本/公允价值变动/处置损益
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number              // 公式
  closingUnadjusted: number            // 借方公式
  closingAJE: number
  closingRJE: number
  closingAdjusted: number              // 公式
  indexRef: string
}
```

### G1-4 结存表数据模型

```typescript
interface InventoryRow {
  id: string
  seq: number
  securityName: string
  securityCode: string
  securityType: string
  // 期初
  openingQuantity: number
  openingCost: number
  openingFairValue: number
  // 增加
  addQuantity: number
  addCost: number
  // 减少
  reduceQuantity: number
  reduceCost: number
  disposalProceeds: number
  // 期末(公式)
  closingQuantity: number              // =期初+增加-减少
  closingCost: number                  // =期初成本+增加-减少
  closingFairValue: number
  unrealizedGain: number               // =期末公允-期末成本
}
```

## Error Handling

1. **selfLoad失败**：render-config返回404/500时显示错误卡片+重试按钮
2. **公式计算异常**：parseNum兜底（NaN/Infinity→0），除零保护
3. **Level条件启用**：Level切换时清空其他Level数据避免脏数据
4. **198行超长附注**：虚拟滚动+分页加载（首次加载前50行）
5. **35列区段Tab切换**：切换时保持行选中状态+区段间行同步
6. **多层审定表展开/折叠**：保持展开状态在localStorage
7. **盘点倒轧日期逻辑**：盘点日>报表日→警告"盘点日不应晚于报表日"
8. **借贷不平衡**：实时校验，不平衡时底部红色警告
9. **EventBus发布失败**：5秒无消费确认→toast提示
10. **导入格式错误**：后端返回详细错误列表（行号/字段/原因）

## Testing Strategy

### 前端PBT测试

| 测试文件 | 覆盖Property | 框架 |
|----------|-------------|------|
| useG1FormulaEngine.pbt.spec.ts | P1~P12 | vitest + fast-check |

### 后端测试

| 测试文件 | 覆盖范围 |
|----------|----------|
| test_g1_trading_financial_assets_pbt.py | 公允价值/借方余额/盘点差异round-trip |
| test_g1_trading_financial_assets.py | render策略+注册契约 |

### 集成测试

- sheetName分发正确性（16个sheet名→对应组件）
- 借方余额公式链（期初+借方-贷方=期末未审→+AJE+RJE=审定）
- G1-2五区段Tab行同步+公式链
- G1-6 Level条件启用/禁用逻辑
- G1-6 Level1差异公式（持仓×报价-账面值）
- G1-11→G1-12监盘→倒轧数据传递
- G1-13抽凭引擎样本填入
- EventBus(substantive:adjudicated)跨组件传递
- 导入导出round-trip(10张表)
- 虚拟滚动（198行附注流畅性）

## Correctness Properties

### Property 1: 借方余额公式
∀ opening, debit, credit ∈ ℝ≥0: calcDebitBalance(opening, debit, credit) === opening + debit - credit
**Validates: Requirements 13.1, 3.4**

### Property 2: 公允价值计算
∀ quantity ∈ ℤ≥0, unitFV ∈ ℝ≥0: calcFairValue(quantity, unitFV) === quantity × unitFV
**Validates: Requirements 13.3, 5.3, 9.3**

### Property 3: 未实现损益公式
∀ fairValue, cost ∈ ℝ≥0: calcUnrealizedGain(fairValue, cost) === fairValue - cost
**Validates: Requirements 13.4, 7.4**

### Property 4: 已实现损益公式
∀ proceeds, cost ∈ ℝ≥0: calcRealizedGain(proceeds, cost) === proceeds - cost
**Validates: Requirements 13.5, 5.5, 8.3**

### Property 5: Level1差异公式
∀ qty ∈ ℤ≥0, quote, bookValue ∈ ℝ≥0: calcLevel1Diff(qty, quote, bookValue) === qty×quote - bookValue
**Validates: Requirements 13.7, 9.2**

### Property 6: 盘点差异公式
∀ counted, booked ∈ ℤ: calcCountDiff(counted, booked) === counted - booked
**Validates: Requirements 13.8, 12.2**

### Property 7: 倒轧余额公式
∀ countDay, increase, decrease ∈ ℝ≥0: calcReconciliation(countDay, increase, decrease) === countDay + increase - decrease
**Validates: Requirements 13.9, 12.5**

### Property 8: 期末数量公式
∀ opening, bought, sold ∈ ℤ≥0: calcClosingQuantity(opening, bought, sold) === opening + bought - sold
**Validates: Requirements 13.10, 5.2, 7.2**

### Property 9: 借贷平衡恒等
∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
**Validates: Requirements 13.11, 6.2**

### Property 10: 净损益公式
∀ realizedGain ∈ ℝ, fee ∈ ℝ≥0: calcNetGain(realizedGain, fee) === realizedGain - fee
**Validates: Requirements 13.6, 8.4**

### Property 11: 公允价值变动方向性
∀ endFV > startFV ≥ 0: calcFairValueChange(endFV, startFV) > 0
**Validates: Requirements 13.12**

### Property 12: 审定数公式
∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
**Validates: Requirements 13.2, 3.5, 5.8**
