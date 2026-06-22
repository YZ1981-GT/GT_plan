# Design Document

## Overview

为 D0-6 应收及销售替代程序创建专用组件 `GtConfirmationAlternativeD06`（componentType=`confirmation-alternative-d06`），与 D0-5 姊妹关系：**结构完全同构**（多公司 master-detail + 抽样配置 + 余额汇总 + 4 区块 + 审计说明结论），仅 4 区块列配置、余额口径（应收账款 vs 合同负债）不同。设计上**复用 D0-5 的 CheckBlock.vue + useAlternativeData composable**，替换 BLOCK_COLUMN_CONFIGS_D06。

## Architecture

```
htmlRendererRegistry 新注册：confirmation-alternative-d06 → GtConfirmationAlternativeD06
后端 _WP_CODE_OVERRIDE / render-config 对 D0-6 sheet → componentType

GtConfirmationAlternativeD06.vue（主组件，结构与 D0-5 同构）
├── AlternativeDashboard.vue    复用 D0-5（看板）
├── AlternativeMaster.vue       复用 D0-5（公司列表）
├── AlternativeDetail.vue       复用 D0-5（容器）
│     ├── SamplingConfig.vue    复用（placeholder 改为应收账款口径）
│     ├── BalanceSummary.vue    复用（函证项目=应收账款）
│     ├── CheckBlock.vue × 4   复用 D0-5 通用组件，传入 BLOCK_COLUMN_CONFIGS_D06
│     └── AuditConclusion.vue   复用
│
├── useAlternativeData.ts      复用 D0-5（composable 结构完全相同）
├── alternativeD06Types.ts     类型（复用 AlternativeCompany/CheckRow，区块字段键名可不同）
├── alternativeD06Enums.ts     枚举（复用 sampling_method/yes_no）
└── BLOCK_COLUMN_CONFIGS_D06   新增常量（4 区块列定义）

联动：D0-1"未回函"应收账款公司 / D0-4"未达账项/未回函" → 带入。
保存链路：payload = { companies: [...], _format: 'alternative-d06-v1' }
编制指引：wp_guidance/D0-6.json
```

## Components and Interfaces

### GtConfirmationAlternativeD06.vue（新主组件）
- 结构与 D0-5 完全一致，仅传入 BLOCK_COLUMN_CONFIGS_D06 + componentType 不同
- 旧格式降级 GtGridSheet 只读

