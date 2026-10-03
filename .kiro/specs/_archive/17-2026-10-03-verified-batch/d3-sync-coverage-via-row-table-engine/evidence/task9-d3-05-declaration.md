# Task 9 证据记录：`phase5_d3_05_long_term.py` 声明（单区）

**实施日期**：2026-09-26　**方法**：独立 openpyxl 直读权威模板复核 Task 1 实测值 + 参照
Task 6（`phase5_d3_06_related_party.py`）的结构范式 + 判据先行验证。

## 一、openpyxl 独立实测过程（不盲信 Task 1 证据文档的转述）

任务原文要求本任务自行用 openpyxl 直读模板核实一次（不能只抄 Task 1 的证据文档）。执行了三轮
独立探测：

**第一轮**——表头（行 10）与候选空列（I..N）：

```python
import openpyxl
wb = openpyxl.load_workbook(r'wp_templates/D/D3 预收账款.xlsx', data_only=False)
ws = wb['账龄1年以上的预收账款检查表D3-5']
```

实测输出（逐字摘录）：

```
max_row 20 max_col 8
--- row 10 header (A..K) ---
A10 '对方单位名称'
B10 '期末余额'
C10 '账龄'
D10 '经济业务说明'
E10 '未结转或未偿还的原因'
F10 '至审计日结转或偿还金额'
G10 '处理计划'
H10 '备注'
I10 None
J10 None
K10 None
--- rows 11..15 col A..K ---
B14 '=SUM(B11:B13)'
F14 '=SUM(F11:F13)'
A15 '三、审计说明'
--- row 14 footer full A..K ---
A14 None
B14 '=SUM(B11:B13)'
C14 None
D14 None
E14 None
F14 '=SUM(F11:F13)'
G14 None
H14 None
I14 None
J14 None
K14 None
--- rows 1..9 (page-header formulas area) ---
A1 '致同会计师事务所'
A2 '账龄1年以上的预收账款检查表'
A3 '=底稿目录!A2'
C3 '=底稿目录!A4'
E3 '=底稿目录!A5'
G3 '索引号：'
H3 '=底稿目录!F17'
A4 '=底稿目录!A3'
C4 '=底稿目录!A6'
E4 '=底稿目录!A7'
G4 '页次：'
A5 '一、审计目标'
A6 '资产负债表中记录的预收账款是存在的，且已经记录在恰当的账户中。'
A7 '二、审计过程'
A8 '1.……'
```

**结论逐项与 Task 1 证据一致**：
- max_row=20，max_col=8（A-H），与 requirements.md/design.md 表格「20 行×8 列」逐字一致。
- 表头 A-H 逐字：对方单位名称/期末余额/账龄/经济业务说明/未结转或未偿还的原因/至审计日结转
  或偿还金额/处理计划/备注；I/J/K 为空（候选空列）。
- 页眉区（行 1-4）确有 7 处引用公式（`A3/C3/E3/H3/A4/C4/E4`，全部引用「底稿目录」跨表）——
  与 requirements.md「主公式列 A2 C2 E2」这个坐标速记（指公式落点样例坐标，不是数据行公式列）
  的实际含义一致，同 Task 6 对同类速记的解读方式。

**第二轮**——全表公式坐标扫描 + 数据行（11-13）逐格确认为空：

```python
count = 0
for row in ws.iter_rows():
    for cell in row:
        if isinstance(cell.value, str) and cell.value.startswith('='):
            print(cell.coordinate, repr(cell.value))
            count += 1
```

实测输出：

```
A3 '=底稿目录!A2'
C3 '=底稿目录!A4'
E3 '=底稿目录!A5'
H3 '=底稿目录!F17'
A4 '=底稿目录!A3'
C4 '=底稿目录!A6'
E4 '=底稿目录!A7'
B14 '=SUM(B11:B13)'
F14 '=SUM(F11:F13)'
total formulas: 9
```

**结论**：全表恰好 9 处公式，与「9 公式」逐字一致。**7 处是页眉引用公式（不落在数据行区间
11-13 内）+ 2 处是 footer SUM 公式（B14/F14）**。逐格核对行 11/12/13 的 A-H 全部为 `None`
（本轮独立确认）：

```
A11 None  B11 None  C11 None  D11 None  E11 None  F11 None  G11 None  H11 None
A12 None  B12 None  C12 None  D12 None  E12 None  F12 None  G12 None  H12 None
A13 None  B13 None  C13 None  D13 None  E13 None  F13 None  G13 None  H13 None
```

