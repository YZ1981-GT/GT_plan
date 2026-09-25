# Requirements — 多 sheet materialize 的 defined-name 位移归一化

**spec 名**: `multi-sheet-materialize-defined-name-shift-normalization`
**类型**: bugfix（correctness-critical，Design-First）
**关联**: `excel-structural-row-insertion-and-shift-aware-verification` / `excel-workbook-wide-row-change-propagation` / `oo-html-writeback-performance`（footer 修复的下游门）

---

## 1. 背景与真实缺陷（实证复现）

一个 workbook 里多张受管 sheet（D4-2 / D4-22 / D4-23 / D4-29 …）由**同一个 adapter** 在一次
`materialize` 里**多趟叠写**进同一份输出 xlsx（`adapters/excel.py::materialize` 的多 binding 分支）。
每趟 `materialize_projection` 为**那一张** sheet 生成自己的 `MaterializePlan`，含那趟自己的
`row_shift` 与 `workbook_row_change`。

真实触发（真实 PG，project `0ec33ac9…` / wp `b3ab3c46…` / entry `xlsx/gt-d4-operating-revenue`，
sheet_key `d4-29-managed`，151 行客户数据）：编辑 D4-29 触发的 combined projection 里
**D4-22（`key_indicator_rows`）与 D4-23（`invoice_compare_rows`）各有 12 个 orphan 行需结构性插行**。
每趟插行时，那趟自己的 `workbook_row_change` **正确地**把 `xl/workbook.xml` 里指向该 sheet 的
own-sheet defined-name 位移了：

- `GT_FOOTER_ANCHOR_D422`: `'重要指标分析表D4-22'!$A$24` → `$A$36`
- `GT_FOOTER_ANCHOR_D423`: `'收入与开具发票金额比较分析D4-23'!$A$24` → `$A$36`
- `_xlnm.Print_Area`(D4-22): `$A$1:$H$29` → `$A$1:$H$41`
- `_xlnm.Print_Area`(D4-23): `$A$1:$K$30` → `$A$1:$K$42`

（逐字节 diff 实证：`xl/styles.xml` 完全不变；上述 4 处是 workbook.xml 仅有的变化，全部是插 12 行的合法后果。）

**缺陷**：最终返回的 `MaterializeResult` 只保留**主 binding（D4-29）那一趟**的 `workbook_row_change`
（`adapters/excel.py::materialize` 的 `dataclasses.replace(primary_result, …)`，三个声明字段随
`primary_result` 原样带出）。sibling 各趟的 `workbook_row_change`（含它们对 workbook.xml own-sheet
defined-name 的合法位移声明）**被丢弃**。

`content_mutation.py` 把 `materialized.workbook_row_change` 传给
`verify_unmanaged_regions`。verify 侧对 `workbook_and_styles` 桶（含 `xl/workbook.xml`）的归一化
**完全依赖** `propagation.propagations` 里是否有 `part="xl/workbook.xml"` 的条目
（`excel_extract.py::unmanaged_region_digest` 的 `propagated_parts` 集合）。主 binding（D4-29，转置表，
无这些 defined-name 位移）的 plan 里没有 D4-22/D4-23 的条目 ⇒ workbook.xml 走逐字节比对 ⇒
判 `adapter_unmanaged_region_drift`（error_code `adapter_unmanaged_region_drift`）。

## 2. 根因收敛（来自现状 grep 确认）

verify 的归一化机制**本身有能力**归一化 workbook.xml（先例：K11 的跨 sheet definedName 传播就是
这么过的）。缺口**唯一**在**声明的保留**：

- **保留缺口**：多 binding materialize 只保留主 binding 的 `workbook_row_change`；sibling 各趟对
  workbook.xml 的合法 defined-name 位移声明没有合并进最终 `MaterializeResult`，因此从未传给 verify。

（注：不存在"生成缺口"。经实证，own-sheet defined-name 如 `GT_FOOTER_ANCHOR_D42x` /
`_xlnm.Print_Area` 是**指向该 sheet 的限定引用**，`scan_reference_carriers` 的
`qualified_only=True` + `propagate_sheets={target_sheet}` **会**把它们扫成 `part="xl/workbook.xml"`
的 `PropagationEntry`，`_write_entries` 也**会**据此正确位移。位移本身正确且已声明——只是那份声明
在多趟合并时被丢了。）

## 3. 需求（EARS）

