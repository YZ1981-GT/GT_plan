# Task 13 证据：D3-1 审定表 `AdjudicationSheetSpec` 声明

**日期**：2026-09-26　**范围**：阶段 4 声明任务（只落声明 + Property 6 判据，不翻灰度开关、
不重生成契约、不接四态状态机——接入验收是 Task 14）　**方法**：openpyxl 直读权威模板复核
+ 现算 mask + pytest 判据。全程离线，未连库、未改任何引擎/框架层/模板文件。

---

## 一、openpyxl 实测复核结论（裁决 F3：不得只信 evidence 转述，自己读一遍模板）

一次性探针脚本 `backend/_tmp_d3_01_probe.py`（用完即删，按仓库规约不留存）直读
`backend/wp_templates/D/D3 预收账款.xlsx` 的 `审定表D3-1` sheet（`data_only=False`），
复算结论与 Task 1 evidence（`task1-sheet-morphology-and-geometry.md`）逐项一致：

| 项 | 实测复核值 | Task 1 在案值 | 一致性 |
|---|---|---|---|
| sheet 真名 | `审定表D3-1` | `审定表D3-1` | ✅ |
| 行×列 | 30 行 × 12 列（A1:L30） | 30×12 | ✅ |
| 公式数 | 88 | 88 | ✅ |
| Excel Table | 无 ⇒ 走 `AdjudicationSheetSpec` | 无 | ✅ |
| 区块数 | **2**（性质分类 + 账龄分类） | 2 | ✅ |
| 区1 表头 | 行 6-7（B6=期初数/F6=期末数/J6=比较/L6=原因分析；B7-K7 子表头） | 6-7 | ✅ |
| 区1 数据行 | **8-12**（A8-A11 四项固定标签，A12 无标签占位第 5 行） | 8-12 | ✅ |
| 区1 合计行 | **13**（`B13=SUM(B8:B12)`，SUM 区间覆盖 5 行含占位） | 13 | ✅ |
| 区2 表头 | 行 15-16 | 15-16 | ✅ |
| 区2 数据行 | **17-20**（A17-A20 与前端 AGING_ROWS 4 项逐字对应） | 17-20 | ✅ |
| 区2 合计行 | **21**（`B21=SUM(B17:B20)`） | 21 | ✅ |
| 调节行 | 行 22 `A22='试算平衡表数'` / 行 23 `A23='差异数'`（`E23=E21-E22`,`I23=I21-I22`，**只对账龄区做差异**） | 22/23 | ✅ |
| note 区 | A25『1.审计说明：』/ A26 / A30（footer 之下，HTML-only 候选） | A25/A26/A30 | ✅ |

**🔴 裁决 F3 关键结论**：D3-1 是**两区块**（nature/aging），**不是** D1-1 的 3 区
（gross/bd/net），也**不是** D2-1 的 1 区写死 4 行。区1「模板 5 行 vs 前端 4 项」的落差在
`last_data_row=12` + subtotal SUM 区间 8:12 里如实处理。

### 逐格公式分布（实测，供 mask 现算依据）

- 表头底稿目录引用格（6 个，**不计入受管 mask**）：A3/E3/H3/A4/E4/H4（`=底稿目录!...`）
- 区1 数据行 8-11：每行 B/C/D 跨 sheet SUMIF（引用 D3-2）+ E=B+C+D + F/G/H SUMIF + I=F+G+H
  + J=I-E + K=IF ⇒ 每行 10 公式格（B..K）
- 区1 占位行 12：仅 E/I/J/K（B12/C12/D12/F12/G12/H12 为空，无 SUMIF）
- 区1 合计行 13：B/C/D/E/F/G/H/I 为 SUM + J=I-E + K=IF（10 格）
- 区2 数据行 17-20：仅 E/I/J/K（🔴 账龄区无跨 sheet SUMIF，B/C/D/F/G/H 是手工空格）
- 区2 合计行 21：B..J 为 SUM + K=IF（10 格）
- 差异行 23：E23/I23 两格（🔴 只有 E/I，只对账龄区合计做差异）

