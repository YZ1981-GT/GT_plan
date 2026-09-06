# 变异清单交接：`mutate_excel_row_shift_guards.py`（B → E）

**spec**: `excel-structural-row-insertion-and-shift-aware-verification`（Task 20 / N3）
**日期**: 2026-09-04
**交接理由**: 分工书 §2 把 `backend/scripts/diagnose/mutate_*.py` 判给 **E**（判据治理），
B 行的文件面只有五个生产文件。本 spec 的 tasks.md 把 N3 写成 B 的产物，与 §2 冲突 ——
按 §2 执行：**B 提供清单与预期态，E 写文件并统一四态判读标准**。

---

## 已实测验证：28 条锚点全 RED

清单不是推测出来的。B 在会话内用一个等价的临时脚本跑过完整四态判读，**28 条全 RED**，
四个被变异文件还原后 sha256 自证一致。E 落文件时可直接采用这些锚点。

基线：`137 passed`（T1 35 + T2 80 + T4 22，见下方 TESTS）。
基线自检：`passed < 137` 即中止（spec 要求的「passed < N 即中止」）。

```python
TESTS = [
    "backend/tests/workpaper_sync/test_excel_row_shift.py",
    "backend/tests/workpaper_sync/test_excel_shift_aware_verification.py",
    "backend/tests/workpaper_sync/test_excel_row_insertion_wiring.py",
]
BASELINE_PASSED = 137
```

⚠ Task 19/21 的两份测试（`test_excel_row_insertion_readiness.py` 21 例 /
`test_excel_row_insertion_openability.py` 12 例）**刻意不进 TESTS**：前者读模板库、
后者要 docker + OnlyOffice 容器，都会让变异循环变慢且引入环境依赖。它们的判据由 CI 单独跑。

---

## 四态判读的两条实测教训（E 落文件时请保留）

### 1. `errors` 必须计入「红」，不能只数 `failed`

变异写出**语法错误**或导致导入失败时，pytest 报的是 `N error` 而不是 `N failed`。
只数 `failed` 会把「模块根本没跑起来」判成 **GREEN**。

> 实测：M28 首轮就是这么误判的 —— 那条 mutation 把调用头换成 `_ = (` 造出非法元组
> （关键字参数在元组里），模块导入失败，四态判读报 GREEN。

```python
failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
errors = int(m.group(1)) if (m := re.search(r"(\d+) error", out)) else 0
failed += errors          # ← 这一行是判据本体
```

### 2. mutation 本身必须是**语法合法**的

否则打红的原因是「语法错」而不是「守卫抓到了行为变化」，WRONG-TEST 与 RED 就分不开。
整段调用一起换成 `pass`，不要只换调用头。

---

## 清单（28 条）

`path` 相对 `backend/app/services/workpaper_sync/`。锚点命中次数必须恰为 1。

### Wave 1~2：位移纯函数与 shift-aware 归一化（M1~M14）

| id | path | 所守的假绿形态 | 预期打红 |
|---|---|---|---|
M1 | `excel_row_shift.py` | 新行做回共享公式**成员** ⇒ 整组失效 | `test_new_rows_are_not_shared_formula_members` |
M2 | `excel_row_shift.py` | 新行不继承样式 | `test_new_row_inherits_style_from_source_row` |
M3 | `excel_row_shift.py` | 扩张计数改为**按声明推**（而非实测比出） | `test_extension_count_is_measured_not_declared` |
M4 | `excel_row_shift.py` | 摘掉合计区间扩张 | `test_total_formula_range_extends` |
M5 | `excel_row_shift.py` | 摘掉横向组 fail closed | `test_horizontal_group_style_source_fails_closed` |
M6 | `excel_row_shift.py` | 位移敏感清单漏掉 `mergeCell` | `test_listed_structures_all_have_handlers` |
M7 | `excel_row_shift.py` | 元素**文本**里的 A1 不位移 | `test_element_text_a1_refs_shift` |
M8 | `excel_row_shift.py` | 不认 `&quot;` 实体字面量 | `test_entity_encoded_string_literals_are_not_mistaken_for_refs` |
M9 | `excel_extract.py` | 新插入行**不排除** | `test_inserted_rows_are_excluded_from_the_digest` |
M10 | `excel_extract.py` | 格坐标归一化改恒等 | `test_cell_coords_are_normalised` |
M11 | `excel_extract.py` | 结构块归一化空转 | `test_structure_blocks_are_normalised` |
M12 | `excel_extract.py` | 公式文本不归一化 | `test_formula_text_is_normalised` |
M13 | `excel_extract.py` | **两侧都**归一化（= 什么都没归一化） | `test_only_the_after_side_is_normalised` |
M14 | `excel_extract.py` | 归一化表在 verifier 侧**另抄一份** | `test_verifier_does_not_hardcode_a_second_structure_list` |