**⇒ 数据行区间（11-13）内逐行没有任何公式**——这是本任务独立扫描新发现的一个比 Task 1
转述更精确的结论（Task 1 记录了"数据区行11-13"与"合计行14的 SUM 公式"，但未明确点出"9 处
公式全部不落在数据行本身，7 处在页眉、2 处在 footer"）。这直接决定了本文件的 `field_specs`
**全部 8 列均为 editable，无一列进 `formula_columns`**（详见第二节）。

**第三轮**——候选空列扩大扫描（I..N，行 10-17 全范围）+ note/conclusion 区确认：

```python
for col in 'IJKLMN':
    for r in range(10, 18):
        v = ws[f'{col}{r}'].value
        if v is not None:
            print(f'{col}{r}', repr(v))
print('done (no output above cols line = all empty)')
```

实测输出：`done (no output above cols line = all empty)` —— I/J/K/L/M/N 在行 10-17 全部
为 `None`，独立确认可用候选空列范围比 Task 1 记录的"I/J/K"更宽（扩大到 L/M/N 同样全空）。
选定 **I** 列（数据区最后一列是 H「备注」，I 是紧邻数据区的最近候选空列），选列原则与
D3-6 选 K（紧邻其 A-J 数据区）一致。

note/conclusion 区确认：

```
--- rows 15..20 (note/conclusion area) ---
A15 '三、审计说明'
A19 '四、审计结论'
```

与 Task 1 记录的"A15「三、审计说明」+ A19「四、审计结论」（内容留白）"逐字一致，均落在
footer(14) 之下，登记为 HTML-only 候选（同 D4-5/D3-6 判例），不进本文件 `field_specs`。

## 二、公式方向与 `formula_columns` 的判定结论

与 Task 1 转述的差异点（本任务独立扫描发现的更精确结论，不影响最终几何参数，但影响
`formula_columns` 传参决策）：

- **footer 行 14 的两处 SUM 公式（`B14='=SUM(B11:B13)'`/`F14='=SUM(F11:F13)'`）确覆盖全部
  3 行数据区（11-13），无落差**——与 D3-6 footer SUM 只覆盖 3/5 行、D3-4 段①差异公式硬编码
  4 行的"模板预存缺陷"不同，本表 SUM 区间与数据区行数完全匹配。⇒ `footer_carries_total_
  formula=True` 无歧义，显式传值（保持与 Task 8 的显式声明风格一致）。
- **数据行区间（11-13）内逐行没有任何公式列**（本任务独立扫描的核心发现）。参照 Task 8
  D3-4 段②（贷方区，无差异计算公式）的处置原则：数据行本身无公式列时，声明代码**不传**
  `formula_columns`（沿用引擎默认值空 tuple），`formula_mask` 由引擎 property 现算为空
  tuple，**不是遗漏**——这与"footer 有 SUM 公式"是两个不同的事实层面（`formula_columns`
  语义是"数据区间内哪些列逐行都有公式"，footer 层公式由 `footer_carries_total_formula`
  单独表达，两者不冲突）。

## 三、新建/改动文件清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/services/workpaper_sync/phase5_d3_05_long_term.py` | 新建 | sheet 层薄声明（`SPEC_D305`），照抄 Task 6（`phase5_d3_06_related_party.py`）的结构范式：模块 docstring 交代裁决理由 → 冻结常量 → `FIELD_SPECS` 元组 → `SPEC_D305` 实例化 → `__all__`。本 spec 结构最简单的一个（单区、无双区裁决张力、无数据行公式列），不需要 Task 8 那种方案 A/B 裁决讨论 |
| `backend/app/services/workpaper_sync/phase5_d3_expansion.py` | 改动（182→194 行） | 新增 `_INCLUDE_D305_LONG_TERM: Final[bool] = False` 灰度开关 + `managed_row_table_specs()` 追加 D3-5 逻辑（`if _INCLUDE_D305_LONG_TERM: specs.append(_d305.SPEC_D305)`） |
| `backend/app/services/workpaper_sync/phase5_d3_prepaid_receipts.py` | **未改动**（仍 965 行） | 任务原文预判"理论上不需要改动这个函数本体"已验证成立——`_expansion_sheets_payload()`（Task 8 已重构为按 `sheet_key` 分组）通用地遍历 `_expansion.managed_row_table_specs()`，D3-5 是独立的单一 `sheet_key="d35-managed"`（不与 D3-4/D3-6 共享），本函数无需任何改动即可正确处理 D3-5 开关打开后的场景 |

未修改任何模板文件（`D/D3 预收账款.xlsx`）、未修改 Task 3 的判据文件本身（其
`test_d3_05_long_term_store_item_id` 按设计在本任务落地后自动从 SKIPPED 转 PASSED，无需改
判据文件）。

