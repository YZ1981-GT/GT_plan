# Design Document: G3 应收股利专属HTML精美组件

## Overview

G3应收股利专属组件`g3-dividend-receivable`。覆盖1个xlsx源模板(469KB)/7有效sheet。科目1131应收股利（借方/资产类）。相对简单，el-tabs模式(7个tab)。

核心架构：
- componentType `g3-dividend-receivable`，主入口 GtG3DividendReceivable.vue
- **el-tabs模式**：7 sheets适合用tabs
- 每个sheet独立子组件 + composable
- 宽表拆分：G3-2(33列→4区段Tab) / G3-4(18列→2区段Tab)
- 借方科目公式：期末未审 = 期初审定 + 借方(宣告) - 贷方(收回)
- EventBus联动：publish substantive:adjudicated(accountCode='1131')
- 特色：股利测算(持股数×每股股利) + 33列明细宽表 + 实际分红率分析 + 长期未收回评估
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useG3ImportExport, 5张表) + AI(3 section)

## Architecture

### sheetName分发模式 + el-tabs组织

GtG3DividendReceivable.vue 接收 `sheetName` prop，用正则提取编码(G3A/G3-1~G3-5/附注)，`v-if` 分发到对应子组件。外层采用el-tabs展示7个tab。

```
sheetName → regex提取编码 → v-if匹配 → 子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

el-tabs 7 tabs:
├── G3A  实质性程序表 (a-program-console)
├── G3-1 审定表（22列，按被投资方分行）
├── 附注披露(上市)
├── 附注披露(国企)
├── G3-2 明细表 (33列→4区段Tab)
├── G3-3 调整分录
├── G3-4 测算及检查表 (18列→2区段Tab)
└── G3-5 长期未收回检查
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtG3DividendReceivable.vue                  # 主入口 sheetName v-if分发 + el-tabs
├── g3-dividend-receivable/
│   ├── G3TabAdjudication.vue                   # G3-1 审定表（22列，按被投资方）
│   ├── G3TabDisclosureListed.vue               # 附注披露(上市)
│   ├── G3TabDisclosureSOE.vue                  # 附注披露(国企)
│   ├── G3TabDetail.vue                         # G3-2 明细表(33列→4区段Tab)
│   ├── G3TabAdjustment.vue                     # G3-3 调整分录
│   ├── G3TabCalcCheck.vue                      # G3-4 测算及检查表(2区段Tab)
│   └── G3TabOverdueCheck.vue                   # G3-5 长期未收回检查
├── composables/
│   ├── useG3FormulaEngine.ts                   # G3公式引擎(股利/分红率/借方余额/审定/逾期/权益份额)
│   ├── useG3FormData.ts                        # 数据加载/保存/selfLoad
│   ├── useG3Adjudication.ts                    # G3-1审定表逻辑(按被投资方)
│   ├── useG3Detail.ts                          # G3-2明细表逻辑(4区段)
│   ├── useG3CalcCheck.ts                       # G3-4测算及检查逻辑(2区段)
│   ├── useG3OverdueCheck.ts                    # G3-5长期未收回逻辑
│   ├── useG3ImportExport.ts                    # 导入导出composable(5张表)
│   └── useG3DualMode.ts                        # 双模式OO切换

backend/app/routers/wp_render_strategies/
├── _g3_dividend_receivable.py                  # render策略+注册RENDERER_DISPATCH
├── _g3_dividend_receivable_import_export.py    # 导入导出3端点(5张表)
└── _g3_dividend_receivable_ai.py              # AI生成3 section
```

### G3-2明细表 4区段Tab设计（33列）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │
│ │被投资方信息8列│ │ 持股明细9列  │ │ 分红方案8列  │ │ 应收核算8列  │Tab│
│ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │
│                                                                         │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ el-table (动态行，区段间行同步)                                    │   │
│ │ 被投资方: 序号|名称|信用代码|注册资本|行业|投资类型|投资成本|投资日期│   │
│ │ 持股明细: 数量|比例|净利润|净资产|权益份额(公式)|账面值|核算方法|    │   │
│ │           是否上市|上市代码                                         │   │
│ │ 分红方案: 决议日|方案描述|每股股利|宣告日|权利日|除权日|分红总额(公式)│   │
│ │           |实际分红率(公式)                                         │   │
│ │ 应收核算: 应收股利(公式)|已收|期末应收(公式)|收款日|收款方式|是否逾期│   │
│ │           |逾期天数(公式)|备注                                      │   │
│ └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│ 底部合计：投资成本合计/分红总额合计/应收合计/已收合计/期末应收合计         │
└─────────────────────────────────────────────────────────────────────────┘
```

### G3-4 测算及检查表 2区段Tab设计（18列）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ┌─────────────────────────┐ ┌─────────────────────────┐                │
│ │ 股利测算(9列)           │ │ 凭证检查(9列)           │  ← 2区段Tab   │
│ └─────────────────────────┘ └─────────────────────────┘                │
│                                                                         │
│ 抽凭引擎按钮 [使用抽凭引擎]                                              │
│                                                                         │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ 股利测算: 序号|被投资方|持股数量|每股股利|应收股利(公式)|宣告日|   │   │
│ │           权利日|分红文件编号|测算差异(公式)                       │   │
│ │ 凭证检查: 凭证日期|凭证编号|摘要|对方科目|金额|收款银行|到账日期| │   │
│ │           核对结果|审计结论                                        │   │
│ └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│ 底部合计 + 审计结论 textarea + AI按钮 + 编制提示details                   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 数据流

```
G3-1 审定表 ── EventBus(substantive:adjudicated, accountCode='1131') ──→ 附注披露 + trial_balance

