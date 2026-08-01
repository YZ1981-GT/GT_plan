# Design

## Overview

H5 油气资产（§八、25，**仅国企**）的附注模板结构已与源模板一致，本 spec 只修**前端载荷侧**的 4 个静默 bug + 补模板 `columns`/`guidance`：

1. **模板层**：幂等脚本给 §八、25 唯一表补 5 列 `columns`（显式 `flat`）+ `guidance`（源模板「—」列示约定 + 四层勾稽）。
2. **映射层**（`h5NoteSectionMap.ts`）：复用共享 `ColumnDef`；列定义 3→5 列且 key/label 对齐模板；行形态由位置化 `values` 改业务键 dict；行集按源模板 16 行四层构造（层合计填期末，其中类别与期初/增减留 `null`）；`_note_texts` 移入 `sub_table_data`。
3. **组件层**（`H5TabDisclosureSoe.vue`）：删自调度、改 `watch` 实际数据触发自动同步。
4. **守卫层**：后端结构守卫（openpyxl 交叉比对 + 反向自检）+ 前端契约守卫（含上市豁免登记）。

不新建上市章节（`variant_matrix` listed=null 且 listed 模板实测 0 章节）。

## Architecture

**载荷契约**（后端 `SyncFromWorkpaperRequest` 实测）：顶层仅 `wp_id` / `sheet_name` / `section_id` / `sub_table_data` / `columns` / `current_standard` / `year`。`_note_texts` 与 `_removed_table_keys` 是 `sub_table_data` 内的 `_` 前缀**元数据键**，由服务层 `_extract_note_texts` pop 后写 `text_content`。放顶层 → pydantic 忽略额外字段 → 静默丢弃。

**行形态**：`sub_table_data = {表名: [业务键 dict]}`，投影器 `note_sub_table_projector.project_sub_tables` 按 `row.get(colDef.key)` 取值。位置化 `{label, values:[]}` 虽有逆投影兜底，但**列数/列序不符时会静默错列**（H5 现状：2 值塞进 4 数据列且顺序相反）。

**单级表头**：源模板 §八、25 表头是单行 5 列 → columns 必须显式 `flat`，否则 `_extract_column_groups` 返回 `None` 走前缀推断（`本期增加额`/`本期减少额` 会被反猜出凭空「本期」父表头）。

**自动同步**：`useDisclosureAutoSync` 的 `scheduleAutoSync(fn)` 必须由 **watch 实际数据** 调用；写在 `fn` 内部即自调度（周期重复 POST + 骗过覆盖率守卫）。watch 默认 `immediate:false`，挂载本身不触发，**不需要**一次性防护。

## Components and Interfaces

### 后端

- `backend/scripts/fix/fix_note_h5_oil_gas_structure.py`（新建，复用 `_note_structure_kit`）
  - soe §八、25 plan：表 `油气资产` → `flat_columns([('label','项目',None),('begin','期初余额',AMOUNT),('increase','本期增加额',AMOUNT),('decrease','本期减少额',AMOUNT),('end','期末余额',AMOUNT)])`；`rows=None`（模板行集已正确，不动）；补 `guidance`。
- `backend/tests/test_note_h5_oil_gas_structure.py`（新建）：`--check` 无欠账 / 表名 / 行集 16 行四层且合计行标 `is_total` / flat 表态 / columns key 与前端一致 / guidance / openpyxl 交叉比对源 xlsx 表头（行 9）与四层行标签（行 10~24）/ 反向自检 / **listed 豁免断言**（listed 模板 0 个油气章节）。

### 前端

- `h5NoteSectionMap.ts` 重写：
  - `import type { ColumnDef } from './disclosureColumnDefs'`（删本地定义）
  - `H5_SOE_SUBTABLE = { main: '油气资产' }`；`H5_SOE_ROW_LABELS`（16 条，单一真源）
  - `H5_SOE_COLUMNS`：5 列，`label` 列 `is_label + flat`，金额列 `format:'amount'`
  - `buildH5SyncPayload(opts)`：`layerTotals` 入参（`{cost, depletion, impairment}` 期末值）→ 构造 16 行 dict；层合计填 `end`，其余键与「其中：」行为 `null`；`四、账面价值合计.end = cost − depletion − impairment`；`sub_table_data._note_texts` 带中文 title + 空过滤
- `H5TabDisclosureSoe.vue`：
  - 删 `syncToNote()` 内的 `autoSync.scheduleAutoSync(syncToNote)`
  - 新增 `watch([() => summaryRows.value, () => soeDisclosureText.value], () => autoSync.scheduleAutoSync(syncToNote), { deep: true })`
  - 调用处改传 `layerTotals`（不再传自造 4 行）
