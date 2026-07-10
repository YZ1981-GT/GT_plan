# Design Document: G6 其他债权投资底稿(ECL组)专属HTML精美组件

## Overview

G6其他债权投资(ECL组)专属组件`g6-other-bond-investment-ecl`。覆盖1个xlsx源模板中的5个sheet（ECL减值+凭证检查组）。科目1503其他债权投资（借方/资产类，FVOCI类金融资产）。**CAS22/CAS24预期信用损失计量核心逻辑**：三阶段划分(G6-11)→减值测算(G6-12)→ECL计量测试(G6-13)→转回核销(G6-14)→凭证检查(G6-15)。

核心架构：
- componentType `g6-other-bond-investment-ecl`，主入口 GtG6OtherBondInvestmentEcl.vue
- **sheetName v-if dispatch模式**：5 sheets用v-if分发（不用el-tabs）
- 子目录分组：impairment/ + voucher/
- 宽表拆分：G6-12(22列→2区段Tab) / G6-15(22列→3区段Tab)
- 公式引擎：useG6EclFormulaEngine.ts（8纯函数，ECL公式链核心⑥=⑤×②A+①×(②A-②)可负）
- 特色：**列式转置**(G6-11,同G4-9/G5-9) + ECL公式链自动计算 + 凭证OCR识别 + 借贷平衡校验
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useG6EclImportExport, 3张表) + AI(4 section)
- 五大集成：版本链✅ 抽凭✅(G6-15) OCR✅(G6-15) 复核✅ 截止❌ 附注EventBus❌
- 虚拟滚动：G6-11(61行) / G6-15(100行)

**三组拆分定位**：
| 组 | spec | 核心职责 |
|----|------|----------|
| main | g6-other-bond-investment-main | 程序表+审定表+附注+明细表+调整+利息测算 |
| SPPI | g6-other-bond-investment-sppi | SPPI合同现金流+业务模式+利息测算+盘点 |
| **ECL(本spec)** | g6-other-bond-investment-ecl | 三阶段划分+减值测算+ECL计量+转回核销+凭证检查 |

**G6 vs G4/G5 ECL差异**：
- G6减值按**摊余成本口径**计提（非公允价值口径），但账面价值通过OCI调整
- G6-12含OCI影响列（Tab1新增）和OCI调整列（Tab2新增）
- G6-13为49行×10列问卷（含PD/LGD/EAD/折现率/前瞻性信息5大section）
- G6-14为42行×8列（比G4-12更简洁）

## Architecture

### sheetName分发模式 + 子目录组织

GtG6OtherBondInvestmentEcl.vue 接收 `sheetName` prop，用正则提取编码，`v-if` 分发到对应子组件。

```
sheetName → regex提取编码 → v-if匹配 → defineAsyncComponent子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

5 sheets 子目录分组:
├── impairment/
│   ├── G6-11  三阶段划分（列式转置结构，投资项目为列→行式交互视图）
│   ├── G6-12  减值准备测算表（22列→2区段Tab，ECL公式链）
│   ├── G6-13  ECL计量测试（49行×10列，PD/LGD/EAD问卷）
│   └── G6-14  转回核销检查表（42行×8列）
└── voucher/
    └── G6-15  凭证检查表（22列→3区段Tab + 行级OCR + 抽凭引擎）
```

### 高层数据流

