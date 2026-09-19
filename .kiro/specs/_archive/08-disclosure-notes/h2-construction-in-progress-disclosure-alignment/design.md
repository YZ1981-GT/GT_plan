# Design

## Overview

H2 在建工程披露结构对齐分三层协同修订，全部围绕致同源模板 `backend/wp_templates/H/H2 在建工程.xlsx`（运行时权威）：

1. **附注模板层**（后端 `note_template_{listed,soe}.json` §五、23 / §八、23）：用幂等脚本重建两级表头、改名「项  目」→「工程物资」、删 `header_label` 假行、补 `columns`/`guidance`。
2. **前端映射层**（`h2NoteSectionMap.ts` / `h2DisclosureSyncPayload` 或等价 `buildH2SyncPayload`）：补两级 `ColumnDef.group` 列定义、`materials` 子表改名、载荷行键对齐叶子列 key、旧名进 `_removed_table_keys`。
3. **守卫层**：前端契约 `h2NoteSubtableContract.spec.ts`（复用共享 `_disclosureSubtableContract.helper`）+ 后端 `test_note_h2_construction_structure.py`（openpyxl 直读源 xlsx tab 名/表头交叉比对 + 反向自检）+ CI job。

不触碰四表取数（`_h2_construction_in_progress.py` 逻辑与灰度默认值）与已上线的同步触发机制。

## Architecture

两级表头唯一机制（平台既有，不新造）：`ColumnDef.group`（前端） / `columns[].group`（附注模板 JSON） → 后端 `note_sub_table_projector._extract_column_groups` 派生 `_column_groups`（`{group,start,span}` 扁平结构，`start` 为 headers 下标，标签列占 0）→ 消费方 `DisclosureEditor.activeTableColumns`（嵌套 el-table-column）+ `note_word_exporter._build_two_level_header_rows`。

`_extract_column_groups` 三态：`None`=未声明（回退 `_infer_groups_from_headers` 前缀推断）/ `[]`=任一列带 `flat` 即显式单级 / 非空=显式分组。→ 单行表头表必须显式 `flat`，两级表头表用 `group`。

附注模板修订走共享 `backend/scripts/fix/_note_structure_kit.py`（`flat_columns` / `grouped_columns` / `two_period_columns` / `rule` / `apply_plan` / `validate_section` / `run_section` / `build_cli`），沿用 D1/D6/H1 范式：幂等 `--dry-run`/`--check`、`_aligned_by` 戳记、`drop_tables` 清垃圾名、`titleize_text_sections` 兜底。

## Components and Interfaces

### 后端

- `backend/scripts/fix/fix_note_h2_construction_structure.py`（新建）：
  - listed §五、23 plan：6 表（summary flat / detail 两级 / projectMovement flat / projectCont flat / impairment flat / materials 改名 flat）；drops=["项  目"]（迁移后）；detail rows 去 header_label。
  - soe §八、23 plan：4 表（summary 两级 / detail 两级 / projectMovement flat / impairment flat）。
  - `two_period_columns(label=("label","项目"), groups=("期末余额","上年年末余额"|"期初余额"), subs=[("book","账面余额",AMOUNT),("impairment","减值准备",AMOUNT),("net"|"value","账面净值"|"账面价值",AMOUNT)])`。
- `backend/tests/test_note_h2_construction_structure.py`（新建）：`--check` 无欠账 / 表数表名 / 两级分组自洽 / flat 表态 / columns key 与前端一致 / openpyxl 读源 xlsx `附注披露信息（上市公司|国有企业）` tab 名与关键表头（账面余额/减值准备/账面净值|账面价值）交叉比对 / 反向自检。
- 灰度与取数逻辑不变。

### 前端

- `h2NoteSectionMap.ts`：`H2_LISTED_SUBTABLE.materials` 「项  目」→「工程物资」；新增/修订两级列定义 `buildH2ListedColumns` / `H2_SOE_COLUMNS`（detail/summary 用 `group`）。
- `buildH2SyncPayload`：detail/summary 行对象改用叶子列 key（`end_book`/`end_impairment`/`end_net`|`end_value`/`prior_*`）；`_removed_table_keys` 含旧名「项  目」。
- `h2NoteSubtableContract.spec.ts`（新建）：复用 `_disclosureSubtableContract.helper` 的 P1~P6 + H2 专属（两级分组、materials 改名、无「项  目」残留）。

## Data Models

两级列定义（TypeScript / JSON 同构）：

