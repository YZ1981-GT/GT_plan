# Task 8 证据记录：`phase5_d3_04_analysis.py` 双区裁决与声明

**实施日期**：2026-09-26　**方法**：openpyxl 独立直读复核 Task 1 证据 + 通读框架层三个判据
文件（`excel_extract.py`/`phase5_row_table_sheet.py`/`contracts.py`）+ 通读两个真实先例
（`phase5_d1_04_bad_debt.py`/`phase5_d4_customer_structure.py`）+ 核查上游 D1 spec Task 24
状态 + 判据先行验证。

## 一、裁决：方案 A（标准动态行表双区），不是方案 B（D4-33 式 `limited_bidirectional`）

### 1.1 独立核实过程（不盲信 Task 1 转述，自己读一次模板）

用 openpyxl 直读 `backend/wp_templates/D/D3 预收账款.xlsx` 的「预收账款分析表D3-4」sheet
（`data_only=False`），逐格核对行 1-38：

```
9  | A9='（一）预收账款借方发生额分析'
10 | A10='项目' B10='金额' C10='数据来源' D10='备注'
11 | A11='本期借方发生额合计'
12 | A12='对方科目：'
13 | A13='资产处置损益'
14 | A14='固定资产'
15 | A15='增值税'
16 | A16=' ……'
17 | A17='差异' B17='=B11-B13-B14-B15-B16'
18 | A18='差异合理性分析'
19 | A19='（三）预收账款贷方发生额分析'
20 | B20='金额' C20='数据来源' D20='与对方科目核对' E20='说明'
21 | A21='本期贷方发生额合计' C21='预收账款总账' D21='N/A' E21='N/A'
22 | A22='其中：银行存款收款' E22='与银行存款借方发生额核对'
23 | A23='      应收票据' E23='与应收票据借方发生额核对'
24 | A24='         ……'
25 | A25='差异合理性分析'
26 | A26='（四）期末预收账款主要债务人分析' I26='提示：...'
27 | A27='债务人名称' B27='期末账面余额' ...
28-32 | A28-32='债务人1'~'债务人5' D28-32='=Bn-Cn' E28-32='=Dn/Cn'
33 | A33='小计' B33='=SUM(B28:B32)' ...
34 | A34='三、审计说明'
38 | A38='四、审计结论'
```

**结论：与 Task 1 证据文档逐字一致**。独立复核确认三个关键事实：
1. 段①数据区确为 13-16（4 行固定文字标签占位），差异公式 `B17='=B11-B13-B14-B15-B16'`
   确实硬编码引用这 4 行。
2. 段②数据区确为 22-24（3 行固定文字标签占位），R25 是纯文字（无 `=` 开头，不是公式），
   与段①不同——段②没有类似段①的"差异计算硬编码"问题。
3. 段③（26-33，债务人分析）是纯派生 `top5Debtors`，从 `D3-det-rows` 明细表交叉算出，
   前端无导入/导出按钮、无独立 store 键，**不进本文件受管区**——与 Task 1 结论一致。

另外用 openpyxl 独立扫描候选空列（J/K/L/M/N，行 1-38 全范围），确认全部为空——本表 max_column
实测为 9（A-I），J 及以后全空，可用作两区各自独立的 UUID 注入列。

### 1.2 框架层判据核实（`excel_extract.py` / `phase5_row_table_sheet.py`）

读取 `excel_extract.BindingKind` 枚举定义（docstring 逐字引用）：

> `static_region` —— ...承载「只有绝对坐标 static cell、无动态行/无 UUID 列」的纯静态受管区
> （D4-33/D4-8）。

判据核心是**"无行维度"**（单 cell 锚点）。段①②每行是同构记录（label/amount/source/remark
四列一行一条），有清晰的行维度，**不满足** `static_region` 的判据。

读取 `phase5_row_table_sheet.RowTableSheetSpec.last_data_row` 字段注释：

> `last_data_row: int  # 模板预画末行（超出按样式克隆扩行）`

