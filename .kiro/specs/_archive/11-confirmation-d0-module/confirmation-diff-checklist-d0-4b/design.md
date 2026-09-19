# Design Document

## Overview

为 D0-4b 函证差异检查表（示例）创建专用组件 `GtConfirmationDiffChecklist`（componentType=`confirmation-diff-checklist`），核心设计是**多公司 master-detail + A-I 双向调节公式链全自动 + B/C/F/G 未达明细子表自动合计 + 科目列共享 + 从 D0-4 联动带入 + 经理复核红线**。

D0-4b 与 D0-4 的关系：D0-4 是"差异汇总"（按笔列出差异、分类、分析原因、决定是否调整），D0-4b 是"逐公司深挖调节"（对 D0-4 中差异≠0 的具体公司做双向余额调节 A-I）。一个向下穿透一个。

形态上 D0-4b 是 **master（公司列表）+ detail（结构化 A-I 调节表单 + 明细子表）**，和 D0-1/D0-2 的 master-detail 同构但 detail 内容不同——不是 38 列宽表拆分，而是固定公式链结构 + 嵌套子表（B/C/F/G 各区明细）。

## Architecture

```
htmlRendererRegistry 新注册：confirmation-diff-checklist → GtConfirmationDiffChecklist
后端 _WP_CODE_OVERRIDE / render-config 对 D0-4b sheet 标 componentType=confirmation-diff-checklist

GtConfirmationDiffChecklist.vue（主组件）
├── props: wpId / sheetName / schema / htmlData / readonly
├── emit: save / open-formula / restore
│
├── ChecklistDashboard.vue     看板（总公司数/已平/有差异/超重要性/完成率 + 折叠）
├── ChecklistMaster.vue        公司列表（科目|被询证单位|A|E|I|差异状态|是否调整 + 工具栏）
├── ChecklistDetail.vue        A-I 结构化调节表单
│     ├── ReconcileSection A/D/E/H/I  顶层金额+公式（D/H/I 只读自动）
│     ├── DetailSubTable B    本公司已增未确认明细（日期/日期/凭证号/金额/索引/是否调整）
│     ├── DetailSubTable C    本公司已减未确认明细
│     ├── DetailSubTable F    对方已增本方未确认明细
│     └── DetailSubTable G    对方已付本方未收到明细
├── ChecklistAuditNote.vue     审计说明（每公司+全局）
│
├── useDiffChecklistData.ts   数据核心（companies/dirty/CRUD/A-I公式/子表合计/buildPayload/metrics）
├── useCellSelection.ts       复用
├── CellContextMenu.vue       复用
├── useDictStore              复用
├── useExcelIO                复用
├── diffChecklistTypes.ts     类型定义
└── diffChecklistEnums.ts     枚举 dictKey

联动：上游 D0-4（差异汇总表）经带入传递公司信息+A/E金额；下游 是否调整→AJE 引用。
  与 D0-1 通过 confirm_index 可跳转。

保存链路（复用既有）：emit('save', payload) → POST /save
  payload = { companies: [ChecklistCompany...], global_note, materiality_config, _format: 'diff-checklist-v1' }
```

## Components and Interfaces

### GtConfirmationDiffChecklist.vue（新，主组件）
- 旧格式降级 GtGridSheet 只读；布局：看板 → 公司 master → 展开 detail

### ChecklistMaster.vue（新）
- Props: `{ companies, readonly, expandedId }`；Emit: `expand / add / delete / import-d04 / context-menu`
- 关键列：科目 | 被询证单位 | A(回函) | E(账面) | I(最终差异) | 差异状态(绿/橙/红) | 是否调整
- 工具栏（新增/删除/从 D0-4 带入/保存/导入/导出）

### ChecklistDetail.vue（新）
- Props: `{ company, readonly }`；Emit: `field-change / subtable-change`
- 结构化表单：A → B(子表) → C(子表) → D(只读=A+B-C) → E → F(子表) → G(子表) → H(只读=E+F-G) → I(只读=H-D)
- 每区块标题清晰（对应模板 A-I 含义描述）

### DetailSubTable.vue（新，复用性高）
- Props: `{ rows, section, readonly }`；Emit: `row-change / add / delete`
- 列：序号(auto) | 日期1 | 日期2 | 凭证号 | 金额 | 索引号 | 是否调整
- 合计行 == rows.∑金额
- 支持增删行 + 右键 + useCellSelection（选区/复制/粘贴/求和，从 Excel 批量贴入未达明细）