### Wave 3：footer 两门位移感知 + 契约字段（M15~M20）

| id | path | 所守的假绿形态 | 预期打红 |
|---|---|---|---|
M15 | `excel_materialize.py` | footer anchor 判据**不加位移** | `test_planned_shift_is_accepted_and_unplanned_is_not` |
M16 | `excel_materialize.py` | footer anchor **无条件**加 `count` | `test_footer_above_the_insertion_point_is_not_expected_to_move` |
M17 | `excel_materialize.py` | 合计判据仍用**旧**区间 | `test_shift_without_extension_still_fails_closed` |
M18 | `excel_materialize.py` | 声明带合计却无公式**不再** fail closed | `test_declared_but_formula_free_row_fails_closed` |
M19 | `contracts.py` | 契约字段又被**静默丢弃** | `test_declared_true_is_retained` |
M20 | `contracts.py` | 非布尔取值被当真 | `test_non_boolean_values_fail_closed` |

🔴 **M15 与 M16 锚点部分重叠** —— M15 必须含前一行 `frozen_row = int(raw_frozen)` 才唯一，
否则 ANCHOR-MISS。请保留这个区分。

### Wave 4：接线（M21~M28）

| id | path | 所守的假绿形态 | 预期打红 |
|---|---|---|---|
M21 | `excel_materialize.py` | orphan **不再**算位移计划（整体空转） | `test_plan_count_tracks_the_orphan_count` |
M22 | `excel_materialize.py` | 新插入行**不写** row identity | `test_every_inserted_row_carries_its_row_identity` |
M23 | `excel_materialize.py` | 静态行拒绝理由被摘掉 | `test_production_contract_rejects_insertion_with_that_reason` |
M24 | `excel_materialize.py` | 合计不会扩张也照插 | `test_all_six_reasons_are_reachable_and_pairwise_distinct` |
M25 | `excel_materialize.py` | Table `ref` 不长 | `test_managed_table_ref_really_grew` |
M26 | `excel_materialize.py` | 计划期用**未位移**的 XML 求值 | `test_plan_count_tracks_the_orphan_count` |
M27 | `excel_extract.py` | 合计扩张还原被**无条件抹平** | `test_unextending_is_declaration_driven_not_a_blanket_pass` |
M28 | `excel_materialize.py` | 位移后**不复核** footer 两门 | `test_failing_shifted_gate_publishes_nothing` |

🔴 **M28 的 `want` 值得单说**：它打红的是「证明调用点在链路上」那条守卫
（`test_failing_shifted_gate_publishes_nothing`），**不是** footer 判据自身的用例。
B 首版把 `want` 写成后者，四态判读正确地报了 **WRONG-TEST**。

M28 也是**变异检验捞出真缺陷**的一例：它首轮 GREEN，暴露出「T4 只调
`apply_plan_zip_with_report`，从未走完整 `materialize_projection`」⇒
`assert_shifted_footer_gates` 的调用点**一次都没被执行**，两个新参数在生产链路上是
零消费的死参数。补了 `TestMaterializeProjectionRunsTheWholeChain` 才转 RED。

---

## 锚点原文（逐条，可直接粘）

为避免 CRLF 与缩进歧义，B 已验证过的锚点原文见 spec 的 tasks.md Task 20 条目下方，
或直接向 B 索取 `tmp_b_mutate_check.py`（会话内临时脚本，未入库）。

关键几条：

```python
# M15（必须含前一行才唯一）
anchor = '    frozen_row = int(raw_frozen)\n    expected = row_shift.shift(frozen_row)'
new    = '    frozen_row = int(raw_frozen)\n    expected = frozen_row'

# M16
anchor = '    expected = row_shift.shift(frozen_row)'
new    = '    expected = frozen_row + row_shift.count'

# M28（整段调用一起换，保持语法合法）
anchor = ('                assert_shifted_footer_gates(\n'
          '                    staged_bytes=staged,\n'
          '                    plan=plan,\n'
          '                    contract=definitions.contract,\n'
          '                    region=substrate_view.region,\n'
          '                    runtime_binding=runtime_binding,\n'
          '                )')
new    = '                pass'
```

⚠ 锚点里含 `\n` 与 spec 的「锚点不含 `\n`」要求冲突。B 的临时脚本用**CRLF 归一后再匹配**
解决（`text.replace("\r\n", "\n")`）。E 若坚持无 `\n` 锚点，M15 / M28 需改用
「单行锚点 + 命中次数断言」两段式。

---

## 给 E 的其他两条

1. **`--check-anchors` 只读入口**：spec 明确要求。B 的临时脚本有等价能力（跑前逐条验证
   命中次数恰为 1），但没做成独立子命令。
2. **子进程不经 shell**：`subprocess.run([...])`。B 的临时脚本已如此。
