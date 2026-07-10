# Design Document: F2 存货底稿特殊组（合同履约成本 + IPO/舞弊应对）专属HTML精美组件

## Overview

F2存货底稿特殊组专属组件`f2-inventory-special`。覆盖2个xlsx源模板/18有效sheet。科目1405合同履约成本（借方/资产类）+ IPO审计专项程序。

核心架构：
- componentType `f2-inventory-special`，主入口 GtF2InventorySpecial.vue
- **无内部el-tabs**：外层GtWpRenderer已有sheet目录行(chips)，专属组件接收`sheetName` prop用`v-if`分发到子组件
- 每个sheet独立子组件(150-500行) + 独立/共享composable
- 2个子目录：contract/(F2-55~F2-58) + ipo/(F2-61~F2-72)
- F2-70/F2-72采用多公司Master-Detail卡片模式
- 10个composable：useF2SpecialFormulaEngine(纯函数) + useF2SpecialFormData + useF2ContractCost + useF2Impairment + useF2LossContract + useF2IpoPurchaseAnalysis + useF2SupplierAnalysis + useF2MasterDetail + useF2SpecialImportExport + useF2SpecialDualMode
- IPO组条件可见性：business_category ∈ ['IPO','上市公司年审','新三板','重大资产重组']
- 双模式（HTML ↔ OnlyOffice）+ 导入导出三级 + AI审计说明(8 section)

## Architecture

### sheetName分发模式（非嵌套Tab）

GtF2InventorySpecial.vue 接收 `sheetName` prop（完整中文名如"合同履约成本构成明细表F2-55"），用正则提取末尾编码(F2-55A/F2-55/F2-61等)，`v-if` 分发到对应子组件。未迁移的sheet走 OnlyOffice fallback（GtOnlyOfficeSheet全高）。

```
sheetName → regex提取编码 → v-if匹配 → 子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback
```

### IPO条件可见性架构

```
project.business_category → watch → isIpoProject computed
                                        ↓
                    ┌────────────────────┴────────────────────┐
                    │ true: 渲染F2-61~F2-72 sheet chips      │
                    │ false: 隐藏F2-61~F2-72 sheet chips     │
                    └─────────────────────────────────────────┘
                    
后端render策略：
  if business_category not in IPO_CATEGORIES:
      sheets = [s for s in sheets if not s.code.startswith('F2-6')]
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtF2InventorySpecial.vue              # 主入口 sheetName v-if分发（defineAsyncComponent lazy）
├── f2-special/
│   ├── contract/
│   │   ├── F2TabContractProcedure.vue    # F2-55A 程序表（复用a-program-console+selfLoad）
│   │   ├── F2TabContractCostDetail.vue   # F2-55 合同履约成本明细（37列→6区段Tab）
│   │   ├── F2TabContractCostCheck.vue    # F2-56 合同履约成本检查（23列固定+滚动）
│   │   ├── F2TabImpairment.vue           # F2-57 减值准备测算
│   │   └── F2TabLossContract.vue         # F2-58 亏损合同预计损失测算
│   └── ipo/
│       ├── F2TabIpoProcedure.vue         # F2-61A IPO程序表（复用a-program-console+selfLoad）
│       ├── F2TabPurchasePrice.vue        # F2-61 原材料采购价格分析（118行虚拟滚动）
│       ├── F2TabUnitPrice.vue            # F2-62 原材料单价分析
│       ├── F2TabCapacityEnergy.vue       # F2-63 产量与产能/能耗分析
│       ├── F2TabUnitConsumption.vue      # F2-64 单耗分析（232行虚拟滚动+产品分组折叠）
│       ├── F2TabRelatedPartyInquiry.vue  # F2-65 关联方定价核查-询价函
│       ├── F2TabRelatedPartyMarket.vue   # F2-66 关联方定价核查-市场价
│       ├── F2TabUndisclosedRelated.vue   # F2-67 识别未披露关联方
│       ├── F2TabSupplierStructure.vue    # F2-68 重要供应商结构（25列固定+滚动）
│       ├── F2TabSupplierChecklist.vue    # F2-69 供应商核查清单
│       ├── F2TabSupplierInfoCheck.vue    # F2-70 供应商信息核查（Master-Detail）
│       ├── F2TabInterviewSummary.vue     # F2-71 供应商访谈汇总
│       └── F2TabInterviewDetail.vue      # F2-72 供应商访谈记录（Master-Detail）
├── composables/
│   ├── useF2SpecialFormData.ts           # 数据加载/保存/selfLoad（~200行）
│   ├── useF2SpecialFormulaEngine.ts     # 纯函数公式引擎15函数（~220行）
│   ├── useF2ContractCost.ts              # F2-55/56 合同履约成本明细+检查（~350行）
│   ├── useF2Impairment.ts               # F2-57 减值准备测算（~200行）
│   ├── useF2LossContract.ts             # F2-58 亏损合同预计损失（~200行）
│   ├── useF2IpoPurchaseAnalysis.ts      # F2-61/62/63/64 采购+单价+产能+单耗分析（~400行）
│   ├── useF2SupplierAnalysis.ts         # F2-65~F2-72 关联方+供应商全组（~450行）
│   ├── useF2MasterDetail.ts             # F2-70/F2-72 多公司Master-Detail通用（~180行）
│   ├── useF2SpecialImportExport.ts      # 导入导出（axios+三端点复用）（~150行）
│   └── useF2SpecialDualMode.ts          # 双模式OO健康检查（~80行）

backend/app/routers/wp_render_strategies/
├── _f2_special.py                        # render策略+注册RENDERER_DISPATCH+IPO可见性过滤
├── _f2_special_import_export.py          # 导入导出3端点
└── _f2_special_ai.py                     # AI生成8 section
```