## 四、`_expansion_sheets_payload()` 确认无需改动的验证过程

任务原文要求核实这一点（而非想当然认为不需要）。核实方法：monkeypatch 打开
`_INCLUDE_D305_LONG_TERM` 开关后调用 `managed_row_table_specs()` / `instrumentation_specs()`
/ `all_store_item_ids()` 三个函数，确认 D3-5 正确出现在扩容面清单里：

```python
from app.services.workpaper_sync import phase5_d3_expansion as expansion
print('managed_row_table_specs (all off):', expansion.managed_row_table_specs())
print('all_store_item_ids (all off):', expansion.all_store_item_ids())

expansion._INCLUDE_D305_LONG_TERM = True
specs = expansion.managed_row_table_specs()
print('with D305 on:', [s.store_item_id for s in specs])
print('instrumentation_specs with D305 on:', [s.managed_sheet for s in expansion.instrumentation_specs()])
print('all_store_item_ids with D305 on:', expansion.all_store_item_ids())
expansion._INCLUDE_D305_LONG_TERM = False
print('reverted:', expansion.managed_row_table_specs())
```

实测输出：

```
managed_row_table_specs (all off): ()
all_store_item_ids (all off): ('D3-det-rows',)
with D305 on: ['D3-lt-rows']
instrumentation_specs with D305 on: ['账龄1年以上的预收账款检查表D3-5']
all_store_item_ids with D305 on: ('D3-det-rows', 'D3-lt-rows')
reverted: ()
```

**结论**：开关关闭时（现状）扩容面清单为空，与"D3 现状只有 1 个受管区"逐字等价（零回归）；
monkeypatch 打开后 D3-5 正确出现在三个聚合函数的输出里，`_expansion_sheets_payload()`
（`phase5_d3_prepaid_receipts.py` 内，按 `sheet_key` 分组遍历 `managed_row_table_specs()`）
无需任何改动即可正确装配 D3-5 的契约 sheet 条目（因为它是独立 `sheet_key`，会自动产出一个
新的、独立的契约 sheets 条目，不与 D3-4/D3-6 共享分组桶）。

## 五、判据验证结果（命令+输出）

### 5.1 Task 3 判据（Property 2）：`test_d3_05_long_term_store_item_id` 从 SKIPPED 转 PASSED

```
cwd: backend
命令: python -m pytest tests/workpaper_sync/test_d3_property2_store_item_id_exact_match.py -v --tb=short
```

关键输出行：

```
TestSixSheetsStoreItemIdExactMatch::test_d3_06_related_party_store_item_id PASSED
TestSixSheetsStoreItemIdExactMatch::test_d3_04_analysis_store_item_ids_both_regions PASSED
TestSixSheetsStoreItemIdExactMatch::test_d3_05_long_term_store_item_id PASSED   ← 从 SKIPPED 转 PASSED
TestSixSheetsStoreItemIdExactMatch::test_d3_07_voucher_check_store_item_ids_both_regions SKIPPED   ← 仍 SKIPPED（Task 11 范围）
TestSixSheetsStoreItemIdExactMatch::test_all_real_values_are_pairwise_distinct PASSED
======================== 14 passed, 1 skipped in 1.07s ========================
```

**结论**：`test_d3_05_long_term_store_item_id` 从 Task 3 落地时的 SKIPPED（因
`phase5_d3_05_long_term` 模块不存在）**自动转为 PASSED**（无需改判据文件本身），断言
`SPEC_D305.store_item_id == "D3-lt-rows"` 成立。D3-6/D3-4 两条延续之前任务落地后的 PASSED
状态（未受本任务影响），D3-7 一条继续 SKIPPED（不属本任务范围，正确未受影响）。

### 5.2 Task 2 判据（零回归基线）

```
cwd: backend
命令: python scripts/check/check_sync_provider_golden_digest.py
输出: ✅ golden digest 零回归：26 个 digest 逐个不变
```

**结论**：D3-2（及其余 7 家 contract）的三段 canonical JSON digest 在本任务改动前后逐字节
不变——因为灰度开关 `_INCLUDE_D305_LONG_TERM=False`，`_expansion_sheets_payload()` 在当前
状态下对 D3-5 的贡献恒为空，`build_contract_payload()` 的输出结构与改动前逐字节相同。

### 5.3 `test_d3_expansion.py`：既有判据零回归

```
cwd: backend
命令: python -m pytest tests/workpaper_sync/test_d3_expansion.py -v --tb=short
```

