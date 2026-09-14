# Design Document: G5 长期应收款底稿专属HTML精美组件

## Overview

G5长期应收款专属组件`g5-long-term-receivable`。覆盖1个xlsx源模板/16有效sheet。科目1531长期应收款（借方/资产类）。**G循环中涉及融资租赁和保理业务的重要科目**，包含内含利率法摊销、实际利率法摊销、保理终止确认核查、ECL三阶段减值等特色审计内容。

核心架构：
- componentType `g5-long-term-receivable`，主入口 GtG5LongTermReceivable.vue
- **sheetName v-if dispatch模式**：16 sheets用v-if分发（不用el-tabs）
- 子目录分组：core/ + measurement/ + impairment/ + voucher/
- 宽表拆分：G5-2(22列→2区段Tab) / G5-3(20列→2区段) / G5-5(18列→2区段) / G5-10(19列→2区段) / G5-11(20列→2区段) / G5-12(21列→3区段)
- 借方科目公式：期末未审 = 期初审定 + 借方 - 贷方
- EventBus联动：publish `substantive:adjudicated`(accountCode='1531') + `disclosure:note-text-updated`
- 特色：内含利率法(G5-5) + 实际利率法(G5-6) + 保理终止确认(G5-7) + ECL三阶段(G5-9) + ECL公式链(G5-10)
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useG5ImportExport, 9张表) + AI(9 section)
- 六大集成：版本链✅ 抽凭✅ 截止✅ 附注EventBus✅ OCR✅ 复核✅

## Architecture

### sheetName分发模式 + 子目录组织

GtG5LongTermReceivable.vue 接收 `sheetName` prop，用正则提取编码(G5A/G5-1~G5-12/附注披露(上市)/附注披露(国企)/底稿目录)，`v-if` 分发到对应子组件。

```
sheetName → regex提取编码 → v-if匹配 → defineAsyncComponent子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

16 sheets 子目录分组:
├── core/
│   ├── G5A    实质性程序表（复用a-program-console + 抽凭引擎 + 截止提取）
│   ├── G5-1   审定表（87行多层：原值/坏账/净值/一年内到期/报表列示数）
│   ├── G5-2   余额明细表（22列→2区段Tab：债务人基础/余额分析+账龄）
│   ├── G5-3   坏账准备明细表（20列→2区段Tab：未审+调整/审定数）
│   ├── G5-4   调整分录汇总（AJE/RJE + 借贷平衡校验）
│   ├── 附注披露(上市)（113行虚拟滚动）
│   ├── 附注披露(国企)（109行虚拟滚动）
│   └── 底稿目录
├── measurement/
│   ├── G5-5   融资租赁未实现收益测算（内含利率法，18列→2区段Tab）
│   ├── G5-6   分期销售未实现收益测算（实际利率法）
│   ├── G5-7   保理核查表（终止确认条件判断）
│   └── G5-8   信用减值损失会计政策检查（四section问卷）
├── impairment/
│   ├── G5-9   三阶段划分（列式转置结构，债务人为列→行式交互视图）
│   ├── G5-10  坏账准备测算（ECL公式链，19列→2区段Tab）
│   └── G5-11  减值转回核销检查（20列→2区段Tab）
└── voucher/
    └── G5-12  凭证检查表（21列→3区段Tab + 抽凭引擎 + 行级OCR）
```

### 高层数据流

```mermaid
graph TD
    TB[trial_balance<br/>科目1531] -->|自动取数| G5_1[G5-1 审定表]
    G5_1 -->|EventBus: substantive:adjudicated| NOTE_L[附注披露-上市]
    G5_1 -->|EventBus: substantive:adjudicated| NOTE_S[附注披露-国企]
    NOTE_L -->|EventBus: disclosure:note-text-updated| EXT[附注模块]
    NOTE_S -->|EventBus: disclosure:note-text-updated| EXT
    G5_4[G5-4 调整分录] -->|AJE/RJE汇总回写| G5_1
    G5_5[G5-5 融资租赁测算] -->|融资收益合计比对| G5_1
    G5_6[G5-6 分期销售测算] -->|融资收益合计比对| G5_1
    G5_10[G5-10 坏账测算] -->|审定坏账准备| G5_1
    G5A[G5A 程序表] -->|抽凭引擎| VOUCHER[GtVoucherSamplingEngine]
    G5A -->|截止提取| CUTOFF[useCutoffAutoSampling]
    G5_12[G5-12 凭证检查] -->|抽凭引擎| VOUCHER
    G5_12 -->|行级OCR| OCR[/d4/contract-ocr]
    MAIN[GtG5LongTermReceivable] -->|autoSnapshot| VER[useVersionTrail]
    MAIN -->|provide openReviewDialog| CHILDREN[所有子组件]
```


### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtG5LongTermReceivable.vue                    # 主入口 sheetName v-if分发（defineAsyncComponent lazy×16）
├── g5-long-term-receivable/
│   ├── core/
│   │   ├── G5TabProcedure.vue                    # G5A 程序表（复用a-program-console+selfLoad+抽凭+截止）
│   │   ├── G5TabAdjudication.vue                 # G5-1 审定表（87行多层+虚拟滚动）
│   │   ├── G5TabBalanceDetail.vue                # G5-2 余额明细表(22列→2区段Tab)
│   │   ├── G5TabBadDebtDetail.vue                # G5-3 坏账准备明细表(20列→2区段Tab)
│   │   ├── G5TabAdjustment.vue                   # G5-4 调整分录(AJE/RJE+借贷校验)
│   │   ├── G5TabDisclosureListed.vue             # 附注披露(上市)(113行虚拟滚动)
│   │   ├── G5TabDisclosureSOE.vue                # 附注披露(国企)(109行虚拟滚动)
│   │   └── G5TabDirectory.vue                    # 底稿目录
│   ├── measurement/
│   │   ├── G5TabLeaseAmortization.vue            # G5-5 融资租赁测算（内含利率法，2区段Tab）
│   │   ├── G5TabInstallmentSales.vue             # G5-6 分期销售测算（实际利率法）
│   │   ├── G5TabFactoringCheck.vue               # G5-7 保理核查表（终止确认）
│   │   └── G5TabEclPolicy.vue                    # G5-8 会计政策检查（四section）
│   ├── impairment/
│   │   ├── G5TabStageClassification.vue          # G5-9 三阶段划分（列式→行式转置）
│   │   ├── G5TabImpairmentCalc.vue               # G5-10 坏账准备测算(ECL公式链，2区段)
│   │   └── G5TabReversalWriteoff.vue             # G5-11 转回核销检查(2区段Tab)
│   └── voucher/
│       └── G5TabVoucherCheck.vue                 # G5-12 凭证检查(3区段Tab+OCR)
├── composables/
│   ├── useG5FormulaEngine.ts                     # G5公式引擎(22个纯函数+parseNum)
│   ├── useG5FormData.ts                          # 数据加载/保存/selfLoad/writebackTB
│   ├── useG5Adjudication.ts                      # G5-1审定表逻辑(五层+EventBus)
│   ├── useG5BalanceDetail.ts                     # G5-2余额明细(2区段+行同步+账龄)
│   ├── useG5BadDebtDetail.ts                     # G5-3坏账准备(2区段+分组+公式)
│   ├── useG5Adjustment.ts                        # G5-4调整分录(借贷校验+回写)
│   ├── useG5LeaseAmortization.ts                 # G5-5融资租赁(内含利率法+分组+期间连续性)
│   ├── useG5InstallmentSales.ts                  # G5-6分期销售(实际利率法+摊余成本)
│   ├── useG5FactoringCheck.ts                    # G5-7保理核查(终止确认逻辑)
│   ├── useG5EclPolicy.ts                         # G5-8政策检查(四section问卷)
│   ├── useG5StageClassification.ts               # G5-9三阶段(列式转置+判定规则)
│   ├── useG5ImpairmentCalc.ts                    # G5-10坏账测算(ECL公式链+Stage分组)
│   ├── useG5ReversalWriteoff.ts                  # G5-11转回核销(2区段+转回校验)
│   ├── useG5VoucherCheck.ts                      # G5-12凭证检查(3区段+OCR+抽凭)
│   ├── useG5ImportExport.ts                      # 导入导出composable(9张表)
│   └── useG5DualMode.ts                          # 双模式OO切换+localStorage

