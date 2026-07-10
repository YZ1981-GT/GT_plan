# Design Document: G4 债权投资底稿(ECL组)专属HTML精美组件

## Overview

G4债权投资(ECL组)专属组件`g4-bond-investment-ecl`。覆盖1个xlsx源模板中的7个sheet（含2个只读参考材料）。科目1501债权投资（借方/资产类）。**CAS22/CAS24预期信用损失计量核心逻辑**：三阶段划分确定减值计提基数和方法，ECL测算验证减值准备金额的合理性，凭证检查确认会计处理正确性。

核心架构：
- componentType `g4-bond-investment-ecl`，主入口 GtG4BondInvestmentEcl.vue
- **sheetName v-if dispatch模式**：7 sheets用v-if分发（不用el-tabs）
- 子目录分组：impairment/ + voucher/ + reference/
- 宽表拆分：G4-10(19列→2区段Tab) / G4-12(20列→2区段Tab) / G4-13(19列→3区段Tab)
- 公式引擎：useG4EclFormulaEngine.ts（15纯函数，ECL公式链核心⑥=⑤×②A+①×(②A-②)可负）
- 特色：三阶段Stage判定+ECL公式链自动计算+凭证OCR识别+借贷平衡实时校验
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useG4EclImportExport, 4张表) + AI(5 section)
- 六大集成：版本链✅ 抽凭✅(G4-13) OCR✅(G4-13) 复核✅ 截止❌ 附注EventBus❌
- 虚拟滚动：G4-9(61行) / G4-13(97行) / 参考-减值指引(178行)

**三组拆分定位**：
| 组 | spec | 核心职责 |
|----|------|----------|
| main | g4-bond-investment-main | 程序表+审定表+附注+明细表+调整+利息测算 |
| SPPI | g4-bond-investment-sppi | 业务模式分析+SPPI合同现金流+盘点倒轧 |
| **ECL(本spec)** | g4-bond-investment-ecl | 三阶段划分+减值测算+ECL计量+转回核销+凭证检查+参考材料 |

## Architecture

### sheetName分发模式 + 子目录组织

GtG4BondInvestmentEcl.vue 接收 `sheetName` prop，用正则提取编码，`v-if` 分发到对应子组件。

```
sheetName → regex提取编码 → v-if匹配 → 子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

7 sheets 子目录分组:
├── impairment/
│   ├── G4-9   三阶段划分（Stage1/2/3判定 + 一致性比对）
│   ├── G4-10  减值准备测算表（ECL公式链 + 2区段Tab）
│   ├── G4-11  预期信用损失计量测试（ECL方法评价 + 4 section）
│   └── G4-12  减值准备转回核销检查（2区段Tab）
├── voucher/
│   └── G4-13  凭证检查表（3区段Tab + 行级OCR + 抽凭引擎）
└── reference/
    ├── 参考-减值指引（只读178行 + 虚拟滚动）
    └── 参考-PD折算（只读20行）
```

### 高层数据流

