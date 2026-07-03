# Design Document: G11 投资收益底稿专属HTML精美组件

## Overview

G11投资收益专属组件`g11-investment-income`。覆盖1个xlsx源模板/9有效sheet（排除"修订前"）。科目6111投资收益（**损益类/贷方**）。**G循环中投资回报核实的核心科目**，含收益率分析（投入产出比）、多层按投资类型审定（79行）等特色审计内容。

核心架构：
- componentType `g11-investment-income`，主入口 GtG11InvestmentIncome.vue
- **sheetName v-if dispatch模式**：9 sheets用v-if分发（不用el-tabs）
- 子目录分组：core/ + analysis/ + voucher/
- 宽表拆分：G11-5凭证检查(17列→3区段Tab)
- **损益类科目公式**：审定 = 未审 + 调整（取发生额，非余额递推）
- 列为"本期/上期"模式（非期初/期末）：本期(未审|调整|审定) / 上期(未审|调整|审定)
- EventBus联动：publish `substantive:adjudicated`(accountCode='6111') + `disclosure:note-text-updated`
- 特色：收益率分析G11-4（平均余额+收益率+异常波动识别）
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useG11ImportExport, 4张表) + AI(3 section)
- 六大集成：版本链✅ 抽凭✅ 截止✅ 附注EventBus✅ OCR✅ 复核✅

**与G8的关键区别**：
- G8=资产类/借方，有期初/期末余额递推；G11=损益类/贷方，只有本期/上期发生额
- G11无calcDebitBalance/calcEndingBalance，取而代之calcAverageBalance/calcReturnRate
- G11审定表按投资类型79行多层分组（非按被投资单位逐项）
- G11-4收益率分析为本组件最大特色（G8特色为公允价值三层次+CAS22适当性）

## Architecture

### sheetName分发模式 + 子目录组织

GtG11InvestmentIncome.vue 接收 `sheetName` prop，用正则提取编码(G11A/G11-1~G11-5/附注披露(上市)/附注披露(国企)/底稿目录)，`v-if` 分发到对应子组件。

```
sheetName → regex提取编码 → v-if匹配 → defineAsyncComponent子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

9 sheets 子目录分组:
├── core/
│   ├── G11A    实质性程序表（复用a-program-console + 抽凭引擎 + 截止提取）
│   ├── G11-1   审定表（79行×11列，损益类/贷方，本期/上期模式）
│   ├── G11-2   明细分析表（39行×13列，按投资类型分组）
│   ├── G11-3   调整分录汇总（23行×10列，AJE/RJE + 借贷平衡）
│   ├── 附注披露(上市)（34行×5列）
│   ├── 附注披露(国企)（26行×4列）
│   └── 底稿目录
├── analysis/
│   └── G11-4   收益率分析表（31行×10列，平均余额+收益率+异常波动）
└── voucher/
    └── G11-5   凭证检查表（45行×17列→3区段Tab + 抽凭引擎 + 行级OCR）
```

### 高层数据流