### ChecklistDashboard.vue（新）
- Props: `{ metrics, collapsed }`
- 总公司数/已平/有差异/超重要性/完成率

### useDiffChecklistData.ts（新 composable）
```ts
interface SubTableRow { id: string; date1: string; date2: string; voucher: string; amount: number|null; ref_index: string; need_adjust: string }
interface ChecklistCompany {
  id: string; confirm_index: string; subject: string; entity_name: string
  a_reply: number | null        // A: 回函金额
  b_rows: SubTableRow[]          // B 明细
  c_rows: SubTableRow[]          // C 明细
  e_book: number | null          // E: 账面余额
  f_rows: SubTableRow[]          // F 明细
  g_rows: SubTableRow[]          // G 明细
  audit_note: string             // 审计说明
  _source?: 'd0-4' | 'manual'
}
// 派生（只读自动）
// b_total = sum(b_rows.amount)
// c_total = sum(c_rows.amount)
// d_adjusted_reply = a_reply + b_total - c_total    // D = A+B-C
// f_total = sum(f_rows.amount)
// g_total = sum(g_rows.amount)
// h_adjusted_book = e_book + f_total - g_total      // H = E+F-G
// i_difference = h_adjusted_book - d_adjusted_reply  // I = H-D

useDiffChecklistData(htmlData, readonly) => {
  companies, addCompany, deleteCompany, updateCompany, importCompanies
  computeFormula(company)    // 返回 { b_total, c_total, d, f_total, g_total, h, i }
  companyStatus(company)     // 'balanced'|'diff'|'over_materiality'
  metrics                    // computed: 总公司/已平/有差异/超重要性/完成率
  dirty, buildPayload
}
```

## Data Models

### ChecklistCompany / SubTableRow（见上）

### Metrics
```ts
{ total: number; balanced: number; with_diff: number; over_materiality: number; completion_rate: number }
```

### 保存载荷（`_format: 'diff-checklist-v1'`）
```ts
{ "_format": "diff-checklist-v1", "companies": [ChecklistCompany...], "global_note": "", "materiality_config": {...} }
```

## Correctness Properties

### Property 1: A-I 公式链正确
D == A + B_total − C_total；H == E + F_total − G_total；I == H − D；B_total == ∑b_rows.amount（精确小数）；同理 C/F/G。所有派生值只读不可手填。
**Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10**

### Property 2: 子表合计一致
每区块(B/C/F/G)合计行 SHALL == 该区所有明细行金额之和；增删行后同 tick 重算。
**Validates: Requirements 3.2**

### Property 3: 差异状态由 I 派生
I=0→balanced(绿)；0<|I|<materiality→diff(橙)；|I|≥materiality→over_materiality(红)；无重要性配置时不区分橙红（全为 diff）。
**Validates: Requirements 2.9, 7.1, 7.2**

### Property 4: D0-4 带入去重
从 D0-4 带入按 entity_name+subject 组合去重；映射 A/E 正确；已存在组合不重复带入。
**Validates: Requirements 5.2, 5.3**

### Property 5: 旧格式兼容
htmlData 无 `_format` 时降级 GtGridSheet 只读，不崩。
**Validates: Requirements 11.2**

### Property 6: 只读不可编辑
readonly=true 时所有控件不可编辑，子表增删禁用。
**Validates: Requirements 1.3, 3.4, 10.5**

## Error Handling

- D0-4 不可用 → 带入降级手工，不阻塞
- 金额非数值 → 校验提示，公式跳过 null 不崩
- 重要性未配置 → 不区分橙红，全为"有差异"
- 旧格式 → 降级只读
- 保存失败 → dirty 保留

## Testing Strategy

- **useDiffChecklistData 单测**：CRUD companies + 公式链 A-I 全自动 + 子表合计 + metrics + buildPayload（P1/P2/P3）
- **D0-4 带入 spec**：去重 + 映射 + 降级（P4）
- **差异状态 spec**：I=0绿 / ≠0橙 / ≥重要性红 / 无配置不区分（P3）
- **子表增删 spec**：增删行 → 区块合计重算 → 公式链联动（P1/P2）
- **质量红线 spec**：未分析差异橙 / 超重要性红 / 应调未调提示
- **回归**：render-config 冒烟
- **Playwright**：新增公司→从 D0-4 带入→填 B/C 明细→D 自动算→填 F/G 明细→H/I 自动→差异状态红→标调整→保存→重开持久化→跳 D0-4/D0-1