```mermaid
graph TD
    G4_9[G4-9 三阶段划分] -->|Stage分类结果| G4_10[G4-10 减值测算]
    G4_10 -->|减值准备审定| MAIN[g4-bond-investment-main<br/>G4-1审定表]
    G4_11[G4-11 ECL计量测试] -->|方法评价| G4_10
    G4_12[G4-12 转回核销] -->|转回/核销金额| G4_10
    G4_13[G4-13 凭证检查] -->|抽凭引擎| VOUCHER[GtVoucherSamplingEngine]
    G4_13 -->|OCR识别| OCR[/d4/contract-ocr]
    ECL_MAIN[GtG4BondInvestmentEcl] -->|autoSnapshot| VER[useVersionTrail]
    ECL_MAIN -->|provide openReviewDialog| CHILDREN[所有子组件]
    REF[参考材料] -.->|只读查阅| G4_9
    REF -.->|只读查阅| G4_10
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtG4BondInvestmentEcl.vue                      # 主入口 sheetName v-if分发
├── g4-bond-investment-ecl/
│   ├── impairment/
│   │   ├── G4TabStageClassification.vue           # G4-9 三阶段划分（61行虚拟滚动）
│   │   ├── G4TabImpairmentCalc.vue                # G4-10 减值测算（2区段Tab）
│   │   ├── G4TabEclMeasurement.vue                # G4-11 ECL计量测试（4 section）
│   │   └── G4TabReversalWriteOff.vue              # G4-12 转回核销（2区段Tab）
│   ├── voucher/
│   │   └── G4TabVoucherCheck.vue                  # G4-13 凭证检查（3区段Tab+OCR）
│   └── reference/
│       ├── G4TabRefImpairmentGuidance.vue         # 参考-减值指引（178行虚拟滚动）
│       └── G4TabRefPdConversion.vue               # 参考-PD折算（20行只读）
├── composables/
│   ├── useG4EclFormulaEngine.ts                   # 公式引擎(15纯函数+parseNum)
│   ├── useG4EclFormData.ts                        # 数据加载/保存/selfLoad
│   ├── useG4EclStageClassification.ts             # G4-9逻辑(Stage判定+一致性比对)
│   ├── useG4EclImpairmentCalc.ts                  # G4-10逻辑(公式链+分组小计)
│   ├── useG4EclReversalWriteOff.ts                # G4-12逻辑(转回校验+核销标记)
│   ├── useG4EclVoucherCheck.ts                    # G4-13逻辑(OCR+异常判定+借贷校验)
│   ├── useG4EclImportExport.ts                    # 导入导出composable(4张表)
│   └── useG4EclDualMode.ts                        # 双模式OO切换+localStorage

backend/app/routers/wp_render_strategies/
├── _g4_bond_investment_ecl.py                     # render策略+RENDERER_DISPATCH
├── _g4_bond_investment_ecl_import_export.py       # 导入导出端点(4张表)
└── _g4_bond_investment_ecl_ai.py                  # AI生成5 section
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtG4BondInvestmentEcl.vue props
interface G4BondInvestmentEclProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// sheetName正则匹配映射
const SHEET_CODE_MAP: Record<string, string> = {
  'G4-9': 'stageClassification',
  'G4-10': 'impairmentCalc',
  'G4-11': 'eclMeasurement',
  'G4-12': 'reversalWriteOff',
  'G4-13': 'voucherCheck',
  '参考-中证协': 'refImpairmentGuidance',
  '参考-根据剩余期限折算PD': 'refPdConversion',
}
```

### G4-9 三阶段划分数据模型

```typescript
interface StageClassificationRow {
  id: string
  seq: number
  investProject: string              // 投资项目
  initialRating: string              // 初始信用评级
  currentRating: string              // 当前信用评级
  ratingChange: string               // 评级变动
  overdue30Days: boolean             // 是否逾期30天以上
  creditImpaired: boolean            // 是否发生信用减值事件
  companyStage: 'Stage1' | 'Stage2' | 'Stage3'  // 企业划分阶段(下拉)
  auditStage: 'Stage1' | 'Stage2' | 'Stage3'    // 审计判断阶段(下拉)
  isConsistent: boolean              // 公式: companyStage === auditStage
  discrepancyNote: string            // 差异说明(不一致时必填)
  indexRef: string                   // 索引
}

interface StageClassificationData {
  rows: StageClassificationRow[]
  summary: {
    stage1Count: number
    stage2Count: number
    stage3Count: number
    inconsistentCount: number
  }
  conclusion: string                 // 审计结论
}
```

### G4-10 减值准备测算表数据模型（19列→2区段Tab）

```typescript
interface ImpairmentCalcRow {
  id: string
  seq: number
  investProject: string              // 投资项目
  stageGroup: 'Stage1' | 'Stage2' | 'Stage3'  // 所属Stage分组

  // ══ Tab1: 未审数+审计调整(9列) ══
  bookBalance: number                // ①账面余额
  pvFutureCashFlow: number           // 预计未来现金流量现值
  creditLossRate: number             // ②预期信用损失率
  impairmentProvision: number        // ③减值准备 = ①×② (公式)
  bookValue: number                  // ④账面价值 = ①-③ (公式)
  balanceAdjustment: number          // ⑤账面余额调整
  adjustedCreditLossRate: number     // ②A调整后信用损失率
  impairmentAdjustment: number       // ⑥减值准备调整 = ⑤×②A+①×(②A-②) (公式,可负)

  // ══ Tab2: 审定数+差异(7列) ══
  adjBookBalance: number             // ⑦审定账面余额 = ①+⑤ (公式)
  adjImpairment: number              // ⑧审定减值准备 = ③+⑥ (公式)
  adjBookValue: number               // ⑨审定账面价值 = ⑦-⑧ (公式)
  priorImpairment: number            // 上年减值准备
  currentProvision: number           // 本年计提 (公式)
  currentReversal: number            // 本年转回 (公式)
  differenceNote: string             // 差异说明
}

interface ImpairmentCalcData {
  rows: ImpairmentCalcRow[]
  conclusion: string
}
```

