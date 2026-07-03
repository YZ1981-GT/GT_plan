# Design Document: G0 投资循环函证

## Overview

G0投资循环函证。覆盖1个xlsx源模板(878KB)/9有效sheet。科目：交易性金融资产/债权投资/长期股权投资/其他权益工具投资。复用D0共享函证组件(7个直接映射) + 新建2个（confirmation-diff-securities + confirmation-alternative-g06）。

核心架构：
- 7个sheet直接映射D0已有共享组件（confirmation-summary/entity-verify/followup/diff-reconcile/reliability/fraud-risk + a-program-console）
- **2个新建组件**：G0-3(证券)差异核对 + G0-6投资替代程序
- G0-3(证券)：多公司Master-Detail，证券持仓/公允价值/市值三维差异核对
- G0-6：多公司Master-Detail，4区块29列宽表（持仓证明/股利收入/处置收益/公允价值佐证）
- 宽表拆分：G0-6(29列→4区块各拆为左右视觉分组)
- 特色：证券投资vs非证券投资两种差异核对模式 + 公允价值Level1-3佐证

## Architecture

### D0共享组件复用 + 新建组件

```
G0 函证模块（9 sheets）
├── G0A  → a-program-console（复用）
├── G0-1 → confirmation-summary（复用D0）
├── G0-2 → confirmation-entity-verify（复用D0）
├── G0-3 → confirmation-followup（复用D0）
├── G0-3S→ confirmation-diff-securities ★新建
├── G0-4 → confirmation-diff-reconcile（复用D0）
├── G0-6 → confirmation-alternative-g06 ★新建
├── G0-7 → confirmation-reliability（复用D0）
└── G0-8 → confirmation-fraud-risk（复用D0）
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtConfirmationDiffSecurities.vue        # G0-3(证券) 差异核对-证券投资
├── GtConfirmationAlternativeG06.vue        # G0-6 投资循环替代程序
├── g0-confirmation/
│   ├── composables/
│   │   ├── useDiffSecuritiesData.ts        # 证券差异核对数据管理
│   │   ├── useAlternativeG06Data.ts        # 替代程序4区块数据管理
│   │   ├── useG0FormulaEngine.ts           # G0公式引擎(差异/处置损益/股利)
│   │   ├── useG0ImportExport.ts            # 导入导出composable
│   │   └── useG0DualMode.ts                # 双模式OO切换

backend/app/routers/wp_render_strategies/
├── _g0_confirmation.py                     # render策略+注册RENDERER_DISPATCH(2个)
├── _g0_confirmation_import_export.py       # 导入导出3端点
└── _g0_confirmation_ai.py                  # AI生成2 section
```

### G0-3(证券) 差异核对表设计（17列）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Master: 证券列表（左侧Panel / el-select）                                │
├─────────────────────────────────────────────────────────────────────────┤
│ ┌── 差异汇总区 ──────────────────────────────────────────────────────┐ │
│ │ 证券名称 | 证券代码 | 回函持仓 | 账面持仓 | 数量差异              │ │
│ │ 回函公允值 | 账面公允值 | 公允价值差异 | 差异原因分类               │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ ┌── 明细核对区（17列 el-table）─────────────────────────────────────┐  │
│ │ 序号|证券名称|证券代码|证券类型|回函持仓数量|账面持仓数量|         │  │
│ │ 数量差异(公式)|回函单位公允值|账面单位公允值|公允价值差异(公式)|    │  │
│ │ 回函总市值|账面总市值|市值差异(公式)|差异原因|调节事项|核实结论|备注│  │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ 底部汇总：核对笔数/有差异笔数/无差异笔数/最大单笔差异                     │
│ 审计结论 textarea + AI按钮                                               │
└─────────────────────────────────────────────────────────────────────────┘
```

### G0-6 替代程序检查表设计（29列→4区块）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Master: 投资项目列表（左侧Panel / el-select）                            │
├─────────────────────────────────────────────────────────────────────────┤
│ ┌── 余额汇总区 ──────────────────────────────────────────────────────┐ │
│ │ 投资类型 | 年初余额 | 本期增加 | 本期减少 | 期末余额 | 投资收益 |   │ │
│ │ 公允价值变动                                                        │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── 抽样参数区 ──────────────────────────────────────────────────────┐ │
│ │ 6字段textarea: 测试范围/特定样本/抽样总体/确定样本量/抽样方法/抽样过程│ │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ ┌── ①持仓证明检查（15列：记账凭证5列 | 检查证据10列）──────────────┐  │
│ │ [记账凭证] 日期|凭证编号|业务内容|对方科目|金额                    │  │
│ │ [检查证据] 对账单日期|品种|数量|市值 | 托管确认函|确认日期 |        │  │
│ │            中登查询日|持仓一致性|索引号                             │  │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── ②投资收益/股利收入证据（14列）────────────────────────────────┐  │
│ │ [记账凭证] 日期|凭证编号|业务内容|对方科目|金额                    │  │
│ │ [检查证据] 分红公告日期|每股股利|应收金额 | 银行回单日期|到账金额 |  │  │
│ │            红利税扣缴|实收金额|差异|索引号                          │  │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── ③投资处置收益证据（15列）──────────────────────────────────────┐  │
│ │ [记账凭证] 日期|凭证编号|业务内容|对方科目|金额                    │  │
│ │ [检查证据] 交易确认单日期|卖出数量|成交价|成交金额 | 原始成本|      │  │
│ │            处置损益(公式) | 手续费|净收入|银行到账|索引号            │  │
│ └──────────────────────────────────────────────────────────────────────┘ │
│ ┌── ④公允价值佐证（14列）──────────────────────────────────────────┐  │
│ │ [记账凭证] 日期|凭证编号|业务内容|对方科目|金额                    │  │
│ │ [检查证据] 报价来源|报价日期|报价值 | 估值模型|估值假设|Level层级 | │  │
│ │            账面vs报价差异|合理性判断|索引号                          │  │
│ └──────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ 审计说明 textarea + 审计结论 textarea（均支持AI辅助）                      │
└─────────────────────────────────────────────────────────────────────────┘
```

