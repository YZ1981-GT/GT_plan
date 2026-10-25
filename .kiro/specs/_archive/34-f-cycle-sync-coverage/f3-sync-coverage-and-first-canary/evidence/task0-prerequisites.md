# Task 0 前置依赖核查（F3 / F4 / F5 三 spec 共用主证据）

**执行**：2026-09-26　**基线**：工作树（HEAD `07eb3fb75` + 并发会话 WIP）
**范围**：F3/F4/F5 三份 spec 的 Task 0 共同前置；F4/F5 的 `evidence/task0-prerequisites.md` 引用本文件并只补各自特有项。

🔴 **核查基线说明**：spec 的 Task 0 原文要求 `git show HEAD:`，但实测发现工作树有并发会话的大量 WIP
（含框架层 `phase5_row_table_sheet.py` / `merge.py` / `excel_extract.py` / `excel_materialize.py`），
实施必须在工作树上跑测试 ⇒ 本核查以**工作树**为准，并对每项标注该能力是否来自 WIP。

## 1. 框架层 `RowTableSheetSpec`（✅ 已支持）

`backend/app/services/workpaper_sync/phase5_row_table_sheet.py:100-165`（dataclass frozen）。
字段清单（逐字实测，**与 spec 描述有两处命名差异**）：

| 字段 | 默认值 | 备注 |
|---|---|---|
| `managed_sheet` / `sheet_key` / `table_key` / `template_id` / `table_name` | 必填 | — |
| `uuid_col` | 必填 | 🔴 字段名是 `uuid_col`，**不是** spec 受管区清单表头写的 `uuid_column` |
| `first_data_row` / `last_data_row` / `footer_row` | 必填 | — |
| `header_row` / `header_group_row` / `header_leaf_row` | `None` | 两级表头用后两个 |
| `binding_kind` | `BindingKind.excel_table` | — |
| `defined_name` | `""` | 仅 `static_region` |
| `store_item_id` / `empty_payload` | `""` / `"[]"` | — |
| `row_identity_key` | `"rowId"` | 三形态：`rowId` / 稳定 key / `""`(static_region) |
| `store_kind` | `StoreKind.rows` | — |
| `field_specs` | `()` | 🔴 **7 元组** `(column_key, column, mode, value_type, json_key, header_text, group_header_cell)` |
| `formula_columns` / `formula_templates` | `()` / `{}` | — |
| `aging_layout` / `aging_groups` | `None` / `()` | nested / flat 两形态 |
| `footer_marker` | `"合计"` | 🔴 含空格的 marker 须逐字传（F3-2/F3-4「合␠␠计」） |
| `footer_carries_total_formula` | `True` | 见 §2 |
| `error_label` | `""` | — |
| `html_only_item_ids` | `()` | D4-5 范式 |
| `ghost_row_anchor_index` | `0` | 首字段不适合当锚点时传 1（D5/D6 先例） |

`formula_mask` 是 **property**（L168-176），现算 `tuple(f"{col}{first}:{col}{last}" for col in formula_columns)`
⇒ 矩形。**F3-H4 拆两个 spec 的裁决前提成立**：F3-1 的 R7/R8（6 公式列）与 R9/R10（2 公式列）
若合成一个 spec，R9/R10 的 B/F/G/H 会被矩形 mask 误标 formula。

## 2. 锚行 footer（`footer_carries_total_formula=False`）（✅ 已支持，有生产先例）

声明位 L152；docstring 明写 D3-4 段② 是首例。磁盘契约实证
（`backend/data/workpaper_sync_contracts/d3.prepaid_receipts_detail.json`）：

```
d34-managed | analysis_credit_rows | carries_total_formula: False | marker: '差异合理性分析'
```

⇒ F5-8（R30「三、审计说明」）与 F5-7（R32 同）的锚行处置**可直接用**，无需框架层改动。
`spec_to_contract_sheet_payload` 把它写进 `footer_anchor.carries_total_formula`（L~250）。

## 3. 兄弟 Table ref 位移（✅ 已支持，双区生产先例）

