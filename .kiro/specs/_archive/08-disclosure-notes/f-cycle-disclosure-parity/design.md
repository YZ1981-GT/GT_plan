# Design: F 类披露表与附注对齐补齐

## 落点总览

| 需求 | 文件 | 性质 |
|---|---|---|
| R1/R2 | `composables/f3NoteSectionMap.ts` | 变体拆分 + 行序 |
| R3 | `backend/scripts/fix/fix_note_notes_payable_structure.py`（新建） | 幂等脚本 |
| R3 | `backend/tests/services/test_note_notes_payable_structure.py`（新建） | 结构守卫 |
| R4 | `composables/__tests__/f3NoteSubtableContract.spec.ts`（新建） | 契约守卫 |
| R5 | `f1DisclosureSyncPayload.ts` / `f3NoteSectionMap.ts` / `f4NoteSectionMap.ts` | 载荷 |
| R6 | `f4-accounts-payable/F4TabDisclosure{Listed,SOE}.vue` | 自动同步接线 |
| R7 | `backend/scripts/fix/fix_note_prepayment_structure.py` | 幂等脚本扩展 |
| R8 | `composables/__tests__/_disclosureSubtableContract.helper.ts` | helper 增 P6 |
| R9 | 3 个循环的披露 Tab + `_f1_ai_generate.py` + `useF1AiGenerate.ts` | AI 接线 |

## R1/R2：F3 变体拆分

现状单一常量：

```ts
const F3_YFPJ_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '种类', is_label: true },
  { key: 'end_amount', label: '期末余额', format: 'amount' },
  { key: 'prior_amount', label: '上年年末余额', format: 'amount' },
]
```

改为按变体两份并导出（供契约测试引用），第 3 列 key 保持 `prior_amount`
（后端字段名不随变体变，只有 label 变），并显式标 `flat`（源模板单行表头）：

```ts
export const F3_LISTED_YFPJ_COLUMNS  // 种类 / 期末余额 / 上年年末余额
export const F3_SOE_YFPJ_COLUMNS     // 类别 / 期末余额 / 期初余额
export const F3_LISTED_SUBTABLE = { notesPayable: '应付票据' } as const
export const F3_SOE_SUBTABLE = { notesPayable: '应付票据' } as const
export const F3_YFPJ_COLUMNS_BY_VARIANT: Record<F3DisclosureVariant, ColumnDef[]>
```

`buildF3SyncPayload` 按 variant 取列头与子表名。

行序：`orderF3ClassRows` 的 `order()` 改为 `银行承兑 → 0`、`商业承兑 → 1`、`供应链 → 2`，
补零行顺序同步改为 `['银行承兑汇票', '商业承兑汇票']`；模板 seed 行由 R3 脚本改为同序。

## R3：F3 模板幂等脚本

沿用 `fix_note_inventory_structure.py` 的 plan/游标范式（最小化，只 1 张表 × 2 变体）：

- `LISTED_PATCH` / `SOE_PATCH`：`headers` + `columns`（标签列标 `flat`）+ `guidance`
- `rows`：`银行承兑汇票 / 商业承兑汇票 / 合计`
- `validate_section`：表名唯一、`columns` 长度 === `headers`、逐位 label 一致、
  必须表态 flat/group、必须有 guidance、headers 纯文本
- `ALIGNED_BY = "f-cycle-disclosure-parity"`
- guidance 取源：上市 r10「说明：本期末已到期未支付的应付票据总额为XXX元。」+ r11 供应链票据
  红字；国企 r10「注：企业应说明本期已到期未支付的应付票据总金额。」

## R5：`_note_texts` 中文 title

各循环沿用 F2 的 `buildF2NoteTexts` 形状（三元组 `[section, title, text]` + 空文本过滤），
但**不抽公共模块** —— 三处调用点各自 3~7 条，抽取带来的跨循环耦合大于收益，
且平台既有 `buildD1NoteTexts` / `buildD2NoteTexts` / `buildN1NoteTexts` 也是各自实现。
每个循环导出 `buildXNoteTexts(entries)` 供测试直接断言。

title 取源（源 xlsx 说明行 / 底稿卡片标题，禁自拟）：

- F1 listed：账龄披露说明 / 账龄超过1年的重要预付款项说明 / 前五名预付款项说明 /
  前五名汇总披露
- F1 soe：账龄列示说明 / 账龄超过1年的大额预付款项说明 / 前五名预付款项说明
- F3：已到期未支付的应付票据说明
- F4：应付账款披露说明

## R6：F4 自动同步

照抄 F2/F3 范式：`useDisclosureAutoSync({ isReadonly })` + `watch([实际数据..., 文本], ...)`
+ `onBeforeUnmount(cancelPending)`。触发源必须是**披露表实际数据**（性质/账龄行、超1年行、
说明文本），不能只 watch 提示横幅。不加 mounted 一次性防护。

## R7：F1 headers 去 `<br/>`

在 `fix_note_prepayment_structure.py` 的上市 top5 表 patch 中把 `headers` 写成纯文本
（与既有 `columns[].label` 对齐），并在其 `validate_section` 增 headers 纯文本断言。

## R8：helper 增 P6

在 `runDisclosureSubtableContract` 内新增：

```
it(`P6 ${variant} 模板 headers 为纯文本`)
```

遍历该变体章节下**被 subtables 覆盖的表**的模板 `headers`，命中 `/<[^>]+>/` 即失败。
只覆盖已登记的表，避免把别的循环的历史欠账拉进来。

## R9：AI 接线

- F3/F4 后端 section 已就绪 → 只在 Tab 内 `useF3AiGenerate` / `useF4AiGenerate` +
  `AI_TARGETS` 表 + 标题行右对齐的「🤖 AI 辅助」按钮（`margin-left:auto`）。
- F1 需四处登记：`_f1_ai_generate.py` 的 `_SUPPORTED_SECTIONS` / `_SECTION_PROMPTS`
  各加 6 条（listed/soe × aging/over1/top5），`useF1AiGenerate.ts` 的 `F1AiSection`
  联合类型同步，Tab 内 `AI_TARGETS`。prompt ≥20 字 + 写明源模板口径 + 「不得虚构」。
- `aiContext()` 传合计口径与勾稽状态，避免模型凭空编数。
