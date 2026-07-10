# Design Document: G9 其他非流动金融资产底稿专属HTML精美组件

## Overview

G9其他非流动金融资产专属组件`g9-other-noncurrent-financial`。覆盖1个xlsx源模板/10有效sheet。科目1504其他非流动金融资产（借方/资产类）。**G循环中第三层次公允价值计量审计最突出的科目**，包含混合计量属性分组（FVTPL/FVOCI/摊余成本）、公允价值Level1-3层次测试、第三层次调节表（L3 Reconciliation）等特色审计内容。

核心架构：
- componentType `g9-other-noncurrent-financial`，主入口 GtG9OtherNoncurrentFinancial.vue
- **sheetName v-if dispatch模式**：10 sheets用v-if分发（不用el-tabs）
- 子目录分组：core/ + valuation/ + voucher/
- 宽表拆分：G9-2(28列→3区段Tab) / G9-4(21列→2区段Tab) / G9-6(20列→3区段Tab)
- 借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额
- 混合计量：同一科目按业务模式分别以FVTPL/FVOCI/摊余成本计量
- EventBus联动：publish `substantive:adjudicated`(accountCode='1504') + `disclosure:note-text-updated`
- 特色：**74行多层审定表**(按计量属性分组) + **第三层次调节表G9-5**(10因子变动分析) + **28列超宽明细表**(3区段Tab)
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useG9ImportExport, 5张表) + AI(4 section)
- 六大集成：版本链✅ 抽凭✅ 截止✅ 附注EventBus✅ OCR✅ 复核✅

**区别于G8的关键差异**：
1. G8为单一FVOCI计量 → G9为混合计量(FVTPL+FVOCI+摊余成本)，审定表按分组展示
2. G8审定表29行 → G9审定表74行(需虚拟滚动)
3. G8明细表24列/2区段 → G9明细表28列/3区段(多了利息/减值/OCI变动因子)
4. G8有指定适当性检查(G8-5) → G9有第三层次调节表(G9-5)
5. G8公式7个 → G9公式8个(多了calcL3Reconciliation)
6. G8导入导出4张表 → G9导入导出5张表(多了G9-5)

## Architecture

### sheetName分发模式 + 子目录组织

GtG9OtherNoncurrentFinancial.vue 接收 `sheetName` prop，用正则提取编码(G9A/G9-1~G9-6/附注披露(上市)/附注披露(国企)/底稿目录)，`v-if` 分发到对应子组件。

```
sheetName → regex提取编码 → v-if匹配 → defineAsyncComponent子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

10 sheets 子目录分组:
├── core/
│   ├── G9A    实质性程序表（复用a-program-console + 抽凭引擎 + 截止提取）
│   ├── G9-1   审定表（74行×15列，按FVTPL/FVOCI/摊余成本分组，虚拟滚动）
│   ├── G9-2   明细表（47行×28列→3区段Tab：基础信息/期初+变动/期末+公允价值）
│   ├── G9-3   调整分录汇总（24行×10列，AJE/RJE + 借贷平衡校验）
│   ├── 附注披露(上市)（13行×5列）
│   ├── 附注披露(国企)（13行×5列）
│   └── 底稿目录
├── valuation/
│   ├── G9-4   公允价值测试表（38行×21列→2区段Tab：基础+审定/估值详情+层次）
│   └── G9-5   第三层次调节表（22行×13列，L3期初→期末变动分析）
└── voucher/
    └── G9-6   凭证检查表（99行×20列→3区段Tab + 抽凭引擎 + 行级OCR + 虚拟滚动）
```

### 高层数据流

