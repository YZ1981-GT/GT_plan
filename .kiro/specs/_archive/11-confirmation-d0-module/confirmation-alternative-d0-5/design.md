# Design Document

## Overview

为 D0-5 合同负债及销售替代程序创建专用组件 `GtConfirmationAlternativeD05`（componentType=`confirmation-alternative-d05`），核心设计是**多公司 master-detail + 4 区块检查宽表（各区块列结构不同，含明细行+合计自动）+ 抽样配置 + 余额汇总(检查比例自动) + D0-1/D0-4 联动带入 + 经理复核红线 + 底部提示就近落位**。

与 D0-1/D0-2 形态高度同构（超宽表 → master-detail），但 detail 内部不是一个平铺宽表，而是**4 个结构不同的检查区块**（期后结转/期末余额证据/本期收款/本期出库证据），各区块列结构各异（10-30列），类似 D0-1 的"按生命周期分区"。

## Architecture

```
htmlRendererRegistry 新注册：confirmation-alternative-d05 → GtConfirmationAlternativeD05
后端 _WP_CODE_OVERRIDE / render-config 对 D0-5 sheet → componentType

GtConfirmationAlternativeD05.vue（主组件）
├── props: wpId / sheetName / schema / htmlData / readonly
├── emit: save / open-formula / restore
│
├── AlternativeDashboard.vue    看板（总公司/完成数/有异常/检查比例分布 + 折叠）
├── AlternativeMaster.vue       公司列表（被询证单位/索引/期末余额/完成度/异常/结论 + 工具栏）
├── AlternativeDetail.vue       单公司 detail 容器
│     ├── SamplingConfig.vue    抽样配置区（测试范围/特定样本/抽样总体/样本量/方法/过程）
│     ├── BalanceSummary.vue    余额汇总（年初/借贷方/期末/销售/收款检查比例auto/出库检查比例auto）
│     ├── CheckBlock.vue × 4   4 区块检查宽表（各区块列配置不同，含合计自动 + useCellSelection + 右键）
│     └── AuditConclusion.vue   审计说明 + 结论
│
├── useAlternativeData.ts      数据核心（companies/dirty/CRUD/4区块明细/合计/检查比例/metrics/buildPayload）
├── useCellSelection.ts        复用
├── CellContextMenu.vue        复用
├── useDictStore               复用
├── useExcelIO                 复用
├── alternativeTypes.ts        类型定义
└── alternativeEnums.ts        枚举 dictKey

联动：D0-1"未回函"公司/D0-4"未达账项/未回函"行 → 带入 D0-5 作待检公司。

保存链路（复用既有）：emit('save', payload) → POST /save
  payload = { companies: [AlternativeCompany...], _format: 'alternative-d05-v1' }
```

## Components and Interfaces

### GtConfirmationAlternativeD05.vue（新，主组件）
- 旧格式降级 GtGridSheet 只读；布局：看板 → master → detail

### AlternativeMaster.vue（新）
- Props: `{ companies, readonly, expandedId }`；Emit: `expand / add / delete / import / context-menu`
- 关键列 + 工具栏（新增/删除/从 D0-1 带入/保存/导入/导出）

### AlternativeDetail.vue（新）
- Props: `{ company, readonly }`；Emit: `change`
- 容器组织：SamplingConfig → BalanceSummary → 4×CheckBlock → AuditConclusion

### SamplingConfig.vue（新）
- Props: `{ config, readonly }`；Emit: `change`
- 字段：测试范围/特定样本/抽样总体/样本量/抽样方法(枚举)/抽样过程 + placeholder 示例

### BalanceSummary.vue（新）
- Props: `{ balance, block3Total, block4Total, salesAmount, readonly }`；Emit: `change`
- 年初/借方/贷方/期末/本期销售/收款检查比例(auto=block3合计/sales)/出库检查比例(auto=block4合计/sales)

### CheckBlock.vue（新，复用性高，× 4 实例）
- Props: `{ blockType, rows, readonly, columnConfig }`；Emit: `row-change / add / delete / context-menu`
- blockType 驱动列配置（4 区块列各异）；el-table + 合计行 + 分组表头着色 + 冻结序号 + 斑马纹 + 空值淡化 + useCellSelection + 右键
- 列配置由 `BLOCK_COLUMN_CONFIGS` 常量定义

### AuditConclusion.vue（新）
- Props: `{ auditNote, conclusion, hasAbnormal, readonly }`；Emit: `change`
- 审计说明文本 + 结论枚举+文本 + 异常未决提示

