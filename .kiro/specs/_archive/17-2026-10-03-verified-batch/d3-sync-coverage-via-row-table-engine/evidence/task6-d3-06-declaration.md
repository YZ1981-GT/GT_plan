# Task 6 证据记录：`phase5_d3_06_related_party.py` 声明 + 灰度开关

**实施日期**：2026-09-26　**方法**：独立 openpyxl 直读权威模板复核 Task 1 实测值 + 参照
D1-2 / D1 expansion 两个已落地范式 + 判据先行验证。

## 一、新建/改动文件清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/app/services/workpaper_sync/phase5_d3_06_related_party.py` | 新建 | sheet 层薄声明（`SPEC_D306`），照抄 D1-2 结构，行身份改为 `rowId` |
| `backend/app/services/workpaper_sync/phase5_d3_expansion.py` | 新建 | 伴生编排层（灰度开关 + 三个聚合函数 + 对齐守卫），照抄 `phase5_d1_expansion.py` 骨架，裁掉 D1 特有的静态区寄生分支（D3 六张均非 static_region，Task 1 已判） |
| `backend/app/services/workpaper_sync/phase5_d3_prepaid_receipts.py` | 改动（+73 行，869→942 行） | 循环层追加 `_expansion_sheet_row_table_payload()` + `_expansion_sheets_payload()` 两个私有函数 + `build_contract_payload()` 的 `sheets` 列表追加 `*_expansion_sheets_payload()`；D3-2 自身现有代码**一字未改** |
| `backend/tests/workpaper_sync/test_d3_expansion.py` | 新建 | 伴生模块判据测试（7 条，照抄 `test_d1_instrumentation_specs_expansion.py` 骨架并按 D3-6 单区场景裁剪） |

未修改任何模板文件（`D/D3 预收账款.xlsx`）、未修改 Task 3 的判据文件（其
`test_d3_06_related_party_store_item_id` 按设计会在本任务落地后自动从 SKIPPED 转 PASSED，
无需改判据文件本身）。

## 二、`field_specs` 的实测过程（openpyxl 独立复核，不盲信 Task 1 证据）

任务原文要求本任务自行用 openpyxl 直读模板核实（不能只抄 Task 1 的证据文档）。执行了两轮
独立探测：

**第一轮**——表头（行 11）与数据区公式（行 12-17）：

```python
import openpyxl
wb = openpyxl.load_workbook(r'backend/wp_templates/D/D3 预收账款.xlsx', data_only=False)
ws = wb['关联关系及交易检查表D3-6']
```

实测输出（逐字摘录）：

```
max_row 34 max_col 12
--- row 11 header (A..L) ---
A11 '关联方名称'
B11 '关联关系'
C11 '期初余额'
D11 '借方发生'
E11 '贷方发生'
F11 '期末余额'
G11 '发生时间及账龄'
H11 '发生原因（款项性质）'
I11 '索引号'
J11 '备注'
K11 None
L11 None
--- row 12..17 col A..L ---
F12 '=C12+E12-D12'
F13 '=C13+E13-D13'
F14 '=C14+E14-D14'
F15 '=C15+E15-D15'
F16 '=C16+E16-D16'
A17 '合计'
C17 '=SUM(C12:C14)'
D17 '=SUM(D12:D14)'
E17 '=SUM(E12:E14)'
F17 '=SUM(F12:F14)'
--- row 17 (footer) full row A..L ---
A17 '合计'
B17 None
C17 '=SUM(C12:C14)'
D17 '=SUM(D12:D14)'
E17 '=SUM(E12:E14)'
F17 '=SUM(F12:F14)'
G17 None ... L17 None
```

**结论逐项与 Task 1 证据一致**：
- 表头 A-J 逐字：关联方名称/关联关系/期初余额/借方发生/贷方发生/期末余额/发生时间及账龄/
  发生原因（款项性质）/索引号/备注；K/L 为空。
- 数据区 12-16 唯一逐行有公式的列是 **F**，公式模板 `=Cn+En-Dn`（期末余额=期初余额+贷方
  发生-借方发生），公式方向未反（独立核实通过：C 期初 + E 贷方 - D 借方，与业务语义一致）。
