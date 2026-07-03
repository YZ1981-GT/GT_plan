# Design Document: G7 长期股权投资(子公司组)底稿专属HTML精美组件

## Overview

G7长期股权投资(子公司组)专属组件`g7-long-term-equity-subsidiary`。覆盖源模板22个sheet中的7个sheet。科目1511长期股权投资（借方/资产类）。**本组聚焦子公司投资的初始→后续→处置全生命周期测试**：初始判断(G7-7)→同控取得(G7-8)/非同控取得(G7-9)→后续计量(G7-10)→处置(G7-11/G7-12)→凭证检查(G7-18)。

核心架构：
- componentType `g7-long-term-equity-subsidiary`，主入口 GtG7LongTermEquitySubsidiary.vue
- **sheetName v-if dispatch模式**：7 sheets用v-if分发（不用el-tabs）
- 子目录分组：initial/ + subsequent/ + disposal/ + voucher/
- 宽表拆分：G7-18(19列→3区段Tab)；G7-11/G7-12(14列单表可接受)
- 借方科目公式：期末未审 = 期初审定 + 借方发生额 - 贷方发生额
- 核心特色：控制判断CAS33六要素问卷(G7-7) + 同控/非同控合并判定(G7-8/G7-9) + 分步合并投资成本确认
- EventBus联动：无附注EventBus（本组不含附注sheet）
- 四大集成：版本链✅ 抽凭✅(G7-18) 行级OCR✅(G7-18) 复核✅
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useG7SubImportExport, 6张表) + AI(5 section)

## Architecture

### sheetName分发模式 + 子目录组织

GtG7LongTermEquitySubsidiary.vue 接收 `sheetName` prop，用正则提取编码(G7-7/G7-8/G7-9/G7-10/G7-11/G7-12/G7-18)，`v-if` 分发到对应子组件。

```
sheetName → regex提取编码 → v-if匹配 → defineAsyncComponent子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

7 sheets 子目录分组:
├── initial/
│   ├── G7-7   初始判断决策树（47行×9列，CAS33控制六要素问卷）
│   ├── G7-8   同控初始计量测试（52行×9列，账面价值法）
│   └── G7-9   非同控初始计量测试（53行×9列，公允价值法+商誉）
├── subsequent/
│   └── G7-10  后续计量测试表（48行×9列，成本法：股利+减值）
├── disposal/
│   ├── G7-11  处置（非一揽子）（47行×14列，单次处置损益）
│   └── G7-12  处置（一揽子）（54行×14列，多次交易追溯调整）
└── voucher/
    └── G7-18  凭证检查表（99行×19列→3区段Tab + 抽凭引擎 + 行级OCR）
```

### 高层数据流