### useAlternativeData.ts（新 composable）
```ts
interface CheckRow { id: string; [field: string]: any; is_abnormal: string; ref_index: string }
interface AlternativeCompany {
  id: string; confirm_index: string; entity_name: string
  sampling: { scope: string; specific: string; population: string; sample_size: string; method: string; process: string }
  balance: { opening: number|null; debit: number|null; credit: number|null; closing: number|null; sales: number|null }
  block1_rows: CheckRow[]   // 期后结转
  block2_rows: CheckRow[]   // 期末余额证据
  block3_rows: CheckRow[]   // 本期收款
  block4_rows: CheckRow[]   // 本期出库证据
  audit_note: string; conclusion: string
  _source?: 'd0-1' | 'd0-4' | 'manual'
}

useAlternativeData(htmlData, readonly) => {
  companies, addCompany, deleteCompany, updateCompany, importCompanies
  blockTotal(company, blockKey)    // 各区块金额列合计
  checkRatio(company)              // { receiptRatio: block3Total/sales, deliveryRatio: block4Total/sales }
  completionStatus(company)        // 4区块中有记录的比例 + 是否有异常行
  metrics                          // 看板指标
  dirty, buildPayload
}
```

### BLOCK_COLUMN_CONFIGS（常量）
```ts
{
  block1: [ // 期后结转
    { key: 'seq', label: '序号', auto: true },
    { key: 'date', label: '日期', type: 'date' },
    { key: 'voucher_no', label: '凭证编号' },
    { key: 'content', label: '业务内容' },
    { key: 'counter_subject', label: '对方科目' },
    { key: 'detail_subject', label: '明细科目' },
    { key: 'debit_amount', label: '借方金额', type: 'amount' },
    { key: 'acceptance_date', label: '验收单日期/编号' },
    { key: 'quantity', label: '数量', type: 'number' },
    { key: 'signature', label: '签字签章' },
    { key: 'invoice_recipient', label: '收票方名称' },
    { key: 'invoice_amount', label: '发票金额', type: 'amount' },
    { key: 'ref_index', label: '索引号' },
    { key: 'is_abnormal', label: '是否异常', type: 'enum', dictKey: 'yes_no' },
  ],
  block2: [ /* 期末余额证据：贷方金额+银行收款(日期/付款方/金额)+合同(客户/金额/比例)+索引+异常 */ ],
  block3: [ /* 本期收款：金额+银行回单(日期/付款方)+销售发票(日期编号/对手方/金额)+索引+异常 */ ],
  block4: [ /* 本期出库：金额+销售合同+出库单+运输单+签收单+索引+异常+其他说明 */ ],
}
```

## Data Models

### AlternativeCompany / CheckRow（见上）/ BLOCK_COLUMN_CONFIGS（见上）

### Metrics
```ts
{ total: number; completed: number; abnormal_count: number; avg_receipt_ratio: number; avg_delivery_ratio: number }
```

### 保存载荷
`{ "_format": "alternative-d05-v1", "companies": [AlternativeCompany...] }`

## Correctness Properties

### Property 1: 区块合计正确
每区块金额列合计 SHALL == 该区所有明细行金额之和（精确小数）；增删行后同 tick 重算。
**Validates: Requirements 4.2**

### Property 2: 检查比例自动派生
收款检查比例 == block3合计/本期销售金额；出库检查比例 == block4合计/本期销售金额；销售金额为空或 0 时显 N/A 不报错。
**Validates: Requirements 3.2, 3.3**

### Property 3: 完成度与异常派生
completionStatus == 4区块中有≥1条记录的区块数/4；hasAbnormal == 任一明细行 is_abnormal=是。
**Validates: Requirements 1.1, 6.1, 6.2**

### Property 4: D0-1/D0-4 带入去重
带入按 entity_name+confirm_index 去重，映射字段正确，不重复带入。
**Validates: Requirements 5.2, 5.3**

### Property 5: 旧格式兼容
htmlData 无 `_format` 时降级 GtGridSheet 只读，不崩。
**Validates: Requirements 11.2**

### Property 6: 只读不可编辑
readonly=true 时所有控件不可编辑，子表增删禁用。
**Validates: Requirements 1.3, 4.5, 10.5**

## Error Handling

- D0-1/D0-4 不可用 → 降级手工
- 金额非数值 → 校验提示，合计/比例跳过
- 销售金额 0 → 检查比例显 N/A
- 旧格式 → 降级只读
- 保存失败 → dirty 保留

## Testing Strategy

- **useAlternativeData 单测**：CRUD + 4 区块合计 + 检查比例自动 + completionStatus/hasAbnormal + metrics + buildPayload（P1/P2/P3）
- **D0-1/D0-4 带入 spec**：去重 + 映射 + 降级（P4）
- **CheckBlock spec**：4 区块各列配置正确 + 合计 + 增删 + 右键 + 只读守卫
- **提示落位 spec**：3 条提示分别就近到区块①/②④/顶部+guidance
- **回归**：render-config 冒烟
- **Playwright**：新增公司→从 D0-1 带入→填抽样配置→填余额→区块①②③④各增行→合计自动→检查比例自动→标异常→审计结论→保存→重开持久化→跳 D0-1/D0-4
