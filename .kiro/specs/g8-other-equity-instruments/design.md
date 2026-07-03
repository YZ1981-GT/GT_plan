# Design Document: G8 其他权益工具投资底稿专属HTML精美组件

## Overview

G8其他权益工具投资专属组件`g8-other-equity-instruments`。覆盖1个xlsx源模板/10有效sheet。科目1503其他权益工具投资（借方/资产类）。**G循环中指定适当性审计最突出的科目**，包含非交易性权益工具指定合规性判断（CAS22）、公允价值Level1-3层次测试（含第三层次估值技术验证）等特色审计内容。

核心架构：
- componentType `g8-other-equity-instruments`，主入口 GtG8OtherEquityInstruments.vue
- **sheetName v-if dispatch模式**：10 sheets用v-if分发（不用el-tabs）
- 子目录分组：core/ + valuation/ + voucher/
- 宽表拆分：G8-2(24列→2区段Tab) / G8-4(19列→2区段Tab) / G8-6(18列→3区段Tab)
- 借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额
- OCI核算：公允价值变动计入其他综合收益（不进损益）
- EventBus联动：publish `substantive:adjudicated`(accountCode='1503') + `disclosure:note-text-updated`
- 特色：指定适当性检查G8-5(CAS22问卷) + 公允价值三层次G8-4(Level3必填校验)
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useG8ImportExport, 4张表) + AI(4 section)
- 六大集成：版本链✅ 抽凭✅ 截止✅ 附注EventBus✅ OCR✅ 复核✅

## Architecture

### sheetName分发模式 + 子目录组织

GtG8OtherEquityInstruments.vue 接收 `sheetName` prop，用正则提取编码(G8A/G8-1~G8-6/附注披露(上市)/附注披露(国企)/底稿目录)，`v-if` 分发到对应子组件。

```
sheetName → regex提取编码 → v-if匹配 → defineAsyncComponent子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

10 sheets 子目录分组:
├── core/
│   ├── G8A    实质性程序表（复用a-program-console + 抽凭引擎 + 截止提取）
│   ├── G8-1   审定表（29行×11列，借方/公允价值计量）
│   ├── G8-2   明细表（39行×24列→2区段Tab：基础信息/公允价值+OCI）
│   ├── G8-3   调整分录汇总（24行×10列，AJE/RJE + 借贷平衡校验）
│   ├── 附注披露(上市)（18行×7列）
│   ├── 附注披露(国企)（20行×7列）
│   └── 底稿目录
├── valuation/
│   ├── G8-4   公允价值测试表（40行×19列→2区段Tab：Level1/2/3+估值技术）
│   └── G8-5   指定的适当性检查表（36行×19列，问卷式CAS22合规）
└── voucher/
    └── G8-6   凭证检查表（102行×18列→3区段Tab + 抽凭引擎 + 行级OCR）
```

### 高层数据流

