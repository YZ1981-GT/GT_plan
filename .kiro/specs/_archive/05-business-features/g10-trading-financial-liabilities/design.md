# Design Document: G10 交易性金融负债底稿专属HTML精美组件

## Overview

G10交易性金融负债专属组件`g10-trading-financial-liabilities`。覆盖1个xlsx源模板/12有效sheet。科目2201交易性金融负债（**贷方/负债类**）。**G循环中唯一的金融负债科目**，包含衍生金融工具核查（78行复杂问卷5个section）、分类适当性检查（问卷式）、第三层次公允价值调节（负债方向：新增/终止 vs 资产方向：购入/处置）等特色审计内容。

核心架构：
- componentType `g10-trading-financial-liabilities`，主入口 GtG10TradingFinancialLiabilities.vue
- **sheetName v-if dispatch模式**：12 sheets用v-if分发（不用el-tabs）
- 子目录分组：core/ + classification/ + voucher/
- 宽表拆分：G10-2(24列→2区段Tab) / G10-5(18列→2区段Tab) / G10-7(17列→3区段Tab)
- **贷方科目公式：期末未审 = 期初审定 + 贷方发生额 - 借方发生额**（方向与G8借方科目相反）
- 计量属性：公允价值计量且变动计入当期损益（FVTPL）
- EventBus联动：publish `substantive:adjudicated`(accountCode='2201') + `disclosure:note-text-updated`
- 特色：衍生金融工具核查G10-8(78行问卷+虚拟滚动) + 分类适当性检查G10-4(28行问卷) + L3调节表(负债方向)
- 双模式（HTML ↔ OnlyOffice）+ 导入导出(useG10ImportExport, 5张表) + AI(5 section)
- 六大集成：版本链✅ 抽凭✅ 截止✅ 附注EventBus✅ OCR✅ 复核✅

**与G8关键差异**：
| 维度 | G8(借方/资产) | G10(贷方/负债) |
|------|-------------|---------------|
| 科目方向 | 期末=期初+借方-贷方 | 期末=期初+**贷方**-**借方** |
| Sheet数量 | 10 | **12**（多G10-4分类检查+G10-8衍生工具） |
| 特色表 | G8-5适当性(CAS22) | **G10-4分类+G10-8衍生工具(78行5section)** |
| 审定表 | 29行按投资方分 | **63行按初始金额/公允价值变动分组** |
| L3调节表 | 购入/处置(资产) | **新增/终止(负债)** |
| 公式引擎 | 7+parseNum(含calcDebitBalance/calcEndingBalance/calcFairValueDiff) | **6+parseNum(calcCreditBalance替代，无calcEndingBalance/calcFairValueDiff因明细表12列审定=未审+调整)** |
| AI section | 4 | **5**（多derivative-conclusion） |
| 导入导出 | 4张表 | **5张表**（多G10-5） |
| 虚拟滚动 | G8-6(102行) | **G10-1(63行)/G10-7(99行)/G10-8(78行)/附注国企(79行)** |

## Architecture

### sheetName分发模式 + 子目录组织

GtG10TradingFinancialLiabilities.vue 接收 `sheetName` prop，用正则提取编码(G10A/G10-1~G10-8/附注披露(上市)/附注披露(国企)/底稿目录)，`v-if` 分发到对应子组件。

```
sheetName → regex提取编码 → v-if匹配 → defineAsyncComponent子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback

12 sheets 子目录分组:
├── core/
│   ├── G10A   实质性程序表（复用a-program-console + 抽凭引擎 + 截止提取）
│   ├── G10-1  审定表（63行×12列，**贷方**/公允价值计量，分组折叠+虚拟滚动）
│   ├── G10-2  明细表（39行×24列→2区段Tab：基础信息/公允价值+分类）
│   ├── G10-3  调整分录汇总（23行×10列，AJE/RJE + 借贷平衡校验）
│   ├── 附注披露(上市)（42行×5列）
│   ├── 附注披露(国企)（79行×5列，虚拟滚动）
│   └── 底稿目录
├── classification/
│   ├── G10-4  分类适当性检查表（28行×9列，问卷式合规检查）
│   ├── G10-5  公允价值测试表（39行×18列→2区段Tab：Level1/2/3测试）
│   └── G10-6  第三层次公允价值调节表（23行×13列，负债方向）
└── voucher/
    ├── G10-7  凭证检查表（99行×17列→3区段Tab + 抽凭引擎 + 行级OCR + 虚拟滚动）
    └── G10-8  衍生金融工具核查表（78行×10列，5section问卷式 + 虚拟滚动）
```

### 高层数据流

