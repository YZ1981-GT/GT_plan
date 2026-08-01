# Design

## Overview

H3 投资性房地产披露重建分三层协同，裁决者 = 源 xlsx `backend/wp_templates/H/H3 投资性房地产.xlsx`（运行时权威）：

1. **附注模板层**（`note_template_{listed,soe}.json` §五、21 / §八、21）：幂等脚本重建国企两级表头、按源模板重建两版行集、国企第 3 表消重名、补 `columns`/`guidance`、上市补 (4) 转换情况文本段。
2. **前端映射层**（`h3NoteSectionMap.ts`）：章节号纠正（已先行修 soe 八、22→八、21，本 spec 补守卫）、表名对齐模板、行形态由位置化 `values` 改规范业务键 dict、两级列定义、计量模式条件性 `_removed_table_keys`、合计行载荷层补齐。
3. **宿主/守卫层**：披露 Tab 接 `useDisclosureAutoSync` + `:project-id`；后端结构守卫（openpyxl 交叉比对）+ 前端契约守卫（共享 helper P1~P6）+ CI job。

不触碰 H3 四表取数（`_h3_investment_property.py`）与既有跨底稿勾稽（`h3TransferReconcile` / `h3MortgageReconcile`）。

## Architecture

**两级表头唯一机制**（平台既有）：`ColumnDef.group` → 后端 `note_sub_table_projector._extract_column_groups` → `_column_groups`（`{group,start,span}` 扁平，`start` 为 headers 下标）→ 消费方 `DisclosureEditor.activeTableColumns` + `note_word_exporter._build_two_level_header_rows`（Word 侧读时重投影，与 UI 同源）。

`_extract_column_groups` 三态：`None`=未声明（回退前缀推断）/ `[]`=任一列 `flat` 显式单级 / 非空=显式分组。混合分组（部分列无 `group`，如国企「期初余额」「期末余额」rowspan=2）前后端与 `validate_section` 均已支持。

**推送 vs seed 两路径**：`_source=workpaper` 时投影器只渲染推送的 `sub_table_data` + 载荷 `columns`（**不与模板 `_tables` 合并**）→ 模板 seed 只服务「从未同步过的项目」。故行集/列结构两侧都要对齐。

模板修订走共享 `backend/scripts/fix/_note_structure_kit.py`（`flat_columns` / `grouped_columns` / `rule` / `apply_plan` / `validate_section` / `run_section` / `build_cli`），沿用 D1/D6/H1/H2 范式（幂等 `--dry-run`/`--check` + `_aligned_by` 戳记）。

**上市列转置**：源模板上市列 = 资产类别（房屋、建筑物 / 土地使用权 / 在建工程 / 合计），行 = 变动层次。故列 `key` 用类别名（同 H1「固定资产情况」范式：`{key: '房屋、建筑物', label: '房屋、建筑物'}`），行 label 承载层次明细。类别可按项目实际扩展，seed 保留源模板四列。

## Components and Interfaces

### 后端

- `backend/scripts/fix/fix_note_h3_investment_property_structure.py`（新建）
  - listed §五、21 plan（3 表 + text_sections）：
    - `按成本计量的投资性房地产`：flat 5 列（项目 + 房屋、建筑物 / 土地使用权 / 在建工程 / 合计），行 = 源模板四层（去「可无限量添加行」占位）
    - `按公允价值计量的投资性房地产`：flat 5 列同上，行 = 期初 / 本期变动（加·减·公允价值变动）/ 期末
    - `未办妥产权证书的情况`：flat 3 列（项目 / 账面价值 / 未办妥产权证书原因）+ 空行骨架 + 合计
    - `text_sections` 补 (4) 房地产转换情况（`#### ` 前缀，避免裸表名当正文）
  - soe §八、21 plan（3 表）：
    - `以成本计量`：两级 7 列 `grouped_columns(('label','项目'), [(begin,期初余额,AMOUNT,None), (buy_or_provision,购置或计提,AMOUNT,本期增加), (transfer_in,自用房地产或存货转入,AMOUNT,本期增加), (disposal,处 置,AMOUNT,本期减少), (transfer_out,转为自用房地产,AMOUNT,本期减少), (end,期末余额,AMOUNT,None)])`，行 = 5 层 × (合计 + 2 类别)
    - `以公允价值计量`：两级 8 列（本期增加 3 子列含 `公允价值变动损益`；本期减少 2 子列），行 = 3 层 × (合计 + 其中 2 类别)
    - `未办妥产权证书的投资性房地产`（由重名 `以公允价值计量` 改名，走 `rule` aliases）：flat 3 列（项目 / 账面价值 / 原因）