### 数据流

```
G0-1 函证结果汇总 ── 未回函项目列表 ──→ G0-6 替代程序（反向联动）
G0-3(证券) 差异核对 ── 证券差异数据 ──→ 函证结论
G0-6 替代程序 ── 检查结果 ──→ 函证结论
useVersionTrail ── autoSnapshot on save ──→ 版本快照
```

### 后端AI Section清单

```
securities-diff-conclusion / alternative-audit-conclusion
```

## Components and Interfaces

### 前端组件接口

```typescript
// GtConfirmationDiffSecurities.vue props
interface DiffSecuritiesProps {
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}

// G0-3(证券) 差异核对行
interface SecuritiesDiffRow {
  id: string
  seq: number
  securityName: string          // 证券名称
  securityCode: string          // 证券代码
  securityType: 'stock' | 'fund' | 'bond'  // 证券类型
  confirmedQuantity: number     // 回函持仓数量
  bookedQuantity: number        // 账面持仓数量
  quantityDiff: number          // 数量差异(公式)
  confirmedUnitFV: number       // 回函单位公允价值
  bookedUnitFV: number          // 账面单位公允价值
  fairValueDiff: number         // 公允价值差异(公式)
  confirmedMarketValue: number  // 回函总市值
  bookedMarketValue: number     // 账面总市值
  marketValueDiff: number       // 市值差异(公式)
  diffReason: string            // 差异原因
  reconciliationItem: string    // 调节事项
  conclusion: string            // 核实结论
  remark: string
}

// G0-6 替代程序-持仓证明检查行
interface HoldingCheckRow {
  id: string
  seq: number
  // 记账凭证
  date: string
  voucherNo: string
  content: string
  counterAccount: string
  amount: number
  // 检查证据
  statementDate: string
  holdingItem: string
  holdingQuantity: number
  marketValue: number
  custodianConfirmRef: string
  custodianConfirmDate: string
  csdcQueryDate: string
  holdingConsistency: string
  indexRef: string
}

// G0-6 替代程序-处置收益证据行
interface DisposalEvidenceRow {
  id: string
  seq: number
  // 记账凭证
  date: string
  voucherNo: string
  content: string
  counterAccount: string
  amount: number
  // 检查证据
  tradeConfirmDate: string
  soldQuantity: number
  tradePrice: number
  tradeAmount: number
  originalCost: number
  disposalGain: number          // 公式=成交金额-原始成本-手续费
  commission: number
  netProceeds: number
  bankReceipt: number
  indexRef: string
}

// G0-6 替代程序-公允价值佐证行
interface FairValueEvidenceRow {
  id: string
  seq: number
  // 记账凭证
  date: string
  voucherNo: string
  content: string
  counterAccount: string
  amount: number
  // 检查证据
  quoteSource: string           // 报价来源(交易所/Wind/Bloomberg)
  quoteDate: string
  quoteValue: number
  valuationModel: string        // 估值模型
  valuationAssumptions: string  // 估值假设
  fairValueLevel: '1' | '2' | '3'  // Level层级
  bookVsQuoteDiff: number       // 账面vs报价差异
  reasonableness: string        // 合理性判断
  indexRef: string
}
```

### 后端接口

