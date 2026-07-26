# Design Document

## Overview

把 J1（应付职工薪酬 2211）接入平台附注联动三链，实现方式与 D1/E1/F3/N1 完全同构：新增一个前端映射/载荷模块 `j1NoteSectionMap.ts`，在两张披露表挂「同步到附注」「跳转回附注」入口，并在三个既有注册点（正向跳转 / 反向跳转 / 定向刷新）+ 一个守卫（覆盖率）登记 J1。后端零改动（复用既有 `sync-from-workpaper` 端点与 `note_sub_table_projector` 投影）。

关键决策：

- **决策 1（子表所有权）**：`五、40`/`八、40` 由 J1 独占（无其他科目共推该章节；J2 长期应付职工薪酬走 `五、49`/`八、54`）。因此三张子表 owner 全部为 J1，不需要 N1/N3 那种跨底稿所有权切分。
- **决策 2（列头来源）**：`columns` 的 label 逐字取自**附注模板 headers**（`项目/期初余额/本期增加/本期减少/期末余额`），而不是底稿组件列头。listed 组件用「上年年末数」是底稿侧呈现习惯，同步到附注必须用模板列头，否则附注表头与模板不一致。
- **决策 3（soe 重名表消歧）**：soe `八、40` 第二/三张表模板 name 同为「短期薪酬列示」。`sub_table_data` 是按键浅合并，同名键会互相覆盖丢表。故第三张表 Sub_Table_Key 取模板 `text_sections` 的章节标题「设定提存计划列示」，并在映射文件登记为**允许偏离模板 name 的情形**（同 D2 已备查的 4 类偏差范式）。不改模板文件。
- **决策 4（章节精确匹配）**：`五、40` 属"两位数字章节号"，判定必须 `===`；用 `startsWith` 会与 `五、4` 混淆方向（`五、4` 是应收票据），也会被 `五、40x` 之类未来章节误命中。
- **决策 5（sheet 名以 DB 为准）**：J1 render 策略声明 `附注披露信息（国有企业）`，但 D1/N1 实测为 `（国企）`，各循环命名不统一。Wave 0 必须用 `workpaper_sheet_classification` 核实后写死，禁止凭习惯推断。

## Architecture

```
J1TabDisclosureListed / J1TabDisclosureSoe
  │  「同步到附注」                              「跳转回附注」
  │        │                                          │
  │        ▼                                          ▼
  │  j1NoteSectionMap.buildJ1SyncPayload      noteDisclosureReverseJump
  │        │  (三张子表 + columns + _note_texts)   .buildNoteJumpRoute
  │        ▼                                          │
  │  POST /api/disclosure-notes/{pid}/{year}/{sec}/sync-from-workpaper
  │        │  （后端不改：浅合并 sub_table_data + pop _note_texts → text_content）
  │        ▼
  │  disclosure_notes(五、40 / 八、40)
  │        │  get_note_detail → note_sub_table_projector 投影 _tables
  │        ▼
  │  附注模块 DisclosureEditor 渲染
  │        │  「跳转至披露表」
  │        ▼
  └── noteDisclosureJump.resolveNoteDisclosureJumpTarget → J1 披露 sheet

事件：披露表 emit disclosure:note-text-updated{accountCode:'2211', projectId, sectionIds}
      → useNoteRefresh 匹配 2211 分支 → 定向刷新当前章节
```

## Components and Interfaces

### 新增：`components/workpaper/composables/j1NoteSectionMap.ts`

纯数据 + 纯函数模块（便于 vitest，不依赖组件实例）：

```ts
export type J1DisclosureVariant = 'listed' | 'soe'

/** 权威矩阵 ying_fu_zhi_gong_xin_chou */
export const J1_NOTE_SECTION = { listed: '五、40', soe: '八、40' } as const

/** workpaper_sheet_classification 实测值（Wave 0 核实后写死） */
export const J1_DISCLOSURE_SHEET_NAME = { listed: '<实测>', soe: '<实测>' } as const

/** 逐字取自模板 tables[].name；soe 第三张表按 Decision 3 消歧 */
export const J1_SUB_TABLE_KEYS = {
  listed: { summary: '应付职工薪酬', shortTerm: '短期薪酬', postEmployment: '设定提存计划' },
  soe: { summary: '应付职工薪酬列示', shortTerm: '短期薪酬列示', postEmployment: '设定提存计划列示' },
} as const

/** 五列，label 逐字取自模板 headers（两变体相同） */
export function j1MovementColumns(): ColumnDef[]

export function resolveJ1CurrentStandard(variant, applicableStandards): string

export interface J1DisclosureSnapshot {
  summary: J1SyncRow[]
  shortTerm: J1SyncRow[]
  postEmployment: J1SyncRow[]
  notes: Record<string, string>
}

export function buildJ1SyncPayload(args: {
  variant: J1DisclosureVariant
  wpId: string
  year: number | string
  snapshot: J1DisclosureSnapshot
  applicableStandards?: readonly string[] | null
}): { section: string; body: Record<string, unknown> }

export function buildJ1NoteTexts(variant, notes): Array<{ section: string; title: string; text: string }>
```