### G4-11 ECL计量测试数据模型

```typescript
interface EclMeasurementData {
  // section(一) ECL计量方法评价
  methodEvaluation: MethodEvalRow[]
  // section(二) 组合划分依据
  groupBasis: GroupBasisRow[]
  // section(三) 信用损失率确定
  parameterEvaluation: ParameterEvalRow[]
  // section(四) 审计结论
  conclusion: string
}

interface MethodEvalRow {
  id: string
  checkItem: string                  // 检查项目
  checkContent: string               // 检查内容(方法论上下文)
  companyMethod: string              // 企业采用方法(textarea)
  auditEvaluation: '合理' | '基本合理' | '不合理'  // 审计评价(下拉)
  note: string                       // 说明(textarea)
}

interface GroupBasisRow {
  id: string
  groupName: string                  // 组合名称
  basis: string                      // 划分依据
  riskCharacteristic: string         // 信用风险特征
  sampleSize: number                 // 样本量
  auditEvaluation: '合理' | '不合理'  // 审计评价(下拉)
  note: string                       // 说明
}

interface ParameterEvalRow {
  id: string
  paramName: string                  // 参数名称(PD/LGD/EAD)
  dataSource: string                 // 数据来源
  calcMethod: string                 // 计算方法
  verificationResult: string         // 审计验证结果
  auditEvaluation: '合理' | '基本合理' | '不合理'
  note: string
}
```

### G4-12 转回核销检查表数据模型（20列→2区段Tab）

```typescript
interface ReversalRow {
  id: string
  seq: number
  unitName: string                   // 单位名称
  reversalReason: string             // 转回原因
  recoveryMethod: string             // 收回方式
  originalBasis: string              // 原确定坏账准备依据
  reversalAmount: number             // 收回或转回金额
  accumulatedProvision: number       // 收回前累计计提
  reasonAnalysis: string             // 合理性分析(textarea)
  isReasonable: '合理' | '不合理'    // 是否合理(下拉)
  indexRef: string                   // 索引
}

interface WriteOffRow {
  id: string
  seq: number
  unitName: string                   // 单位名称
  writeOffType: '到期' | '逾期' | '其他'  // 核销性质(下拉)
  writeOffAmount: number             // 核销金额
  writeOffReason: string             // 核销原因(textarea)
  writeOffProcedure: string          // 核销程序(textarea)
  isRelatedParty: boolean            // 是否关联交易
  reasonAnalysis: string             // 合理性分析(textarea)
  isReasonable: '合理' | '不合理'
  indexRef: string
}

interface ReversalWriteOffData {
  reversals: ReversalRow[]
  writeOffs: WriteOffRow[]
  conclusion: string
}
```

### G4-13 凭证检查表数据模型（19列→3区段Tab）