- footer 行 17：A17='合计'（纯两字无空格）；SUM 区间只覆盖 `C12:C14`/`D12:D14`/`E12:E14`/
  `F12:F14`（3 行，12-14），**没有覆盖到 15-16 两行**——与 Task 1 记录的"5 行模板占位但 SUM
  只覆盖 3 行"的模板预存缺陷逐字一致。本任务的声明代码**不做任何特殊处理**，按实测的公式
  模板原样声明（`FORMULA_TEMPLATES_D306 = {"F": "=C{r}+E{r}-D{r}"}`），这个缺陷是否会被
  行表引擎的位移归一化机制自动纠正，留给 Task 7 接入验收用真实测试验证。

**第二轮**——候选空列扫描（K/L/M/N/O 全空 + 页眉引用公式确认）：

```python
print('--- K..O across rows 11..17 ---')
# 逐格扫描 K(11)/L(12)/M(13)/N(14)/O(15) 列，rows 11..17
```

实测输出：`done (no output above = all empty)` —— K/L/M/N/O 在行 11-17 全部为 `None`，
独立确认 K 列可用作候选空列（与 Task 1 记录一致，选 K 而非更远的 L/M/N/O，因为 K 是最靠近
数据区 A-J 的候选）。

同时核对了行 3/4 的页眉引用公式（`A3='=底稿目录!A2'`、`D3='=底稿目录!A4'`、
`J3='=底稿目录!F18'` 等），确认这些不是数据行公式，**不进** `formula_columns`——本表数据行
区间（12-16）唯一有公式的列只有 F，与 requirements.md 表格"主公式列 F6 D3 A2"这个坐标速记
（不是逐列枚举）的实际含义一致（F6/D3/A2 分别是公式落点样例坐标，不是"F、D、A 三列都是数据行
公式列"）。

## 三、`formula_mask` 是引擎 property 现算的验证过程

读取 `backend/app/services/workpaper_sync/phase5_row_table_sheet.py` 的
`RowTableSheetSpec` 类定义，确认：

```python
@property
def formula_mask(self) -> tuple[str, ...]:
    """七家实测形态：全为列向区间 `{COL}{FIRST}:{COL}{LAST}`。取代 provider 侧手写 mask 字面量。

    做成 property 而非字段：七家无一例外都是该形态；做成字段会保留「手写 mask 与
    formula_columns 不一致」这个漂移面（design §Components 裁决依据）。
    """
    return tuple(
        f"{col}{self.first_data_row}:{col}{self.last_data_row}"
        for col in self.formula_columns
    )
```

**确认结论**：`formula_mask` 是 `@property` 装饰的现算属性，不是 dataclass 字段，因此
`RowTableSheetSpec(...)` 构造调用**不能**也**不应该**传 `formula_mask=` 参数（传了会因为
`RowTableSheetSpec` 是 `@dataclass(frozen=True)` 且 `formula_mask` 不在字段列表里而报
`TypeError: unexpected keyword argument`）。`SPEC_D306` 的实例化只传了 `formula_columns=("F",)`，
未传 `formula_mask`，与 D1-2 (`SPEC_D102`) 的写法一致。

运行时验证（Python 交互式确认 property 真实现算出预期值）：

```python
>>> from app.services.workpaper_sync.phase5_d3_06_related_party import SPEC_D306
>>> SPEC_D306.formula_mask
('F12:F16',)
```

即 `formula_mask` 由 `formula_columns=("F",)` × 数据行区间 `[first_data_row=12,
last_data_row=16]` 自动导出为 `('F12:F16',)`，与手写字面量完全等价但不需要手写，钉住
design.md Property 5。

## 四、Property 2 判据从 SKIPPED 转 PASSED 的验证（命令+输出）

```
cwd: backend
命令: python -m pytest tests/workpaper_sync/test_d3_property2_store_item_id_exact_match.py -v --tb=short
```

关键输出行：

```
tests/workpaper_sync/test_d3_property2_store_item_id_exact_match.py::TestSixSheetsStoreItemIdExactMatch::test_d3_06_related_party_store_item_id PASSED [ 66%]
tests/workpaper_sync/test_d3_property2_store_item_id_exact_match.py::TestSixSheetsStoreItemIdExactMatch::test_d3_04_analysis_store_item_ids_both_regions SKIPPED [ 73%]
tests/workpaper_sync/test_d3_property2_store_item_id_exact_match.py::TestSixSheetsStoreItemIdExactMatch::test_d3_05_long_term_store_item_id SKIPPED [ 80%]
tests/workpaper_sync/test_d3_property2_store_item_id_exact_match.py::TestSixSheetsStoreItemIdExactMatch::test_d3_07_voucher_check_store_item_ids_both_regions SKIPPED [ 86%]
tests/workpaper_sync/test_d3_property2_store_item_id_exact_match.py::TestSixSheetsStoreItemIdExactMatch::test_all_real_values_are_pairwise_distinct PASSED [ 93%]
...
======================== 12 passed, 3 skipped in 1.07s ========================
```