⇒ 引擎设计目标本身就是**支持超出模板行数增长**（`_grow_managed_table_ref`/`CompositeRowShift`
位移归一化机制），不是"模板画几行数据区就固定几行"。这直接反驳了"模板固定行数 ⇒ 该判
`limited_bidirectional`"的推论前提。

### 1.3 与两个真实先例的几何对照

| | D1-4 个别/组合计提两区（已判 `excel_table`） | D3-4 段①②（本任务待裁决） | D4-33 业务类型矩阵（已判 `limited_bidirectional`） |
|---|---|---|---|
| 数据行数 | 各 4 行（13-16 / 18-21） | 4 行（13-16）/ 3 行（22-24） | N/A（无行维度，是 12 月固定行 × 3 固定列组的矩阵） |
| 父行公式 | `SUM(13:16)`/`SUM(18:21)` 硬编码引用固定区间 | 段①`=B11-B13-B14-B15-B16` 硬编码引用固定 4 行 | 合计列 B/C/D + 各组毛利率列 G/J/M 全公式 |
| 前端 store 形状 | 未直接核（个别/组合计提各自独立 rows，任意长度） | `ref<AnalysisRow[]>`，任意长度数组，无固定长度常量 | `bizTypes[]`，前端"业务类型"数组，**槎位语义**（`store.bizTypes[slot].id` 按位置映射到模板固定 3 列组） |
| 裁决 | `excel_table`（标准动态行表） | **本任务裁决：`excel_table`** | `limited_bidirectional`（位置映射，第 4+ 业务类型 HTML-only） |
| 裁决理由 | 有行身份维度，行数可增删 | 有行身份维度（每行同构 4 字段记录），行数可增删 | **列组不能插入**——3 个固定列组是模板画死的空间结构，不是"数据行占位"，业务类型数超过 3 就没有列可用 |

**关键区分**：D4-33 的 `limited_bidirectional` 本质是"前端 N 个业务类型 → 模板固定 **3 个
列组**"的**位置映射**问题——列组是横向的模板结构（E-G/H-J/K-M 三组各 3 列），不能靠"插入更
多列组"解决（模板画死了）。D3-4 段①②是"前端 N 行 → 模板预画 4/3 **行**占位"的**行数**问题
——这正是行表引擎的 row-shift 机制设计要解决的场景（D1-4 已验证的同型先例）。

### 1.4 最终裁决

**方案 A**：声明两个标准 `RowTableSheetSpec`（`binding_kind` 用默认值 `excel_table`），
`row_identity_key='rowId'`（UUID 动态行）。理由汇总：
1. `static_region` 判据是"无行维度"，段①②不满足。
2. 引擎设计目标本身支持超出模板行数增长。
3. D1-4 是几何同型的已判先例，判 `excel_table` 而非 `static_region`。
4. D4-33 的 `limited_bidirectional` 本质是列组位置映射问题，与 D3-4 的行数问题本质不同。
5. 前端 `useD3Analysis.ts` 的 `debitRows`/`creditRows` 确认是任意长度数组（无固定长度常量），
   与 D1-4 两区（也是任意长度）同型，不是 D4-33 式"槎位语义"数组。

**模板预存缺陷处置**（同 Task 6 处置原则）：段①差异公式硬编码引用 `B13:B16`（固定 4 行）——
若用户实际业务数据超过 4 行，第 5+ 行不会被这个差异公式计入。这个缺陷是否会被行表引擎的位移
归一化机制在插行后自动纠正为覆盖全部数据行，**本任务不做判断**，如实记录在声明代码 docstring
里，留给 Task 10（阶段 2 验收）用真实测试验证。声明代码**不做任何特殊处理**，按实测的公式
模板原样声明。段②无此问题（无差异计算公式硬编码引用固定行，R25 是纯文字说明）。

## 二、上游 D1 spec Task 24 前置核查（如实记录）