```mermaid
graph TD
    G6_11[G6-11 三阶段划分] -->|Stage分类结果| G6_12[G6-12 减值测算]
    G6_12 -->|减值准备审定| MAIN[g6-other-bond-investment-main<br/>审定表]
    G6_13[G6-13 ECL计量测试] -->|方法评价参考| G6_12
    G6_14[G6-14 转回核销] -->|转回/核销金额| G6_12
    G6_15[G6-15 凭证检查] -->|抽凭引擎| VOUCHER[GtVoucherSamplingEngine]
    G6_15 -->|OCR识别| OCR[/d4/contract-ocr]
    ECL_MAIN[GtG6OtherBondInvestmentEcl] -->|autoSnapshot| VER[useVersionTrail]
    ECL_MAIN -->|provide openReviewDialog| CHILDREN[所有子组件]
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtG6OtherBondInvestmentEcl.vue                 # 主入口 sheetName v-if分发
├── g6-other-bond-investment-ecl/
│   ├── impairment/
│   │   ├── G6TabStageClassification.vue           # G6-11 三阶段划分（列式转置+61行虚拟滚动）
│   │   ├── G6TabImpairmentCalc.vue                # G6-12 减值测算（2区段Tab+ECL公式链）
│   │   ├── G6TabEclMeasurement.vue                # G6-13 ECL计量测试（5 section问卷）
│   │   └── G6TabReversalWriteOff.vue              # G6-14 转回核销检查
│   └── voucher/
│       └── G6TabVoucherCheck.vue                  # G6-15 凭证检查（3区段Tab+OCR）
├── composables/
│   ├── useG6EclFormulaEngine.ts                   # 公式引擎(8纯函数+parseNum)
│   ├── useG6EclFormData.ts                        # 数据加载/保存/selfLoad
│   ├── useG6EclStageClassification.ts             # G6-11逻辑(列式转置+Stage判定+一致性)
│   ├── useG6EclImpairmentCalc.ts                  # G6-12逻辑(ECL公式链+Stage分组)
│   ├── useG6EclVoucherCheck.ts                    # G6-15逻辑(OCR+异常判定+借贷校验)
│   ├── useG6EclImportExport.ts                    # 导入导出composable(3张表)
│   └── useG6EclDualMode.ts                        # 双模式OO切换+localStorage

backend/app/routers/wp_render_strategies/
├── _g6_other_bond_investment_ecl.py               # render策略+RENDERER_DISPATCH
├── _g6_other_bond_investment_ecl_import_export.py # 导入导出端点(3张表)
└── _g6_other_bond_investment_ecl_ai.py            # AI生成4 section
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtG6OtherBondInvestmentEcl.vue props
interface G6OtherBondInvestmentEclProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// sheetName正则匹配映射
const SHEET_CODE_MAP: Record<string, string> = {
  'G6-11': 'stageClassification',
  'G6-12': 'impairmentCalc',
  'G6-13': 'eclMeasurement',
  'G6-14': 'reversalWriteOff',
  'G6-15': 'voucherCheck',
}
```

### G6-11 三阶段划分数据模型（列式转置→行式视图）

```typescript
// ═══ 列式转置解析 ═══
// 源模板：61行×16384列（合并单元格），投资项目作为列头
// 前端：转换为行式视图，每个投资项目一行

interface StageClassificationRow {
  id: string
  seq: number
  investProject: string                         // 投资项目名称（原始列头）
  significantIncrease: string                   // 信用风险是否显著增加(综合判断)
  lowCreditRisk: boolean                        // 是否具有较低信用风险
  creditImpaired: boolean                       // 是否已发生信用减值
  companyStage: 'Stage1' | 'Stage2' | 'Stage3'  // 企业划分阶段(下拉)
  auditStage: 'Stage1' | 'Stage2' | 'Stage3'    // 审计判断阶段(下拉)
  isConsistent: boolean                         // 公式: companyStage === auditStage
  discrepancyNote: string                       // 差异说明(不一致时强制)
  indexRef: string                              // 索引
}

interface StageClassificationData {
  rows: StageClassificationRow[]
  summary: {
    stage1Count: number
    stage2Count: number
    stage3Count: number
    inconsistentCount: number
  }
  conclusion: string                            // 审计结论
}

// 列式→行式转换函数接口
interface TransposedColumnData {
  headers: string[]        // 源模板列头（投资项目名称）
  checkItems: string[][]   // 各检查项数据（按行→按列取值）
}

function transposeToRows(raw: TransposedColumnData): StageClassificationRow[]
```

### G6-12 减值准备测算表数据模型（22列→2区段Tab）

