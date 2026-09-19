# Design Document

## Overview

为 D0-8 函证程序舞弊风险评价表创建专用组件 `GtConfirmationFraudRisk`（componentType=`confirmation-fraud-risk`），核心设计是**预置检查清单（~19条舞弊风险迹象）+ 逐条评估(是否存在/索引/应对) + 举例tooltip精确就近 + 编制说明4条落位 + 条件高亮(是→应对措施提示) + 汇总风险因素→B50联动**。

形态是 **d-form-qa 类检查表**（非宽表非备忘录）：固定条目清单 + 每条 3 个评估字段 + 末尾汇总 + 审计说明结论。与 D0-1~D0-7 的网格/master-detail 不同，D0-8 更接近"程序表/检查表"形态。

## Architecture

```
htmlRendererRegistry 新注册：confirmation-fraud-risk → GtConfirmationFraudRisk
后端 _WP_CODE_OVERRIDE / render-config 对 D0-8 sheet → componentType
（跨循环复用：D0-8/E0-8/F0-8/K0-8/L0-7 等同模板同 componentType）

GtConfirmationFraudRisk.vue（主组件）
├── props: wpId / sheetName / schema / htmlData / readonly
├── emit: save / open-formula / restore
│
├── FraudRiskDashboard.vue      看板（总条目/存在迹象数/已填应对/未填应对 + 折叠）
├── FraudRiskChecklist.vue      预置检查清单（~19条 + 自由扩展行 + 评估三列 + tooltip 举例）
├── FraudRiskSummary.vue        汇总识别的风险因素（报表层次/认定层次/初步应对 + B50 跳转）
├── FraudRiskConclusion.vue     审计说明 + 审计结论
│
├── useFraudRiskData.ts         数据核心（items/dirty/CRUD/条件高亮/metrics/buildPayload）
├── PRESET_FRAUD_ITEMS          预置条目常量（19条描述文本 + 举例tooltip映射）
├── ITEM_TOOLTIPS_D08           举例/场景描述常量（第14/18/19条等）
├── useCellSelection.ts         复用（清单/子表选区/复制/粘贴/求和）
├── CellContextMenu.vue         复用
├── useDictStore                复用
├── fraudRiskTypes.ts           类型定义
└── fraudRiskEnums.ts           枚举 dictKey

保存链路：payload = { items, summary, audit_note, conclusion, _format: 'fraud-risk-d08-v1' }
编制指引：wp_guidance/D0-8.json（编制说明4条完整 + 举例场景 + 审计准则引用）
```

## Components and Interfaces

### GtConfirmationFraudRisk.vue（新主组件）
- 旧格式降级 GtGridSheet 只读
- 布局：顶部说明(编制说明①精简) → 看板 → 检查清单 → 汇总 → 审计说明/结论

### FraudRiskChecklist.vue（新，核心）
- Props: `{ items, readonly }`；Emit: `item-change / add / delete / context-menu`
- 渲染：每条为一行（可用 el-table 或 el-form 卡片），列：序号 | 舞弊风险迹象(长文本) | 是否存在(枚举) | 索引号或信息来源(文本+跳转) | 应对措施(文本)
- 条件高亮：is_exist=是 → 行高亮 + 应对为空→橙色警示
- 举例 tooltip：部分条目旁问号图标 → hover 展示 ITEM_TOOLTIPS_D08 内容
- 末尾汇总提示行 + B50 跳转链接
- 支持增删自定义行；工具栏（新增/删除/保存/导出）

### FraudRiskDashboard.vue（新）
- Props: `{ metrics, collapsed }`
- 总条目/存在迹象数/已填应对/未填应对

### FraudRiskSummary.vue（新）
- Props: `{ summary, readonly }`；Emit: `change`
- 财务报表层次风险(文本) + 认定层次风险(文本) + 初步应对措施计划(文本)
- 提示：将已发现迹象汇总后区分层次记录

### FraudRiskConclusion.vue（新）
- Props: `{ auditNote, conclusion, hasPending, readonly }`；Emit: `change`
- 审计说明 + 结论 + 未决提示

### useFraudRiskData.ts（新 composable）
```ts
interface FraudRiskItem {
  id: string; seq: number
  description: string       // 舞弊风险迹象描述（预置文本，可编辑）
  is_exist: string          // 是否存在（是/否/不适用）
  source_ref: string        // 索引号或信息来源
  countermeasure: string    // 应对措施
  _preset: boolean          // 是否预置条目（vs 用户自定义）
}
interface FraudRiskSummary { report_level: string; assertion_level: string; initial_plan: string }

useFraudRiskData(htmlData, readonly) => {
  items, addItem, deleteItem, updateItem
  summary, updateSummary
  metrics   // computed: { total, exist_count, with_measure, without_measure }
  dirty, buildPayload
}
```

