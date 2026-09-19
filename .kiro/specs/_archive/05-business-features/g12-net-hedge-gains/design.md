# Design Document: G12 净敞口套期收益底稿专属HTML精美组件

## Overview

G12净敞口套期收益专属组件`g12-net-hedge-gains`。覆盖1个xlsx源模板/9有效sheet（排除"修订前"）。科目6103净敞口套期收益/损失（**损益类**）。**G循环中套期会计审计最复杂的科目**，含风险净敞口检查（79行5section复杂问卷）、套期公允价值测试（18列2区段）、套期关系明细（15列配对表）等特色审计内容。

核心架构：
- componentType `g12-net-hedge-gains`，主入口 GtG12NetHedgeGains.vue
- **sheetName v-if dispatch模式**：9 sheets用v-if分发（不用el-tabs）
- 子目录分组：core/ + hedging/ + voucher/
- 宽表拆分：G12-4公允价值测试(18列→2区段Tab) / G12-6凭证检查(19列→3区段Tab)
- **损益类科目公式**：审定 = 未审 + 调整（取发生额，非余额递推）；本期发生额=贷方-借方（净收益为正）
- 列为"本期/上期"模式（非期初/期末）：本期(未审|调整|审定) / 上期(未审|调整|审定)
- EventBus联动：publish `substantive:adjudicated`(accountCode='6103') + `disclosure:note-text-updated`
- **套期会计三要素**：被套期项目 + 套期工具 + 套期关系指定文档
- 特色：风险净敞口检查G12-5(79行5section问卷+虚拟滚动) + 公允价值测试G12-4(18列2区段) + 套期关系明细G12-2(15列配对)
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useG12ImportExport, 4张表) + AI(4 section)
- 六大集成：版本链✅ 抽凭✅ 截止✅ 附注EventBus✅ OCR✅ 复核✅

**与G10/G11关键差异**：
| 维度 | G10(贷方/负债) | G11(损益类/贷方) | G12(损益类/套期) |
|------|---------------|-----------------|-----------------|
| 科目方向 | 期末=期初+贷方-借方 | 本期发生额(贷-借) | **本期发生额(贷-借)** |
| Sheet数量 | 12 | 9 | **9** |
| 最大特色 | 衍生工具78行+分类检查 | 收益率分析 | **风险净敞口79行+套期有效性** |
| 公式引擎 | 6+parseNum(含calcCreditBalance/calcL3Reconciliation) | 6+parseNum(含calcAverageBalance/calcReturnRate) | **6+parseNum(含calcFVChange/calcHedgeIneffectiveness)** |
| 宽表 | G10-2(24列)/G10-5(18列)/G10-7(17列) | G11-5(17列) | **G12-4(18列)/G12-6(19列)** |
| AI section | 5 | 3 | **4** |
| 虚拟滚动 | G10-1(63行)/G10-7(99行)/G10-8(78行) | — | **G12-5(79行)/G12-6(90行)** |
| 导入导出 | 5张表 | 4张表 | **4张表** |

**套期会计审计核心逻辑**：
```
套期有效性 = 套期工具FV变动 能否抵销 被套期项目FV变动
套期无效部分 = |套期工具FV变动 - 被套期项目FV变动|（绝对差）
净敞口 = 被套期项目组合中多头净额 - 空头净额
```

## Architecture

### sheetName分发模式 + 子目录组织

GtG12NetHedgeGains.vue 接收 `sheetName` prop，用正则提取编码(G12A/G12-1~G12-6/附注披露(上市)/附注披露(国企)/底稿目录)，`v-if` 分发到对应子组件。

```
sheetName → regex提取编码 → v-if匹配 → defineAsyncComponent子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

9 sheets 子目录分组:
├── core/
│   ├── G12A    实质性程序表（35行×10列，复用a-program-console + 抽凭 + 截止）
│   ├── G12-1   审定表（23行×11列，损益类/本期上期模式）
│   ├── G12-3   调整分录汇总（23行×10列，AJE/RJE + 借贷平衡）
│   ├── 附注披露(上市)（12行×5列）
│   ├── 附注披露(国企)（11行×5列）
│   └── 底稿目录
├── hedging/
│   ├── G12-2   套期关系明细表（25行×15列，套期工具×被套期项目配对）
│   ├── G12-4   公允价值测试表（29行×18列→2区段Tab：套期工具/被套期项目）
│   └── G12-5   风险净敞口检查表（79行×10列，5section问卷+虚拟滚动）
└── voucher/
    └── G12-6   凭证检查表（90行×19列→3区段Tab + 抽凭 + OCR + 虚拟滚动）
```