```mermaid
graph TD
    TB[trial_balance<br/>科目2201] -->|自动取数| G10_1[G10-1 审定表]
    G10_1 -->|EventBus: substantive:adjudicated| NOTE_L[附注披露-上市]
    G10_1 -->|EventBus: substantive:adjudicated| NOTE_S[附注披露-国企]
    NOTE_L -->|EventBus: disclosure:note-text-updated| EXT[附注模块]
    NOTE_S -->|EventBus: disclosure:note-text-updated| EXT
    G10_3[G10-3 调整分录] -->|AJE/RJE汇总回写| G10_1
    G10_2[G10-2 明细表] -->|逐笔合计比对| G10_1
    G10_5[G10-5 公允价值测试] -->|审定公允价值比对| G10_1
    G10_4[G10-4 分类检查] -->|分类合规结论| G10_5
    G10_6[G10-6 L3调节表] -->|L3合计比对| G10_5
    G10_8[G10-8 衍生工具核查] -->|衍生结论引用| G10_4
    G10A[G10A 程序表] -->|抽凭引擎| VOUCHER[GtVoucherSamplingEngine]
    G10A -->|截止提取| CUTOFF[useCutoffAutoSampling]
    G10_7[G10-7 凭证检查] -->|抽凭引擎| VOUCHER
    G10_7 -->|行级OCR| OCR[/d4/contract-ocr]
    MAIN[GtG10TradingFinancialLiabilities] -->|autoSnapshot| VER[useVersionTrail]
    MAIN -->|provide openReviewDialog| CHILDREN[所有子组件]
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtG10TradingFinancialLiabilities.vue           # 主入口 sheetName v-if分发（defineAsyncComponent lazy×12）
├── g10-trading-financial-liabilities/
│   ├── core/
│   │   ├── G10TabProcedure.vue                    # G10A 程序表（复用a-program-console+selfLoad+抽凭+截止）
│   │   ├── G10TabAdjudication.vue                 # G10-1 审定表（63行×12列，贷方+分组折叠+虚拟滚动）
│   │   ├── G10TabDetail.vue                       # G10-2 明细表(24列→2区段Tab)
│   │   ├── G10TabAdjustment.vue                   # G10-3 调整分录(AJE/RJE+借贷校验)
│   │   ├── G10TabDisclosureListed.vue             # 附注披露(上市)(42行)
│   │   ├── G10TabDisclosureSOE.vue                # 附注披露(国企)(79行+虚拟滚动)
│   │   └── G10TabDirectory.vue                    # 底稿目录
│   ├── classification/
│   │   ├── G10TabClassificationCheck.vue          # G10-4 分类适当性检查(28行问卷式)
│   │   ├── G10TabFairValueTest.vue                # G10-5 公允价值测试(2区段Tab+Level3必填)
│   │   └── G10TabL3Reconciliation.vue             # G10-6 L3调节表(负债方向)
│   └── voucher/
│       ├── G10TabVoucherCheck.vue                 # G10-7 凭证检查(3区段Tab+OCR+虚拟滚动99行)
│       └── G10TabDerivativeCheck.vue              # G10-8 衍生工具核查(78行5section问卷+虚拟滚动)
├── composables/
│   ├── useG10FormulaEngine.ts                     # G10公式引擎(6个纯函数+parseNum)
│   ├── useG10FormData.ts                          # 数据加载/保存/selfLoad/writebackTB
│   ├── useG10ImportExport.ts                      # 导入导出composable(5张表: G10-2/G10-3/G10-5/G10-6/G10-7)
│   └── useG10DualMode.ts                          # 双模式OO切换+localStorage

backend/app/routers/wp_render_strategies/
├── _g10_trading_financial_liabilities.py           # render策略+注册RENDERER_DISPATCH
├── _g10_trading_financial_liabilities_service.py   # 业务逻辑(公式验证/TB取数/EventBus)
├── _g10_trading_financial_liabilities_import_export.py # 导入导出端点(5张表×3=15端点)
└── _g10_trading_financial_liabilities_ai.py       # AI生成5 section
```

### EventBus事件

| 事件名 | 发布者 | 消费者 | payload |
|--------|--------|--------|---------|
| `substantive:adjudicated` | G10-1审定表 | 附注披露(上市/国企) + trial_balance | `{accountCode:'2201', adjudicatedAmount}` |
| `disclosure:note-text-updated` | 附注披露 | 附注模块 | `{accountCode:'2201', text}` |

### 后端AI Section清单

```
adjudication-analysis / classification-conclusion / fair-value-conclusion / derivative-conclusion / voucher-conclusion
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtG10TradingFinancialLiabilities.vue props
interface G10TradingFinancialLiabilitiesProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// sheetName正则匹配映射
const SHEET_CODE_MAP: Record<string, string> = {
  'G10A': 'procedure',
  'G10-1': 'adjudication',
  'G10-2': 'detail',
  'G10-3': 'adjustment',
  'G10-4': 'classificationCheck',
  'G10-5': 'fairValueTest',
  'G10-6': 'l3Reconciliation',
  'G10-7': 'voucherCheck',
  'G10-8': 'derivativeCheck',
  '附注披露信息（上市公司）': 'disclosureListed',
  '附注披露信息（国企）': 'disclosureSOE',
  '底稿目录': 'directory',
}
```

### G10-1 审定表数据模型（63行×12列，贷方科目，分组结构）

