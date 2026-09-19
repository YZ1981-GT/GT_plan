# Design: D 类剩余披露表与附注结构对齐（D3 / D5 / D6 / D7）

## Overview

四个循环共用一条已存在的链路：底稿披露 Tab → `buildDXSyncPayload` →
`POST /api/projects/{id}/disclosure-notes/sync-from-workpaper` →
`note_sub_table_projector` 投影 → 附注编辑页 / Word 导出。链路本身健康
（四个 Tab 都已接 `useDisclosureAutoSync`），本 spec 只修两端的**结构**：

- **模板端**（`backend/data/note_template_{listed,soe}.json`）：补 `columns` / `guidance`，
  修垃圾表名与被压扁的表头 → 影响 seed 路径（新建项目）与 Word 导出
- **载荷端**（`audit-platform/frontend/src/components/workpaper/composables/dXNoteSectionMap.ts`）：
  两级表头改走 `ColumnDef.group`、补回缺失的上年年末段、表名对齐模板 → 影响已同步项目

裁决顺序（平台既定）：源 xlsx（`backend/wp_templates/D/`，权威目录）> 校验预设 >
模板 JSON。`基础数据/` 目录在本仓库不存在，不作为裁决者。

## Architecture

```
backend/wp_templates/D/D{3,5,6,7} *.xlsx   ← 唯一裁决者（openpyxl 逐格 + 合并区）
        │
        ├─ backend/scripts/fix/fix_note_d_cycle_rest_structure.py   (幂等，--check/--apply)
        │       └─→ backend/data/note_template_{listed,soe}.json
        │              五、38 八、38 | 五、6 八、6 | 五、10 八、11 | 五、39 八、39
        │
        └─ audit-platform/frontend/src/components/workpaper/composables/
                 d3NoteSectionMap.ts / d5… / d6… / d7…      (载荷列头单一真源)
                        ↑
                 d3/D3TabDisclosure{Listed,Soe}.vue
                 d5/D5TabDisclosure.vue
                 d6/D6TabDisclosure.vue
                 d7/D7TabDisclosure.vue
```

守卫三层：
1. `backend/tests/test_note_d_cycle_rest_structure.py` — 模板结构（表数/列/group/flat/guidance）
2. `composables/__tests__/d{3,5,6,7}NoteSubtableContract.spec.ts` — 复用共享 helper 5 条 Property
3. `__tests__/disclosureColumnsCoverage.spec.ts` — `P1_ROUTE` 登记（新增 builder 时）

## Components and Interfaces

### 幂等脚本 `fix_note_d_cycle_rest_structure.py`

沿用 `fix_note_d1_notes_receivable_structure.py` 的形态：

```python
SECTIONS = {
    ("listed", "五、38"): D3_LISTED_TABLES,   # 3 表
    ("soe",    "八、38"): D3_SOE_TABLES,      # 2 表
    ("listed", "五、6"):  D5_LISTED_TABLES,   # 4 表
    ("soe",    "八、6"):  D5_SOE_TABLES,      # 1 表
    ("listed", "五、10"): D6_LISTED_TABLES,   # 6 表（模板 9 → 6，删/改垃圾表名）
    ("soe",    "八、11"): D6_SOE_TABLES,      # 3 表
    ("listed", "五、39"): D7_LISTED_TABLES,   # 3 表
    ("soe",    "八、39"): D7_SOE_TABLES,      # 2 表
}
```

每表描述 `{name, headers, columns, guidance, rows?}`；`_aligned_by` 打标记；
`--check` 对比现状与目标，差异非空即 exit 1。垃圾表名处理走
`RENAMES`（旧名 → 新名）与 `DROPS`（整表删除）两张显式表，避免误删他 spec 的表。

### D6 列定义（唯一真源在 `d6NoteSectionMap.ts`）