- `backend/tests/test_note_h3_investment_property_structure.py`（新建）：`--check` 无欠账 / 表数表名序 / 两级分组自洽 / flat 表态 / columns key 与前端一致 / 行集层次 / 无重名 / openpyxl 直读源 xlsx tab 名 + 国企两级子表头（购置或计提·自用房地产或存货转入·处 置·转为自用房地产·公允价值变动损益）交叉比对 / 反向自检。

### 前端

- `h3NoteSectionMap.ts` 重写：
  - `H3_NOTE_SECTION = {listed:'五、21', soe:'八、21'}`（已修，守卫锁定）
  - `H3_LISTED_SUBTABLE` / `H3_SOE_SUBTABLE` 常量对齐模板表名 + `H3_LEGACY_OBSOLETE_TABLES`（旧四套载荷表名 + 重名 `以公允价值计量`）
  - `buildH3ListedColumns()` / `buildH3SoeColumns()`（两级用 `group`，单级标 `flat`）
  - `buildH3SyncPayload` 行形态改 `{key: dict}`；按 `measurementModel` 二选一 + `_removed_table_keys`；合计行经 `withTotalRow()` 幂等补齐；`_note_texts` 带中文 title + 空文本过滤
- `GtH3InvestmentProperty.vue` / 披露 Tab：接 `useDisclosureAutoSync`（watch 构建载荷的实际数据）、`:project-id` 透传、(4) 转换情况文本域 + AI + `GtReviewTrigger`
- `h3NoteSubtableContract.spec.ts`（新建）：共享 helper P1~P6 + H3 专属（章节号、两级分组、无 `八、22`、行形态为 dict 非 values）

## Data Models

国企「以成本计量」两级列（7 列，混合分组）：

```
{ key: label,             label: 项目,                   is_label: true }
{ key: begin,             label: 期初余额,                format: amount }            // 无 group（rowspan=2）
{ key: buy_or_provision,  label: 购置或计提,              group: 本期增加, format: amount }
{ key: transfer_in,       label: 自用房地产或存货转入,     group: 本期增加, format: amount }
{ key: disposal,          label: 处 置,                   group: 本期减少, format: amount }
{ key: transfer_out,      label: 转为自用房地产,           group: 本期减少, format: amount }
{ key: end,               label: 期末余额,                format: amount }            // 无 group
```

国企「以公允价值计量」两级列（8 列）：`期初公允价值` + 本期增加{`购置`, `自用房地产或存货转入`, `公允价值变动损益`} + 本期减少{`处 置`, `转为自用房地产`} + `期末公允价值`。

上市两表列转置（flat 5 列）：`项目` + `房屋、建筑物` / `土地使用权` / `在建工程` / `合计`（key 用类别名，同 H1「固定资产情况」范式）。

`_removed_table_keys`：旧载荷表名（`以成本模式计量的投资性房地产（账面原值）` 等 4 条 + `投资性房地产（账面原值）` 等 4 条）∪ 未选中的计量模式表名 ∪ 重名旧键。

## Correctness Properties

### Property 1: 章节号正确且不串味

*For any* variant，`H3_NOTE_SECTION[variant]` SHALL 等于 `note_template_variant_matrix.json` 中 `tou_zi_xing_fang_di_chan` 对应值（listed=五、21 / soe=八、21）；`八、22`（固定资产）SHALL 不出现在 H3 任何映射或断言中。