```typescript
interface ImpairmentCalcRow {
  id: string
  seq: number
  investProject: string                         // 投资项目
  stageGroup: 'Stage1' | 'Stage2' | 'Stage3'   // 所属Stage分组

  // ══ Tab1: 未审+调整(12列) ══
  amortizedCost: number                         // ①摊余成本余额
  fairValue: number                             // 公允价值(参考)
  creditLossRate: number                        // ②预期信用损失率
  impairmentProvision: number                   // ③坏账准备 = ①×② (公式)
  bookValue: number                             // ④账面价值 = ①-③ (公式)
  balanceAdjustment: number                     // ⑤余额调整
  adjustedCreditLossRate: number                // ②A调整后损失率
  impairmentAdjustment: number                  // ⑥坏账调整 = ⑤×②A+①×(②A-②) (公式,可负)
  stage: 'Stage1' | 'Stage2' | 'Stage3'         // 阶段
  ociImpact: number                             // OCI影响
  indexRef: string                              // 索引

  // ══ Tab2: 审定数(10列) ══
  adjBalance: number                            // ⑦审定余额 = ①+⑤ (公式)
  adjImpairment: number                         // ⑧审定坏账 = ③+⑥ (公式)
  adjBookValue: number                          // ⑨审定账面价值 = ⑦-⑧ (公式)
  adjFairValue: number                          // 审定公允价值
  priorImpairment: number                       // 上年坏账
  currentProvision: number                      // 本年计提 = ⑧-上年坏账 (公式)
  currentReversal: number                       // 本年转回
  ociAdjustment: number                         // OCI调整
  differenceNote: string                        // 差异说明
}

interface ImpairmentCalcData {
  rows: ImpairmentCalcRow[]
  conclusion: string
}

// Stage分组显示+小计
interface ImpairmentCalcGrouped {
  stage1: { rows: ImpairmentCalcRow[], subtotal: GroupSubtotal }
  stage2: { rows: ImpairmentCalcRow[], subtotal: GroupSubtotal }
  stage3: { rows: ImpairmentCalcRow[], subtotal: GroupSubtotal }
  grandTotal: GroupSubtotal
}

interface GroupSubtotal {
  amortizedCost: number         // Σ①
  impairmentProvision: number   // Σ③
  bookValue: number             // Σ④
  balanceAdjustment: number     // Σ⑤
  impairmentAdjustment: number  // Σ⑥
  adjBalance: number            // Σ⑦
  adjImpairment: number         // Σ⑧
  adjBookValue: number          // Σ⑨
}
```

### G6-13 ECL计量测试数据模型

```typescript
interface EclMeasurementData {
  // (一) PD（违约概率）
  pdSection: EclCheckRow[]
  // (二) LGD（违约损失率）
  lgdSection: EclCheckRow[]
  // (三) EAD（违约风险暴露）
  eadSection: EclCheckRow[]
  // (四) 折现率
  discountRateSection: EclCheckRow[]
  // (五) 前瞻性信息
  forwardLookingSection: EclCheckRow[]
  // 方法论上下文
  methodologyContext: string
}

interface EclCheckRow {
  id: string
  seq: number
  checkArea: string                              // 检查区域
  checkItem: string                              // 检查项目
  auditRequirement: string                       // 审计要求(方法论上下文)
  companyParam: string                           // 企业参数(textarea)
  isReasonable: '合理' | '基本合理' | '不合理' | '' // 是否合理(下拉)
  auditConclusion: string                        // 审计结论(textarea)
  riskLevel: '高' | '中' | '低' | ''             // 风险等级
  indexRef: string                               // 索引
  remark: string                                 // 备注
}
```

### G6-14 转回核销检查表数据模型

```typescript
interface ReversalWriteOffRow {
  id: string
  seq: number
  investProject: string                          // 投资项目
  type: '转回' | '核销' | '收回'                  // 转回/核销类型(下拉)
  amount: number                                 // 金额
  reason: string                                 // 原因(textarea)
  approvalProcedure: string                      // 审批程序
  reasonConclusion: '合理' | '基本合理' | '不合理' // 合理性结论(下拉)
  indexRef: string                               // 索引
}

interface ReversalWriteOffData {
  rows: ReversalWriteOffRow[]
  conclusion: string
}
```