```mermaid
graph TD
    G7_7[G7-7 初始判断] -->|控制类型结论| G7_8[G7-8 同控合并]
    G7_7 -->|控制类型结论| G7_9[G7-9 非同控合并]
    G7_8 -->|初始入账成本| G7_10[G7-10 后续计量]
    G7_9 -->|初始入账成本+商誉| G7_10
    G7_10 -->|期末账面| G7_11[G7-11 处置-非一揽子]
    G7_10 -->|期末账面| G7_12[G7-12 处置-一揽子]
    G7_18[G7-18 凭证检查] -->|抽凭引擎| VOUCHER[GtVoucherSamplingEngine]
    G7_18 -->|行级OCR| OCR[/d4/contract-ocr]
    MAIN[GtG7LongTermEquitySubsidiary] -->|autoSnapshot| VER[useVersionTrail]
    MAIN -->|provide openReviewDialog| CHILDREN[所有子组件]
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtG7LongTermEquitySubsidiary.vue              # 主入口 sheetName v-if分发（defineAsyncComponent lazy×7）
├── g7-long-term-equity-subsidiary/
│   ├── initial/
│   │   ├── G7TabControlJudgment.vue              # G7-7 初始判断决策树（47行×9列，CAS33问卷）
│   │   ├── G7TabSameControlMeasurement.vue       # G7-8 同控初始计量（52行×9列，账面价值法）
│   │   └── G7TabNotSameControlMeasurement.vue    # G7-9 非同控初始计量（53行×9列，FV+商誉）
│   ├── subsequent/
│   │   └── G7TabSubsequentMeasurement.vue        # G7-10 后续计量（48行×9列，成本法）
│   ├── disposal/
│   │   ├── G7TabDisposalSingle.vue               # G7-11 处置-非一揽子（47行×14列）
│   │   └── G7TabDisposalPackage.vue              # G7-12 处置-一揽子（54行×14列）
│   └── voucher/
│       └── G7TabVoucherCheck.vue                 # G7-18 凭证检查（99行×19列→3区段Tab+OCR）
├── composables/
│   ├── useG7SubFormulaEngine.ts                  # G7子公司组公式引擎(7个纯函数+parseNum)
│   ├── useG7SubFormData.ts                       # 数据加载/保存/selfLoad
│   ├── useG7SubImportExport.ts                   # 导入导出composable(6张表)
│   └── useG7SubDualMode.ts                       # 双模式OO切换+localStorage

backend/app/routers/wp_render_strategies/
├── _g7_long_term_equity_subsidiary.py            # render策略+注册RENDERER_DISPATCH
├── _g7_long_term_equity_subsidiary_service.py    # 业务逻辑(公式验证)
├── _g7_long_term_equity_subsidiary_import_export.py # 导入导出端点(6张表×3=18端点)
└── _g7_long_term_equity_subsidiary_ai.py         # AI生成5 section
```

### EventBus事件

本组无附注sheet，不发布`substantive:adjudicated`事件（由g7-long-term-equity-main的G7-1审定表负责）。

### 后端AI Section清单

```
control-judgment-conclusion / initial-measurement-conclusion / subsequent-conclusion / disposal-conclusion / voucher-conclusion
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtG7LongTermEquitySubsidiary.vue props
interface G7SubsidiaryProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// sheetName正则匹配映射
const SHEET_CODE_MAP: Record<string, string> = {
  'G7-7': 'controlJudgment',
  'G7-8': 'sameControlMeasurement',
  'G7-9': 'notSameControlMeasurement',
  'G7-10': 'subsequentMeasurement',
  'G7-11': 'disposalSingle',
  'G7-12': 'disposalPackage',
  'G7-18': 'voucherCheck',
}
```

### G7-7 初始判断决策树数据模型（47行×9列，CAS33问卷）

```typescript
interface G7ControlJudgmentData {
  sections: G7ControlSection[]
  overallConclusion: string            // 综合审计结论(textarea)
}

interface G7ControlSection {
  id: string
  sectionNo: string                    // (一)~(六) 对应CAS33六要素
  title: string
  // (一) 权力 — 投资方是否拥有对被投资方的权力
  // (二) 可变回报 — 投资方是否因参与被投资方的相关活动而享有可变回报
  // (三) 权力与回报的联系 — 投资方是否有能力运用权力影响回报
  // (四) 实质性权利判断 — 投资方持有的权利是否为实质性权利
  // (五) 代理人/委托人判断 — 投资方是否作为代理人行使权力
  // (六) 综合判断 — 控制/共同控制/重大影响/无重大影响结论
  rows: G7ControlRow[]
}

interface G7ControlRow {
  id: string
  seq: number
  dimension: string                    // 判断维度
  criterion: string                    // 判断标准（方法论预填）
  investeeName: string                 // 被投资单位
  judgmentResult: 'control' | 'joint_control' | 'significant_influence' | 'none'  // 判断结果(下拉)
  judgmentBasis: string                // 判断依据(textarea)
  riskFlag: 'high' | 'medium' | 'low' | 'none'  // 风险标识(下拉)
  auditConclusion: string              // 审计结论(textarea)
  indexRef: string                     // 索引(GtIndexChip)
}
```

### G7-8 同控初始计量数据模型（52行×9列）