### F2-55 合同履约成本明细 6区段Tab设计

F2-55是全spec最宽表(37列)，拆为6区段Tab：

```
┌─────────────────────────────────────────────────────────────────┐
│ [基础信息] [期初余额] [本期增加] [本期减少] [期末余额] [审计调整+审定] │  ← Tab切换
├─────────────────────────────────────────────────────────────────┤
│ 基础信息区段（4列）：                                              │
│   项目编码 | 项目名称 | 收入合同名称 | 收入合同金额                  │
├─────────────────────────────────────────────────────────────────┤
│ 期初/增加/减少/期末区段（各5列）：                                   │
│   设备材料 | 建安分包 | 人工 | 其他 | 小计                          │
├─────────────────────────────────────────────────────────────────┤
│ 审计调整+审定区段（13列）：                                         │
│   是否与合同直接相关 | 是否预期能收回                               │
│   + 审计调整(设备材料/建安分包/人工/其他/小计)                       │
│   + 期末审定金额(设备材料/建安分包/人工/其他/小计)                    │
│   + 备注                                                          │
├─────────────────────────────────────────────────────────────────┤
│ 合计行 + 审计说明 + 审计结论                                       │
└─────────────────────────────────────────────────────────────────┘
```

### F2-68 重要供应商结构 固定列+滚动列设计

```
┌──────────────────────┬─────────────────────────────────────────────┐
│ 固定列（5列）         │ 滚动列（20列）                               │
│ 始终可见              │ 横向滚动                                     │
├──────────────────────┼─────────────────────────────────────────────┤
│ 序号                  │ T期金额/占比/排名                            │
│ 供应商名称            │ T-1期金额/占比/排名                          │
│ 主要采购品类          │ T-2期金额/占比/排名                          │
│ 合作起始年份          │ 金额变动(T vs T-1)/变动率                    │
│ 是否关联方            │ 金额变动(T-1 vs T-2)/变动率                  │
│                      │ 新增/退出标记                                │
│                      │ 集中度评价 | 索引号 | 备注                    │
└──────────────────────┴─────────────────────────────────────────────┘
```

### F2-70/F2-72 多公司Master-Detail卡片模式

参照D4合同检查三模式中的卡片模式：