**Validates: Requirements 1.1, 1.5**

### Property 2: 子表名逐字命中模板且无重名

*For any* H3 载荷子表名，SHALL 存在于对应 variant 模板 `tables[].name`；模板同一章节内表名 SHALL 唯一（国企第 3 表不得与第 2 表同名）。

**Validates: Requirements 1.2, 1.3**

### Property 3: 两级表头叶子列与源模板一致

*For any* 国企两级表，columns 叶子列名序列 SHALL 等于源 xlsx 第二行表头，分组名等于第一行跨列表头；rowspan=2 的期初/期末列 SHALL 无 `group`。

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 4: 分组结构自洽

*For any* 两级表，`_column_groups` SHALL 由 columns.group 派生（相邻同名合并、`start≥1`、`start+span≤len(headers)`）且 `group` 不含 `/`；单级表 SHALL 无 `_column_groups` 且至少一列标 `flat`。

**Validates: Requirements 2.4, 6.1**

### Property 5: 载荷行形态规范

*For any* 载荷 `sub_table_data` 表，其行 SHALL 为业务键 dict（键 ⊆ 该表 columns 的 key 集合），SHALL NOT 为位置化 `{label, values:[]}`。

**Validates: Requirements 4.1**

### Property 6: 计量模式互斥且旧键清理

*For any* `measurementModel`，载荷 SHALL 只含该模式的表，另一模式表名 SHALL 出现在 `_removed_table_keys`；历史孤儿表名 SHALL 一并清理。

**Validates: Requirements 1.4, 4.2, 4.3**

### Property 7: 行集层次与占位

*For any* 模板表 rows，SHALL 无「可无限量添加行」占位说明行、无 `row_type: header_label`；国企两表层次数分别为 5 层 / 3 层且每层含 2 个类别行。

**Validates: Requirements 3.1, 3.2, 3.5**

### Property 8: columns[0] 对齐 headers[0] 且 guidance 齐备

*For any* 表，`columns[0].label == headers[0]` 且首列 `is_label`；每表 `guidance` 非空。

**Validates: Requirements 6.1, 6.2**

### Property 9: 幂等与零回归

*For any* 连续两次运行 `fix_note_h3_investment_property_structure.py`，第二次 SHALL 为空操作；运行后附注 JSON SHALL 可解析且 §五、21 / §八、21 之外章节不变。

**Validates: Requirements 7.2, 7.3**

## Error Handling

- 幂等脚本 `apply_plan` 找不到目标表时只 `warning`（除非 `insert=True`）；表名迁移目标已被占用则跳过并告警。
- `run_section` 在 `validate_section` 有 errs 时**不写文件**，坏结构不落盘。
- 表名改名（国企重名 `以公允价值计量` → 未办妥产权证书）走 `rule` aliases，**不能进 `drops`**（`drop_tables` 在 `apply_plan` 之前执行，会连行一起删掉——H2 已踩过）。
- 前端同步 `catch` 静默吞 409（跨主体类型守卫）沿用平台语义；缺 `projectId` 由平台守卫拦截。
- 源 xlsx 读取失败时守卫直接 fail（不 fallback），确保结构确权基于真源。

## Testing Strategy

- 后端：`fix_note_h3_investment_property_structure.py --check`（幂等 0 欠账）+ `test_note_h3_investment_property_structure.py`（结构 + openpyxl 交叉比对 + 反向自检）。
- 前端：`h3NoteSubtableContract.spec.ts`（共享 helper P1~P6 + H3 专属）+ 载荷单测（行形态 dict / 计量模式互斥 / `_removed_table_keys` / 合计行幂等）。
- 集成：CI job `note-h3-structure`。
- 实测：chrome-devtools + postgres 只读，两变体（listed 需临时把 `0ec33ac9` 的 `applicable_standard_v2.entity_type` 置 listed，测后还原）验证 Tab 挂载、两级表头落库、无孤儿表、`last_sync_at` 前移。