G3-4 测算检查 ←── GtVoucherSamplingEngine(科目1131) ──── 抽凭引擎

G3-2 明细表 ── 被投资方/持股/分红数据 ──→ G3-4 测算检查
G3-2 明细表 ── 逾期数据 ──→ G3-5 长期未收回

useVersionTrail ── autoSnapshot on save ──→ 版本快照
```

### EventBus事件

| 事件名 | 发布者 | 消费者 |
|--------|--------|--------|
| `substantive:adjudicated` | G3-1审定表 | 附注披露组件 + trial_balance |
| `disclosure:note-text-updated` | 附注披露 | 附注模块 |

### 后端AI Section清单

```
dividend-calc-conclusion / overdue-evaluation / overall-opinion
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtG3DividendReceivable.vue props
interface G3DividendReceivableProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// G3-2 明细表行（33列分4区段）
interface DividendDetailRow {
  id: string
  seq: number
  // 被投资方信息(8列)
  investeeName: string
  socialCreditCode: string
  registeredCapital: number
  industry: string
  investType: 'long-term-equity' | 'other-equity'
  initialCost: number
  investDate: string
  // 持股明细(9列)
  sharesHeld: number            // 持股数量(股)
  shareholdingRatio: number     // 持股比例(%)
  investeeNetProfit: number     // 被投资方净利润
  investeeNetAssets: number     // 被投资方净资产
  equityShare: number           // 权益份额(公式)
  bookValue: number             // 账面值
  accountingMethod: 'cost' | 'equity'  // 核算方法
  isListed: string
  listingCode: string
  // 分红方案(8列)
  resolutionDate: string        // 股东大会决议日
  dividendPlan: string          // 分红方案描述
  dps: number                   // 每股股利(元)
  declarationDate: string       // 宣告日
  recordDate: string            // 股权登记日
  exDividendDate: string        // 除权日
  totalDividend: number         // 分红总额(公式)
  payoutRatio: number           // 实际分红率(公式)
  // 应收核算(8列)
  dividendReceivable: number    // 应收股利(公式)
  receivedAmount: number        // 已收金额
  netReceivable: number         // 期末应收(公式)
  receiptDate: string           // 收款日期
  receiptMethod: string         // 收款方式
  isOverdue: string             // 是否逾期
  overdueDays: number           // 逾期天数(公式)
  remark: string
}

// G3-4 测算及检查行
interface CalcCheckRow {
  id: string
  seq: number
  // 股利测算区段
  investeeName: string
  sharesHeld: number
  dps: number
  calculatedDividend: number    // 公式=持股×每股股利
  declarationDate: string
  recordDate: string
  dividendDocNo: string
  calcVariance: number          // 测算差异(公式)
  // 凭证检查区段
  voucherDate: string
  voucherNo: string
  summary: string
  counterAccount: string
  amount: number
  receivingBank: string
  receiptDate: string
  reconciliationResult: string
  auditConclusion: string
}

