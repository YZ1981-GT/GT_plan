# Design Document: G2 应收利息专属HTML精美组件

## Overview

G2应收利息专属组件`g2-interest-receivable`。覆盖1个xlsx源模板(97KB)/10有效sheet。科目1132应收利息（借方/资产类）。独立组件，el-tabs模式(10个tab)。

核心架构：
- componentType `g2-interest-receivable`，主入口 GtG2InterestReceivable.vue
- **el-tabs模式**：10 sheets适合用tabs
- 每个sheet独立子组件 + composable
- 宽表拆分：G2-7(18列→2区段Tab) / G2-8(21列→借方/贷方独立区块)
- 借方科目公式：期末未审 = 期初审定 + 借方 - 贷方
- EventBus联动：publish substantive:adjudicated(accountCode='1132')
- 特色：利息测算(面值×利率×天数/365) + ECL三阶段减值测算 + 长期未收回风险
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useG2ImportExport, 7张表) + AI(5 section)

## Architecture

### sheetName分发模式 + el-tabs组织

GtG2InterestReceivable.vue 接收 `sheetName` prop，用正则提取编码(G2A/G2-1~G2-8/附注)，`v-if` 分发到对应子组件。外层采用el-tabs展示10个tab。

```
sheetName → regex提取编码 → v-if匹配 → 子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

el-tabs 10 tabs:
├── G2A  实质性程序表 (a-program-console)
├── G2-1 审定表
├── 附注披露(上市)
├── 附注披露(国企)
├── G2-2 明细表
├── G2-3 坏账准备明细
├── G2-4 调整分录
├── G2-5 利息测算表
├── G2-6 长期未收回检查
├── G2-7 坏账准备测算 (2区段Tab)
└── G2-8 凭证检查表 (借方/贷方区块)
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtG2InterestReceivable.vue                  # 主入口 sheetName v-if分发 + el-tabs
├── g2-interest-receivable/
│   ├── G2TabAdjudication.vue                   # G2-1 审定表（借方科目）
│   ├── G2TabDisclosureListed.vue               # 附注披露(上市)
│   ├── G2TabDisclosureSOE.vue                  # 附注披露(国企)
│   ├── G2TabDetail.vue                         # G2-2 明细表(16列)
│   ├── G2TabBadDebtDetail.vue                  # G2-3 坏账准备明细(ECL)
│   ├── G2TabAdjustment.vue                     # G2-4 调整分录
│   ├── G2TabInterestCalc.vue                   # G2-5 利息测算表
│   ├── G2TabOverdueCheck.vue                   # G2-6 长期未收回检查
│   ├── G2TabECLCalc.vue                        # G2-7 坏账准备测算(2区段Tab)
│   └── G2TabVoucherCheck.vue                   # G2-8 凭证检查表(借方/贷方区块)
├── composables/
│   ├── useG2FormulaEngine.ts                   # G2公式引擎(利息365/ECL/逾期/借方余额/阶段判定)
│   ├── useG2FormData.ts                        # 数据加载/保存/selfLoad
│   ├── useG2Adjudication.ts                    # G2-1审定表逻辑
│   ├── useG2Detail.ts                          # G2-2明细表逻辑
│   ├── useG2BadDebtDetail.ts                   # G2-3坏账准备明细逻辑
│   ├── useG2InterestCalc.ts                    # G2-5利息测算逻辑
│   ├── useG2OverdueCheck.ts                    # G2-6长期未收回逻辑
│   ├── useG2ECLCalc.ts                         # G2-7 ECL测算逻辑(2区段)
│   ├── useG2VoucherCheck.ts                    # G2-8检查表逻辑(借方/贷方)
│   ├── useG2ImportExport.ts                    # 导入导出composable(7张表)
│   └── useG2DualMode.ts                        # 双模式OO切换

backend/app/routers/wp_render_strategies/
├── _g2_interest_receivable.py                  # render策略+注册RENDERER_DISPATCH
├── _g2_interest_receivable_import_export.py    # 导入导出3端点(7张表)
└── _g2_interest_receivable_ai.py              # AI生成5 section
```

### G2-7 坏账准备测算 2区段Tab设计（18列→2×9列）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ┌────────────────────────┐ ┌────────────────────────┐                  │
│ │ 阶段划分(9列)          │ │ ECL测算(9列)           │  ← 2区段Tab      │
│ └────────────────────────┘ └────────────────────────┘                  │
│                                                                         │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ 阶段划分: 序号|投资标的|期末余额|信用等级|显著增加|已减值|         │   │
│ │           划分阶段(公式)|上期阶段|变动说明                         │   │
│ │ ECL测算:  12个月PD|存续期PD|适用PD(公式)|LGD|EAD|ECL(公式)|       │   │
│ │           企业计提|差异(公式)|测算结论                             │   │
│ └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│ 底部合计 + 审计结论 textarea + AI按钮                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### G2-8 凭证检查表 借方/贷方独立区块设计

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 抽凭引擎按钮 [使用抽凭引擎]    导入导出▾                                  │
├─────────────────────────────────────────────────────────────────────────┤
│ ┌── 借方检查区（增加/利息确认）──────────────────────────────────────┐ │
│ │ el-table: 序号|摘要|对方科目|金额|凭证日期|凭证编号|投资标的|面值|  │ │
│ │           利率|计息天数|测算利息(公式)|差异|审计结论|备注            │ │
│ │ 底部小计：金额合计 / 测算利息合计 / 差异合计                       │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ ┌── 贷方检查区（减少/利息收回）──────────────────────────────────────┐ │
│ │ el-table: 序号|摘要|对方科目|金额|凭证日期|凭证编号|收款银行|       │ │
│ │           收款日期|是否到期收回|逾期天数|审计结论|备注                │ │
│ │ 底部小计：金额合计 / 逾期笔数                                      │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ 审计结论 textarea + AI按钮                                               │
└─────────────────────────────────────────────────────────────────────────┘
```

### 数据流

```
G2-1 审定表 ── EventBus(substantive:adjudicated, accountCode='1132') ──→ 附注披露 + trial_balance