```mermaid
graph TD
    TB[trial_balance<br/>科目1504] -->|自动取数| G9_1[G9-1 审定表<br/>74行多层]
    G9_1 -->|EventBus: substantive:adjudicated| NOTE_L[附注披露-上市]
    G9_1 -->|EventBus: substantive:adjudicated| NOTE_S[附注披露-国企]
    NOTE_L -->|EventBus: disclosure:note-text-updated| EXT[附注模块]
    NOTE_S -->|EventBus: disclosure:note-text-updated| EXT
    G9_3[G9-3 调整分录] -->|AJE/RJE汇总回写| G9_1
    G9_2[G9-2 明细表<br/>28列3区段] -->|分类合计比对| G9_1
    G9_4[G9-4 公允价值测试<br/>21列2区段] -->|审定公允价值比对| G9_1
    G9_5[G9-5 L3调节表] -->|L3期末验证| G9_4
    G9A[G9A 程序表] -->|抽凭引擎| VOUCHER[GtVoucherSamplingEngine]
    G9A -->|截止提取| CUTOFF[useCutoffAutoSampling]
    G9_6[G9-6 凭证检查<br/>99行虚拟滚动] -->|抽凭引擎| VOUCHER
    G9_6 -->|行级OCR| OCR[/d4/contract-ocr]
    MAIN[GtG9OtherNoncurrentFinancial] -->|autoSnapshot| VER[useVersionTrail]
    MAIN -->|provide openReviewDialog| CHILDREN[所有子组件]
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtG9OtherNoncurrentFinancial.vue              # 主入口 sheetName v-if分发（defineAsyncComponent lazy×10）
├── g9-other-noncurrent-financial/
│   ├── core/
│   │   ├── G9TabProcedure.vue                    # G9A 程序表（复用a-program-console+selfLoad+抽凭+截止）
│   │   ├── G9TabAdjudication.vue                 # G9-1 审定表（74行×15列，混合计量分组+虚拟滚动）
│   │   ├── G9TabDetail.vue                       # G9-2 明细表(28列→3区段Tab)
│   │   ├── G9TabAdjustment.vue                   # G9-3 调整分录(AJE/RJE+借贷校验)
│   │   ├── G9TabDisclosureListed.vue             # 附注披露(上市)(13行)
│   │   ├── G9TabDisclosureSOE.vue                # 附注披露(国企)(13行)
│   │   └── G9TabDirectory.vue                    # 底稿目录
│   ├── valuation/
│   │   ├── G9TabFairValueTest.vue                # G9-4 公允价值测试(2区段Tab+Level3必填)
│   │   └── G9TabL3Reconciliation.vue             # G9-5 第三层次调节表(L3变动分析)
│   └── voucher/
│       └── G9TabVoucherCheck.vue                 # G9-6 凭证检查(3区段Tab+OCR+虚拟滚动)
├── composables/
│   ├── useG9FormulaEngine.ts                     # G9公式引擎(8个纯函数+parseNum)
│   ├── useG9FormData.ts                          # 数据加载/保存/selfLoad/writebackTB
│   ├── useG9ImportExport.ts                      # 导入导出composable(5张表: G9-2/G9-3/G9-4/G9-5/G9-6)
│   └── useG9DualMode.ts                          # 双模式OO切换+localStorage

backend/app/routers/wp_render_strategies/
├── _g9_other_noncurrent_financial.py             # render策略+注册RENDERER_DISPATCH
├── _g9_other_noncurrent_financial_service.py     # 业务逻辑(公式验证/TB取数/EventBus)
├── _g9_other_noncurrent_financial_import_export.py # 导入导出端点(5张表×3=15端点)
└── _g9_other_noncurrent_financial_ai.py          # AI生成4 section
```

### EventBus事件

| 事件名 | 发布者 | 消费者 | payload |
|--------|--------|--------|---------|
| `substantive:adjudicated` | G9-1审定表 | 附注披露(上市/国企) + trial_balance | `{accountCode:'1504', adjudicatedAmount, groups:{fvtpl, fvoci, amortizedCost}}` |
| `disclosure:note-text-updated` | 附注披露 | 附注模块 | `{accountCode:'1504', text}` |

### 后端AI Section清单

```
adjudication-analysis / fair-value-conclusion / l3-reconciliation-conclusion / voucher-conclusion
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtG9OtherNoncurrentFinancial.vue props
interface G9OtherNoncurrentFinancialProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// sheetName正则匹配映射
const SHEET_CODE_MAP: Record<string, string> = {
  'G9A': 'procedure',
  'G9-1': 'adjudication',
  'G9-2': 'detail',
  'G9-3': 'adjustment',
  'G9-4': 'fairValueTest',
  'G9-5': 'l3Reconciliation',
  'G9-6': 'voucherCheck',
  '附注披露信息（上市公司）': 'disclosureListed',
  '附注披露信息（国企）': 'disclosureSOE',
  '底稿目录': 'directory',
}
```

### G9-1 审定表数据模型（74行×15列，混合计量分组）

```typescript
// 计量属性分组枚举
type MeasurementCategory = 'FVTPL' | 'FVOCI' | 'AmortizedCost'

interface G9AdjudicationData {
  groups: G9AdjudicationGroup[]        // 按计量属性分组（FVTPL/FVOCI/摊余成本）
  grandTotals: G9AdjudicationTotals    // 合计行
  trialBalanceAmount: number           // 试算表取数(科目1504)
  variance: number                     // 差异=审定合计-试算表
}

interface G9AdjudicationGroup {
  category: MeasurementCategory        // 分组类型
  label: string                        // "一、以公允价值计量且变动计入当期损益" / ...
  rows: G9AdjudicationRow[]
  subtotals: G9AdjudicationTotals      // 分组小计
  collapsed: boolean                   // 折叠状态（默认展开）
}

interface G9AdjudicationRow {
  id: string
  item: string                         // 资产名称
  category: MeasurementCategory        // 所属分组
  // 期初
  openingUnadjusted: number            // 期初未审数
  openingAJE: number                   // 期初AJE调整
  openingRJE: number                   // 期初RJE调整
  openingAdjusted: number              // 公式: 未审 + AJE + RJE
  // 期末
  closingUnadjusted: number            // 期末未审数
  closingAJE: number                   // 期末AJE调整
  closingRJE: number                   // 期末RJE调整
  closingAdjusted: number              // 公式: 未审 + AJE + RJE
  // 变动
  changeAmount: number                 // 公式: 期末审定 - 期初审定
  changeRate: number | null            // 公式: (期末-期初)/期初, 期初=0时null
  reasonAnalysis: string               // |变动率|>20%时必填(橙色高亮)
  indexRef: string                     // 索引号
}

interface G9AdjudicationTotals {
  openingAdjusted: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
}
```