- `composables/__tests__/h5NoteSubtableContract.spec.ts`（新建）

## Data Models

§八、25 列定义（单级 5 列）：

```
{ key: label,    label: 项目,       is_label: true, flat: true }
{ key: begin,    label: 期初余额,    format: amount }
{ key: increase, label: 本期增加额,  format: amount }
{ key: decrease, label: 本期减少额,  format: amount }
{ key: end,      label: 期末余额,    format: amount }
```

15 行四层（4 层合计 + 11 类别行；`其中：` 行与非期末列一律 `null`）：

```
一、原价合计                        is_total  end=cost
  其中：1．探明矿区权益 / 2．未探明矿区权益 / 3．井及相关设施
二、累计折耗合计                    is_total  end=depletion
  其中：1．探明矿区权益 / 2．井及相关设施          ← 该层源模板只有 2 类
三、油气资产减值准备累计金额合计      is_total  end=impairment
  其中：1．探明矿区权益 / 2．未探明矿区权益 / 3．井及相关设施
四、油气资产账面价值合计             is_total  end=cost−depletion−impairment
  其中：1．探明矿区权益 / 2．未探明矿区权益 / 3．井及相关设施
```

## Correctness Properties

### Property 1: 行标签逐字对齐模板

*For any* 载荷行，其 `label` SHALL 属于模板 `rows[].label` 集合；且载荷行序 SHALL 与模板行序一致（**15 行** = 4 层合计 + 11 类别行）。

**Validates: Requirements 1.1, 1.2**

### Property 2: 行形态与列键一致

*For any* 载荷行，SHALL 为 dict 且其非 `label`/`is_total` 键 ⊆ columns 的 key 集合；SHALL NOT 含 `values` 键。

**Validates: Requirements 2.2**

### Property 3: 列定义对齐模板

`H5_SOE_COLUMNS[主表]` 的 key/label 序列 SHALL 等于设计的 5 列；`columns[0].label == 模板 headers[0]` 且首列 `is_label` + `flat`。

**Validates: Requirements 2.1, 5.1**

### Property 4: 宁缺勿造

*For any* 「其中：」类别行，其 `begin`/`increase`/`decrease`/`end` SHALL 全为 `null`；*for any* 层合计行，其 `begin`/`increase`/`decrease` SHALL 为 `null`（底稿无该维度数据时不得用 0 冒充）。

**Validates: Requirements 1.3**

### Property 5: 账面价值层派生

`四、油气资产账面价值合计.end` SHALL === `一、原价合计.end − 二、累计折耗合计.end − 三、减值准备累计金额合计.end`。

**Validates: Requirements 1.4**

### Property 6: `_note_texts` 位置与 title

`_note_texts` SHALL 出现在 `sub_table_data` 内且**不在**载荷顶层；每条 SHALL 有非空中文 `title`；空文本 SHALL 不产生条目。

**Validates: Requirements 3.1, 3.2**

### Property 7: 无自调度

`H5TabDisclosureSoe.vue` 的 `syncToNote` 函数体 SHALL NOT 含 `scheduleAutoSync`；组件 SHALL 存在 watch 型 `scheduleAutoSync` 调用。

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 8: 上市豁免

`note_template_listed.json` SHALL 不含 `油气资产` 章节，且 `variant_matrix.you_qi_zi_chan.listed_standalone` SHALL 为 `null` —— 守卫固化该事实，防后人凭空建章节。

**Validates: Requirements 6.3**

## Error Handling

- 幂等脚本 `run_section` 在 `validate_section` 有 errs 时不写文件；`rows=None` 表示不动模板行集。
- 载荷层对缺失层级数据返回 `null` 而非 0；`syncToNote` 在全零时提示「请先填写披露数据」并 return（既有语义保留）。
- 前端 `catch` 保留既有 `ERR_CANCELED` 静默处理。
- 源 xlsx 读取失败时守卫直接 fail（不 fallback）。

## Testing Strategy

- 后端：`fix_note_h5_oil_gas_structure.py --check` + `test_note_h5_oil_gas_structure.py`（结构 + openpyxl 交叉比对 + listed 豁免 + 反向自检）。
- 前端：`h5NoteSubtableContract.spec.ts`（Property 1~8；Property 7 读组件源码并先 `stripComments` 防守卫注释误判，含反向自检）。
- CI：挂 `note-h5-structure` job。
- 实测：soe 项目录入后确认 §八、25 落库 16 行、期末值正确、`text_content` 含补充披露、无周期重复 POST。