| 能力 | 位置 |
|---|---|
| 同 sheet 多 table 绑定装配 | `phase5_row_table_sheet.attach_sibling_bindings:474` |
| 兄弟 Table ref 位移 | `excel_materialize._shift_sibling_table_refs:2566` |
| 受管 table ref 扩张 | `excel_materialize._grow_managed_table_ref:2631` |
| 位移后 footer 门 | `excel_materialize.assert_shifted_footer_gates:2474` |
| 行位移计划 | `excel_materialize._plan_row_shift:2119` |
| 区间字符串扩张 | `excel_materialize._grow_range_string:2942` |

生产先例（D3 磁盘契约同 sheet 两 table）：
- `d34-managed`：`analysis_debit_rows`(anchor A10, uuid_col J) + `analysis_credit_rows`(A10, uuid_col K)
- `d37-managed`：`voucher_check_current_rows`(A15, uuid_col R) + `voucher_check_post_rows`(A29, uuid_col S)

🔴 同 sheet 多区靠 **`uuid_col` 配对** spec↔table（`spec_to_contract_sheet_payload` L~255 注释：
「同 sheet 双区配对键：`_table_for` 在同一 sheet_key 下有多个 table 时，用 `uuid_col` 把 spec 与 table 一一配对。
缺它 → 匹配 0 张 → ProviderCapabilityError」）。

⇒ **F3-7 三区必须三个不同的 `uuid_col`**。但 F3 spec 受管区清单把三区的 UUID 列都写成 **S**（同一列）
⇒ 按上述配对机制会匹配失败。同理 F4-7 五区都写 **L**、F4-8 两区都写 **S**、F4-1 两区都写 **M**。
🔴 **这是三份 spec 的共同事实缺陷**，Task 2 须为每个同 sheet 多区逐区实测独立空列（D3-4 的 J/K、D3-7 的 R/S 即此范式）。

## 4. nested json 路径（dict ✅ / **数组下标 🔴 不支持**）

- `resolve_json_path:328`：逐段 `cursor.get(segment)`，`if not isinstance(cursor, Mapping): return None`
- `set_json_path:341`：逐段建 dict，`if not isinstance(nxt, dict): nxt = {}; cursor[seg] = nxt`

dict 形态（D3/D7 账龄 `agingPrior/within1`）✅ 已支持并有生产用例。

🔴 **F5-2 的 `months[12]` 是数组，两个函数都不支持**：
- 投影：`resolve_json_path(row, "months/0")` → `cursor = row["months"]` 是 `list` → `isinstance(list, Mapping)` False → 返回 `None` ⇒ **投影恒空**
- 合并：`set_json_path(row, "months/0", v)` → `nxt = cursor.get("months")` 是 `list` → 不是 `dict` → **被替换成 `{}`** ⇒ 12 个月数据全丢

⇒ **F5 裁决 F5-H5 的事实前提错误**。spec 原文写「引擎 `resolve_json_path` 支持，D4-2 / D3 账龄组同机制」——
D3 账龄组是 nested **dict**，不是数组下标；D4-2 亦然（已核 D4 契约无数组下标 json_key）。
处置见 F5 evidence §补-1（框架层加 list 索引分支，零回归门钉住 dict 行为不变）。

## 5. `merge` 保护与数值规范化（✅ 保护已支持 / 🔴 百分比换算无）

- `merge.py:115` 导入 `PROTECTED_MODES`（来自 `contracts`）
- `merge.py:457` `_DECIMAL_TYPES: Final[frozenset[ValueType]]`；`:513` `if value_type in _DECIMAL_TYPES:` 只做 Decimal 规范化
- 全文件 **零** `percent` 字样 ⇒ **FC-10 所需的 `value_type=percent_points`（投影 ÷100 / 合并 ×100）确实不存在**

⇒ F3 的 FC-10 四列（F3-2 J/U、F3-4 G、F3-5 I）在换算落地前**必须**判 HTML-only（需求 3.3 / 4.3 成立）。
F4（红基线 B6）/ F5（B6）初判「FC-10 不命中」须由各自 Task 2 逐列取证后才可采信。

## 6. 模板覆盖层（✅ 已交付，可用）

- spec `.kiro/specs/excel-template-override-layer-and-onlyoffice-template-editor/tasks.md`：**25 done / 0 todo**
- 运行时 API `backend/app/services/wp_template_override.py`：`stage_override:642` / `activate_staged_override:725` /
  `resolve_template:446` / `resolve_all_templates:470` / `prepare_template_edit_session:1003` /
  `commit_template_edit_session:1083` / `record_override_version:1322` / `promote_override_version:1402`
