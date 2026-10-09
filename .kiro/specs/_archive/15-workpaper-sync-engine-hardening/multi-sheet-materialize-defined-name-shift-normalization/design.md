# Design — 多 sheet materialize 的 defined-name 位移归一化

## 0. 现状 grep 确认（设计前实证，全部带文件:行号）

| 事实 | 位置 | 结论 |
|---|---|---|
| 多 binding materialize 多趟叠写，返回 `dataclasses.replace(primary_result, …)`，三个声明字段随 primary 带出 | `adapters/excel.py::materialize` L350-411 | sibling 各趟的 `step.workbook_row_change` 被丢弃（**保留缺口**） |
| 每趟 `step = materialize_projection(...).result`，`step` 是 `MaterializeResult`，带那趟自己的 `workbook_row_change` | `adapters/excel.py` L365-388；`base.py::MaterializeResult` L390-430 | 合并的**输入现成**：循环里逐趟可拿到 |
| 每趟 plan 的 `workbook_row_change` 由 `plan_workbook_row_change_for_insert(managed_sheet_name=region.sheet_name)` 生成 | `excel_materialize.py` L1791-1803 | 声明按那趟 sheet 冻结，`ref_before/ref_after` 由执行侧同一改写器生成 |
| own-sheet defined-name（`GT_FOOTER_ANCHOR_D42x` / `_xlnm.Print_Area`）是**指向该 sheet 的限定引用**，`scan_reference_carriers(qualified_only=True, propagate_sheets={target_sheet})` 会扫成 `part="xl/workbook.xml"` 条目 | `excel_workbook_row_change.py::scan_reference_carriers` L1124；`propagate_defined_names` L1442；`build_propagation_entry` L1536 | **无生成缺口**：位移声明本就正确生成 |
| `_write_entries` 跳过 `plan.sheet_part`，对 `xl/workbook.xml` 等其余 part 按 `plan.propagations` 逐条改 | `excel_materialize.py::_write_entries` L2157-2216 | 位移在 apply 期正确执行（after diff 已实证 $A$24→$A$36） |
| verify 侧 `unmanaged_region_digest` 只按 `{entry.part for entry in propagation.propagations}` 决定归一化哪些 part；`_propagation_normalised_digest` → `normalise_propagated_part` 只读 `plan.propagations` | `excel_extract.py` L1716-1738、L1228-1251；`excel_workbook_row_change.py::normalise_propagated_part` L1895 | **verify 只消费 `.propagations`**——不读 `at/count/managed_sheet_name` |
| `verify_unmanaged_regions`（唯一生产调用点）三参数取自 `materialized` | `content_mutation.py` L1678-1686 | 只要 `materialized.workbook_row_change.propagations` 含各 sheet 条目即可 |
| adapter 层 verify 对 sibling binding 置 `row_shift=None`，但 `propagation` **对所有 binding 都传同一个** | `adapters/excel.py::verify_unmanaged_regions` L570-590 | 归一化 workbook.xml 用的是这个统一 propagation ⇒ 只要它 `.propagations` 全了即可，无需按 binding 分派 |

**根因单点**：保留缺口。verify 机制无需改；只需让最终 `materialized.workbook_row_change.propagations`
包含**每一张发生插行的 sheet** 的 workbook.xml defined-name 条目。

## 1. 方案选择

### 采用：聚合各趟 workbook.xml propagations 到一个"合并声明"载体

在 `adapters/excel.py::materialize` 多 binding 循环里，收集每趟 `step.workbook_row_change`
（非 None 的），把它们的 `propagations` 里 **`part == "xl/workbook.xml"`** 的条目按身份去重后并集，
构造一个供 verify 消费的**合并 propagation 载体**，挂到返回的 `MaterializeResult.workbook_row_change`。

**为什么只并 workbook.xml 条目**：sibling sheet 自己的 worksheet part（`xl/worksheets/sheetN.xml`）
由该 sheet 自己的 binding 在 verify 时作为 `managed_sheet_*` aspect（shift-aware）或
`extra_managed_sheet_parts` 处理，**不进** `other_sheet_parts` 逐字节桶
（`adapters/excel.py` verify 循环 L560-590 + `extra_managed_sheet_parts`）。跨 sheet 引用侧
sheet 的传播条目仍由主 binding 那趟负责（现状不动）。真正无人认领的**只有 workbook.xml 里
sibling own-sheet defined-name**这一类——故只并这一类，最小化 blast radius。