### G6-15 凭证检查表数据模型（22列→3区段Tab）

```typescript
interface VoucherCheckRow {
  id: string
  seq: number

  // ══ Tab1: 凭证基础(8列) ══
  date: string                                   // 日期
  voucherNo: string                              // 凭证号
  businessContent: string                        // 业务内容
  counterAccount: string                         // 对方科目
  detailAccount: string                          // 明细
  debitAmount: number                            // 借方
  creditAmount: number                           // 贷方
  attachment: string | null                      // 📎附件(OCR)

  // ══ Tab2: 核对内容(8列) ══
  supportingDoc: string                          // 支持性文件
  checkOriginal: boolean                         // 核对1-原始凭证
  checkAuthorized: boolean                       // 核对2-授权
  checkAccounting: boolean                       // 核对3-账务
  checkAmount: boolean                           // 核对4-金额
  checkClassification: boolean                   // 核对5-分类
  checkImpairment: boolean                       // 核对6-减值
  checkInterest: boolean                         // 核对7-利息

  // ══ Tab3: 结论(6列) ══
  indexRef: string                               // 索引
  isAbnormal: boolean                            // 是否异常(任一核对✗→自动)
  abnormalNote: string                           // 异常说明
  riskLevel: '高' | '中' | '低' | ''             // 风险等级
  suggestion: string                             // 处理建议
  remark: string                                 // 备注
}

interface VoucherCheckData {
  rows: VoucherCheckRow[]
  debitTotal: number                             // 借方合计
  creditTotal: number                            // 贷方合计
  difference: number                             // 差额
  isBalanced: boolean                            // |差额| < 0.01
  conclusion: string
}
```

### 后端接口

```python
# _g6_other_bond_investment_ecl.py
def render_g6_other_bond_investment_ecl(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='g6-other-bond-investment-ecl'和sheets配置"""

# _g6_other_bond_investment_ecl_import_export.py
POST /api/workpapers/{wp_id}/g6-ecl/export-template?sheet={code}
POST /api/workpapers/{wp_id}/g6-ecl/export-data?sheet={code}
POST /api/workpapers/{wp_id}/g6-ecl/import-data?sheet={code}  # multipart/form-data
# sheet codes: G6-12 / G6-14 / G6-15
# G6-12按2区段分sheet导出，G6-15按3区段分sheet导出

# _g6_other_bond_investment_ecl_ai.py
POST /api/workpapers/{wp_id}/g6-ecl/ai/{section}
# section: stage-conclusion / impairment-conclusion /
#           ecl-measurement-conclusion / voucher-conclusion
```

### 注册四件套

```python
# 1. htmlRendererRegistry (前端)
'g6-other-bond-investment-ecl': () => import('./workpaper/GtG6OtherBondInvestmentEcl.vue')

# 2. wp_code_overrides.json (5条)
{
  "G6-11-其他债权投资三阶段划分": "g6-other-bond-investment-ecl",
  "G6-12-其他债权投资减值准备测算表": "g6-other-bond-investment-ecl",
  "G6-13-预期信用损失的计量测试": "g6-other-bond-investment-ecl",
  "G6-14-减值准备转回核销检查表": "g6-other-bond-investment-ecl",
  "G6-15-凭证检查表": "g6-other-bond-investment-ecl"
}

# 3. VALID_COMPONENT_TYPES (后端)
'g6-other-bond-investment-ecl'

# 4. RENDERER_DISPATCH (后端)
'g6-other-bond-investment-ecl': render_g6_other_bond_investment_ecl
```

## Data Models

### 存储结构（working_paper.content JSON）

```typescript
interface G6EclContent {
  stageClassification: StageClassificationData   // G6-11
  impairmentCalc: ImpairmentCalcData             // G6-12
  eclMeasurement: EclMeasurementData             // G6-13
  reversalWriteOff: ReversalWriteOffData         // G6-14
  voucherCheck: VoucherCheckData                 // G6-15
}
```

### G6-11 列式转置解析策略