```typescript
interface VoucherCheckRow {
  id: string
  seq: number
  section: 'debit' | 'credit'        // 借方区/贷方区

  // ══ Tab1: 记账凭证基础列(8列) ══
  date: string                       // 日期
  voucherNo: string                  // 凭证编号
  businessContent: string            // 业务内容
  counterAccount: string             // 对方科目
  detailAccount: string              // 明细科目
  debitAmount: number                // 借方金额
  creditAmount: number               // 贷方金额
  attachment: string | null          // 📎附件(文件路径/OCR结果)

  // ══ Tab2: 支持性文件+核对内容(7列) ══
  supportingDocDesc: string          // 支持性文件描述
  checkOriginalComplete: boolean     // 核对1-原始凭证完整
  checkAuthorized: boolean           // 核对2-有授权批准
  checkAccountingCorrect: boolean    // 核对3-账务处理正确
  checkInitialCostCorrect: boolean   // 核对4-初始成本计算正确
  checkInterestCorrect: boolean      // 核对5-利息计算正确
  checkImpairmentCorrect: boolean    // 核对6-减值计提正确

  // ══ Tab3: 结论+备注(4列) ══
  indexRef: string                   // 索引号
  isAbnormal: boolean                // 是否异常(任一核对✗→自动设为是)
  abnormalNote: string               // 异常说明(textarea)
  remark: string                     // 备注
}

interface VoucherCheckData {
  rows: VoucherCheckRow[]
  debitTotal: number                 // 借方合计
  creditTotal: number                // 贷方合计
  difference: number                 // 差额
  isBalanced: boolean                // |差额| < 0.01
  conclusion: string
}
```

### 后端接口

```python
# _g4_bond_investment_ecl.py
def render_g4_bond_investment_ecl(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='g4-bond-investment-ecl'和sheets配置"""

# _g4_bond_investment_ecl_import_export.py
POST /api/workpapers/{wp_id}/g4-ecl/export-template?sheet={code}
POST /api/workpapers/{wp_id}/g4-ecl/export-data?sheet={code}
POST /api/workpapers/{wp_id}/g4-ecl/import-data?sheet={code}  # multipart/form-data
# sheet codes: G4-9 / G4-10 / G4-12 / G4-13
# G4-10按2区段分sheet导出，G4-12按2Tab分sheet导出，G4-13按3区段分sheet导出

# _g4_bond_investment_ecl_ai.py
POST /api/workpapers/{wp_id}/g4-ecl/ai/{section}
# section: stage-classification-conclusion / ecl-measurement-conclusion /
#           ecl-method-evaluation / reversal-writeoff-conclusion / voucher-check-conclusion
```

### 注册四件套

```python
# 1. htmlRendererRegistry (前端)
'g4-bond-investment-ecl': () => import('./workpaper/GtG4BondInvestmentEcl.vue')

# 2. wp_code_overrides.json (7条)
{
  "G4-9-债权投资三阶段划分": "g4-bond-investment-ecl",
  "G4-10-债权投资减值准备测算表": "g4-bond-investment-ecl",
  "G4-11-预期信用损失的计量测试": "g4-bond-investment-ecl",
  "G4-12-减值准备转回核销检查表": "g4-bond-investment-ecl",
  "G4-13-凭证检查表": "g4-bond-investment-ecl",
  "G4-参考-中证协金融工具减值指引": "g4-bond-investment-ecl",
  "G4-参考-根据剩余期限折算PD": "g4-bond-investment-ecl"
}

# 3. VALID_COMPONENT_TYPES (后端)
'g4-bond-investment-ecl'

# 4. RENDERER_DISPATCH (后端)
'g4-bond-investment-ecl': render_g4_bond_investment_ecl
```

## Data Models

### 存储结构（working_paper.content JSON）

```typescript
interface G4EclContent {
  stageClassification: StageClassificationData   // G4-9
  impairmentCalc: ImpairmentCalcData             // G4-10
  eclMeasurement: EclMeasurementData             // G4-11
  reversalWriteOff: ReversalWriteOffData         // G4-12
  voucherCheck: VoucherCheckData                 // G4-13
  // 参考材料为只读，不存储编辑数据
}
```

### G4-10 分组小计结构

```typescript
// G4-10按Stage分组显示 + 小计行
interface ImpairmentCalcGrouped {
  stage1: { rows: ImpairmentCalcRow[], subtotal: GroupSubtotal }
  stage2: { rows: ImpairmentCalcRow[], subtotal: GroupSubtotal }
  stage3: { rows: ImpairmentCalcRow[], subtotal: GroupSubtotal }
  grandTotal: GroupSubtotal
}

interface GroupSubtotal {
  bookBalance: number           // Σ①
  impairmentProvision: number   // Σ③
  bookValue: number             // Σ④
  balanceAdjustment: number     // Σ⑤
  impairmentAdjustment: number  // Σ⑥
  adjBookBalance: number        // Σ⑦
  adjImpairment: number         // Σ⑧
  adjBookValue: number          // Σ⑨
}
```