### 合并载体的形态

verify 只读 `.propagations`（实证）。但 `WorkbookRowChangePlan.__post_init__` 强校验
`at/count/kind/managed_sheet_name`，一个实例无法表达多 sheet。两个候选：

- **候选 A（采用）**：以**主 binding 的 plan 为基**，用 `dataclasses.replace` 把它的
  `propagations` 换成"主 binding 原有 propagations ∪ 各 sibling 的 workbook.xml 条目"。
  主 plan 的标量字段（at/count/managed_sheet_name = D4-29 的）保持合法，verify 不读它们。
  - 若主 binding 那趟 `workbook_row_change is None`（D4-29 转置表通常无跨 sheet 传播）：
    则需要一个"仅承载 propagations、标量字段填一个合法占位"的实例。为避免占位语义污染，
    改用**候选 B**。
- **候选 B（采用为主实现）**：新增一个**只读聚合类型** `MaterializeWorkbookChangeSet`
  （dataclass，字段仅 `propagations: tuple[PropagationEntry, ...]`），verify 侧的
  `unmanaged_region_digest` / `normalise_propagated_part` 只用 `.propagations` 属性
  （鸭子类型，两者都已只读该属性）。materialize 返回这个聚合类型代替单个 plan。
  - 优点：语义诚实（"这是一次多 sheet materialize 的全部 workbook.xml 位移声明集合"，
    没有虚假的单 sheet `at/count`）；不触碰 `WorkbookRowChangePlan` 的校验。
  - 需确认 verify 两处消费点只用 `.propagations`（**已实证**：`normalise_propagated_part`
    `[e for e in plan.propagations if e.part == part]`；`unmanaged_region_digest`
    `{entry.part for entry in propagation.propagations}`）。

**裁定**：采用**候选 B**。新增 `MaterializeWorkbookChangeSet(propagations=...)` 只读聚合类型，
放在 `excel_workbook_row_change.py`（与 `WorkbookRowChangePlan` 同源）。它**不是** plan，不含
`at/count/kind`——诚实表达"这是给 verify 的、跨多 sheet 的 workbook.xml 位移声明并集"。
apply 侧不消费它（apply 仍在每趟内用各自的 `plan.workbook_row_change` 逐趟执行，现状不动）。

### 拒绝的方案

1. **让 verify 从 after diff 反推 workbook.xml 位移** —— 违反 R2（让被检查对象自证合法）。
2. **把 workbook.xml 整个排除出 unmanaged 校验** —— 关掉一整类篡改检测，违反"不砍校验"。
3. **强行把多 sheet 塞进一个 `WorkbookRowChangePlan`**（伪造 at/count）—— 校验会红或语义谎报。
4. **在 `scan_reference_carriers` 里额外扫 own-sheet defined-name** —— 无生成缺口，改这里是
   南辕北辙（生成本就正确）。

## 2. 改动点（最小集）

### 2.1 `excel_workbook_row_change.py`：新增聚合类型
```python
@dataclass(frozen=True)
class MaterializeWorkbookChangeSet:
    """一次多 sheet materialize 的 workbook.xml 位移声明**并集**（只读，零写入面）。

    verify 只消费 `.propagations`（与 WorkbookRowChangePlan 同鸭子接口）；不含 at/count/kind
    —— 多 sheet 各有自己的插行，单一标量无法诚实表达。apply 不消费它（apply 仍逐趟用
    各自 plan.workbook_row_change）。
    """
    propagations: tuple[PropagationEntry, ...]

    def __post_init__(self) -> None:
        assert_no_mutation_surface(self, label="MaterializeWorkbookChangeSet")
        # 条目身份唯一（part+locator+ref_before+ref_after），去重后不得再有冲突声明。
```
- 提供一个构造器 `merge_workbook_defined_name_changes(plans, *, part="xl/workbook.xml")`：
  从多个 `WorkbookRowChangePlan | None` 收集 `part==workbook.xml` 的 `PropagationEntry`，
  按 `(part, locator, ref_before, ref_after)` 去重，返回 `MaterializeWorkbookChangeSet`
  （空则返回 None，保持零传播路径）。
  - **冲突检测**：同一 `(part, ref_before)` 若出现两个不同 `ref_after` ⇒ 抛
    `PropagationDriftError`（两张 sheet 声称把同一处 defined-name 位移到不同行 = 不自洽）。