### R1 sibling 位移声明必须完整传达到 verify
WHEN 一次 materialize 涉及多张受管 sheet 且其中**多张**发生结构性插行，
THE SYSTEM SHALL 使**每一张**发生插行的 sheet 的 workbook.xml defined-name 位移声明
（`PropagationEntry(part="xl/workbook.xml")`）都被 `verify_unmanaged_regions` 消费到，
从而这些合法位移不被判 `adapter_unmanaged_region_drift`。

### R2 不得放宽为"按观测归一化"
THE SYSTEM SHALL 仅按**写盘之前冻结的声明**（各趟 plan 冻结的 `PropagationEntry.ref_before/ref_after`）
归一化 workbook.xml；声明之外的任何 workbook.xml 字节变化 SHALL 仍判漂移。
（即：合并的是各趟**已冻结的声明**，不是事后从 after diff 推断的位移。）

### R3 声明与实测必须对账
WHEN 合并 sibling 位移声明后归一化 workbook.xml，
THE SYSTEM SHALL 保持既有的"逐条逆替换 + 出现次数对账"语义
（`normalise_propagated_part` 的 `reverted == declared`）：产物里缺一条声明的位移、或多一处
未声明但形态相同的改动，都 SHALL 判漂移。

### R4 单 sheet / 零位移路径零回归
WHEN 只有一张受管 sheet，或没有任何 sibling 发生插行，
THE SYSTEM SHALL 与本 spec 之前逐字节相同（纯增量，`workbook_row_change is None` 或只有主 binding
一份时行为不变）。

### R5 主 binding 现有语义不回退
THE SYSTEM SHALL 保留 `adapters/excel.py::materialize` 现有的"三个声明字段以主 binding 为准"里
**除 workbook.xml defined-name 归一化之外**的语义（`row_shift`/`total_formula_rows` 仍按主 binding
用于主 sheet 的 shift-aware cell/structure 归一化；identity 清册仍用主 binding）。本 spec 只补齐
workbook.xml defined-name 这一类**跨全部受管 sheet**的位移声明。

### R5b sibling 自身 worksheet part 的 shift-aware 归一化（真实 E2E 暴露的同源扩大）
WHEN 一次多 sheet materialize 里**主 binding 未插行、而 sibling sheet 插行**，
THE SYSTEM SHALL 让每张**发生插行的 sheet** 的 verify 用**它自己那趟冻结的** `row_shift` /
`total_formula_rows` 对其 worksheet part 的 `managed_sheet_unmanaged_cells` /
`managed_sheet_structure` 做 shift-aware 归一化，不得因"主 binding 不是插行 sheet"而对 sibling
强制 `row_shift=None` ⇒ 把 sibling 的合法插行判 `adapter_unmanaged_region_drift`。
（与 R1 同源:materialize 只保留主 binding 位移声明的保留缺口,此处是它对 worksheet part 的一面。）

### R6 端到端真实验证
THE SYSTEM SHALL 在真实 PG + 真实 substrate（gen-26）上，用真实 D4-29 编辑场景
（sheet_key `d4-29-managed`，D4-22/D4-23 各 12 orphan）跑通 materialize 端到端，
不再出现 `adapter_unmanaged_region_drift`，且合法位移之外的篡改仍被拦。

## 4. 不砍的校验（硬约束，全程不弱化）

- roundtrip 等价（`_assert_roundtrip_equivalent`）
- structure_hash / identity carrier / identity inventory
- footer 两门（anchor stable + formula covers）——含 `oo-html-writeback-performance` 已修的
  sibling footer 扩张
- unmanaged region 的其余 7 个 aspect（managed cell / structure / other sheets / protected /
  shared strings / relationships / other parts）逐字节或既有归一化不动
- `PropagationEntry.__post_init__` 的全部校验、`assert_propagation_declared_exactly` 对账
- final fence / value_type-from-contract

## 5. 验收判据

1. 新增回归测试：多 sheet 契约、多张 sibling 各插行时，合并后的位移声明覆盖每张 sheet 的
   workbook.xml defined-name；**非空守卫**——去掉合并（只留主 binding）时该测试必红。
2. 真实端到端（R6）：materialize 200，不再 `adapter_unmanaged_region_drift`。
3. 篡改仍被拦：人为在 workbook.xml 里多改一处未声明的 defined-name ⇒ 仍判漂移。
4. 焦点回归零新增失败（materialize / shift-aware / row-insertion / D4 dual-sheet 套件）。