### 高层数据流

```mermaid
graph TD
    TB[trial_balance<br/>科目6103<br/>取发生额] -->|自动取数| G12_1[G12-1 审定表]
    G12_1 -->|EventBus: substantive:adjudicated| NOTE_L[附注披露-上市]
    G12_1 -->|EventBus: substantive:adjudicated| NOTE_S[附注披露-国企]
    NOTE_L -->|EventBus: disclosure:note-text-updated| EXT[附注模块]
    NOTE_S -->|EventBus: disclosure:note-text-updated| EXT
    G12_3[G12-3 调整分录] -->|AJE/RJE汇总回写| G12_1
    G12_2[G12-2 套期关系明细] -->|套期无效部分汇总| G12_1
    G12_4[G12-4 公允价值测试] -->|FV变动比对| G12_2
    G12_5[G12-5 风险净敞口检查] -->|有效性结论引用| G12_2
    G12_5 -->|净敞口验证| G12_4
    G12A[G12A 程序表] -->|抽凭引擎| VOUCHER[GtVoucherSamplingEngine]
    G12A -->|截止提取| CUTOFF[useCutoffAutoSampling]
    G12_6[G12-6 凭证检查] -->|抽凭引擎| VOUCHER
    G12_6 -->|行级OCR| OCR[/d4/contract-ocr]
    MAIN[GtG12NetHedgeGains] -->|autoSnapshot| VER[useVersionTrail]
    MAIN -->|provide openReviewDialog| CHILDREN[所有子组件]
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtG12NetHedgeGains.vue                        # 主入口 sheetName v-if分发（defineAsyncComponent lazy×9）
├── g12-net-hedge-gains/
│   ├── core/
│   │   ├── G12TabProcedure.vue                   # G12A 程序表（复用a-program-console+selfLoad+抽凭+截止）
│   │   ├── G12TabAdjudication.vue                # G12-1 审定表（23行×11列，损益类本期/上期）
│   │   ├── G12TabAdjustment.vue                  # G12-3 调整分录(AJE/RJE+借贷校验)
│   │   ├── G12TabDisclosureListed.vue            # 附注披露(上市)(12行×5列)
│   │   ├── G12TabDisclosureSOE.vue               # 附注披露(国企)(11行×5列)
│   │   └── G12TabDirectory.vue                   # 底稿目录
│   ├── hedging/
│   │   ├── G12TabHedgeDetail.vue                 # G12-2 套期关系明细(25行×15列)
│   │   ├── G12TabFairValueTest.vue               # G12-4 公允价值测试(18列→2区段Tab)
│   │   └── G12TabNetExposureCheck.vue            # G12-5 风险净敞口检查(79行5section+虚拟滚动)
│   └── voucher/
│       └── G12TabVoucherCheck.vue                # G12-6 凭证检查(19列→3区段Tab+OCR+虚拟滚动90行)
├── composables/
│   ├── useG12FormulaEngine.ts                    # G12公式引擎(6个纯函数+parseNum)
│   ├── useG12FormData.ts                         # 数据加载/保存/selfLoad/writebackTB
│   ├── useG12ImportExport.ts                     # 导入导出composable(4张表: G12-2/G12-3/G12-4/G12-6)
│   └── useG12DualMode.ts                         # 双模式OO切换+localStorage

backend/app/routers/wp_render_strategies/
├── _g12_net_hedge_gains.py                       # render策略+注册RENDERER_DISPATCH
├── _g12_net_hedge_gains_service.py               # 业务逻辑(公式验证/TB取数/EventBus)
├── _g12_net_hedge_gains_import_export.py         # 导入导出端点(4张表×3=12端点)
└── _g12_net_hedge_gains_ai.py                    # AI生成4 section
```

### EventBus事件

| 事件名 | 发布者 | 消费者 | payload |
|--------|--------|--------|---------|
| `substantive:adjudicated` | G12-1审定表 | 附注披露(上市/国企) + trial_balance | `{accountCode:'6103', adjudicatedAmount}` |
| `disclosure:note-text-updated` | 附注披露 | 附注模块 | `{accountCode:'6103', text}` |

### 后端AI Section清单

```
adjudication-analysis / hedge-effectiveness-conclusion / net-position-conclusion / voucher-conclusion
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtG12NetHedgeGains.vue props
interface G12NetHedgeGainsProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// sheetName正则匹配映射
const SHEET_CODE_MAP: Record<string, string> = {
  'G12A': 'procedure',
  'G12-1': 'adjudication',
  'G12-2': 'hedgeDetail',
  'G12-3': 'adjustment',
  'G12-4': 'fairValueTest',
  'G12-5': 'netExposureCheck',
  'G12-6': 'voucherCheck',
  '附注披露信息（上市公司）': 'disclosureListed',
  '附注披露信息（国企）': 'disclosureSOE',
  '底稿目录': 'directory',
}
```

