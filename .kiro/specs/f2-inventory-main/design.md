# Design Document: F2 存货底稿核心组专属HTML精美组件

## Overview

F2存货底稿核心组专属组件`f2-inventory-main`。平台第二大单科目底稿（4个xlsx源模板/35有效sheet/~500+公式）。科目1401~1412存货（借方科目/资产类）。

核心架构：
- componentType `f2-inventory-main`，主入口 GtF2InventoryMain.vue
- **无内部el-tabs**：外层GtWpRenderer已有sheet目录行(chips)，专属组件接收`sheetName` prop用`v-if`分发到子组件
- 每个sheet独立子组件(150-500行) + 独立/共享composable
- 通用明细表组件F2DetailSheet.vue覆盖F2-3~F2-13共11张相似结构表
- 通用截止测试组件F2CutoffSheet.vue覆盖F2-29~F2-32共4张表
- 12个composable：useF2FormulaEngine(纯函数) + useF2FormData + useF2CrossSheet + useF2Adjudication + useF2DetailSheet + useF2Adjustment + useF2Policy + useF2Analysis + useF2CutoffTest + useF2PurchaseInspection + useF2ImportExport + useF2DualMode
- 跨sheet数据流通过 allResponses Map computed 响应式链（不走API）
- 4方EventBus联动 + GtIndexChip交叉索引
- 双模式（HTML ↔ OnlyOffice）+ 导入导出三级(useF2ImportExport) + AI审计说明(5 section)

## Architecture

### sheetName分发模式（非嵌套Tab）

GtF2InventoryMain.vue 接收 `sheetName` prop（完整中文名如"存货审定表F2-1"），用正则提取末尾编码(F2-1/F2-3等)，`v-if` 分发到对应子组件。未迁移的sheet走 OnlyOffice fallback（GtOnlyOfficeSheet全高）。

```
sheetName → regex提取编码 → v-if匹配 → 子组件渲染
                                     ↘ 未匹配 → OnlyOffice fallback
```

### 文件结构

```
audit-platform/frontend/src/components/workpaper/
├── GtF2InventoryMain.vue                 # 主入口 sheetName v-if分发（defineAsyncComponent lazy）
├── f2/
│   ├── core/
│   │   ├── F2TabProcedure.vue            # F2A 程序表（复用a-program-console+selfLoad）
│   │   ├── F2TabAdjudication.vue         # F2-1 审定表（三大块：原值/跌价/净值）
│   │   ├── F2TabDetailSummary.vue        # F2-2 明细汇总表（只读聚合）
│   │   ├── F2TabAdjustment.vue           # F2-14 调整分录
│   │   ├── F2TabDisclosureListed.vue     # 附注披露(上市)
│   │   └── F2TabDisclosureSoe.vue        # 附注披露(国企)
│   ├── detail/
│   │   ├── F2DetailSheet.vue             # 通用明细表组件（config驱动，覆盖F2-3~F2-13）
│   │   └── F2DetailSheetDev.vue          # F2-10开发产品专用（35列→5区段Tab）
│   ├── analysis/
│   │   ├── F2TabPolicy.vue               # F2-16 会计政策
│   │   ├── F2TabOverallAnalysis.vue      # F2-18 总体分析
│   │   ├── F2TabProductionSales.vue      # F2-19 产销量变动
│   │   └── F2TabCostComparison.vue       # F2-20 成本比较
│   └── inspection/
│       ├── F2CutoffSheet.vue             # 通用截止测试组件（config驱动，覆盖F2-29~F2-32）
│       ├── F2TabPurchaseInspection.vue   # F2-33 采购入库检查（22列固定+滚动）
│       ├── F2TabMaterialUsage.vue        # F2-34 材料领用检查
│       └── F2TabSubcontracting.vue       # F2-35 委托加工核查
├── composables/
│   ├── useF2FormData.ts                  # 数据加载/保存/selfLoad/writebackTB（~200行）
│   ├── useF2FormulaEngine.ts             # 纯函数公式引擎13函数（~180行）
│   ├── useF2CrossSheet.ts                # 跨sheet联动computed（~350行）
│   ├── useF2Adjudication.ts              # F2-1 审定表三大块（~400行）
│   ├── useF2DetailSheet.ts               # F2-3~F2-13 通用明细表逻辑（~250行）
│   ├── useF2Adjustment.ts                # F2-14 调整分录（~150行）
│   ├── useF2Policy.ts                    # F2-16 会计政策（~120行）
│   ├── useF2Analysis.ts                  # F2-18/19/20 分析组通用（~250行）
│   ├── useF2CutoffTest.ts               # F2-29~32 截止测试通用（~180行）
│   ├── useF2PurchaseInspection.ts        # F2-33/34/35 检查组（~200行）
│   ├── useF2ImportExport.ts              # 导入导出（axios+三端点复用）（~150行）
│   └── useF2DualMode.ts                  # 双模式OO健康检查（~80行）

backend/app/routers/wp_render_strategies/
├── _f2_inventory_main.py                 # render策略+注册RENDERER_DISPATCH
├── _f2_import_export.py                  # 导入导出3端点（export-template/export-data/import-data）
├── _f2_ai_generate.py                    # AI生成5 section
└── _f2_resolvers.py                      # 3 resolver（f2_tb_inventory/f2_detail_aggregation/f2_aging_distribution）
```