**公式合计核对**：`4×10（区1 8-11）+ 4（占位 12）+ 10（区1 合计 13）+ 4×4（区2 17-20）
+ 10（区2 合计 21）+ 2（差异 23）= 82` 受管公式格 + 6 个表头底稿目录引用 = **88** ✅。

---

## 二、前端 store 键模型复核（`useD3Adjudication.ts` 逐字实测）

- per-cell 键：`makeItemId(section, rowKey, field)` → `D3-adj-${section}-${rowKey}-${field}`，
  `section ∈ {nature, aging}`（🔴 **不是** `by-nature`/`by-aging`——后者是 `sectionKey`
  展示用；`makeItemId` 与 `updateCell` 里用的都是 `nature`/`aging`）。
- `NATURE_ROWS` 4 项（派生自 `D3_NATURE_CATEGORIES`）；`AGING_ROWS` 4 项
  + `LEGACY_AGING_ROWKEY` 动态段兼容映射。
- field：`priorUnadjusted`/`priorAje`/`priorRje`/`currentUnadjusted`/`currentAje`/`currentRje`/
  `reasonAnalysis`（`audited`/`change` 是 computed 不落库）。
- 三个 note item：`D3-adj-note-aging-reason`/`-change-analysis`/`-conclusion`（HTML-only）。
- 一个 TB 种子：`D3-adj-trial-balance-amount`。
- 值来源：`currentUnadjusted` 跨 sheet（D3-2 SUMIF 聚合，`crossSheetCurrent !== 0` 优先，
  否则手工）；`prior*` 手工；`audited`/`change` computed。

---

## 三、新建文件

1. `backend/app/services/workpaper_sync/phase5_d3_01_adjudication.py`
   - 导出 `SPEC_D301` + `MANAGED_SHEET_D301`（+ `SHEET_KEY_D301`/`TEMPLATE_ID_D301` 供测试用）
   - `managed_sheet="审定表D3-1"`（实测真名）
   - 两个 `AdjudicationSection`：`nature`（数据 8-12 / 合计 13）/ `aging`（数据 17-20 / 合计 21），
     `uuid_col=""`（固定行不需 UUID，同 D1-1）
   - `row_mode=AdjudicationRowMode.fixed_rows`
   - `total_row=21`（=账龄区小计）/ `tb_row=22` / `diff_row=23` / `footer_marker="合计"`
   - `per_cell_key_template="D3-adj-{section}-{slug}-{field}"`（框架层占位符 `{slug}`，与前端
     `{rowKey}` 对齐——读 D1-1 范式确认框架层用 `{slug}`）
   - `field_specs`：A=item_name(editable/text)、B-K 列级 formula、L=reason_analysis(editable/text)
   - `cell_mask`：`_build_cell_mask()` 现算 82 格（**不手写字面量**，Property 5 纪律）
   - `value_sources`：`current_unadjusted=cross_sheet`、`*_audited`/`change_*=computed`、其余 manual
   - `html_only_item_ids`：三个 note item + TB 种子

2. `backend/tests/workpaper_sync/test_d3_01_adjudication_spec.py`（Property 6 判据 + 变异必红）

**未改动**：任何引擎/框架层（`phase5_adjudication_sheet.py`、`excel_*`、materialize、extract）、
模板文件、灰度开关、契约。**零 `if is_d3` 分支。**

---

## 四、Property 6 判据运行结果（含变异必红证明）

```
python -m pytest tests/workpaper_sync/test_d3_01_adjudication_spec.py -v --tb=short
⇒ 15 passed
```

