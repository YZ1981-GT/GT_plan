# Design

## Overview

H8 使用权资产（上市 §五、25 / 国企 §八、26，各 1 张表）的**行集已与源模板一致**，本 spec 只补列元数据/提示与修文本元数据：

1. **模板层**：幂等脚本给两版补 `columns`（单级 `flat`）+ `guidance`，并把上市 headers 的 `……` 占位列头展开为 `其他`（与底稿默认分类及载荷列名一致）。`rows=None` **不动行集**（上市 `……` 行是真实可扩行）。
2. **载荷层**（`h8DisclosureSyncPayload.ts`）：`_note_texts` 补中文 `title` + 空文本过滤（抽 `buildH8NoteTexts` 纯函数，两变体共用）。
3. **守卫层**：后端结构守卫（openpyxl 交叉比对 + 反向自检 + 正向断言 `……` 行保留）+ 前端契约守卫（列 key 一致 / title / 空过滤 / 无自调度）+ CI job。

不动行集、不动自动同步（两 Tab 的 `scheduleAutoSync` 在 `onSave` 回调，已正确）。

## Architecture

**单级表头 + `flat`**：两版表头都是单行 → `columns` 必须显式 `flat`，否则 `_extract_column_groups` 返回 `None` 走 `_infer_groups_from_headers`，国企 `本期增加`/`本期减少` 会被反猜出凭空「本期」父表头（平台已多次踩中）。

**列转置（上市）**：列 = 资产类别（房屋及建筑物/机器设备/运输设备/其他）+ 合计，行 = 四层变动明细。列 `key` 用**类别名本身**（与 `buildH8ListedColumns` 的 `key: c.label` 同口径，也与 H1「固定资产情况」范式一致）。故模板 seed 的列名必须等于底稿默认分类名 —— 这是把 `……` 展开为 `其他` 的依据。

**`……` 两种语义要分清**（本 spec 的关键判断）：
- **`……` 作列头**：无法承载数据（载荷永远不会推一个叫 `……` 的类别）→ 必须展开为实际类别 `其他`。
- **`……` 作行**：在 H8 底稿模型里是**真实可扩行**（`cost_inc_ellipsis` / `dep_inc_ellipsis` 等键参与各块 `sumOf` 小计）→ **必须保留**，与「可无限量添加行」那类纯占位说明不同（后者才须删）。

**`_note_texts` 契约**：位于 `sub_table_data` 内；每条 `{section, title, text}`。缺 `title` 时后端 `_format_note_texts` 用 `section` 兜底 → 正文出现英文键。空文本须过滤（与 F2/D1/H5 范式一致）。

模板修订走共享 `_note_structure_kit`（`flat_columns` / `rule` / `run_section` / `build_cli`），幂等 `--dry-run`/`--check` + `_aligned_by` 戳记。

## Components and Interfaces

### 后端

- `backend/scripts/fix/fix_note_h8_right_of_use_structure.py`（新建）
  - listed §五、25：`rule('使用权资产', flat_columns([('label','项目',None), ('房屋及建筑物',…,AMOUNT), ('机器设备',…), ('运输设备',…), ('其他',…), ('合计',…)]), None, guidance)`
    —— `headers_of(cols)` 自然产出展开后的 6 列 headers，`……` 随之消失。
  - soe §八、26：`rule('使用权资产', flat_columns([('label','项目',None),('begin','期初余额',AMOUNT),('increase','本期增加',AMOUNT),('decrease','本期减少',AMOUNT),('end','期末余额',AMOUNT)]), None, guidance)`
- `backend/tests/test_note_h8_right_of_use_structure.py`（新建）

### 前端

- `h8DisclosureSyncPayload.ts`
  - 新增 `H8_NOTE_TEXT_TITLES: Record<string,string>` + `buildH8NoteTexts(items)` 纯函数（过滤空、补 title），两变体共用
  - `buildH8ListedSubTableData` / `buildH8SoeSubTableData` 改用该函数；全空时不产生 `_note_texts` 键
- `composables/__tests__/h8NoteSubtableContract.spec.ts`（新建）

## Data Models

上市列（6 列 flat，key = 类别名）：

```
{ key: label,        label: 项目,        is_label: true, flat: true }
{ key: 房屋及建筑物,  label: 房屋及建筑物, format: amount }
{ key: 机器设备,      label: 机器设备,     format: amount }
{ key: 运输设备,      label: 运输设备,     format: amount }
{ key: 其他,          label: 其他,         format: amount }   ← 原为「……」占位列头
{ key: 合计,          label: 合计,         format: amount }
```

国企列（5 列 flat）：`label/begin/increase/decrease/end` → `项目/期初余额/本期增加/本期减少/期末余额`。

`_note_texts` 标题映射：

```
listed-short-low   → 短期租赁及低价值资产租赁费用说明
listed-impairment  → 使用权资产减值情况说明
soe-impairment     → 使用权资产减值情况说明
```

## Correctness Properties

### Property 1: 列定义表态且对齐 headers

*For any* 变体，表 `columns` SHALL 非空、首列 `is_label` + `flat`、`columns[i].label` 序列 SHALL 等于 `headers`，且 SHALL NOT 残留 `_column_groups`。

**Validates: Requirements 1.2, 1.4**

### Property 2: `……` 列头已展开且不复活

*For any* 变体的 `headers` 与 `columns[].label`，SHALL NOT 包含 `……`；上市第 5 列 SHALL 为 `其他`。

**Validates: Requirements 1.1**

### Property 3: 载荷列 key ≡ 模板列 key

`buildH8ListedColumns(默认分类)` 与 `H8_SOE_COLUMNS` 的 key 序列 SHALL 分别等于模板两版 `columns[].key` 序列（seed 路径与推送路径同键）。

**Validates: Requirements 1.3**

### Property 4: 行集不变且 `……` 行保留

*For any* 变体，模板行标签序列 SHALL 与源 xlsx 一致（上市 38 行、国企 25 行）；上市 SHALL 保留 6 个 `……` 行（正向断言，防被当占位误删）。

**Validates: Requirements 4.4, 4.1**

### Property 5: `_note_texts` 中文标题与空过滤

*For any* 非空文本条目 SHALL 有非空中文 `title`（不得为 `section` 英文键）；空白文本 SHALL 不产生条目；全空时 SHALL 无 `_note_texts` 键；`_note_texts` SHALL 位于 `sub_table_data` 内。

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 6: 无自调度

两个披露 Tab 的 `syncToNotes` 函数体 SHALL NOT 含 `scheduleAutoSync`（现状为 `onSave` 回调触发，守卫防回退）。

**Validates: Requirements 4.2**

### Property 7: 幂等与零回归

连续两次运行脚本第二次 SHALL 为空操作；附注 JSON SHALL 可解析；两章节之外内容不变。

**Validates: Requirements 4.4**

## Error Handling

- `run_section` 在 `validate_section` 有 errs 时不写文件；`rows=None` 表示不动行集。
- `buildH8NoteTexts` 对 `undefined`/`null`/空串一致过滤，不抛错。
- 源 xlsx 读取失败时守卫直接 fail（不 fallback）。

## Testing Strategy

- 后端：`fix_note_h8_right_of_use_structure.py --check` + `test_note_h8_right_of_use_structure.py`（Property 1/2/4/7 + openpyxl 交叉比对 + 反向自检）。
- 前端：`h8NoteSubtableContract.spec.ts`（Property 3/5/6；Property 6 读组件源码先 `stripComments` 并按花括号配对截取函数体，含反向自检）。
- CI：`note-h8-structure` job。