### G12-1 审定表数据模型（23行×11列，损益类本期/上期模式）

```typescript
interface G12AdjudicationData {
  rows: G12AdjudicationRow[]
  totals: G12AdjudicationTotals
  trialBalanceAmount: number           // 试算表取数(科目6103发生额)
  variance: number                     // 差异=审定-试算表
}

interface G12AdjudicationRow {
  id: string
  item: string                         // 项目名称（净敞口套期收益/套期工具公允价值变动/被套期项目公允价值变动等）
  // 本期
  currentUnadjusted: number            // 本期未审数
  currentAdjustment: number            // 本期调整
  currentAdjusted: number              // 公式: 未审 + 调整
  // 上期
  priorUnadjusted: number              // 上期未审数
  priorAdjustment: number              // 上期调整
  priorAdjusted: number                // 公式: 未审 + 调整
  // 变动
  changeAmount: number                 // 公式: 本期审定 - 上期审定
  changeRate: number | null            // 公式: (本期-上期)/|上期|, 上期=0时null
  reasonAnalysis: string               // |变动率|>20%时必填(橙色高亮)
  indexRef: string                     // 索引号
}

interface G12AdjudicationTotals {
  currentAdjusted: number
  priorAdjusted: number
  changeAmount: number
  changeRate: number | null
}
```

### G12-2 套期关系明细表数据模型（25行×15列）

```typescript
interface G12HedgeDetailRow {
  id: string
  seq: number
  hedgeRelationId: string              // 套期关系编号
  hedgeType: 'fair_value' | 'cash_flow' | 'net_investment'  // 套期类型(下拉：公允价值/现金流量/净投资)
  hedgedItem: string                   // 被套期项目
  hedgingInstrument: string            // 套期工具
  designationDate: string              // 指定日期
  maturityDate: string                 // 到期日
  hedgedRisk: string                   // 被套期风险
  hedgeRatio: number                   // 套期比率
  instrumentFVChange: number           // 本期套期工具FV变动
  itemFVChange: number                 // 本期被套期项目FV变动
  ineffectiveness: number              // 套期无效部分(公式: |instrumentFVChange - itemFVChange|)
  profitLossAmount: number             // 计入损益金额
  effectivenessConclusion: 'effective' | 'ineffective' | 'partially_effective'  // 有效性评估结论(下拉)
  indexRef: string                     // 索引
  remark: string                       // 备注
}
```

### G12-3 调整分录数据模型（23行×10列）

```typescript
interface G12AdjustmentEntry {
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

### G12-4 公允价值测试表数据模型（29行×18列→2区段Tab）

```typescript
interface G12FairValueTestRow {
  id: string
  seq: number
  hedgeRelationId: string              // 套期关系编号（两Tab行同步key）

  // ══ Tab1: 套期工具侧(9列) ══
  instrumentName: string               // 套期工具名称
  instrumentType: string               // 工具类型(下拉: 利率互换/远期合约/期权/期货/其他)
  instrumentOpeningFV: number          // 期初公允价值
  instrumentClosingFV: number          // 期末公允价值
  instrumentFVChange: number           // FV变动(公式: 期末-期初)
  instrumentValuationMethod: string    // 估值方法
  instrumentFVLevel: 'Level1' | 'Level2' | 'Level3'  // 公允价值层次
  instrumentValuationSource: string    // 估值来源

  // ══ Tab2: 被套期项目侧(9列) ══
  itemName: string                     // 被套期项目名称
  itemType: string                     // 项目类型(下拉: 固定利率贷款/存货/确定承诺/预期交易/其他)
  itemOpeningFV: number                // 期初公允价值
  itemClosingFV: number                // 期末公允价值
  itemFVChange: number                 // FV变动(公式: 期末-期初)
  itemRiskFactor: string               // 风险因素(利率/汇率/商品价格/信用)
  itemTestMethod: string               // 测试方法(下拉: 回归分析/美元抵销/假设衍生工具)
  itemEffectivenessConclusion: 'effective' | 'ineffective' | 'partially_effective'  // 有效性结论(下拉)
}
```

### G12-5 风险净敞口检查表数据模型（79行×10列，5section问卷）

```typescript
interface G12NetExposureCheckData {
  sections: G12NetExposureSection[]
  overallConclusion: string            // 综合审计结论(textarea)
  methodologyContext: string           // 方法论上下文(CAS24套期会计三要素+有效性条件)
}