```typescript
// 源模板：61行×16384列（合并单元格）
// 实际有效：~12列有数据（每个投资项目一列）
// 智能解析步骤：
// 1. 扫描第1行（列头行），跳过合并单元格，提取非空列头
// 2. 仅保留有效列（有列头且至少一个数据行非空）
// 3. 对每个有效列（投资项目），提取对应行数据
// 4. 将列式数据转为行式StageClassificationRow[]

interface ColumnParseResult {
  validColumnCount: number           // 实际有效列数
  projects: string[]                 // 投资项目名称列表
  rawData: Map<string, string[]>     // 项目名→各检查项值
}
```

### ECL公式链关系图

```
① amortizedCost ──────────────────────────────┐
② creditLossRate ─────────┐                   │
                          ├─→ ③ = ①×②         │
                          │                    │
                    ④ = ① - ③                  │
                                               │
⑤ balanceAdj ─────────────┐                   │
②A adjRate ───────────────┼─→ ⑥ = ⑤×②A + ①×(②A-②) ← 可负（冲回）
                          │
              ⑦ = ① + ⑤   │
              ⑧ = ③ + ⑥   │
              ⑨ = ⑦ - ⑧   └─ 审定链

注：G6按摊余成本口径（①=摊余成本），非公允价值口径
```

## Formula Engine Design

### useG6EclFormulaEngine.ts — 8个纯函数 + parseNum

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
// 坏账准备③ = 摊余成本余额① × 预期信用损失率②
// ══════════════════════════════════════════════════════════
export function calcImpairmentProvision(amortizedCost: number, creditLossRate: number): number {
  return Math.round(parseNum(amortizedCost) * parseNum(creditLossRate) * 100) / 100
}

// ══════════════════════════════════════════════════════════
// 坏账调整⑥ = ⑤×②A + ①×(②A-②)  【可为负数=冲回】
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
// 审定余额⑦ = ① + ⑤
// ══════════════════════════════════════════════════════════
export function calcAdjustedBalance(origBalance: number, balanceAdj: number): number {
  return Math.round((parseNum(origBalance) + parseNum(balanceAdj)) * 100) / 100
}

// ══════════════════════════════════════════════════════════
// 审定坏账⑧ = ③ + ⑥
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
// 三阶段判定 — hasCreditImpairment优先级最高(Stage3)
// ══════════════════════════════════════════════════════════
export function determineStage(
  hasSignificantIncrease: boolean, hasLowCreditRisk: boolean, hasCreditImpairment: boolean
): 'Stage1' | 'Stage2' | 'Stage3' {
  if (hasCreditImpairment) return 'Stage3'
  if (hasSignificantIncrease) return 'Stage2'
  return 'Stage1'
}

// ══════════════════════════════════════════════════════════
// 借贷平衡判断 — |SUM(debits) - SUM(credits)| < 0.01
// ══════════════════════════════════════════════════════════
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean {
  const sumD = debits.reduce((s, v) => s + parseNum(v), 0)
  const sumC = credits.reduce((s, v) => s + parseNum(v), 0)
  return Math.abs(sumD - sumC) < 0.01
}
```

## Integration Design（五大集成接入点）

### 1. 版本链 (useVersionTrail)

```typescript
// GtG6OtherBondInvestmentEcl.vue 主入口
const { autoSnapshot, showVersionTrail } = useVersionTrail(wpId)
async function handleSave() {
  await saveData()
  await autoSnapshot()
}
```

### 2. 抽凭引擎 (G6-15)

```typescript
// G6TabVoucherCheck.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['1503']"
  dialog-mode
  @samples-ready="fillVoucherSamples"