- 守卫：`assert_override_root_disjoint_from_authoritative:180`（覆盖层与 `backend/wp_templates/` 物理隔离）
- 覆盖粒度 = **整文件副本**（不是格级 patch）⇒ 改 F5-7!G31 的方式是「以权威模板为基底、改该格公式、存为覆盖文件」

⇒ **F5-7!G31（裁决 F5-H2）默认方向①可用**，不必退备选②。
⇒ F3-4 应计利息（裁决 F3-H2）的方向②技术上也可用，但它是**口径变更**需业务确认，仍按默认③。

## 7. D3 provider 范式（✅ 完整，F3/F4/F5 照抄基准）

`backend/app/services/workpaper_sync/phase5_d3_prepaid_receipts.py`：

| 构件 | 行号 | 要点 |
|---|---|---|
| `EntrySelectionError` / `StorePayloadError` | 73 / 79 | `error_code` 各 entry 独立 |
| 冻结常量 | 95-120 | `PHASE5_WAVE` / `ENTRY_ID` / `ADAPTER_ID` / `WP_CODES`(幻影码) / `EXPECTED_PROFILE_ID` / `TEMPLATE_RELATIVE_PATH` / `TEMPLATE_SHA256` |
| `read_authoritative_template` | 272 | sha 哨兵不符即抛 |
| `assert_no_implicit_template_fallback` | 296 | 幻影码在 finder 零命中 + 父码落权威模板 |
| `assert_entry_selectable(*, resolution, manifest=None)` | 322 | 🔴 **无关闭开关**；校 document_type / independent_entry / profile_id / wp_code_patterns == WP_CODES，末尾调 fallback 判据 |
| `instrumentation_spec` / `instrumentation_specs`(复数) | 359 / 383 | 复数走 `build_instrumentation_payload_for_sheets` |
| `build_contract_payload` | 622 | — |
| `assert_contract_file_matches_source` | 680 | 磁盘 vs 现算 digest 比对 + `parse_contract` |
| `publish_definitions` | 770 | 五个 definition + bundle，含 template/instrumentation digest 单向引用校验 |
| `build_matcher` | 850 | `EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)` |
| `build_registration` | 854 | 🔴 `matcher=build_matcher()` + `declared_capability=Capability.bidirectional` + `contract=… or load_contract_from_disk()`（字段名**不是** `adapter_id`/`entry_matcher`） |
| `attach_adapters` | 916 | 前置 `manifest_capability_enabled()` + `resolve_visible_current_representation_id` |
| `assert_manifest_capability_enabled` | 983 | capability 必须已是 bidirectional 且 adapter_id 匹配 |
| 别名 | 末尾 | `publish_pilot_definitions = publish_definitions` / `attach_pilot_adapters = attach_adapters` |

sheet 层薄声明范式：`phase5_d3_06_related_party.py`（**无 `def` / 无 `class`**，只有 `Final` 常量 + 一个
`RowTableSheetSpec` 实例 + `__all__`）。F3-6 / F4-6 与它同型（单级表头 + 1 公式列 + footer 合计 + `rowId`）。

多 sheet 灰度开关范式：`phase5_d3_expansion.py:75-116`（`_INCLUDE_D3xx: Final[bool]`）+
`managed_row_table_specs:149` / `instrumentation_specs:180` / `all_store_item_ids:192` /
`all_managed_sheet_names:294` / `assert_specs_align_with_contract_sheets:316`。

## 8. 契约发布链五环与登记点

| 环 | 实现 | 状态 |
|---|---|---|
| ① 生成器 `--apply` | `backend/scripts/gen/generate_phase5_{d1,d3,d4,d5,d6,d7,e1}_contract.py`（7 个范式） | ✅ 可照抄；F3/F4/F5 三个待建 |
| ② `assert_contract_file_matches_source` | provider 内（D3:680） | ✅ |
| ③ approved bundle → **published representation** | `projection_first_publication` / `projection_provisioning` | 🔴 **缺供给**（见下） |
| ④ `working_paper_sync_entry_state` | 同上 | 🔴 F 循环 0 行 |
| ⑤ `register_from_manifest()` | `adapters/registry.py` | ✅ 代码在，但需 ③④ 先成立 |