## Formula Engine Design

### useG4EclFormulaEngine.ts — 15个纯函数 + parseNum

所有函数为纯函数（无副作用、无Vue响应式依赖、无外部状态），支持fast-check PBT验证。

```typescript
// ══════════════════════════════════════════════════════════
// parseNum — 输入清洗（null/undefined/NaN/空串/非数字字符串 → 0）
// ══════════════════════════════════════════════════════════
export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ══════════════════════════════════════════════════════════
// 减值准备③ = 账面余额① × 信用损失率②
// ══════════════════════════════════════════════════════════
export function calcImpairmentProvision(bookBalance: number, creditLossRate: number): number {
  return Math.round(parseNum(bookBalance) * parseNum(creditLossRate) * 100) / 100
}

// ══════════════════════════════════════════════════════════
// 账面价值④ = 账面余额① - 减值准备③
// ══════════════════════════════════════════════════════════
export function calcBookValue(bookBalance: number, impairmentProvision: number): number {
  return Math.round((parseNum(bookBalance) - parseNum(impairmentProvision)) * 100) / 100
}

// ══════════════════════════════════════════════════════════
// 减值准备调整⑥ = ⑤×②A + ①×(②A-②)  【可为负数】
// 当审计师调低信用损失率(②A<②)时，代表减值准备冲回
// ══════════════════════════════════════════════════════════
export function calcImpairmentAdjustment(
  balanceAdj: number, adjRate: number, origBalance: number, origRate: number
): number {
  const ba = parseNum(balanceAdj)
  const ar = parseNum(adjRate)
  const ob = parseNum(origBalance)
  const or_ = parseNum(origRate)
  return Math.round((ba * ar + ob * (ar - or_)) * 100) / 100
}

// ══════════════════════════════════════════════════════════
// 审定账面余额⑦ = ① + ⑤
// ══════════════════════════════════════════════════════════
export function calcAdjustedBalance(origBalance: number, balanceAdj: number): number {
  return Math.round((parseNum(origBalance) + parseNum(balanceAdj)) * 100) / 100
}

// ══════════════════════════════════════════════════════════
// 审定减值准备⑧ = ③ + ⑥
// ══════════════════════════════════════════════════════════
export function calcAdjustedImpairment(origImpairment: number, impairmentAdj: number): number {
  return Math.round((parseNum(origImpairment) + parseNum(impairmentAdj)) * 100) / 100
}

// ══════════════════════════════════════════════════════════
// 审定账面价值⑨ = ⑦ - ⑧
// ══════════════════════════════════════════════════════════
export function calcAdjustedBookValue(adjBalance: number, adjImpairment: number): number {
  return Math.round((parseNum(adjBalance) - parseNum(adjImpairment)) * 100) / 100
}

// ══════════════════════════════════════════════════════════
// 三阶段判定 — hasCreditImpairment优先级最高
// ══════════════════════════════════════════════════════════
export function determineStage(
  hasSignificantIncrease: boolean, hasLowCreditRisk: boolean, hasCreditImpairment: boolean
): 'Stage1' | 'Stage2' | 'Stage3' {
  if (hasCreditImpairment) return 'Stage3'
  if (hasSignificantIncrease) return 'Stage2'
  return 'Stage1'  // 无显著增加 或 具有较低信用风险
}

// ══════════════════════════════════════════════════════════
// 阶段一致性判定
// ══════════════════════════════════════════════════════════
export function isStageConsistent(companyStage: string, auditStage: string): boolean {
  return companyStage === auditStage
}

// ══════════════════════════════════════════════════════════
// 转回有效性 — 转回金额 ≤ 累计计提
// ══════════════════════════════════════════════════════════
export function isReversalValid(reversalAmount: number, accumulatedProvision: number): boolean {
  return parseNum(reversalAmount) <= parseNum(accumulatedProvision)
}

// ══════════════════════════════════════════════════════════
// 借贷平衡判断 — |SUM(debits) - SUM(credits)| < 0.01
// ══════════════════════════════════════════════════════════
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const sumD = debits.reduce((s, v) => s + parseNum(v), 0)
  const sumC = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(sumD - sumC) < 0.01
}

// ══════════════════════════════════════════════════════════
// 借贷差额计算
// ══════════════════════════════════════════════════════════
export function calcDebitCreditDifference(debits: number[], credits: number[]): number {
  const sumD = debits.reduce((s, v) => s + parseNum(v), 0)
  const sumC = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.round((sumD - sumC) * 100) / 100
}

// ══════════════════════════════════════════════════════════
// 凭证正常性判定 — 6项核对全部true时正常
// ══════════════════════════════════════════════════════════
export function isVoucherNormal(checks: boolean[]): boolean {
  return checks.length === 6 && checks.every(c => c === true)
}

// ══════════════════════════════════════════════════════════
// 合计行求和 — 空数组返回0
// ══════════════════════════════════════════════════════════
export function calcSumColumn(values: number[]): number {
  return values.reduce((s, v) => s + parseNum(v), 0)
}
```