/>
// 抽样结果自动填入Tab1凭证基础列
```

### 3. 行级OCR (G6-15 Tab1 📎附件列)

```typescript
// G6TabVoucherCheck.vue
async function handleAttachmentUpload(row: VoucherCheckRow, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await http.post('/d4/contract-ocr', formData)
  await ElMessageBox.confirm(renderOcrPreview(data), 'OCR识别结果', {
    dangerouslyUseHTMLString: true
  })
  Object.assign(row, mapOcrToVoucherFields(data))
}
```

### 4. 复核对话 (provide/inject)

```typescript
// GtG6OtherBondInvestmentEcl.vue (provide)
const { openReviewDialog } = useReviewDialog(wpId)
provide('openReviewDialog', openReviewDialog)
// 子组件section标题栏右侧按钮 inject使用
```

### 5. 截止自动提取 — ❌ 不集成

本组sheet不涉及截止测试（截止在SPPI组/main组）。

### 6. 附注EventBus — ❌ 不集成

本组sheet不涉及附注联动（附注在main组）。

## Performance Strategy

### 虚拟滚动

| 组件 | 行数 | 策略 |
|------|------|------|
| G6-11 三阶段划分 | 61行 | 启用虚拟滚动（>50行阈值） |
| G6-15 凭证检查 | 100行 | 启用虚拟滚动 |

### 懒加载

```typescript
// GtG6OtherBondInvestmentEcl.vue
const G6TabStageClassification = defineAsyncComponent(() =>
  import('./g6-other-bond-investment-ecl/impairment/G6TabStageClassification.vue'))
const G6TabImpairmentCalc = defineAsyncComponent(() =>
  import('./g6-other-bond-investment-ecl/impairment/G6TabImpairmentCalc.vue'))
const G6TabEclMeasurement = defineAsyncComponent(() =>
  import('./g6-other-bond-investment-ecl/impairment/G6TabEclMeasurement.vue'))
const G6TabReversalWriteOff = defineAsyncComponent(() =>
  import('./g6-other-bond-investment-ecl/impairment/G6TabReversalWriteOff.vue'))
const G6TabVoucherCheck = defineAsyncComponent(() =>
  import('./g6-other-bond-investment-ecl/voucher/G6TabVoucherCheck.vue'))