🔴 **第③环缺供给（BP-61-1）已由 slice 实证**：`backend/data/workpaper_sync_f_cycle_manifest_slice.json`
三条 entry 的 `published_representation` 全为 **`null`**，且 `authority_model` / `definition_bundle` /
`instrumentation_candidate` / `adapter_id` 亦全为 `null`（五个 null 供给位）。
`capability_target_blocked_by` 逐元素实测：

| entry | 实测值 |
|---|---|
| `xlsx/gt-f3-notes-payable` | `["BP-1","BP-2","BP-3","BP-4"]` |
| `xlsx/gt-f4-accounts-payable` | `["BP-1","BP-2","BP-3","BP-4"]` |
| `xlsx/gt-f5-cost-of-sales` | `["BP-1","BP-2","BP-3","BP-4","BP-7"]`（🔴 含 BP-7，**不含 BP-5**——BP-5 是 F2 专属） |

⇒ 三份 spec 标 `[ ]*` 的发布链任务（F3 T9 / F4 T8 / F5 T9）确认为**真实外部阻塞**，按 spec 要求如实登记 `upstream_gap`。

登记点真实位置（`DELIVERED_PER_ENTRY_CONTRACTS` / `_ALLOWED_PROVIDER_MODULES` 各 5 处生产定义/消费）：

| 登记点 | 文件 |
|---|---|
| `DELIVERED_PER_ENTRY_CONTRACTS` | `adapters/registry.py:970` · `projection_first_publication.py:126` · `projection_lane_registry.py:212` · `projection_provisioning.py:259` · `store_projection_response.py:57` |
| `_ALLOWED_PROVIDER_MODULES` | `adapters/registry.py:1395` · `projection_first_publication.py:664` · `projection_lane_registry.py:1026` · `projection_provisioning.py:260` · `store_projection_response.py:65` |
| golden digest | `backend/scripts/check/check_sync_provider_golden_digest.py` + `_sync_provider_golden_digest.json` |
| overlay | `backend/data/workpaper_sync_entry_overlay.json` |
| wp_code 裁决 | `backend/data/workpaper_sync_entry_wp_code_adjudication.json` |

## 9. FC-11 根因（🔴 实测比 spec 记载多一处）

`backend/scripts/fix/fix_f_cycle_prefill_presets.py`：

```python
# L406-414  _ensure_block（新建块时）
new_block = { ..., "items": [] }          # 🔴 根因之二：新建块直接就叫 items

# L417-432  _ensure_cells
items_key = "items" if "items" in block else "cells"
if items_key not in block:
    block["items"] = []                    # 🔴 根因之一（spec 记的 L418-423）
    items_key = "items"
```

⇒ spec F3 需求 7.2③ 只点了 `_ensure_cells`，**漏了 `new_block`**。只修前者的话，新增块仍会造 `items`。
本 spec Task 17 两处一起修。

prefill 现状实测（`convert_prefill_presets()` 现算，`app.services.formula_management.preset_library`）：

```
workpaper:F0=2  F1=33  F2=78  F3=18  F4=18      F5 缺席（'workpaper:F5' not in counter）
```

`prefill_formula_mapping.json`（308 个 mapping 块）中 `cells` 为空的块共 **11 个**，分两类：

| 类 | 块 | 说明 |
|---|---|---|
| items 型（7 个，spec 已记） | `[222]`F3 上市 · `[223]`F3 国企(全角) · `[224]`F4 上市 · `[225]`F4 国企(全角) · `[226]`F5(14 条) · `[306]`F3 国企(半角) · `[307]`F4 国企(半角) | `cells: []` + `items` 非空 |
| 空块（4 个，🔴 spec 未记） | `[171]`J1`明细表J1-2␠` · `[179]`K1`明细表K1-2` · `[185]`K3`明细表K3-2` · `[195]`M2`明细表（非上市公司）M2-2` | `cells` 与 `items` **都空** |

⇒ 新增的 `--check` 校验「块 `cells` 非空」会连带打红这 4 个空块（非 F 循环）。处置：校验按 wp_code 限定
F 循环，或对空块单独登记豁免并移交对应循环 spec —— 本 spec Task 17 取前者（只校 F 循环块），
4 个空块如实登记为顺带发现。