```typescript
interface G10AdjudicationData {
  groups: G10AdjudicationGroup[]       // 按分组：(一)初始金额/(二)公允价值变动/合计
  totals: G10AdjudicationTotals        // 合计行
  trialBalanceAmount: number           // 试算表取数(科目2201)
  variance: number                     // 差异=审定-试算表
}

interface G10AdjudicationGroup {
  id: string
  title: string                        // "(一)初始金额" | "(二)公允价值变动" | "合计"
  collapsed: boolean                   // 分组折叠状态
  rows: G10AdjudicationRow[]
}

interface G10AdjudicationRow {
  id: string
  item: string                         // 项目名称（交易性金融负债/卖出回购/衍生金融负债等）
  // 期初
  openingUnadjusted: number            // 期初未审数
  openingAdjustment: number            // 期初账项调整
  openingAdjusted: number              // 公式: 未审 + 账项调整
  // 期末
  closingUnadjusted: number            // 期末未审数（**贷方余额公式**）
  closingAdjustment: number            // 期末账项调整
  closingAdjusted: number              // 公式: 未审 + 账项调整
  // 变动
  changeAmount: number                 // 公式: 期末审定 - 期初审定
  changeRate: number | null            // 公式: (期末-期初)/期初, 期初=0时null
  reasonAnalysis: string               // |变动率|>20%时必填(橙色高亮)
  indexRef: string                     // 索引号
}

interface G10AdjudicationTotals {
  openingAdjusted: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number | null
}
```

### G10-2 明细表数据模型（24列→2区段Tab）

```typescript
interface G10DetailRow {
  id: string
  seq: number
  // ══ Tab1: 基础信息(12列) ══
  liabilityName: string                // 负债名称
  liabilityType: string                // 负债类型(下拉: 交易性债券/卖出回购/衍生金融负债/其他)
  counterparty: string                 // 对手方
  contractDate: string                 // 合同日
  maturityDate: string                 // 到期日
  initialAmount: number                // 初始金额
  openingBalance: number               // 期初余额
  openingAdjusted: number              // 期初审定
  currentIncrease: number              // 本期增加(贷方)
  currentDecrease: number              // 本期减少(借方)
  closingBalance: number               // 期末余额
  closingAdjusted: number              // 公式: 未审 + 调整(12列审定=未审+调整)

  // ══ Tab2: 公允价值+分类(12列) ══
  liabilityNameRef: string             // 负债名称(引用)
  fairValueLevel: 'Level1' | 'Level2' | 'Level3'  // 公允价值层次(下拉)
  valuationMethod: string              // 估值方法
  openingFairValue: number             // 期初公允价值
  closingFairValue: number             // 期末公允价值
  fairValueChange: number              // 公允价值变动
  profitLossAmount: number             // 计入损益金额
  isDerivative: boolean                // 是否衍生工具
  hostContractDesc: string             // 主合同描述
  embeddedDerivativeJudgment: string   // 嵌入衍生判断
  confirmationStatus: string           // 发函情况
  remark: string                       // 备注
}
```

### G10-3 调整分录数据模型（23行×10列）

```typescript
interface G10AdjustmentEntry {
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

### G10-4 分类适当性检查表数据模型（28行×9列，问卷式）

```typescript
interface G10ClassificationCheckData {
  sections: G10ClassificationSection[]
  overallConclusion: string            // 综合审计结论(textarea)
}

interface G10ClassificationSection {
  id: string
  sectionNo: string                    // 序号
  title: string
  // 检查区域示例：
  // - 初始分类依据检查
  // - 持有目的验证
  // - 公允价值计量适当性
  // - 重分类可能性评估
  rows: G10ClassificationRow[]
}

interface G10ClassificationRow {
  id: string
  seq: number                          // 序号
  checkItem: string                    // 检查项目
  auditRequirement: string             // 审计要求(方法论)
  managementReply: string              // 管理层回复(textarea)
  compliance: 'compliant' | 'non_compliant' | 'not_applicable'  // 是否合规(下拉)
  conclusion: string                   // 结论(textarea)
  indexRef: string                     // 索引
}
```

### G10-5 公允价值测试表数据模型（39行×18列→2区段Tab）

```typescript
interface G10FairValueTestRow {
  id: string
  seq: number
  // ══ Tab1: 基础信息+审定(9列) ══
  liabilityName: string                // 负债名称
  initialDate: string                  // 初始确认日期
  closingUnadjustedQty: number         // 期末未审-数量
  closingUnadjustedPrice: number       // 期末未审-单价
  closingUnadjustedFV: number          // 期末未审-公允价值
  closingAuditedQty: number            // 期末审定-数量
  closingAuditedPrice: number          // 期末审定-单价
  closingAuditedFV: number             // 期末审定-公允价值
  fairValueLevel: 'Level1' | 'Level2' | 'Level3'  // 公允价值层次(下拉)