**结论**：`test_d3_06_related_party_store_item_id` 从 Task 3 落地时的 SKIPPED（因
`phase5_d3_06_related_party` 模块不存在）**自动转为 PASSED**（无需改判据文件），其余三条
声明级判据（D3-4/D3-5/D3-7）继续 SKIPPED（对应模块确实尚未声明，Task 8/9/11 的范围），
9 条合成级判据（`TestMutationDetectsWrongKeyName`）全部保持 PASSED，未受任何影响。

## 五、Property 1 零回归基线验证（命令+输出）

```
cwd: backend
命令: python scripts/check/check_sync_provider_golden_digest.py
```

输出：

```
✅ golden digest 零回归：26 个 digest 逐个不变
```

**结论**：D3-2（及其余 7 家 contract：b60/d1/d2/d4/d5/d6/d7）的三段 canonical JSON digest
（`build_contract_payload()` / `build_store_projection()` / `instrumentation_spec(s)()`）
在本任务改动前后逐字节不变——尽管 `build_contract_payload()` 的实现被修改（追加了
`_expansion_sheets_payload()` 调用），因为灰度开关 `_INCLUDE_D306_RELATED_PARTY=False`，
该函数在当前状态下恒返回空列表，`sheets` 列表的输出结构与改动前逐字节相同。

补充验证（本任务新增的判据测试之一，从另一角度直接断言契约结构而非只看 digest）：

```
test_build_contract_payload_unchanged_when_switch_off PASSED
```

该测试直接读取 `ENTRY.build_contract_payload()["sheets"]`，断言长度为 1 且唯一项的
`sheet_key == ENTRY.SHEET_KEY`（即 D3-2 自身），与开关关闭前的契约形状完全一致。

## 六、伴生模块 `phase5_d3_expansion.py` 的判据测试运行结果

新建 `backend/tests/workpaper_sync/test_d3_expansion.py`（7 条测试，照抄
`test_d1_instrumentation_specs_expansion.py` 骨架并按 D3-6 单区场景裁剪，不含 D1 特有的
静态区寄生测试）：

```
cwd: backend
命令: python -m pytest tests/workpaper_sync/test_d3_expansion.py -v --tb=short
```

```
tests/workpaper_sync/test_d3_expansion.py::test_switches_off_equals_current_state PASSED
tests/workpaper_sync/test_d3_expansion.py::test_enabling_d306_adds_one_managed_region PASSED
tests/workpaper_sync/test_d3_expansion.py::test_translation_preserves_geometry PASSED
tests/workpaper_sync/test_d3_expansion.py::test_store_item_ids_have_no_duplicates PASSED
tests/workpaper_sync/test_d3_expansion.py::test_alignment_guard_reports_exact_diff PASSED
tests/workpaper_sync/test_d3_expansion.py::test_alignment_guard_passes_when_switch_and_contract_are_both_on PASSED
tests/workpaper_sync/test_d3_expansion.py::test_build_contract_payload_unchanged_when_switch_off PASSED
======================== 7 passed in 1.21s ========================
```

覆盖：①开关全 False ⇒ 与现状等价（扩容面清单为空，store item 只有 `D3-det-rows`）②打开
D3-6 开关 ⇒ 受管区 1→2，`store_item_id` 集合含 `D3-rp-rows` ③翻译正确性（几何逐项相等）
④两方向 store item 无重复 ⑤对齐计数守卫在不对齐时 fail-closed 且精确报差集（D4-35 事故
形态）⑥**开关与契约同时打开时对齐守卫通过**（第 6 条是本任务额外补充的集成性判据，超出
D1 同名测试的覆盖范围，用于验证扩容面 spec 集合与循环层追加的契约 sheets 始终同步增减）
⑦开关关闭时契约结构本身的可读性断言。

**过程中发现并修复的一个真实 bug**（如实记录）：第 6 条测试首次运行时失败——
`_expansion_sheets_payload()` 最初把 sheet 级 `locator.anchor` 误填成原始单元格坐标
`f"A{spec.header_row}"`（即 `"A11"`），触发 `ContractCarrierGateError`：