```ts
// 主表（上市）：标签列 + 两组 × 3 列
const D6_MAIN_GROUPS = { listed: ['期末余额', '上年年末余额'], soe: ['期末数', '期初数'] }
const mainColumns = (v: D6DisclosureVariant): ColumnDef[] => [
  { key: 'label', label: '项  目', is_label: true },
  ...D6_MAIN_GROUPS[v].flatMap((g, i) => (['账面余额', '减值准备', '账面价值'] as const)
      .map((sub, j) => ({ key: `${i ? 'prior' : 'end'}_${['book_balance','impairment','book_value'][j]}`,
                          label: sub, group: g, format: 'amount' }))),
]

// （2）减值准备计提情况（上市）：源 11 列，两级（三级表头的第 3 层拼进子列名）
//   期末余额 → 账面余额金额 / 账面余额比例(%) / 减值准备金额 / 预期信用损失率(%) / 账面价值
const IMPAIRMENT_SUBS = ['金额', '比例(%)', '减值准备金额', '预期信用损失率(%)', '账面价值'] as const
```

> 三级表头（源 B44:C44「账面余额」下再分「金额/比例(%)」）在平台附注渲染器只支持两级，
> 故第 3 层并入子列名（`金额` / `比例(%)` 保持源字面，语义由 `group` 承载），
> 与 D2 分类披露的既有处理一致。

### 二选一表组（D6 上市 A20「或：披露格式如下」）

源模板 A21-A26 是主表的**替代格式**（合同资产 / 减：合同资产减值准备 / 小计 /
减：列示于其他非流动资产的合同资产 / 合计）。按 F2 范式做 `mainFormat` 开关
（`detailed` | `simple`），未选中的一侧进 `_removed_table_keys`。

### 文本段落

各循环文本域键集集中声明在 `dXNoteSectionMap.ts` 的 `DX_NOTE_TEXT_SECTIONS`，
组件按同一常量渲染文本域 + AI 按钮；守卫交叉校验「组件键集 ≡ 常量 ≡ 后端 prompt 键」。

## Data Models

### 模板表结构（目标态摘要）

D3 上市 五、38（3 表）
1. `预收款项` — `项 目 | 期末余额 | 上年年末余额`（flat）
2. `账龄超过1年的重要预收款项` — `项目 | 期末余额 | 未偿还或未结转的原因`（flat）
3. `本期预收账款账面价值的重大变动` — `项目 | 变动金额 | 变动原因`（flat）

D3 国企 八、38（2 表）
1. `预收款项` — `账  龄 | 期末余额 | 期初余额`（flat）
2. `账龄超过1年的重要预收账款` — `债权单位名称 | 期末余额 | 未偿还原因`（flat；源 A11 为「未偿还原因」）

D5 上市 五、6（4 表）
1. `应收款项融资` — `项  目 | 期末余额 | 上年年末余额`（flat；行含 应收票据/应收账款/小 计/减：其他综合收益-公允价值变动/期末公允价值）
2. `本期计提、收回或转回的减值准备情况` — `项目 | 减值准备金额`（flat；补回标签列）
3. `期末本公司已质押的应收票据` — `种  类 | 期末已质押金额`（flat）
4. `期末本公司已背书或贴现但尚未到期的应收票据` — `种  类 | 期末终止确认金额 | 期末未终止确认金额`
   （🔴 必须 flat：两列共前缀「期末」会被推断出凭空父表头）

D5 国企 八、6（1 表）：`应收款项融资` — `项  目 | 期末余额 | 期初余额`（flat）

D6 上市 五、10（6 表，两级表头 4 张）
1. `合同资产` — 标签 + `期末余额`{账面余额,减值准备,账面价值} + `上年年末余额`{同构}
2. `本期合同资产账面价值的重大变动` — flat 3 列
3. `合同资产减值准备计提情况` — 标签 + `期末余额`{金额,比例(%),减值准备金额,预期信用损失率(%),账面价值} + `上年年末余额`{同构}
4. `按单项计提减值准备` — `名 称 | 账面余额 | 坏账准备 | 预期信用损失率(%) | 计提理由`（flat）
5. `按单项计提减值准备（续：上年年末余额）` — 同构（源 A61「续：」）
6. `组合计提项目：{组名}` — 标签 + `期末余额`{合同资产,坏账准备,预期信用损失率(%)} + `上年年末余额`{同构}
7. `本期计提、收回或转回的合同资产减值准备情况` — flat 5 列