```typescript
interface G7SameControlRow {
  id: string
  seq: number
  investeeName: string                 // 被投资单位名称
  mergerDate: string                   // 合并日
  mergerType: string                   // 合并方式(吸收合并/控股合并/新设合并 下拉)
  acquireeNetAssets: number            // 被合并方账面净资产
  shareholdingRatio: number            // 持股比例(小数)
  shareOfNetAssets: number             // 公式: acquireeNetAssets × shareholdingRatio
  initialCost: number                  // 初始投资成本(=享有份额)
  consideration: number                // 支付对价
  differenceHandling: string           // 差额处理(textarea)：调整资本公积/留存收益
  auditConclusion: string              // 审计结论(textarea)
}
```

### G7-9 非同控初始计量数据模型（53行×9列）

```typescript
interface G7NotSameControlRow {
  id: string
  seq: number
  investeeName: string                 // 被投资单位名称
  acquisitionDate: string              // 购买日
  mergerType: string                   // 合并方式(下拉)
  consideration: number                // 支付对价
  directFees: number                   // 直接相关费用
  initialCost: number                  // 公式: consideration + directFees
  acquireeNetAssetsFV: number          // 被购买方可辨认净资产公允价值
  shareholdingRatio: number            // 持股比例(小数)
  shareOfFV: number                    // 公式: acquireeNetAssetsFV × shareholdingRatio
  goodwill: number                     // 公式: initialCost - shareOfFV（正=商誉,负=营业外收入）
  auditConclusion: string              // 审计结论(textarea)
}
```

### G7-10 后续计量数据模型（48行×9列）

```typescript
interface G7SubsequentRow {
  id: string
  seq: number
  investeeName: string                 // 被投资单位名称
  openingBalance: number               // 期初账面
  additionInvestment: number           // 本期增加(追加投资)
  impairmentLoss: number               // 本期减值
  declaredDividend: number             // 被投资方宣告股利
  shareholdingRatio: number            // 持股比例(小数)
  investmentIncome: number             // 公式: declaredDividend × shareholdingRatio
  closingBalance: number               // 公式: openingBalance + additionInvestment - impairmentLoss
  companyEndingBalance: number         // 企业期末数
  variance: number                     // 公式: closingBalance - companyEndingBalance
  auditConclusion: string              // 审计结论(textarea)
}
```

### G7-11 处置测试表（非一揽子）数据模型（47行×14列）

```typescript
interface G7DisposalSingleRow {
  id: string
  seq: number
  investeeName: string                 // 被投资单位名称
  disposalDate: string                 // 处置日
  disposalRatio: number                // 处置比例(小数)
  disposalPrice: number                // 处置对价
  disposalDateBookValue: number        // 处置日长投账面
  disposalDateDividend: number         // 处置日应收股利
  priorOCICumulative: number           // 处置前OCI累计
  transferableOCI: number              // 可转损益OCI
  individualGain: number               // 公式: price - bookValue - dividend + transferableOCI
  consolidationAdjustment: number      // 合并报表调整
  consolidatedNetAssetShare: number    // 合并层面净资产份额
  consolidatedGain: number             // 公式: consolidationAdjustment相关计算
  auditConclusion: string              // 审计结论(textarea)
  indexRef: string                     // 索引(GtIndexChip)
}
```

### G7-12 处置测试表（一揽子交易）数据模型（54行×14列）

```typescript
interface G7DisposalPackageRow {
  id: string
  seq: number
  investeeName: string                 // 被投资单位名称
  transactionDate: string              // 各次交易日期
  transactionPrice: number             // 各次交易对价
  shareholdingChange: number           // 各次交易持股变动
  cumulativePrice: number              // 累计对价(公式: SUM of prior prices)
  cumulativeShareChange: number        // 累计持股变动(公式: SUM of prior changes)
  lossOfControlDate: string            // 丧失控制权日
  lossDateBookValue: number            // 丧失日长投账面
  remainingInvestmentFV: number        // 丧失日剩余投资公允价值
  retrospectiveAdjustment: number      // 追溯调整金额(公式)
  consolidatedGain: number             // 合并处置损益(公式)
  packageJudgmentBasis: string         // 一揽子判断依据(textarea)
  auditConclusion: string              // 审计结论(textarea)
  indexRef: string                     // 索引(GtIndexChip)
}
```

### G7-18 凭证检查表数据模型（99行×19列→3区段Tab）