backend/app/routers/wp_render_strategies/
├── _g5_long_term_receivable.py                   # render策略+注册RENDERER_DISPATCH
├── _g5_long_term_receivable_service.py           # 业务逻辑(公式验证/TB取数/EventBus)
├── _g5_long_term_receivable_import_export.py     # 导入导出端点(9张表×3=27端点)
└── _g5_long_term_receivable_ai.py                # AI生成9 section
```

### EventBus事件

| 事件名 | 发布者 | 消费者 | payload |
|--------|--------|--------|---------|
| `substantive:adjudicated` | G5-1审定表 | 附注披露(上市/国企) + trial_balance | `{accountCode:'1531', adjudicatedAmount}` |
| `disclosure:note-text-updated` | 附注披露 | 附注模块 | `{accountCode:'1531', text}` |

### 后端AI Section清单

```
adjudication-analysis / lease-amortization-conclusion / sales-amortization-conclusion /
factoring-conclusion / ecl-policy-conclusion / stage-conclusion /
impairment-conclusion / reversal-writeoff-conclusion / voucher-conclusion
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtG5LongTermReceivable.vue props
interface G5LongTermReceivableProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// sheetName正则匹配映射
const SHEET_CODE_MAP: Record<string, string> = {
  'G5A': 'procedure',
  'G5-1': 'adjudication',
  'G5-2': 'balanceDetail',
  'G5-3': 'badDebtDetail',
  'G5-4': 'adjustment',
  'G5-5': 'leaseAmortization',
  'G5-6': 'installmentSales',
  'G5-7': 'factoringCheck',
  'G5-8': 'eclPolicy',
  'G5-9': 'stageClassification',
  'G5-10': 'impairmentCalc',
  'G5-11': 'reversalWriteoff',
  'G5-12': 'voucherCheck',
  '附注披露信息（上市公司）': 'disclosureListed',
  '附注披露信息（国企）': 'disclosureSOE',
  '底稿目录': 'directory',
}
```


### G5-1 审定表数据模型（五层结构，87行）

```typescript
interface G5AdjudicationData {
  groups: AdjudicationGroup[]          // 五大分组
  trialBalanceAmount: number           // 试算表取数(科目1531)
  variance: number                     // 差异=审定-试算表
}

interface AdjudicationGroup {
  groupName: string                    // "一、原值" / "二、坏账准备" / "三、净值" / "四、一年内到期" / "五、报表列示数"
  groupType: 'gross' | 'provision' | 'net' | 'oneYear' | 'report'
  expanded: boolean
  rows: AdjudicationRow[]
  subtotal: AdjudicationTotals
}

interface AdjudicationRow {
  id: string
  item: string                         // 债务人/交易类型/小计等
  category: string                     // 融资租赁/分期销售/保理/其他/组合计提/单项计提
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number              // 公式: unadjusted + AJE + RJE
  closingUnadjusted: number            // 公式: 期初审定 + 借方 - 贷方
  closingAJE: number
  closingRJE: number
  closingAdjusted: number              // 公式: 未审 + AJE + RJE
  changeAmount: number                 // 公式: 期末审定 - 期初审定
  changeRate: number | null            // 公式: (期末-期初)/期初, 期初=0时null
  reasonAnalysis: string               // |变动率|>20%时必填(橙色高亮)
}

interface AdjudicationTotals {
  openingAdjusted: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
}
```

### G5-2 余额明细表行（22列→2区段Tab）

```typescript
interface BalanceDetailRow {
  id: string
  seq: number
  // ══ Tab1: 债务人基础信息(10列) ══
  debtorName: string                   // 债务人名称
  businessType: 'lease' | 'installment' | 'factoring' | 'other'  // 业务类型(下拉)
  contractNo: string                   // 合同编号
  startDate: string                    // 起始日
  maturityDate: string                 // 到期日
  contractAmount: number               // 合同总额
  recoveredAmount: number              // 已收回金额
  closingBalance: number               // 公式: 合同总额 - 已收回金额
  isRelatedParty: boolean              // 是否关联方

  // ══ Tab2: 余额分析+账龄(12列) ══
  unrealizedIncome: number             // 未实现融资收益
  netAmount: number                    // 公式: 期末余额 - 未实现融资收益
  aging1Year: number                   // 1年以内
  aging1to2: number                    // 1-2年
  aging2to3: number                    // 2-3年
  aging3to4: number                    // 3-4年
  aging4to5: number                    // 4-5年
  aging5Plus: number                   // 5年以上
  agingTotal: number                   // 公式: 各账龄段之和
  remark: string                       // 备注
}
```

### G5-3 坏账准备明细表行（20列→2区段Tab）

```typescript
interface BadDebtDetailRow {
  id: string
  seq: number
  // ══ Tab1: 未审数+审计调整(11列) ══
  debtorOrGroup: string                // 债务人/组合名称
  provisionMethod: 'group' | 'individual'  // 计提方式(下拉)
  closingBalance: number               // 期末余额①
  creditLossRate: number               // 信用损失率②(小数)
  unadjustedProvision: number          // 公式: ①×②
  balanceAdjustment: number            // 余额调整⑤
  adjustedLossRate: number             // 调整后损失率②A(小数)
  provisionAdjustment: number          // 公式: ⑤×②A + ①×(②A-②)
  adjustmentDesc: string               // 调整说明
  indexRef: string                     // 索引

