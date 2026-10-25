# Task 5 / 6 / 7 证据：BP-5 修复 · GC-2 中性化 · GC-8 prefill + 补守卫

**执行时间**：2026-09-27

## Task 5：BP-5 —— `G1_SHEET_LABEL_MAP` 5 条错名 → 模板真名

改 `audit-platform/frontend/src/components/workpaper/composables/g1SheetLabels.ts`：

| 编码 | 改前 | 改后（模板真名） |
|---|---|---|
| `G1A` | `'交易性金融资产实质性程序表G1A'` | `'交易性金融资产实质性程序表G1A '` 🔴 **尾部空格** |
| `G1-8` | `'业务模式评估问卷G1-8'` | `'业务模式分析G1-8'` |
| `G1-10` | `'合同现金流量特征测试表G1-10'` | `'合同现金流量特征分析G1-10'` |
| `G1-12` | `'盘点倒轧表G1-12'` | `'有价证券盘点倒轧表G1-12'` |
| `附注国企` | `'附注披露信息（国有企业）'` | `'附注披露信息（国企）'` |

其余 13 条改前即命中，未动。

### 🔴 顺带修掉一条**错的注释**（它就是缺陷成因）

原注释：`/** 与 Excel / useGInvestmentCycleSheetGroups 一致：编码紧贴表名、无空格 */`
—— 「无空格」这条描述本身与源模板矛盾（`G1A` 的真实 tab 尾部**有**一个空格），
按它写出来的值在模板里永远找不到。已改为「必须逐字等于 `wb.sheetnames`，**含空格**」并指向判据。

### 触类旁通：三个错名的全仓残留 = 0

grep 全仓（`.ts` / `.vue` / `.py` / `.json` / `.yaml`）：
`业务模式评估问卷G1-8` / `合同现金流量特征测试表G1-10` 只剩三类**应当保留**的出现：

1. slice `BP-5` 正文（冻结取证，不改）；
2. 我的判据里的历史台账 `KNOWN_WRONG`（stale 检测用）；
3. **ACNR 权威目录** `backend/data/acnr/global_catalog.json` 的 `sheet_name_aliases`。

第 3 条是本轮最有价值的旁证：ACNR 早就把正确名登记为 `sheet_name`、把这三个错名登记为 `sheet_name_aliases`：

```json
{ "sheet_name": "合同现金流量特征分析G1-10", "sheet_name_aliases": ["合同现金流量特征测试表G1-10"] }
{ "sheet_name": "业务模式分析G1-8",        "sheet_name_aliases": ["业务模式评估问卷G1-8"] }
{ "sheet_name": "有价证券盘点倒轧表G1-12",  "sheet_name_aliases": ["盘点倒轧表G1-12"] }
```

⇒ **平台级命名真源（ACNR）与我改后的值完全一致，`g1SheetLabels.ts` 是唯一的偏离方**。
`附注披露信息（国有企业）` 在 G 循环文件里 0 命中（其它循环模板确实用这个 tab 名，属各自真名）。

判据：`TestGfP4Bp5G1SheetLabels`（9 passed），含
`test_trailing_space_is_preserved_verbatim`（正向锁空格）+
`test_mutation_strip_comparison_would_hide_the_space_defect`（证明 strip 会放过）+
`test_known_wrong_names_are_really_wrong_and_right_names_really_exist`（台账 stale 检测）。

## Task 6：GC-2 —— 13 册 per-file 挂 OO 崩溃中性化

### 交付形态：规则 + 判据（不是 17 条 plan）

`StoreMergePlan` 的 `provider_module` 是**必填**字段 ⇒ plan 不能在 provider 模块存在之前声明。
而 17 条 entry 分散在**四份** spec：

| spec | entry | 数 |
|---|---|---|
| `g-cycle-sync-foundation-and-first-canary`（本 spec） | G2 | 1 |
| `g4-g6-shared-workbook-three-entry-lanes` | G4×3 + G6×3 | 6 |
| `g5-nested-sections-and-template-defects` | G5 | 1 |
| `g-cycle-single-region-detail-lanes`（**不在本轮范围**） | G1 G3 G8 G9 G10 G11 G12 G13 G14 | 9 |

⇒ 判据写成「17 条全在」会在最后一份 lane spec 交付前**永久红**，而永久红的判据等于没有判据。
改为两条并存：

* `test_every_delivered_g_adapter_declares_neutralization` —— **已交付**的一律带
  `oo_crash_neutralization_fn="neutralize_oo_crash_if_formulas"`，**无例外**；
* `test_undelivered_adapters_are_registered_with_owning_spec` —— 未交付者必须有归属 spec 登记
  （`ADAPTER_OWNER_SPEC` 17 条全覆盖），禁沉默欠账。全部交付后自然变空集检查。

### per-file 保守策略的证据