```mermaid
graph TD
    TB[trial_balance<br/>科目1503] -->|自动取数| G8_1[G8-1 审定表]
    G8_1 -->|EventBus: substantive:adjudicated| NOTE_L[附注披露-上市]
    G8_1 -->|EventBus: substantive:adjudicated| NOTE_S[附注披露-国企]
    NOTE_L -->|EventBus: disclosure:note-text-updated| EXT[附注模块]
    NOTE_S -->|EventBus: disclosure:note-text-updated| EXT
    G8_3[G8-3 调整分录] -->|AJE/RJE汇总回写| G8_1
    G8_2[G8-2 明细表] -->|公允价值变动合计比对| G8_1
    G8_4[G8-4 公允价值测试] -->|审定公允价值比对| G8_1
    G8_5[G8-5 适当性检查] -->|指定合规结论| G8_4
    G8A[G8A 程序表] -->|抽凭引擎| VOUCHER[GtVoucherSamplingEngine]
    G8A -->|截止提取| CUTOFF[useCutoffAutoSampling]
    G8_6[G8-6 凭证检查] -->|抽凭引擎| VOUCHER
    G8_6 -->|行级OCR| OCR[/d4/contract-ocr]
    MAIN[GtG8OtherEquityInstruments] -->|autoSnapshot| VER[useVersionTrail]
    MAIN -->|provide openReviewDialog| CHILDREN[所有子组件]
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtG8OtherEquityInstruments.vue                # 主入口 sheetName v-if分发（defineAsyncComponent lazy×10）
├── g8-other-equity-instruments/
│   ├── core/
│   │   ├── G8TabProcedure.vue                    # G8A 程序表（复用a-program-console+selfLoad+抽凭+截止）
│   │   ├── G8TabAdjudication.vue                 # G8-1 审定表（29行×11列，借方+公允价值计量）
│   │   ├── G8TabDetail.vue                       # G8-2 明细表(24列→2区段Tab)
│   │   ├── G8TabAdjustment.vue                   # G8-3 调整分录(AJE/RJE+借贷校验)
│   │   ├── G8TabDisclosureListed.vue             # 附注披露(上市)(18行)
│   │   ├── G8TabDisclosureSOE.vue                # 附注披露(国企)(20行)
│   │   └── G8TabDirectory.vue                    # 底稿目录
│   ├── valuation/
│   │   ├── G8TabFairValueTest.vue                # G8-4 公允价值测试(2区段Tab+Level3必填)
│   │   └── G8TabDesignationCheck.vue             # G8-5 适当性检查(问卷式CAS22)
│   └── voucher/
│       └── G8TabVoucherCheck.vue                 # G8-6 凭证检查(3区段Tab+OCR+虚拟滚动)
├── composables/
│   ├── useG8FormulaEngine.ts                     # G8公式引擎(7个纯函数+parseNum)
│   ├── useG8FormData.ts                          # 数据加载/保存/selfLoad/writebackTB
│   ├── useG8ImportExport.ts                      # 导入导出composable(4张表: G8-2/G8-3/G8-4/G8-6)
│   └── useG8DualMode.ts                          # 双模式OO切换+localStorage

backend/app/routers/wp_render_strategies/
├── _g8_other_equity_instruments.py               # render策略+注册RENDERER_DISPATCH
├── _g8_other_equity_instruments_service.py       # 业务逻辑(公式验证/TB取数/EventBus)
├── _g8_other_equity_instruments_import_export.py # 导入导出端点(4张表×3=12端点)
└── _g8_other_equity_instruments_ai.py            # AI生成4 section
```

### EventBus事件

| 事件名 | 发布者 | 消费者 | payload |
|--------|--------|--------|---------|
| `substantive:adjudicated` | G8-1审定表 | 附注披露(上市/国企) + trial_balance | `{accountCode:'1503', adjudicatedAmount}` |
| `disclosure:note-text-updated` | 附注披露 | 附注模块 | `{accountCode:'1503', text}` |

### 后端AI Section清单

```
adjudication-analysis / fair-value-conclusion / designation-conclusion / voucher-conclusion
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtG8OtherEquityInstruments.vue props
interface G8OtherEquityInstrumentsProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// sheetName正则匹配映射
const SHEET_CODE_MAP: Record<string, string> = {
  'G8A': 'procedure',
  'G8-1': 'adjudication',
  'G8-2': 'detail',
  'G8-3': 'adjustment',
  'G8-4': 'fairValueTest',
  'G8-5': 'designationCheck',
  'G8-6': 'voucherCheck',
  '附注披露信息（上市公司）': 'disclosureListed',
  '附注披露信息（国企）': 'disclosureSOE',
  '底稿目录': 'directory',
}
```

### G8-1 审定表数据模型（29行×11列，借方科目公允价值计量）

```typescript
interface G8AdjudicationData {
  rows: G8AdjudicationRow[]            // 按被投资单位逐项列示
  totals: G8AdjudicationTotals         // 合计行
  trialBalanceAmount: number           // 试算表取数(科目1503)
  variance: number                     // 差异=审定-试算表
}

interface G8AdjudicationRow {
  id: string
  item: string                         // 被投资单位名称
  // 期初
  openingUnadjusted: number            // 期初未审数
  openingAdjustment: number            // 期初账项调整
  openingAdjusted: number              // 公式: 未审 + 账项调整
  // 期末
  closingUnadjusted: number            // 期末未审数（借方余额公式）
  closingAdjustment: number            // 期末账项调整
  closingAdjusted: number              // 公式: 未审 + 账项调整
  // 变动
  changeAmount: number                 // 公式: 期末审定 - 期初审定
  changeRate: number | null            // 公式: (期末-期初)/期初, 期初=0时null
  reasonAnalysis: string               // |变动率|>20%时必填(橙色高亮)
}

interface G8AdjudicationTotals {
  openingAdjusted: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
}
```