任务原文要求核查 `d1-sync-row-table-engine-and-d1-coverage` 的 Task 24（"位移判据清单按
provider 参数化"）状态。核查方法：读 `.kiro/specs/d1-sync-row-table-engine-and-d1-coverage/
tasks.md` 找 Task 24 的复选框状态。

**核查结果：Task 24 仍是 `[ ]` 未完成**：

```
- [ ] 24. `test_sibling_table_ref_row_shift.py` 的参数化判据改按 provider 取清单
  - 现状 `_multi_region_sheets()` 只从 D4 取 ⇒ 扩成 provider 参数化
  - P12 判据：D1 的多区 sheet 接入后**自动**进入覆盖清单；变异改回硬编码 D4 ⇒ 必红
  - _Requirements: 5.4_
```

进一步用 grep 核实 `_multi_region_sheets()` 的真实实现（`backend/tests/workpaper_sync/
test_sibling_table_ref_row_shift.py:655`）：

```python
def _multi_region_sheets() -> dict[str, list[Any]]:
    """`managed_sheet → [spec, …]`，只保留同 sheet ≥2 个受管区的组（按首数据行升序）。"""
    by_sheet: dict[str, list[Any]] = {}
    for spec in D4.instrumentation_specs():
        if not (getattr(spec, "table_name", None) and getattr(spec, "uuid_col", None)):
            continue
        by_sheet.setdefault(str(spec.managed_sheet), []).append(spec)
    return {
        sheet: sorted(specs, key=lambda s: int(s.first_data_row))
        for sheet, specs in by_sheet.items()
        if len(specs) >= 2
    }
```

**确认属实**：该函数硬编码只遍历 `D4.instrumentation_specs()`（导入 `D4` 模块），不是按
provider 参数化。这是一个真实存在的前置缺口。

**对本任务的影响（如实记录）**：
- 声明代码本身**可以落地**，不依赖 Task 24（`RowTableSheetSpec` 引擎本身不感知这个测试文件，
  本文件的声明与它是否被纳入该判据无关）。
- 但"D3-4 双区位移链自动化判据覆盖"**确实缺失**——D3-4 声明后不会自动进入
  `test_all_multi_region_sheets_shift_sibling_table_refs` 的 `@pytest.mark.parametrize
  ("sheet_name", sorted(_MULTI))` 覆盖清单，因为该函数只认 D4 模块。
- 本任务**不代为修复** `_multi_region_sheets()`（那是上游 D1 spec Task 24 自己的范围，修复它
  需要改成"遍历全部已注册 provider"的参数化形态，涉及跨 spec 的判据文件改动，不属于 D3 spec
  Task 8 的范围）。已在 `phase5_d3_04_analysis.py` 模块 docstring 里如实记录这个缺口，留给该
  缺口后续解决或本 spec Task 10 手写一条临时判据补上。

## 三、`sheet_key` 共享裁决（design.md 骨架的一处过时示意）

design.md 的示意骨架写：

```python
SPEC_D304_CREDIT = RowTableSheetSpec(
    managed_sheet="预收账款分析表D3-4", sheet_key="d34-managed-credit", ...)
SPEC_D304_DEBIT  = RowTableSheetSpec(
    managed_sheet="预收账款分析表D3-4", sheet_key="d34-managed-debit", ...)