  // ══ Tab2: 估值详情(9列) ══
  valuationMethod: string              // 估值方法(下拉: 市场法/收益法/成本法/其他)
  methodConsistentWithPrior: 'yes' | 'no'  // 与上期一致
  valuationSource: string              // 公允价值来源机构
  inputSourceAndAdjustment: string     // 输入值来源及调整(textarea)
  valuationTechnique: string           // 估值技术
  unobservableInputDesc: string        // 不可观察输入值描述(textarea)
  unobservableInputValue: string       // 数值
  sensitivityAnalysis: string          // 敏感性分析(textarea)
  valuationDocIndex: string            // 估值文件索引号
}
```

### G10-6 第三层次公允价值调节表数据模型（23行×13列，负债方向）

```typescript
interface G10L3ReconciliationRow {
  id: string
  seq: number
  liabilityName: string                // 负债名称
  openingBalance: number               // 期初余额
  currentNew: number                   // 本期新增（负债方向：新发行/新确认）
  currentTerminated: number            // 本期终止（负债方向：到期/提前清偿）
  transferIntoL3: number               // 转入第三层次
  transferOutOfL3: number              // 转出第三层次
  fairValueChange: number              // 公允价值变动(计入损益)
  interestExpense: number              // 利息费用
  otherChanges: number                 // 其他变动
  closingBalance: number               // 期末余额(公式)
  variance: number                     // 差异(公式: 期末-计算值)
  remark: string                       // 备注
}
```

### G10-7 凭证检查表数据模型（99行×17列→3区段Tab）

```typescript
interface G10VoucherCheckRow {
  id: string
  seq: number
  // ══ Tab1: 凭证基础(6列) ══
  voucherDate: string                  // 日期
  voucherNo: string                    // 凭证编号
  businessContent: string              // 业务内容
  counterAccount: string               // 对方科目
  debitAmount: number                  // 借方金额
  creditAmount: number                 // 贷方金额

  // ══ Tab2: 核对内容(6列) ══
  attachment: string | null            // 📎附件路径(OCR触发)
  supportingDocDesc: string            // 支持性文件描述
  check1OriginalComplete: boolean      // 核对1-原始凭证完整
  check2Authorization: boolean         // 核对2-授权批准
  check3Accounting: boolean            // 核对3-账务处理正确
  check4FairValueCorrect: boolean      // 核对4-公允价值计量正确

  // ══ Tab3: 结论(5列) ══
  indexNo: string                      // 索引号(GtIndexChip)
  isAbnormal: boolean                  // 是否异常(Tab2任一✗→自动是)
  abnormalDesc: string                 // 异常说明(textarea)
  riskLevel: 'high' | 'medium' | 'low'  // 风险等级(下拉)
  remark: string                       // 备注
}
```

### G10-8 衍生金融工具核查表数据模型（78行×10列，5section问卷）

```typescript
interface G10DerivativeCheckData {
  sections: G10DerivativeSection[]
  overallConclusion: string            // 综合审计结论(textarea)
  methodologyContext: string           // 方法论上下文(衍生工具五要素定义)
}

interface G10DerivativeSection {
  id: string
  sectionNo: string                    // (一)~(五)
  title: string
  // (一) 衍生金融工具基本信息：工具类型/对手方/合同条款
  // (二) 嵌入衍生工具判断：主合同分析+拆分必要性
  // (三) 公允价值计量：估值方法+输入值验证
  // (四) 套期关系检查：是否指定套期+有效性测试
  // (五) 披露完整性：衍生工具相关披露检查
  rows: G10DerivativeRow[]
}

interface G10DerivativeRow {
  id: string
  seq: number                          // 序号
  checkArea: string                    // 检查区域
  checkItem: string                    // 检查项目
  auditRequirement: string             // 审计要求(方法论)
  checkResult: string                  // 检查结果(textarea)
  compliance: 'compliant' | 'non_compliant' | 'not_applicable'  // 是否合规(下拉)
  riskLevel: 'high' | 'medium' | 'low' | ''  // 风险等级(下拉)
  auditConclusion: string              // 审计结论(textarea)
  indexRef: string                     // 索引
  remark: string                       // 备注
}
```

### 附注数据模型

```typescript
interface G10DisclosureSection {
  id: string
  title: string
  rows?: G10DisclosureRow[]
  textContent?: string                 // 文本区内容（AI辅助）
}

