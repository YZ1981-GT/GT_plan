# -*- coding: utf-8 -*-
"""Task 14 变异检验：stable-field 三方 merge 与冲突 domain 的守卫是否真能打红。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 14
Requirements: 6.6, 6.7, 6.8, 6.9, 7.4, 8.1, 8.5
Properties: P24 / P25 / P26 / P27 / P32 / P35

═══ 变异改的是**生产代码**，不是守卫 ═══

落点三处（两处是本任务的域，第三处只为证明「零消费方」这条边界不是空转）：

* `workpaper_sync/merge.py` —— MISSING 哨兵、类型规范化、真值表九行、行生命周期、
  Word 多实例归并、contract 索引、结构异常收敛、裁决落地、任务边界登记
* `workpaper_sync/conflicts.py` —— 冲突记录自洽性、dedupe/摘要、四类拒绝路径、
  resolve fence 的九步不可交换顺序
* `workpaper_sync/__init__.py` —— **注入**一处 merge 域的生产消费方（M78），
  用来证明「当前零消费方」这条边界判据可 falsify

判定四态：打红=RED（守卫有效）；不红=GREEN（**守卫缺陷**，逐条归因修守卫，绝不降标）；
红了但不是预期项=WRONG-TEST（污染残留 / 锚点错行）；锚点未命中或命中多处=ANCHOR-MISS
（脚本缺陷）。

═══ 本任务两类高风险形态各自的对策 ═══

**(a) 同类型异常 / 同形状冲突记录互相遮蔽。**
Task 12/13 已实测两次：两条拒绝路径抛同一异常类、文案又重叠，短路其中一条时另一条
把它遮蔽 ⇒ GREEN。本域有三处这种结构，处理办法都是「让每条原因有自己可分辨的文案或
自己的类型」，并让守卫断言到**那句话**而不只是异常类：

1. `resolved_value_for` 的四条禁令 → 四个互不继承的异常类
   （`test_four_rejection_types_are_pairwise_distinct` 双向断言）
2. `assert_all_conflicts_resolved` 的 missing / unknown 两条 → 两个类 + 各自文案；
   守卫必须**同时给上真实裁决**才能测到 unknown 那条（M71/M72 分别覆盖）
3. `models.assert_direct_primary` 的六条禁令共用 `DuplicateLinkError` 且都被收成同一个
   `FenceReason` → 守卫按 `broken` 参数断言各自的可分辨文案，反例构造成「只坏一条」
   （M67 正是靠这一点才能打红 `[stranded]` 而不被别的分支遮蔽）

**(b) 否定式承诺没有可短路的语句，必须注入反例。**
「同字段冲突不自动选边」「MISSING 永不折叠成 None」「merge 域当前零生产消费方」
「本任务不引入载体库」这四条，源码里根本没有对应的语句可以短路 —— 短路式变异必 GREEN
（Task 12 的 M51、Task 13 的 M40~M43 已实证）。因此 M74~M78 全是**注入**：

* M74 往冲突分支注入 `_put(..., i)`（直接实现 last-write-wins）
* M75 往 `_put` 注入 `absent → ValueEnvelope.of(None)`（直接实现 MISSING 折叠）
* M76 往 merge.py 注入 `if False: import openpyxl`（载体库依赖）
* M77 往 merge.py 注入 `class ContentMutationService`（第二个业务提交边界）
* M78 往 `workpaper_sync/__init__.py` 注入一次 merge 域 import（第二个消费方）

**2026-08-26（Task 15 落地后）**：M77/M78 的 `want` 随边界判据翻转而更新 ——
merge 域现在有**恰一个**生产消费方（`content_mutation.py`），`ContentMutationService`
定义**恰一处**。两条注入证明「≥2」这一侧仍可 falsify；「0」那一侧由守卫自身的
`assert wired` / `assert defined == [...]` 覆盖（把接线删掉即红）。M79 的锚点从已退役的
`"15,26"` 改到仍未接线的 resolve API 那条（`"27,28"`）。

═══ 已知的判据设计取舍（写在这里免得下一个人重踩）═══

1. **静态受管格与动态行的「incoming 缺失」是两条判据**：前者是载体漂移（fail closed），
   后者是合法删除。合成一条会让其中一支永不被测到（M40 与
   `test_row_scoped_field_deleted_on_both_sides_agrees_without_conflict` 各锁一支）。
2. **`(MISSING, MISSING, MISSING)` 不是真值表的一行**：键域是三方并集，全缺时没有可判定
   的对象。写成真值表行会逼实现遍历整份契约的键空间，而行域字段的 `{row_uuid}` 模板
   本就无法枚举。
3. **多行 `if (...)` / `raise (...)` 不可整行替换**（破坏续行语法 ⇒ 文件级 collect ERROR
   ⇒ 判定退化成 WRONG-TEST）。本脚本一律改其中**一个条件行**（M20/M23/M31/M37/M65）。
4. **`if False:` 短路某些校验会让下游抛同类型异常**（例如关掉「金额空串」判据后
   `Decimal("")` 仍抛 `InvalidOperation` → 被收成同一个 `ValueNormalizationError`）。
   这类位置改用**语义化 fail-open**（M09 把空串变成 `"0"`），否则行为不变 = 无效变异。

用法（仓库根）::

    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task14_merge_conflict_guards.py --list
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task14_merge_conflict_guards.py --check-anchors
    .\\.venv\\Scripts\\python.exe backend/scripts/diagnose/mutate_task14_merge_conflict_guards.py --run all \\
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task14-merge-conflicts/mutation_report.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

MERGE = "backend/app/services/workpaper_sync/merge.py"
CONFLICTS = "backend/app/services/workpaper_sync/conflicts.py"
PKG_INIT = "backend/app/services/workpaper_sync/__init__.py"

#: 覆盖面分母：Task 14 唯一的守卫文件。
#:
#: 只有一个分母项，所以「覆盖面」这项在本脚本里天然满足 —— 真正的判据强度来自
#: **每条变异都必须命中它自己那条测试**（`want` 精确到 nodeid），而不是「有某个守卫红了」。
GUARD_FILES = {
    "test_task14_merge_conflicts.py":
        "Task 14 新建：MISSING 哨兵非折叠、类型规范化双向、三方真值表逐行真实执行、"
        "P24 保护字段 / P25 不同字段自动合并 / P26 同字段异值必冲突 / P27 delete-update "
        "不整表覆盖 / P32 Word 多实例 / P35 冲突双侧可追溯、四条 Hypothesis 属性、"
        "conflict set 摘要与 dedupe、resolve fence 九步顺序、任务边界与反向自检",
}

U = "test_task14_merge_conflicts"

MUTATIONS: list[Mutation] = [
    # ══ 一、MISSING 哨兵：与 None / "" / 0 永不折叠 ══════════════════════
    Mutation(
        id="M01", side="be", path=MERGE, kind="replace",
        anchor="        return MISSING",
        new="        return None",
        want=f"{U}.py::TestMissingSentinel::test_normalize_returns_missing_identically_for_every_value_type",
        wants=(
            f"{U}.py::TestMissingSentinel::test_missing_vs_none_is_never_equal",
            f"{U}.py::TestMissingSentinel::test_deleted_and_cleared_produce_different_merged_results",
        ),
        why="`normalize_value` 把 MISSING 折叠成 None ⇒ 「行/载体被删」与「用户清空这个格」"
            "规范化后同值，HTML projection / 回滚 / 审计轨迹里再也分不开",
    ),
    Mutation(
        id="M02", side="be", path=MERGE, kind="replace",
        anchor="        return a is MISSING and b is MISSING",
        new="        return True",
        want=f"{U}.py::TestMissingSentinel::test_missing_vs_none_is_never_equal",
        why="`values_equal` 让 MISSING 与任何值判等 ⇒ 删除侧恒判「未改动」，"
            "delete/update 冲突永不产生（AC 6.9 失效）",
    ),
    Mutation(
        id="M03", side="be", path=CONFLICTS, kind="replace",
        anchor='            return {"present": False}',
        new='            return {"present": True, "value": None}',
        want=f"{U}.py::TestMissingSentinel::test_envelope_absent_and_present_null_have_different_jsonb",
        why="落库形态把 absent 写成 present-but-null ⇒ `base_value` 落库后无法区分"
            "「会话打开时没有这个字段」与「会话打开时它是 null」，裁决界面与回滚都无从下手",
    ),
    Mutation(
        id="M04", side="be", path=MERGE, kind="replace",
        anchor="    if left.present != right.present:",
        new="    if False:",
        want=f"{U}.py::TestMissingSentinel::test_envelopes_equal_never_folds_absent_into_null",
        why="信封级比较不再看 present ⇒ absent 与 present-but-null 在**比较层**折叠。"
            "与 M01/M02 是三个不同层级（规范化 / 值比较 / 信封比较），任一层折叠都足以致命",
    ),
    Mutation(
        id="M05", side="be", path=MERGE, kind="insert",
        anchor="    __slots__ = ()",
        new="\n    def __bool__(self) -> bool:\n        return False\n",
        want=f"{U}.py::TestMissingSentinel::test_missing_is_truthy_so_if_value_cannot_swallow_it",
        why="给哨兵加 falsy 真值 ⇒ 生产代码里一句 `if value:` 就会把 MISSING 与 "
            "None/\"\"/0 一起当空值，这正是本域要防的折叠（刻意不实现 __bool__ 的理由）",
    ),
    Mutation(
        id="M06", side="be", path=MERGE, kind="replace",
        anchor="    def __reduce__(self) -> tuple:",
        new="    def __reduce__ignored__(self) -> tuple:",
        want=f"{U}.py::TestMissingSentinel::test_missing_survives_copy_deepcopy_and_pickle",
        why="去掉 pickle 支持 ⇒ 反序列化出**另一个** _Missing 实例，身份相等失效，"
            "跨进程/跨缓存边界后 `value is MISSING` 恒 False（outbox 重放会踩到）",
    ),

    # ══ 二、类型规范化：该等的等、不该等的坚决不等 ════════════════════════
    Mutation(
        id="M07", side="be", path=MERGE, kind="replace",
        anchor="    if isinstance(value, bool):",
        new="    if False:",
        want=f"{U}.py::TestTypeNormalization::test_amount_rejects_non_numeric_inputs",
        why="金额字段不再拒绝 bool ⇒ `True` 被当 1、`False` 被当 0，"
            "「勾选」与「金额 1 元」判等",
    ),
    Mutation(
        id="M08", side="be", path=MERGE, kind="replace",
        anchor="        return Decimal(str(value))",
        new="        return Decimal(value)",
        want=f"{U}.py::TestTypeNormalization::test_amount_representations_that_are_the_same_number_are_equal",
        why="float 直接进 Decimal ⇒ `Decimal(0.1)` 带二进制误差尾巴，"
            "`0.1` 与 `\"0.1\"` 判不等 ⇒ 未改动的金额格被误判成冲突",
    ),
    Mutation(
        id="M09", side="be", path=MERGE, kind="replace",
        anchor="        text = value.strip()",
        new='        text = value.strip() or "0"',
        want=f"{U}.py::TestTypeNormalization::test_amount_rejects_non_numeric_inputs",
        why="空串静默变 0（典型 fail-open）⇒ 「这一格没填」与「这一格是 0」判等。"
            "🔴 这里**不能**用 `if False:` 短路空串判据：`Decimal(\"\")` 仍会抛 "
            "`InvalidOperation` 并被收成同一个 `ValueNormalizationError` ⇒ 行为不变 = 无效变异",
    ),
    Mutation(
        id="M10", side="be", path=MERGE, kind="replace",
        anchor='        return out.replace(_ZERO_WIDTH_BOM, "")',
        new='        return out.replace(_ZERO_WIDTH_BOM, "").strip()',
        want=f"{U}.py::TestTypeNormalization::test_text_normalizes_only_line_endings_and_bom",
        why="文本规范化多做一步 trim ⇒ 用户有意义的前后空格被抹平，"
            "`\"a \"` 与 `\"a\"` 判等（design 明文「不 trim 用户有意义空格」）",
    ),
    Mutation(
        id="M11", side="be", path=MERGE, kind="replace",
        anchor='_LINE_ENDING_PAIRS: Final[tuple[tuple[str, str], ...]] = (("\\r\\n", "\\n"), ("\\r", "\\n"))',
        new='_LINE_ENDING_PAIRS: Final[tuple[tuple[str, str], ...]] = (("\\r\\n", "\\n"), ("\\r", "\\n"), ("\\u00a0", " "))',
        want=f"{U}.py::TestTypeNormalization::test_text_normalizes_only_line_endings_and_bom",
        why="把 NBSP 也归一成普通空格 ⇒ OO 粘贴进来的 NBSP 与手输空格判等。"
            "与 M10 是两个方向：多 trim vs 多折叠不可见字符，只测一条时另一条不会红",
    ),
    Mutation(
        id="M12", side="be", path=MERGE, kind="replace",
        anchor="        if isinstance(value, datetime):",
        scope="    if value_type is ValueType.date:",
        offset=2,
        new="        if False:",
        want=f"{U}.py::TestTypeNormalization::test_date_and_datetime_do_not_fold_into_each_other",
        why="date 分支不再先拒 datetime ⇒ `datetime` 是 `date` 的子类，会被当同一个值。"
            "「日期」与「时点」折叠后，OO 回来的 datetime 覆盖服务端的 date 不产生冲突",
    ),
    Mutation(
        id="M13", side="be", path=MERGE, kind="replace",
        anchor='        if isinstance(value, str) and value in ("true", "false"):',
        new='        if isinstance(value, (str, int)) and value in ("true", "false", 0, 1):',
        want=f"{U}.py::TestTypeNormalization::test_boolean_rejects_zero_one_and_capitalised_strings",
        why="布尔字段接受 0/1 ⇒ `0` 与 `False`、`1` 与 `True` 折叠，"
            "「未勾选」与「数值 0」在审计底稿里不是一件事",
    ),
    Mutation(
        id="M14", side="be", path=MERGE, kind="replace",
        anchor="            return value",
        scope="    if value_type is ValueType.enum:",
        offset=2,
        new="            return value.lower()",
        want=f"{U}.py::TestTypeNormalization::test_enum_is_case_sensitive",
        why="枚举做大小写折叠 ⇒ `Listed` 与 `listed` 判等。枚举值是 identity，"
            "折叠后 OO 侧改大小写不再产生冲突而被静默采纳",
    ),
    Mutation(
        id="M15", side="be", path=MERGE, kind="replace",
        anchor='            return canonical_json_bytes({"v": value})',
        new="            return repr(value)",
        want=f"{U}.py::TestTypeNormalization::test_json_is_key_order_insensitive_but_value_sensitive",
        why="json 字段不走 Task 12 的 canonical 字节而用 `repr` ⇒ 键序变化被当值变化，"
            "OO 一次往返就产生整片假冲突",
    ),
    Mutation(
        id="M16", side="be", path=MERGE, kind="replace",
        anchor='            f"enum 字段必须是字符串，实得 {type(value).__name__} {value!r}"',
        new='            f"字段必须是字符串，实得 {type(value).__name__} {value!r}"',
        want=f"{U}.py::TestTypeNormalization::test_normalization_failure_messages_name_the_value_type",
        why="规范化失败文案不再点名自己的 value_type ⇒ 七类失败原因不可分辨，"
            "短路其中一类时另一类会把它遮蔽（Task 12/13 实测的 GREEN 成因）",
    ),

    # ══ 三、Property 24：保护字段修改形成冲突（AC 6.6）════════════════════
    Mutation(
        id="M17", side="be", path=MERGE, kind="replace",
        anchor="            locator.is_protected",
        new="            False",
        want=f"{U}.py::TestProperty24ProtectedField::test_oo_edit_on_protected_field_yields_protected_conflict",
        why="关掉保护判据 ⇒ OO 改公式格后走 took_incoming，公式结果被 OO 值覆盖"
            "（AC 6.6 明令禁止）",
    ),
    Mutation(
        id="M18", side="be", path=CONFLICTS, kind="replace",
        anchor="        return self is not ProtectionPolicy.editable and self is not ProtectionPolicy.word_only",
        new="        return self in (ProtectionPolicy.read_only_formula, ProtectionPolicy.read_only_auto_source)",
        want=f"{U}.py::TestProperty24ProtectedField::test_oo_edit_on_protected_field_yields_protected_conflict",
        why="把「mask 覆盖的受保护单元格」从保护集合里摘掉 ⇒ AC 6.6 的第三类只读来源失守。"
            "三类保护是三条独立判据，合并成两条时第三类永不被测到",
    ),
    Mutation(
        id="M19", side="be", path=MERGE, kind="replace",
        anchor="            and column_in_ranges(spec.cell.column, template.formula_mask)",
        new="            and False",
        want=f"{U}.py::TestProperty24ProtectedField::test_oo_edit_on_protected_field_yields_protected_conflict",
        why="不再按 `formula_mask` 判「受保护单元格」⇒ 契约里 editable 但落在 mask 内的格"
            "（OO 侧是受保护格）被当普通可编辑格。与 M18 是两处：分类真源 vs 分类结果",
    ),
    Mutation(
        id="M20", side="be", path=MERGE, kind="replace",
        anchor="            and b.present",
        new="            and True",
        want=f"{U}.py::TestProperty24ProtectedField::test_new_row_added_in_oo_does_not_conflict_on_its_formula_cell",
        why="保护判据不再要求 base 侧存在 ⇒ OO 新增行时其公式格（base 里本来没有）"
            "被误报 protected 冲突，正常插行变成必须人工裁决",
    ),
    Mutation(
        id="M21", side="be", path=CONFLICTS, kind="replace",
        anchor="    if record.locator.is_protected and choice.kind is not ResolutionKind.keep_current:",
        new="    if False:",
        want=f"{U}.py::TestProperty24ProtectedField::test_protected_conflict_cannot_be_resolved_by_taking_incoming",
        why="裁决层不再拦「受保护字段取 incoming」⇒ 冲突虽然报了，人工一点 take_incoming "
            "仍能覆盖公式。检测与裁决是两道门，缺一道等于没有",
    ),
    Mutation(
        id="M22", side="be", path=CONFLICTS, kind="replace",
        anchor="            if not self.locator.is_protected:",
        new="            if False:",
        want=f"{U}.py::TestProperty24ProtectedField::test_protected_record_with_editable_policy_is_rejected",
        why="冲突记录不再自检「protected 冲突的 protection_policy 必须真是受保护」⇒ "
            "自相矛盾的记录可落库，裁决界面按 editable 渲染出可覆盖按钮",
    ),

    # ══ 四、Property 25：不同字段自动三方合并（AC 6.8）════════════════════
    Mutation(
        id="M23", side="be", path=MERGE, kind="replace",
        anchor="        if same_current_base:",
        new="        if False:",
        want=f"{U}.py::TestProperty25DifferentFieldsAutoMerge::test_current_changes_a_incoming_changes_b",
        wants=(
            f"{U}.py::TestProperty25And26Hypothesis::test_property_disjoint_field_edits_merge_without_conflict",
            f"{U}.py::TestProperty25DifferentFieldsAutoMerge::test_parallel_edits_on_different_rows_of_the_same_table",
            f"{U}.py::TestThreeWayTruthTable::test_row",
        ),
        why="真值表第 6 行（仅 OO 改 ⇒ 采 incoming）被短路 ⇒ 不同字段的并行修改全部变成"
            "冲突，AC 6.8「自动合并」彻底失效",
    ),
    Mutation(
        id="M24", side="be", path=MERGE, kind="replace",
        anchor="        if same_incoming_base:",
        new="        if False:",
        want=f"{U}.py::TestThreeWayTruthTable::test_unchanged_incoming_preserves_newer_server_value",
        wants=(
            f"{U}.py::TestProperty25And26Hypothesis::test_property_untouched_incoming_preserves_current_everywhere",
            f"{U}.py::TestProperty25And26Hypothesis::test_property_merge_of_three_identical_sides_is_the_identity",
        ),
        why="真值表第 5 行（OO 未改 ⇒ 保 current）被短路 ⇒ 服务端新值被打回或变成冲突，"
            "AC 6.7「仅 current 变更则保 current」失效",
    ),
    Mutation(
        id="M25", side="be", path=MERGE, kind="replace",
        anchor="        ordered: list[str] = [r for r in _row_order(incoming, table_key) if r in alive]",
        new="        ordered: list[str] = [r for r in _row_order(current, table_key) if r in alive]",
        want=f"{U}.py::TestProperty25DifferentFieldsAutoMerge::test_row_reorder_alone_produces_no_conflict_and_no_value_change",
        why="merged 行序改成以 current 为主 ⇒ 用户在 OO 里的重排在回写后被打回原序，"
            "「重排只改展示顺序」变成「重排被丢弃」",
    ),
    Mutation(
        id="M26", side="be", path=MERGE, kind="insert",
        anchor="    merged_values: dict[str, FieldValue] = {}",
        new="    for _tk in sorted(set(incoming.row_keys or {}) | set(current.row_keys or {})):\n"
            "        if _row_order(incoming, _tk) != _row_order(current, _tk):\n"
            "            row_decisions.append(RowDecision(\n"
            "                table_key=_tk, row_key=\"__reordered__\",\n"
            "                lifecycle=RowLifecycle.delete_update_conflict,\n"
            "                member_keys=(), held=True))\n",
        want=f"{U}.py::TestProperty25DifferentFieldsAutoMerge::test_row_reorder_alone_produces_no_conflict_and_no_value_change",
        why="🔴 **注入**：让行序差异本身产出一个 delete_update_conflict 行决策。"
            "「不得把位置变化误判为整表覆盖」（AC 6.9）是否定式承诺 —— 源码里没有"
            "「比较位置」的语句可短路，只能注入反例证明判据可 falsify",
    ),

    # ══ 五、Property 26：同字段异值必冲突且不选边（AC 6.8）════════════════
    Mutation(
        id="M27", side="be", path=MERGE, kind="replace",
        anchor="        if same_current_incoming:",
        new="        if False:",
        want=f"{U}.py::TestProperty26SameFieldDifferentValues::test_both_sides_changed_to_the_same_value_merges",
        wants=(f"{U}.py::TestThreeWayTruthTable::test_row",),
        why="真值表第 7 行（两侧改成同值 ⇒ 合并）被短路 ⇒ 两边都填了同一个数也要人工裁决，"
            "冲突预览被无意义条目淹没",
    ),
    Mutation(
        id="M28", side="be", path=CONFLICTS, kind="replace",
        anchor="    if missing:",
        new="    if False:",
        want=f"{U}.py::TestProperty26SameFieldDifferentValues::test_unresolved_conflict_blocks_apply",
        wants=(
            f"{U}.py::TestProperty25And26Hypothesis::test_property_same_field_three_values_never_auto_picks_a_side",
            f"{U}.py::TestProperty26SameFieldDifferentValues::test_missing_and_unknown_resolutions_are_two_distinguishable_types",
        ),
        why="缺裁决不再拦 ⇒ `apply_resolutions` 静默返回「hold 在 current」的快照当成裁决结果，"
            "AC 4.6「不得自动选 incoming 或 current」被绕过（虽然选的是 current，"
            "但那是**未经人确认**的自动选边）",
    ),
    Mutation(
        id="M29", side="be", path=CONFLICTS, kind="replace",
        anchor="    if unknown:",
        new="    if False:",
        want=f"{U}.py::TestProperty26SameFieldDifferentValues::test_resolution_pointing_at_a_nonexistent_conflict_is_rejected",
        why="裁决指向不存在的冲突不再拒 ⇒ stale 冲突集（已被 supersede/rebase）的裁决被"
            "静默接受。🔴 这条能打红的前提是守卫**同时给上真实裁决** —— 否则 missing 分支"
            "（M28）会先抛，把本条遮蔽",
    ),
    Mutation(
        id="M30", side="be", path=CONFLICTS, kind="replace",
        anchor="        if choice.dedupe_key in by_key:",
        new="        if False:",
        want=f"{U}.py::TestProperty26SameFieldDifferentValues::test_duplicate_resolutions_for_one_conflict_are_rejected",
        why="同一冲突被裁决两次不再拒 ⇒ 后者静默覆盖前者，批量裁决界面的重复提交"
            "无法被发现（审计轨迹里只留下最后一次选择）",
    ),

    # ══ 六、Property 27：delete/update 冲突不整表覆盖（AC 6.9）════════════
    Mutation(
        id="M31", side="be", path=MERGE, kind="replace",
        anchor="            if current_changed",
        new="            if False",
        want=f"{U}.py::TestProperty27DeleteUpdate::test_incoming_deletes_row_current_updates_it",
        why="OO 删行 + 服务端改同一行 ⇒ 不再报 delete_update 冲突而直接接受删除，"
            "服务端的改动被静默丢弃",
    ),
    Mutation(
        id="M32", side="be", path=MERGE, kind="replace",
        anchor="            if incoming_changed",
        new="            if False",
        want=f"{U}.py::TestProperty27DeleteUpdate::test_current_deletes_row_incoming_updates_it",
        why="服务端删行 + OO 改同一行 ⇒ 同上但方向相反。与 M31 是两个方向，"
            "只测一条时删另一条不会红",
    ),
    Mutation(
        id="M33", side="be", path=MERGE, kind="replace",
        anchor="        held = lifecycle is RowLifecycle.delete_update_conflict or row_key in blocked_rows",
        new="        held = True",
        want=f"{U}.py::TestStructuralConflicts::test_reported_row_identity_anomaly_blocks_only_that_row",
        wants=(
            f"{U}.py::TestProperty25DifferentFieldsAutoMerge::test_parallel_edits_on_different_rows_of_the_same_table",
            f"{U}.py::TestProperty27DeleteUpdate::test_incoming_deletes_row_current_updates_it",
        ),
        why="把封锁面从「出问题的那一行」扩大到**全部行** ⇒ 一处行身份坏了就整表 hold 在 "
            "current，正是 AC 6.9 明令禁止的「整表覆盖」的镜像形态",
    ),
    Mutation(
        id="M34", side="be", path=MERGE, kind="replace",
        anchor="            if b.present and (c.present != i.present)",
        new="            if False",
        want=f"{U}.py::TestThreeWayTruthTable::test_current_delete_vs_incoming_update_is_delete_update_not_value",
        why="delete/update 被降级成普通 value 冲突 ⇒ 裁决界面显示「两个值二选一」，"
            "而实际语义是「要不要保留这一行」，选项本身就是错的",
    ),
    Mutation(
        id="M35", side="be", path=CONFLICTS, kind="replace",
        anchor="        if self.kind is ConflictKind.delete_update and not (",
        new="        if False and not (",
        want=f"{U}.py::TestProperty27DeleteUpdate::test_delete_update_record_requires_exactly_one_absent_side",
        why="不再自检「delete_update 要求恰好一侧缺失」⇒ 两侧都有值也能标成 delete_update，"
            "落库后 UI 拿不到可删的那一侧",
    ),
    Mutation(
        id="M36", side="be", path=MERGE, kind="replace",
        anchor="            not resolved_env[record.dedupe_key].present for record in row_conflicts",
        new="            False for record in row_conflicts",
        want=f"{U}.py::TestProperty27DeleteUpdate::test_resolving_delete_update_as_delete_removes_the_whole_row",
        why="「整行冲突全裁决为缺失 ⇒ 删整行」不再成立 ⇒ 用户明确选了删除，"
            "行里其余字段仍留在 projection 里成为半截幽灵行",
    ),

    # ══ 七、Property 32：Word 多实例异值冲突（AC 7.4）══════════════════════
    Mutation(
        id="M37", side="be", path=MERGE, kind="replace",
        anchor="        envelopes_equal(inst.envelope, first, locator.value_type) for inst in ordered[1:]",
        new="        True for inst in ordered[1:]",
        want=f"{U}.py::TestProperty32WordDuplicateInstances::test_divergent_instances_yield_duplicate_conflict_with_every_xpath",
        why="同 tag 多实例恒判「值一致」⇒ 异值实例被静默取 XPath 序第一个，"
            "另外几处的内容悄悄丢失（AC 7.4 要求生成 duplicate 冲突并列全部位置）",
    ),
    Mutation(
        id="M38", side="be", path=MERGE, kind="replace",
        anchor="    refs = tuple(WordInstanceRef(xpath=inst.xpath, value=inst.envelope) for inst in ordered)",
        new="    refs = tuple(WordInstanceRef(xpath=inst.xpath, value=inst.envelope) for inst in ordered[:2])",
        want=f"{U}.py::TestProperty32WordDuplicateInstances::test_divergent_instances_yield_duplicate_conflict_with_every_xpath",
        why="只列前两个实例位置（仍满足 ≥2 的自检）⇒ 第三处及以后的 XPath 不出现在"
            "裁决界面，AC 7.4「列出全部 OO 位置」被悄悄削减",
    ),
    Mutation(
        id="M39", side="be", path=CONFLICTS, kind="replace",
        anchor="            if len(payloads) < 2:",
        new="            if False:",
        want=f"{U}.py::TestProperty32WordDuplicateInstances::test_all_equal_instances_cannot_be_recorded_as_duplicate_conflict",
        why="全部实例值相同也能标成 duplicate 冲突 ⇒ AC 7.4 前半句（值一致时合并为一个字段）"
            "失效，Word 底稿每次回写都刷出一批假冲突",
    ),
    Mutation(
        id="M40", side="be", path=CONFLICTS, kind="replace",
        anchor="            if len(self.word_instances) < 2:",
        new="            if False:",
        want=f"{U}.py::TestProperty32WordDuplicateInstances::test_all_equal_instances_cannot_be_recorded_as_duplicate_conflict",
        why="单实例也能标成 duplicate 冲突 ⇒ 记录自相矛盾。与 M39 是同一个 `__post_init__` 的"
            "两条不同判据（实例数 vs 值分歧），必须分别覆盖",
    ),
    Mutation(
        id="M41", side="be", path=CONFLICTS, kind="replace",
        anchor="        record.kind is ConflictKind.duplicate_word_instance",
        new="        False",
        want=f"{U}.py::TestProperty32WordDuplicateInstances::test_take_incoming_is_ambiguous_and_must_be_rejected",
        why="多实例异值时 `take_incoming` 不再被拒 ⇒ 系统替用户挑了 XPath 序第一个实例，"
            "AC 7.4 要求的「显式指明取哪个实例」被绕过",
    ),
    Mutation(
        id="M42", side="be", path=MERGE, kind="replace",
        anchor="        if len(seen) != len(self.instances):",
        new="        if False:",
        want=f"{U}.py::TestProperty32WordDuplicateInstances::test_duplicate_xpath_in_observation_is_rejected",
        why="实例 XPath 重复不再拒 ⇒ 同一位置被登记两次，裁决界面出现两个一模一样的选项",
    ),
    Mutation(
        id="M43", side="be", path=MERGE, kind="replace",
        anchor="        if locator.mode is FieldMode.word_only:",
        new="        if False:",
        want=f"{U}.py::TestProperty32WordDuplicateInstances::test_word_only_field_never_enters_the_html_projection",
        wants=(
            f"{U}.py::TestMergeOutcomeDerivedJudgements::test_word_only_keys_are_excluded_from_the_refresh_comparison",
        ),
        why="`word_only` 字段进 HTML projection ⇒ Word 权威的自由文本被写进 HTML 底稿"
            "（AC 7.3），并让 `requires_client_refresh` 恒判需要重载",
    ),

    # ══ 八、结构 / 身份异常 fail closed ═══════════════════════════════════
    Mutation(
        id="M44", side="be", path=MERGE, kind="replace",
        anchor="        if not locator.row_key and b.present and not i.present:",
        new="        if False:",
        want=f"{U}.py::TestStructuralConflicts::test_missing_static_carrier_in_incoming_fails_closed",
        wants=(f"{U}.py::TestThreeWayTruthTable::test_row",),
        why="静态受管格在 incoming 里消失时不再 fail closed ⇒ 载体（单元格/SDT）被删掉"
            "会被当成「合法删除」，而静态格本不该消失。这条与动态行的合法删除是两条判据",
    ),
    Mutation(
        id="M45", side="be", path=CONFLICTS, kind="replace",
        anchor="        return self in _VALUE_ADJUDICABLE_ANOMALIES",
        new="        return True",
        want=f"{U}.py::TestStructuralConflicts::test_identity_anomaly_cannot_be_resolved_by_picking_a_side",
        why="把身份类结构异常也标成「可靠选边收敛」⇒ 行 UUID 空/重复时选 current 或 incoming"
            "都只是把坏结构固化下来（AC 6.15 要求先修结构）",
    ),
    Mutation(
        id="M46", side="be", path=CONFLICTS, kind="replace",
        anchor="    if not record.adjudicable_by_value_choice:",
        new="    if False:",
        want=f"{U}.py::TestStructuralConflicts::test_identity_anomaly_cannot_be_resolved_by_picking_a_side",
        why="裁决层不再拦身份类结构冲突。与 M45 是分类真源 vs 执行守卫两处，"
            "只测一条时另一条被遮蔽",
    ),
    Mutation(
        id="M47", side="be", path=CONFLICTS, kind="replace",
        anchor="            if self.schema_anomaly is None:",
        new="            if False:",
        want=f"{U}.py::TestStructuralConflicts::test_schema_conflict_without_anomaly_kind_is_rejected",
        why="schema 冲突不再强制给出 `schema_anomaly` ⇒ 「结构哪里坏了」不可诊断（AC 5.12），"
            "而 `adjudicable_by_value_choice` 会在 assert 上炸",
    ),
    Mutation(
        id="M48", side="be", path=MERGE, kind="replace",
        anchor="        blocked_keys.update(anomaly.blocks_stable_keys or (anomaly.stable_field_key,))",
        new="        blocked_keys.update(())",
        want=f"{U}.py::TestStructuralConflicts::test_key_level_anomaly_blocks_only_that_key",
        why="**键级**封锁失效 ⇒ 报了 schema 冲突却仍按三方规则把 incoming 写进那个键，"
            "fail closed 变成 fail open。🔴 首轮两次踩坑：先判 GREEN（当时只有行级封锁的"
            "守卫，`blocked_keys` 这条路径根本没有判据），补了 key 级守卫后又因 want 仍"
            "写着行级测试而判 WRONG-TEST。两条封锁路径必须各有自己的 want（另一条见 M81）",
    ),
    Mutation(
        id="M81", side="be", path=MERGE, kind="replace",
        anchor="        if anomaly.blocks_row_key:",
        new="        if False:",
        want=f"{U}.py::TestStructuralConflicts::test_reported_row_identity_anomaly_blocks_only_that_row",
        why="**行级**封锁失效 ⇒ 行身份坏了却只封锁报错那一个键，同行其他字段仍按三方规则"
            "采纳 incoming（`blocks_row_key` 的语义就是「这一行整体不可信」）。"
            "与 M48 成对：键级 vs 行级是两条独立语句、两条独立判据",
    ),
    Mutation(
        id="M49", side="be", path=MERGE, kind="replace",
        anchor="        if missing:",
        new="        if False:",
        want=f"{U}.py::TestStructuralConflicts::test_anomaly_outside_the_contract_must_bring_its_own_traceability",
        why="契约外的结构异常不再要求自带 label/pointer/OO 地址 ⇒ 落库出空标签空地址的"
            "冲突记录，AC 8.1/8.2 的可追溯性断链",
    ),
    Mutation(
        id="M50", side="be", path=MERGE, kind="replace",
        anchor="        if not matches:",
        new="        if False:",
        want=f"{U}.py::TestStructuralConflicts::test_contract_index_rejects_prefix_only_matches",
        wants=(
            f"{U}.py::TestStructuralConflicts::test_anomaly_outside_the_contract_must_bring_its_own_traceability",
        ),
        why="`ContractIndex.resolve` 对契约未登记的 key 不再抛 `UnknownStableKeyError` ⇒ "
            "落到 `matches[0]` 的 IndexError，诊断信息丢失（Requirement 6.20 的 fail closed "
            "退化成崩溃）。🔴 首轮把 want 写成 "
            "`test_unknown_stable_key_in_a_projection_fails_closed` 判了 WRONG-TEST —— "
            "那条测试实际由 Task 13 的 `Projection.assert_matches_contract` 在**更早**的"
            "入口拦下，与本判据不是同一道门。判据归属写错就是脚本缺陷，不是守卫缺陷",
    ),
    Mutation(
        id="M51", side="be", path=MERGE, kind="replace",
        anchor="    if len(exp) != len(act):",
        new="    if False:",
        want=f"{U}.py::TestStructuralConflicts::test_contract_index_rejects_prefix_only_matches",
        why="键匹配退化成「只比前缀 / 段数不限」⇒ `equity_changes/{row_uuid}/closing_amount` "
            "会误配到任何同前缀键，D2 那类大表直接串数据（Task 13 已用替身实证过这个形态）",
    ),
    Mutation(
        id="M52", side="be", path=MERGE, kind="replace",
        anchor='        if (declared or "") != locator.row_key:',
        new="        if False:",
        want=f"{U}.py::TestStructuralConflicts::test_contract_index_rejects_row_key_disagreement",
        why="`FieldValue.row_key` 与 stable key 里的行身份段不一致时不再拒 ⇒ 行身份有两个"
            "真源且可互相矛盾，删行/重排后数据串到别的行",
    ),
    Mutation(
        id="M53", side="be", path=MERGE, kind="replace",
        anchor="            return False",
        new="            return True",
        want=f"{U}.py::TestStructuralConflicts::test_type_normalization_failure_keeps_raw_values_for_adjudication",
        why="`_comparable` 不再跳过会抛规范化错误的键 ⇒ 行级「是否改动过」的比较里抛出"
            "未捕获的 `ValueNormalizationError`，整次 merge 崩掉而不是收成 schema 冲突",
    ),

    # ══ 九、冲突集：dedupe、排序、摘要（AC 8.1 / 8.5）══════════════════════
    Mutation(
        id="M54", side="be", path=CONFLICTS, kind="replace",
        anchor="            if key in seen:",
        new="            if False:",
        want=f"{U}.py::TestProperty35ConflictTraceability::test_duplicate_dedupe_key_in_a_set_is_rejected",
        why="同一 `(stable_field_key, row_key, oo_location)` 出现两条冲突不再拒 ⇒ 落库时撞 "
            "`uq_wpsc_field`，重复 callback 变成 500 而不是幂等",
    ),
    Mutation(
        id="M55", side="be", path=CONFLICTS, kind="replace",
        anchor='        object.__setattr__(self, "records", tuple(sorted(self.records, key=_sort_key)))',
        new='        object.__setattr__(self, "records", tuple(self.records))',
        want=f"{U}.py::TestConflictSetDigest::test_digest_is_deterministic_and_order_insensitive",
        why="冲突集不再确定性排序 ⇒ `conflict_set_digest` 随插入顺序变化，"
            "resolve fence 会把「同一批冲突」误判成 `conflict_set_changed`（AC 8.5 恒 409）",
    ),
    Mutation(
        id="M56", side="be", path=CONFLICTS, kind="replace",
        anchor='            "base": self.base.to_jsonb(),',
        new='            "base": None,',
        want=f"{U}.py::TestConflictSetDigest::test_digest_changes_when_any_of_the_three_values_changes",
        why="摘要不再含 base 值 ⇒ 只有 base 变化的冲突集算出同一个 digest，"
            "stale 冲突集通不过 fence 却被判「没变」",
    ),

    # ══ 十、resolve fence 的九步不可交换顺序（AC 8.5）══════════════════════
    Mutation(
        id="M57", side="be", path=CONFLICTS, kind="replace",
        anchor="    if request.canonical_application_id != application.canonical_application_id:",
        new="    if False:",
        want=f"{U}.py::TestResolveFence::test_each_fence_break_has_its_own_reason",
        why="不再校验「请求的 canonical application == 服务端锁定的 application」⇒ "
            "对着另一个 application 的冲突集提交裁决",
    ),
    Mutation(
        id="M58", side="be", path=CONFLICTS, kind="replace",
        anchor="    if request.room_generation != room.generation:",
        new="    if False:",
        want=f"{U}.py::TestResolveFence::test_each_fence_break_has_its_own_reason",
        why="room generation 已轮转仍允许裁决 ⇒ 基于过期基线的选择被写进新 generation",
    ),
    Mutation(
        id="M59", side="be", path=CONFLICTS, kind="replace",
        anchor="    if application.write_fence_epoch != room.write_fence_epoch:",
        new="    if False:",
        want=f"{U}.py::TestResolveFence::test_each_fence_break_has_its_own_reason",
        why="write fence epoch 已提升（有 participant 被撤销/超时）仍放行 ⇒ 被撤销的 writer "
            "的改动经裁决路径回到底稿",
    ),
    Mutation(
        id="M60", side="be", path=CONFLICTS, kind="replace",
        anchor="    if application.initiator_permission_epoch != room.initiator_permission_epoch:",
        new="    if False:",
        want=f"{U}.py::TestResolveFence::test_each_fence_break_has_its_own_reason",
        why="发起人权限 epoch 已变仍放行 ⇒ 权限被收回后旧授权仍可提交裁决"
            "（authorization-first 失效）",
    ),
    Mutation(
        id="M61", side="be", path=CONFLICTS, kind="replace",
        anchor="    if request.client_edit_epoch != application.client_edit_epoch:",
        new="    if False:",
        want=f"{U}.py::TestResolveFence::test_each_fence_break_has_its_own_reason",
        why="客户端编辑轮次已变仍放行 ⇒ 冲突预览基于过期快照，用户看到的三值不是当前真值",
    ),
    Mutation(
        id="M62", side="be", path=CONFLICTS, kind="replace",
        anchor="    if room.state_is_refresh_required:",
        new="    if False:",
        want=f"{U}.py::TestResolveFence::test_each_fence_break_has_its_own_reason",
        why="room 处于 refresh-required 仍放行 ⇒ 上次 merged 与 incoming 不等值还没让编辑器"
            "确认新基线，就在旧基线上继续裁决",
    ),
    Mutation(
        id="M63", side="be", path=CONFLICTS, kind="replace",
        anchor="    if request.conflict_set_digest != room.conflict_set_digest:",
        new="    if False:",
        want=f"{U}.py::TestResolveFence::test_each_fence_break_has_its_own_reason",
        why="冲突集摘要不再比对 ⇒ 冲突列表已变（多/少了条目）仍按旧列表落裁决",
    ),
    Mutation(
        id="M64", side="be", path=CONFLICTS, kind="replace",
        anchor="    if same_canonical:",
        new="    if False:",
        want=f"{U}.py::TestResolveFence::test_same_application_higher_sequence_folds_and_never_supersedes_itself",
        why="同一 canonical application 的更高 request sequence 不再做单调 fold ⇒ 自己把自己"
            "判 stale/superseded（AC 8.5 明文禁止 self-supersede）",
    ),
    Mutation(
        id="M65", side="be", path=CONFLICTS, kind="replace",
        anchor="        and room.latest_durable_sequence > application.effective_request_sequence",
        new="        and False",
        want=f"{U}.py::TestResolveFence::test_newer_different_canonical_application_supersedes",
        why="room latest durable 指向另一个**更新**的 application 时不再判 superseded ⇒ "
            "旧 operation 的裁决覆盖新 application 的结果",
    ),
    Mutation(
        id="M66", side="be", path=CONFLICTS, kind="replace",
        anchor="    if request.expected_current_revision != room.current_revision:",
        new="    if False:",
        want=f"{U}.py::TestResolveFence::test_current_revision_change_rebases",
        why="content revision 已推进仍按旧 current 落裁决 ⇒ 丢掉期间的服务端改动"
            "（AC 8.5 要求返回 409 `CONFLICT_REBASED` 并以 frozen base 重跑三方 merge）",
    ),
    Mutation(
        id="M67", side="be", path=CONFLICTS, kind="replace",
        anchor="                application_id=application.canonical_application_id,",
        new="                application_id=duplicate_link.primary.application_id,",
        want=f"{U}.py::TestResolveFence::test_invalid_duplicate_link_is_rejected_before_canonicalize",
        why="把「duplicate 目标必须已绑定本次 canonical application」改成自比 ⇒ "
            "`None != None` 恒假，stranded shell（未绑定 application 的 pre-correlation 壳）"
            "被当合法 primary。🔴 这条能被抓到，靠的是守卫按 `broken` 参数断言各自的"
            "可分辨文案 —— 只断言异常类型时会被另外五条禁令遮蔽",
    ),
    Mutation(
        id="M68", side="be", path=CONFLICTS, kind="replace",
        anchor="        if shape is not OperationShape.duplicate:",
        new="        if False:",
        want=f"{U}.py::TestResolveFence::test_duplicate_link_requires_a_terminal_duplicate_requested_operation",
        why="`duplicate_link` 的前置条件（requested 必须是 terminal duplicate）不再校验 ⇒ "
            "primary 自己被当 duplicate 去校验直指关系，调用方用法错被静默接受",
    ),
    Mutation(
        id="M69", side="be", path=CONFLICTS, kind="delete",
        anchor='    FenceReason.ok: "全部乐观锁一致，可提交裁决",',
        want=f"{U}.py::TestResolveFence::test_every_reason_message_is_pairwise_distinct",
        why="删掉一条 reason 文案 ⇒ `FENCE_REASON_MESSAGES` 与 `FenceReason` 不再一一对应，"
            "`FenceEvaluation.message` 在该 reason 上 KeyError",
    ),
    Mutation(
        id="M70", side="be", path=CONFLICTS, kind="replace",
        anchor='    FenceReason.write_fence_changed: "room write fence epoch 已提升（有 participant 被撤销或超时）",',
        new='    FenceReason.write_fence_changed: "room generation 已轮转，需重开编辑器确认新基线后再裁决",',
        want=f"{U}.py::TestResolveFence::test_every_reason_message_is_pairwise_distinct",
        why="让两条 reason 共用同一句文案 ⇒ 「哪条判据在起作用」不可分辨，"
            "短路其中一条时另一条会把它遮蔽（本 spec 已两次实测到的 GREEN 成因）",
    ),
    Mutation(
        id="M71", side="be", path=CONFLICTS, kind="replace",
        anchor="        return self.decision in (FenceDecision.proceed, FenceDecision.fold)",
        new="        return True",
        want=f"{U}.py::TestResolveFence::test_newer_different_canonical_application_supersedes",
        wants=(
            f"{U}.py::TestResolveFence::test_current_revision_change_rebases",
            f"{U}.py::TestResolveFence::test_each_fence_break_has_its_own_reason",
        ),
        why="`may_apply` 恒真 ⇒ rejected/superseded/rebase 三种判定照样产出 merged projection，"
            "整个 fence 变成只记录不拦截",
    ),
    Mutation(
        id="M72", side="be", path=CONFLICTS, kind="replace",
        anchor="        if not is_digest(self.conflict_set_digest):",
        new="        if False:",
        want=f"{U}.py::TestResolveFence::test_request_rejects_malformed_digest_and_negative_counters",
        why="全零 hash / 非法 digest 进 fence 请求 ⇒ 与「摘要一致」的比较可能因两边都是"
            "全零而通过（Task 12 已登记的 typed-null 反例形态）",
    ),
    Mutation(
        id="M73", side="be", path=CONFLICTS, kind="replace",
        anchor="            if getattr(self, name) < 0:",
        new="            if False:",
        want=f"{U}.py::TestResolveFence::test_request_rejects_malformed_digest_and_negative_counters",
        why="负数 generation/epoch/sequence 进 fence 请求 ⇒ 单调 fold 的比较基准可以被"
            "负值污染（`fold_effective_sequence` 取 GREATEST）",
    ),

    # ══ 十一、否定式承诺：只能靠**注入**证明可 falsify ════════════════════
    Mutation(
        id="M74", side="be", path=MERGE, kind="replace",
        anchor="        _put(merged_values, locator, c)",
        scope="    merged = Projection(",
        offset=-2,
        new="        _put(merged_values, locator, i)",
        want=f"{U}.py::TestThreeWayTruthTable::test_never_last_write_wins",
        wants=(
            f"{U}.py::TestProperty25And26Hypothesis::test_property_same_field_three_values_never_auto_picks_a_side",
            f"{U}.py::TestProperty26SameFieldDifferentValues::test_three_values_are_complete_and_neither_side_applied",
            f"{U}.py::TestThreeWayTruthTable::test_row",
        ),
        why="🔴 **注入**：往 value/delete_update 冲突分支写入 incoming ⇒ 直接实现 "
            "last-write-wins。「同字段冲突不自动选边」是否定式承诺 —— 源码里没有"
            "「选 incoming」的语句可短路，只能注入反例（同 Task 12 的 M51 / Task 13 的 M40~M43）",
    ),
    Mutation(
        id="M75", side="be", path=MERGE, kind="insert",
        anchor='    """把胜出信封写进 merged。absent ⇒ **不写键**（键缺失就是 MISSING 的表示）。"""',
        new="    if not envelope.present:\n        envelope = ValueEnvelope.of(None)\n",
        want=f"{U}.py::TestMissingSentinel::test_deleted_and_cleared_produce_different_merged_results",
        wants=(
            f"{U}.py::TestThreeWayTruthTable::test_row",
            f"{U}.py::TestMergeOutcomeDerivedJudgements::test_incoming_managed_keys_and_deleted_keys",
        ),
        why="🔴 **注入**：在写入 merged 的唯一出口把 absent 折叠成显式 null ⇒ "
            "「行/载体被删」与「在 OO 里清空这一格」产出同一个 merged。"
            "「MISSING 永不折叠成 None」是否定式承诺，短路无从下手 —— 与 M01（规范化层）、"
            "M02（值比较层）、M04（信封比较层）合起来把四个层级都证明可 falsify",
    ),
    Mutation(
        id="M76", side="be", path=MERGE, kind="insert",
        anchor="from enum import Enum",
        new="if False:  # noqa\n    import openpyxl  # noqa: F401\n",
        want=f"{U}.py::TestTask14ScopeBoundary::test_no_carrier_library_or_persistence_surface",
        why="🔴 **注入**：给纯域加载体库依赖。「本任务零 openpyxl/python-docx」是否定式承诺。"
            "刻意包在 `if False:` 里 —— 真执行 import 会变成 collect ERROR，"
            "判定退化成 WRONG-TEST 而不是 RED（同时也证明判据扫的是源码结构不是运行时）",
    ),
    Mutation(
        id="M77", side="be", path=MERGE, kind="insert",
        anchor="MISSING: Final[_Missing] = _Missing()",
        new="\n\nclass ContentMutationService:  # noqa\n    pass\n",
        want=f"{U}.py::TestTask14ScopeBoundary::test_content_mutation_service_is_defined_exactly_once",
        why="🔴 **注入**：在 merge.py 里再定义一个 `ContentMutationService`。"
            "判据必须是**类定义**而不是词出现 —— `ContentMutationService` 被 6+ 个模块的"
            "注释/文案提到，按词判会得出「到处都有」的错误结论。"
            "Task 15 落地后该判据从「目标还不存在」翻转成「恰一处定义且在 "
            "content_mutation.py」：本条证明 ≥2 处（出现第二个业务提交边界）会被抓",
    ),
    Mutation(
        id="M78", side="be", path=PKG_INIT, kind="insert",
        anchor='"""',
        new="\nif False:  # noqa\n"
            "    from app.services.workpaper_sync.merge import merge_projections  # noqa: F401\n",
        want=f"{U}.py::TestTask14ScopeBoundary::test_merge_domain_has_exactly_one_production_consumer",
        why="🔴 **注入**：在生产包 `__init__.py` 里再接一次 merge 域。Task 14 时期这条边界是"
            "「零生产消费方」，Task 15 接线后翻转为「**恰一个**消费方且是 "
            "content_mutation.py」—— 注入第二个消费方即证明「有人绕过唯一 "
            "ContentMutationService.commit(...) 直接消费 merge 域」会被抓。"
            "两个方向（0 个 / ≥2 个）都可 falsify，判据没有被退役削弱成恒真",
    ),
    Mutation(
        id="M79", side="be", path=MERGE, kind="replace",
        anchor='        "blocking_task": "27,28",',
        new='        "blocking_task": "",',
        want=f"{U}.py::TestTask14ScopeBoundary::test_deferred_consumers_registration_is_complete",
        why="延后登记丢掉 `blocking_task` ⇒ 「以后再说」不再是可核对的登记，"
            "没人知道该等哪个任务来接线（收口任务也无法机器核对）。"
            "锚点从原先的 `\"15,26\"` 改到仍未接线的 resolve API 那条（27,28）："
            "Task 15 已把 merge_projections 的登记退役进 RETIRED_DEFERRALS",
    ),
    Mutation(
        id="M80", side="be", path=MERGE, kind="insert",
        anchor="def settled_projection(outcome: MergeOutcome) -> Projection:",
        new="    if False:  # noqa\n"
            "        outcome.session.commit()\n",
        want=f"{U}.py::TestTask14ScopeBoundary::test_no_carrier_library_or_persistence_surface",
        why="🔴 **注入**：在登记表**之外**放一处真 `session.commit()` 面。"
            "M76 证明的是「载体库依赖会被抓」，本条证明的是「剔除登记表文案的定界没有"
            "把真副作用面一起吞掉」—— `_cut_registration_block` 若改用固定字符窗口或 "
            "`index()` 算边界，就会剔错范围而让本条变 GREEN",
    ),
]

if __name__ == "__main__":
    raise SystemExit(run_cli(
        mutations=MUTATIONS,
        guard_files=GUARD_FILES,
        repo=REPO,
        backend_args=[
            "backend/tests/workpaper_sync/test_task14_merge_conflicts.py",
            "-q", "--tb=no", "-rf", "-p", "no:cacheprovider",
        ],
        # 冻结基线来源：
        #   2026-08-25 Task 14 收口实测 177 passed（首轮变异后由 175 → 177：M32/M48 判
        #   GREEN、M56 判 WRONG-TEST，三条都归因为守卫缺陷并按「不降标」修补）。
        #   2026-08-26 Task 15 退役 merge 域延后登记后 → **178 passed**：
        #   `test_merge_domain_has_no_production_consumer_yet` 与
        #   `test_blocking_task_15_is_registered_and_its_target_does_not_exist_yet`
        #   翻转成 `test_merge_domain_has_exactly_one_production_consumer` /
        #   `test_content_mutation_service_is_defined_exactly_once`，并新增
        #   `test_retired_deferral_records_who_wired_it`（净 +1）。
        baseline_backend_passed=178,
    ))