```python
# _g0_confirmation.py
def render_g0_diff_securities(wp_id: str, config: dict) -> dict:
    """Render策略: confirmation-diff-securities"""

def render_g0_alternative(wp_id: str, config: dict) -> dict:
    """Render策略: confirmation-alternative-g06"""

# _g0_confirmation_import_export.py
POST /api/workpapers/{wp_id}/g0/export-template?sheet={code}
POST /api/workpapers/{wp_id}/g0/export-data?sheet={code}
POST /api/workpapers/{wp_id}/g0/import-data?sheet={code}

# _g0_confirmation_ai.py
POST /api/workpapers/{wp_id}/g0/ai/{section}
# section: securities-diff-conclusion / alternative-audit-conclusion
```

## Data Models

### G0-3(证券) 差异汇总数据

```typescript
interface SecuritiesDiffSummary {
  totalItems: number             // 核对笔数
  withDifference: number         // 有差异笔数
  noDifference: number           // 无差异笔数
  maxSingleDiff: number          // 最大单笔差异(绝对值)
}
```

### G0-6 替代程序余额汇总

```typescript
interface AlternativeG06Summary {
  investmentType: string         // 投资类型
  openingBalance: number         // 年初余额
  currentIncrease: number        // 本期增加
  currentDecrease: number        // 本期减少
  closingBalance: number         // 期末余额
  investmentIncome: number       // 投资收益
  fairValueChange: number        // 公允价值变动
}
```

## Error Handling

1. **Master-Detail加载失败**：左侧证券/项目列表加载失败时显示错误提示+重试按钮
2. **差异计算异常**：parseNum兜底（NaN→0），确保差异始终为数值
3. **处置损益负值**：允许负值（亏损处置），但>成本50%时橙色提示
4. **公允价值Level3**：Level3无市场报价时，差异列显示"N/A（需估值模型）"
5. **导入格式错误**：后端返回详细错误列表（行号/字段/原因）
6. **OCR识别失败**：返回空结果时toast"未识别到有效证券信息"
7. **反向联动失败**：G0-1未回函列表为空时，G0-6显示"暂无待替代程序项目"

## Testing Strategy

### 前端PBT测试

| 测试文件 | 覆盖Property | 框架 |
|----------|-------------|------|
| useG0FormulaEngine.pbt.spec.ts | P1~P8 | vitest + fast-check |

### 后端测试

| 测试文件 | 覆盖范围 |
|----------|----------|
| test_g0_confirmation_pbt.py | 差异计算/处置损益round-trip |
| test_g0_confirmation.py | render策略+注册契约 |

### 集成测试

- wp_code_overrides映射正确性（10条G0映射）
- G0-3(证券)差异计算三维公式（数量/公允价值/市值）
- G0-6处置损益公式（成交-成本-手续费）
- G0-6四区块独立增删行+合计
- G0-1→G0-6反向联动（未回函项目传入）
- 导入导出round-trip
- 版本快照autoSnapshot

## Correctness Properties

### Property 1: 数量差异公式
∀ confirmed, booked ∈ ℤ: calcQuantityDiff(confirmed, booked) === confirmed - booked
**Validates: Requirements 2.5, 7.1**

### Property 2: 公允价值差异公式
∀ confirmedFV, bookedFV ∈ ℝ: calcFairValueDiff(confirmedFV, bookedFV) === confirmedFV - bookedFV
**Validates: Requirements 2.6, 7.2**

### Property 3: 市值差异公式
∀ confirmedMV, bookedMV ∈ ℝ≥0: calcMarketValueDiff(confirmedMV, bookedMV) === confirmedMV - bookedMV
**Validates: Requirements 2.7, 7.3**

### Property 4: 处置损益公式
∀ proceeds, cost, fee ∈ ℝ≥0: calcDisposalGain(proceeds, cost, fee) === proceeds - cost - fee
**Validates: Requirements 3.13, 7.4**

### Property 5: 股利差异恒等
∀ declared, received, tax ∈ ℝ≥0: calcDividendDiff(declared, received, tax) === declared - received - tax
**Validates: Requirements 7.5**

### Property 6: 差异判定对称性
∀ a, b ∈ ℝ: hasDifference(a, b) === hasDifference(b, a)
**Validates: Requirements 7.6**

### Property 7: 零差异恒等
∀ v ∈ ℝ: calcQuantityDiff(v, v) === 0 ∧ calcFairValueDiff(v, v) === 0
**Validates: Requirements 7.1, 7.2, 7.3**

### Property 8: 处置损益与手续费反比
∀ proceeds, cost固定, fee1 > fee2 ≥ 0: calcDisposalGain(proceeds, cost, fee1) < calcDisposalGain(proceeds, cost, fee2)
**Validates: Requirements 7.4**