### 通用组件设计（减少代码重复）

**F2DetailSheet.vue** — 11张明细表通用组件

通过`config`prop传入差异配置（列定义/区段划分/特殊校验），共享核心逻辑：
- 区段Tab切换（期初/增加/减少/期末/库龄）
- 动态行增删（ElMessageBox.prompt输入品名）
- 合计行自动计算
- 公式链（期末=期初+增加-减少；单价=金额/数量）
- 库龄合计校验（≠期末金额时橙色高亮）
- 虚拟滚动（>100行）
- 导入导出

```typescript
interface DetailSheetConfig {
  sheetCode: string           // 'F2-3' | 'F2-4' | ... | 'F2-13'
  categoryLabel: string       // '原材料' | '材料采购在途' | ...
  segments: SegmentDef[]      // 区段Tab定义
  extraColumns?: ColumnDef[]  // 差异列（如F2-8库存商品多"出库方式"列）
  hasQuantity: boolean        // 是否有数量列（F2-12合同履约成本无数量）
}
```

**F2CutoffSheet.vue** — 4张截止测试通用组件

通过`config`prop区分：入库/出库 × 正向/反向。列结构差异仅在入库15列 vs 出库10列。

```typescript
interface CutoffSheetConfig {
  sheetCode: string           // 'F2-29' | 'F2-30' | 'F2-31' | 'F2-32'
  direction: 'inbound' | 'outbound'
  testType: 'forward' | 'backward'
  columns: ColumnDef[]        // 差异列定义
}
```

### 审定表三大块结构设计

F2-1审定表148行×11列，核心结构：

```
┌─────────────────────────────────────────────────────────────┐
│ 一、存货原值（可折叠 el-card）                                │
│   ┌─────────┬────────┬──────────┬──────────┬────────┬─────┐ │
│   │ 项目    │ 期初数 │ 本期增加 │ 本期减少 │ 期末数 │索引 │ │
│   ├─────────┼────────┼──────────┼──────────┼────────┼─────┤ │
│   │ 原材料  │        │          │          │        │     │ │ ← 未审数行
│   │         │        │          │          │        │     │ │ ← 账项调整行
│   │         │        │          │          │        │     │ │ ← 审定数行（=未审+调整）
│   │ ...×13类│        │          │          │        │     │ │
│   │ 合计    │  SUM   │   SUM    │   SUM    │  SUM   │     │ │
│   └─────────┴────────┴──────────┴──────────┴────────┴─────┘ │
├─────────────────────────────────────────────────────────────┤
│ 二、存货跌价准备（可折叠 el-card，结构同上）                   │
├─────────────────────────────────────────────────────────────┤
│ 三、存货净值（可折叠 el-card，默认折叠）                       │
│   各类别净值 = 原值审定行期末数 - 跌价审定行期末数              │
│   净值合计 = 原值合计 - 跌价合计                              │
├─────────────────────────────────────────────────────────────┤
│ 试算平衡表数 / 差异数 / 审计说明 / 审计结论                    │
└─────────────────────────────────────────────────────────────┘
```

