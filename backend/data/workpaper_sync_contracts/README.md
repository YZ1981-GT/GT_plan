# `workpaper_sync_contracts/` —— per-entry 语义契约真源

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure`（Task 13 建目录与 schema，Tasks 36 / 40~57 / 62~64 逐 entry 填内容）

强校验器：`backend/app/services/workpaper_sync/contracts.py`（`parse_contract` / `load_contract`）

## 文件命名

| 形态 | 含义 |
|---|---|
| `{adapter_id}.json` | 生产契约。`contract_id` 必须等于文件名（`adapter_id`），否则注册被拒 |
| `_*.json` / `_*.md` | schema 文档与**候选**示例，不参与 `available_contract_ids()` 的生产清册 |

## 发布顺序（不可颠倒）

```
template → instrumentation → contract → definition bundle → representation
```

- contract payload **单向**引用已发布的 `template_definition_sha256` 与
  `instrumentation_definition_sha256`；
- contract payload **禁止**出现 `bundle_*` / `definition_bundle_*` 前向引用；
- contract payload **禁止**内嵌自身 artifact UUID/hash。`definitions._SELF_REFERENCE_KEYS`
  会递归拒绝裸键 `sha256` / `id` / `artifact_id` 等，所以模板 blob 的哈希字段名必须写
  `template_sha256` 与 `normalized_structure_hash`（这两个名字是 requirements 6.14 / 6.2
  的原文用词），**不能**写 design.md 示例里的 `sha256` / `structure_hash`。

## 顶层字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `schema_version` | ✓ | 固定 `contract-definition:v1` |
| `contract_id` | ✓ | 稳定 key，等于文件名 |
| `semantic_version` | ✓ | 契约语义版本 |
| `review_status` | ✓ | `candidate` \| `reviewed`；只有 `reviewed` 可注册生产 adapter |
| `document_type` | ✓ | `xlsx` \| `docx` |
| `template_definition_sha256` | ✓ | 已发布 template definition 的 digest |
| `instrumentation_definition_sha256` | ✓ | 已发布 instrumentation definition 的 digest |
| `template.relative_path` | ✓ | `backend/wp_templates/` 下的相对路径 |
| `template.template_sha256` | ✓ | 模板 blob 内容哈希 |
| `template.normalized_structure_hash` | ✓ | 规范化结构哈希（与物理 SHA 用途不可混用） |
| `identity_carriers` | ✓ | 逐条必须通过真实 OO 9.4 probe gate（见下） |
| `sheets` | xlsx | `sheets[].tables[].fields[]` |
| `fields` / `repeaters` | docx | 顶层字段与行域字段 |

xlsx 契约不得出现顶层 `fields`/`repeaters`，docx 契约不得出现 `sheets` —— 文档类型串用一律拒绝。

## identity 载体 probe gate（真源，不在代码里复制）

| 文档类型 | 真源 | 节点 |
|---|---|---|
| xlsx | `backend/data/onlyoffice_excel_identity_carrier_contract.json` | `gate_for_downstream_tasks.task_17_instrumentation_definition` |
| docx | `backend/data/onlyoffice_word_sdt_carrier_contract.json` | `downstream_gate` |

当前实测裁决：

- xlsx 载体允许 `hidden_sheet` / `defined_name` / `excel_table` / `hidden_uuid_column`；
  sheet 定位锚点只允许 `defined_name_ref` / `excel_table_sheet_association`，
  `sheet_id` 与 `sheet_display_name` 在 OO 9.4 上 **failed**，禁止使用。
- docx 载体允许 `field_sdt_inline` / `field_sdt_block` / `sdt_external_body` /
  `cell_level_field_sdt_tag_carrying_row_uuid`；**`row_sdt` 在 OO 9.4 上 failed**
  （OO 会把 row 级 SDT 包装整体剥掉），因此 design.md 里
  `repeaters[].row_tag = "gt:row:..."` 的写法**不可用** —— 行身份必须由单元格内
  inline field SDT 的 tag 携带 `{row_uuid}`。锚点只允许 `w_tag`。

## 字段级硬约束

- 每个受管字段必须同时有 `stable_field_key` / `json_pointer` / `mode` / `value_type` /
  `source_ref`；xlsx 还要 `cell`，docx 还要 `sdt_tag`。
- `stable_field_key` 与 `sdt_tag` 必须是 ASCII 稳定 key，**不得含中文 label**。
- 任何 `col_a` / `col_bc` 形态（`^col_[a-z]+$`）的段都被无条件拒绝：那是 generated
  YAML 的无语义列占位，永不可作写格身份。**即使填了 `source_ref` 也不放行。**
- 行域字段的 `json_pointer` 必须含恰好一个 `{row_uuid}`；`cell.row_from` 必须是
  `row_identity`，不得写死行号。
- `row_identity.kind` 只能是 `field` / `template_row_key`；`index` / `ordinal` /
  `position` / `row_number` / `array_index` 一律拒绝。
- `dynamic_columns.identity` 必须恰为 `{slot}_{seq}`。
- `footer_anchor` 只能用 `marker` + `search_column`，不得写行号。
- `mode=formula` 的字段其列必须落在同表 `formula_mask` 覆盖的列跨度内。
- 声明了 `row_identity` 的表必须同时声明 `delete_policy`（`tombstone` / `reject`），反之亦然。
- `header_rows` 取 1..3（两级表头 = 2）。

## 校验方式

```powershell
python -m pytest backend/tests/workpaper_sync/test_task13_contract_registry.py -q
```