```
在建工程明细（listed，7 列）:
  { key: label,          label: 项目,      is_label: true }
  { key: end_book,       label: 账面余额,  group: 期末余额,     format: amount }
  { key: end_impairment, label: 减值准备,  group: 期末余额,     format: amount }
  { key: end_net,        label: 账面净值,  group: 期末余额,     format: amount }
  { key: prior_book,     label: 账面余额,  group: 上年年末余额, format: amount }
  { key: prior_impairment,label: 减值准备, group: 上年年末余额, format: amount }
  { key: prior_net,      label: 账面净值,  group: 上年年末余额, format: amount }

在建工程 / （1）在建工程情况（soe，7 列）:
  同上，但两组为「期末余额」/「期初余额」，末子列为「账面价值」(key: end_value / prior_value)。
```

单级表（flat）列 key 沿用既有同步载荷键（实现时读 `buildH2SyncPayload` 对齐，禁反向改载荷键——它是 columns-coverage 已验证真源）。

`_removed_table_keys`：`["项  目"]`（materials 旧名），仅在推送时上报，避免附注永久残留孤儿空表。

## Correctness Properties

### Property 1: 两级表头叶子列与源模板一致

*For any* H2 附注两级表（上市在建工程明细 / 国企在建工程汇总 / 国企在建工程情况），其 columns 叶子列名序列 SHALL 等于源 xlsx 第二行表头（账面余额/减值准备/账面净值|账面价值），且分组名等于第一行跨列表头（期末余额 / 上年年末余额|期初余额）。

**Validates: Requirements 1.1, 1.2, 4.1**

### Property 2: 分组结构自洽

*For any* 两级表，`_column_groups` SHALL 由 columns.group 派生（相邻同名合并、`start≥1`、`start+span≤len(headers)`），且 `group` 不含 `/`；单级表 SHALL 无 `_column_groups` 且至少一列标 `flat`。

**Validates: Requirements 1.3, 1.4**

### Property 3: 表名与前端映射一致且无孤儿

*For any* §五、23 / §八、23 表，其 `name` SHALL 存在于前端 `H2_*_SUBTABLE` 值集合，反之前端每个子表名 SHALL 逐字命中附注模板某表名；「项  目」SHALL 不出现在任一侧。

**Validates: Requirements 2.1, 2.3, 4.3**

### Property 4: columns[0] 对齐 headers[0] 且 key 不漂移

*For any* 表，`columns[0].label == headers[0]` 且首列 `is_label`；`columns[].key` 序列 SHALL 等于前端同步载荷该表列 key 序列。

**Validates: Requirements 3.1, 3.3, 4.2**

### Property 5: 幂等与零回归

*For any* 连续两次运行 `fix_note_h2_construction_structure.py`，第二次 SHALL 为空操作（幂等）；运行后附注 JSON SHALL 可解析且 §五、23 / §八、23 之外的章节字节不变。

**Validates: Requirements 5.2, 5.3**

### Property 6: 假数据行与 guidance

*For any* §五、23 / §八、23 表，SHALL 无 `row_type: header_label` 行，且每表 `guidance` 非空。

**Validates: Requirements 2.2, 3.2**

## Error Handling

- 幂等脚本 `apply_plan` 找不到目标表时只 `warning` 不插入（除非 `insert=True`），避免误伤他 spec 的表；表名迁移目标已被占用时跳过并告警。
- `run_section` 在 `validate_section` 有 errs 时**不写文件**（校验失败即中止落盘），保证坏结构不被持久化。
- 前端同步 `catch` 静默吞 409（跨主体类型）沿用平台既有语义；缺 `projectId` 由平台守卫拦截。
- 源 xlsx 读取失败时守卫测试直接 fail（不 fallback），确保结构确权基于真源。

## Testing Strategy

- 后端：`fix_note_h2_construction_structure.py --check`（幂等 0 欠账）+ `test_note_h2_construction_structure.py`（表数/表名/两级/flat/columns-key/openpyxl 交叉比对/反向自检）。
- 前端：`h2NoteSubtableContract.spec.ts`（共享 helper P1~P6 + H2 专属两级/改名/无孤儿 + 反向自检）。
- 集成：CI job `note-h2-structure` 跑 `--check` + 两侧守卫。
- 实测：chrome-devtools/playwright 驱动两 Tab 推送 + postgres 只读验证落库两级表头、`_last_sync_at` 前移、无「项  目」孤儿表。