> 表 6 是**逐组一张**（源示例组名「工程施工」「质量保证金」），模板里的两张示例表保留为骨架。

D6 国企 八、11（3 表）
1. `合同资产情况` — 标签 + `期末数`{3 列} + `期初数`{3 列}
2. `合同资产减值准备` — `项  目 | 期初数 | 本期变动金额`{计提,转回,转销/核销} + `期末数 | 原因`
3. `本期合同资产账面价值的重大变动` — flat 3 列（源 A25 标注「国资委格式未要求披露」→ 写入 guidance）

D7 上市 五、39（3 表）：`合同负债`（flat）/ `账龄超过1年的重要合同负债`（flat）/
`本期合同负债账面价值的重大变动`（flat）
D7 国企 八、39（2 表）：`合同负债`（flat）/ `本期合同负债账面价值的重大变动`
（原占位名 `合同负债（表2）` → 重命名）

## Correctness Properties

### Property 1: 载荷子表名与模板表名逐字一致
对四循环 8 个章节的每个载荷子表名，存在模板 `tables[].name` 与之逐字相等。
**Validates: Requirements 3.1, 3.4**

### Property 2: 每张表显式表态 flat 或 group
每张表的 `columns` 中，存在至少一列带 `flat: true`，或存在至少一列带非空 `group`；
两者不得在同一张表内同时出现。
**Validates: Requirements 1.2, 1.3**

### Property 3: 分组列索引连续且不含标签列
对任一表的 `_column_groups`，同一 `group` 的列索引连续，且 `start >= 1`（标签列不入组）。
**Validates: Requirements 2.1, 2.2**

### Property 4: 两期同构
D6 含比较期的表（主表 / 减值计提情况 / 组合明细），期末组与上年组的子列名序列相等。
**Validates: Requirements 2.1, 2.2, 2.4**

### Property 5: 幂等性
脚本 `--apply` 连续两次运行，第二次变更数为 0，且 `--check` exit 0。
**Validates: Requirements 1.5, 5.1**

### Property 6: 无垃圾表名与假数据行
四循环 8 个章节内，不存在空表名、以 `续：` 单独命名的表、与 `headers[0]` 同名的表，
也不存在 `row_type == 'header_label'` 的行。
**Validates: Requirements 3.2, 5.2**

### Property 7: 文本段落键集一致
每循环「组件文本域键集」≡「`DX_NOTE_TEXT_SECTIONS` 键集」，且每键有中文 `title`。
**Validates: Requirements 4.1, 4.2**

## Error Handling

- 脚本对**未在 `RENAMES` / `DROPS` 显式登记**的既有表一律不动（宁漏不误杀，
  同章节可能被别的底稿推送）
- `--check` 只读；`--apply` 前打印 diff 摘要
- 载荷侧遇空数据整表跳过而非推空表（避免把附注既有数据清空）

## Testing Strategy

1. 后端 `backend/tests/test_note_d_cycle_rest_structure.py`：参数化跑 8 个章节 ×
   Property 1~4、6；含反向自检（构造一张缺 flat 的表，断言守卫会红）
2. 前端 `d{3,5,6,7}NoteSubtableContract.spec.ts`：`runDisclosureSubtableContract`
3. 前端 `d6DisclosureColumns.spec.ts`：D6 两级表头结构逐表钉死（Property 4）
4. Word 导出：`backend/tests/services/test_note_word_export_d_cycle.py`，
   复用 D1 范式验证 `_build_two_level_header_rows`（D6 的 4 张两级表）
5. 浏览器实测：chrome-devtools MCP 驱动 + postgres 只读比对落库