```
┌────────────────────┬──────────────────────────────────────────┐
│ 左侧面板（列表）   │ 右侧面板（详情）                           │
│ 260px fixed        │ flex: 1                                   │
├────────────────────┼──────────────────────────────────────────┤
│ [搜索框]           │ ┌── el-card: 基础工商信息 ──┐             │
│                    │ │ 供应商名称 / 信用代码     │             │
│ ● 供应商A ←当前    │ │ 法人 / 注册资本 / 成立日 │             │
│ ○ 供应商B          │ │ 经营范围                  │             │
│ ○ 供应商C          │ └──────────────────────────┘             │
│ ○ 供应商D          │ ┌── el-card: 经营情况 ──────┐             │
│                    │ │ 经营地址 / 员工人数       │             │
│ [+ 新增]           │ │ 主要客户 / 财务状况       │             │
│                    │ └──────────────────────────┘             │
│                    │ ┌── el-card: 审计核查 ──────┐             │
│                    │ │ 合作年限 / 交易金额       │             │
│                    │ │ 核查方式 / 核查结论       │             │
│                    │ └──────────────────────────┘             │
│                    │ 底部: 核查结论textarea + AI               │
└────────────────────┴──────────────────────────────────────────┘
```

### 合同履约成本减值/亏损公式链

```
F2-57 减值测算:
  完工进度 = 已确认收入 / 预计总收入
  待发生成本 = 预计总成本 - 已发生成本
  可收回金额 = (已确认收入/预计总收入) × 预计总成本
  减值金额 = max(0, 账面价值 - 可收回金额)
  差异 = 减值金额 - 管理层计提

F2-58 亏损判定:
  是否亏损 = 预计总成本 > 预计总收入
  亏损金额 = 预计总成本 - 预计总收入（非亏损=0）
  应确认预计损失 = 亏损金额 × (1 - 完工进度)
  本期应计提 = 应确认预计损失 - 已确认预计损失
  差异 = 本期应计提 - 管理层计提

F2-55 → F2-57 联动: 项目编码/名称/期末金额可引用
F2-57 ↔ F2-58 联动: 共享项目数据（总收入/总成本/完工进度）
```

### 后端AI Section清单

```
contract-cost-note / impairment-analysis / loss-analysis / price-analysis /
capacity-analysis / consumption-analysis / related-party-conclusion / supplier-analysis
```

### 与f2-inventory-main设计的关键差异

1. **IPO条件可见性**：f2-main所有sheet始终可见→f2-special的IPO子组(F2-61~F2-72)需business_category控制
2. **Master-Detail模式**：f2-main无Master-Detail→f2-special的F2-70/F2-72用多公司Master-Detail卡片模式
3. **公式复杂度更高**：f2-main以加减乘除为主→f2-special含减值/亏损判定/完工进度等复合公式
4. **按产品分组折叠**：f2-main的明细表平铺→f2-special的F2-64需按产品分组折叠(232行)
5. **固定+滚动列更多**：f2-main只有F2-33(22列)→f2-special的F2-55(37列)/F2-56(23列)/F2-68(25列)都需要
6. **关联方/供应商核查**：f2-special独有的IPO专项底稿(8张)，无对应f2-main模式

## Components and Interfaces

### 前端组件接口