### G8-2 明细表数据模型（24列→2区段Tab）

```typescript
interface G8DetailRow {
  id: string
  seq: number
  // ══ Tab1: 被投资单位基础信息(12列) ══
  investeeName: string                 // 被投资单位名称
  investmentRatio: number              // 投资比例(小数)
  openingBalance: number               // 期初余额
  openingAdjustment: number            // 期初调整数
  openingAdjusted: number              // 公式: 期初余额 + 期初调整数
  increaseAmount: number               // 本期增加
  decreaseAmount: number               // 本期减少
  fvChangeAmount: number               // 公允价值变动
  closingBalance: number               // 公式: 期初审定+增加-减少+公允价值变动
  closingAdjustment: number            // 期末调整数
  closingAdjusted: number              // 公式: 期末余额 + 调整数
  designationReason: string            // 指定为OCI的原因

  // ══ Tab2: 公允价值+OCI(12列) ══
  ociCumulativeChange: number          // OCI累计变动
  ociCurrentChange: number             // 本期OCI变动
  ociToRetainedEarnings: number        // OCI转入留存收益金额
  transferReason: string               // 转入原因
  confirmationStatus: string           // 发函情况
  fairValueLevel: 'Level1' | 'Level2' | 'Level3'  // 公允价值层次(下拉)
  valuationMethod: string              // 估值方法
  sharesHeld: number                   // 持股数量
  pricePerShare: number                // 每股公允价值
  fairValueTotal: number               // 公允价值合计
  remark: string                       // 备注
}
```

### G8-3 调整分录数据模型（24行×10列）

```typescript
interface G8AdjustmentEntry {
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

### G8-4 公允价值测试表数据模型（40行×19列→2区段Tab）

```typescript
interface G8FairValueTestRow {
  id: string
  seq: number
  // ══ Tab1: 基础信息+审定(10列) ══
  investeeName: string                 // 被投资单位名称
  initialInvestDate: string            // 初始投资日期
  closingUnadjustedQty: number         // 期末未审-数量
  closingUnadjustedPrice: number       // 期末未审-单价
  closingUnadjustedFV: number          // 期末未审-公允价值
  closingAuditedQty: number            // 期末审定-数量
  closingAuditedPrice: number          // 期末审定-单价
  closingAuditedFV: number             // 期末审定-公允价值
  fairValueDiff: number                // 公式: 审定FV - 未审FV
  fairValueLevel: 'Level1' | 'Level2' | 'Level3'  // 公允价值层次(下拉)

  // ══ Tab2: 估值详情(9列) ══
  valuationMethod: string              // 估值方法(下拉: 市场法/收益法/资产基础法/其他)
  methodConsistentWithPrior: 'yes' | 'no'  // 估值方法与上期是否一致
  valuationSource: string              // 公允价值来源机构
  inputSourceAndAdjustment: string     // 输入值来源及调整考虑因素(textarea)
  valuationTechnique: string           // 估值技术(市场法/收益法/资产基础法)
  unobservableInputDesc: string        // 不可观察输入值描述(textarea)
  unobservableInputValue: string       // 数值
  valuationDocIndex: string            // 估值文件索引号
}
```

### G8-5 指定适当性检查表数据模型（36行×19列，问卷式）

```typescript
interface G8DesignationCheckData {
  sections: G8DesignationSection[]
  overallConclusion: string            // 综合审计结论(textarea)
}

interface G8DesignationSection {
  id: string
  sectionNo: string                    // (一)~(四)
  title: string
  // (一)指定是否符合准则要求
  // (二)管理层持有目的验证
  // (三)金融资产分类合规性
  // (四)指定的不可撤销性
  rows: G8DesignationRow[]
}