```

两个不同 `sheet_key`。核对两个真实先例后发现这与实际架构不符：

- `phase5_d4_customer_structure.py`（D4-9，design.md 点名的"形如 D4-9 双区"参照对象）：
  `SHEET_KEY_D49="d49-managed"` **单一共享值**，三个 table（current/prior/totals）共用。
- `phase5_d1_04_bad_debt.py`（D1-4，同 sheet 三区）：`SHEET_KEY_D104` **单一共享值**，
  `_base_spec()` 内三区共用。

框架层证实：`contracts.SheetSpec.tables` 本身是 `tuple[TableSpec, ...]`（一个 sheet 天然可
含多 table）；`phase5_d1_expansion.assert_specs_align_with_contract_sheets` 用
`{s.resolved_sheet_key for s in instrumentation_specs()}` 集合去重——两个 spec 共享
`sheet_key` 会正确 collapse 成一个契约 sheets 条目。若用两个不同 `sheet_key`，则会产生"同
`excel_name` 两个 sheet 条目"的重复/冲突声明。

**裁决**：不照抄 design.md 旧骨架的两个不同 `sheet_key`，改用**单一共享**
`SHEET_KEY_D304="d34-managed"`。design.md 该处是 Task 1 实测前写的过时示意，本次裁决据两个
真实先例修正。

## 四、新建/改动文件清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/services/workpaper_sync/phase5_d3_04_analysis.py` | 新建 | sheet 层薄声明（`SPEC_D304_DEBIT`/`SPEC_D304_CREDIT`），照抄 `phase5_d1_04_bad_debt.py` 的 `_base_spec()` 共用骨架手法，两区共享 `SHEET_KEY_D304`，各自独立 UUID 列（J/K）与 `footer_carries_total_formula`（True/False） |
| `backend/app/services/workpaper_sync/phase5_row_table_sheet.py` | 改动（+8 行，520→527 行） | `RowTableSheetSpec` 新增 `footer_carries_total_formula: bool = True` 字段（默认值与七家既有 provider 现状逐字等价，零回归） |
| `backend/app/services/workpaper_sync/phase5_d3_expansion.py` | 改动（+7 行，163→182 行，含注释） | 新增 `_INCLUDE_D304_ANALYSIS: Final[bool] = False` 灰度开关 + `managed_row_table_specs()` 追加 D3-4 两区逻辑 |
| `backend/app/services/workpaper_sync/phase5_d3_prepaid_receipts.py` | 改动（942→965 行） | ①`_expansion_sheet_row_table_payload()` 改读 `spec.footer_carries_total_formula` 而非硬编码 `True` ②`_expansion_sheets_payload()` 重构为**按 `sheet_key` 分组**（`by_sheet_key` 字典去重手法，同 `phase5_e1_monetary_fund.build_contract_payload()` 先例），修复了 Task 6 落地时隐含的"一个 spec = 一个契约 sheet 条目"的错误假设（D3-6 单区场景 1:1 恰好不出错，D3-4 双区场景才暴露这个 bug） |

未修改任何模板文件、未修改 Task 3/Task 4 的判据文件本身（它们按设计会在本任务落地后自动从
SKIPPED/红基线转为对应状态，无需改判据文件）。

## 五、`_expansion_sheets_payload()` 的重构细节（本任务发现并修复的一个真实缺陷）

Task 6 落地 D3-6（单区）时，`_expansion_sheets_payload()` 的原实现是：

```python
return [
    {"sheet_key": spec.sheet_key, "excel_name": spec.managed_sheet, ...,
     "tables": [_expansion_sheet_row_table_payload(spec)]}
    for spec in _expansion.managed_row_table_specs()
]
```

**隐含假设**："一个 spec = 一个契约 sheet 条目"。D3-6 场景（1 个 spec）恰好 1:1，没有暴露
问题。D3-4（2 个 spec，共享 `sheet_key`）会让这个实现产生**两个** `excel_name` 相同的契约
sheets 条目（同一张 Excel sheet 出现两次）——这既不对齐 D4-9/D1-4 两个真实先例的"一 sheet
多 table"契约形态，也会让 `assert_specs_align_with_contract_sheets` 的集合去重（按
`resolved_sheet_key`）与契约侧的重复条目产生歧义。

**修复**：按 `sheet_key` 分组（`by_sheet_key` 字典去重手法，逐字参照
`phase5_e1_monetary_fund.build_contract_payload()` 第 505-518 行的先例）：

```python
sheets: list[dict[str, Any]] = []
by_sheet_key: dict[str, dict[str, Any]] = {}
for spec in _expansion.managed_row_table_specs():
    entry = by_sheet_key.get(spec.sheet_key)
    if entry is None:
        entry = {"sheet_key": spec.sheet_key, "excel_name": spec.managed_sheet,
                  "locator": {"anchor": TABLE_SHEET_ANCHOR}, "tables": []}
        by_sheet_key[spec.sheet_key] = entry
        sheets.append(entry)
    entry["tables"].append(_expansion_sheet_row_table_payload(spec))
return sheets
```