```
结构锚点 'A11' 未在 onlyoffice_excel_identity_carrier_contract.json 登记
（已登记 ['defined_name', 'defined_name_ref', 'excel_table', 'excel_table_sheet_association', ...]）
```

根因：`locator.anchor` 必须是已登记的结构锚点关键字（`TABLE_SHEET_ANCHOR =
"excel_table_sheet_association"`，D3-2 自身沿用的同一个值），不是原始单元格坐标——这是 sheet
级"载体识别锚点"与 table 级"表内定位锚点"（`_expansion_sheet_row_table_payload` 里
`"anchor": f"A{spec.header_row}"`，这个是对的，属于 table payload 内部字段）两个不同概念，
本次改动最初把二者混淆了。修复：`_expansion_sheets_payload()` 的 `locator.anchor` 改用
`from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR`，与 D3-2 自身
`build_contract_payload()` 里 `"locator": {"anchor": TABLE_SHEET_ANCHOR}` 完全一致。修复后
全部 7 条测试通过，且这条判据（第 6 条）本身就是防止此类混淆复发的守护测试——它比任务原文
要求的判据范围（开关 False/True 两态的基础断言）多验证了一层"契约实际能否被 `parse_contract`
成功解析"，属于本任务主动加强的部分。

## 七、其余全量 D3 回归验证（超出任务要求的完成标准，作为额外确认）

```
cwd: backend
命令: python -m pytest tests/workpaper_sync -k "d3 or D3" -v --tb=short
结果: 62 passed, 3 skipped, 8918 deselected in 21.15s
```

覆盖了 `test_d3_property3_4_dual_zone_baseline.py`（Task 4 基线，6 条全 PASSED，未受影响）、
`test_row_table_engine_core_equivalence.py`/`test_row_table_engine_equivalence.py`（D3
provider 与引擎等价性判据，PASSED）、`test_masked_cell_protection_is_cell_level.py`（D3
entry 的格级保护判据，PASSED）、`test_ghost_row_defense.py`（D3 幽灵行防护，PASSED）、
`test_task5_d3_performance_baseline.py`（Task 5 性能基线，含真实 `adapter_registered=False`
现状登记判据，PASSED）、`test_task75_published_identity_observer.py`（D3 published identity
观察者判据，PASSED）等既有判据全部保持通过，没有因本任务的循环层改动引入任何回归。

同时运行了全仓文件行数门禁（`check_file_size.py`）——确认本任务新建/改动的三个文件均不在
超限清单内（清单里现存 143 处超限均为本任务之前已存在的历史文件，与本任务无关）。
`phase5_d3_prepaid_receipts.py` 改动后 942 行，仍低于 whitelist 登记的 967 行基线。

## 八、结论

1. `phase5_d3_06_related_party.py`——**已落地**，`SPEC_D306` 逐项几何/字段/公式均经本任务
   独立 openpyxl 复核，与 Task 1 证据完全一致，`store_item_id="D3-rp-rows"` 逐字对照 Task 3
   判据文件真实值表，行身份 `row_identity_key='rowId'`（UUID 动态行，非照抄 D1-2 的
   `'key'`），`formula_mask` 未手写（确认为引擎 property 现算）。
2. `phase5_d3_expansion.py`——**新建**（伴生编排层），理由：D3 entry 模块当前 869 行（改动后
   942 行）虽未顶穿 967 行 whitelist 基线，但为与 D1/E1 架构范式一致、便于 Task 8/9/11
   复用同一套灰度开关/聚合函数骨架，选择新建而非直接塞进 entry 模块本体。
3. `phase5_d3_prepaid_receipts.py`——**小幅改动**（+73 行），只追加了 sheet 清单拼装逻辑
   （`_expansion_sheet_row_table_payload` + `_expansion_sheets_payload` 两个私有函数 +
   `build_contract_payload()` 的 `sheets` 列表追加），D3-2 自身现有代码逐字未改，golden
   digest 门确认零回归。
4. 灰度开关现状：**关闭**（`_INCLUDE_D306_RELATED_PARTY: Final[bool] = False`）——本任务
   只声明不激活，是否打开留给 Task 7（D3-6 接入验收）决定。
5. Property 2（Task 3 判据文件）：`test_d3_06_related_party_store_item_id` **已从 SKIPPED
   转为 PASSED**，其余判据不受影响。
6. Property 1（Task 2 零回归基线脚本）：**验证通过**，26 个 digest 逐个不变。