### PRESET_FRAUD_ITEMS（常量，预置 19 条）
```ts
[
  { seq: 1, description: '管理层不允许寄发询证函；' },
  { seq: 2, description: '管理层过度热情配合函证程序；' },
  { seq: 3, description: '管理层试图干预、拦截、篡改询证函或回函，如坚持以特定的方式发送询证函；' },
  { seq: 4, description: '管理层提供的函证相关信息含糊、矛盾、不完整或有缺失；' },
  // 5 missing in template, jump to 6
  { seq: 6, description: '注册会计师跟进访问被询证者，发现回函信息与被询证者记录不一致；' },
  { seq: 7, description: '从私人电子信箱发送的回函；' },
  { seq: 8, description: '收到同一日期发回的、相同笔迹的多份回函；' },
  { seq: 9, description: '收到的回函与发出的询证函不是同一份、不是原件；' },
  { seq: 10, description: '不同被询证者回函信封上的联系方式（地址、电话等）相同或相近；位于不同地址的多家被询证者的回函邮戳显示的发函地址相同；' },
  { seq: 11, description: '印章模糊不清难以核对，或印章存在明显瑕疵，或与被询证者不一致；' },
  { seq: 14, description: '不正常的回函率；', tooltip: '例如：银行函证未回函；与以前年度相比，回函率异常偏高或回函率重大变动；向被审计单位债权人发送的询证函回函率很低；' },
  { seq: 16, description: '管理层不愿意提高函证所涉及信息的披露质量，使财务报表更为完整透明，但又不能提供合理解释；' },
  { seq: 17, description: '回函印章与以前期间收到的回函印章不一致' },
  { seq: 18, description: '回函中包含免责或其他限制性条款' },
  { seq: 19, description: '第三方对函证信息有误的询证函作出与函证信息相符的回函，或对前后两次函证信息有差异的询证函均作出信息相符的回函。' },
  // ... 可扩展
]
```

### ITEM_TOOLTIPS_D08（举例/场景描述，就近映射）
```ts
{
  14: '例如：银行函证未回函；与以前年度相比，回函率异常偏高或回函率重大变动；向被审计单位债权人发送的询证函回函率很低；',
  18: '提示：部分空白、对交易级别请求仅提供汇总回复等情况也需关注',
  19: '提示：说明被询证方可能未认真核对就直接确认，存在串通舞弊可能',
  // 截图红框中的举例内容按条目落位
}
```

## Data Models

### FraudRiskItem / FraudRiskSummary（见上）

### Metrics
```ts
{ total: number; exist_count: number; with_measure: number; without_measure: number }
```

### 保存载荷
`{ "_format": "fraud-risk-d08-v1", "items": [FraudRiskItem...], "summary": FraudRiskSummary, "audit_note": "", "conclusion": "" }`

## Correctness Properties

### Property 1: 预置条目完整且可编辑
初始加载 SHALL 含全部预置条目（~19条）；用户可修改描述文本；可新增自定义条目（_preset=false）。
**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

### Property 2: 条件高亮与应对提示
is_exist=是 的行 SHALL 高亮；is_exist=是 AND countermeasure 为空 SHALL 橙色警示。
**Validates: Requirements 4.1, 4.2**

### Property 3: 指标派生
exist_count == is_exist=是的条数；with_measure == 其中 countermeasure 非空数；without_measure == 差值。
**Validates: Requirements 4.4**

### Property 4: 旧格式兼容
无 `_format` → 降级 GtGridSheet 只读不崩。
**Validates: Requirements 9.2**

### Property 5: 只读不可编辑
readonly 时全禁用。
**Validates: Requirements 1.5, 8.4**

## Error Handling

- 旧格式 → 降级只读
- 保存失败 → dirty 保留
- 预置条目缺失（htmlData 已有自定义结构）→ 合并预置+已有，不覆盖用户数据

## Testing Strategy

- **useFraudRiskData 单测**：预置加载 + CRUD + 条件高亮逻辑 + metrics + buildPayload（P1/P2/P3）
- **预置条目 spec**：19条完整 + 可编辑 + 可新增 + 保存后重开保留
- **tooltip spec**：第14/18/19条举例正确落位
- **编制说明落位 spec**：4条分别到组件顶部/应对措施placeholder/索引列tooltip/是=是条件提示
- **回归**：render-config 冒烟
- **Playwright**：打开预置清单→第3条标"是"+填应对→新增自定义条目→汇总填风险→审计结论→保存→重开持久化→跳 B50