```mermaid
graph TD
    TB[trial_balance<br/>科目6111<br/>取发生额] -->|自动取数| G11_1[G11-1 审定表]
    G11_1 -->|EventBus: substantive:adjudicated| NOTE_L[附注披露-上市]
    G11_1 -->|EventBus: substantive:adjudicated| NOTE_S[附注披露-国企]
    NOTE_L -->|EventBus: disclosure:note-text-updated| EXT[附注模块]
    NOTE_S -->|EventBus: disclosure:note-text-updated| EXT
    G11_3[G11-3 调整分录] -->|AJE/RJE汇总回写| G11_1
    G11_2[G11-2 明细分析] -->|按投资类型合计比对| G11_1
    G11_4[G11-4 收益率分析] -->|收益率异常标记| G11_1
    G11A[G11A 程序表] -->|抽凭引擎| VOUCHER[GtVoucherSamplingEngine]
    G11A -->|截止提取| CUTOFF[useCutoffAutoSampling]
    G11_5[G11-5 凭证检查] -->|抽凭引擎| VOUCHER
    G11_5 -->|行级OCR| OCR[/d4/contract-ocr]
    MAIN[GtG11InvestmentIncome] -->|autoSnapshot| VER[useVersionTrail]
    MAIN -->|provide openReviewDialog| CHILDREN[所有子组件]
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtG11InvestmentIncome.vue                     # 主入口 sheetName v-if分发（defineAsyncComponent lazy×9）
├── g11-investment-income/
│   ├── core/
│   │   ├── G11TabProcedure.vue                   # G11A 程序表（复用a-program-console+selfLoad+抽凭+截止）
│   │   ├── G11TabAdjudication.vue                # G11-1 审定表（79行×11列，损益类本期/上期）
│   │   ├── G11TabDetailAnalysis.vue              # G11-2 明细分析表(39行×13列)
│   │   ├── G11TabAdjustment.vue                  # G11-3 调整分录(AJE/RJE+借贷校验)
│   │   ├── G11TabDisclosureListed.vue            # 附注披露(上市)(34行×5列)
│   │   ├── G11TabDisclosureSOE.vue               # 附注披露(国企)(26行×4列)
│   │   └── G11TabDirectory.vue                   # 底稿目录
│   ├── analysis/
│   │   └── G11TabReturnRateAnalysis.vue          # G11-4 收益率分析表(31行×10列)
│   └── voucher/
│       └── G11TabVoucherCheck.vue                # G11-5 凭证检查表(3区段Tab+OCR)
├── composables/
│   ├── useG11FormulaEngine.ts                    # G11公式引擎(6个纯函数)
│   ├── useG11FormData.ts                         # 数据加载/保存/selfLoad/writebackTB
│   ├── useG11ImportExport.ts                     # 导入导出composable(4张表: G11-2/G11-3/G11-4/G11-5)
│   └── useG11DualMode.ts                         # 双模式OO切换+localStorage

backend/app/routers/wp_render_strategies/
├── _g11_investment_income.py                     # render策略+注册RENDERER_DISPATCH
├── _g11_investment_income_service.py             # 业务逻辑(公式验证/TB取数/EventBus)
├── _g11_investment_income_import_export.py       # 导入导出端点(4张表×3=12端点)
└── _g11_investment_income_ai.py                  # AI生成3 section
```

### EventBus事件

| 事件名 | 发布者 | 消费者 | payload |
|--------|--------|--------|---------|
| `substantive:adjudicated` | G11-1审定表 | 附注披露(上市/国企) + trial_balance | `{accountCode:'6111', adjudicatedAmount}` |
| `disclosure:note-text-updated` | 附注披露 | 附注模块 | `{accountCode:'6111', text}` |

### 后端AI Section清单

```
adjudication-analysis / return-rate-conclusion / voucher-conclusion
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtG11InvestmentIncome.vue props
interface G11InvestmentIncomeProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// sheetName正则匹配映射
const SHEET_CODE_MAP: Record<string, string> = {
  'G11A': 'procedure',
  'G11-1': 'adjudication',
  'G11-2': 'detailAnalysis',
  'G11-3': 'adjustment',
  'G11-4': 'returnRateAnalysis',
  'G11-5': 'voucherCheck',
  '附注披露信息（上市公司）': 'disclosureListed',
  '附注披露信息（国企）': 'disclosureSOE',
  '底稿目录': 'directory',
}
```

### G11-1 审定表数据模型（79行×11列，损益类/贷方/本期-上期模式）