  // ══ Tab2: 审定数(9列) ══
  adjustedBalance: number              // 公式: ①+⑤
  adjustedProvision: number            // 公式: 未审坏账+坏账调整
  adjustedNetValue: number             // 公式: 审定余额-审定坏账
  priorYearProvision: number           // 上年坏账准备
  currentYearProvision: number         // 公式: 审定坏账-上年+本年转回
  currentYearReversal: number          // 本年转回
  remark: string                       // 备注
}
```

### G5-5 融资租赁测算数据模型（内含利率法）

```typescript
interface LeaseAmortizationGroup {
  id: string
  projectName: string                  // 租赁项目名称
  // Tab1: 租赁基础信息
  basic: LeaseBasicData
  // Tab2: 摊销计算（多行=多计息期间）
  periods: LeaseAmortizationPeriod[]
}

interface LeaseBasicData {
  lessee: string                       // 承租人
  leaseStartDate: string               // 租赁开始日
  leaseEndDate: string                 // 租赁到期日
  minimumLeasePayment: number          // 最低租赁收款额
  unguaranteedResidual: number         // 未担保余值
  fairValue: number                    // 租赁资产公允价值
  implicitRate: number                 // 内含利率(小数，至少4位)
}

interface LeaseAmortizationPeriod {
  id: string
  periodNo: number                     // 期次
  openingReceivable: number            // 期初应收融资租赁款
  openingUnrealized: number            // 期初未实现融资收益
  openingNetInvestment: number         // 公式: 应收 - 未实现
  periodIncome: number                 // 公式: 净投资额 × 内含利率（核心）
  periodCollection: number             // 本期收款额
  closingReceivable: number            // 公式: 期初应收 - 本期收款
  closingUnrealized: number            // 公式: 期初未实现 - 本期收益
  closingNetInvestment: number         // 公式: 期末应收 - 期末未实现
  variance: number                     // 差异: 审计测算 - 企业账面
}

interface LeaseAmortizationSummary {
  totalIncome: number                  // 各项目融资收益合计
  companyBookIncome: number            // 企业账面融资收益
  totalVariance: number                // 差异合计
  conclusion: string                   // 审计结论
}
```

### G5-6 分期销售测算数据模型（实际利率法）

```typescript
interface InstallmentSalesGroup {
  id: string
  projectName: string                  // 销售项目名称
  // Section(一): 初始交易要素
  initial: InstallmentInitialData
  // Section(二): 分期摊销（多行=多收款期间）
  periods: InstallmentPeriod[]
}

interface InstallmentInitialData {
  contractTotal: number                // 合同约定应收总额
  fairValue: number                    // 商品公允价值
  unrealizedIncome: number             // 公式: 应收总额 - 公允价值
  effectiveRate: number                // 实际利率(小数)
  collectionTerm: string               // 收款期限
}

interface InstallmentPeriod {
  id: string
  periodNo: number                     // 期次
  openingReceivable: number            // 期初应收款余额
  openingUnrealized: number            // 期初未实现融资收益
  openingAmortizedCost: number         // 公式: 应收 - 未实现
  periodIncome: number                 // 公式: 摊余成本 × 实际利率（核心）
  periodCollection: number             // 本期收款额
  closingReceivable: number            // 公式: 期初应收 - 本期收款
  closingAmortizedCost: number         // 公式: 期初摊余 + 收益 - 收款
}
```

### G5-7 保理核查表数据模型

```typescript
interface FactoringCheckRow {
  id: string
  seq: number
  debtorName: string                   // 债务人名称
  factorName: string                   // 保理商名称
  factoringAmount: number              // 保理金额
  factoringType: 'recourse' | 'non-recourse'  // 有追索/无追索
  meetsDerecognition: boolean          // 是否满足终止确认
  derecognitionBasis: string           // 终止确认判断依据(textarea)
  auditConclusion: 'reasonable' | 'unreasonable'  // 审计结论
  indexRef: string                     // 索引
}

interface FactoringSummary {
  totalAmount: number                  // 保理总金额
  derecognizedAmount: number           // 已终止确认金额
  notDerecognizedAmount: number        // 未终止确认金额
}
```


### G5-8 会计政策检查数据模型（四section问卷）

```typescript
interface EclPolicyData {
  sections: EclPolicySection[]
  overallConclusion: string            // 综合审计结论
}

interface EclPolicySection {
  id: string
  sectionNo: number                    // (一)~(四)
  title: string                        // ECL计量方法/组合划分/参数确定/政策一致性
  rows: EclPolicyRow[]
}

// Section(一)(二)(三)
interface EclPolicyRow {
  id: string
  checkItem: string                    // 检查项目
  requirement: string                  // 要求(方法论)
  companyPolicy: string                // 企业政策(textarea)
  compliance: 'compliant' | 'basically_compliant' | 'non_compliant'  // 是否合规
  description: string                  // 说明
}

// Section(四) 政策一致性
interface PolicyConsistencyRow {
  id: string
  policyItem: string                   // 政策事项
  priorYearPolicy: string              // 上年政策
  currentYearPolicy: string            // 本年政策
  hasChanged: boolean                  // 是否变更
  changeReason: string                 // 变更理由
  reasonability: 'reasonable' | 'basically_reasonable' | 'unreasonable'  // 合理性评价
}
```

### G5-9 三阶段划分数据模型（列式转置→行式交互视图）

```typescript
interface StageClassificationData {
  debtors: StageDebtorRow[]            // 行式交互视图（每债务人一行）
  detailChecks: StageDetailCheck[]     // 展开明细（逐项检查）
  summary: StageSummary
}

interface StageDebtorRow {
  id: string
  debtorName: string                   // 债务人名称
  hasSignificantIncrease: boolean      // 综合：信用风险显著增加
  hasLowCreditRisk: boolean            // 综合：较低信用风险
  hasCreditImpairment: boolean         // 综合：已发生信用减值
  companyStage: 'Stage1' | 'Stage2' | 'Stage3'  // 企业划分阶段
  auditStage: 'Stage1' | 'Stage2' | 'Stage3'    // 审计判断阶段（规则计算）
  isConsistent: boolean                // 公式: companyStage === auditStage
  varianceDesc: string                 // 不一致时差异说明（强制填写）
  indexRef: string                     // 索引
}

interface StageDetailCheck {
  debtorId: string                     // 关联债务人
  part: 'significantIncrease' | 'lowCreditRisk' | 'creditImpairment'  // 三个区块
  items: { factor: string; answer: 'yes' | 'no' | 'na' }[]  // 逐项检查
}