修复后 D3-6（1 spec）与 D3-4（2 spec 共享 sheet_key）两种场景都能正确装配：D3-6 产出 1 个
sheet 条目含 1 个 table；D3-4 产出 1 个 sheet 条目含 2 个 table（顺序即
`managed_row_table_specs()` 返回顺序，本模块保证按 Excel 行序：段①借方在段②贷方之前）。

## 六、`footer_carries_total_formula` 字段的新增理由

段①（R17 `B17='=B11-B13-B14-B15-B16'`）确有公式，段②（R25「差异合理性分析」纯文字）确无
公式——这是本引擎首次出现"同一 provider 内两个 table，footer 是否有公式"不同的场景。既有
七家 provider（含 D3-6/D1-4/E1）的 entry 层 table payload 全部硬编码
`"carries_total_formula": True`（`grep` 确认全仓无一例外），因为它们的 footer 行全部真有
公式。

若不给段②显式声明，沿用硬编码 `True` 会与实测几何不符——`excel_materialize.
_grow_managed_table_ref` 的 `carries_total_formula` 参数用于决定插行后 footer 公式区间是否
需要跟随重新归一化；对一个实际无公式的 footer 行错误声明"有公式"，理论上会让归一化逻辑去
寻找一个不存在的 SUM/差异公式模式，属于"声明与实测几何不一致"的缺陷（同本 spec 反复强调的
"按值实测，不按模式推演"纪律）。

**修复**：在 `RowTableSheetSpec` 新增 `footer_carries_total_formula: bool = True` 字段
（默认值 `True` 保证七家既有 provider 零回归），entry 层的 `_expansion_sheet_row_table_payload
()` 改读 `spec.footer_carries_total_formula` 而非硬编码常量。`SPEC_D304_DEBIT` 显式传
`True`（段① R17 确有公式），`SPEC_D304_CREDIT` 显式传 `False`（段② R25 确无公式）——不沿用
默认值掩盖这个真实差异。

## 七、判据验证结果（命令+输出）

### 7.1 Task 3 判据（Property 2）：`test_d3_04_analysis_store_item_ids_both_regions` 转绿

```
cwd: backend
命令: python -m pytest tests/workpaper_sync/test_d3_property2_store_item_id_exact_match.py -v --tb=short
```

关键输出：

```
TestSixSheetsStoreItemIdExactMatch::test_d3_06_related_party_store_item_id PASSED
TestSixSheetsStoreItemIdExactMatch::test_d3_04_analysis_store_item_ids_both_regions PASSED  ← 从 SKIPPED 转 PASSED
TestSixSheetsStoreItemIdExactMatch::test_d3_05_long_term_store_item_id SKIPPED   ← 仍 SKIPPED（Task 9 范围）
TestSixSheetsStoreItemIdExactMatch::test_d3_07_voucher_check_store_item_ids_both_regions SKIPPED  ← 仍 SKIPPED（Task 11 范围）
TestSixSheetsStoreItemIdExactMatch::test_all_real_values_are_pairwise_distinct PASSED
======================== 26 passed, 2 skipped in 1.53s ========================
```

**结论**：`test_d3_04_analysis_store_item_ids_both_regions` 从 Task 3 落地时的 SKIPPED（因
`phase5_d3_04_analysis` 模块不存在）**自动转为 PASSED**（未改判据文件本身），断言
`{SPEC_D304_DEBIT.store_item_id, SPEC_D304_CREDIT.store_item_id} == {"D3-ana-debit-rows",
"D3-ana-credit-rows"}` 成立。D3-5/D3-7 两条继续 SKIPPED（不属本任务范围，正确未受影响）。

### 7.2 Task 4 判据（Property 3/4 基线）：维持红基线，未意外提前转绿