```typescript
interface G11AdjudicationData {
  groups: G11AdjudicationGroup[]       // 按投资类型分组
  totals: G11AdjudicationTotals        // 合计行
  trialBalanceAmount: number           // 试算表取数(科目6111,发生额)
  variance: number                     // 差异=审定-试算表
}

interface G11AdjudicationGroup {
  id: string
  groupName: string                    // 投资类型名称
  collapsed: boolean                   // 折叠状态
  rows: G11AdjudicationRow[]
  subtotal: G11AdjudicationTotals
}

// 投资类型分组（79行多层）:
// - 权益法核算的长期股权投资收益
// - 处置长期股权投资产生的投资收益
// - 处置划分为持有待售资产的长投收益
// - 交易性金融资产持有期间/处置收益
// - 债权投资持有期间/处置收益
// - 其他债权投资持有期间/处置/重分类收益
// - 其他权益工具投资股利收益
// - 其他非流动金融资产持有/处置收益

interface G11AdjudicationRow {
  id: string
  item: string                         // 项目名称
  // 本期（损益类：取发生额）
  currentUnadjusted: number            // 本期未审数
  currentAdjustment: number            // 本期账项调整
  currentAdjusted: number              // 公式: 未审 + 账项调整
  // 上期
  priorUnadjusted: number              // 上期未审数
  priorAdjustment: number              // 上期账项调整
  priorAdjusted: number                // 公式: 未审 + 账项调整
  // 变动
  changeAmount: number                 // 公式: 本期审定 - 上期审定
  changeRate: number | null            // 公式: (本期-上期)/|上期|, 上期=0时null
  reasonAnalysis: string               // |变动率|>20%时必填(橙色高亮)
  indexRef: string                     // 索引
}

interface G11AdjudicationTotals {
  currentAdjusted: number
  priorAdjusted: number
  changeAmount: number
  changeRate: number | null
}
```

### G11-2 明细分析表数据模型（39行×13列）

```typescript
interface G11DetailAnalysisRow {
  id: string
  seq: number
  investmentName: string               // 投资项目名称
  investmentType: string               // 投资类型(下拉: 权益法/处置/交易性/债权/其他)
  investeeName: string                 // 被投资单位
  holdingRatio: number                 // 持股比例(小数)
  investmentBalance: number            // 投资余额
  currentIncome: number                // 本期投资收益
  priorIncome: number                  // 上期投资收益
  changeAmount: number                 // 公式: 本期-上期
  changeRate: number | null            // 公式: (本期-上期)/|上期|
  incomeSource: string                 // 收益来源说明(textarea)
  isRelatedParty: boolean              // 是否关联方
  indexRef: string                     // 索引
  remark: string                       // 备注
}
```

### G11-3 调整分录数据模型（23行×10列）

```typescript
interface G11AdjustmentEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'            // 分录类型
  date: string                         // 日期
  summary: string                      // 摘要
  accountCode: string                  // 科目代码
  accountName: string                  // 科目名称
  debitAmount: number                  // 借方金额
  creditAmount: number                 // 贷方金额
  preparedBy: string                   // 编制人
  remark: string                       // 备注
}
```

### G11-4 收益率分析表数据模型（31行×10列）

```typescript
interface G11ReturnRateRow {
  id: string
  seq: number
  investmentName: string               // 投资项目
  investmentType: string               // 投资类型(下拉)
  openingBalance: number               // 期初投资余额
  closingBalance: number               // 期末投资余额
  averageBalance: number               // 公式: (期初+期末)/2
  currentIncome: number                // 本期投资收益
  returnRate: number | null            // 公式: 收益/平均余额×100% (余额=0→null)
  priorReturnRate: number | null       // 上期收益率
  returnRateChange: number | null      // 公式: 本期收益率-上期收益率
  abnormalNote: string                 // 异常说明(textarea, |变动|>5pp时高亮)
}

interface G11ReturnRateData {
  rows: G11ReturnRateRow[]
  conclusion: string                   // 审计结论(textarea, AI辅助)
}
```

### G11-5 凭证检查表数据模型（45行×17列→3区段Tab）

```typescript
interface G11VoucherCheckRow {
  id: string
  seq: number
  // ══ Tab1: 凭证基础(7列) ══
  voucherDate: string                  // 日期
  voucherNo: string                    // 凭证编号
  businessContent: string              // 业务内容
  counterAccount: string               // 对方科目
  debitAmount: number                  // 借方金额
  creditAmount: number                 // 贷方金额
  attachment: string | null            // 📎附件路径(OCR触发)

  // ══ Tab2: 核对内容(5列) ══
  supportingDocDesc: string            // 支持性文件描述
  check1OriginalComplete: boolean      // 核对1-原始凭证完整
  check2Authorization: boolean         // 核对2-授权批准
  check3Accounting: boolean            // 核对3-账务处理正确
  check4IncomeRecognition: boolean     // 核对4-收益确认正确

  // ══ Tab3: 结论(5列) ══
  indexNo: string                      // 索引号(GtIndexChip)
  isAbnormal: boolean                  // 是否异常(Tab2任一✗→自动是)
  abnormalDesc: string                 // 异常说明(textarea)
  riskLevel: 'high' | 'medium' | 'low'  // 风险等级(下拉)
  remark: string                       // 备注
}
```