### ECL公式链关系图

```
① bookBalance ────────────────────────────────┐
② creditLossRate ─────────┐                   │
                          ├─→ ③ = ①×②         │
                          │                    │
                    ④ = ① - ③                  │
                                               │
⑤ balanceAdj ─────────────┐                   │
②A adjRate ───────────────┼─→ ⑥ = ⑤×②A + ①×(②A-②) ← 可负
                          │
              ⑦ = ① + ⑤   │
              ⑧ = ③ + ⑥   │
              ⑨ = ⑦ - ⑧   └─ 审定链
```

## Integration Design（6大集成接入点）

### 1. 版本链 (useVersionTrail)

```typescript
// GtG4BondInvestmentEcl.vue 主入口
const { autoSnapshot, showVersionTrail } = useVersionTrail(wpId)
async function handleSave() {
  await saveData()
  await autoSnapshot()
}
```

### 2. 抽凭引擎 (G4-13)

```typescript
// G4TabVoucherCheck.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['1501']"
  dialog-mode
  @samples-ready="fillVoucherSamples"
/>
// 抽样结果自动填入借方区/贷方区
```

### 3. 行级OCR (G4-13 Tab1 📎附件列)

```typescript
// G4TabVoucherCheck.vue
async function handleAttachmentUpload(row: VoucherCheckRow, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await http.post('/d4/contract-ocr', formData)
  // ElMessageBox确认弹窗展示识别结果
  await ElMessageBox.confirm(renderOcrPreview(data), 'OCR识别结果', { dangerouslyUseHTMLString: true })
  // 确认后merge填入当前行
  Object.assign(row, mapOcrToVoucherFields(data))
}
```

### 4. 复核对话 (provide/inject)

```typescript
// GtG4BondInvestmentEcl.vue (provide)
const { openReviewDialog } = useReviewDialog(wpId)
provide('openReviewDialog', openReviewDialog)
// 子组件section标题栏右侧按钮 inject使用
```

### 5. 截止自动提取 — ❌ 不集成

本组sheet不涉及截止测试。

### 6. 附注EventBus — ❌ 不集成

本组sheet不涉及附注联动（附注在main组）。

## Performance Strategy

### 虚拟滚动

| 组件 | 行数 | 策略 |
|------|------|------|
| G4-9 三阶段划分 | 61行 | 启用虚拟滚动（>50行阈值） |
| G4-13 凭证检查 | 97行 | 启用虚拟滚动 |
| 参考-减值指引 | 178行 | 启用虚拟滚动 |

### 懒加载

```typescript
// GtG4BondInvestmentEcl.vue
const G4TabStageClassification = defineAsyncComponent(() =>
  import('./g4-bond-investment-ecl/impairment/G4TabStageClassification.vue'))
const G4TabImpairmentCalc = defineAsyncComponent(() =>
  import('./g4-bond-investment-ecl/impairment/G4TabImpairmentCalc.vue'))
const G4TabEclMeasurement = defineAsyncComponent(() =>
  import('./g4-bond-investment-ecl/impairment/G4TabEclMeasurement.vue'))
const G4TabReversalWriteOff = defineAsyncComponent(() =>
  import('./g4-bond-investment-ecl/impairment/G4TabReversalWriteOff.vue'))
const G4TabVoucherCheck = defineAsyncComponent(() =>
  import('./g4-bond-investment-ecl/voucher/G4TabVoucherCheck.vue'))
const G4TabRefImpairmentGuidance = defineAsyncComponent(() =>
  import('./g4-bond-investment-ecl/reference/G4TabRefImpairmentGuidance.vue'))
const G4TabRefPdConversion = defineAsyncComponent(() =>
  import('./g4-bond-investment-ecl/reference/G4TabRefPdConversion.vue'))
```