`test_every_workbook_has_bare_if_cells`（13 册 parametrize）：跑生产函数
`neutralize_oo_crash_if_formulas(副本)`，逐册断言格数 > 0 且等于基线，
并在同一判据里断言 **①幂等**（复跑返回 `()`）**②权威模板字节不变**（只改 substrate 副本）。

`test_excel_adapter_has_no_adapter_id_literal_branch`：`adapters/excel.py` 不得有
`if adapter_id == "…"` 字面量分支（Task 13 已收敛掉两处，锁住不回退）。

### 🔴 口径修正（详见 `task0-prerequisites.md`）

spec RG-4 表里的数字（G1 141 / G4 186 / G5 122 …）是**正则出现次数**，不是「格数」。
权威口径 = 生产函数返回的格数：G1 **71** / G2 21 / G3 18 / G4 **154** / G5 **61** / G6 137 /
G8 12 / G9 42 / G10 28 / G11 95 / G12 7 / G13 11 / G14 11。
反证：`_strip_bare_if_cells` docstring 写「实测 G7 权威模板 **1065** 个裸 IF 格」——
与格数口径一字不差（出现次数是 2325）。
判据 `test_occurrence_count_caliber_differs_from_cell_caliber` 把 2:1 关系锁住，
`test_heuristic_probe_would_undercount` 证明「`IF(` 后跟 `IS*`/`AND`/`OR`」启发式会低估。

实质结论两种口径都成立：**13/13 册命中**、**13 张审定表全部命中**（GF-H5 共性证据①）。

## Task 7：GC-8 —— prefill 两块改名 + 补 G 循环缺失的 sheet 存在性守卫

### 改名（**不是删块**）

扩既有幂等脚本 `backend/scripts/fix/fix_g_cycle_prefill_presets.py`（**不另建**），
新增 `RENAME_SHEETS` 段与「1b」处理步：

```
改名 G13 / sheet='明细分析表G13-2' → '明细表G13-2'
改名 G14 / sheet='明细分析表G14-2' → '明细表G14-2'
共 2 项变更 → [WRITTEN] backend/data/prefill_formula_mapping.json
复跑 --check → [OK] G 循环公式预设无欠账（幂等）
```

🔴 与既有 `DROP_BLOCKS`（幽灵 sheet ⇒ 整块作废）的区别写进了代码注释：
这两块的 sheet **存在**、只是名字写错 ⇒ 必须改名；删块会把 4+3=**7 条有效预设**一起丢。

处理顺序放在「整块删除之后、单元格删除之前」：后两者用 `(wp, sheet)` 做键、登记的是**原名**，
先改名会让键失配（现状两集合无交集，此顺序是防御性的）。

### 补守卫（加在**既有文件**，口径照 I 循环）

`backend/tests/four_table/test_g_cycle_formula_presets.py` 新增 **Property 11**：

* `test_property_11_every_block_sheet_exists_in_template` —— 每个 G 块的 `sheet` ∈ 对应源 xlsx
  `sheetnames`，**不 strip**（G 目录确有带空格的 tab：`交易性金融资产实质性程序表G1A ` /
  `信用减值损失审计程序表G14A -修订前`），**无白名单**；
* `test_no_stale_sheet_label_ledger` —— 历史台账 stale 检测（照
  `test_i_cycle_formula_presets.test_no_stale_sheet_label_whitelist`）：
  错名必须确实不在模板里、真名必须确实在；
* `test_property_11_reverse_self_check_would_catch_a_ghost_sheet` —— 反向自检防空转；
* `test_prefill_script_check_is_clean` —— `--check` 0 欠账（幂等锚点，显式 `encoding='utf-8'`）。

`template_sheets` fixture 逐字照 `test_i_cycle_formula_presets._load_template_sheetnames`
（跳过 `~$` 锁文件、按 `^(G\d+)\s` 提 wp_code），**不新造第二套口径**。

结果：`test_g_cycle_formula_presets.py` **9 passed**（原 4 项 + 新 4 项 + 既有披露脚本核）。

### 需求 5.4 计数不减

`convert_prefill_presets()` 返回 `list[PresetEntry]`（**不是 dict**），按 `.page_key` 计数：
`workpaper:G13` ≥ 14 · `workpaper:G14` ≥ 13，且 13 个 G 科目**全非零**（与 F5 的 0 对比）。

## 四文件合跑结果

```
test_g_foundation_p1_p3_fc_reinterpretation.py
test_g_foundation_p4_p8_p17_p18_red_baselines.py
test_g_foundation_p20_golden_digest_baseline.py
tests/four_table/test_g_cycle_formula_presets.py
→ 101 passed
```

红基线 5 条转绿情况：BP-5 ×2 ✅（Task 5）· prefill ×1 ✅（Task 7）· G6 错注释 ✅（Task 8）·
GC-2 plan ✅（改为「已交付者一律带」+ 未交付登记）。