### G9-2 明细表数据模型（28列→3区段Tab）

```typescript
interface G9DetailRow {
  id: string
  seq: number
  // ══ Tab1: 基础信息(8列) ══
  assetName: string                    // 资产名称
  classification: 'FVTPL' | 'FVOCI' | 'AmortizedCost'  // 金融资产分类(下拉)
  initialInvestDate: string            // 初始投资日
  maturityDate: string                 // 到期日
  holdingQuantity: number              // 持有数量
  faceValueOrCost: number              // 面值/成本
  measurementAttribute: string         // 计量属性
  isRelatedParty: boolean              // 是否关联方

  // ══ Tab2: 期初+本期变动(10列) ══
  // assetName (行锚定，跨Tab显示)
  openingBalance: number               // 期初余额
  openingAdjustment: number            // 期初调整
  openingAdjusted: number              // 公式: 期初余额 + 期初调整
  increaseAmount: number               // 本期增加
  decreaseAmount: number               // 本期减少
  fvChangeAmount: number               // 本期公允价值变动
  interestIncome: number               // 本期利息收入
  impairmentLoss: number               // 本期减值
  ociChange: number                    // 本期OCI变动
  // (期末余额在Tab3计算)

  // ══ Tab3: 期末+公允价值(10列) ══
  // assetName (行锚定)
  closingBalance: number               // 公式: 期初审定+增加-减少+FV变动+利息-减值
  closingAdjustment: number            // 调整数
  closingAdjusted: number              // 公式: 期末余额 + 调整数
  fairValueLevel: 'Level1' | 'Level2' | 'Level3'  // 公允价值层次(下拉)
  valuationMethod: string              // 估值方法
  confirmationStatus: string           // 发函情况
  ociCumulative: number                // OCI累计
  impairmentProvision: number          // 减值准备
  remark: string                       // 备注
}
```

### G9-3 调整分录数据模型（24行×10列）

```typescript
interface G9AdjustmentEntry {
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

### G9-4 公允价值测试表数据模型（38行×21列→2区段Tab）

```typescript
interface G9FairValueTestRow {
  id: string
  seq: number
  // ══ Tab1: 基础+未审审定(11列) ══
  assetName: string                    // 资产名称
  initialInvestDate: string            // 初始投资日
  closingUnadjustedQty: number         // 期末未审-数量
  closingUnadjustedPrice: number       // 期末未审-单价
  closingUnadjustedFV: number          // 期末未审-公允价值
  closingAuditedQty: number            // 期末审定-数量
  closingAuditedPrice: number          // 期末审定-单价
  closingAuditedFV: number             // 期末审定-公允价值
  fairValueDiff: number                // 公式: 审定FV - 未审FV
  fairValueLevel: 'Level1' | 'Level2' | 'Level3'  // 公允价值层次(下拉)

  // ══ Tab2: 估值详情(10列) ══
  // assetName (行锚定)
  valuationMethod: string              // 估值方法(下拉: 市场法/收益法/资产基础法/其他)
  methodConsistentWithPrior: 'yes' | 'no'  // 与上期一致性
  valuationSource: string              // 来源机构
  inputSourceAndAdjustment: string     // 输入值来源(textarea)
  valuationTechnique: string           // 估值技术
  unobservableInputDesc: string        // 不可观察输入值(textarea)
  unobservableInputValue: string       // 数值
  nonLiquidityDiscount: number         // 非流通折价率
  valuationDocIndex: string            // 估值文件索引
}
```

### G9-5 第三层次调节表数据模型（22行×13列）

```typescript
interface G9L3ReconciliationRow {
  id: string
  seq: number
  assetName: string                    // 资产名称
  openingFairValue: number             // 期初公允价值
  purchaseAmount: number               // 本期购入
  disposalAmount: number               // 本期处置
  transferIn: number                   // 转入第三层次
  transferOut: number                  // 转出第三层次
  fvChangePL: number                   // 公允价值变动(计入损益)
  fvChangeOCI: number                  // 公允价值变动(计入OCI)
  interestIncome: number               // 利息收入
  impairmentLoss: number               // 减值损失
  otherChanges: number                 // 其他变动
  closingFairValue: number             // 公式: 期初+购入-处置+转入-转出+FV_PL+FV_OCI+利息-减值+其他
  variance: number                     // 公式: 计算期末 - 企业报告期末
}

interface G9L3ReconciliationData {
  rows: G9L3ReconciliationRow[]
  reportedClosing: Record<string, number>  // 企业报告的各资产期末(key=assetName)
  conclusion: string                   // 审计结论(textarea, AI辅助)
}
```

### G9-6 凭证检查表数据模型（99行×20列→3区段Tab）

```typescript
interface G9VoucherCheckRow {
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