### 附注数据模型

```typescript
interface G11DisclosureSection {
  id: string
  title: string
  rows?: G11DisclosureRow[]
  textContent?: string                 // 文本区内容（AI辅助）
}

interface G11DisclosureRow {
  id: string
  label: string
  value: string | number
  editable: boolean
}
```

## Data Models

### 存储结构（working_paper.content JSON）

```typescript
interface G11Content {
  // G11-1 审定表
  adjudication: {
    groups: G11AdjudicationGroup[]
    totals: G11AdjudicationTotals
  }
  // G11-2 明细分析
  detailAnalysis: {
    rows: G11DetailAnalysisRow[]
  }
  // G11-3 调整分录
  adjustment: {
    entries: G11AdjustmentEntry[]
  }
  // G11-4 收益率分析
  returnRateAnalysis: G11ReturnRateData
  // G11-5 凭证检查
  voucherCheck: {
    rows: G11VoucherCheckRow[]
  }
  // 附注
  disclosureListed: { sections: G11DisclosureSection[] }
  disclosureSOE: { sections: G11DisclosureSection[] }
}
```

### API接口

```python
# _g11_investment_income.py
# RENDERER_DISPATCH注册
def render_g11_investment_income(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='g11-investment-income'和sheets配置"""

# _g11_investment_income_import_export.py
POST /api/workpapers/{wp_id}/g11/export-template?sheet={code}
POST /api/workpapers/{wp_id}/g11/export-data?sheet={code}
POST /api/workpapers/{wp_id}/g11/import-data?sheet={code}  # multipart/form-data
# sheet codes: G11-2 / G11-3 / G11-4 / G11-5
# 宽表按区段分sheet导出：G11-5(3sheet)

# _g11_investment_income_ai.py
POST /api/workpapers/{wp_id}/g11/ai/{section}
# section: adjudication-analysis / return-rate-conclusion / voucher-conclusion

# _g11_investment_income_service.py
class G11InvestmentIncomeService:
    async def get_trial_balance_data(project_id, year) -> dict
    async def save_adjudication(wp_id, data) -> dict
    async def validate_formulas(data) -> list[ValidationError]
```

### trial_balance 取数

```sql
-- G11-1审定表自动取数（损益类/贷方，取发生额）
SELECT standard_account_code, unadjusted_amount, aje_adjustment, audited_amount
FROM trial_balance
WHERE project_id = :project_id
  AND year = :year
  AND standard_account_code LIKE '6111%'
-- 注意：损益类取发生额字段，非余额递推
```

### 注册四件套

```python
# 1. htmlRendererRegistry (前端)
'g11-investment-income': () => import('./workpaper/GtG11InvestmentIncome.vue')

# 2. wp_code_overrides.json (10条，含排除修订前=9有效+1排除标记)
{
  "G11A-投资收益实质性程序表": "g11-investment-income",
  "G11-1-审定表": "g11-investment-income",
  "G11-2-明细分析表": "g11-investment-income",
  "G11-3-调整分录汇总": "g11-investment-income",
  "G11-4-收益率分析表": "g11-investment-income",
  "G11-5-凭证检查表": "g11-investment-income",
  "G11-附注披露信息（上市公司）": "g11-investment-income",
  "G11-附注披露信息（国企）": "g11-investment-income",
  "G11-底稿目录": "g11-investment-income",
  "G11A-投资收益实质性程序表-修订前": "onlyoffice-sheet"
}

# 3. VALID_COMPONENT_TYPES (后端)
'g11-investment-income'

# 4. RENDERER_DISPATCH (后端)
'g11-investment-income': render_g11_investment_income
```