### 跨Sheet数据流

```
F2-3~F2-13 明细表 ──聚合──→ F2-2 汇总表 ──汇总──→ F2-1 审定表(原值区)
                                                       ↑
F2-14 调整分录 ──────────────AJE合计──────────────────→ F2-1(账项调整行)
                                                       ↓
                                              F2-1 审定表(跌价区)
                                                       ↓
                                              F2-1 审定表(净值区) = 原值 - 跌价
                                                       ↓
                                              TB回写(1401~1412)
                                                       ↓
                                              附注披露(取审定数)
```

### EventBus事件

| 事件名 | 发布者 | 消费者 |
|--------|--------|--------|
| `substantive:adjudicated` | F2-1 | TB回写（存货科目组1401~1412） |
| `adjustment:created` | F2-14 | F2-1审定表, A13 |
| `analytical:significant-change` | F2-18/19/20 | A1-13 |
| `risk:updated` | B50 | F2A |

### 后端AI Section清单

```
adj-note / adj-conclusion / analysis-conclusion / cutoff-conclusion / policy-evaluation
```

### 与D4设计的关键差异

1. **通用组件模式**：D4每个sheet独立Vue组件→F2用F2DetailSheet.vue通用组件覆盖11张相似明细表（config驱动差异）
2. **三大块审定表**：D4审定表单级结构→F2三大块(原值/跌价/净值)可折叠结构
3. **明细表区段统一**：D4明细表各自不同→F2-3~F2-13统一"期初/增加/减少/期末/库龄"5区段
4. **截止测试通用化**：D4截止正向/反向独立→F2用F2CutoffSheet通用组件config驱动4张表
5. **科目组映射**：D4单科目6001→F2多科目组1401~1412按类别映射TB回写
6. **composable更少**：D4有16个composable→F2用12个（通用组件减少独立composable需求）

## Components and Interfaces

### 前端组件接口

```typescript
// GtF2InventoryMain.vue props
interface F2InventoryMainProps {
  htmlData: Record<string, any> | null  // render-config返回数据，bundle内嵌时为null
  sheetName: string                      // 当前sheet完整中文名
  wpId: string                           // 底稿ID
  projectId: string                      // 项目ID
  readonly?: boolean                     // 只读模式
}

// F2DetailSheet.vue props
interface F2DetailSheetProps {
  config: DetailSheetConfig
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  readonly?: boolean
}

// F2CutoffSheet.vue props
interface F2CutoffSheetProps {
  config: CutoffSheetConfig
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  readonly?: boolean
}

// DetailSheetConfig
interface DetailSheetConfig {
  sheetCode: string           // 'F2-3' | 'F2-4' | ... | 'F2-13'
  categoryLabel: string       // '原材料' | '材料采购在途' | ...
  segments: SegmentDef[]      // 区段Tab定义
  extraColumns?: ColumnDef[]  // 差异列
  hasQuantity: boolean        // 是否有数量列
}

// CutoffSheetConfig
interface CutoffSheetConfig {
  sheetCode: string           // 'F2-29' | 'F2-30' | 'F2-31' | 'F2-32'
  direction: 'inbound' | 'outbound'
  testType: 'forward' | 'backward'
  columns: ColumnDef[]
}

// SegmentDef
interface SegmentDef {
  label: string               // Tab标签（如"期初"/"本期增加"）
  columns: ColumnDef[]        // 该区段的列定义
}

// ColumnDef
interface ColumnDef {
  key: string                 // 字段key
  label: string               // 列标题
  width?: number              // min-width
  type: 'number' | 'text' | 'select' | 'date' | 'index'
  formula?: string            // 公式表达式（如"opening + increase - decrease"）
  editable?: boolean          // 是否可编辑（默认true）
  options?: string[]          // select类型的选项
}
```