interface G8DesignationRow {
  id: string
  seq: number
  checkItem: string                    // 检查项目
  auditRequirement: string             // 审计要求(方法论)
  evidenceOrReply: string              // 管理层回复/审计获取证据(textarea)
  compliance: 'compliant' | 'non_compliant' | 'not_applicable'  // 是否合规(下拉)
  auditConclusion: string              // 审计结论(textarea)
  indexRef: string                     // 索引
}
```

### G8-6 凭证检查表数据模型（102行×18列→3区段Tab）

```typescript
interface G8VoucherCheckRow {
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

  // ══ Tab2: 核对内容(6列) ══
  supportingDocDesc: string            // 支持性文件描述
  check1OriginalComplete: boolean      // 核对1-原始凭证完整
  check2Authorization: boolean         // 核对2-授权批准
  check3Accounting: boolean            // 核对3-账务处理正确
  check4FairValueCorrect: boolean      // 核对4-公允价值计量正确
  check5OCICorrect: boolean            // 核对5-OCI计入正确

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
interface G8DisclosureSection {
  id: string
  title: string
  rows?: G8DisclosureRow[]
  textContent?: string                 // 文本区内容（AI辅助）
}

interface G8DisclosureRow {
  id: string
  label: string
  value: string | number
  editable: boolean
}
```

## Data Models

### 存储结构（working_paper.content JSON）

```typescript
interface G8Content {
  // G8-1 审定表
  adjudication: {
    rows: G8AdjudicationRow[]
    totals: G8AdjudicationTotals
  }
  // G8-2 明细表
  detail: {
    rows: G8DetailRow[]
  }
  // G8-3 调整分录
  adjustment: {
    entries: G8AdjustmentEntry[]
  }
  // G8-4 公允价值测试
  fairValueTest: {
    rows: G8FairValueTestRow[]
    conclusion: string                 // 审计结论
  }
  // G8-5 指定适当性检查
  designationCheck: G8DesignationCheckData
  // G8-6 凭证检查
  voucherCheck: {
    rows: G8VoucherCheckRow[]
  }
  // 附注
  disclosureListed: { sections: G8DisclosureSection[] }
  disclosureSOE: { sections: G8DisclosureSection[] }
}
```

### API接口

```python
# _g8_other_equity_instruments.py
# RENDERER_DISPATCH注册
def render_g8_other_equity_instruments(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='g8-other-equity-instruments'和sheets配置"""

# _g8_other_equity_instruments_import_export.py
POST /api/workpapers/{wp_id}/g8/export-template?sheet={code}
POST /api/workpapers/{wp_id}/g8/export-data?sheet={code}
POST /api/workpapers/{wp_id}/g8/import-data?sheet={code}  # multipart/form-data
# sheet codes: G8-2 / G8-3 / G8-4 / G8-6
# 宽表按区段分sheet导出：
#   G8-2(2sheet) / G8-4(2sheet) / G8-6(3sheet)

# _g8_other_equity_instruments_ai.py
POST /api/workpapers/{wp_id}/g8/ai/{section}
# section: adjudication-analysis / fair-value-conclusion /
#          designation-conclusion / voucher-conclusion

# _g8_other_equity_instruments_service.py
class G8OtherEquityInstrumentsService:
    async def get_trial_balance_data(project_id, year) -> dict
    async def save_adjudication(wp_id, data) -> dict
    async def validate_formulas(data) -> list[ValidationError]
```

### trial_balance 取数

```sql
-- G8-1审定表自动取数（资产类/借方）
SELECT standard_account_code, unadjusted_amount, aje_adjustment, audited_amount
FROM trial_balance
WHERE project_id = :project_id
  AND year = :year
  AND standard_account_code LIKE '1503%'
```

### 注册四件套

```python
# 1. htmlRendererRegistry (前端)
'g8-other-equity-instruments': () => import('./workpaper/GtG8OtherEquityInstruments.vue')

# 2. wp_code_overrides.json (10条)
{
  "G8A-其他权益工具投资实质性程序表": "g8-other-equity-instruments",
  "G8-1-审定表": "g8-other-equity-instruments",
  "G8-2-明细表": "g8-other-equity-instruments",
  "G8-3-调整分录汇总": "g8-other-equity-instruments",
  "G8-4-公允价值测试表": "g8-other-equity-instruments",
  "G8-5-指定的适当性检查表": "g8-other-equity-instruments",
  "G8-6-凭证检查表": "g8-other-equity-instruments",
  "G8-附注披露信息（上市公司）": "g8-other-equity-instruments",
  "G8-附注披露信息（国企）": "g8-other-equity-instruments",
  "G8-底稿目录": "g8-other-equity-instruments"
}

# 3. VALID_COMPONENT_TYPES (后端)
'g8-other-equity-instruments'

# 4. RENDERER_DISPATCH (后端)
'g8-other-equity-instruments': render_g8_other_equity_instruments
```

## Integration Design（6大集成接入点）

### 1. 版本链 (useVersionTrail)

```typescript
// GtG8OtherEquityInstruments.vue 主入口
const { autoSnapshot, showVersionTrail } = useVersionTrail(wpId)

async function handleSave() {
  await saveData()
  await autoSnapshot()  // 触发版本快照
}
// 工具栏"版本历史"按钮 → GtWpVersionTrail drawer
```

### 2. 抽凭引擎 (G8A程序表 + G8-6凭证检查)

```typescript
// G8TabProcedure.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['1503']"
  dialog-mode
  @samples-ready="fillSamples"
/>

// G8TabVoucherCheck.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['1503']"
  dialog-mode
  @samples-ready="fillVoucherRows"
/>
```

### 3. 截止自动提取 (useCutoffAutoSampling)

```typescript
// G8TabProcedure.vue 截止测试步骤
const { fetchCutoffSamples } = useCutoffAutoSampling({
  projectId, accountCode: '1503', days: 5
})
```

### 4. 附注EventBus

```typescript
// G8TabAdjudication.vue (发布者)
watch(reportAmount, (val) => {
  eventBus.publish('substantive:adjudicated', {
    accountCode: '1503',
    adjudicatedAmount: val
  })
})

// G8TabDisclosureListed.vue / G8TabDisclosureSOE.vue (消费者)
eventBus.subscribe('substantive:adjudicated', (payload) => {
  if (payload.accountCode === '1503') refreshData()
})

// 附注文本变更发布
eventBus.publish('disclosure:note-text-updated', {
  accountCode: '1503', text: noteText
})
```

### 5. 行级OCR (G8-6 📎附件列)

```typescript
// G8TabVoucherCheck.vue
async function handleOCR(row: G8VoucherCheckRow, file: File) {
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
// GtG8OtherEquityInstruments.vue (主入口)
const { openReviewDialog } = useReviewDialog(wpId)
provide('openReviewDialog', openReviewDialog)

// 子组件 (section标题栏右侧按钮)
const openReviewDialog = inject('openReviewDialog')
```

## 宽表区段Tab拆分详细设计

### G8-2 明细表（24列→2区段Tab）

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌────────────────────────┐ ┌───────────────────────┐           │
│ │Tab1: 被投资单位基础(12列)│ │Tab2: 公允价值+OCI(12列)│  区段Tab  │
│ └────────────────────────┘ └───────────────────────┘           │
│                                                                 │
│ Tab1: 序号|名称|投资比例|期初余额|期初调整|期初审定(公式)|         │
│       增加|减少|公允价值变动|期末余额(公式)|调整数|审定(公式)|      │
│       指定OCI原因                                                │
│                                                                 │
│ Tab2: 序号|名称|OCI累计变动|本期OCI变动|OCI转留存收益|转入原因|    │
│       发函情况|层次(L1/L2/L3)|估值方法|持股数|每股公允价值|        │
│       公允价值合计|备注                                           │
│                                                                 │
│ 底部：合计行（期初/增加/减少/公允价值变动/期末/OCI合计）           │
│ 行同步：Tab切换保持行索引                                        │
└─────────────────────────────────────────────────────────────────┘
```

### G8-4 公允价值测试表（19列→2区段Tab）

```
┌─────────────────────────────────────────────────────────────────┐
│ 方法论上下文（琥珀色左边线+浅黄背景）                             │
│ "公允价值三层次定义：                                            │
│   Level1-活跃市场上相同资产的报价(未经调整)                       │
│   Level2-除Level1外可直接/间接观察到的输入值                     │
│   Level3-相关资产不可观察的输入值(估值技术)"                      │
│                                                                 │
│ ┌──────────────────────┐ ┌──────────────────┐                  │
│ │Tab1: 基础信息+审定(10列)│ │Tab2: 估值详情(9列)│    区段Tab      │
│ └──────────────────────┘ └──────────────────┘                  │
│                                                                 │
│ Tab1: 序号|名称|初始投资日期|未审数量|未审单价|未审FV|              │
│       审定数量|审定单价|审定FV|差异(公式)|层次(下拉)               │
│                                                                 │
│ Tab2: 序号|名称|估值方法(下拉)|与上期一致(是/否)|来源机构|         │
│       输入值来源(textarea)|估值技术|不可观察输入值描述|数值|       │
│       估值文件索引号                                              │
│                                                                 │
│ ⚠️ Level3必填校验：层次=Level3时Tab2(估值技术+不可观察输入值)必填 │
│                                                                 │
│ 底部：审计结论textarea(AI辅助) + <details>编制提示</details>      │
│ 行同步：Tab切换保持行索引                                        │
└─────────────────────────────────────────────────────────────────┘
```

### G8-5 适当性检查表（问卷式，无需区段拆分）

```
┌─────────────────────────────────────────────────────────────────┐
│ 方法论上下文（琥珀色左边线+浅黄背景）                             │
│ "CAS22指定条件：                                                 │
│   ① 该金融资产非为交易目的而持有                                  │
│   ② 在初始确认时做出不可撤销的选择                                │
│   ③ 公允价值变动计入其他综合收益                                  │
│   ④ 处置时累计OCI可转入留存收益（不经损益）"                      │
│                                                                 │
│ ═══ (一) 指定是否符合准则要求 ═══════════ [AI] [复核] ══════════ │
│ │ 序号 │ 检查项目 │ 审计要求 │ 证据/回复 │ 合规 │ 结论 │ 索引 │   │
│ │ 1.1  │ ...      │ ...     │ textarea │ 下拉 │ ...  │ ...  │   │
│ │ 1.2  │ ...      │ ...     │ textarea │ 下拉 │ ...  │ ...  │   │
│                                                                 │
│ ═══ (二) 管理层持有目的验证 ═══════════ [AI] [复核] ═══════════ │
│ │ ...                                                            │
│                                                                 │
│ ═══ (三) 金融资产分类合规性 ═══════════ [AI] [复核] ═══════════ │
│ │ ...                                                            │
│                                                                 │
│ ═══ (四) 指定的不可撤销性 ═══════════ [AI] [复核] ═════════════ │
│ │ ...                                                            │
│                                                                 │
│ 综合审计结论 textarea(AI辅助)                                    │
│ <details>编制提示</details>                                      │
└─────────────────────────────────────────────────────────────────┘
```

### G8-6 凭证检查表（18列→3区段Tab）

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌──────────────┐ ┌──────────────┐ ┌──────────┐                │
│ │Tab1: 凭证基础(7)│ │Tab2: 核对内容(6)│ │Tab3: 结论(5)│  3区段Tab │
│ └──────────────┘ └──────────────┘ └──────────┘                │
│                                                                 │
│ Tab1: 日期|凭证编号|业务内容|对方科目|借方|贷方|📎附件             │
│       (📎点击→上传→OCR识别→ElMessageBox确认→填入)                │
│                                                                 │
│ Tab2: 文件描述|✓完整|✓授权|✓账务正确|✓公允价值正确|✓OCI正确       │
│       (任一✗→Tab3"是否异常"自动置"是")                           │
│                                                                 │
│ Tab3: 索引号(GtIndexChip)|是否异常|异常说明|风险等级|备注         │
│                                                                 │
│ 顶部：借贷差额汇总（差额≠0红色）                                 │
│ 虚拟滚动：102行                                                  │
│ 行同步：3个Tab间切换保持行索引                                    │
└─────────────────────────────────────────────────────────────────┘
```

## Formula Engine Design (useG8FormulaEngine.ts)

### 7个纯函数 + parseNum

```typescript
/**
 * 安全数值转换：null/undefined/NaN/空字符串/'  '/'abc' → 0; 有效数值→原值
 */
export function parseNum(v: unknown): number

/**
 * 借方余额公式：期末未审 = 期初审定 + 借方 - 贷方
 * G8为借方/资产类科目
 */
export function calcDebitBalance(opening: number, debit: number, credit: number): number

/**
 * 审定数 = 未审数 + 账项调整
 * G8只有账项调整（无AJE/RJE分列）
 */
export function calcAdjustedAmount(unadjusted: number, adjustment: number): number

/**
 * 期末余额 = 期初审定 + 增加 - 减少 + 公允价值变动
 * G8-2明细表核心公式（OCI不影响账面余额方向，公允价值变动计入OCI同时调账面）
 */
export function calcEndingBalance(openingAdjusted: number, increase: number, decrease: number, fvChange: number): number

/**
 * 公允价值差异 = 审定公允价值 - 未审公允价值
 * G8-4测试表用
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
```

### 公式引用关系

```
G8-1 审定表:
  openingAdjusted = calcAdjustedAmount(openingUnadjusted, openingAdjustment)
  closingAdjusted = calcAdjustedAmount(closingUnadjusted, closingAdjustment)
  changeAmount = closingAdjusted - openingAdjusted
  changeRate = calcChangeRate(openingAdjusted, closingAdjusted)

G8-2 明细表:
  openingAdjusted = calcAdjustedAmount(openingBalance, openingAdjustment)
  closingBalance = calcEndingBalance(openingAdjusted, increase, decrease, fvChange)
  closingAdjusted = calcAdjustedAmount(closingBalance, closingAdjustment)

G8-3 调整分录:
  balanced = isDebitCreditBalanced(allDebits, allCredits)

G8-4 公允价值测试:
  fairValueDiff = calcFairValueDiff(closingAuditedFV, closingUnadjustedFV)

G8-1 vs 试算表:
  closingUnadjusted ≈ calcDebitBalance(openingAdjusted, totalDebit, totalCredit)
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 借方余额公式

*For any* opening, debit, credit ∈ ℝ: `calcDebitBalance(opening, debit, credit)` === `opening + debit - credit`

**Validates: Requirements 3.3, 10.1**

### Property 2: 审定数公式

*For any* unadjusted, adjustment ∈ ℝ: `calcAdjustedAmount(unadjusted, adjustment)` === `unadjusted + adjustment`

**Validates: Requirements 3.4, 5.2, 10.2**

### Property 3: 期末余额公式

*For any* openingAdjusted, increase, decrease, fvChange ∈ ℝ: `calcEndingBalance(openingAdjusted, increase, decrease, fvChange)` === `openingAdjusted + increase - decrease + fvChange`

**Validates: Requirements 5.3, 10.3**

### Property 4: 公允价值差异

*For any* audited, unadjusted ∈ ℝ: `calcFairValueDiff(audited, unadjusted)` === `audited - unadjusted`

**Validates: Requirements 7.4, 10.4**

### Property 5: 变动率方向性与除零保护

*For any* current > prior > 0: `calcChangeRate(prior, current)` > 0;
*For any* current < prior, prior > 0: `calcChangeRate(prior, current)` < 0;
`calcChangeRate(0, any)` === null

**Validates: Requirements 3.8, 10.5**

### Property 6: 借贷平衡恒等

*For any* debits[], credits[] ∈ ℝ[]: `isDebitCreditBalanced(debits, credits)` ↔ (|SUM(debits) - SUM(credits)| < 0.01)

**Validates: Requirements 6.2, 9.5, 10.6**

### Property 7: parseNum健壮性

*For any* input ∈ {null, undefined, '', NaN, '  ', 'abc'}: `parseNum(input)` === 0;
*For any* n ∈ ℝ (finite): `parseNum(n)` === n

**Validates: Requirements 10.7**

### Property 8: 期末余额与审定一致性（组合性质）

*For any* openingAdjusted, increase, decrease, fvChange, adjustment ∈ ℝ: `calcAdjustedAmount(calcEndingBalance(openingAdjusted, increase, decrease, fvChange), adjustment)` === `openingAdjusted + increase - decrease + fvChange + adjustment`

**Validates: Requirements 5.2, 5.3, 10.2, 10.3**

## Error Handling

| 场景 | 处理策略 |
|------|---------|
| render-config 加载失败 | selfLoad重试1次 → 失败显示"加载失败"占位 + 重试按钮 |
| trial_balance 取数无数据 | 审定表显示0值 + 橙色提示"未找到科目1503数据" |
| 公式计算溢出/NaN | parseNum兜底→0，公式列显示"—" |
| 导入Excel格式不匹配 | 后端返回422 + 具体列错误信息 → 前端ElMessage.error |
| EventBus消息丢失 | 附注组件mounted时主动拉取最新审定数（非纯被动监听） |
| 保存时网络异常 | 自动重试3次(指数退避) → 失败后localStorage暂存 + 恢复提示 |
| sheetName无法识别 | fallback到OnlyOffice渲染（确保不白屏） |
| Level3必填校验未通过 | Tab2对应行红框高亮 + 顶部toast提示具体缺失字段 |
| G8-6 102行虚拟滚动渲染异常 | 降级为分页模式(每页30行) |
| OCR识别失败 | ElMessage.warning提示 + 允许手动填入 |
| 公允价值层次下拉未选择 | 保存时阻断 + 提示必选 |

## Testing Strategy

### 测试分层

| 层 | 工具 | 范围 | 数量估计 |
|----|------|------|---------|
| PBT(前端) | vitest + fast-check | 7个公式函数×8属性 | ~10 test cases |
| PBT(后端) | pytest + hypothesis | 公式验证 | ~8 test cases |
| 单元测试(前端) | vitest | composable逻辑/数据转换/Level3校验/异常自动检测 | ~18 test cases |
| 单元测试(后端) | pytest | service/renderer/import-export | ~10 test cases |
| 集成测试 | pytest | API端点(12导入导出+4AI+render) | ~8 test cases |
| E2E | Playwright | 关键用户路径(审定+公允价值测试+适当性检查) | ~4 scenarios |

### PBT配置

- 前端：fast-check，`numRuns: 100`
- 后端：hypothesis，`max_examples=5`
- 每个PBT测试注释标注对应属性编号
- Tag格式：`Feature: g8-other-equity-instruments, Property {N}: {描述}`

### 关键测试路径

1. **审定表完整流程**：TB取数(1503) → 借方公式 → 填写调整 → 审定计算 → EventBus发布 → 附注刷新
2. **公允价值三层次测试**：填入Level1/2/3 → Level3时Tab2必填校验触发 → 估值详情填入 → 差异计算 → 高亮
3. **指定适当性检查**：CAS22四section问卷 → 逐项合规判断 → AI辅助生成结论
4. **凭证检查流程**：抽凭引擎→样本填入 → Tab2核对5项 → 任一✗自动异常 → OCR识别→确认填入

### PBT测试文件

```
audit-platform/frontend/src/components/workpaper/composables/__tests__/
└── useG8FormulaEngine.spec.ts         # 8个PBT属性 + fast-check

backend/tests/
└── test_g8_other_equity_instruments_pbt.py  # 后端PBT验证(hypothesis)
```

### 单元测试重点

- **Level3必填校验逻辑**：验证当fairValueLevel='Level3'时，valuationTechnique和unobservableInputDesc不能为空
- **异常自动检测逻辑**：验证当check1-5任一为false时，isAbnormal自动设为true
- **区段Tab行同步**：验证Tab切换后当前选中行索引不变
- **导入导出宽表分sheet**：验证G8-2导出2sheet、G8-4导出2sheet、G8-6导出3sheet