行映射：`{ label, values: [期初, 增加, 减少, 期末], is_total }` → 投影后首列取 label。数值走 `nullableAmount()`（空/未填 → `null`）。

### 修改：`J1TabDisclosureListed.vue` / `J1TabDisclosureSoe.vue`

- 工具栏新增「同步到附注」（success plain，只读禁用，loading 态）与「跳转回附注（五、40 / 八、40）」。
- `syncToDisclosureNotes()`：从 composable 现有 `summaryData / shortTermData / postEmploymentData / notes` 组装 `J1DisclosureSnapshot` → `buildJ1SyncPayload` → POST → 成功后 `eventBus.emit('disclosure:note-text-updated', { wpCode:'J1', accountCode:'2211', projectId, sectionIds:[J1_NOTE_SECTION[variant]] })`。
- 失败：`ElMessage.error` + 不改本地数据（Requirement 8.5）。

### 修改：`noteDisclosureJump.ts`（正向）

新增 `isJ1EmployeeBenefitsNoteSection(section)`（精确匹配 `五、40`/`八、40`）+ resolver 分支（返回 J1 底稿 + 对应披露 sheet）+ `wpCode` 联合类型补 `'J1'` + 族标签 map 补 `J1: '应付职工薪酬'`。分支位置置于既有精确章节分支区，不落入任何 `syncedSheet.includes(...)` 通用回退之后。

### 修改：`noteDisclosureReverseJump.ts`（反向）

`DISCLOSURE_NOTE_SECTION_MAP` 增 `J1: { listed: '五、40', soe: '八、40' }`。交叉守卫测试断言其与正向 predicate 同源。

### 修改：`useNoteRefresh.ts`（刷新）

`matchesDisclosureFamily` 增 2211 分支：`accountCode === '2211' && (current === '五、40' || current === '八、40')`。

### 修改：`backend/scripts/check/check_disclosure_columns_coverage.py`

`COLUMN_BUILDERS` 增 `buildJ1SyncPayload`，使 `--strict` 覆盖数 +1 且不出现未覆盖告警。

## Data Models

### J1SyncRow

| 字段 | 类型 | 说明 |
|---|---|---|
| label | string | 行标签（逐字沿用披露表行名/模板行名） |
| values | (number \| null)[] | 4 个数值列：期初余额 / 本期增加 / 本期减少 / 期末余额 |
| is_total | boolean? | 合计行标记 |

### Sync_Payload body

| 字段 | 说明 |
|---|---|
| wp_id | J1 底稿 wp_id |
| year | 审计年度（`useAuditContext().year`，显式传，不依赖后端默认自然年） |
| sheet_name | `J1_DISCLOSURE_SHEET_NAME[variant]` |
| section_id | `J1_NOTE_SECTION[variant]` |
| current_standard | 四值之一 |
| sub_table_data | `{ [Sub_Table_Key]: J1SyncRow[], _note_texts: Note_Texts }` |
| columns | `{ [Sub_Table_Key]: ColumnDef[] }`（键与 sub_table_data 同名） |

### 允许偏离模板的情形（备查）

| 情形 | 位置 | 依据 |
|---|---|---|
| 第三张表 Sub_Table_Key 取「设定提存计划列示」而非模板重复 name「短期薪酬列示」 | soe 八、40 | 模板 `text_sections` 章节标题；避免同名键覆盖丢表（Decision 3） |
| listed 组件列头「上年年末数」不作为 columns label，改用模板「期初余额」 | listed 五、40 | 附注表头须与模板一致（Decision 2） |

## Correctness Properties