### 后端接口

```python
# _f2_inventory_main.py
def render_f2_inventory_main(wp_id: str, config: dict) -> dict:
    """Render策略函数，返回componentType和sheets配置"""

# _f2_import_export.py
POST /api/workpapers/{wp_id}/f2/export-template?sheet={code}
POST /api/workpapers/{wp_id}/f2/export-data?sheet={code}
POST /api/workpapers/{wp_id}/f2/import-data?sheet={code}  # multipart/form-data

# _f2_ai_generate.py
POST /api/workpapers/F2/ai/{section}  # section: adj-note/adj-conclusion/analysis-conclusion/cutoff-conclusion/policy-evaluation

# _f2_resolvers.py
# 注册到 auto_data_resolvers._REGISTRY
f2_tb_inventory(project_id, year, scope) -> dict
f2_detail_aggregation(project_id, year, scope) -> dict
f2_aging_distribution(project_id, year, scope) -> dict
```

## Data Models

### 审定表数据模型

```typescript
interface AdjudicationRow {
  rowKey: string              // 唯一标识
  label: string               // 类别名称（如"原材料"）
  category: string            // 类别代码
  section: 'originalValue' | 'impairment' | 'netValue'
  rowType: 'unadjusted' | 'adjustment' | 'audited' | 'total'
  openingAmount: number       // 期初数
  increaseAmount: number      // 本期增加
  decreaseAmount: number      // 本期减少
  endAmount: number           // 期末数（公式列）
  indexRef: string            // 索引引用
}

// 13类别常量
const INVENTORY_CATEGORIES = [
  'raw_material',           // 原材料
  'material_in_transit',    // 材料采购在途
  'turnover_material',      // 周转材料
  'semi_finished',          // 自制半成品
  'subcontracting',         // 委托加工
  'finished_goods',         // 库存商品
  'goods_shipped',          // 发出商品
  'development_product',    // 开发产品
  'development_cost',       // 开发成本
  'contract_cost',          // 合同履约成本
  'biological_asset',       // 消耗性生物资产
  'price_difference',       // 商品进销差价
  'impairment_provision',   // 存货跌价准备
] as const
```

### 明细表数据模型

```typescript
interface DetailRow {
  id: string                  // 行ID
  name: string                // 品名
  spec?: string               // 规格型号
  openingQty: number          // 期初数量
  openingPrice: number        // 期初单价（公式）
  openingAmount: number       // 期初金额
  increaseQty: number         // 增加数量
  increasePrice: number       // 增加单价（公式）
  increaseAmount: number      // 增加金额
  decreaseQty: number         // 减少数量
  decreasePrice: number       // 减少单价（公式）
  decreaseAmount: number      // 减少金额
  endQty: number              // 期末数量（公式）
  endPrice: number            // 期末单价（公式）
  endAmount: number           // 期末金额（公式）
  aging1Year: number          // 库龄1年以内
  aging1to2: number           // 库龄1-2年
  aging2to3: number           // 库龄2-3年
  agingOver3: number          // 库龄3年以上
  extra?: Record<string, any> // 扩展字段（按config差异）
}
```

### 截止测试数据模型

```typescript
interface CutoffRow {
  id: string
  seq: number                 // 序号
  supplier?: string           // 供应商（入库用）
  department?: string         // 领用部门（出库用）
  docNumber: string           // 单据号
  docDate: string             // 单据日期
  itemName: string            // 品名
  qty: number                 // 数量
  amount: number              // 金额
  voucherNumber?: string      // 记账凭证号
  bookingDate: string         // 记账日期
  isCrossPeriod: boolean      // 是否跨期（公式）
  belongPeriod?: string       // 应归属期间
  bookPeriod?: string         // 入账期间
  isCutoffCorrect: boolean    // 截止是否正确（公式）
  adjustSuggestion?: string   // 调整建议
  remark?: string             // 备注
}
```

## Error Handling