### 区段Tab切换性能（G4-10/G4-12/G4-13）

- Tab切换不销毁表格实例，仅切换列定义(columns computed)
- 行数据共享同一reactive数组，多区段引用同一rows
- 行选中状态通过 `selectedRowIndex` ref保持（跨Tab同步）
- G4-9 16384列解析：运行时确认有效列数（约12列），合并单元格fallback

## Error Handling

1. **selfLoad失败**：render-config返回404/500时显示错误卡片+重试按钮
2. **公式计算异常**：parseNum兜底（null/undefined/NaN/空串→0），所有公式不抛异常不返回NaN
3. **G4-9 16384列**：合并单元格解析后取有效列，超出预设12列时按实际渲染+warning日志
4. **转回金额校验**：转回金额>累计计提时红色高亮+校验错误信息
5. **借贷不平衡**：实时校验差额，顶部红色显示差额金额
6. **OCR识别失败**：POST失败或返回空结果时ElMessage.error提示，不影响手工填写
7. **抽凭引擎无样本**：dialog关闭时不填入任何数据，保持原状
8. **浮点精度**：金额保留2位小数(Math.round(x*100)/100)
9. **导入格式错误**：后端返回详细错误列表（行号/字段/原因），前端ElMessage展示
10. **参考材料只读保护**：所有编辑操作被阻止，无保存按钮

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 减值准备公式

*For any* bookBalance ∈ ℝ≥0, creditLossRate ∈ [0,1]: `calcImpairmentProvision(bookBalance, creditLossRate)` SHALL equal `round(bookBalance × creditLossRate, 2)`

**Validates: Requirements 8.1, 3.2**

### Property 2: 账面价值公式

*For any* bookBalance ∈ ℝ≥0, impairmentProvision ∈ ℝ≥0 where impairmentProvision ≤ bookBalance: `calcBookValue(bookBalance, impairmentProvision)` SHALL equal `round(bookBalance - impairmentProvision, 2)`

**Validates: Requirements 8.2, 3.3**

### Property 3: 审计调整公式链一致性

*For any* ①,②,⑤,②A ∈ ℝ: `calcAdjustedBookValue(calcAdjustedBalance(①,⑤), calcAdjustedImpairment(calcImpairmentProvision(①,②), calcImpairmentAdjustment(⑤,②A,①,②)))` SHALL equal `round((①+⑤) - (①×② + ⑤×②A + ①×(②A-②)), 2)`（即 ⑨=⑦-⑧ 恒等成立）

**Validates: Requirements 8.3, 8.4, 8.5, 8.6, 3.4, 3.5, 3.6, 3.7**

### Property 4: 减值准备调整公式展开

*For any* balanceAdj, adjRate, origBalance, origRate ∈ ℝ: `calcImpairmentAdjustment(balanceAdj, adjRate, origBalance, origRate)` SHALL equal `round(balanceAdj×adjRate + origBalance×(adjRate-origRate), 2)`（结果可为负数）

**Validates: Requirements 8.3, 3.4**

### Property 5: 三阶段划分确定性与优先级

*For any* (hasSignificantIncrease, hasLowCreditRisk, hasCreditImpairment) ∈ boolean³:
- WHEN hasCreditImpairment=true: `determineStage(...)` SHALL return 'Stage3'（最高优先级）
- WHEN hasSignificantIncrease=true AND !hasCreditImpairment: SHALL return 'Stage2'
- WHEN !hasSignificantIncrease AND !hasCreditImpairment: SHALL return 'Stage1'

**Validates: Requirements 8.7, 2.2**

### Property 6: Stage1必要条件

*For any* inputs: `determineStage(...) === 'Stage1'` → (hasSignificantIncrease=false AND hasCreditImpairment=false)