interface G12NetExposureSection {
  id: string
  sectionNo: string                    // (一)~(五)
  title: string
  // (一) 套期关系指定：指定文档完整性/套期目标/风险管理策略
  // (二) 套期有效性测试：前瞻性/回顾性测试方法和结果
  // (三) 净敞口头寸计算：多头/空头/净敞口金额验证
  // (四) 再平衡和终止：套期比率调整/终止确认条件
  // (五) 会计处理检查：套期收益/损失的会计处理正确性
  rows: G12NetExposureRow[]
}

interface G12NetExposureRow {
  id: string
  seq: number                          // 序号
  checkArea: string                    // 检查区域
  checkItem: string                    // 检查项目
  auditRequirement: string             // 审计要求(方法论)
  checkResult: string                  // 检查结果(textarea)
  compliance: 'compliant' | 'non_compliant' | 'not_applicable'  // 是否合规(下拉)
  riskLevel: 'high' | 'medium' | 'low' | ''  // 风险等级(下拉)
  conclusion: string                   // 结论(textarea)
  indexRef: string                     // 索引
  remark: string                       // 备注
}
```

### G12-6 凭证检查表数据模型（90行×19列→3区段Tab）

```typescript
interface G12VoucherCheckRow {
  id: string
  seq: number
  // ══ Tab1: 凭证基础(7列) ══
  voucherDate: string                  // 日期
  voucherNo: string                    // 凭证编号
  businessContent: string              // 业务内容
  hedgeRelationId: string              // 关联套期关系编号
  counterAccount: string               // 对方科目
  debitAmount: number                  // 借方金额
  creditAmount: number                 // 贷方金额