```typescript
interface G7VoucherCheckRow {
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
  supportingDocDesc: string            // 支持性文件描述
  check1OriginalComplete: boolean      // 核对1-原始凭证完整
  check2Authorization: boolean         // 核对2-授权批准
  check3Accounting: boolean            // 核对3-账务处理正确
  check4AmountCorrect: boolean         // 核对4-金额正确
  check5Classification: boolean        // 核对5-科目分类正确
  check6InvestmentIncome: boolean      // 核对6-投资收益确认正确

  // ══ Tab3: 结论(5列) ══
  indexNo: string                      // 索引号(GtIndexChip)
  isAbnormal: boolean                  // 是否异常(Tab2任一✗→自动是)
  abnormalDesc: string                 // 异常说明(textarea)
  riskLevel: 'high' | 'medium' | 'low'  // 风险等级(下拉)
  remark: string                       // 备注
}
```

## Data Models

### 存储结构（working_paper.content JSON）

```typescript
interface G7SubContent {
  // G7-7 初始判断
  controlJudgment: G7ControlJudgmentData
  // G7-8 同控初始计量
  sameControlMeasurement: {
    rows: G7SameControlRow[]
    conclusion: string
  }
  // G7-9 非同控初始计量
  notSameControlMeasurement: {
    rows: G7NotSameControlRow[]
    conclusion: string
  }
  // G7-10 后续计量
  subsequentMeasurement: {
    rows: G7SubsequentRow[]
    conclusion: string
  }
  // G7-11 处置(非一揽子)
  disposalSingle: {
    rows: G7DisposalSingleRow[]
    conclusion: string
  }
  // G7-12 处置(一揽子)
  disposalPackage: {
    rows: G7DisposalPackageRow[]
    conclusion: string
  }
  // G7-18 凭证检查
  voucherCheck: {
    rows: G7VoucherCheckRow[]
  }
}
```

### API接口

```python
# _g7_long_term_equity_subsidiary.py
# RENDERER_DISPATCH注册
def render_g7_long_term_equity_subsidiary(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='g7-long-term-equity-subsidiary'和sheets配置"""

# _g7_long_term_equity_subsidiary_import_export.py
POST /api/workpapers/{wp_id}/g7-sub/export-template?sheet={code}
POST /api/workpapers/{wp_id}/g7-sub/export-data?sheet={code}
POST /api/workpapers/{wp_id}/g7-sub/import-data?sheet={code}  # multipart/form-data
# sheet codes: G7-8 / G7-9 / G7-10 / G7-11 / G7-12 / G7-18
# G7-18按3区段分sheet导出

# _g7_long_term_equity_subsidiary_ai.py
POST /api/workpapers/{wp_id}/g7-sub/ai/{section}
# section: control-judgment-conclusion / initial-measurement-conclusion /
#          subsequent-conclusion / disposal-conclusion / voucher-conclusion

# _g7_long_term_equity_subsidiary_service.py
class G7SubsidiaryService:
    async def save_control_judgment(wp_id, data) -> dict
    async def save_measurement(wp_id, sheet_code, data) -> dict
    async def validate_formulas(data) -> list[ValidationError]
```

### 注册四件套

```python
# 1. htmlRendererRegistry (前端)
'g7-long-term-equity-subsidiary': () => import('./workpaper/GtG7LongTermEquitySubsidiary.vue')

# 2. wp_code_overrides.json (7条)
{
  "G7-7-长期股权投资初始判断": "g7-long-term-equity-subsidiary",
  "G7-8-子公司初始计量测试（同控）": "g7-long-term-equity-subsidiary",
  "G7-9-子公司初始计量测试（非同控）": "g7-long-term-equity-subsidiary",
  "G7-10-子公司后续计量测试表": "g7-long-term-equity-subsidiary",
  "G7-11-处置子公司测试表（不包含一揽子交易）": "g7-long-term-equity-subsidiary",
  "G7-12-处置子公司测试表（一揽子交易）": "g7-long-term-equity-subsidiary",
  "G7-18-凭证检查表": "g7-long-term-equity-subsidiary"
}

# 3. VALID_COMPONENT_TYPES (后端)
'g7-long-term-equity-subsidiary'

# 4. RENDERER_DISPATCH (后端)
'g7-long-term-equity-subsidiary': render_g7_long_term_equity_subsidiary
```