### BLOCK_COLUMN_CONFIGS_D06（新常量，核心差异）
```ts
{
  block1: [ // 期末余额形成证据（应收账款借方）
    { key: 'seq', label: '序号', auto: true },
    { key: 'date', label: '日期', type: 'date' },
    { key: 'voucher_no', label: '凭证编号' },
    { key: 'content', label: '业务内容' },
    { key: 'counter_subject', label: '对方科目' },
    { key: 'detail_subject', label: '明细科目' },
    { key: 'debit_amount', label: '借方金额', type: 'amount' },
    { key: 'contract_no', label: '合同号' },
    { key: 'delivery_no', label: '出库单编号' },
    { key: 'delivery_product', label: '品名' },
    { key: 'delivery_qty', label: '数量', type: 'number' },
    { key: 'warehouse_keeper', label: '仓库保管员' },
    { key: 'shipper', label: '发货人' },
    { key: 'transport_no', label: '运输单编号' },
    { key: 'transport_qty', label: '运输数量', type: 'number' },
    { key: 'transport_company', label: '运输公司' },
    { key: 'transport_address', label: '运输地址' },
    { key: 'receipt_amount', label: '验收确认金额', type: 'amount' },
    { key: 'receipt_signer', label: '签收人' },
    { key: 'receipt_stamp_type', label: '盖章类型' },
    { key: 'receipt_stamp_entity', label: '盖章单位' },
    { key: 'invoice_recipient', label: '收票方名称' },
    { key: 'invoice_amount', label: '发票金额', type: 'amount' },
    { key: 'ref_index', label: '索引号' },
    { key: 'is_abnormal', label: '是否异常', type: 'enum', dictKey: 'yes_no' },
  ],
  block2: [ // 期后回款检查（应收账款贷方）
    { key: 'seq', label: '序号', auto: true },
    { key: 'date', label: '日期', type: 'date' },
    { key: 'voucher_no', label: '凭证编号' },
    { key: 'content', label: '业务内容' },
    { key: 'counter_subject', label: '对方科目' },
    { key: 'detail_subject', label: '明细科目' },
    { key: 'credit_amount', label: '贷方金额', type: 'amount' },
    { key: 'bank_summary', label: '银行回单摘要' },
    { key: 'bank_payer', label: '付款方' },
    { key: 'bank_amount', label: '回单金额', type: 'amount' },
    { key: 'bill_endorser', label: '承兑汇票前手名称' },
    { key: 'bill_drawer', label: '出票人' },
    { key: 'ref_index', label: '索引号' },
    { key: 'is_abnormal', label: '是否异常', type: 'enum', dictKey: 'yes_no' },
  ],
  block3: [ // 本期销售出库证据
    { key: 'seq', label: '序号', auto: true },
    { key: 'date', label: '日期', type: 'date' },
    { key: 'doc_no', label: '编号' },
    { key: 'product', label: '品名' },
    { key: 'quantity', label: '数量', type: 'number' },
    { key: 'amount', label: '金额', type: 'amount' },
    { key: 'contract_no', label: '订单号/合同号' },
    { key: 'delivery_keeper', label: '仓库保管员' },
    { key: 'delivery_shipper', label: '发货人' },
    { key: 'transport_no', label: '运输单编号' },
    { key: 'transport_qty', label: '运输数量', type: 'number' },
    { key: 'transport_company', label: '运输公司' },
    { key: 'transport_address', label: '运输地址' },
    { key: 'sign_date', label: '签收日期', type: 'date' },
    { key: 'sign_person', label: '签收人' },
    { key: 'sign_stamp_type', label: '盖章类型' },
    { key: 'sign_stamp_entity', label: '盖章单位' },
    { key: 'ref_index', label: '索引号' },
    { key: 'is_abnormal', label: '是否异常', type: 'enum', dictKey: 'yes_no' },
    { key: 'other_note', label: '其他说明' },
  ],
  block4: [ // 本期收款
    { key: 'seq', label: '序号', auto: true },
    { key: 'date', label: '日期', type: 'date' },
    { key: 'voucher_no', label: '凭证编号' },
    { key: 'content', label: '业务内容' },
    { key: 'counter_subject', label: '对方科目' },
    { key: 'amount', label: '金额', type: 'amount' },
    { key: 'bank_payer', label: '银行回单付款方' },
    { key: 'invoice_date_no', label: '发票日期/编号' },
    { key: 'invoice_counterparty', label: '对手方名称' },
    { key: 'ref_index', label: '索引号' },
    { key: 'is_abnormal', label: '是否异常', type: 'enum', dictKey: 'yes_no' },
  ],
}
```

## Data Models

复用 D0-5 的 AlternativeCompany / CheckRow / Metrics 类型（import from D0-5 或抽到共享 types），仅 `_format` 改为 `alternative-d06-v1`。

### 保存载荷
`{ "_format": "alternative-d06-v1", "companies": [AlternativeCompany...] }`

## Correctness Properties

### Property 1: 区块合计正确
每区块金额列合计 == 该区所有明细行金额之和（精确小数），增删行后同 tick 重算。
**Validates: Requirements 4.2**

### Property 2: 检查比例自动派生
出库检查比例 == block3合计/本期销售金额；收款检查比例 == block4合计/本期销售金额；销售=0→N/A。
**Validates: Requirements 3.2, 3.3**

### Property 3: 完成度与异常派生
completionStatus == 4区块有记录数/4；hasAbnormal == 任一行 is_abnormal=是。
**Validates: Requirements 1.1, 6.1, 6.2**

### Property 4: D0-1/D0-4 带入去重
按 entity_name+confirm_index 去重，映射正确，不重复。
**Validates: Requirements 5.2, 5.3**

### Property 5: 旧格式兼容
无 `_format` → 降级 GtGridSheet 只读不崩。
**Validates: Requirements 11.2**

### Property 6: 只读不可编辑
readonly 时全禁用。
**Validates: Requirements 1.3, 4.5, 10.5**

## Error Handling

- 同 D0-5（D0-1/D0-4 不可用→降级 / 金额非数值→跳过 / 销售0→N/A / 旧格式→降级）

## Testing Strategy

- **useAlternativeData 单测**（复用 D0-5 测试，改列配置验证）：CRUD + 4 区块合计 + 检查比例 + completionStatus/hasAbnormal + buildPayload
- **BLOCK_COLUMN_CONFIGS_D06 列配置 spec**：4 区块列与源模板逐列吻合
- **D0-1/D0-4 带入 spec**：去重 + 映射 + 降级
- **提示落位 spec**：编制说明①②③+概述要求 精确就近
- **回归**：render-config 冒烟
- **Playwright**：新增公司→带入→区块①②③④各增行→合计→比例→标异常→结论→保存→重开→跳 D0-1/D0-4
