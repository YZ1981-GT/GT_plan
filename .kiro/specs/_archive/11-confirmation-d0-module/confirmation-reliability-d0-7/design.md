# Design Document

## Overview

为 D0-7 邮件/传真回函可靠性验证创建专用组件 `GtConfirmationReliability`（componentType=`confirmation-reliability`），核心设计是**中等宽度可编辑网格（~14列）+ 条件列（是否寄回原件=否时展开验证6列）+ 注1/注2/注3 精确就近 tooltip + D0-1 联动带入电子回函行 + 质量红线**。

与 D0-4（差异调节汇总）形态类似——单层可编辑网格 + 自动派生（此处派生的是已验证率/不可靠计数），无需 master-detail。

## Architecture

```
htmlRendererRegistry 新注册：confirmation-reliability → GtConfirmationReliability
后端 _WP_CODE_OVERRIDE / render-config 对 D0-7 sheet → componentType

GtConfirmationReliability.vue（主组件）
├── props: wpId / sheetName / schema / htmlData / readonly
├── emit: save / open-formula / restore
│
├── ReliabilityDashboard.vue   看板（总行/已验证率/不可靠数 + 折叠）
├── ReliabilityGrid.vue        明细网格（~14列 + 条件列 + 合计无金额 + useCellSelection + 右键）
├── ReliabilityConclusion.vue  审计说明 + 审计结论
│
├── useReliabilityData.ts     数据核心（rows/dirty/CRUD/条件列/metrics/buildPayload）
├── RELIABILITY_COLUMN_CONFIG 列配置常量（含条件列标记+tooltip注1/注2/注3）
├── FIELD_TOOLTIPS_D07        注1/注2/注3 完整文本常量（就近 tooltip 内容）
├── useCellSelection.ts       复用
├── CellContextMenu.vue       复用
├── useDictStore              复用
├── useExcelIO                复用
├── reliabilityTypes.ts       类型定义
└── reliabilityEnums.ts       枚举 dictKey

联动：D0-1"回函方式=传真/电子邮件"行 → 带入 D0-7。
保存链路：payload = { rows, audit_note, conclusion, _format: 'reliability-d07-v1' }
编制指引：wp_guidance/D0-7.json（注1/注2/注3 原文 + 顶部提示全文 + 技术提示4号链接）
```

## Components and Interfaces

### GtConfirmationReliability.vue（新主组件）
- 旧格式降级 GtGridSheet 只读
- 布局：顶部一行精简说明（电子回函风险概述）→ 看板 → 网格 → 审计说明/结论

### ReliabilityGrid.vue（新）
- Props: `{ rows, readonly }`；Emit: `field-change / add / delete / import / context-menu`
- ~14 列 el-table，**分组表头**（前6列"基本信息" / 中间7列"期末未收回原件函证可靠性验证" / 最后1列"结论"，按区着色），条件列（is_original_returned=否时展开验证7列，=是时灰掉）
- useCellSelection + 右键（复制/插入/删除/复制索引/跳转 D0-1）
- 列标题含 tooltip 图标（注1→身份确认 / 注2→邮箱验证 / 注3→信息可靠性）
- 工具栏（新增/删除/从 D0-1 带入/保存/导入/导出）

### ReliabilityDashboard.vue（新）
- Props: `{ metrics, collapsed }`
- 总行数/已验证率(结论非空比例)/不可靠笔数

### ReliabilityConclusion.vue（新）
- Props: `{ auditNote, conclusion, readonly }`；Emit: `change`
- 审计说明（文本 + placeholder 提示：记录审计人员/日期/获取电话方式/联络人/部门/沟通过程结果）
- 审计结论（枚举 reply_reliability_conclusion + 文本）

### useReliabilityData.ts（新 composable）
```ts
interface ReliabilityRow {
  id: string
  confirm_index: string         // 函证索引号
  entity_name: string           // 被询证单位名称
  reply_method: string          // 回函方式（传真/电子邮件）
  direct_received: string       // 是否由审计项目组直接接收
  is_original_returned: string  // 是否寄回原件
  // ↓ 条件列：is_original_returned ≠ 是 时需填
  identity_confirm: string      // 被函证者身份确认（注1）
  fax_info_verify: string       // 发函及回函传真信息及验证
  send_email: string            // 发函邮箱
  reply_email: string           // 回函邮箱
  email_reliability: string     // 邮箱可靠性验证（注2）
  phone_confirmed: string       // 是否致电被函证者确认
  info_reliability: string      // 对函证信息可靠性的考虑（注3）
  // ↓ 结论
  reliability_conclusion: string // 回函可靠性结论
  _source?: 'd0-1' | 'manual'
}

useReliabilityData(htmlData, readonly) => {
  rows, addRow, deleteRow, updateField, importRows
  metrics   // computed: { total, verified_rate, unreliable_count }
  dirty, buildPayload
}
```