```
test_switches_off_equals_current_state PASSED
test_enabling_d306_adds_one_managed_region PASSED
test_translation_preserves_geometry PASSED
test_store_item_ids_have_no_duplicates PASSED
test_alignment_guard_reports_exact_diff PASSED
test_alignment_guard_passes_when_switch_and_contract_are_both_on PASSED
test_build_contract_payload_unchanged_when_switch_off PASSED
======================== 7 passed in 1.25s ========================
```

**结论**：全部 7 条既有判据（D3-6/D3-4 场景的判据）保持通过，未受本任务新增
`_INCLUDE_D305_LONG_TERM` 开关与 `managed_row_table_specs()` 追加逻辑的影响（新增逻辑是
纯追加分支，不改动既有 D3-6/D3-4 分支的行为）。

### 5.4 全量 D3 回归

```
cwd: backend
命令: python -m pytest tests/workpaper_sync -k "d3 or D3" -v --tb=short
结果: 74 passed, 1 skipped, 8922 deselected in 20.12s
```

覆盖了 `test_d3_06_offline_materialize_and_verify.py`/`test_d3_06_related_party_spec.py`/
`test_d3_expansion.py`/`test_d3_property2_store_item_id_exact_match.py`/
`test_d3_property3_4_dual_zone_baseline.py`/`test_ghost_row_defense.py`/
`test_masked_cell_protection_is_cell_level.py`（D3 entry）/
`test_row_table_engine_core_equivalence.py`[d3]/`test_row_table_engine_equivalence.py`[d3]/
`test_sibling_table_ref_row_shift.py`/`test_task5_d3_performance_baseline.py`/
`test_task75_published_identity_observer.py`（D3 entry）等既有判据全部保持通过，1 个 skip
是 D3-7（不属本任务范围，正确保持跳过）。**没有因本任务的循环层改动引入任何回归。**

### 5.5 文件行数门禁

```
cwd: backend
命令: python scripts/check/check_file_size.py
```

142 个文件超限，与既有基线（Task 6/8 记录的 143 处，本次因未涉及的历史文件计数轻微波动，
与本任务无关）同量级；本任务改动/新建的三个文件（`phase5_d3_05_long_term.py` 130 行 /
`phase5_d3_expansion.py` 194 行 / `phase5_d3_prepaid_receipts.py` 未改动仍 965 行，低于
whitelist 登记的 967 行基线）均**未出现**在超限清单里。

## 六、结论

1. `phase5_d3_05_long_term.py`——**已落地**，`SPEC_D305` 逐项几何/字段均经本任务独立
   openpyxl 复核，与 Task 1 证据完全一致（且本任务额外发现并记录了"9 处公式全部不落在数据
   行本身"这个比 Task 1 转述更精确的结论），`store_item_id="D3-lt-rows"` 逐字对照 Task 3
   判据文件真实值表，行身份 `row_identity_key='rowId'`（UUID 动态行），`formula_columns`
   不传（数据行区间内逐行无公式，`formula_mask` 现算为空 tuple，不是遗漏），
   `footer_carries_total_formula=True`（footer SUM 公式确覆盖全部 3 行数据区，显式传值）。
2. `phase5_d3_expansion.py`——**已改动**（+12 行），新增 `_INCLUDE_D305_LONG_TERM` 灰度开关
   （维持 False）+ `managed_row_table_specs()` 追加 D3-5 逻辑。
3. `phase5_d3_prepaid_receipts.py`——**确认无需改动**（本任务已实测验证而非想当然假设）：
   D3-5 是独立单一 `sheet_key`，`_expansion_sheets_payload()`（Task 8 已重构为按
   `sheet_key` 分组）通用地处理它，无需任何改动即可正确装配 D3-5 的契约 sheet 条目。
4. 灰度开关现状：**关闭**（`_INCLUDE_D305_LONG_TERM: Final[bool] = False`）——本任务只声明
   不激活，是否打开留给 Task 10（阶段 2 验收）决定，理由同 Task 6/Task 8 的处置原则（翻
   开关涉及重生成磁盘契约、打红既有基线判据的假设，超出本任务单方面决定范围）。
5. Property 2（Task 3 判据文件）：`test_d3_05_long_term_store_item_id` **已从 SKIPPED 转为
   PASSED**，其余判据不受影响（D3-7 继续正确 SKIPPED）。
6. Property 1（Task 2 零回归基线脚本）：**验证通过**，26 个 digest 逐个不变。
7. `test_d3_expansion.py` 既有 7 条判据：**全部保持通过**，未受影响。
8. 全量 D3 回归（74 passed, 1 skipped）：**全部保持通过**，未引入任何回归。