```typescript
// GtF2InventorySpecial.vue props
interface F2InventorySpecialProps {
  htmlData: Record<string, any> | null  // render-config返回数据，bundle内嵌时为null
  sheetName: string                      // 当前sheet完整中文名
  wpId: string                           // 底稿ID
  projectId: string                      // 项目ID
  readonly?: boolean                     // 只读模式
}

// IPO可见性判定
const IPO_CATEGORIES = ['IPO', '上市公司年审', '新三板', '重大资产重组'] as const

// F2-55 六区段配置
interface ContractCostSegmentConfig {
  segments: [
    { label: '基础信息', columns: ['projectCode','projectName','contractName','contractAmount'] },
    { label: '期初余额', columns: ['opening_equipment','opening_construction','opening_labor','opening_other','opening_subtotal'] },
    { label: '本期增加', columns: ['increase_equipment','increase_construction','increase_labor','increase_other','increase_subtotal'] },
    { label: '本期减少', columns: ['decrease_equipment','decrease_construction','decrease_labor','decrease_other','decrease_subtotal'] },
    { label: '期末余额', columns: ['end_equipment','end_construction','end_labor','end_other','end_subtotal'] },
    { label: '审计调整+审定', columns: ['isDirectlyRelated','isRecoverable','adj_equipment','adj_construction','adj_labor','adj_other','adj_subtotal','audited_equipment','audited_construction','audited_labor','audited_other','audited_subtotal','remark'] },
  ]
}

// Master-Detail模式接口
interface MasterDetailConfig {
  entityLabel: string          // '供应商' | '访谈记录'
  listWidth: number            // 左侧面板宽度（默认260）
  searchable: boolean          // 列表是否支持搜索
  groupBy?: string             // F2-72按供应商分组
  detailSections: DetailSection[]  // 右侧详情区域配置
}

interface DetailSection {
  title: string
  fields: FieldDef[]
}

interface FieldDef {
  key: string
  label: string
  type: 'text' | 'textarea' | 'select' | 'date' | 'number' | 'multi-select'
  options?: string[]
  editable?: boolean
}
```

### 后端接口

```python
# _f2_special.py
def render_f2_special(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType和sheets配置
    IPO可见性过滤：检查project.business_category
    """

IPO_CATEGORIES = {'IPO', '上市公司年审', '新三板', '重大资产重组'}

# _f2_special_import_export.py
POST /api/workpapers/{wp_id}/f2-special/export-template?sheet={code}
POST /api/workpapers/{wp_id}/f2-special/export-data?sheet={code}
POST /api/workpapers/{wp_id}/f2-special/import-data?sheet={code}  # multipart/form-data

# _f2_special_ai.py
POST /api/workpapers/F2-special/ai/{section}
# sections: contract-cost-note / impairment-analysis / loss-analysis / price-analysis /
#           capacity-analysis / consumption-analysis / related-party-conclusion / supplier-analysis
```

## Data Models

### 合同履约成本明细数据模型 (F2-55)

```typescript
interface ContractCostRow {
  id: string
  projectCode: string           // 项目编码
  projectName: string           // 项目名称
  contractName: string          // 收入合同名称
  contractAmount: number        // 收入合同金额
  // 期初余额
  opening_equipment: number     // 设备材料
  opening_construction: number  // 建安分包
  opening_labor: number         // 人工
  opening_other: number         // 其他
  opening_subtotal: number      // 小计（公式）
  // 本期增加（同结构）
  increase_equipment: number
  increase_construction: number
  increase_labor: number
  increase_other: number
  increase_subtotal: number     // 公式
  // 本期减少（同结构）
  decrease_equipment: number
  decrease_construction: number
  decrease_labor: number
  decrease_other: number
  decrease_subtotal: number     // 公式
  // 期末余额（公式列）
  end_equipment: number         // = opening + increase - decrease
  end_construction: number
  end_labor: number
  end_other: number
  end_subtotal: number
  // 审计调整+审定
  isDirectlyRelated: '是' | '否'    // 是否与合同直接相关
  isRecoverable: '是' | '否'        // 是否预期能收回
  adj_equipment: number             // 审计调整
  adj_construction: number
  adj_labor: number
  adj_other: number
  adj_subtotal: number              // 公式
  audited_equipment: number         // 审定金额 = 期末 + 调整
  audited_construction: number
  audited_labor: number
  audited_other: number
  audited_subtotal: number          // 公式
  remark: string
}
```

### 减值准备测算数据模型 (F2-57)

```typescript
interface ImpairmentRow {
  id: string
  projectCode: string
  projectName: string
  estimatedTotalRevenue: number    // 合同预计总收入
  recognizedRevenue: number         // 已确认收入
  completionRate: number            // 完工进度（公式）
  estimatedTotalCost: number        // 预计总成本
  incurredCost: number              // 已发生成本
  remainingCost: number             // 待发生成本（公式）
  recoverableAmount: number         // 可收回金额（公式）
  bookValue: number                 // 账面价值
  impairmentAmount: number          // 减值金额（公式）
  managementProvision: number       // 管理层计提
  difference: number                // 差异（公式）
  remark: string
}
```