## Integration Design（4大集成接入点）

### 1. 版本链 (useVersionTrail)

```typescript
// GtG7LongTermEquitySubsidiary.vue 主入口
const { autoSnapshot, showVersionTrail } = useVersionTrail(wpId)

async function handleSave() {
  await saveData()
  await autoSnapshot()  // 触发版本快照
}
// 工具栏"版本历史"按钮 → GtWpVersionTrail drawer
```

### 2. 抽凭引擎 (G7-18凭证检查)

```typescript
// G7TabVoucherCheck.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['1511']"
  dialog-mode
  @samples-ready="fillVoucherRows"
/>
```

### 3. 行级OCR (G7-18 📎附件列)

```typescript
// G7TabVoucherCheck.vue
async function handleOCR(row: G7VoucherCheckRow, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const result = await http.post('/d4/contract-ocr', formData)
  const confirmed = await ElMessageBox.confirm(
    `识别结果：${result.data.summary}，是否填入？`
  )
  if (confirmed) mergeOCRResult(row, result.data)
}
```

### 4. 复核对话 (provide/inject)

```typescript
// GtG7LongTermEquitySubsidiary.vue (主入口)
const { openReviewDialog } = useReviewDialog(wpId)
provide('openReviewDialog', openReviewDialog)

// 子组件 (section标题栏右侧按钮)
const openReviewDialog = inject('openReviewDialog')
```

## 宽表区段Tab拆分详细设计