```
cwd: backend
命令: python -m pytest tests/workpaper_sync/test_d3_property3_4_dual_zone_baseline.py -v --tb=short
```

```
test_current_d3_managed_region_count_is_pre_expansion_baseline PASSED
test_d3_4_dual_zone_not_yet_reaching_target_count_of_four PASSED   ← 断言 count < 4，仍成立
test_d3_7_dual_zone_not_yet_reaching_target_count_of_seven PASSED
test_mutation_d3_4_declaring_only_debit_zone_loses_credit_key_visibility PASSED
test_mutation_d3_7_declaring_only_current_zone_loses_post_key_visibility PASSED
test_mutation_merging_into_shared_table_key_still_loses_one_key PASSED
======================== 6 passed in ... ========================
```

**结论**：因灰度开关 `_INCLUDE_D304_ANALYSIS` 维持 `False`，
`D3.assert_contract_file_matches_source()` 读到的磁盘契约（`sheets` 只有 D3-2 自身 1 项）
未受本任务改动影响，受管区计数仍是 1（< 4），符合任务要求"此时应仍然是『未接入』状态"——
**未意外提前转绿**。

### 7.3 Task 2 判据（零回归基线）

```
cwd: backend
命令: python scripts/check/check_sync_provider_golden_digest.py
输出: ✅ golden digest 零回归：26 个 digest 逐个不变
```

### 7.4 D3-6 既有判据回归验证（Task 6/7 判据零回归）

```
cwd: backend
命令: python -m pytest tests/workpaper_sync/test_d3_expansion.py -v --tb=short
======================== 7 passed in ... ========================
```

全部 7 条通过，未受 `_expansion_sheets_payload()` 重构与 `footer_carries_total_formula`
字段新增影响。

### 7.5 D3 全 scope 回归

```
cwd: backend
命令: python -m pytest tests/workpaper_sync -k "d3 or D3" -v --tb=short
======================== 73 passed, 2 skipped in 20.91s ========================
```

覆盖 `test_d3_06_offline_materialize_and_verify.py`/`test_d3_06_related_party_spec.py`/
`test_d3_expansion.py`/`test_d3_property2_store_item_id_exact_match.py`/
`test_d3_property3_4_dual_zone_baseline.py`/`test_ghost_row_defense.py`/
`test_masked_cell_protection_is_cell_level.py`（D3 entry）/
`test_row_table_engine_core_equivalence.py`[d3]/`test_row_table_engine_equivalence.py`[d3]/
`test_task5_d3_performance_baseline.py`/`test_task75_published_identity_observer.py`（D3
entry）等既有判据全部保持通过，2 个 skip 是 D3-5/D3-7（不属本任务范围，正确保持跳过）。

### 7.6 框架层改动的全域回归（`footer_carries_total_formula` 新字段的风险面覆盖）

`RowTableSheetSpec` 是被 D1/D3/D5/D6/D7/E1 六家共用的框架层类，本任务新增字段是本任务风险
最高的改动，需要覆盖全部使用方：

```
cwd: backend
命令: python -m pytest tests/workpaper_sync/test_row_table_engine_core_equivalence.py \
      tests/workpaper_sync/test_row_table_engine_equivalence.py \
      tests/workpaper_sync/test_phase5_row_table_sheet.py -v --tb=short
======================== 46 passed in 2.22s ========================
```

覆盖 D1/D3/D5/D6/D7 五家的 `build_store_projection`/`merge_projection_into_store_rows`/
`fail_closed_behaviours`/`formula_mask`/`managed_field_specs`/`aging_layout` 等价性判据、
`static_region_spec_rejects_row_projection`、`GhostRowAnchorIndex` 等全部保持通过。

```
命令: python -m pytest tests/workpaper_sync -k "d1 or e1" -q --tb=short
======================== 163 passed, 1 xfailed in 26.62s ========================
```

D1/E1 两家（既有 `RowTableSheetSpec` 重度使用方）163 条全部保持通过（1 条既有 xfailed 与
本任务无关，是既有生产代码 bug 标记）。