判据清单：
- `test_d3_01_has_exactly_two_sections` —— 区块数 == 2（非 D1-1 的 3、非 D2-1 的 1）
- `test_d3_01_section_keys_match_frontend_tokens` —— `["nature","aging"]`，反证不含 gross/bd/net
- `test_d3_01_nature_section_geometry_matches_template` —— 区1 数据 8-12 / 合计 13 / uuid_col=""
- `test_d3_01_aging_section_geometry_matches_template` —— 区2 数据 17-20 / 合计 21
- `test_d3_01_row_mode_is_fixed_rows`
- `test_d3_01_footer_rows_match_template` —— total 21 / tb 22 / diff 23
- `test_d3_01_data_and_computed_rows` —— data (8-12,17-20) / computed (13,21,22,23)
- `test_d3_01_cell_mask_is_cell_level_and_matches_measured_formulas` —— mask 82 格 + 区2 手工列不落 mask
- `test_d3_01_editable_data_cells_not_masked` —— A/L 不入 mask（fail-closed 纪律）
- `test_d3_01_cell_mask_is_engine_style_not_hardcoded_literal` —— 现算 == spec.masked_cells
- `test_d3_01_value_sources_and_oo_writable_discipline` —— cross_sheet/computed 派生格不可 OO 直写
- `test_d3_01_html_only_note_items_registered`
- `test_d3_01_per_cell_key_template_aligns_frontend`
- **`test_mutation_d1_style_three_sections_is_detected`** —— 变异体（3 区 gross/bd/net）区块数/键/
  几何全部与 D3-1 实测不符
- **`test_mutation_run_real_geometry_asserts_would_fail`** —— 把真声明的几何断言对变异体逐条跑，
  `pytest.raises(AssertionError)` 确认三条断言（两区/nature-aging 键/账龄区 last_data_row=20）
  **对变异体全部抛**，对真声明全部过 ⇒ 变异必红的可执行证明。

**⇒ Property 6（`sections`/`row_mode` 与模板实测几何一致；变异改成 D1-1 的 3 区必红）成立。**

---

## 五、零回归结论

1. **golden digest 零回归**：`python scripts/check/check_sync_provider_golden_digest.py`
   ⇒ `✅ golden digest 零回归：87 个 digest 逐个不变`。本声明未接入任何契约/注册表（不翻灰度
   开关，同 Task 6/8/9/11「只声明不翻开关」模式），故 87 基线全不变。
2. **D3 property + 扩容 + 框架层判据零回归**：
   `test_d3_property2_store_item_id_exact_match.py` / `test_d3_property3_4_dual_zone_baseline.py`
   / `test_d3_expansion.py` / `test_adjudication_sheet_spec.py` / `test_phase5_adjudication_sheet.py`
   ⇒ **64 passed**。

---

## 六、已知基线红核对（任务原文列出，勿归因给本任务）

- `test_task5_d3_performance_baseline::test_real_registration_path_fails_before_reaching_d3`
  ⇒ 复跑确认仍红（`DID NOT RAISE ...RegistryError`），根因 = D3 `adapter_registered=False`
  真实前置（裁决 F5），与本任务声明无关。
- `test_row_table_engine_core_equivalence::test_fail_closed_behaviours_match[d3]`
  ⇒ 复跑显示 `[d3]` 参数 xfailed（xfail-strict，已知边界），非本任务引入。
- `test_excel_row_insertion_scope_closure::…definition_store` / `test_sibling_table_ref_row_shift[D1-8]`
  （D1-11 TypographyRowError 并发 lane）⇒ 按任务原文属别 lane 未提交改动，未触及、未复现归因。

本任务新增失败 = 0。

---

## 七、停下报告的裁决点

**无。** 本任务全程在框架层已提供的能力内完成（`AdjudicationSheetSpec` 两区 + fixed_rows +
逐格 mask + value_sources + html_only 全部是框架层现成字段），未发现框架层缺能力，未需硬改
引擎，未触及灰度开关/契约重生成（那是 Task 14 范围）。一次性探针脚本已删。