### G7-18 凭证检查表（19列→3区段Tab）

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌──────────────┐ ┌──────────────┐ ┌──────────┐                │
│ │Tab1: 凭证基础(7)│ │Tab2: 核对内容(7)│ │Tab3: 结论(5)│  3区段Tab │
│ └──────────────┘ └──────────────┘ └──────────┘                │
│                                                                 │
│ Tab1: 日期|凭证编号|业务内容|对方科目|借方|贷方|📎附件             │
│       (📎点击→上传→OCR识别→ElMessageBox确认→填入)                │
│                                                                 │
│ Tab2: 文件描述|✓原始凭证|✓授权|✓账务|✓金额|✓分类|✓投资收益       │
│       (任一✗→Tab3"是否异常"自动置"是")                           │
│                                                                 │
│ Tab3: 索引号(GtIndexChip)|是否异常|异常说明|风险等级|备注         │
│                                                                 │
│ 顶部：借贷差额汇总（差额≠0红色）                                 │
│ 虚拟滚动：99行                                                   │
│ 行同步：3个Tab间切换保持行索引                                    │
└─────────────────────────────────────────────────────────────────┘
```

### G7-7 初始判断决策树（问卷式，无需区段拆分）

```
┌─────────────────────────────────────────────────────────────────┐
│ 方法论上下文（琥珀色左边线+浅黄背景）                             │
│ "CAS33控制的定义(六要素)：                                       │
│   ① 权力 — 主导被投资方相关活动的现时权利                        │
│   ② 可变回报 — 因参与相关活动而享有可变回报                      │
│   ③ 权力与回报的联系 — 有能力运用权力影响回报金额                │
│   ④ 实质性权利 — 权利是否为实质性(可行使)                        │
│   ⑤ 代理人判断 — 是否仅为代理人(非主要责任人)                    │
│   ⑥ 综合判断 — 控制三要素同时满足=控制"                         │
│                                                                 │
│ 蓝色渐变引导区（2列grid）：                                      │
│   Step1: 逐项填写六要素判断 → Step2: 确定控制类型                │
│   Step3: 据此选择计量方法   → Step4: AI辅助生成结论              │
│                                                                 │
│ ═══ (一) 权力判断 ═══════════════ [AI] [复核] ═══════════════   │
│ │ 序号 │ 判断维度 │ 判断标准 │ 被投资单位 │ 结果 │ 依据 │ 风险 │ │
│ │ 1.1  │ 表决权   │ ...     │ ...       │ 下拉 │ ... │ ...  │  │
│ │ 1.2  │ 潜在表决权│ ...    │ ...       │ 下拉 │ ... │ ...  │  │
│                                                                 │
│ ═══ (二) 可变回报 ═══════════════ [AI] [复核] ═══════════════   │
│ │ ...                                                            │
│ ...                                                              │
│ ═══ (六) 综合判断 ═══════════════ [AI] [复核] ═══════════════   │
│ │ ...                                                            │
│                                                                 │
│ 综合审计结论 textarea(AI辅助)                                    │
│ <details>编制提示</details>                                      │
└─────────────────────────────────────────────────────────────────┘
```

### G7-8 同控合并 + G7-9 非同控合并（9列单表）

```
┌─────────────────────────────────────────────────────────────────┐
│ 方法论上下文（琥珀色左边线+浅黄背景）                             │
│ G7-8: "同一控制下企业合并(CAS20)：                               │
│   合并方取得的净资产按被合并方账面价值计量                        │
│   差额调整资本公积→留存收益                                      │
│   不确认商誉"                                                    │
│ G7-9: "非同一控制下企业合并(CAS20)：                             │
│   购买方按公允价值计量                                            │
│   初始投资成本=对价+直接费用                                     │
│   成本>份额→商誉；成本<份额→营业外收入(负商誉)"                  │
│                                                                 │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ 被投资单位 │ 日期 │ 方式 │ 净资产/对价 │ 比例 │ 份额 │ ...│  │
│ │ (ElMessageBox动态增行) │ ... │ ... │ 公式列(虚线) │ ... │  │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                                 │
│ 底部：审计结论textarea(AI辅助) + <details>编制提示</details>      │
└─────────────────────────────────────────────────────────────────┘
```

### G7-11/G7-12 处置测试表（14列单表）

```
┌─────────────────────────────────────────────────────────────────┐
│ 方法论上下文（琥珀色左边线+浅黄背景）                             │
│ G7-11: "非一揽子处置(CAS33/CAS2)：                               │
│   单次交易丧失控制权                                              │
│   个别报表：处置损益=对价-账面-应收股利+可转损益OCI               │
│   合并报表：需考虑商誉分摊+少数股东权益调整"                      │
│ G7-12: "一揽子交易处置(CAS33解释)：                               │
│   多次交易实质构成一项处置安排（6个月+商业理由）                  │
│   各次交易视为一项处置→丧失日统一确认                            │
│   之前确认的损益需追溯调整"                                       │
│                                                                 │
│ ┌──────────────────────────────────────────────────────────┐    │
│ │ 被投资 │ 处置日 │ 比例 │ 对价 │ 账面 │ ... │ 损益(公式) │    │
│ │ ... 14列 横向可滚动(固定前2列：被投资单位+日期) ...      │    │
│ └──────────────────────────────────────────────────────────┘    │
│                                                                 │
│ 底部：审计结论textarea(AI辅助) + <details>编制提示</details>      │
└─────────────────────────────────────────────────────────────────┘
```

## Formula Engine Design (useG7SubFormulaEngine.ts)

### 7个纯函数 + parseNum

```typescript
/**
 * 安全数值转换：null/undefined/NaN/空字符串/'  '/'abc' → 0; 有效数值→原值
 */
export function parseNum(v: unknown): number

/**
 * 同一控制下合并：初始投资成本 = 被合并方账面净资产 × 持股比例
 * CAS20: 按账面价值入账，差额调整资本公积
 */
export function calcSameControlCost(netAssets: number, ratio: number): number

/**
 * 非同一控制下合并：初始投资成本 = 支付对价 + 直接相关费用
 * CAS20: 按公允价值入账
 */
export function calcNotSameControlCost(price: number, fees: number): number

/**
 * 商誉 = 初始投资成本 - 享有被购买方可辨认净资产公允价值份额
 * 正值=商誉(资产)；负值=营业外收入(负商誉/廉价购买利得)
 */
export function calcGoodwill(cost: number, share: number): number