### 2.2 `adapters/excel.py::materialize` 多 binding 分支：收集 + 合并
- 循环里除 `primary_result` / `last_result` 外，收集 `sibling_plans: list = []`，
  逐趟 `if step.workbook_row_change is not None: sibling_plans.append(step.workbook_row_change)`
  （含主 binding 那趟）。
- 返回前：
  ```python
  merged = merge_workbook_defined_name_changes(sibling_plans)  # None or MaterializeWorkbookChangeSet
  return dataclasses.replace(primary_result, ..., workbook_row_change=merged_or_primary)
  ```
  - `merged` 语义：把**所有趟**的 workbook.xml own-sheet defined-name 条目并起来。
  - 若同时主 binding 的 `workbook_row_change` 还含**非 workbook.xml**（引用侧 sheet）条目怎么办?
    —— 见 2.3：那些条目由现有"主 binding propagation 传所有 binding"的路径消费，而 verify 侧
    `other_sheet_parts` 桶的归一化也只看 `propagation.propagations` 的 part。因此 merged
    **必须同时保留主 binding 的引用侧 sheet 条目**，否则回退 R5。故 `merge_*` 收集**全部** part
    的条目（不只 workbook.xml），只是**去重 + 冲突检测**；命名保留但语义是"并所有趟的所有传播条目"。
    - 修正 2.1：`merge_workbook_defined_name_changes` 不按 part 过滤，收集所有 `PropagationEntry`
      并集去重。（workbook.xml 是其中一类；引用侧 sheet 条目一并保留，保证 R5 不回退。）

### 2.3 `content_mutation.py`：无需改
`verify_unmanaged_regions(propagation=materialized.workbook_row_change)` 现状即可——它拿到的
是聚合后的 `.propagations`，鸭子接口一致。

### 2.4 `excel_extract.py` / `adapters/excel.py::verify_unmanaged_regions`：无需改
两处消费点已只用 `.propagations`（实证）。`MaterializeWorkbookChangeSet` 鸭子兼容。

## 3. 正确性论证（对齐 R1-R5）

- **R1**：merged 含每张插行 sheet 的 workbook.xml 条目 ⇒ verify `propagated_parts` 含
  `xl/workbook.xml` ⇒ 归一化生效。
- **R2/R3**：合并的是各趟**冻结的 `PropagationEntry`**（`ref_before/ref_after` 计划期生成），
  `normalise_propagated_part` 的"逐条逆替换 + reverted==declared 对账"语义原样复用；
  未声明的 workbook.xml 改动逆替换碰不到 ⇒ 仍判漂移。
- **R4**：单 sheet 走 `len(bindings)==1` 分支，不进合并；零位移时各趟 `workbook_row_change`
  皆 None ⇒ `merge_*` 返回 None ⇒ 逐字节路径（现状）。
- **R5**：`row_shift`/`total_formula_rows`/identity 清册仍按 primary 带出（不动）；合并只加
  workbook.xml + 引用侧的**声明并集**，不改主 binding 的 cell/structure 归一化口径。

## 4. 测试策略（对齐验收 1-4）

1. **单元**：`merge_workbook_defined_name_changes` 并集 + 去重 + 冲突检测（同 ref_before
   两个不同 ref_after ⇒ 抛）。
2. **集成（非空守卫）**：构造两张 sibling 各插行的多 sheet 场景，跑 adapter `materialize` +
   `verify_unmanaged_regions`：
   - 合并后 → `equivalent=True`；
   - 去掉合并（只留 primary 的 workbook_row_change）→ workbook.xml 判漂移（红）。证明守卫非空。
3. **篡改仍被拦**：在 after 的 workbook.xml 里多改一处未声明 defined-name ⇒ 仍 `equivalent=False`。
4. **真实端到端（R6）**：真实 PG + gen-26 substrate + d4-29-managed，materialize 200。
5. **焦点回归**：materialize / shift-aware / row-insertion / D4 dual-sheet 套件零新增失败。