G2-8 检查表 ←── GtVoucherSamplingEngine(科目1132) ──── 抽凭引擎

G2-8 检查表 ←── 📎OCR(凭证扫描件) ──── 凭证信息自动识别

G2-2 明细表 ── 利息数据 ──→ G2-5 利息测算表 ── 验证 ──→ G2-1 审定表
G2-2 明细表 ── 减值阶段 ──→ G2-3 坏账明细 ──→ G2-7 ECL测算

useVersionTrail ── autoSnapshot on save ──→ 版本快照
```

### EventBus事件

| 事件名 | 发布者 | 消费者 |
|--------|--------|--------|
| `substantive:adjudicated` | G2-1审定表 | 附注披露组件 + trial_balance |
| `disclosure:note-text-updated` | 附注披露 | 附注模块 |

### 后端AI Section清单

```
interest-calc-conclusion / ecl-conclusion / overdue-evaluation /
voucher-check-conclusion / overall-opinion
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtG2InterestReceivable.vue props
interface G2InterestReceivableProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// G2-2 明细表行
interface InterestDetailRow {
  id: string
  seq: number
  investTarget: string          // 投资标的
  investType: string            // 投资类型
  faceValue: number             // 面值/本金
  couponRate: number            // 票面利率(%)
  accrualStart: string          // 计息起始日
  accrualEnd: string            // 计息截止日
  accruedDays: number           // 计息天数(公式)
  accruedInterest: number       // 应计利息(公式)
  receivedInterest: number      // 已收利息
  netReceivable: number         // 期末应收(公式)
  bookValue: number             // 企业账面值
  variance: number              // 差异(公式)
  eclStage: 'Stage1' | 'Stage2' | 'Stage3'  // 减值阶段
  remark: string
  indexRef: string
}

// G2-7 ECL测算行
interface ECLCalcRow {
  id: string
  seq: number
  // 阶段划分区段
  investTarget: string
  closingBalance: number
  creditRating: string
  significantIncrease: boolean
  isImpaired: boolean
  determinedStage: 1 | 2 | 3    // 公式
  previousStage: 1 | 2 | 3
  stageChangeNote: string
  // ECL测算区段
  pd12Month: number             // 12个月PD
  pdLifetime: number            // 整个存续期PD
  applicablePD: number          // 适用PD(公式)
  lgd: number                   // LGD
  ead: number                   // EAD
  eclAmount: number             // ECL金额(公式)
  companyProvision: number      // 企业计提
  eclVariance: number           // 差异(公式)
  conclusion: string
}

// G2-8 借方检查行
interface DebitCheckRow {
  id: string
  seq: number
  summary: string
  counterAccount: string
  amount: number
  voucherDate: string
  voucherNo: string
  investTarget: string
  faceValue: number
  rate: number
  accruedDays: number
  calculatedInterest: number    // 公式=面值×利率/100×天数/365
  variance: number              // 公式=测算-金额
  auditConclusion: string
  remark: string
}