```

### 区段Tab切换性能（G6-12/G6-15）

- Tab切换不销毁表格实例，仅切换列定义(columns computed)
- 行数据共享同一reactive数组，多区段引用同一rows
- 行选中状态通过 `selectedRowIndex` ref保持（跨Tab同步）
- G6-11 16384列解析：运行时智能扫描有效列（约12列），合并单元格fallback

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: ECL公式链一致性

*For any* ①(amortizedCost) ∈ ℝ, ②(creditLossRate) ∈ ℝ, ⑤(balanceAdjustment) ∈ ℝ, ②A(adjustedRate) ∈ ℝ:
`calcAdjustedBookValue(calcAdjustedBalance(①,⑤), calcAdjustedImpairment(calcImpairmentProvision(①,②), calcImpairmentAdjustment(⑤,②A,①,②)))` SHALL equal `round((①+⑤) - (①×② + ⑤×②A + ①×(②A-②)), 2)` — 即 ⑨=⑦-⑧ 恒等成立。

**Validates: Requirements 3.2, 6.1**

### Property 2: 三阶段确定性与Stage3优先级

*For any* (hasSignificantIncrease, hasLowCreditRisk, hasCreditImpairment) ∈ boolean³:
- `determineStage(...)` 输出 SHALL ∈ {'Stage1', 'Stage2', 'Stage3'}（确定性）
- WHEN hasCreditImpairment=true: SHALL return 'Stage3'（最高优先级，无论其他参数）
- WHEN hasSignificantIncrease=true AND !hasCreditImpairment: SHALL return 'Stage2'
- WHEN !hasSignificantIncrease AND !hasCreditImpairment: SHALL return 'Stage1'

**Validates: Requirements 2.3, 6.1**

### Property 3: 坏账调整展开式

*For any* balanceAdj ∈ ℝ, adjRate ∈ ℝ, origBalance ∈ ℝ, origRate ∈ ℝ:
`calcImpairmentAdjustment(balanceAdj, adjRate, origBalance, origRate)` SHALL equal `round(balanceAdj×adjRate + origBalance×(adjRate-origRate), 2)`（结果可为负数=冲回）

**Validates: Requirements 3.2, 6.1**

### Property 4: 借贷平衡

*For any* debits[] ∈ ℝ[], credits[] ∈ ℝ[]:
`isDebitCreditBalanced(debits, credits)` ↔ (|SUM(debits)-SUM(credits)| < 0.01)

**Validates: Requirements 5.3, 6.1**

### Property 5: parseNum健壮性

*For any* input ∈ {null, undefined, '', NaN, '  ', 'abc', Infinity}: `parseNum(input)` === 0
*For any* n ∈ ℝ (finite number): `parseNum(n)` === n（有效数字透传不变）

**Validates: Requirements 6.1**

### Property 6: 列式转置数据完整性

*For any* 有效列集合 columns[] 其中每列有列头且至少一行非空数据:
`transposeToRows(columns)` 输出行数 SHALL equal 有效列数，且每行的 `investProject` 字段对应原始列头，所有非空数据值在转换后完整保留。

**Validates: Requirements 2.1, 2.6**

## Error Handling

1. **selfLoad失败**：render-config返回404/500时显示错误卡片+重试按钮
2. **公式计算异常**：parseNum兜底（null/undefined/NaN/空串→0），所有公式不抛异常不返回NaN
3. **G6-11 16384列解析**：合并单元格解析后取有效列，超出预设列数时按实际渲染+warning日志
4. **Stage不一致校验**：企业与审计Stage不同时红色高亮+强制差异说明（阻止保存）
5. **借贷不平衡**：G6-15实时校验差额，顶部红色banner显示差额金额
6. **OCR识别失败**：POST失败或返回空结果时ElMessage.error提示，不影响手工填写
7. **抽凭引擎无样本**：dialog关闭时不填入任何数据，保持原状
8. **浮点精度**：金额保留2位小数(Math.round(x*100)/100)
9. **导入格式错误**：后端返回详细错误列表（行号/字段/原因），前端ElMessage展示
10. **OCI金额异常**：G6-12 OCI列超出合理范围时琥珀色warning提示

## Testing Strategy

### PBT配置（fast-check）

- 框架：vitest + fast-check
- 文件：`frontend/src/composables/__tests__/useG6EclFormulaEngine.pbt.spec.ts`
- 每个Property对应一个 `fc.assert(fc.property(...))`
- numRuns: ≥100
- 生成器策略：
  - 金额：`fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })`
  - 利率：`fc.float({ min: -1, max: 1, noNaN: true })`（可负=冲回场景）
  - 布尔：`fc.boolean()`
  - 数组：`fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true }), { minLength: 0, maxLength: 50 })`
  - Stage枚举：`fc.constantFrom('Stage1', 'Stage2', 'Stage3')`
  - 列数据：`fc.array(fc.record({ header: fc.string({ minLength: 1 }), values: fc.array(fc.string()) }), { minLength: 1, maxLength: 20 })`
- Tag格式：`// Feature: g6-other-bond-investment-ecl, Property {N}: {title}`

### 单元测试

- G6-11 列式转置解析（空列/合并单元格/全空列过滤）
- G6-12 ECL公式链端到端（具体数值：如①=1000万,②=1%,⑤=200万,②A=2%）
- G6-13 section结构完整性（5个section均存在）
- G6-14 转回类型校验（仅允许转回/核销/收回）
- G6-15 凭证异常自动判定（7项核对全通过=正常，任一✗=异常）
- parseNum边界值（null/undefined/NaN/Infinity/空串/含空格数字）

### 集成测试

- selfLoad模式：render-config端点返回正确结构
- 导入导出：3张表×3端点 roundtrip
- 抽凭引擎：dialog→样本填入G6-15 Tab1
- OCR：POST /d4/contract-ocr → 确认 → 字段填入
- 版本链：save触发autoSnapshot
- AI接口：4个section各返回合理文本

### Playwright E2E

- sheetName分发到5个子组件
- G6-11列式转置渲染+Stage不一致红色高亮
- G6-12区段Tab切换+行同步+公式自动计算
- G6-13问卷填写+AI辅助按钮
- G6-15借贷平衡实时校验+异常高亮+OCR上传
- 虚拟滚动在100行凭证检查中流畅滚动
- 双模式切换（HTML↔OnlyOffice）