## 4b. 真实端到端暴露的范围扩大（实施中发现,诚实记录）

批次 1/2（workbook.xml defined-name 合并）实施后跑真实 E2E（gen-26 + d4-29-managed），
`workbook_and_styles` 漂移**已消失**（合并生效），但暴露出**同源的更广一环**：

**DIAG 实测**（`adapters/excel.py::verify` 循环）：
```
binding=revenue_detail_rows  sheet6  is_primary=True   row_shift=None   ← 主 binding D4-2 本次没插行
binding=key_indicator_rows   sheet30 is_primary=False  row_shift=None   ← D4-22 真插了 12 行,却拿 None
```
报错：`managed_sheet_unmanaged_cells: before 130 → after 185`（D4-22 sheet30）。

**根因扩大**：`adapters/excel.py::verify_unmanaged_regions` 把 `row_shift`/`total_formula_rows`
**只给主 binding**（`binding.table_key == self.binding.table_key ? 值 : None/()`）。但多 sheet 场景里
**主 binding 不一定是发生插行的 sheet**——真实场景主 binding 是 D4-2（未插行），真正插行的是
sibling D4-22/D4-23。于是：
- 主 binding 拿到 `row_shift` 但它没插行（无害，恰好 None 也行）；
- sibling **插了行**却被强制 `row_shift=None` ⇒ 它自己 worksheet part 的
  `managed_sheet_unmanaged_cells` / `managed_sheet_structure` 因插行（130→185）没做 shift-aware
  归一化 ⇒ 判漂移。

这与 workbook.xml defined-name 是**同一个保留缺口**的两个面：materialize 只保留主 binding 那趟的
`row_shift`/`total_formula_rows`，sibling 各趟的被丢。

### 扩大后的方案:per-sheet 位移声明保留 + verify 按 sheet 分派

1. **`MaterializeResult` 新增 per-table 位移声明映射**（`Any = None`，默认不破坏 Word/单 sheet）：
   `per_table_shift: Mapping[str, tuple[row_shift, total_formula_rows]] | None`
   —— 键是 `table_key`，值是那趟冻结的 `(row_shift, total_formula_rows)`。
   仅当某趟真有 `row_shift` 时登记。
2. **`materialize` 多 binding 循环**：收集每趟 `step.row_shift`/`step.total_formula_rows`（非 None）到
   `per_table` 字典，返回时 `dataclasses.replace(..., per_table_shift=per_table or None)`。
   主 binding 的 `row_shift`/`total_formula_rows` 标量字段**仍保留**（向后兼容 + 单 sheet 路径）。
3. **`adapters/excel.py::verify_unmanaged_regions`**：改为按 `region.table_key` 从
   `materialized.per_table_shift` 取**那张 sheet 自己**的 `(row_shift, total_formula_rows)` 传入；
   `per_table_shift is None` 时回退现状（主 binding 标量 + sibling None，单 sheet 不变）。
   - 需要 verify 能拿到 `per_table_shift`：`content_mutation.py` 调用点把它一并传入
     （新增一个可选入参，默认 None，纯增量）。
4. workbook.xml defined-name 合并（批次 1/2）保持不变——它解决 `workbook_and_styles` 桶，
   本扩大解决各 sibling 自己 worksheet part 的 `managed_sheet_*` 桶。两者互补。

### 为什么不是"把所有 sheet 的 row_shift 合成一个"

`row_shift` 是**单张 sheet 的插行计划**（insert_at/count/style_from/table_key），多张 sheet 各不同，
无法合成一个。`managed_sheet_*` 归一化本就是 per-region（`unmanaged_region_digest` 对
`region.sheet_part` 单独算），所以正确做法是**按 region 分派各自的 row_shift**，而不是合并。

## 5. 风险与回滚

- 风险：`MaterializeWorkbookChangeSet` 鸭子替换 `WorkbookRowChangePlan` 传入 verify——若某处
  verify 路径**读了 `.propagations` 以外**的字段则 AttributeError。已实证两处消费点只读
  `.propagations`；测试 4 真实链路兜底。
- 回滚：改动集中在 `materialize` 返回值组装 + 新增一个只读类型 + 一个纯函数合并器，
  独立 commit + tag 可回退。