interface StageSummary {
  stage1Count: number
  stage2Count: number
  stage3Count: number
  inconsistentCount: number
}
```

### G5-10 坏账准备测算数据模型（ECL公式链，19列→2区段）

```typescript
interface ImpairmentCalcRow {
  id: string
  // ══ Tab1: 未审数+审计调整(11列) ══
  debtorOrGroup: string                // 债务人/组合
  bookBalance: number                  // 账面余额①
  pvFutureCashFlow: number             // 预计未来现金流量现值
  creditLossRate: number               // 预期信用损失率②(小数)
  unadjustedProvision: number          // 公式: ①×② (坏账准备③)
  bookValue: number                    // 公式: ①-③ (账面价值④)
  balanceAdjustment: number            // 余额调整⑤
  adjustedLossRate: number             // 调整后损失率②A
  provisionAdjustment: number          // 公式: ⑤×②A+①×(②A-②) (坏账调整⑥)
  stage: 'Stage1' | 'Stage2' | 'Stage3'  // 阶段
  indexRef: string                     // 索引

  // ══ Tab2: 审定数+差异(8列) ══
  adjustedBalance: number              // 公式: ①+⑤ (审定余额⑦)
  adjustedProvision: number            // 公式: ③+⑥ (审定坏账准备⑧)
  adjustedBookValue: number            // 公式: ⑦-⑧ (审定账面价值⑨)
  priorYearProvision: number           // 上年坏账准备
  currentYearProvision: number         // 公式: ⑧-上年+本年转回
  currentYearReversal: number          // 本年转回
  varianceDesc: string                 // 差异说明
}
```

### G5-11 转回核销检查数据模型（20列→2区段Tab）

```typescript
interface ReversalCheckRow {
  id: string
  seq: number
  // ══ Tab1: 转回检查(10列) ══
  entityName: string                   // 单位名称
  reversalReason: string               // 转回原因
  recoveryMethod: string               // 收回方式
  originalBasis: string                // 原计提依据
  reversalAmount: number               // 转回金额
  accumulatedProvision: number         // 收回前累计计提
  reasonabilityAnalysis: string        // 合理性分析(textarea)
  isReasonable: 'reasonable' | 'unreasonable'  // 是否合理
  indexRef: string                     // 索引
}

interface WriteoffCheckRow {
  id: string
  seq: number
  // ══ Tab2: 核销检查(10列) ══
  entityName: string                   // 单位名称
  writeoffNature: string               // 核销性质(下拉)
  writeoffAmount: number               // 核销金额
  writeoffReason: string               // 核销原因(textarea)
  writeoffProcedure: string            // 核销程序(textarea)
  isRelatedTransaction: boolean        // 是否关联交易
  reasonabilityAnalysis: string        // 合理性分析(textarea)
  isReasonable: 'reasonable' | 'unreasonable'  // 是否合理
  indexRef: string                     // 索引
}
```

### G5-12 凭证检查表数据模型（21列→3区段Tab）

```typescript
interface VoucherCheckRow {
  id: string
  // ══ Tab1: 凭证基础(8列) ══
  voucherDate: string                  // 日期
  voucherNo: string                    // 凭证编号
  businessContent: string              // 业务内容
  counterAccount: string               // 对方科目
  detailAccount: string                // 明细科目
  debitAmount: number                  // 借方金额
  creditAmount: number                 // 贷方金额
  attachment: string | null            // 📎附件路径(OCR触发)

  // ══ Tab2: 核对内容(8列) ══
  supportingDocDesc: string            // 支持性文件描述
  check1OriginalComplete: boolean      // 核对1-原始凭证完整
  check2Authorization: boolean         // 核对2-授权批准
  check3Accounting: boolean            // 核对3-账务处理正确
  check4Calculation: boolean           // 核对4-金额计算正确
  check5FinancingIncome: boolean       // 核对5-融资收益确认正确
  check6Impairment: boolean            // 核对6-减值计提正确
  check7Classification: boolean        // 核对7-期限分类正确

