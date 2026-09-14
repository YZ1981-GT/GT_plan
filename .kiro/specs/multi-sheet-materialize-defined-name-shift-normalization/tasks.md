# Tasks — 多 sheet materialize 的 defined-name 位移归一化

> 依赖:`oo-html-writeback-performance` 的 footer 修复（已完成）。
> 硬约束:全程不砍任何校验（见 requirements §4）。每个实现任务后必跑相关焦点回归。

## 批次 1:聚合载体 + 合并器（纯函数,零风险）✅

- [x] 1. 在 `excel_workbook_row_change.py` 新增只读聚合类型 `MaterializeWorkbookChangeSet`
  - 字段仅 `propagations: tuple[PropagationEntry, ...]`（frozen dataclass）
  - `__post_init__`:`assert_no_mutation_surface`（零写入面）+ 条目身份去重后不得有冲突
  - docstring 写明:verify 只消费 `.propagations`（鸭子接口同 `WorkbookRowChangePlan`）;不含
    at/count/kind（多 sheet 无法用单标量诚实表达）;apply 不消费它

- [x] 2. 在同文件新增纯函数 `merge_workbook_row_change_propagations(plans)`
  - 入参:`Iterable[WorkbookRowChangePlan | None]`（各趟 materialize 的 workbook_row_change）
  - 收集**所有** part 的 `PropagationEntry` 并集（不只 workbook.xml——保 R5:引用侧 sheet 条目
    也要保留,否则主 binding 的跨 sheet 传播归一化回退）
  - 按 `(part, locator, ref_before, ref_after)` 去重
  - **冲突检测**:同一 `(part, ref_before)` 出现两个不同 `ref_after` ⇒ 抛 `PropagationDriftError`
    （两张 sheet 声称把同一处位移到不同行 = 不自洽）
  - 全空 ⇒ 返回 `None`（保持零传播路径,R4）;否则返回 `MaterializeWorkbookChangeSet`

- [x] 3. 批次 1 单元测试（`tests/workpaper_sync/test_multi_sheet_workbook_change_merge.py`,6 passed）
  - 并集:两个 plan 各含不同 part 的条目 ⇒ 合并后条目数 = 两者之和
  - 去重:两个 plan 含相同 `(part,locator,ref_before,ref_after)` ⇒ 只保留一份
  - 冲突:同 `(part, ref_before)` 两个不同 `ref_after` ⇒ 抛 `PropagationDriftError`
  - 全 None ⇒ 返回 None
  - `MaterializeWorkbookChangeSet` 零写入面（`assert_no_mutation_surface` 不抛）

## 批次 2:接线到 materialize 返回值 ✅

- [x] 4. 改 `adapters/excel.py::materialize` 多 binding 分支（收集 trip_changes + merge，import Any 已在）
  - 循环里收集每趟 `step.workbook_row_change`（非 None）到 `trip_changes: list`
  - 返回前 `merged = merge_workbook_row_change_propagations(trip_changes)`
  - `dataclasses.replace(primary_result, ..., workbook_row_change=merged)`
  - 单 binding 分支(`len(bindings)==1`)不动（R4）
  - 🔴 保留现有注释精神:`row_shift`/`total_formula_rows`/identity 清册仍按 primary 带出;
    本改动只把 `workbook_row_change` 从"仅主 binding"升级为"全趟 propagations 并集"

- [x] 5. 确认三处消费点只读 `.propagations`（excel_extract.py:1717 `propagation.propagations`;
    normalise_propagated_part `plan.propagations`;adapters/excel.py verify 只转手 propagation）——
    `MaterializeWorkbookChangeSet` 鸭子兼容,无需改。

## 批次 2b:per-sheet 位移声明保留 + verify 按 sheet 分派（真实 E2E 暴露的同源扩大,见 design §4b）

- [x] 5a. `MaterializeResult` 新增 `per_table_shift: Any = None`
- [x] 5b. `adapters/excel.py::materialize` 循环收集每趟 row_shift/total_formula_rows 到 per_table
- [x] 5c. `content_mutation.py` verify 调用点传入 `per_table_shift=materialized.per_table_shift`
- [x] 5d. `adapters/excel.py::verify_unmanaged_regions` 按 region.table_key 分派各表 row_shift
- [x] 5e. 真实 E2E 复跑:**materialize 200**（replayed=False,真实产出新 representation）

## 批次 3:集成守卫 + 真实端到端 ✅

- [x] 6. 集成守卫(非空):`tests/test_multi_sheet_materialize_e2e_live.py`（live,skipif 后端不在线）
  - 真实 D4-29 编辑 → materialize 200;三修复任一回退 ⇒ 500 ⇒ 本测试红（非空守卫成立）
  - 批次 1 merge 单元测试另含并集/去重/冲突/None 的非空守卫（6 passed）

- [x] 7. 真实端到端(R6):真实 PG + gen-26 substrate + sheet_key `d4-29-managed`
  - **materialize 200**（replayed=False），不再 `adapter_unmanaged_region_drift`;
    三门全过:footer 扩张 + workbook.xml defined-name 合并 + sibling worksheet per-sheet shift

- [x] 8. 焦点回归零新增失败:272 passed（merge/d4-dual/task38/workbook-row-change insert+apply+
  zero-regression/shift-aware）。失败项全 pre-existing（逐一 stash 验证）:
  test_every_listed_structure_lands_in_exactly_one_bucket（ROW_BEARING_STRUCTURES 16vs15）/
  test_behaviour_matches_frozen_baseline（zero-regression baseline drift）/ task15 的
  test_no_router_or_carrier_library_in_this_task（content_mutation 已含 "docx"）+
  test_successful_stage_publishes_both_artifacts + test_unmanaged_verification_is_fed(...structure_anchors)
  + workbook_row_change_wiring test_propagation_precedes_cell_patch —— 均与本改动无关。
  另:task15 fake adapter 已同步加 per_table_shift kwarg + 断言集（BP-23 喂声明纪律）。

## 批次 4:收尾 ✅

- [x] 9. 清理临时探针脚本;evidence 落 `evidence/r6-real-e2e.md`
- [x] 10. 更新 `.kiro/specs/INDEX.md`（新增本 spec 状态行）