interface G10DisclosureRow {
  id: string
  label: string
  value: string | number
  editable: boolean
}
```

## Data Models

### 存储结构（working_paper.content JSON）

```typescript
interface G10Content {
  // G10-1 审定表
  adjudication: {
    groups: G10AdjudicationGroup[]
    totals: G10AdjudicationTotals
  }
  // G10-2 明细表
  detail: {
    rows: G10DetailRow[]
  }
  // G10-3 调整分录
  adjustment: {
    entries: G10AdjustmentEntry[]
  }
  // G10-4 分类适当性检查
  classificationCheck: G10ClassificationCheckData
  // G10-5 公允价值测试
  fairValueTest: {
    rows: G10FairValueTestRow[]
    conclusion: string                 // 审计结论
  }
  // G10-6 L3调节表
  l3Reconciliation: {
    rows: G10L3ReconciliationRow[]
  }
  // G10-7 凭证检查
  voucherCheck: {
    rows: G10VoucherCheckRow[]
  }
  // G10-8 衍生工具核查
  derivativeCheck: G10DerivativeCheckData
  // 附注
  disclosureListed: { sections: G10DisclosureSection[] }
  disclosureSOE: { sections: G10DisclosureSection[] }
}
```

### API接口

```python
# _g10_trading_financial_liabilities.py
# RENDERER_DISPATCH注册
def render_g10_trading_financial_liabilities(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType='g10-trading-financial-liabilities'和sheets配置"""

# _g10_trading_financial_liabilities_import_export.py
POST /api/workpapers/{wp_id}/g10/export-template?sheet={code}
POST /api/workpapers/{wp_id}/g10/export-data?sheet={code}
POST /api/workpapers/{wp_id}/g10/import-data?sheet={code}  # multipart/form-data
# sheet codes: G10-2 / G10-3 / G10-5 / G10-6 / G10-7
# 宽表按区段分sheet导出：
#   G10-2(2sheet) / G10-5(2sheet) / G10-7(3sheet) / G10-3(1sheet) / G10-6(1sheet)

# _g10_trading_financial_liabilities_ai.py
POST /api/workpapers/{wp_id}/g10/ai/{section}
# section: adjudication-analysis / classification-conclusion /
#          fair-value-conclusion / derivative-conclusion / voucher-conclusion

# _g10_trading_financial_liabilities_service.py
class G10TradingFinancialLiabilitiesService:
    async def get_trial_balance_data(project_id, year) -> dict
    async def save_adjudication(wp_id, data) -> dict
    async def validate_formulas(data) -> list[ValidationError]
```

### trial_balance 取数

```sql
-- G10-1审定表自动取数（负债类/贷方）
SELECT standard_account_code, unadjusted_amount, aje_adjustment, audited_amount
FROM trial_balance
WHERE project_id = :project_id
  AND year = :year
  AND standard_account_code LIKE '2201%'
```

### 注册四件套

```python
# 1. htmlRendererRegistry (前端)
'g10-trading-financial-liabilities': () => import('./workpaper/GtG10TradingFinancialLiabilities.vue')

# 2. wp_code_overrides.json (12条)
{
  "G10A-交易性金融负债实质性程序表": "g10-trading-financial-liabilities",
  "G10-1-审定表": "g10-trading-financial-liabilities",
  "G10-2-明细表": "g10-trading-financial-liabilities",
  "G10-3-调整分录汇总": "g10-trading-financial-liabilities",
  "G10-4-分类的适当性检查表": "g10-trading-financial-liabilities",
  "G10-5-公允价值测试表": "g10-trading-financial-liabilities",
  "G10-6-第三层次公允价值计量的调节表": "g10-trading-financial-liabilities",
  "G10-7-凭证检查表": "g10-trading-financial-liabilities",
  "G10-8-衍生金融工具核查表": "g10-trading-financial-liabilities",
  "G10-附注披露信息（上市公司）": "g10-trading-financial-liabilities",
  "G10-附注披露信息（国企）": "g10-trading-financial-liabilities",
  "G10-底稿目录": "g10-trading-financial-liabilities"
}

# 3. VALID_COMPONENT_TYPES (后端)
'g10-trading-financial-liabilities'

# 4. RENDERER_DISPATCH (后端)
'g10-trading-financial-liabilities': render_g10_trading_financial_liabilities
```

## Integration Design（6大集成接入点）

### 1. 版本链 (useVersionTrail)

```typescript
// GtG10TradingFinancialLiabilities.vue 主入口
const { autoSnapshot, showVersionTrail } = useVersionTrail(wpId)

async function handleSave() {
  await saveData()
  await autoSnapshot()  // 触发版本快照
}
// 工具栏"版本历史"按钮 → GtWpVersionTrail drawer
```

### 2. 抽凭引擎 (G10A程序表 + G10-7凭证检查)

```typescript
// G10TabProcedure.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['2201']"
  dialog-mode
  @samples-ready="fillSamples"
/>

// G10TabVoucherCheck.vue
<GtVoucherSamplingEngine
  :project-id="projectId"
  :account-codes="['2201']"
  dialog-mode
  @samples-ready="fillVoucherRows"
/>
```

### 3. 截止自动提取 (useCutoffAutoSampling)

```typescript
// G10TabProcedure.vue 截止测试步骤
const { fetchCutoffSamples } = useCutoffAutoSampling({
  projectId, accountCode: '2201', days: 5
})
```

### 4. 附注EventBus

```typescript
// G10TabAdjudication.vue (发布者)
watch(reportAmount, (val) => {
  eventBus.publish('substantive:adjudicated', {
    accountCode: '2201',
    adjudicatedAmount: val
  })
})

// G10TabDisclosureListed.vue / G10TabDisclosureSOE.vue (消费者)
eventBus.subscribe('substantive:adjudicated', (payload) => {
  if (payload.accountCode === '2201') refreshData()
})

// 附注文本变更发布
eventBus.publish('disclosure:note-text-updated', {
  accountCode: '2201', text: noteText
})
```

### 5. 行级OCR (G10-7 📎附件列)

```typescript
// G10TabVoucherCheck.vue
async function handleOCR(row: G10VoucherCheckRow, file: File) {
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
// GtG10TradingFinancialLiabilities.vue (主入口)
const { openReviewDialog } = useReviewDialog(wpId)
provide('openReviewDialog', openReviewDialog)

// 子组件 (section标题栏右侧按钮)
const openReviewDialog = inject('openReviewDialog')
```

## 宽表区段Tab拆分详细设计

### G10-2 明细表（24列→2区段Tab）

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌─────────────────────────┐ ┌──────────────────────────┐       │
│ │Tab1: 基础信息(12列)      │ │Tab2: 公允价值+分类(12列)  │ 区段Tab│
│ └─────────────────────────┘ └──────────────────────────┘       │
│                                                                 │
│ Tab1: 序号|负债名称|负债类型(下拉)|对手方|合同日|到期日|           │
│       初始金额|期初余额|期初审定|本期增加|本期减少|期末余额|       │
│       审定数(公式:未审+调整)                                     │
│                                                                 │
│ Tab2: 序号|负债名称|公允价值层次(L1/L2/L3)|估值方法|              │
│       期初公允价值|期末公允价值|公允价值变动|计入损益金额|         │
│       是否衍生工具|主合同描述|嵌入衍生判断|发函情况|备注           │
│                                                                 │
│ 底部：合计行（初始金额/期初/增加/减少/期末/公允价值变动合计）     │
│ 行同步：Tab切换保持行索引                                        │
│ 动态行：ElMessageBox.prompt输入负债名称→创建行                   │
└─────────────────────────────────────────────────────────────────┘
```

### G10-5 公允价值测试表（18列→2区段Tab）

```
┌─────────────────────────────────────────────────────────────────┐
│ 方法论上下文（琥珀色左边线+浅黄背景）                             │
│ "公允价值三层次定义：                                            │
│   Level1-活跃市场上相同负债的报价(未经调整)                       │
│   Level2-除Level1外可直接/间接观察到的输入值                     │
│   Level3-相关负债不可观察的输入值(估值技术)"                      │
│                                                                 │
│ ┌──────────────────────┐ ┌──────────────────┐                  │
│ │Tab1: 基础信息+审定(9列) │ │Tab2: 估值详情(9列)│    区段Tab      │
│ └──────────────────────┘ └──────────────────┘                  │
│                                                                 │
│ Tab1: 序号|名称|初始确认日期|未审数量|未审单价|未审FV|              │
│       审定数量|审定单价|审定FV|层次(下拉)                         │
│                                                                 │
│ Tab2: 序号|名称|估值方法(下拉)|与上期一致(是/否)|来源机构|         │
│       输入值来源(textarea)|估值技术|不可观察输入值描述|数值|       │
│       敏感性分析(textarea)|估值文件索引号                         │
│                                                                 │
│ ⚠️ Level3必填校验：层次=Level3时Tab2(估值技术+不可观察输入值)必填 │
│                                                                 │
│ 底部：审计结论textarea(AI辅助) + <details>编制提示</details>      │
│ 行同步：Tab切换保持行索引                                        │
└─────────────────────────────────────────────────────────────────┘
```

### G10-4 分类适当性检查表（28行×9列，问卷式）

```
┌─────────────────────────────────────────────────────────────────┐
│ 方法论上下文（琥珀色左边线+浅黄背景）                             │
│ "交易性金融负债分类条件(CAS22/37)：                               │
│   ① 承担该金融负债的目的是为了近期出售或回购                      │
│   ② 属于进行集中管理的可辨认金融工具组合的一部分(短期获利)         │
│   ③ 属于衍生金融负债(不符合套期会计要求的)"                       │
│                                                                 │
│ ═══ 检查区域一 ══════════════════════════ [AI] [复核] ═════════ │
│ │ 序号 │ 检查项目 │ 审计要求 │ 管理层回复 │ 合规 │ 结论 │ 索引 │  │
│ │ 1    │ ...      │ ...     │ textarea  │ 下拉 │ ...  │ ...  │  │
│ │ 2    │ ...      │ ...     │ textarea  │ 下拉 │ ...  │ ...  │  │
│                                                                 │
│ ═══ 检查区域二 ══════════════════════════ [AI] [复核] ═════════ │
│ │ ...                                                            │
│                                                                 │
│ ═══ 检查区域三 ══════════════════════════ [AI] [复核] ═════════ │
│ │ ...                                                            │
│                                                                 │
│ 综合审计结论 textarea(AI辅助: classification-conclusion)          │
│ <details>编制提示</details>                                      │
└─────────────────────────────────────────────────────────────────┘
```

### G10-8 衍生金融工具核查表（78行×10列，5section问卷+虚拟滚动）

```
┌─────────────────────────────────────────────────────────────────┐
│ 方法论上下文（琥珀色左边线+浅黄背景）                             │
│ "衍生金融工具五要素(CAS22)：                                     │
│   ① 其价值随特定利率/金融工具价格/汇率等变动而变动                │
│   ② 不要求初始净投资,或与对市场条件变动类似合同相比净投资很少     │
│   ③ 在未来某一日期结算                                           │
│   ④ 以固定或可确定的金额交换                                     │
│   ⑤ 可以净额结算"                                               │
│                                                                 │
│ ═══ (一) 衍生金融工具基本信息 ═══════════ [AI] [复核] ═════════ │
│ │序号│检查区域│检查项目│审计要求│检查结果│合规│风险│结论│索引│备注│ │
│ │ 1  │类型    │...    │...    │textarea│下拉│下拉│... │... │... │ │
│ │ 2  │对手方  │...    │...    │textarea│下拉│下拉│... │... │... │ │
│ │...                                                             │
│                                                                 │
│ ═══ (二) 嵌入衍生工具判断 ═══════════════ [AI] [复核] ═════════ │
│ │ ... (主合同分析+拆分必要性)                                    │
│                                                                 │
│ ═══ (三) 公允价值计量 ═══════════════════ [AI] [复核] ═════════ │
│ │ ... (估值方法+输入值验证)                                      │
│                                                                 │
│ ═══ (四) 套期关系检查 ═══════════════════ [AI] [复核] ═════════ │
│ │ ... (是否指定套期+有效性测试)                                  │
│                                                                 │
│ ═══ (五) 披露完整性 ═════════════════════ [AI] [复核] ═════════ │
│ │ ... (衍生工具相关披露检查)                                     │
│                                                                 │
│ 虚拟滚动：78行全表启用                                           │
│ 综合审计结论 textarea(AI辅助: derivative-conclusion)              │
│ <details>编制提示</details>                                      │
└─────────────────────────────────────────────────────────────────┘
```

### G10-7 凭证检查表（17列→3区段Tab）

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌──────────────────┐ ┌──────────────────┐ ┌──────────┐        │
│ │Tab1: 凭证基础(6列)│ │Tab2: 核对内容(6列)│ │Tab3: 结论(5列)│ 3区段 │
│ └──────────────────┘ └──────────────────┘ └──────────┘        │
│                                                                 │
│ Tab1: 日期|凭证编号|业务内容|对方科目|借方|贷方                   │
│                                                                 │
│ Tab2: 📎附件|文件描述|✓完整|✓授权|✓账务正确|✓公允价值正确         │
│       (📎点击→上传→OCR识别→ElMessageBox确认→填入)                │
│       (任一✗→Tab3"是否异常"自动置"是")                           │
│                                                                 │
│ Tab3: 索引号(GtIndexChip)|是否异常|异常说明|风险等级|备注         │
│                                                                 │
│ 顶部：借贷差额汇总（差额≠0红色）                                 │
│ 虚拟滚动：99行                                                   │
│ 行同步：3个Tab间切换保持行索引                                    │
└─────────────────────────────────────────────────────────────────┘
```

## Formula Engine Design (useG10FormulaEngine.ts)

### 6个纯函数 + parseNum

```typescript
/**
 * 安全数值转换：null/undefined/NaN/空字符串/'  '/'abc' → 0; 有效数值→原值
 */
export function parseNum(v: unknown): number

/**
 * 贷方余额公式：期末未审 = 期初审定 + 贷方 - 借方
 * G10为贷方/负债类科目（方向与G8借方相反）
 * 对比G8: calcDebitBalance = opening + debit - credit
 */
export function calcCreditBalance(opening: number, credit: number, debit: number): number

/**
 * 审定数 = 未审数 + 账项调整
 */
export function calcAdjustedAmount(unadjusted: number, adjustment: number): number

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
 * L3调节表期末公式：期初+新增-终止+转入-转出+FV变动+利息+其他
 * 负债方向：新增(贷方增加) / 终止(借方减少)
 */
export function calcL3Reconciliation(
  opening: number,
  newIssued: number,
  terminated: number,
  transferIn: number,
  transferOut: number,
  fvChange: number,
  interestExpense: number,
  other: number
): number
```

**注意**：G10不需要G8的`calcEndingBalance`和`calcFairValueDiff`，因为：
- G10-2明细表的审定数直接用`calcAdjustedAmount`（未审+调整），不走期初+增-减+FV变动
- 公允价值差异在G10不作为独立公式（直接在UI中显示期末FV-期初FV）

### 公式引用关系

```
G10-1 审定表(贷方科目):
  openingAdjusted = calcAdjustedAmount(openingUnadjusted, openingAdjustment)
  closingUnadjusted ≈ calcCreditBalance(openingAdjusted, totalCredit, totalDebit)
  closingAdjusted = calcAdjustedAmount(closingUnadjusted, closingAdjustment)
  changeAmount = closingAdjusted - openingAdjusted
  changeRate = calcChangeRate(openingAdjusted, closingAdjusted)

G10-2 明细表:
  closingAdjusted = calcAdjustedAmount(closingBalance, closingAdjustment)
  (注：明细表12列审定=未审+调整，不使用calcEndingBalance)

G10-3 调整分录:
  balanced = isDebitCreditBalanced(allDebits, allCredits)

G10-6 L3调节表:
  closingBalance = calcL3Reconciliation(opening, new, terminated, transferIn, transferOut, fvChange, interest, other)
  variance = actualClosing - closingBalance

G10-1 vs 试算表:
  closingUnadjusted ≈ calcCreditBalance(openingAdjusted, totalCredit, totalDebit)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 贷方余额公式

*For any* opening, credit, debit ∈ ℝ: `calcCreditBalance(opening, credit, debit)` === `opening + credit - debit`

**Validates: Requirements 3.3, 10.1**

### Property 2: 审定数公式

*For any* unadjusted, adjustment ∈ ℝ: `calcAdjustedAmount(unadjusted, adjustment)` === `unadjusted + adjustment`

**Validates: Requirements 3.4, 10.1**

### Property 3: L3调节表恒等

*For any* opening, newIssued, terminated, transferIn, transferOut, fvChange, interestExpense, other ∈ ℝ: `calcL3Reconciliation(opening, newIssued, terminated, transferIn, transferOut, fvChange, interestExpense, other)` === `opening + newIssued - terminated + transferIn - transferOut + fvChange + interestExpense + other`

**Validates: Requirements 7.3, 10.1**

### Property 4: 变动率方向性与除零保护

*For any* current > prior > 0: `calcChangeRate(prior, current)` > 0;
*For any* current < prior, prior > 0: `calcChangeRate(prior, current)` < 0;
`calcChangeRate(0, any)` === null

**Validates: Requirements 3.8, 10.1**

### Property 5: 借贷平衡恒等

*For any* debits[], credits[] ∈ ℝ[]: `isDebitCreditBalanced(debits, credits)` ↔ (|SUM(debits) - SUM(credits)| < 0.01)

**Validates: Requirements 6.1, 10.1**

### Property 6: parseNum健壮性

*For any* input ∈ {null, undefined, '', NaN, '  ', 'abc'}: `parseNum(input)` === 0;
*For any* n ∈ ℝ (finite): `parseNum(n)` === n

**Validates: Requirements 10.1**

## Error Handling

| 场景 | 处理策略 |
|------|---------|
| render-config 加载失败 | selfLoad重试1次 → 失败显示"加载失败"占位 + 重试按钮 |
| trial_balance 取数无数据 | 审定表显示0值 + 橙色提示"未找到科目2201数据" |
| 公式计算溢出/NaN | parseNum兜底→0，公式列显示"—" |
| 导入Excel格式不匹配 | 后端返回422 + 具体列错误信息 → 前端ElMessage.error |
| EventBus消息丢失 | 附注组件mounted时主动拉取最新审定数（非纯被动监听） |
| 保存时网络异常 | 自动重试3次(指数退避) → 失败后localStorage暂存 + 恢复提示 |
| sheetName无法识别 | fallback到OnlyOffice渲染（确保不白屏） |
| Level3必填校验未通过 | Tab2对应行红框高亮 + 顶部toast提示具体缺失字段 |
| G10-7/G10-8虚拟滚动渲染异常 | 降级为分页模式(每页30行) |
| OCR识别失败 | ElMessage.warning提示 + 允许手动填入 |
| 衍生工具核查78行加载慢 | skeleton占位+分section懒渲染 |
| 贷方公式方向错误 | 后端校验calcCreditBalance与TB数据对比，差异>1%告警 |
| G10-4/G10-8问卷下拉未选择 | 保存时阻断 + 高亮未填项 + toast提示 |
| 附注国企79行虚拟滚动 | 同G10-7降级策略 |

## Testing Strategy

### 测试分层

| 层 | 工具 | 范围 | 数量估计 |
|----|------|------|---------|
| PBT(前端) | vitest + fast-check | 6个公式函数×6属性 | ~8 test cases |
| PBT(后端) | pytest + hypothesis | 公式验证 | ~6 test cases |
| 单元测试(前端) | vitest | composable逻辑/数据转换/Level3校验/异常自动检测/贷方方向 | ~20 test cases |
| 单元测试(后端) | pytest | service/renderer/import-export | ~12 test cases |
| 集成测试 | pytest | API端点(15导入导出+5AI+render) | ~10 test cases |
| E2E | Playwright | 关键用户路径(审定+分类检查+衍生工具核查+公允价值测试) | ~5 scenarios |

### PBT配置

- 前端：fast-check，`numRuns: 100`
- 后端：hypothesis，`max_examples=5`
- 每个PBT测试注释标注对应属性编号
- Tag格式：`Feature: g10-trading-financial-liabilities, Property {N}: {描述}`

### 关键测试路径

1. **审定表完整流程（贷方方向）**：TB取数(2201) → 贷方公式(+贷-借) → 填写调整 → 审定计算 → 分组折叠 → EventBus发布 → 附注刷新
2. **分类适当性检查**：方法论上下文 → 28行问卷逐项填写 → 合规判断 → AI辅助生成结论
3. **衍生金融工具核查**：78行5section问卷 → 虚拟滚动 → 嵌入衍生判断 → 套期关系检查 → AI derivative-conclusion
4. **公允价值三层次测试**：Level1/2/3选择 → Level3时Tab2必填校验 → L3调节表联动(负债方向)
5. **凭证检查流程**：抽凭引擎→样本填入 → Tab2核对4项 → 任一✗自动异常 → OCR识别→确认填入

### PBT测试文件

```
audit-platform/frontend/src/components/workpaper/composables/__tests__/
└── useG10FormulaEngine.spec.ts        # 6个PBT属性 + fast-check

backend/tests/
└── test_g10_trading_financial_liabilities_pbt.py  # 后端PBT验证(hypothesis)
```

### 单元测试重点

- **贷方公式方向验证**：验证calcCreditBalance方向与calcDebitBalance相反（opening+credit-debit vs opening+debit-credit）
- **Level3必填校验逻辑**：验证当fairValueLevel='Level3'时，valuationTechnique和unobservableInputDesc不能为空
- **异常自动检测逻辑**：验证当check1-4任一为false时，isAbnormal自动设为true
- **区段Tab行同步**：验证Tab切换后当前选中行索引不变
- **L3调节表差异计算**：验证variance = actualClosing - calcL3Reconciliation(...)
- **G10-8虚拟滚动**：验证78行启用虚拟滚动且section折叠正确
- **导入导出宽表分sheet**：验证G10-2导出2sheet、G10-5导出2sheet、G10-7导出3sheet
- **|变动率|>20%触发**：验证橙色高亮和原因分析必填联动