  // ══ Tab3: 结论(5列) ══
  indexNo: string                      // 索引号(GtIndexChip)
  isAbnormal: boolean                  // 是否异常(Tab2任一✗→自动是)
  abnormalDesc: string                 // 异常说明(textarea)
  riskLevel: 'high' | 'medium' | 'low'  // 风险等级
  remark: string                       // 备注
}
```

## API Design

### 后端接口

```python
# _g5_long_term_receivable.py
# RENDERER_DISPATCH注册
def render_g5_long_term_receivable(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='g5-long-term-receivable'和sheets配置"""

# _g5_long_term_receivable_import_export.py
POST /api/workpapers/{wp_id}/g5/export-template?sheet={code}
POST /api/workpapers/{wp_id}/g5/export-data?sheet={code}
POST /api/workpapers/{wp_id}/g5/import-data?sheet={code}  # multipart/form-data
# sheet codes: G5-2 / G5-3 / G5-4 / G5-5 / G5-6 / G5-7 / G5-10 / G5-11 / G5-12
# 宽表按区段分sheet导出：
#   G5-2(2sheet) / G5-3(2sheet) / G5-5(2sheet) / G5-10(2sheet) / G5-11(2sheet) / G5-12(3sheet)

# _g5_long_term_receivable_ai.py
POST /api/workpapers/{wp_id}/g5/ai/{section}
# section: adjudication-analysis / lease-amortization-conclusion /
#          sales-amortization-conclusion / factoring-conclusion /
#          ecl-policy-conclusion / stage-conclusion /
#          impairment-conclusion / reversal-writeoff-conclusion / voucher-conclusion

# _g5_long_term_receivable_service.py
class G5LongTermReceivableService:
    async def get_trial_balance_data(project_id, year) -> dict
    async def save_adjudication(wp_id, data) -> dict
    async def validate_formulas(data) -> list[ValidationError]
    async def get_cutoff_samples(project_id, account_code, days) -> list
```

### trial_balance 取数

```sql
-- G5-1审定表自动取数
SELECT standard_account_code, unadjusted_amount, aje_adjustment, audited_amount
FROM trial_balance
WHERE project_id = :project_id
  AND year = :year
  AND standard_account_code LIKE '1531%'
```

### 注册四件套

```python
# 1. htmlRendererRegistry (前端)
'g5-long-term-receivable': () => import('./workpaper/GtG5LongTermReceivable.vue')

# 2. wp_code_overrides.json (16条)
{
  "G5A-长期应收款实质性程序表": "g5-long-term-receivable",
  "G5-1-审定表": "g5-long-term-receivable",
  "G5-2-余额明细表": "g5-long-term-receivable",
  "G5-3-坏账准备明细表": "g5-long-term-receivable",
  "G5-4-调整分录汇总": "g5-long-term-receivable",
  "G5-5-未实现融资收益测算表（租赁）": "g5-long-term-receivable",
  "G5-6-未实现融资收益测算表（销售）": "g5-long-term-receivable",
  "G5-7-长期应收款保理核查表": "g5-long-term-receivable",
  "G5-8-信用减值损失会计政策检查": "g5-long-term-receivable",
  "G5-9-长期应收款三阶段划分": "g5-long-term-receivable",
  "G5-10-长期应收款坏账准备测算": "g5-long-term-receivable",
  "G5-11-减值准备转回核销检查表": "g5-long-term-receivable",
  "G5-12-凭证检查表": "g5-long-term-receivable",
  "G5-附注披露信息（上市公司）": "g5-long-term-receivable",
  "G5-附注披露信息（国企）": "g5-long-term-receivable",
  "G5-底稿目录": "g5-long-term-receivable"
}

# 3. VALID_COMPONENT_TYPES (后端)
'g5-long-term-receivable'

# 4. RENDERER_DISPATCH (后端)
'g5-long-term-receivable': render_g5_long_term_receivable
```


## Data Models

### 存储结构（working_paper.content JSON）

```typescript
interface G5Content {
  // G5-1 审定表
  adjudication: {
    groups: AdjudicationGroup[]
  }
  // G5-2 余额明细
  balanceDetail: {
    rows: BalanceDetailRow[]
  }
  // G5-3 坏账准备明细
  badDebtDetail: {
    rows: BadDebtDetailRow[]
  }
  // G5-4 调整分录
  adjustment: {
    entries: AdjustmentEntry[]
  }
  // G5-5 融资租赁测算
  leaseAmortization: {
    groups: LeaseAmortizationGroup[]
    conclusion: string
  }
  // G5-6 分期销售测算
  installmentSales: {
    groups: InstallmentSalesGroup[]
    conclusion: string
  }
  // G5-7 保理核查
  factoringCheck: {
    rows: FactoringCheckRow[]
    conclusion: string
  }
  // G5-8 会计政策检查
  eclPolicy: EclPolicyData
  // G5-9 三阶段划分
  stageClassification: StageClassificationData
  // G5-10 坏账准备测算
  impairmentCalc: {
    rows: ImpairmentCalcRow[]
  }
  // G5-11 转回核销
  reversalWriteoff: {
    reversals: ReversalCheckRow[]
    writeoffs: WriteoffCheckRow[]
  }
  // G5-12 凭证检查
  voucherCheck: {
    rows: VoucherCheckRow[]
  }
  // 附注
  disclosureListed: { sections: DisclosureSection[] }
  disclosureSOE: { sections: DisclosureSection[] }
}

interface AdjustmentEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  preparedBy: string
  remark: string
}

interface DisclosureSection {
  id: string
  title: string
  rows: DisclosureRow[]
  textContent?: string                 // 文本区内容
}
```

## Integration Design（6大集成接入点）

### 1. 版本链 (useVersionTrail)

```typescript
// GtG5LongTermReceivable.vue 主入口
const { autoSnapshot, showVersionTrail } = useVersionTrail(wpId)

async function handleSave() {
  await saveData()
  await autoSnapshot()  // 触发版本快照
}
// 工具栏"版本历史"按钮 → GtWpVersionTrail drawer
```

### 2. 抽凭引擎 (G5A程序表 + G5-12凭证检查)

```typescript
// G5TabProcedure.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['1531']"
  dialog-mode
  @samples-ready="fillSamples"
/>

// G5TabVoucherCheck.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['1531']"
  dialog-mode
  @samples-ready="fillVoucherRows"
/>
```

### 3. 截止自动提取 (useCutoffAutoSampling)

```typescript
// G5TabProcedure.vue 截止测试步骤
const { fetchCutoffSamples } = useCutoffAutoSampling({
  projectId, accountCode: '1531', days: 5
})
```

### 4. 附注EventBus

```typescript
// G5TabAdjudication.vue (发布者)
watch(reportAmount, (val) => {
  eventBus.publish('substantive:adjudicated', {
    accountCode: '1531',
    adjudicatedAmount: val
  })
})

// G5TabDisclosureListed.vue / G5TabDisclosureSOE.vue (消费者)
eventBus.subscribe('substantive:adjudicated', (payload) => {
  if (payload.accountCode === '1531') refreshData()
})

// 附注文本变更发布
eventBus.publish('disclosure:note-text-updated', {
  accountCode: '1531', text: noteText
})
```

### 5. 行级OCR (G5-12 📎附件列)

```typescript
// G5TabVoucherCheck.vue
async function handleOCR(row: VoucherCheckRow, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const result = await http.post('/d4/contract-ocr', formData)
  // ElMessageBox确认 → merge填入当前行
  const confirmed = await ElMessageBox.confirm(
    `识别结果：${result.data.summary}，是否填入？`
  )
  if (confirmed) mergeOCRResult(row, result.data)
}
```

### 6. 复核对话 (provide/inject)

```typescript
// GtG5LongTermReceivable.vue (主入口)
const { openReviewDialog } = useReviewDialog(wpId)
provide('openReviewDialog', openReviewDialog)

// 子组件 (section标题栏右侧按钮)
const openReviewDialog = inject('openReviewDialog')
```

## 宽表区段Tab拆分详细设计

### G5-2 余额明细表（22列→2区段）

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌──────────────────┐ ┌──────────────────────┐                  │
│ │Tab1: 债务人基础(10)│ │Tab2: 余额分析+账龄(12)│    区段Tab     │
│ └──────────────────┘ └──────────────────────┘                  │
│                                                                 │
│ Tab1: 序号|债务人名称|业务类型|合同编号|起始日|到期日|合同总额|    │
│       已收回|期末余额(公式)|是否关联方                           │
│                                                                 │
│ Tab2: 序号|债务人名称|未实现融资收益|净额(公式)|1年以内|1-2年|    │
│       2-3年|3-4年|4-5年|5年以上|账龄合计(公式)|备注              │
│                                                                 │
│ 校验：账龄合计 ≠ 净额 → 红色高亮                                │
│ 底部：合计行(合同总额/已收回/余额/净额/各账龄段)                  │
│ 行同步：Tab切换保持行索引                                        │
└─────────────────────────────────────────────────────────────────┘
```

### G5-5 融资租赁测算（18列→2区段）

```
┌─────────────────────────────────────────────────────────────────┐
│ 方法论上下文（琥珀色左边线+浅黄背景）                             │
│ "内含利率法：融资收益 = 期初净投资额 × 内含利率"                  │
│                                                                 │
│ ═══ 租赁项目A ═══════════════════════════════════════════════════│
│ Tab1: 租赁基础信息(8列)                                          │
│ ┌───────────────────────────────────────────────────────────┐   │
│ │ 项目名|承租人|开始日|到期日|最低收款额|未担保余值|公允价值|利率 │   │
│ └───────────────────────────────────────────────────────────┘   │
│                                                                 │
│ Tab2: 摊销计算(10列，多行=多期间)                                 │
│ ┌───────────────────────────────────────────────────────────┐   │
│ │ 期次|期初应收|期初未实现|净投资额(公式)|融资收益(公式)|         │
│ │ 收款额|期末应收(公式)|期末未实现(公式)|期末净投资(公式)|差异    │
│ │ ─ 第1期: ...                                              │   │
│ │ ─ 第2期: ... (验证期间连续性)                              │   │
│ └───────────────────────────────────────────────────────────┘   │
│                                                                 │
│ ═══ 租赁项目B ═══ ...                                           │
│                                                                 │
│ 合计：融资收益合计 vs G5-1审定                                    │
│ 审计结论 textarea + AI按钮                                       │
│ <details>编制提示</details>                                      │
└─────────────────────────────────────────────────────────────────┘
```

### G5-12 凭证检查表（21列→3区段Tab）

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│ │Tab1:凭证(8)│ │Tab2:核对(8)│ │Tab3:结论(5)│    3区段Tab        │
│ └──────────┘ └──────────┘ └──────────┘                        │
│                                                                 │
│ Tab1: 日期|凭证编号|业务内容|对方科目|明细科目|借方|贷方|📎附件   │
│       (📎点击→上传→OCR识别→ElMessageBox确认→填入)                │
│                                                                 │
│ Tab2: 文件描述|✓完整|✓授权|✓账务|✓计算|✓融资收益|✓减值|✓期限     │
│       (任一✗→Tab3"是否异常"自动置"是")                           │
│                                                                 │
│ Tab3: 索引号(GtIndexChip)|是否异常|异常说明|风险等级|备注         │
│                                                                 │
│ 顶部：借贷差额汇总（差额≠0红色）                                 │
│ 虚拟滚动：99行                                                   │
│ 行同步：3个Tab间切换保持行索引                                    │
└─────────────────────────────────────────────────────────────────┘
```


## Formula Engine Design (useG5FormulaEngine.ts)

### 22个纯函数签名

```typescript
// === 基础公式 ===
export function parseNum(v: unknown): number
export function calcDebitBalance(opening: number, debit: number, credit: number): number
export function calcAdjustedAmount(unadjusted: number, aje: number, rje: number): number
export function calcNetValue(grossValue: number, badDebtProvision: number): number
export function calcReportAmount(netValue: number, oneYearMaturity: number): number
export function calcChangeRate(prior: number, current: number): number | null

// === 融资租赁（内含利率法）===
export function calcNetInvestment(receivable: number, unrealizedIncome: number): number
export function calcLeaseFinancingIncome(netInvestment: number, implicitRate: number): number
export function calcEndingReceivable(openingReceivable: number, periodCollection: number): number
export function calcEndingUnrealizedIncome(openingUnrealized: number, periodIncome: number): number

// === 分期销售（实际利率法）===
export function calcInstallmentFinancingIncome(amortizedCost: number, effectiveRate: number): number
export function calcSalesAmortizedCost(openingCost: number, income: number, collection: number): number

// === ECL减值 ===
export function calcImpairmentProvision(bookBalance: number, creditLossRate: number): number
export function calcImpairmentAdjustment(balanceAdj: number, adjRate: number, origBalance: number, origRate: number): number
export function calcAdjustedBalance(orig: number, adj: number): number
export function calcAdjustedImpairment(origImpairment: number, impairmentAdj: number): number
export function calcAdjustedBookValue(adjBalance: number, adjImpairment: number): number

// === 三阶段判定 ===
export function determineStage(hasSignificantIncrease: boolean, hasLowCreditRisk: boolean, hasCreditImpairment: boolean): 'Stage1' | 'Stage2' | 'Stage3'

// === 校验函数 ===
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean
export function isReversalValid(reversalAmount: number, accumulatedProvision: number): boolean
export function calcAgingTotal(y1: number, y2: number, y3: number, y4: number, y5: number, y5plus: number): number

// === 辅助 ===
export function calcCurrentYearProvision(adjustedProvision: number, priorYear: number, reversal: number): number
```

### determineStage 决策逻辑

```typescript
export function determineStage(
  hasSignificantIncrease: boolean,
  hasLowCreditRisk: boolean,
  hasCreditImpairment: boolean
): 'Stage1' | 'Stage2' | 'Stage3' {
  // 优先级：Stage3 > Stage2 > Stage1
  if (hasCreditImpairment) return 'Stage3'
  if (hasSignificantIncrease) return 'Stage2'
  return 'Stage1'
  // 注：hasLowCreditRisk为true时可简化判断为Stage1（CAS22简化处理）
  // 但本实现以hasCreditImpairment/hasSignificantIncrease为优先判据
}
```

### ECL公式链推导（G5-10核心）

```
给定：①账面余额, ②信用损失率, ⑤余额调整, ②A调整后损失率

③未审坏账准备 = ① × ②
④账面价值 = ① - ③ = ① - ①×② = ①(1-②)
⑥坏账调整 = ⑤×②A + ①×(②A-②)
⑦审定余额 = ① + ⑤
⑧审定坏账 = ③ + ⑥ = ①×② + ⑤×②A + ①×(②A-②) = ⑤×②A + ①×②A = (①+⑤)×②A = ⑦×②A
⑨审定账面 = ⑦ - ⑧ = (①+⑤) - (①+⑤)×②A = (①+⑤)(1-②A) = ⑦(1-②A)

验证：⑧ = ⑦ × ②A（审定坏账 = 审定余额 × 调整后损失率）
```

## PBT Test Design

### 测试文件结构

```
audit-platform/frontend/src/components/workpaper/composables/__tests__/
└── useG5FormulaEngine.spec.ts         # 18个PBT属性 + fast-check

backend/tests/
└── test_g5_long_term_receivable_pbt.py  # 后端PBT验证(hypothesis)
```

### 前端PBT（fast-check，numRuns≥100）

```typescript
import fc from 'fast-check'
import { describe, it, expect } from 'vitest'
import * as F from '../useG5FormulaEngine'

// P1: 借方余额公式
fc.assert(fc.property(
  fc.float({ min: 0, noNaN: true }), fc.float({ min: 0, noNaN: true }), fc.float({ min: 0, noNaN: true }),
  (opening, debit, credit) => {
    expect(F.calcDebitBalance(opening, debit, credit)).toBeCloseTo(opening + debit - credit, 6)
  }
), { numRuns: 100 })

// P3: 内含利率法
fc.assert(fc.property(
  fc.float({ min: 0, max: 1e9, noNaN: true }),
  fc.float({ min: 0.0001, max: 0.9999, noNaN: true }),
  (net, rate) => {
    expect(F.calcLeaseFinancingIncome(net, rate)).toBeCloseTo(net * rate, 6)
  }
), { numRuns: 100 })

// P4: 实际利率法
fc.assert(fc.property(
  fc.float({ min: 0, max: 1e9, noNaN: true }),
  fc.float({ min: 0.0001, max: 0.9999, noNaN: true }),
  (cost, rate) => {
    expect(F.calcInstallmentFinancingIncome(cost, rate)).toBeCloseTo(cost * rate, 6)
  }
), { numRuns: 100 })

// P5: 融资租赁期间连续性
fc.assert(fc.property(
  fc.float({ min: 0, max: 1e9, noNaN: true }),
  fc.float({ min: 0, max: 1e8, noNaN: true }),
  fc.float({ min: 0, max: 1e9, noNaN: true }),
  fc.float({ min: 0, max: 1e8, noNaN: true }),
  (openRec, collection, openUnr, income) => {
    const endRec = F.calcEndingReceivable(openRec, collection)
    const endUnr = F.calcEndingUnrealizedIncome(openUnr, income)
    const netInv = F.calcNetInvestment(endRec, endUnr)
    expect(netInv).toBeCloseTo((openRec - collection) - (openUnr - income), 6)
  }
), { numRuns: 100 })

// P6: 分期销售摊余成本递推
fc.assert(fc.property(
  fc.float({ min: 0, max: 1e9, noNaN: true }),
  fc.float({ min: 0.0001, max: 0.5, noNaN: true }),
  fc.float({ min: 0, max: 1e8, noNaN: true }),
  (cost, rate, collection) => {
    const income = F.calcInstallmentFinancingIncome(cost, rate)
    const endCost = F.calcSalesAmortizedCost(cost, income, collection)
    expect(endCost).toBeCloseTo(cost * (1 + rate) - collection, 4)
  }
), { numRuns: 100 })

// P7: ECL公式链一致性
fc.assert(fc.property(
  fc.float({ min: 1, max: 1e8, noNaN: true }),   // ①
  fc.float({ min: 0.001, max: 0.99, noNaN: true }), // ②
  fc.float({ min: -1e6, max: 1e6, noNaN: true }),   // ⑤
  fc.float({ min: 0.001, max: 0.99, noNaN: true }), // ②A
  (bal, rate, adj, adjRate) => {
    const prov = F.calcImpairmentProvision(bal, rate)       // ③
    const provAdj = F.calcImpairmentAdjustment(adj, adjRate, bal, rate) // ⑥
    const adjBal = F.calcAdjustedBalance(bal, adj)          // ⑦
    const adjProv = F.calcAdjustedImpairment(prov, provAdj) // ⑧
    const adjBV = F.calcAdjustedBookValue(adjBal, adjProv)  // ⑨
    // ⑨ = (①+⑤) - (①×② + ⑤×②A + ①×(②A-②))
    const expected = (bal + adj) - (bal * rate + adj * adjRate + bal * (adjRate - rate))
    expect(adjBV).toBeCloseTo(expected, 4)
  }
), { numRuns: 100 })

// P8: 坏账调整公式展开
// P9: 三阶段确定性
// P10: Stage3优先级
// P11: 借贷平衡恒等
// P12: 转回有效性
// P13: 净值=原值-坏账
// P14: 报表数=净值-一年内
// P15: 账龄合计交换律
// P16: parseNum健壮性
// P17: 变动率方向性
// P18: 净投资额恒等
// (同requirements中P8~P18定义，每个属性numRuns≥100)
```

### 后端PBT（hypothesis，max_examples=5）

```python
# test_g5_long_term_receivable_pbt.py
from hypothesis import given, strategies as st, settings

@settings(max_examples=5)
@given(
    opening=st.floats(min_value=0, max_value=1e9, allow_nan=False),
    debit=st.floats(min_value=0, max_value=1e9, allow_nan=False),
    credit=st.floats(min_value=0, max_value=1e9, allow_nan=False),
)
def test_debit_balance_formula(opening, debit, credit):
    """P1: 借方余额=期初+借方-贷方"""
    result = calc_debit_balance(opening, debit, credit)
    assert abs(result - (opening + debit - credit)) < 1e-6

@settings(max_examples=5)
@given(
    net_investment=st.floats(min_value=0, max_value=1e9, allow_nan=False),
    implicit_rate=st.floats(min_value=0.0001, max_value=0.9999, allow_nan=False),
)
def test_lease_financing_income(net_investment, implicit_rate):
    """P3: 内含利率法=净投资额×内含利率"""
    result = calc_lease_financing_income(net_investment, implicit_rate)
    assert abs(result - net_investment * implicit_rate) < 1e-6

# P4~P18 同结构...
```

## Performance Design

### 虚拟滚动触发阈值

| Sheet | 行数 | 虚拟滚动 | 实现方案 |
|-------|------|---------|---------|
| G5-1 审定表 | 87 | ✅ | el-table-v2 / vxe-table virtual |
| G5-2 余额明细 | 115 | ✅ | 同上 |
| G5-9 三阶段 | 58 | ✅ | 同上 |
| G5-10 坏账测算 | 63 | ✅ | 同上 |
| G5-12 凭证检查 | 99 | ✅ | 同上 |
| 附注(上市) | 113 | ✅ | 同上 |
| 附注(国企) | 109 | ✅ | 同上 |
| 其他 | <50 | ❌ | 普通el-table |

### defineAsyncComponent 懒加载

```typescript
// GtG5LongTermReceivable.vue
const G5TabProcedure = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabProcedure.vue'))
const G5TabAdjudication = defineAsyncComponent(() => import('./g5-long-term-receivable/core/G5TabAdjudication.vue'))
// ... 共16个defineAsyncComponent
```

## Security & Validation

- 所有导入文件经后端解析验证（openpyxl），不执行公式/宏
- 数值字段通过parseNum统一转换，防NaN/undefined传播
- OCR端点POST限制文件大小≤10MB，仅接受image/pdf类型
- 保理核查"有追索+终止确认"组合触发橙色警告（非阻断）
- 转回金额校验：reversalAmount ≤ accumulatedProvision（阻断保存）
- 借贷平衡校验：差额>0.01时橙色警告（非阻断，允许保存但标记）


## Correctness Properties

> 来自 requirements.md 18个PBT性质的技术实现映射。

### Property 1: 借方余额公式
∀ opening, debit, credit ∈ ℝ≥0: calcDebitBalance(opening, debit, credit) === opening + debit - credit
- 测试函数: calcDebitBalance | 框架: fast-check + hypothesis
- **Validates: Requirements 15.1**

### Property 2: 审定数公式
∀ unadjusted, aje, rje ∈ ℝ: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje
- 测试函数: calcAdjustedAmount | 框架: fast-check + hypothesis
- **Validates: Requirements 15.2**

### Property 3: 内含利率法核心公式
∀ netInvestment ∈ ℝ≥0, implicitRate ∈ (0,1): calcLeaseFinancingIncome(netInvestment, implicitRate) === netInvestment × implicitRate
- 测试函数: calcLeaseFinancingIncome | 框架: fast-check + hypothesis
- **Validates: Requirements 15.6**

### Property 4: 实际利率法核心公式
∀ amortizedCost ∈ ℝ≥0, effectiveRate ∈ (0,1): calcInstallmentFinancingIncome(amortizedCost, effectiveRate) === amortizedCost × effectiveRate
- 测试函数: calcInstallmentFinancingIncome | 框架: fast-check + hypothesis
- **Validates: Requirements 15.7**

### Property 5: 融资租赁期间连续性
∀ openingReceivable, collection, openingUnrealized, income ∈ ℝ≥0: calcNetInvestment(calcEndingReceivable(openingReceivable, collection), calcEndingUnrealizedIncome(openingUnrealized, income)) === (openingReceivable - collection) - (openingUnrealized - income)
- 测试函数: calcNetInvestment∘calcEnding* | 框架: fast-check
- **Validates: Requirements 15.5, 15.8, 15.9**

### Property 6: 分期销售摊余成本递推
∀ openingCost, rate ∈ (0,1), collection ∈ ℝ≥0: calcSalesAmortizedCost(openingCost, calcInstallmentFinancingIncome(openingCost, rate), collection) === openingCost×(1+rate) - collection
- 测试函数: calcSalesAmortizedCost | 框架: fast-check
- **Validates: Requirements 15.10**

### Property 7: ECL公式链一致性
∀ ①,②,⑤,②A ∈ ℝ≥0: calcAdjustedBookValue(calcAdjustedBalance(①,⑤), calcAdjustedImpairment(calcImpairmentProvision(①,②), calcImpairmentAdjustment(⑤,②A,①,②))) === (①+⑤) - (①×② + ⑤×②A + ①×(②A-②))
- 测试函数: 组合验证(③⑥⑦⑧⑨) | 框架: fast-check + hypothesis
- **Validates: Requirements 15.11, 15.12, 15.13, 15.14, 15.15**

### Property 8: 坏账调整公式展开
∀ balanceAdj, adjRate, origBalance, origRate ∈ ℝ: calcImpairmentAdjustment(balanceAdj, adjRate, origBalance, origRate) === balanceAdj×adjRate + origBalance×(adjRate-origRate)
- 测试函数: calcImpairmentAdjustment | 框架: fast-check
- **Validates: Requirements 15.12**

### Property 9: 三阶段划分确定性
∀ (hasSignificantIncrease, hasLowCreditRisk, hasCreditImpairment) ∈ boolean³: determineStage输出确定性映射到Stage1/Stage2/Stage3之一
- 测试函数: determineStage | 框架: fast-check
- **Validates: Requirements 15.16**

### Property 10: Stage3优先级
∀ inputs where hasCreditImpairment=true: determineStage(...) === 'Stage3'
- 测试函数: determineStage(hasCreditImpairment=true) | 框架: fast-check
- **Validates: Requirements 15.16**

### Property 11: 借贷平衡恒等
∀ debits[], credits[] ∈ ℝ[]: isDebitCreditBalanced(debits, credits) ↔ (|SUM(debits)-SUM(credits)| < 0.01)
- 测试函数: isDebitCreditBalanced | 框架: fast-check
- **Validates: Requirements 15.17**

### Property 12: 转回有效性
∀ reversal ∈ ℝ≥0, accumulated ∈ ℝ≥0: isReversalValid(reversal, accumulated) ↔ (reversal ≤ accumulated)
- 测试函数: isReversalValid | 框架: fast-check
- **Validates: Requirements 15.18**

### Property 13: 净值=原值-坏账
∀ gross ∈ ℝ≥0, provision ∈ ℝ≥0: calcNetValue(gross, provision) === gross - provision
- 测试函数: calcNetValue | 框架: fast-check
- **Validates: Requirements 15.3**

### Property 14: 报表数=净值-一年内
∀ net ∈ ℝ≥0, oneYear ∈ ℝ≥0: calcReportAmount(net, oneYear) === net - oneYear
- 测试函数: calcReportAmount | 框架: fast-check
- **Validates: Requirements 15.4**

### Property 15: 账龄合计加法交换律
∀ y1~y5plus ∈ ℝ≥0: calcAgingTotal(y1,y2,y3,y4,y5,y5plus) === calcAgingTotal(permutation(y1~y5plus))
- 测试函数: calcAgingTotal | 框架: fast-check
- **Validates: Requirements 15.20**

### Property 16: parseNum健壮性
∀ input ∈ {null, undefined, '', NaN, '  ', 'abc'}: parseNum(input) === 0；∀ n ∈ ℝ: parseNum(n) === n
- 测试函数: parseNum | 框架: fast-check
- **Validates: Requirements 15.21**

### Property 17: 变动率方向性
∀ current > prior > 0: calcChangeRate(prior, current) > 0；∀ current < prior, prior > 0: calcChangeRate(prior, current) < 0；calcChangeRate(0, any) === null
- 测试函数: calcChangeRate | 框架: fast-check
- **Validates: Requirements 15.19**

### Property 18: 净投资额恒等
∀ receivable ∈ ℝ≥0, unrealized ∈ ℝ≥0 where unrealized ≤ receivable: calcNetInvestment(receivable, unrealized) === receivable - unrealized ≥ 0
- 测试函数: calcNetInvestment | 框架: fast-check
- **Validates: Requirements 15.5**

## Error Handling

| 场景 | 处理策略 |
|------|---------|
| render-config 加载失败 | selfLoad重试1次 → 失败显示"加载失败"占位 + 重试按钮 |
| trial_balance 取数无数据 | 审定表显示0值 + 橙色提示"未找到科目1531数据" |
| 公式计算溢出/NaN | parseNum兜底→0，公式列显示"—" |
| 导入Excel格式不匹配 | 后端返回422 + 具体列错误信息 → 前端ElMessage.error |
| OCR识别失败 | ElMessage.warning提示 + 手动填写fallback |
| EventBus消息丢失 | 附注组件mounted时主动拉取最新审定数（非纯被动监听） |
| 保存时网络异常 | 自动重试3次(指数退避) → 失败后localStorage暂存 + 恢复提示 |
| 虚拟滚动行高不一致 | textarea行使用预估高度 + ResizeObserver动态修正 |
| sheetName无法识别 | fallback到OnlyOffice渲染（确保不白屏） |

## Testing Strategy

### 测试分层

| 层 | 工具 | 范围 | 数量估计 |
|----|------|------|---------|
| PBT(前端) | vitest + fast-check | 22个公式函数×18属性 | ~20 test cases |
| PBT(后端) | pytest + hypothesis | 公式验证+API契约 | ~10 test cases |
| 单元测试(前端) | vitest | composable逻辑/数据转换 | ~30 test cases |
| 单元测试(后端) | pytest | service/renderer/import-export | ~20 test cases |
| 集成测试 | pytest | API端点(27导入导出+9AI+render) | ~15 test cases |
| E2E | Playwright | 关键用户路径(审定表填写/保理核查/凭证OCR) | ~5 scenarios |

### 关键测试路径

1. **审定表完整流程**：TB取数 → 填写AJE/RJE → 公式计算 → EventBus发布 → 附注刷新
2. **融资租赁测算**：输入基础信息 → 内含利率法逐期计算 → 期间连续性验证 → 差异分析
3. **ECL公式链**：余额①+损失率② → 调整⑤/②A → 公式链⑥⑦⑧⑨ → Stage分组汇总
4. **保理核查**：有追索+终止确认 → 橙色警告 → 结论生成
5. **凭证OCR**：上传附件 → OCR识别 → 确认弹窗 → 填入行 → Tab2核对 → Tab3异常判定