## 10. 🔴 顺带发现：F1/F2 并发实施中，且 F1 的 `build_contract_payload` 过不了 `parse_contract`

工作树未跟踪新文件（`git status --porcelain`，🔴 注意 `rtk git status` 压缩输出时会省略部分行，
精确解析必须用原生命令）：

```
?? backend/app/services/workpaper_sync/phase5_f1_prepayment.py      682 行
?? backend/tests/workpaper_sync/test_f1_property1_5_entry_selectable.py
?? backend/tests/workpaper_sync/test_f1_property2_3_store_item_id_and_triad.py
?? backend/tests/workpaper_sync/test_f1_property6_9_formula_caliber_and_preset.py
?? backend/tests/workpaper_sync/test_f1_property13_14_golden_digest_and_tb_gate.py
?? backend/tests/workpaper_sync/test_f2_p2_rg3_matcher_overlap.py
```

F1 四个测试文件现算 `4 failed / 20 passed / 5 xfailed`，4 个 failed 全是 **XPASS(strict)**
（标 xfail 理由「phase5_f1_prepayment 尚未创建」但 provider 已建 ⇒ 实际通过）。

🔴 **F1 provider 的契约装配现在不可用**（实测）：

```
>>> parse_contract(phase5_f1_prepayment.build_contract_payload(), adapter_id="f1.prepayment_detail")
ContractSchemaError: contract[f1.prepayment_detail].sheets[f16-managed].tables[related_party_rows]:
                     table anchor 必须是 A1 单元格，实得 None
```

根因：F1 手写了 `_rows_table_payload`（L329-360），产出 `{table_key, table_name, row_identity:{store_key,column,hidden}, fields:[{stable_field_key, column, mode, value_type, json_key, header_text}], formula_mask, footer:{row_marker, carries_total_formula}}`，
缺 `anchor` / `header_rows` / `delete_policy` / `row_identity.json_pointer` / 字段的 `json_pointer`+`cell`+`source_ref`+`header_source_ref`+`store_item_id`，且 `stable_field_key` 只给了 `column_key` 而非
`{table_key}/{row_uuid}/{column_key}` 全量键。

而框架层 `phase5_row_table_sheet.spec_to_contract_sheet_payload:261` 产出的结构与 D1~D7 七家磁盘契约
逐字段一致（实测 D3-6 输出含 `anchor: "A11"` / `header_rows: 1` / `row_identity.json_pointer: "/rows/*/rowId"` /
`delete_policy: "tombstone"` / `uuid_col: "K"` / 完整 `source_ref`）。

⇒ **裁决：F3/F4/F5 三个 provider 一律用框架层 `spec_to_contract_sheet_payload`，不照抄 F1 的手写版本。**
F1 的该缺陷登记移交 `f1-sync-coverage-and-first-canary`（其 Task 9 发布链一跑就会撞上）。

## 11. 结论：本批可做 / 受阻清单

| 项 | 判定 |
|---|---|
| provider 从零建 + sheet 薄声明 + 红判据 | ✅ 可做（新增文件，与并发会话零冲突） |
| 契约装配（走框架层 payload）+ 生成器 | ✅ 可做 |
| F3-7 三区 / F4-7 五区 / F4-8 双区 / F4-1 两区 | ✅ 能力就绪，但 🔴 须先修 spec 的 `uuid_col` 同列缺陷（§3） |
| F5-7 / F5-8 锚行 footer | ✅ 可做 |
| F5-7!G31 覆盖层修复 | ✅ 可做（覆盖层已交付） |
| FC-11 工具链根因 + 三份数据迁移 | ✅ 可做（两处根因，§9） |
| F5 BP-7 三处修复 | ✅ 可做（三个 composable 均不在并发会话改动列表） |
| F5-2 `months` nested 数组 | 🔴 需框架层新增 list 索引支持（§4） |
| FC-10 四列受管（F3） | 🔴 需 `percent_points` 换算，本批按 spec 判 HTML-only |
| 发布链 ③④⑤ 环 + adapter 注册 + 全部真栈验收 | 🔴 BP-61-1 外部阻塞，如实 `upstream_gap` |
| manifest / overlay / golden digest 登记点改动 | ⚠️ 与并发会话高冲突面，放在最后且逐文件重读后增量改 |