  // ══ Tab2: 核对内容(7列) ══
  attachment: string | null            // 📎附件路径(OCR触发)
  supportingDocDesc: string            // 支持性文件描述
  check1OriginalComplete: boolean      // 核对1-原始凭证完整
  check2Authorization: boolean         // 核对2-授权批准
  check3Accounting: boolean            // 核对3-账务处理正确
  check4HedgeDesignation: boolean      // 核对4-套期关系指定文档匹配
  check5FVValuation: boolean           // 核对5-公允价值估值依据

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
interface G12DisclosureSection {
  id: string
  title: string
  rows?: G12DisclosureRow[]
  textContent?: string                 // 文本区内容（AI辅助）
}

interface G12DisclosureRow {
  id: string
  label: string
  value: string | number
  editable: boolean
}
```

## Data Models

### 存储结构（working_paper.content JSON）

```typescript
interface G12Content {
  // G12-1 审定表
  adjudication: {
    rows: G12AdjudicationRow[]
    totals: G12AdjudicationTotals
  }
  // G12-2 套期关系明细
  hedgeDetail: {
    rows: G12HedgeDetailRow[]
  }
  // G12-3 调整分录
  adjustment: {
    entries: G12AdjustmentEntry[]
  }
  // G12-4 公允价值测试
  fairValueTest: {
    rows: G12FairValueTestRow[]
    conclusion: string                 // 审计结论
  }
  // G12-5 风险净敞口检查
  netExposureCheck: G12NetExposureCheckData
  // G12-6 凭证检查
  voucherCheck: {
    rows: G12VoucherCheckRow[]
  }
  // 附注
  disclosureListed: { sections: G12DisclosureSection[] }
  disclosureSOE: { sections: G12DisclosureSection[] }
}
```

### API接口

```python
# _g12_net_hedge_gains.py
# RENDERER_DISPATCH注册
def render_g12_net_hedge_gains(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='g12-net-hedge-gains'和sheets配置"""

# _g12_net_hedge_gains_import_export.py
POST /api/workpapers/{wp_id}/g12/export-template?sheet={code}
POST /api/workpapers/{wp_id}/g12/export-data?sheet={code}
POST /api/workpapers/{wp_id}/g12/import-data?sheet={code}  # multipart/form-data
# sheet codes: G12-2 / G12-3 / G12-4 / G12-6
# 宽表按区段分sheet导出：
#   G12-4(2sheet: 套期工具/被套期项目) / G12-6(3sheet: 凭证基础/核对内容/结论)
#   G12-2(1sheet) / G12-3(1sheet)

# _g12_net_hedge_gains_ai.py
POST /api/workpapers/{wp_id}/g12/ai/{section}
# section: adjudication-analysis / hedge-effectiveness-conclusion /
#          net-position-conclusion / voucher-conclusion

# _g12_net_hedge_gains_service.py
class G12NetHedgeGainsService:
    async def get_trial_balance_data(project_id, year) -> dict
    async def save_adjudication(wp_id, data) -> dict
    async def validate_formulas(data) -> list[ValidationError]
```

### trial_balance 取数

```sql
-- G12-1审定表自动取数（损益类，取发生额）
-- 损益类：本期发生额 = 贷方发生额 - 借方发生额（净收益为正）
SELECT standard_account_code, unadjusted_amount, aje_adjustment, audited_amount
FROM trial_balance
WHERE project_id = :project_id
  AND year = :year
  AND standard_account_code LIKE '6103%'
```

### 注册四件套

```python
# 1. htmlRendererRegistry (前端)
'g12-net-hedge-gains': () => import('./workpaper/GtG12NetHedgeGains.vue')

# 2. wp_code_overrides.json (10条)
{
  "G12A-净敞口套期收益审计程序表": "g12-net-hedge-gains",
  "G12-1-审定表": "g12-net-hedge-gains",
  "G12-2-明细表": "g12-net-hedge-gains",
  "G12-3-调整分录汇总": "g12-net-hedge-gains",
  "G12-4-公允价值测试表": "g12-net-hedge-gains",
  "G12-5-风险净敞口检查表": "g12-net-hedge-gains",
  "G12-6-凭证检查表": "g12-net-hedge-gains",
  "G12-附注披露信息（上市公司）": "g12-net-hedge-gains",
  "G12-附注披露信息（国企）": "g12-net-hedge-gains",
  "G12-底稿目录": "g12-net-hedge-gains"
}

# 3. VALID_COMPONENT_TYPES (后端)
'g12-net-hedge-gains'

# 4. RENDERER_DISPATCH (后端)
'g12-net-hedge-gains': render_g12_net_hedge_gains
```

## Integration Design（6大集成接入点）

### 1. 版本链 (useVersionTrail)

```typescript
// GtG12NetHedgeGains.vue 主入口
const { autoSnapshot, showVersionTrail } = useVersionTrail(wpId)

async function handleSave() {
  await saveData()
  await autoSnapshot()  // 触发版本快照
}
// 工具栏"版本历史"按钮 → GtWpVersionTrail drawer
```

### 2. 抽凭引擎 (G12A程序表 + G12-6凭证检查)

```typescript
// G12TabProcedure.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['6103']"
  dialog-mode
  @samples-ready="fillSamples"
/>

// G12TabVoucherCheck.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['6103']"
  dialog-mode
  @samples-ready="fillVoucherRows"
/>
```

### 3. 截止自动提取 (useCutoffAutoSampling)

```typescript
// G12TabProcedure.vue 截止测试步骤
const { fetchCutoffSamples } = useCutoffAutoSampling({
  projectId, accountCode: '6103', days: 5
})
```

### 4. 附注EventBus

```typescript
// G12TabAdjudication.vue (发布者)
watch(reportAmount, (val) => {
  eventBus.publish('substantive:adjudicated', {
    accountCode: '6103',
    adjudicatedAmount: val
  })
})

// G12TabDisclosureListed.vue / G12TabDisclosureSOE.vue (消费者)
eventBus.subscribe('substantive:adjudicated', (payload) => {
  if (payload.accountCode === '6103') refreshData()
})

// 附注文本变更发布
eventBus.publish('disclosure:note-text-updated', {
  accountCode: '6103', text: noteText
})
```

### 5. 行级OCR (G12-6 📎附件列)

```typescript
// G12TabVoucherCheck.vue
async function handleOCR(row: G12VoucherCheckRow, file: File) {
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
// GtG12NetHedgeGains.vue (主入口)
const { openReviewDialog } = useReviewDialog(wpId)
provide('openReviewDialog', openReviewDialog)

// 子组件 (section标题栏右侧按钮)
const openReviewDialog = inject('openReviewDialog')
```

## 宽表区段Tab拆分详细设计

### G12-4 公允价值测试表（18列→2区段Tab）

```
┌─────────────────────────────────────────────────────────────────┐
│ 方法论上下文（琥珀色左边线+浅黄背景）                             │
│ "套期有效性测试核心原则(CAS24):                                   │
│   ① 被套期项目与套期工具之间存在经济关系                          │
│   ② 信用风险的影响不主导经济关系中的价值变动                      │
│   ③ 套期比率应等于被套期项目/套期工具实际数量之比"                 │
│                                                                 │
│ ┌──────────────────────────┐ ┌───────────────────────────┐      │
│ │Tab1: 套期工具侧(9列)      │ │Tab2: 被套期项目侧(9列)     │ 区段Tab│
│ └──────────────────────────┘ └───────────────────────────┘      │
│                                                                 │
│ Tab1: 套期关系编号|工具名称|工具类型(下拉)|期初FV|期末FV|          │
│       FV变动(公式)|估值方法|公允价值层次|估值来源                  │
│                                                                 │
│ Tab2: 套期关系编号|项目名称|项目类型(下拉)|期初FV|期末FV|          │
│       FV变动(公式)|风险因素|测试方法(下拉)|有效性结论(下拉)        │
│                                                                 │
│ 底部：审计结论textarea(AI辅助: hedge-effectiveness-conclusion)    │
│ 行同步：Tab切换保持行索引（通过套期关系编号关联）                  │
│ 动态行：ElMessageBox.prompt输入套期关系编号→创建行                │
└─────────────────────────────────────────────────────────────────┘
```

### G12-5 风险净敞口检查表（79行×10列，5section问卷+虚拟滚动）

```
┌─────────────────────────────────────────────────────────────────┐
│ 方法论上下文（琥珀色左边线+浅黄背景）                             │
│ "CAS24套期会计三要素+有效性条件：                                 │
│   三要素：被套期项目+套期工具+套期关系正式指定                     │
│   有效性条件：                                                   │
│   ① 被套期项目与套期工具之间存在经济关系                          │
│   ② 信用风险的影响不主导价值变动                                  │
│   ③ 套期比率=实际对冲数量/风险管理实际使用比率                    │
│   净敞口=合格被套期项目组合中多头净额-空头净额"                    │
│                                                                 │
│ ═══ (一) 套期关系指定 ═══════════════════ [AI] [复核] ═════════ │
│ │序号│检查区域│检查项目│审计要求│检查结果│合规│风险│结论│索引│备注│ │
│ │ 1  │指定文档│...    │...    │textarea│下拉│下拉│... │... │... │ │
│ │ 2  │套期目标│...    │...    │textarea│下拉│下拉│... │... │... │ │
│ │ ...│风险策略│...    │...    │textarea│下拉│下拉│... │... │... │ │
│                                                                 │
│ ═══ (二) 套期有效性测试 ═════════════════ [AI] [复核] ═════════ │
│ │ ... (前瞻性/回顾性测试方法和结果)                              │
│                                                                 │
│ ═══ (三) 净敞口头寸计算 ═════════════════ [AI] [复核] ═════════ │
│ │ ... (多头/空头/净敞口金额验证)                                 │
│                                                                 │
│ ═══ (四) 再平衡和终止 ═══════════════════ [AI] [复核] ═════════ │
│ │ ... (套期比率调整/终止确认条件)                                │
│                                                                 │
│ ═══ (五) 会计处理检查 ═══════════════════ [AI] [复核] ═════════ │
│ │ ... (套期收益/损失的会计处理正确性)                            │
│                                                                 │
│ 虚拟滚动：79行全表启用                                           │
│ 综合审计结论 textarea(AI辅助: net-position-conclusion)            │
│ <details>编制提示</details>                                      │
└─────────────────────────────────────────────────────────────────┘
```

### G12-6 凭证检查表（19列→3区段Tab）

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌──────────────────┐ ┌──────────────────┐ ┌──────────┐         │
│ │Tab1: 凭证基础(7列)│ │Tab2: 核对内容(7列)│ │Tab3: 结论(5列)│ 3区段│
│ └──────────────────┘ └──────────────────┘ └──────────┘         │
│                                                                 │
│ Tab1: 日期|凭证编号|业务内容|关联套期关系|对方科目|借方|贷方       │
│                                                                 │
│ Tab2: 📎附件|文件描述|✓完整|✓授权|✓账务正确|✓套期指定匹配|✓估值依据│
│       (📎点击→上传→OCR识别→ElMessageBox确认→填入)                 │
│       (任一✗→Tab3"是否异常"自动置"是")                            │
│                                                                 │
│ Tab3: 索引号(GtIndexChip)|是否异常|异常说明|风险等级|备注          │
│                                                                 │
│ 顶部：借贷差额汇总（差额≠0红色）                                 │
│ 虚拟滚动：90行                                                   │
│ 行同步：3个Tab间切换保持行索引                                    │
└─────────────────────────────────────────────────────────────────┘
```

## Formula Engine Design (useG12FormulaEngine.ts)

### 6个纯函数 + parseNum

```typescript
/**
 * 安全数值转换：null/undefined/NaN/空字符串/'  '/'abc' → 0; 有效数值→原值
 */
export function parseNum(v: unknown): number

/**
 * 审定数 = 未审数 + 调整
 * 损益类通用公式（本期/上期均适用）
 */
export function calcAdjustedAmount(unadjusted: number, adjustment: number): number

/**
 * 变动率 = (current - prior) / |prior|
 * prior=0时返回null（避免除零）
 * 注意：损益类取绝对值分母，避免负数发生额导致方向错误
 */
export function calcChangeRate(prior: number, current: number): number | null

/**
 * 公允价值变动 = 期末公允价值 - 期初公允价值
 * 用于G12-4套期工具和被套期项目双侧FV变动计算
 */
export function calcFVChange(opening: number, closing: number): number

/**
 * 套期无效部分 = |套期工具FV变动 - 被套期项目FV变动|
 * 核心套期会计公式：绝对差衡量无效对冲部分
 * 完全有效时结果为0，差距越大无效部分越大
 */
export function calcHedgeIneffectiveness(instrumentChange: number, itemChange: number): number

/**
 * 借贷平衡校验：|SUM(debits) - SUM(credits)| < 0.01
 * G12-3调整分录验证
 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean
```

### 公式引用关系

```
G12-1 审定表(损益类，本期/上期):
  currentAdjusted = calcAdjustedAmount(currentUnadjusted, currentAdjustment)
  priorAdjusted = calcAdjustedAmount(priorUnadjusted, priorAdjustment)
  changeAmount = currentAdjusted - priorAdjusted
  changeRate = calcChangeRate(priorAdjusted, currentAdjusted)

G12-2 套期关系明细:
  ineffectiveness = calcHedgeIneffectiveness(instrumentFVChange, itemFVChange)
  // 有效性结论依赖：ineffectiveness 是否在可接受范围内

G12-3 调整分录:
  balanced = isDebitCreditBalanced(allDebits, allCredits)

G12-4 公允价值测试:
  instrumentFVChange = calcFVChange(instrumentOpeningFV, instrumentClosingFV)
  itemFVChange = calcFVChange(itemOpeningFV, itemClosingFV)
  // 两Tab各自独立计算FV变动

G12-4 vs G12-2 联动:
  G12-4.instrumentFVChange ↔ G12-2.instrumentFVChange (交叉验证)
  G12-4.itemFVChange ↔ G12-2.itemFVChange (交叉验证)

G12-1 vs 试算表:
  currentUnadjusted ← trial_balance.unadjusted_amount (6103发生额)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 审定数公式

*For any* unadjusted, adjustment ∈ ℝ: `calcAdjustedAmount(unadjusted, adjustment)` === `unadjusted + adjustment`

**Validates: Requirements 2.3, 6.2**

### Property 2: 公允价值变动

*For any* opening, closing ∈ ℝ: `calcFVChange(opening, closing)` === `closing - opening`

**Validates: Requirements 4.2, 6.2**

### Property 3: 套期无效部分绝对差

*For any* instrumentChange, itemChange ∈ ℝ: `calcHedgeIneffectiveness(instrumentChange, itemChange)` === `|instrumentChange - itemChange|`

**Validates: Requirements 3.2, 6.3**

### Property 4: 套期无效部分非负性

*For any* instrumentChange, itemChange ∈ ℝ: `calcHedgeIneffectiveness(instrumentChange, itemChange)` ≥ 0

**Validates: Requirements 3.2, 6.3**

### Property 5: 变动率除零保护

*For any* current ∈ ℝ: `calcChangeRate(0, current)` === null;
*For any* current > prior > 0: `calcChangeRate(prior, current)` > 0;
*For any* 0 < current < prior: `calcChangeRate(prior, current)` < 0

**Validates: Requirements 6.2**

### Property 6: 借贷平衡恒等

*For any* debits[], credits[] ∈ ℝ[]: `isDebitCreditBalanced(debits, credits)` ↔ (|SUM(debits) - SUM(credits)| < 0.01)

**Validates: Requirements 3.4, 6.2**

### Property 7: parseNum健壮性

*For any* input ∈ {null, undefined, '', NaN, '  ', 'abc'}: `parseNum(input)` === 0;
*For any* n ∈ ℝ (finite): `parseNum(n)` === n

**Validates: Requirements 6.2**

## Error Handling

| 场景 | 处理策略 |
|------|---------|
| render-config 加载失败 | selfLoad重试1次 → 失败显示"加载失败"占位 + 重试按钮 |
| trial_balance 取数无数据 | 审定表显示0值 + 橙色提示"未找到科目6103数据" |
| 公式计算溢出/NaN | parseNum兜底→0，公式列显示"—" |
| 导入Excel格式不匹配 | 后端返回422 + 具体列错误信息 → 前端ElMessage.error |
| EventBus消息丢失 | 附注组件mounted时主动拉取最新审定数（非纯被动监听） |
| 保存时网络异常 | 自动重试3次(指数退避) → 失败后localStorage暂存 + 恢复提示 |
| sheetName无法识别 | fallback到OnlyOffice渲染（确保不白屏） |
| G12-5虚拟滚动渲染异常 | 降级为分页模式(每页30行) |
| G12-6虚拟滚动渲染异常 | 同G12-5降级策略 |
| OCR识别失败 | ElMessage.warning提示 + 允许手动填入 |
| G12-5(79行)首次加载慢 | skeleton占位 + 分section懒渲染 |
| G12-4两Tab行同步失效 | 通过套期关系编号强制重同步 |
| 套期无效部分公式异常 | 后端校验calcHedgeIneffectiveness与G12-2数据对比，差异>1告警 |
| G12-5问卷下拉未选择 | 保存时阻断 + 高亮未填项 + toast提示 |
| 套期关系编号重复 | G12-2新增行时校验编号唯一性 |
| G12-4/G12-2 FV变动交叉不一致 | 黄色告警提示数据不匹配（不阻断） |

## Testing Strategy

### 测试分层

| 层 | 工具 | 范围 | 数量估计 |
|----|------|------|---------|
| PBT(前端) | vitest + fast-check | 6个公式函数×7属性 | ~9 test cases |
| PBT(后端) | pytest + hypothesis | 公式验证 | ~7 test cases |
| 单元测试(前端) | vitest | composable逻辑/数据转换/交叉验证/异常检测 | ~18 test cases |
| 单元测试(后端) | pytest | service/renderer/import-export | ~10 test cases |
| 集成测试 | pytest | API端点(12导入导出+4AI+render) | ~8 test cases |
| E2E | Playwright | 关键用户路径(审定+套期明细+净敞口检查+公允价值测试) | ~5 scenarios |

### PBT配置

- 前端：fast-check，`numRuns: 100`
- 后端：hypothesis，`max_examples=5`
- 每个PBT测试注释标注对应属性编号
- Tag格式：`Feature: g12-net-hedge-gains, Property {N}: {描述}`

### 关键测试路径

1. **审定表完整流程（损益类本期/上期）**：TB取数(6103发生额) → 损益类公式(贷-借) → 填写调整 → 审定计算 → 变动率 → EventBus发布 → 附注刷新
2. **套期关系明细+无效部分**：新增套期关系 → 填写FV变动 → calcHedgeIneffectiveness自动计算 → 有效性结论下拉 → 导入导出
3. **公允价值测试(2区段Tab)**：套期工具侧填写 → calcFVChange → 被套期项目侧填写 → calcFVChange → 行同步验证 → 与G12-2交叉比对
4. **风险净敞口检查(79行问卷)**：方法论上下文CAS24 → 5section逐项检查 → 虚拟滚动 → 每section AI辅助 → 综合结论
5. **凭证检查流程**：抽凭引擎→样本填入 → Tab2核对5项(含套期指定+估值依据) → 任一✗自动异常 → OCR识别→确认填入

### PBT测试文件

```
audit-platform/frontend/src/components/workpaper/composables/__tests__/
└── useG12FormulaEngine.spec.ts        # 7个PBT属性 + fast-check

backend/tests/
└── test_g12_net_hedge_gains_pbt.py    # 后端PBT验证(hypothesis)
```

### 单元测试重点

- **损益类公式方向验证**：验证calcAdjustedAmount用于本期/上期模式正确（审定=未审+调整）
- **套期无效部分核心逻辑**：验证calcHedgeIneffectiveness在各种正负组合下的绝对差正确性
- **交叉验证逻辑**：G12-4的FV变动 vs G12-2的FV变动匹配校验
- **区段Tab行同步**：验证Tab切换后当前选中行索引不变（通过套期关系编号关联）
- **异常自动检测逻辑**：验证当check1-5任一为false时，isAbnormal自动设为true
- **虚拟滚动(79行/90行)**：验证G12-5和G12-6启用虚拟滚动且section折叠正确
- **导入导出宽表分sheet**：验证G12-4导出2sheet、G12-6导出3sheet
- **|变动率|>20%触发**：验证橙色高亮和原因分析必填联动
- **套期关系编号唯一性**：验证G12-2新增行时编号重复校验