### FIELD_TOOLTIPS_D07（常量，注1/注2/注3 精确映射）
```ts
{
  identity_confirm: `注1：回函者的身份确认\n1. 需确定回函者是否属于被询证者或由被询证者授权的人员，回函者对所函证信息是否知情，是否具有客观性。\n2. 身份确认方式：\n(1) 索取回函者名片；\n(2) 通过被询证者的官网或其他公开网站核实回函者的姓名和身份信息；\n(3) 将回函者的信息与被审计单位拥有的相关信息进行核对（如客户或供应商清单、相关销售合同等）；\n(4) 通过被审计单位收到或开具的增值税发票中的联系人信息进行核对。`,
  email_reliability: `注2：回函邮箱的可靠性验证\n1. 从私人电子信箱发送的回函不可靠。\n2. 邮箱验证方式：\n(1) 验证回函邮箱确为回函者所在单位的工作邮箱（如后缀），验证公司邮箱发送函证→致电确认回函真实性；\n(2) 通过电话联系被询证者，确定被询证者是否发送了回函，是否接收了回函；\n(3) 电子签名：按照《电子签名法》要求，核查相关平台是否经国务院信息产业主管部门标准，并获取分省出具的审计证据——参见函证技术提示4号。\n必要时可能还需要对相关平台的安全可靠性进行专门评价。`,
  info_reliability: `注3：对函证信息可靠性的考虑\n1. 为降低被询证者对所列示的信息不加验证是否正确便予以回函确认的风险，注册会计师可以选择在函证中由不列明账户余额或其他信息，而要求被询证者填列有关信息或进一步提供信息。\n2. 函证应增加不可编辑的水印、不易复制的特定标识；收到回函后检查是否为发出的附件，是否存在篡改迹象、印章（如有）是否与其他文书一致。`,
}
```

## Data Models

### ReliabilityRow / Metrics（见上）

### 保存载荷
`{ "_format": "reliability-d07-v1", "rows": [ReliabilityRow...], "audit_note": "", "conclusion": "" }`

## Correctness Properties

### Property 1: 条件列正确显隐
WHEN is_original_returned=是 THEN 验证7列灰掉/折叠（但值保留不清除）；≠是 THEN 正常展示。
**Validates: Requirements 2.1, 2.2, 2.3**

### Property 2: 已验证率派生
verified_rate == 结论非空行数/总行数；unreliable_count == 结论=不可靠的行数。
**Validates: Requirements 6.4**

### Property 3: D0-1 带入去重
从 D0-1 带入仅取回函方式=传真/电子邮件行，按 confirm_index 去重。
**Validates: Requirements 5.2, 5.3**

### Property 4: 旧格式兼容
无 `_format` → 降级 GtGridSheet 只读不崩。
**Validates: Requirements 9.2**

### Property 5: 只读不可编辑
readonly 时全禁用。
**Validates: Requirements 1.3, 8.5**

## Error Handling

- D0-1 不可用 → 降级手工
- 旧格式 → 降级只读
- 保存失败 → dirty 保留

## Testing Strategy

- **useReliabilityData 单测**：CRUD + 条件列保留 + metrics(verified_rate/unreliable_count) + buildPayload（P1/P2）
- **D0-1 带入 spec**：过滤回函方式 + 去重 + 降级（P3）
- **条件列 spec**：is_original_returned 切换→6列显隐/灰掉+值保留（P1）
- **tooltip spec**：注1/注2/注3 精确落到对应列标题图标
- **质量红线 spec**：未验证橙/结论空橙/不可靠红
- **回归**：render-config 冒烟
- **Playwright**：从 D0-1 带入电子回函→条件列展开→填身份确认+邮箱验证+致电→结论→保存→重开→跳 D0-1