## Integration Design（6大集成接入点）

### 1. 版本链 (useVersionTrail)

```typescript
// GtG11InvestmentIncome.vue 主入口
const { autoSnapshot, showVersionTrail } = useVersionTrail(wpId)

async function handleSave() {
  await saveData()
  await autoSnapshot()
}
```

### 2. 抽凭引擎 (G11A程序表 + G11-5凭证检查)

```typescript
// G11TabProcedure.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['6111']"
  dialog-mode
  @samples-ready="fillSamples"
/>

// G11TabVoucherCheck.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['6111']"
  dialog-mode
  @samples-ready="fillVoucherRows"
/>
```

### 3. 截止自动提取 (useCutoffAutoSampling)

```typescript
// G11TabProcedure.vue 截止测试步骤
const { fetchCutoffSamples } = useCutoffAutoSampling({
  projectId, accountCode: '6111', days: 5
})
```

### 4. 附注EventBus

```typescript
// G11TabAdjudication.vue (发布者)
watch(reportAmount, (val) => {
  eventBus.publish('substantive:adjudicated', {
    accountCode: '6111',
    adjudicatedAmount: val
  })
})

// G11TabDisclosureListed.vue / G11TabDisclosureSOE.vue (消费者)
eventBus.subscribe('substantive:adjudicated', (payload) => {
  if (payload.accountCode === '6111') refreshData()
})

// 附注文本变更发布
eventBus.publish('disclosure:note-text-updated', {
  accountCode: '6111', text: noteText
})
```

### 5. 行级OCR (G11-5 📎附件列)

```typescript
// G11TabVoucherCheck.vue
async function handleOCR(row: G11VoucherCheckRow, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const result = await http.post('/d4/contract-ocr', formData)
  const confirmed = await ElMessageBox.confirm(
    `识别结果：${result.data.summary}，是否填入？`
  )
  if (confirmed) mergeOCRResult(row, result.data)
}
```

### 6. 复核对话 (provide/inject)

```typescript
// GtG11InvestmentIncome.vue (主入口)
const { openReviewDialog } = useReviewDialog(wpId)
provide('openReviewDialog', openReviewDialog)

// 子组件 (section标题栏右侧按钮)
const openReviewDialog = inject('openReviewDialog')
```

## 宽表区段Tab拆分详细设计

### G11-5 凭证检查表（17列→3区段Tab）

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌──────────────┐ ┌──────────────┐ ┌──────────┐                │
│ │Tab1: 凭证基础(7)│ │Tab2: 核对内容(5)│ │Tab3: 结论(5)│  3区段Tab │
│ └──────────────┘ └──────────────┘ └──────────┘                │
│                                                                 │
│ Tab1: 日期|凭证编号|业务内容|对方科目|借方|贷方|📎附件             │
│       (📎点击→上传→OCR识别→ElMessageBox确认→填入)                │
│                                                                 │
│ Tab2: 文件描述|✓完整|✓授权|✓账务正确|✓收益确认正确                │
│       (任一✗→Tab3"是否异常"自动置"是")                           │
│                                                                 │
│ Tab3: 索引号(GtIndexChip)|是否异常|异常说明|风险等级|备注         │
│                                                                 │
│ 顶部：借贷差额汇总（差额≠0红色）                                 │
│ 行同步：3个Tab间切换保持行索引                                    │
└─────────────────────────────────────────────────────────────────┘
```

### G11-4 收益率分析表（10列，无需拆分）

```
┌─────────────────────────────────────────────────────────────────┐
│ 方法论上下文（琥珀色左边线+浅黄背景）                             │
│ "收益率分析方法：                                                │
│   平均投资余额 = (期初投资余额 + 期末投资余额) / 2               │
│   投资收益率 = 本期投资收益 / 平均投资余额 × 100%                │
│   收益率变动超过5个百分点视为异常波动，需追查原因"                 │
│                                                                 │
│ ═══ 收益率分析 ═══════════════════════ [AI] [复核] ═══════════  │
│ │ 项目 │ 类型 │ 期初 │ 期末 │ 平均余额 │ 收益 │ 收益率 │ 上期 │ 变动 │ 说明 │
│ │ ...  │ 下拉 │      │      │ (公式)   │      │ (公式) │      │ (公式)│ ...  │
│ │                                                                │
│ ⚠️ |收益率变动|>5pp：该行橙色高亮 + "收益率异常波动"提示         │
│                                                                 │
│ 底部：审计结论textarea(AI辅助) + <details>编制提示</details>      │
│ 动态行增删：ElMessageBox.prompt输入投资项目名称                   │
└─────────────────────────────────────────────────────────────────┘
```

## Formula Engine Design (useG11FormulaEngine.ts)

### 6个纯函数

```typescript
/**
 * 安全数值转换：null/undefined/NaN/空字符串/'  '/'abc' → 0; 有效数值→原值
 */