**Validates: Requirements 8.7, 2.2**

### Property 7: 阶段一致性判定

*For any* s1, s2 ∈ {'Stage1','Stage2','Stage3'}: `isStageConsistent(s1, s2)` ↔ (s1 === s2)

**Validates: Requirements 8.8, 2.3**

### Property 8: 转回有效性

*For any* reversalAmount ∈ ℝ≥0, accumulatedProvision ∈ ℝ≥0: `isReversalValid(reversalAmount, accumulatedProvision)` ↔ (reversalAmount ≤ accumulatedProvision)

**Validates: Requirements 8.9, 5.2**

### Property 9: 借贷平衡恒等

*For any* debits[] ∈ ℝ[], credits[] ∈ ℝ[]: `isDebitCreditBalanced(debits, credits)` ↔ (|SUM(debits)-SUM(credits)| < 0.01)，且 `calcDebitCreditDifference(debits, credits)` SHALL equal `round(SUM(debits)-SUM(credits), 2)`

**Validates: Requirements 8.10, 8.11, 6.6**

### Property 10: 凭证异常判定完备性

*For any* checks ∈ boolean[6]: `isVoucherNormal(checks)` ↔ (checks[0] AND checks[1] AND checks[2] AND checks[3] AND checks[4] AND checks[5])

**Validates: Requirements 8.12, 6.7**

### Property 11: 合计行加法交换律

*For any* values ∈ ℝ[]: `calcSumColumn(values)` === `calcSumColumn(shuffle(values))`（求和与顺序无关）

**Validates: Requirements 8.13**

### Property 12: parseNum健壮性

*For any* input ∈ {null, undefined, '', NaN, '  ', 'abc'}: `parseNum(input)` === 0；*For any* n ∈ ℝ (finite): `parseNum(n)` === n（有效数字透传）

**Validates: Requirements 8.14**

### Property 13: 审定减值准备组合恒等

*For any* ①,②,⑤,②A ∈ ℝ: `calcAdjustedImpairment(calcImpairmentProvision(①,②), calcImpairmentAdjustment(⑤,②A,①,②))` SHALL equal `round(①×② + ⑤×②A + ①×(②A-②), 2)`

**Validates: Requirements 8.5, 8.3**

### Property 14: 审定账面余额=原值+调整

*For any* origBalance ∈ ℝ, balanceAdj ∈ ℝ: `calcAdjustedBalance(origBalance, balanceAdj)` SHALL equal `round(origBalance + balanceAdj, 2)`

**Validates: Requirements 8.4, 3.5**

## Testing Strategy

### PBT配置（fast-check）

- 框架：vitest + fast-check
- 文件：`frontend/src/composables/__tests__/useG4EclFormulaEngine.pbt.spec.ts`
- 每个Property对应一个 `fc.assert(fc.property(...))`
- numRuns: ≥100
- 生成器策略：
  - 金额：`fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })`
  - 利率：`fc.float({ min: 0, max: 1, noNaN: true })`
  - 布尔：`fc.boolean()`
  - 数组：`fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true }), { minLength: 0, maxLength: 50 })`
  - Stage枚举：`fc.constantFrom('Stage1', 'Stage2', 'Stage3')`
- Tag格式：`// Feature: g4-bond-investment-ecl, Property {N}: {title}`

### 单元测试

- G4-9 Stage判定逻辑（边界case：全false/单true/多true）
- G4-10 公式链端到端（具体数值验证）
- G4-12 转回校验（边界case：恰好相等/超过）
- G4-13 凭证异常判定（全通过/单项失败/多项失败）
- parseNum边界值（null/undefined/NaN/Infinity/空串/含空格数字）

### 集成测试

- selfLoad模式：render-config端点返回正确结构
- 导入导出：4张表×3端点 roundtrip
- 抽凭引擎：dialog→样本填入G4-13
- OCR：POST /d4/contract-ocr → 确认 → 字段填入
- 版本链：save触发autoSnapshot

### Playwright E2E

- sheetName分发到7个子组件
- G4-10区段Tab切换+行同步
- G4-13借贷平衡实时校验+异常高亮
- 参考材料只读保护（无法编辑）
- 虚拟滚动在178行参考材料中流畅滚动