1. **selfLoad失败**：render-config返回404/500时显示错误卡片+重试按钮，不白屏
2. **公式计算异常**：parseNum兜底（NaN/Infinity→0），除零保护（qty=0→'-'）
3. **跨sheet数据缺失**：聚合computed容错（源sheet数据为空→返回全0行，不崩溃）
4. **导入格式错误**：后端返回详细错误列表（行号/字段/原因），前端弹窗展示
5. **TB回写失败**：catch后toast错误提示，不影响当前编辑状态
6. **OnlyOffice连接失败**：健康检查失败→自动降级HTML模式+toast提示
7. **AI生成超时**：30秒超时→取消请求+提示"生成超时，请重试"
8. **虚拟滚动边界**：行数0时不启用虚拟滚动；行数>5000时限制显示+提示导出处理

## Testing Strategy

### 前端PBT测试

| 测试文件 | 覆盖Property | 框架 |
|----------|-------------|------|
| useF2FormulaEngine.pbt.spec.ts | P1~P9 | vitest + fast-check |
| useF2CrossSheet.pbt.spec.ts | P10, P11 | vitest + fast-check |
| useF2CutoffTest.pbt.spec.ts | P12 | vitest + fast-check |

### 后端测试

| 测试文件 | 覆盖范围 |
|----------|----------|
| test_f2_import_export_pbt.py | 导入导出round-trip正确性 |
| test_f2_resolvers.py | resolver数据正确性 |
| test_f2_inventory_main.py | render策略+注册契约 |

### 集成测试

- sheetName分发正确性（35个编码→对应组件）
- 三大块净值联动（原值-跌价=净值，13类别）
- 明细→汇总→审定聚合链
- 导入导出round-trip
- 双模式切换

## Correctness Properties

### Property 1: 期末余额公式
∀ opening, increase, decrease ∈ ℝ: calcEndBalance(opening, increase, decrease) === opening + increase - decrease
**Validates: Requirements 18.2, 5.3, 5.4**

### Property 2: 净值公式
∀ originalValue, impairment ∈ ℝ≥0: calcNetValue(originalValue, impairment) === originalValue - impairment
**Validates: Requirements 18.3, 2.5**

### Property 3: 审定数公式
∀ unadjusted, aje ∈ ℝ: calcAuditedAmount(unadjusted, aje) === unadjusted + aje
**Validates: Requirements 18.4, 2.3**

### Property 4: 合计行恒等
∀ arr: number[]: calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)
**Validates: Requirements 18.7, 5.6**

### Property 5: 库龄合计恒等
∀ a,b,c,d ∈ ℝ≥0: calcAgingTotal(a,b,c,d) === a+b+c+d
**Validates: Requirements 18.6, 5.7**

### Property 6: 单价公式
∀ amount ∈ ℝ, qty ∈ ℝ\{0}: calcUnitPrice(amount, qty) === amount/qty
**Validates: Requirements 18.5, 5.5**

### Property 7: 变动率边界
calcChangeRate(0,0)===''; calcChangeRate(0,x)==='N/A'(x≠0); calcChangeRate(a,b)===(b-a)/a(a≠0)
**Validates: Requirements 18.8**

### Property 8: 产销率公式
∀ sales, production ∈ ℝ>0: calcProductionSalesRate(sales, production) === sales/production*100
**Validates: Requirements 18.11, 9.5**

### Property 9: 检查比例公式
∀ checked, total ∈ ℝ>0: calcCoverageRatio(checked, total) === checked/total*100
**Validates: Requirements 18.10, 12.3**

### Property 10: 明细→汇总聚合正确性
∀ detailRows[]: 按类别聚合的合计 === 各明细行对应列之和
**Validates: Requirements 3.1, 4.2**

### Property 11: 审定表净值=原值-跌价
∀ 13类别: netValueRow[i].endAmount === originalValueRow[i].endAudited - impairmentRow[i].endAudited
**Validates: Requirements 2.5, 2.10, 3.10**

### Property 12: 截止判定幂等
∀ date组合: isCutoffCorrect(入库日期, 记账日期, 期末) 结果确定且幂等
**Validates: Requirements 18.13, 11.4**