### Property 1: 章节号冻结
`J1_NOTE_SECTION` 恒为 `{ listed: '五、40', soe: '八、40' }`，与权威变体矩阵一致。
**Validates: Requirements 1.1**

### Property 2: sheet 名与实测一致
`J1_DISCLOSURE_SHEET_NAME` 取值等于 `workpaper_sheet_classification`（wp_code=J1）中披露 sheet 的 `sheet_name`。
**Validates: Requirements 1.2, 1.3**

### Property 3: current_standard 四值封闭
`resolveJ1CurrentStandard` 对任意输入只返回四个合法值之一。
**Validates: Requirements 1.4**

### Property 4: 子表键与模板一致（含消歧）
listed 三键逐字等于模板三张表 name；soe 前两键逐字等于模板，第三键为消歧值「设定提存计划列示」。
**Validates: Requirements 2.2, 3.1, 3.2**

### Property 5: columns 键 = sub_table_data 键
两者键集合完全相等，且每张子表 columns 恰 5 列、label 逐字等于模板 headers。
**Validates: Requirements 2.3, 2.4**

### Property 6: 合计行标记
每张子表恰有一行 `is_total === true`，其余为数据行；缩进子项保留原标签且不被标为合计。
**Validates: Requirements 2.5**

### Property 7: 空值推 null
任一数值缺失/非有限数时对应 `values[i] === null`，不出现被 `0` 替代的情况。
**Validates: Requirements 2.6**

### Property 8: soe 两张同源表都落地
soe 载荷的 `sub_table_data` 同时含短期薪酬与设定提存两张表且行数各自独立（无覆盖）。
**Validates: Requirements 3.4**

### Property 9: 说明文本按段推送且跳过空段
非空说明进入 `_note_texts` 且带稳定 section 与中文标题；空说明不产生条目。
**Validates: Requirements 4.1, 4.2, 4.3**

### Property 10: 正向章节精确匹配
`isJ1EmployeeBenefitsNoteSection` 对 `五、40`/`八、40` 为真；对 `五、4`、`五、49`、`八、4`、`五、400` 为假。
**Validates: Requirements 5.1, 5.2**

### Property 11: 正反向同源
反向 `DISCLOSURE_NOTE_SECTION_MAP.J1` 的两个章节号与正向 predicate 判真集合完全一致。
**Validates: Requirements 6.1, 9.4**

### Property 12: 刷新匹配幂等
2211 + `五、40`/`八、40` 触发刷新为真，其他科目/章节不受影响；重复触发不改变数据。
**Validates: Requirements 7.1, 7.3**

### Property 13: 零回归
后端 sync 服务与附注模板文件字节不变；J1 披露表既有持久化键集合不变；既有跳转/刷新测试全绿。
**Validates: Requirements 8.2, 8.3, 8.4**

## Error Handling

| 场景 | 处理 |
|---|---|
| 同步接口 4xx/5xx | `ElMessage.error` 提示可重试；本地披露表数据不变（无半同步） |
| `projectId` 缺失 | 同步与反向跳转入口禁用（不发请求、不跳错误路由） |
| 只读态 | 同步入口禁用，反向跳转仍可用（只读导航无副作用） |
| 说明段全空 | 正常同步表格，`_note_texts` 为空数组 |
| 附注章节尚未生成 | 后端 upsert 语义负责创建/复活；前端只提示成功行数 |

## Testing Strategy

- **单元/属性测试（vitest）**：`j1NoteSectionMap.spec.ts` 覆盖 Property 1、3–9（纯函数，可用模板真实行名构造 snapshot）。
- **跳转测试**：扩 `noteDisclosureJump.spec.ts`（Property 10：含相邻章节号反例）与 `noteDisclosureReverseJump.spec.ts`（Property 11 交叉守卫）。
- **刷新测试**：扩 `useNoteRefresh` 相关 spec（Property 12）。
- **守卫**：`check_disclosure_columns_coverage.py --strict` 退出码 0（Property 5 的工程侧兜底）。
- **零回归门**：J1 前端全套 + 附注跳转/刷新/同步相关 spec 全绿；`git stash` 对照确认预存在失败与本 spec 无关（Property 13）。
- **live round-trip（可选）**：对真实项目真实章节做「DB 备份 → HTTP sync → GET 附注详情断言 `_tables` → DB 恢复 + RESTORED_IDENTICAL」（平台已 proven 范式，避免 Playwright flaky 且零污染）。