// G3-5 长期未收回行
interface OverdueDividendRow {
  id: string
  seq: number
  investeeName: string
  receivableAmount: number
  declarationDate: string
  agreedPaymentDate: string
  overdueDays: number           // 公式
  overdueReason: string
  investeeOperatingStatus: string
  historicalDividendRecord: string
  recoverability: 'full' | 'partial' | 'unlikely' | 'irrecoverable'
  riskLevel: 'low' | 'medium' | 'high' | 'extreme'
  auditSuggestion: string
  remark: string
}
```

### 后端接口

```python
# _g3_dividend_receivable.py
def render_g3_dividend_receivable(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='g3-dividend-receivable'和sheets配置"""

# _g3_dividend_receivable_import_export.py
POST /api/workpapers/{wp_id}/g3/export-template?sheet={code}
POST /api/workpapers/{wp_id}/g3/export-data?sheet={code}
POST /api/workpapers/{wp_id}/g3/import-data?sheet={code}  # multipart/form-data
# sheet codes: G3-2/G3-3/G3-4/G3-5 (G3-1审定表动态行也支持)

# _g3_dividend_receivable_ai.py
POST /api/workpapers/{wp_id}/g3/ai/{section}
# section: dividend-calc-conclusion / overdue-evaluation / overall-opinion
```

## Data Models

### G3-1 审定表数据模型

```typescript
interface G3AdjudicationData {
  rows: G3AdjudicationRow[]
  trialBalanceAmount: number
  variance: number
}

interface G3AdjudicationRow {
  id: string
  investeeName: string          // 被投资方
  shareholdingRatio: number     // 持股比例
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number       // 公式
  closingUnadjusted: number     // 借方公式=期初+宣告-收回
  closingAJE: number
  closingRJE: number
  closingAdjusted: number       // 公式
  currentDeclared: number       // 本期宣告(借方)
  currentReceived: number       // 本期收回(贷方)
  remark: string
  indexRef: string
}
```

## Error Handling

1. **selfLoad失败**：render-config返回404/500时显示错误卡片+重试按钮
2. **公式计算异常**：parseNum兜底（NaN/Infinity→0），除零保护（净利润=0→分红率N/A）
3. **逾期天数负值保护**：约定日>当前日期→逾期天数0
4. **分红率异常**：净利润≤0时分红率显示"N/A"而非负数
5. **4区段Tab切换**：切换时保持行选中状态
6. **动态行新增**：新增被投资方时弹ElMessageBox.prompt输入名称
7. **借贷不平衡**：实时校验，不平衡时底部红色警告
8. **EventBus发布失败**：5秒无消费确认→toast提示
9. **导入格式错误**：后端返回详细错误列表

## Testing Strategy

### 前端PBT测试

| 测试文件 | 覆盖Property | 框架 |
|----------|-------------|------|
| useG3FormulaEngine.pbt.spec.ts | P1~P10 | vitest + fast-check |

### 后端测试

| 测试文件 | 覆盖范围 |
|----------|----------|
| test_g3_dividend_receivable_pbt.py | 股利计算/借方余额round-trip |
| test_g3_dividend_receivable.py | render策略+注册契约 |

### 集成测试

- sheetName分发正确性（7个sheet名→对应组件）
- 借方余额公式链（期初+借方-贷方=期末未审→+AJE+RJE=审定）
- 股利测算公式（持股数×每股股利）
- 实际分红率计算（分红总额/净利润×100%）
- G3-2四区段Tab切换+行同步
- G3-4两区段Tab行同步+抽凭引擎样本填入
- EventBus(substantive:adjudicated)跨组件传递
- 导入导出round-trip(5张表)
- 逾期天数计算+风险评估

## Correctness Properties

### Property 1: 股利测算公式
∀ shares ∈ ℤ≥0, dps ∈ ℝ≥0: calcDividend(shares, dps) === shares × dps
**Validates: Requirements 9.1, 5.3, 5.5, 7.2**

### Property 2: 借方余额公式
∀ opening, debit, credit ∈ ℝ≥0: calcDebitBalance(opening, debit, credit) === opening + debit - credit
**Validates: Requirements 9.3, 3.3**

### Property 3: 审定数公式
∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
**Validates: Requirements 9.4, 3.4**

### Property 4: 逾期天数非负
∀ currentDate, dueDate: calcOverdueDays(currentDate, dueDate) ≥ 0
**Validates: Requirements 9.5, 8.2**

### Property 5: 借贷平衡恒等
∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
**Validates: Requirements 9.8, 6.2**

### Property 6: 分红率与分红总额正比
∀ d1, d2 ∈ ℝ≥0, d2≠0, netProfit>0固定: calcPayoutRatio(d1, netProfit) / calcPayoutRatio(d2, netProfit) === d1/d2
**Validates: Requirements 9.2, 5.4**

### Property 7: 股利与持股数正比
∀ s1, s2 ∈ ℤ>0, dps固定: calcDividend(s1, dps) / calcDividend(s2, dps) === s1/s2
**Validates: Requirements 9.1, 5.3**

### Property 8: 净应收=应收-已收
∀ receivable ∈ ℝ≥0, received ∈ ℝ≥0: calcNetReceivable(receivable, received) === receivable - received
**Validates: Requirements 9.6, 5.6**

### Property 9: 权益份额公式
∀ netAssets ∈ ℝ, ratio ∈ [0,100]: calcEquityShare(netAssets, ratio) === netAssets × ratio/100
**Validates: Requirements 9.7, 5.2**

### Property 10: 分红率非负(净利润>0)
∀ dividendTotal ∈ ℝ≥0, netProfit ∈ ℝ>0: calcPayoutRatio(dividendTotal, netProfit) ≥ 0
**Validates: Requirements 9.2**