### 亏损合同预计损失数据模型 (F2-58)

```typescript
interface LossContractRow {
  id: string
  projectCode: string
  projectName: string
  estimatedTotalRevenue: number     // 合同预计总收入
  estimatedTotalCost: number        // 预计总成本
  isLoss: '是' | '否'              // 是否亏损（公式）
  lossAmount: number                // 亏损金额（公式）
  completionRate: number            // 完工进度
  recognizedLoss: number            // 已确认预计损失
  expectedLoss: number              // 应确认预计损失（公式）
  currentProvision: number          // 本期应计提（公式）
  managementProvision: number       // 管理层计提
  difference: number                // 差异（公式）
  needAdjustment: '是' | '否'      // 是否需调整（公式）
  adjustmentSuggestion: string      // 调整建议
  remark: string
}
```

### 单耗分析数据模型 (F2-64)

```typescript
interface UnitConsumptionRow {
  id: string
  productName: string               // 产品名称（分组key）
  materialName: string              // 材料名称
  spec: string                      // 规格
  unit: string                      // 单位
  standardConsumption: number       // 标准单耗
  actualConsumption: number         // 实际单耗
  deviationRate: number             // 差异率（公式）
  inputQuantity: number             // 本期投入量
  outputQuantity: number            // 本期产出量
  inputOutputRatio: number          // 投入产出比（公式）
  priorConsumption: number          // 上期单耗
  consumptionChangeRate: number     // 单耗变动率（公式）
  amountImpact: number              // 金额影响（公式）
  reasonExplanation: string         // 合理性说明
  priorYearT1: number               // T-1期对比
  priorYearT2: number               // T-2期对比
  auditAttention: string            // 审计关注
  remark: string
}
```

### Master-Detail数据模型 (F2-70/F2-72)

```typescript
// F2-70 供应商信息核查
interface SupplierInfoEntity {
  id: string
  supplierName: string              // 供应商名称（Master key）
  creditCode: string                // 统一社会信用代码
  legalRepresentative: string       // 法定代表人
  registeredCapital: string         // 注册资本
  establishDate: string             // 成立日期
  businessScope: string             // 经营范围
  operatingAddress: string          // 实际经营地址
  employeeCount: number             // 员工人数
  mainCustomers: string             // 主要客户
  financialStatus: string           // 财务状况
  cooperationYears: number          // 合作年限
  transactionAmount: number         // 交易金额
  checkMethod: string               // 核查方式
  checkConclusion: string           // 核查结论
}

// F2-72 供应商访谈记录
interface InterviewEntity {
  id: string
  supplierName: string              // 供应商名称（分组key）
  interviewDate: string             // 访谈日期
  interviewee: string               // 受访人
  topic: string                     // 访谈主题
  qaPairs: { question: string; answer: string }[]  // 问答对（动态增删）
  auditConcerns: string             // 审计关注点
  conclusion: string                // 访谈结论
}
```

## Error Handling

1. **selfLoad失败**：render-config返回404/500时显示错误卡片+重试按钮，不白屏
2. **IPO可见性判定失败**：business_category字段缺失时默认显示合同组(F2-55~F2-58)，隐藏IPO组(F2-61~F2-72)
3. **公式计算异常**：除零保护（设计产能=0/预计总收入=0→'N/A'）；max(0,x)确保减值非负
4. **Master-Detail数据缺失**：供应商列表为空时显示空状态+引导新增
5. **导入格式错误**：后端返回详细错误列表（行号/字段/原因），前端弹窗展示
6. **虚拟滚动边界**：F2-64按产品分组折叠时，计算可见行高度需包含组头高度
7. **AI生成超时**：30秒超时→取消请求+提示"生成超时，请重试"
8. **OnlyOffice连接失败**：健康检查失败→自动降级HTML模式+toast提示
9. **跨sheet联动**：F2-55→F2-57项目数据引用，源数据缺失时显示"未录入"占位