  // ══ Tab2: 核对内容(7列) ══
  supportingDocDesc: string            // 支持性文件
  check1OriginalDoc: boolean           // 核对1-原始凭证
  check2Authorization: boolean         // 核对2-授权批准
  check3Accounting: boolean            // 核对3-账务处理
  check4Classification: boolean        // 核对4-分类正确
  check5FairValue: boolean             // 核对5-公允价值
  check6Impairment: boolean            // 核对6-减值计提

  // ══ Tab3: 结论(6列) ══
  indexNo: string                      // 索引号(GtIndexChip)
  isAbnormal: boolean                  // 是否异常(Tab2任一✗→自动是)
  abnormalDesc: string                 // 异常说明(textarea)
  riskLevel: 'high' | 'medium' | 'low'  // 风险等级(下拉)
  suggestion: string                   // 处理建议
  remark: string                       // 备注
}
```

### 附注数据模型

```typescript
interface G9DisclosureSection {
  id: string
  title: string
  rows?: G9DisclosureRow[]
  textContent?: string                 // 文本区内容（AI辅助）
}

interface G9DisclosureRow {
  id: string
  label: string
  value: string | number
  editable: boolean
}
```

## Data Models

### 存储结构（working_paper.content JSON）

```typescript
interface G9Content {
  // G9-1 审定表
  adjudication: {
    groups: G9AdjudicationGroup[]
    grandTotals: G9AdjudicationTotals
  }
  // G9-2 明细表
  detail: {
    rows: G9DetailRow[]
  }
  // G9-3 调整分录
  adjustment: {
    entries: G9AdjustmentEntry[]
  }
  // G9-4 公允价值测试
  fairValueTest: {
    rows: G9FairValueTestRow[]
    conclusion: string
  }
  // G9-5 第三层次调节表
  l3Reconciliation: G9L3ReconciliationData
  // G9-6 凭证检查
  voucherCheck: {
    rows: G9VoucherCheckRow[]
  }
  // 附注
  disclosureListed: { sections: G9DisclosureSection[] }
  disclosureSOE: { sections: G9DisclosureSection[] }
}
```

### API接口

```python
# _g9_other_noncurrent_financial.py
# RENDERER_DISPATCH注册
def render_g9_other_noncurrent_financial(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='g9-other-noncurrent-financial'和sheets配置"""

# _g9_other_noncurrent_financial_import_export.py
POST /api/workpapers/{wp_id}/g9/export-template?sheet={code}
POST /api/workpapers/{wp_id}/g9/export-data?sheet={code}
POST /api/workpapers/{wp_id}/g9/import-data?sheet={code}  # multipart/form-data
# sheet codes: G9-2 / G9-3 / G9-4 / G9-5 / G9-6
# 宽表按区段分sheet导出：
#   G9-2(3sheet) / G9-4(2sheet) / G9-6(3sheet) / G9-3(1sheet) / G9-5(1sheet)

# _g9_other_noncurrent_financial_ai.py
POST /api/workpapers/{wp_id}/g9/ai/{section}
# section: adjudication-analysis / fair-value-conclusion /
#          l3-reconciliation-conclusion / voucher-conclusion

# _g9_other_noncurrent_financial_service.py
class G9OtherNoncurrentFinancialService:
    async def get_trial_balance_data(project_id, year) -> dict
    async def save_adjudication(wp_id, data) -> dict
    async def validate_formulas(data) -> list[ValidationError]
    async def get_l3_reconciliation_summary(wp_id) -> dict
```

### trial_balance 取数

```sql
-- G9-1审定表自动取数（资产类/借方）
SELECT standard_account_code, unadjusted_amount, aje_adjustment, audited_amount
FROM trial_balance
WHERE project_id = :project_id
  AND year = :year
  AND standard_account_code LIKE '1504%'
```

### 注册四件套

```python
# 1. htmlRendererRegistry (前端)
'g9-other-noncurrent-financial': () => import('./workpaper/GtG9OtherNoncurrentFinancial.vue')

# 2. wp_code_overrides.json (10条)
{
  "G9A-其他非流动金融资产实质性程序表": "g9-other-noncurrent-financial",
  "G9-1-审定表": "g9-other-noncurrent-financial",
  "G9-2-明细表": "g9-other-noncurrent-financial",
  "G9-3-调整分录汇总": "g9-other-noncurrent-financial",
  "G9-4-公允价值测试表": "g9-other-noncurrent-financial",
  "G9-5-第三层次公允价值计量的调节表": "g9-other-noncurrent-financial",
  "G9-6-凭证检查表": "g9-other-noncurrent-financial",
  "G9-附注披露信息（上市公司）": "g9-other-noncurrent-financial",
  "G9-附注披露信息（国企）": "g9-other-noncurrent-financial",
  "G9-底稿目录": "g9-other-noncurrent-financial"
}

# 3. VALID_COMPONENT_TYPES (后端)
'g9-other-noncurrent-financial'

# 4. RENDERER_DISPATCH (后端)
'g9-other-noncurrent-financial': render_g9_other_noncurrent_financial
```

## Integration Design（6大集成接入点）

### 1. 版本链 (useVersionTrail)

```typescript
// GtG9OtherNoncurrentFinancial.vue 主入口
const { autoSnapshot, showVersionTrail } = useVersionTrail(wpId)

async function handleSave() {
  await saveData()
  await autoSnapshot()  // 触发版本快照
}
// 工具栏"版本历史"按钮 → GtWpVersionTrail drawer
```

### 2. 抽凭引擎 (G9A程序表 + G9-6凭证检查)

```typescript
// G9TabProcedure.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['1504']"
  dialog-mode
  @samples-ready="fillSamples"
/>

// G9TabVoucherCheck.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['1504']"
  dialog-mode
  @samples-ready="fillVoucherRows"
/>
```

### 3. 截止自动提取 (useCutoffAutoSampling)

```typescript
// G9TabProcedure.vue 截止测试步骤
const { fetchCutoffSamples } = useCutoffAutoSampling({
  projectId, accountCode: '1504', days: 5
})
```

### 4. 附注EventBus

```typescript
// G9TabAdjudication.vue (发布者)
watch(reportAmount, (val) => {
  eventBus.publish('substantive:adjudicated', {
    accountCode: '1504',
    adjudicatedAmount: val,
    groups: { fvtpl: fvtplTotal, fvoci: fvociTotal, amortizedCost: acTotal }
  })
})

// G9TabDisclosureListed.vue / G9TabDisclosureSOE.vue (消费者)
eventBus.subscribe('substantive:adjudicated', (payload) => {
  if (payload.accountCode === '1504') refreshData()
})

// 附注文本变更发布
eventBus.publish('disclosure:note-text-updated', {
  accountCode: '1504', text: noteText
})
```

### 5. 行级OCR (G9-6 📎附件列)

```typescript
// G9TabVoucherCheck.vue
async function handleOCR(row: G9VoucherCheckRow, file: File) {
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
// GtG9OtherNoncurrentFinancial.vue (主入口)
const { openReviewDialog } = useReviewDialog(wpId)
provide('openReviewDialog', openReviewDialog)

// 子组件 (section标题栏右侧按钮)
const openReviewDialog = inject('openReviewDialog')
```

## 宽表区段Tab拆分详细设计

### G9-1 审定表（74行，按计量属性分组+虚拟滚动）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ═══ 其他非流动金融资产审定表 ═════════════════════ [AI] [复核] ════════════ │
│                                                                             │
│ 📊 试算表取数(1504): ¥xxx | 差异: ¥0 ✓ (差异≠0时红色)                       │
│                                                                             │
│ ┌── 虚拟滚动容器(74行) ────────────────────────────────────────────────┐    │
│ │ ▼ 一、以公允价值计量且变动计入当期损益(FVTPL)  [折叠/展开]            │    │
│ │   │项目│期初(未审|AJE|RJE|审定)│期末(未审|AJE|RJE|审定)│变动额│变动率│原因│索引│  │
│ │   │ ... │                                                            │    │
│ │   │ 小计│                                                            │    │
│ │                                                                       │    │
│ │ ▼ 二、以公允价值计量且变动计入其他综合收益(FVOCI)  [折叠/展开]        │    │
│ │   │ ... │                                                            │    │
│ │   │ 小计│                                                            │    │
│ │                                                                       │    │
│ │ ▼ 三、以摊余成本计量  [折叠/展开]                                     │    │
│ │   │ ... │                                                            │    │
│ │   │ 小计│                                                            │    │
│ │                                                                       │    │
│ │ ═══ 合计 ═══                                                         │    │
│ └──────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│ ⚠️ |变动率|>20%时橙色高亮，要求填写原因分析                                 │
│ 公式列：虚线下划线+cursor:help+tooltip来源                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### G9-2 明细表（28列→3区段Tab）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ┌─────────────────┐ ┌──────────────────┐ ┌────────────────────┐            │
│ │Tab1: 基础信息(8列)│ │Tab2: 期初+变动(10列)│ │Tab3: 期末+公允价值(10列)│  3区段 │
│ └─────────────────┘ └──────────────────┘ └────────────────────┘            │
│                                                                             │
│ Tab1: 资产名称|分类(FVTPL/FVOCI/摊余 下拉)|初始投资日|到期日|               │
│       持有数量|面值/成本|计量属性|是否关联方                                  │
│                                                                             │
│ Tab2: 资产名称|期初余额|期初调整|期初审定(公式)|本期增加|本期减少|             │
│       公允价值变动|利息收入|减值|OCI变动                                      │
│                                                                             │
│ Tab3: 资产名称|期末余额(公式)|调整数|审定数(公式)|                            │
│       层次(L1/L2/L3)|估值方法|发函情况|OCI累计|减值准备|备注                  │
│                                                                             │
│ 底部：按分类(FVTPL/FVOCI/摊余成本)分组小计 + 总计                            │
│ 行同步：Tab切换保持行索引                                                    │
│ 动态行增删（ElMessageBox.prompt输入资产名称）                                │
│ 导入导出：el-dropdown(导出模板/导出数据/导入数据)                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### G9-4 公允价值测试表（21列→2区段Tab）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 方法论上下文（琥珀色左边线+浅黄背景）                                        │
│ "公允价值三层次定义：                                                        │
│   Level1-活跃市场上相同资产的报价(未经调整)                                   │
│   Level2-除Level1外可直接/间接观察到的输入值                                 │
│   Level3-相关资产不可观察的输入值(估值技术)"                                  │
│                                                                             │
│ ┌───────────────────────┐ ┌──────────────────────┐                         │
│ │Tab1: 基础+未审审定(11列) │ │Tab2: 估值详情+层次(10列)│    2区段Tab          │
│ └───────────────────────┘ └──────────────────────┘                         │
│                                                                             │
│ Tab1: 资产名称|初始投资日|未审(数量/单价/公允价值)|                            │
│       审定(数量/单价/公允价值)|差异(公式)|层次(下拉)                           │
│                                                                             │
│ Tab2: 资产名称|估值方法(下拉)|与上期一致(是/否)|来源机构|                      │
│       输入值来源(textarea)|估值技术|不可观察输入值(textarea)|                  │
│       数值|非流通折价率|估值文件索引                                           │
│                                                                             │
│ ⚠️ Level3必填校验：层次=Level3时Tab2(估值技术+不可观察输入值)必填             │
│                                                                             │
│ 底部：审计结论textarea(AI辅助) + <details>编制提示</details>                  │
│ 行同步：Tab切换保持行索引                                                    │
│ 动态行增删 + 导入导出                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### G9-5 第三层次调节表（22行×13列，G9特色）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ═══ 第三层次公允价值计量调节表 ═══════════════════ [AI] [复核] ═══════════ │
│                                                                             │
│ 方法论上下文（琥珀色左边线+浅黄背景）                                        │
│ "第三层次公允价值计量变动分析：                                               │
│  期初公允价值→(+购入 -处置 +转入L3 -转出L3 +FV变动_损益                     │
│  +FV变动_OCI +利息收入 -减值损失 +其他)→期末公允价值"                        │
│                                                                             │
│ │资产名称│期初FV│购入│处置│转入L3│转出L3│FV_PL│FV_OCI│利息│减值│其他│期末FV│差异│
│ │资产A   │ 100 │ 50 │ 20│  30  │  10  │  15 │   5  │  8 │  3 │  0 │ 175 │ 0 │
│ │资产B   │ ... │    │   │      │      │     │      │    │    │    │     │   │
│ │ ...    │     │    │   │      │      │     │      │    │    │    │     │   │
│ │ 合计   │ Σ   │ Σ  │ Σ │  Σ   │  Σ   │  Σ  │  Σ   │ Σ  │ Σ  │ Σ  │ Σ  │ Σ │
│                                                                             │
│ 公式: 期末FV = 期初+购入-处置+转入-转出+FV_PL+FV_OCI+利息-减值+其他         │
│ 公式: 差异 = 计算期末 - 企业报告期末                                         │
│ ⚠️ |差异|>0.01时红色高亮                                                    │
│                                                                             │
│ 底部：审计结论textarea(AI辅助按钮) + <details>编制提示</details>              │
│ 动态行增删（ElMessageBox.prompt输入资产名称）                                │
│ 导入导出                                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

### G9-6 凭证检查表（20列→3区段Tab + 虚拟滚动）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ┌──────────────┐ ┌────────────────┐ ┌────────────┐                        │
│ │Tab1: 凭证基础(7)│ │Tab2: 核对内容(7) │ │Tab3: 结论(6) │   3区段Tab         │
│ └──────────────┘ └────────────────┘ └────────────┘                        │
│                                                                             │
│ Tab1: 日期|凭证编号|业务内容|对方科目|借方|贷方|📎附件                         │
│       (📎点击→上传→OCR识别→ElMessageBox确认→填入)                            │
│                                                                             │
│ Tab2: 支持性文件|✓原始凭证|✓授权|✓账务处理|✓分类正确|✓公允价值|✓减值计提       │
│       (任一✗→Tab3"是否异常"自动置"是")                                       │
│                                                                             │
│ Tab3: 索引号(GtIndexChip)|是否异常|异常说明|风险等级|处理建议|备注             │
│                                                                             │
│ 顶部：借贷差额汇总（差额≠0红色）                                             │
│ 虚拟滚动：99行                                                               │
│ 行同步：3个Tab间切换保持行索引                                                │
│ 抽凭引擎 + 行级OCR + 动态行增删 + 导入导出                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Formula Engine Design (useG9FormulaEngine.ts)

### 8个纯函数 + parseNum

```typescript
/**
 * 安全数值转换：null/undefined/NaN/空字符串/'  '/'abc' → 0; 有效数值→原值
 */
export function parseNum(v: unknown): number

/**
 * 借方余额公式：期末未审 = 期初审定 + 借方 - 贷方
 * G9为借方/资产类科目(1504)
 */
export function calcDebitBalance(opening: number, debit: number, credit: number): number

/**
 * 审定数 = 未审数 + AJE + RJE
 * G9审定表有AJE/RJE分列（区别于G8只有单列adjustment）
 */
export function calcAdjustedAmount(unadjusted: number, aje: number, rje: number): number

/**
 * 期末余额(G9-2明细表) = 期初审定 + 增加 - 减少 + 公允价值变动 + 利息收入 - 减值
 * G9比G8多了利息收入和减值两个因子（混合计量特有）
 */
export function calcEndingBalance(
  openingAdjusted: number,
  increase: number,
  decrease: number,
  fvChange: number,
  interest: number,
  impairment: number
): number

/**
 * 公允价值差异 = 审定公允价值 - 未审公允价值
 * G9-4测试表用
 */
export function calcFairValueDiff(audited: number, unadjusted: number): number

/**
 * 变动率 = (current - prior) / prior
 * prior=0时返回null（避免除零）
 */
export function calcChangeRate(prior: number, current: number): number | null

/**
 * 借贷平衡校验：|SUM(debits) - SUM(credits)| < 0.01
 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean

/**
 * L3调节表公式（G9特色）：
 * 期末 = 期初 + 购入 - 处置 + 转入 - 转出 + FV_PL + FV_OCI + 利息 - 减值 + 其他
 * 10个输入因子的加减法
 */
export function calcL3Reconciliation(
  opening: number,
  purchase: number,
  disposal: number,
  transferIn: number,
  transferOut: number,
  fvChangePL: number,
  fvChangeOCI: number,
  interest: number,
  impairment: number,
  other: number
): number
```

### 公式引用关系

```
G9-1 审定表:
  openingAdjusted = calcAdjustedAmount(openingUnadjusted, openingAJE, openingRJE)
  closingAdjusted = calcAdjustedAmount(closingUnadjusted, closingAJE, closingRJE)
  changeAmount = closingAdjusted - openingAdjusted
  changeRate = calcChangeRate(openingAdjusted, closingAdjusted)

G9-2 明细表:
  openingAdjusted = openingBalance + openingAdjustment  (简化: 2因子)
  closingBalance = calcEndingBalance(openingAdjusted, increase, decrease, fvChange, interest, impairment)
  closingAdjusted = closingBalance + closingAdjustment

G9-3 调整分录:
  balanced = isDebitCreditBalanced(allDebits, allCredits)

G9-4 公允价值测试:
  fairValueDiff = calcFairValueDiff(closingAuditedFV, closingUnadjustedFV)

G9-5 L3调节表:
  closingFairValue = calcL3Reconciliation(opening, purchase, disposal, transferIn,
                                          transferOut, fvPL, fvOCI, interest, impairment, other)
  variance = closingFairValue - reportedClosing

G9-1 vs 试算表:
  closingUnadjusted ≈ calcDebitBalance(openingAdjusted, totalDebit, totalCredit)

G9-6 凭证检查:
  balanced = isDebitCreditBalanced(allDebits, allCredits)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 借方余额公式

*For any* opening, debit, credit ∈ ℝ: `calcDebitBalance(opening, debit, credit)` === `opening + debit - credit`

**Validates: Requirements 3.3, 10.1**

### Property 2: 审定数公式

*For any* unadjusted, aje, rje ∈ ℝ: `calcAdjustedAmount(unadjusted, aje, rje)` === `unadjusted + aje + rje`

**Validates: Requirements 3.3, 10.1**

### Property 3: L3调节表恒等

*For any* opening, purchase, disposal, transferIn, transferOut, fvPL, fvOCI, interest, impairment, other ∈ ℝ: `calcL3Reconciliation(opening, purchase, disposal, transferIn, transferOut, fvPL, fvOCI, interest, impairment, other)` === `opening + purchase - disposal + transferIn - transferOut + fvPL + fvOCI + interest - impairment + other`

**Validates: Requirements 8.2, 10.2**

### Property 4: 变动率方向性与除零保护

*For any* current > prior > 0: `calcChangeRate(prior, current)` > 0;
*For any* current < prior, prior > 0: `calcChangeRate(prior, current)` < 0;
`calcChangeRate(0, any)` === null

**Validates: Requirements 3.8, 10.1**

### Property 5: 借贷平衡恒等

*For any* debits[], credits[] ∈ ℝ[]: `isDebitCreditBalanced(debits, credits)` ↔ (|SUM(debits) - SUM(credits)| < 0.01)

**Validates: Requirements 6.2, 9.2, 10.1**

### Property 6: parseNum健壮性

*For any* input ∈ {null, undefined, '', NaN, '  ', 'abc'}: `parseNum(input)` === 0;
*For any* n ∈ ℝ (finite): `parseNum(n)` === n

**Validates: Requirements 10.1**

### Property 7: 期末余额多因子加法交换律

*For any* openingAdjusted, increase, decrease, fvChange, interest, impairment ∈ ℝ: `calcEndingBalance(openingAdjusted, increase, decrease, fvChange, interest, impairment)` === `openingAdjusted + increase - decrease + fvChange + interest - impairment`。且对加法项(increase, fvChange, interest)和减法项(decrease, impairment)分别求和后，结果与参数顺序无关。

**Validates: Requirements 5.2, 10.1**

### Property 8: L3差异为零时平衡

*For any* L3调节表行，WHEN `calcL3Reconciliation(...)` === 企业报告期末值 THEN 差异 === 0；即当公式计算的期末等于企业报告的期末时，`variance = calcL3Reconciliation(...) - reportedClosing` 恒为零。

**Validates: Requirements 8.3, 10.2**

## Error Handling

| 场景 | 处理策略 |
|------|---------|
| render-config 加载失败 | selfLoad重试1次 → 失败显示"加载失败"占位 + 重试按钮 |
| trial_balance 取数无数据 | 审定表显示0值 + 橙色提示"未找到科目1504数据" |
| 公式计算溢出/NaN | parseNum兜底→0，公式列显示"—" |
| 导入Excel格式不匹配 | 后端返回422 + 具体列错误信息 → 前端ElMessage.error |
| EventBus消息丢失 | 附注组件mounted时主动拉取最新审定数（非纯被动监听） |
| 保存时网络异常 | 自动重试3次(指数退避) → 失败后localStorage暂存 + 恢复提示 |
| sheetName无法识别 | fallback到OnlyOffice渲染（确保不白屏） |
| Level3必填校验未通过 | Tab2对应行红框高亮 + 顶部toast提示具体缺失字段 |
| G9-1 74行虚拟滚动渲染异常 | 降级为分页模式(每页30行) |
| G9-6 99行虚拟滚动渲染异常 | 降级为分页模式(每页30行) |
| OCR识别失败 | ElMessage.warning提示 + 允许手动填入 |
| 公允价值层次下拉未选择 | 保存时阻断 + 提示必选 |
| L3调节表差异过大(>重要性水平) | 红色高亮 + 自动追加审计说明提示 |
| 混合计量分组错误(明细分类与审定分组不匹配) | 保存时校验 + 橙色提示 |

## Testing Strategy

### 测试分层

| 层 | 工具 | 范围 | 数量估计 |
|----|------|------|---------|
| PBT(前端) | vitest + fast-check | 8个公式函数×8属性 | ~10 test cases |
| PBT(后端) | pytest + hypothesis | 公式验证 | ~8 test cases |
| 单元测试(前端) | vitest | composable逻辑/数据转换/Level3校验/异常自动检测/分组小计 | ~20 test cases |
| 单元测试(后端) | pytest | service/renderer/import-export | ~12 test cases |
| 集成测试 | pytest | API端点(15导入导出+4AI+render) | ~10 test cases |
| E2E | Playwright | 关键用户路径(审定+L3调节表+公允价值测试) | ~4 scenarios |

### PBT配置

- 前端：fast-check，`numRuns: 100`
- 后端：hypothesis，`max_examples=5`
- 每个PBT测试注释标注对应属性编号
- Tag格式：`Feature: g9-other-noncurrent-financial, Property {N}: {描述}`

### 关键测试路径

1. **审定表完整流程**：TB取数(1504) → 借方公式 → 按FVTPL/FVOCI/摊余成本分组 → 填写AJE/RJE → 审定计算 → EventBus发布 → 附注刷新
2. **L3调节表流程**：填入期初+各变动因子 → 公式计算期末 → 与企业报告比对 → 差异高亮 → AI生成结论
3. **公允价值三层次测试**：填入Level1/2/3 → Level3时Tab2必填校验触发 → 估值详情填入 → 差异计算 → 高亮
4. **凭证检查流程**：抽凭引擎→样本填入 → Tab2核对6项 → 任一✗自动异常 → OCR识别→确认填入
5. **明细表28列3区段**：Tab1填基础信息(含分类下拉) → Tab2填变动 → Tab3自动计算期末 → 分组小计验证

### PBT测试文件

```
audit-platform/frontend/src/components/workpaper/composables/__tests__/
└── useG9FormulaEngine.spec.ts         # 8个PBT属性 + fast-check

backend/tests/
└── test_g9_other_noncurrent_financial_pbt.py  # 后端PBT验证(hypothesis)
```

### 单元测试重点

- **L3调节表10因子验证**：验证各变动因子加减方向正确
- **混合计量分组逻辑**：验证FVTPL/FVOCI/摊余成本分组小计与合计一致
- **Level3必填校验逻辑**：验证当fairValueLevel='Level3'时，valuationTechnique和unobservableInputDesc不能为空
- **异常自动检测逻辑**：验证当check1-6任一为false时，isAbnormal自动设为true
- **区段Tab行同步**：验证Tab切换后当前选中行索引不变（G9-2三Tab、G9-4两Tab、G9-6三Tab）
- **导入导出宽表分sheet**：验证G9-2导出3sheet、G9-4导出2sheet、G9-6导出3sheet、G9-3导出1sheet、G9-5导出1sheet
- **变动率>20%高亮+必填**：验证changeRate绝对值>0.2时触发橙色样式和原因必填
- **审定表74行虚拟滚动**：验证可视区域只渲染部分行(buffer=5)