/**
 * 成本法投资收益 = 被投资方宣告股利 × 持股比例
 * 子公司个别报表用成本法，不调账面，仅确认股利
 */
export function calcCostMethodIncome(dividend: number, ratio: number): number

/**
 * 成本法期末账面 = 期初 + 追加投资 - 减值
 * 成本法不含权益法调整，仅追加和减值影响账面
 */
export function calcSubsequentBalance(opening: number, addition: number, impairment: number): number

/**
 * 处置损益(个别报表) = 处置对价 - 处置日账面 - 应收股利 + 可转损益OCI
 * CAS2/CAS33: 单次处置or一揽子统一确认时用此公式
 */
export function calcDisposalGain(price: number, bookValue: number, dividend: number, oci: number): number

/**
 * 借贷平衡校验：|SUM(debits) - SUM(credits)| < 0.01
 */
export function isDebitCreditBalanced(debits: number[], credits: number[]): boolean
```

### 公式引用关系

```
G7-8 同控合并:
  shareOfNetAssets = calcSameControlCost(acquireeNetAssets, shareholdingRatio)
  initialCost = shareOfNetAssets  (同控下初始成本=享有份额)
  差额 = consideration - initialCost → 调整资本公积

G7-9 非同控合并:
  initialCost = calcNotSameControlCost(consideration, directFees)
  shareOfFV = acquireeNetAssetsFV × shareholdingRatio
  goodwill = calcGoodwill(initialCost, shareOfFV)

G7-10 后续计量(成本法):
  investmentIncome = calcCostMethodIncome(declaredDividend, shareholdingRatio)
  closingBalance = calcSubsequentBalance(openingBalance, additionInvestment, impairmentLoss)
  variance = closingBalance - companyEndingBalance

G7-11 处置(非一揽子):
  individualGain = calcDisposalGain(disposalPrice, disposalDateBookValue, disposalDateDividend, transferableOCI)

G7-12 处置(一揽子):
  cumulativePrice = SUM(transactionPrice[0..i])
  cumulativeShareChange = SUM(shareholdingChange[0..i])
  consolidatedGain使用丧失日统一确认逻辑

G7-18 凭证检查:
  balanced = isDebitCreditBalanced(allDebits, allCredits)
  isAbnormal = !(check1 && check2 && check3 && check4 && check5 && check6)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 同控初始投资成本

*For any* netAssets ∈ ℝ, ratio ∈ [0,1]: `calcSameControlCost(netAssets, ratio)` === `netAssets × ratio`

**Validates: Requirements 3.3**

### Property 2: 非同控初始投资成本

*For any* price, fees ∈ ℝ (price ≥ 0, fees ≥ 0): `calcNotSameControlCost(price, fees)` === `price + fees`

**Validates: Requirements 3.4**

### Property 3: 商誉计算及符号语义

*For any* cost, share ∈ ℝ: `calcGoodwill(cost, share)` === `cost - share`；且 cost > share 时结果为正(商誉)，cost < share 时结果为负(营业外收入/廉价购买利得)

**Validates: Requirements 3.4, 7.1**

### Property 4: 成本法投资收益

*For any* dividend ∈ ℝ (dividend ≥ 0), ratio ∈ [0,1]: `calcCostMethodIncome(dividend, ratio)` === `dividend × ratio`

**Validates: Requirements 4.2**

### Property 5: 成本法期末账面余额

*For any* opening, addition, impairment ∈ ℝ (各 ≥ 0): `calcSubsequentBalance(opening, addition, impairment)` === `opening + addition - impairment`

**Validates: Requirements 4.3**

### Property 6: 处置损益

*For any* price, bookValue, dividend, oci ∈ ℝ: `calcDisposalGain(price, bookValue, dividend, oci)` === `price - bookValue - dividend + oci`

**Validates: Requirements 5.3**

### Property 7: 借贷平衡恒等

*For any* debits[], credits[] ∈ ℝ[]: `isDebitCreditBalanced(debits, credits)` ↔ (|SUM(debits) - SUM(credits)| < 0.01)

**Validates: Requirements 6.2, 7.1**

### Property 8: parseNum健壮性

