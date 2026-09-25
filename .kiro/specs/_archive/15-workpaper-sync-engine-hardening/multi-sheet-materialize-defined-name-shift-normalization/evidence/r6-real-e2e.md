# Evidence — 多 sheet materialize defined-name 位移归一化（R6 真实端到端）

## 环境
- 真实后端 127.0.0.1:9980 + 真实 PG（audit_platform）
- project `0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49` / wp `b3ab3c46-828f-4f48-950e-aee9bbdc923f`
- entry `xlsx/gt-d4-operating-revenue`（多 sheet 契约:D4-2/D4-3/D4-5/D4-21~28/D4-29…）
- sheet_key `d4-29-managed`（转置客户表,151 行）
- substrate gen-26（数据:D4-2 已 12-30/footer31;D4-22/D4-23 仍 12-23/footer24）

## 缺陷复现（修复前,逐层剥出）
1. 初始:`materialize` 500 `excel_materialize_footer_formula_range_stale`
   - DIAG:sibling D4-23 apply-phase gate,`total_formula_rows=(31,)`（错,应 24）
   - 根因:`_plan_row_shift` 取裸主键 `GT_FOOTER_ROW=31`（D4-2）而非本表 `GT_FOOTER_ROW_D423=24`
   - 修复（oo-html-writeback-performance）:按 `region.table_key` 的 sheet_key 取 `_resolve_frozen_footer_row`
2. footer 修复后:`materialize` 500 `adapter_unmanaged_region_drift` on `workbook_and_styles`
   - 逐字节 diff:styles.xml 不变;workbook.xml 仅 4 处变化,全是插 12 行合法后果:
     - `GT_FOOTER_ANCHOR_D422` `$A$24`→`$A$36` / `GT_FOOTER_ANCHOR_D423` `$A$24`→`$A$36`
     - `_xlnm.Print_Area`(D4-22) `$H$29`→`$H$41` / (D4-23) `$K$30`→`$K$42`
   - 根因:多 binding materialize 只保留主 binding(D4-29)的 workbook_row_change,sibling 各趟
     对 workbook.xml own-sheet defined-name 的合法位移声明被丢 ⇒ verify 逐字节判漂移
   - 修复:`MaterializeWorkbookChangeSet` + `merge_workbook_row_change_propagations` 并集去重
3. workbook 合并后:`materialize` 500 `adapter_unmanaged_region_drift` on `managed_sheet_unmanaged_cells`
   - DIAG:主 binding=`revenue_detail_rows`(D4-2) is_primary=True 但 row_shift=None（未插行）;
     报错停在 `key_indicator_rows`(D4-22) is_primary=False row_shift=None（插了 12 行却拿 None）
   - 根因（同源扩大）:verify 把 row_shift 只给主 binding,而**主 binding 不是插行的 sheet**;
     sibling 插行 sheet 的 managed_sheet_* 桶漏 shift-aware 归一化
   - 修复:`MaterializeResult.per_table_shift`（table_key→(row_shift,total_formula_rows)）+
     verify 按 `region.table_key` 分派各表自己的 shift

## 修复后（据实）
```
store-projection 200  field_count 305  row_count 151  overlay True
pending-mutations 200
materialize 200  replayed=False   ← 真实产出新 representation,三门全过
```
不再出现 `footer_formula_range_stale` / `adapter_unmanaged_region_drift`。

## 守卫
- 批次1 merge 单元:并集/去重/冲突/None（6 passed,非空守卫）
- 批次3 live e2e `tests/test_multi_sheet_materialize_e2e_live.py`:真实链路 materialize 200;
  三修复任一回退 ⇒ 500 ⇒ 红（非空守卫成立,已本地 1 passed）
- footer 修复守卫:`test_d4_dual_sheet_managed_tables.py` 4 新测试（含 stash 验证的集成守卫）
- 焦点回归 272 passed,失败项全 pre-existing（逐一 stash 验证,与本改动无关）

## 不砍校验（复核）
- roundtrip / structure_hash / identity carrier+inventory / footer 两门 / 其余 7 个 unmanaged aspect
  / PropagationEntry 校验 / 归一化"逐条逆替换+reverted==declared 对账" / final fence —— 全程未弱化。
  归一化用的是**写盘前冻结的声明**（各趟 PropagationEntry / per-table row_shift）,非 after 观测;
  声明之外的 workbook.xml / worksheet 改动仍判漂移。
```