### 7.7 文件行数门禁

```
cwd: backend
命令: python scripts/check/check_file_size.py
```

未在超限清单里出现本任务改动的四个文件（`phase5_d3_prepaid_receipts.py` 965 行，仍低于
whitelist 登记的 967 行基线；`phase5_d3_expansion.py`/`phase5_d3_04_analysis.py`/
`phase5_row_table_sheet.py` 均远低于各自门禁阈值）。

### 7.8 全仓调用点核查

`grep_search` 全仓确认 `_expansion_sheets_payload`/`_expansion_sheet_row_table_payload`
两个被重构的私有函数**只被** `backend/tests/workpaper_sync/test_d3_expansion.py` 调用（已在
7.4 验证保持全绿），未发现其他隐藏调用点会受本次重构影响。

### 7.9 全量 `tests/workpaper_sync` 套件（后台跑，超出本任务要求的完成标准，作为额外确认）

前台运行 8996 项测试超出工具超时限制，已改用后台进程跑（`terminalId=term_1790379732496_gpx41uspjce`，
`python -m pytest tests/workpaper_sync -q --tb=line`）。7.1-7.8 的针对性回归覆盖（D3 全
scope 73 条 + 框架层等价性 46 条 + D1/E1 163 条 + golden digest 26 个 digest + 文件行数门禁
+ 调用点核查）已足以证明本任务改动的风险面得到充分覆盖，后台全量结果作为锦上添花的最终确认。

## 八、结论

1. **裁决结果：方案 A**（标准动态行表双区，`RowTableSheetSpec` 引擎标准路径，非 D4-33 式
   `limited_bidirectional`）。裁决依据见本文档第一节，核心是"有行维度"（段①②每行同构记录）
   与"引擎设计目标支持超出模板行数增长"两条判据，且与几何同型的 D1-4 先例判决一致。
2. **声明代码已落地**：`phase5_d3_04_analysis.py`（`SPEC_D304_DEBIT`/`SPEC_D304_CREDIT`）
   + 框架层新增 `footer_carries_total_formula` 字段（区分段①有公式/段②无公式）+
   `phase5_d3_expansion.py` 灰度开关 + `phase5_d3_prepaid_receipts.py` 的
   `_expansion_sheets_payload()` 按 `sheet_key` 分组重构（修复了 D3-6 单区场景未暴露的
   "1 spec = 1 sheet" 错误假设）。
3. **灰度开关现状：关闭**（`_INCLUDE_D304_ANALYSIS: Final[bool] = False`）——本任务只声明
   不激活，是否打开留给 Task 10（阶段 2 验收）决定，理由同 Task 6/Task 9 的处置原则（翻开关
   涉及重生成磁盘契约、打红既有基线判据的假设，超出本任务单方面决定范围）。
4. **上游 D1 spec Task 24 缺口：存在且已如实记录**。Task 24（`_multi_region_sheets()` 参数
   化）仍是 `[ ]` 未完成，`_multi_region_sheets()` 硬编码只认 D4 模块 ⇒ D3-4 双区声明后不会
   自动进入该判据的 parametrize 覆盖清单——这是真实存在的已知缺口，不在本任务修复范围（不
   属于 D3 spec 的范围），已在 `phase5_d3_04_analysis.py` 模块 docstring 与本文档如实记录。
5. Property 2（Task 3 判据文件）：`test_d3_04_analysis_store_item_ids_both_regions`
   **已从 SKIPPED 转为 PASSED**。
6. Property 3/4（Task 4 判据文件）：**维持红基线**（受管区计数仍 1，< 4），符合任务要求的
   "未接入"状态，未意外提前转绿。
7. Property 1（Task 2 零回归基线脚本）：**验证通过**，26 个 digest 逐个不变。
8. 全域回归（D3 全 scope 73 条 + 框架层等价性 46 条 + D1/E1 163 条）：**全部保持通过**，
   `footer_carries_total_formula` 新字段对既有七家 provider 零回归。