## Testing Strategy

### 前端PBT测试

| 测试文件 | 覆盖Property | 框架 |
|----------|-------------|------|
| useF2SpecialFormulaEngine.pbt.spec.ts | P1~P12 | vitest + fast-check |

### 后端测试

| 测试文件 | 覆盖范围 |
|----------|----------|
| test_f2_special_import_export_pbt.py | 导入导出round-trip正确性 |
| test_f2_special.py | render策略+注册契约+IPO可见性过滤 |

### 集成测试

- sheetName分发正确性（18个编码→对应组件）
- IPO可见性（business_category控制F2-61~F2-72显示/隐藏）
- 合同履约成本公式链（F2-55→F2-57→F2-58联动）
- Master-Detail模式（F2-70/F2-72 CRUD）
- F2-55六区段Tab切换+行同步
- F2-64虚拟滚动+产品分组折叠
- F2-68固定列+滚动列
- 导入导出round-trip

## Correctness Properties

### Property 1: 待发生成本公式
∀ totalCost, incurredCost ∈ ℝ≥0: calcRemainingCost(totalCost, incurredCost) === totalCost - incurredCost
**Validates: Requirements 18.1, 5.3**

### Property 2: 减值公式非负性
∀ bookValue, recoverableAmount ∈ ℝ≥0: calcImpairment(bookValue, recoverableAmount) >= 0
**Validates: Requirements 18.2, 5.5**

### Property 3: 亏损判定一致性
∀ totalRevenue, totalCost ∈ ℝ≥0: isLossContract(totalRevenue, totalCost) === (totalCost > totalRevenue)
**Validates: Requirements 18.4, 6.2**

### Property 4: 预计损失公式
∀ totalRevenue, totalCost ∈ ℝ≥0 where totalCost>totalRevenue, completionRate ∈ [0,1]: calcExpectedLoss(totalRevenue, totalCost, completionRate) === (totalCost - totalRevenue) × (1 - completionRate)
**Validates: Requirements 18.5, 6.4**

### Property 5: 完工进度范围
∀ recognizedRevenue ∈ ℝ≥0, totalRevenue ∈ ℝ>0: calcCompletionRate(recognizedRevenue, totalRevenue) === recognizedRevenue/totalRevenue
**Validates: Requirements 18.6, 5.2**

### Property 6: 产能利用率公式
∀ actual, designed ∈ ℝ>0: calcCapacityUtilization(actual, designed) === actual/designed
**Validates: Requirements 18.7, 9.2**

### Property 7: 价差率公式
∀ actualPrice ∈ ℝ, refPrice ∈ ℝ\{0}: calcPriceDeviation(actualPrice, refPrice) === (actualPrice - refPrice)/refPrice
**Validates: Requirements 18.9, 11.3**

### Property 8: 集中度公式
∀ supplierAmount, totalAmount ∈ ℝ>0: calcConcentrationRatio(supplierAmount, totalAmount) === supplierAmount/totalAmount
**Validates: Requirements 18.10, 13.2**

### Property 9: 期末余额公式
∀ opening, increase, decrease ∈ ℝ: calcEndBalance(opening, increase, decrease) === opening + increase - decrease
**Validates: Requirements 18.13, 3.2**

### Property 10: 分类小计公式
∀ equipment, construction, labor, other ∈ ℝ: calcSubtotalByCategory(equipment, construction, labor, other) === equipment + construction + labor + other
**Validates: Requirements 18.12, 3.4**

### Property 11: 投入产出比公式
∀ input, output ∈ ℝ>0: calcInputOutputRatio(input, output) === input/output
**Validates: Requirements 18.15, 10.4**

### Property 12: 核查完成度公式
∀ completed ∈ ℤ≥0, total ∈ ℤ>0, notApplicable ∈ ℤ≥0 where total>notApplicable: calcChecklistCompletion(completed, total, notApplicable) === completed/(total-notApplicable)×100
**Validates: Requirements 18.11, 14.3**