*For any* input ∈ {null, undefined, '', NaN, '  ', 'abc'}: `parseNum(input)` === 0;
*For any* n ∈ ℝ (finite): `parseNum(n)` === n

**Validates: Requirements 7.1**

## Error Handling

| 场景 | 处理策略 |
|------|---------|
| render-config 加载失败 | selfLoad重试1次 → 失败显示"加载失败"占位 + 重试按钮 |
| 公式计算溢出/NaN | parseNum兜底→0，公式列显示"—" |
| 商誉为负值 | 正常情况（营业外收入），UI标注"廉价购买利得"绿色提示 |
| 导入Excel格式不匹配 | 后端返回422 + 具体列错误信息 → 前端ElMessage.error |
| 保存时网络异常 | 自动重试3次(指数退避) → 失败后localStorage暂存 + 恢复提示 |
| sheetName无法识别 | fallback到OnlyOffice渲染（确保不白屏） |
| G7-18 99行虚拟滚动渲染异常 | 降级为分页模式(每页30行) |
| OCR识别失败 | ElMessage.warning提示 + 允许手动填入 |
| 控制判断结果为空 | 保存时阻断 + 提示"请先完成控制类型判断" |
| 一揽子交易判断依据未填 | 保存时Toast提示必填 |
| 处置比例超过100% | 前端校验阻断 + 红框提示 |
| 动态行增删名称重复 | ElMessageBox.prompt输入时校验唯一性 |
| 同控差额计算异常(对价远超账面) | 橙色高亮 + tooltip提示"差额较大，请核实" |

## Testing Strategy

### 测试分层

| 层 | 工具 | 范围 | 数量估计 |
|----|------|------|---------|
| PBT(前端) | vitest + fast-check | 7个公式函数×8属性 | ~10 test cases |
| PBT(后端) | pytest + hypothesis | 公式验证 | ~8 test cases |
| 单元测试(前端) | vitest | composable逻辑/数据转换/异常自动检测/一揽子累计 | ~16 test cases |
| 单元测试(后端) | pytest | service/renderer/import-export | ~10 test cases |
| 集成测试 | pytest | API端点(18导入导出+5AI+render) | ~8 test cases |
| E2E | Playwright | 关键用户路径(控制判断+同控/非同控+处置) | ~4 scenarios |

### PBT配置

- 前端：fast-check，`numRuns: 100`
- 后端：hypothesis，`max_examples=5`
- 每个PBT测试注释标注对应属性编号
- Tag格式：`Feature: g7-long-term-equity-subsidiary, Property {N}: {描述}`

### 关键测试路径

1. **控制判断完整流程**：进入G7-7 → 逐section填写六要素 → 确定控制类型(控制) → AI生成综合结论
2. **同控合并流程**：新增被投资单位 → 填写净资产+比例 → 公式计算份额 → 确认初始成本 → 差额处理
3. **非同控合并流程**：新增被投资单位 → 填写对价+费用 → 公式计算初始成本 → 比较FV份额 → 商誉/营业外
4. **处置流程**：G7-11填写处置信息 → 公式计算个别处置损益 → 合并报表调整
5. **凭证检查流程**：抽凭引擎→样本填入 → Tab2核对6项 → 任一✗自动异常 → OCR识别→确认填入

### PBT测试文件

```
audit-platform/frontend/src/components/workpaper/composables/__tests__/
└── useG7SubFormulaEngine.spec.ts      # 8个PBT属性 + fast-check

backend/tests/
└── test_g7_sub_formula_pbt.py         # 后端PBT验证(hypothesis)
```

### 单元测试重点

- **控制判断结论推导**：验证六要素全"是"→控制、部分→共同控制/重大影响
- **一揽子累计计算**：验证cumulativePrice/cumulativeShareChange正确累加
- **异常自动检测逻辑**：验证当check1-6任一为false时，isAbnormal自动设为true
- **区段Tab行同步(G7-18)**：验证Tab切换后当前选中行索引不变
- **导入导出6张表**：验证G7-18导出3sheet，其余单sheet
- **商誉符号判断**：正值展示"商誉"、负值展示"营业外收入(负商誉)"