export function parseNum(v: unknown): number

/**
 * 审定数 = 未审数 + 账项调整
 * 损益类公式（本期审定 = 本期未审 + 账项调整）
 */
export function calcAdjustedAmount(unadjusted: number, adjustment: number): number

/**
 * 变动率 = (current - prior) / |prior|
 * prior=0时返回null（避免除零）
 */
export function calcChangeRate(current: number, prior: number): number | null

/**
 * 平均投资余额 = (期初 + 期末) / 2
 * G11-4收益率分析核心公式
 */
export function calcAverageBalance(opening: number, closing: number): number

/**
 * 收益率 = income / avgBalance
 * avgBalance=0时返回null（避免除零）
 * 注意：返回小数形式，前端显示时×100%
 */
export function calcReturnRate(income: number, avgBalance: number): number | null

/**
 * 借贷平衡校验：|SUM(debits) - SUM(credits)| < 0.01
 * G11-3调整分录 + G11-5凭证检查
 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean
```

### 公式引用关系

```
G11-1 审定表（损益类/本期-上期模式）:
  currentAdjusted = calcAdjustedAmount(currentUnadjusted, currentAdjustment)
  priorAdjusted = calcAdjustedAmount(priorUnadjusted, priorAdjustment)
  changeAmount = currentAdjusted - priorAdjusted
  changeRate = calcChangeRate(currentAdjusted, priorAdjusted)

G11-2 明细分析:
  changeAmount = currentIncome - priorIncome
  changeRate = calcChangeRate(currentIncome, priorIncome)

G11-3 调整分录:
  balanced = isDebitCreditBalanced(allDebits, allCredits)

G11-4 收益率分析:
  averageBalance = calcAverageBalance(openingBalance, closingBalance)
  returnRate = calcReturnRate(currentIncome, averageBalance)
  returnRateChange = returnRate - priorReturnRate  (inline)

G11-5 凭证检查:
  balanced = isDebitCreditBalanced(allDebits, allCredits)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 审定数公式

*For any* unadjusted, adjustment ∈ ℝ: `calcAdjustedAmount(unadjusted, adjustment)` === `unadjusted + adjustment`

**Validates: Requirements 3.3, 9.1**

### Property 2: 平均余额公式

*For any* opening, closing ∈ ℝ≥0: `calcAverageBalance(opening, closing)` === `(opening + closing) / 2`

**Validates: Requirements 7.2, 9.1**

### Property 3: 收益率公式

*For any* income ∈ ℝ, avgBalance > 0: `calcReturnRate(income, avgBalance)` === `income / avgBalance`

**Validates: Requirements 7.3, 9.2**

### Property 4: 收益率除零保护

*For any* income ∈ ℝ: `calcReturnRate(income, 0)` === `null`

**Validates: Requirements 7.3, 9.2**

### Property 5: 变动率方向性与除零保护

*For any* current, prior ∈ ℝ where prior ≠ 0: `calcChangeRate(current, prior)` === `(current - prior) / |prior|`;
`calcChangeRate(any, 0)` === `null`

**Validates: Requirements 3.5, 5.3, 9.1**

### Property 6: 借贷平衡恒等

*For any* debits[], credits[] ∈ ℝ[]: `isDebitCreditBalanced(debits, credits)` === `(|SUM(debits) - SUM(credits)| < 0.01)`

**Validates: Requirements 6.1, 9.1**

### Property 7: parseNum健壮性

*For any* input ∈ {null, undefined, '', NaN, '  ', 'abc'}: `parseNum(input)` === 0;
*For any* n ∈ ℝ (finite number): `parseNum(n)` === n

**Validates: Requirements 9.1**

## Error Handling

| 场景 | 处理策略 |
|------|---------|
| render-config 加载失败 | selfLoad重试1次 → 失败显示"加载失败"占位 + 重试按钮 |
| trial_balance 取数无数据 | 审定表显示0值 + 橙色提示"未找到科目6111数据" |
| 公式计算溢出/NaN | parseNum兜底→0，公式列显示"—" |
| 平均余额为0导致收益率null | 收益率列显示"N/A"，tooltip提示"平均余额为零，无法计算收益率" |
| 导入Excel格式不匹配 | 后端返回422 + 具体列错误信息 → 前端ElMessage.error |
| EventBus消息丢失 | 附注组件mounted时主动拉取最新审定数（非纯被动监听） |
| 保存时网络异常 | 自动重试3次(指数退避) → 失败后localStorage暂存 + 恢复提示 |
| sheetName无法识别 | fallback到OnlyOffice渲染（确保不白屏） |
| G11-5 Tab2核对全✗异常 | Tab3 isAbnormal自动true + 橙色高亮 |
| OCR识别失败 | ElMessage.warning提示 + 允许手动填入 |
| 收益率变动>5pp | 橙色高亮行 + tooltip"收益率异常波动，请说明原因" |

## Testing Strategy

### 测试分层

| 层 | 工具 | 范围 | 数量估计 |
|----|------|------|---------|
| PBT(前端) | vitest + fast-check | 6个公式函数×7属性 | ~10 test cases |
| PBT(后端) | pytest + hypothesis | 公式验证 | ~7 test cases |
| 单元测试(前端) | vitest | composable逻辑/数据转换/异常自动检测/变动率高亮 | ~14 test cases |
| 单元测试(后端) | pytest | service/renderer/import-export | ~8 test cases |
| 集成测试 | pytest | API端点(12导入导出+3AI+render) | ~6 test cases |
| E2E | Playwright | 关键用户路径(审定+收益率分析+凭证检查) | ~3 scenarios |

### PBT配置

- 前端：fast-check，`numRuns: 100`
- 后端：hypothesis，`max_examples=5`
- 每个PBT测试注释标注对应属性编号
- Tag格式：`Feature: g11-investment-income, Property {N}: {描述}`

### 关键测试路径

1. **审定表完整流程**：TB取数(6111发生额) → 损益类公式(未审+调整=审定) → 变动率计算 → |变动率|>20%高亮 → EventBus发布 → 附注刷新
2. **收益率分析流程**：填入期初期末余额 → 平均余额自动算 → 填入收益 → 收益率自动算 → |变动|>5pp异常标记 → AI辅助生成结论
3. **凭证检查流程**：抽凭引擎→样本填入 → Tab2核对4项 → 任一✗自动异常 → OCR识别→确认填入

### PBT测试文件

```
audit-platform/frontend/src/components/workpaper/composables/__tests__/
└── useG11FormulaEngine.spec.ts         # 7个PBT属性 + fast-check

backend/tests/
└── test_g11_investment_income_pbt.py   # 后端PBT验证(hypothesis)
```

### 单元测试重点

- **变动率>20%高亮逻辑**：验证|changeRate|>0.2时触发橙色+必填
- **收益率变动>5pp标记逻辑**：验证|returnRateChange|>0.05时橙色高亮行
- **G11-5核对异常自动检测**：验证check1-4任一false时isAbnormal自动true
- **损益类审定表本期/上期对称**：验证本期和上期使用相同公式结构
- **导入导出G11-5宽表分sheet**：验证3区段Tab对应3sheet导出