// G2-8 贷方检查行
interface CreditCheckRow {
  id: string
  seq: number
  summary: string
  counterAccount: string
  amount: number
  voucherDate: string
  voucherNo: string
  receivingBank: string
  receiptDate: string
  isOnTimeRecovery: string
  overdueDays: number
  auditConclusion: string
  remark: string
}
```

### 后端接口

```python
# _g2_interest_receivable.py
def render_g2_interest_receivable(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='g2-interest-receivable'和sheets配置"""

# _g2_interest_receivable_import_export.py
POST /api/workpapers/{wp_id}/g2/export-template?sheet={code}
POST /api/workpapers/{wp_id}/g2/export-data?sheet={code}
POST /api/workpapers/{wp_id}/g2/import-data?sheet={code}  # multipart/form-data
# sheet codes: G2-2/G2-3/G2-4/G2-5/G2-6/G2-7/G2-8

# _g2_interest_receivable_ai.py
POST /api/workpapers/{wp_id}/g2/ai/{section}
# section: interest-calc-conclusion/ecl-conclusion/overdue-evaluation/
#          voucher-check-conclusion/overall-opinion
```

## Data Models

### G2-1 审定表数据模型

```typescript
interface G2AdjudicationData {
  rows: G2AdjudicationRow[]
  trialBalanceAmount: number
  variance: number
}

interface G2AdjudicationRow {
  id: string
  item: string                 // 项目名（债权投资利息/其他债权/定期存款/其他/合计）
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number      // 公式
  closingUnadjusted: number    // 借方公式
  closingAJE: number
  closingRJE: number
  closingAdjusted: number      // 公式
  indexRef: string
}
```

### G2-6 长期未收回行

```typescript
interface OverdueInterestRow {
  id: string
  seq: number
  investTarget: string
  receivableAmount: number
  agreedRecoveryDate: string
  overdueDays: number           // 公式
  overdueReason: string
  debtorCreditStatus: string
  collectionMeasures: string
  recoverability: 'full' | 'partial' | 'unlikely' | 'irrecoverable'
  needStageTransfer: string
  riskLevel: 'low' | 'medium' | 'high' | 'extreme'
  auditSuggestion: string
  remark: string
}
```

## Error Handling

1. **selfLoad失败**：render-config返回404/500时显示错误卡片+重试按钮
2. **公式计算异常**：parseNum兜底（NaN/Infinity→0），除零保护（PD=0/LGD=0→ECL=0）
3. **利息计算日期异常**：计息截止日<起始日→计息天数0，toast警告
4. **逾期天数负值保护**：约定日>当前日期→逾期天数0
5. **ECL阶段判定**：同时标记"已减值"和"未显著增加"→优先Stage3
6. **区段Tab切换**：切换时保持行选中状态
7. **借贷不平衡**：实时校验，不平衡时底部红色警告
8. **EventBus发布失败**：5秒无消费确认→toast提示
9. **导入格式错误**：后端返回详细错误列表（行号/字段/原因）
10. **OCR识别失败**：返回空结果时toast"未识别到有效凭证信息"

## Testing Strategy

### 前端PBT测试

| 测试文件 | 覆盖Property | 框架 |
|----------|-------------|------|
| useG2FormulaEngine.pbt.spec.ts | P1~P10 | vitest + fast-check |

### 后端测试

| 测试文件 | 覆盖范围 |
|----------|----------|
| test_g2_interest_receivable_pbt.py | 利息计算/ECL计算round-trip |
| test_g2_interest_receivable.py | render策略+注册契约 |

### 集成测试

- sheetName分发正确性（10个sheet名→对应组件）
- 借方余额公式链（期初+借方-贷方=期末未审→+AJE+RJE=审定）
- 利息测算公式全链路（面值×利率×天数/365）
- ECL三阶段测算（阶段判定→适用PD→ECL=EAD×PD×LGD）
- G2-7两区段Tab行同步
- G2-8抽凭引擎→样本分配到借方/贷方区
- EventBus(substantive:adjudicated)跨组件传递
- 导入导出round-trip(7张表)
- 长期未收回→阶段转移建议
- 虚拟滚动（72行ECL/103行检查表）

## Correctness Properties

### Property 1: 利息测算公式(365天基准)
∀ principal ∈ ℝ≥0, rate ∈ [0,100], days ∈ ℤ≥0: calcInterest365(principal, rate, days) === principal × rate/100 × days/365
**Validates: Requirements 12.1, 5.3, 8.3**

### Property 2: 借方余额公式
∀ opening, debit, credit ∈ ℝ≥0: calcDebitBalance(opening, debit, credit) === opening + debit - credit
**Validates: Requirements 12.3, 3.3**

### Property 3: 审定数公式
∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
**Validates: Requirements 12.4, 3.4**

### Property 4: ECL公式
∀ EAD ∈ ℝ≥0, PD ∈ [0,1], LGD ∈ [0,1]: calcECL(EAD, PD, LGD) === EAD × PD × LGD
**Validates: Requirements 12.5, 6.2, 10.4**

### Property 5: 逾期天数非负
∀ currentDate, dueDate: calcOverdueDays(currentDate, dueDate) ≥ 0
**Validates: Requirements 12.6, 9.2**

### Property 6: 借贷平衡恒等
∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
**Validates: Requirements 12.8, 7.2**

### Property 7: 利息与面值正比
∀ p1, p2 ∈ ℝ≥0, p2≠0, rate, days固定: calcInterest365(p1, rate, days) / calcInterest365(p2, rate, days) === p1/p2
**Validates: Requirements 12.1, 5.3**

### Property 8: ECL与EAD正比
∀ e1, e2 ∈ ℝ>0, PD, LGD固定: calcECL(e1, PD, LGD) / calcECL(e2, PD, LGD) === e1/e2
**Validates: Requirements 12.5, 10.4**

### Property 9: 阶段判定确定性
∀ impaired ∈ bool, significantIncrease ∈ bool: determineStage(impaired, significantIncrease) ∈ {1, 2, 3} 且 impaired=true → result === 3
**Validates: Requirements 12.7, 10.2**

### Property 10: 净应收=应计-已收
∀ accrued ∈ ℝ≥0, received ∈ ℝ≥0: calcNetReceivable(accrued, received) === accrued - received
**Validates: Requirements 12.9, 5.4**
