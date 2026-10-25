"""删行的行键解析 · 区间端点塌陷方向 · 结构锁（Property 6 + 勘误 E.6）。

spec: workpaper-sync-row-deletion-multi-region-propagation
Tasks: 6.4 · 7.1~7.4 · 13
Requirements: 1.1~1.13 · 6.6

═══ 为什么从 `test_row_deletion_declaration.py` 拆出来 ═══

原文件 1055 行，超 pre-commit 的 800 行上限。切缝按**判据对象**取：
原文件留「载体不变式 / 零传播 / 声明与载体同源 / 计划期 fail-closed」（都在问
「声明对不对」），本文件收「行键解析 / 区间端点塌陷方向 / 结构锁」（都在问
「改写算术与代码形态对不对」）。

判据与它的反向对照组**没有被拆开**：三个类各自的变异反证都在本文件内。
共享固件（`build_entries` / `plan_delete` 与那组区间常量）从原文件 import ——
它们是模块级公开名，不复制第二份（复制就是第二真源，两边一漂就各说各话）。

═══ hypothesis 配置 ═══

`max_examples=5`（用户明确要求，禁默认 100）。
"""

from __future__ import annotations

from app.services.workpaper_sync import excel_workbook_row_change as N1  # noqa: E402
from hypothesis import given, settings
from hypothesis import strategies as st
import ast
import inspect
import pytest
import textwrap

# 🔴 共享固件从原文件 import，**不复制第二份**（复制即第二真源，两边一漂就各说各话）。
from test_row_deletion_declaration import (  # noqa: E402
    PBT,
    REGION_FIRST,
    REGION_LAST,
    _BACKEND,
    _endpoint_rows,
    _uuids,
    build_entries,
    plan_delete,
)




# ═══════════════════════════════════════════════════════════════════════════
# 6. Property 6：留痕键与被删行一一对应
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty6DeletedRowKeys:
    """**Feature: workpaper-sync-row-deletion-multi-region-propagation, Property 6: 留痕键与被删行一一对应**

    **Validates: Requirements 1.9, 1.10**
    """

    @PBT
    @given(
        deleted=st.lists(
            st.integers(min_value=REGION_FIRST, max_value=REGION_LAST),
            min_size=1,
            max_size=6,
        ).map(lambda xs: tuple(sorted(set(xs))))
    )
    def test_keys_are_distinct_and_count_matches(
        self, deleted: tuple[int, ...]
    ) -> None:
        change = plan_delete(deleted, entries=build_entries(), allow_ref_errors=True)
        # 零传播时门面返回 None，但留痕键已在返回之前算过 ⇒ 用直接调用复核
        keys = N1.resolve_deleted_row_keys(deleted, row_uuids=_uuids(list(deleted)))
        assert len(keys) == len(deleted)
        assert len(set(keys)) == len(keys), f"留痕键有重复：{keys}"
        if change is not None:
            assert change.deleted_row_keys == keys

    def test_missing_identity_is_refused(self) -> None:
        """两者皆缺 ⇒ 抛，而不是产出一份不完整的留痕。"""
        with pytest.raises(N1.MissingRowIdentityError):
            plan_delete((20,), row_uuids={20: ""}, stable_ordinals={})

    def test_falls_back_to_stable_ordinal(self) -> None:
        change = plan_delete(
            (20,), row_uuids={}, stable_ordinals={20: "SEQ-0020"}
        )
        assert change is not None
        assert change.deleted_row_keys == ("SEQ-0020",)

    def test_facade_is_the_second_production_consumer(self) -> None:
        """🔴 B4 的「`resolve_deleted_row_keys` 生产入口只有 `build_delete_plan`」由本门面闭合。

        现算生产调用方数并断言 >= 2；**不**写死 2（将来再多一个是好事，不该打红）。
        """
        import ast as _ast

        src = (
            _BACKEND / "app/services/workpaper_sync/excel_workbook_row_change.py"
        ).read_bytes().decode("utf-8")
        tree = _ast.parse(src)
        callers: set[str] = set()

        def _walk(node: _ast.AST, current: str) -> None:
            for child in _ast.iter_child_nodes(node):
                name = current
                if isinstance(child, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    name = child.name
                if isinstance(child, _ast.Call):
                    fn = child.func
                    called = getattr(fn, "id", None) or getattr(fn, "attr", None)
                    if called == "resolve_deleted_row_keys":
                        callers.add(name)
                _walk(child, name)

        _walk(tree, "<module>")
        assert "plan_workbook_row_change_for_delete" in callers, callers
        assert len(callers) >= 2, f"生产调用方现算 {len(callers)} 个：{callers}"


# ═══════════════════════════════════════════════════════════════════════════
# 7. 区间端点的**方向**判据（PBT 抓出来的真缺陷，单独立案钉死）
# ═══════════════════════════════════════════════════════════════════════════


class TestRangeEndpointCollapseDirection:
    """起点向下塌、终点向上塌 —— 两个方向必须各有显式样本。

    **Validates: Requirements 1.6, 4.7, 5.6**

    🔴 这一组是 Property 3 的 PBT 在 `deleted=(7,)` 上**当场打红**逼出来的：首版把区间
    两个端点都用「终点」公式，于是起点 7 被算成 6（区间凭空多覆盖一行）。反过来若都用
    「起点」公式，删最后一个受管行时 `SUM(B7:B25)` 保持 `B7:B25`，而 footer 已从 26
    上移到 25 ⇒ **合计把 footer 自己算进去**（design A5 点名的错值）。

    ⚠ 两个公式在**存活行**上恒相等 ⇒ 判据必须用「端点恰好落在被删行上」的样本，
    否则这个区分恒真空转。
    """

    @pytest.mark.parametrize(
        "deleted,want_head,want_tail",
        [
            ((REGION_FIRST,), REGION_FIRST, REGION_LAST - 1),          # 只删起点
            ((REGION_LAST,), REGION_FIRST, REGION_LAST - 1),           # 只删终点
            ((REGION_FIRST, REGION_LAST), REGION_FIRST, REGION_LAST - 2),  # 两端都删
            ((REGION_FIRST, REGION_FIRST + 1), REGION_FIRST, REGION_LAST - 2),  # 起点连续段
            ((20,), REGION_FIRST, REGION_LAST - 1),                    # 都是存活行（对照）
        ],
    )
    def test_full_region_range_shrinks_correctly(
        self, deleted: tuple[int, ...], want_head: int, want_tail: int
    ) -> None:
        shift = N1.RowDeletionShift(
            deleted_rows=deleted,
            region_first_row=REGION_FIRST,
            region_last_row=REGION_LAST,
        )
        assert shift.shift_range_start(REGION_FIRST) == want_head
        assert shift.shift_range_end(REGION_LAST) == want_tail

    def test_the_two_formulas_differ_only_on_deleted_rows(self) -> None:
        """存活行上两者恒相等 —— 这条说明「为什么必须用边界样本」。"""
        shift = N1.RowDeletionShift(
            deleted_rows=(20, 22), region_first_row=REGION_FIRST, region_last_row=REGION_LAST
        )
        differing = [
            row
            for row in range(1, REGION_LAST + 5)
            if shift.shift_range_start(row) != shift.shift_range_end(row)
        ]
        assert differing == [20, 22], differing

    def test_declared_text_matches_the_direction_on_the_wire(self) -> None:
        """端到端：删最后一个受管行后，跨 sheet 全区间引用的**文本**必须收缩。

        这条是「方向搞错会产出什么坏字节」的直接判据 —— 不看载体算术，看声明文本。
        """
        change = plan_delete((REGION_LAST,))
        assert change is not None
        # 🔴 只看**终点恰好落在被删行上**的条目 —— 方向之争只在那里发生。
        #    首版把全部区间都断言成 `tail_after < REGION_LAST`，被 `Print_Area`
        #    （`$A$1:$W$26`，终点是 footer 行 26 而非 25）当场打红 —— 它上移到 25
        #    是**正确**行为。判据写粗了就会把对的判成错的。
        on_boundary = [
            e
            for e in change.propagations
            if ":" in e.ref_before and _endpoint_rows(e.ref_before)[-1] == REGION_LAST
        ]
        assert on_boundary, "固件里没有终点落在受管末行的区间引用 ⇒ 本条空转"
        for entry in on_boundary:
            tail_after = _endpoint_rows(entry.ref_after)[-1]
            assert tail_after == REGION_LAST - 1, (
                f"{entry.locator} 的终点 {REGION_LAST}→{tail_after}，应为 "
                f"{REGION_LAST - 1}：{entry.ref_before!r} → {entry.ref_after!r} —— "
                "不上移则合计会把上移后的 footer 算进去"
            )
        # 对照：终点在被删行**之下**的条目按普通位移上移一行（不是不动）
        below = [
            e
            for e in change.propagations
            if ":" in e.ref_before and _endpoint_rows(e.ref_before)[-1] > REGION_LAST
        ]
        for entry in below:
            assert _endpoint_rows(entry.ref_after)[-1] == (
                _endpoint_rows(entry.ref_before)[-1] - 1
            ), f"{entry.locator} 终点在被删行之下，应上移 1：{entry.ref_after!r}"

    def test_declared_head_does_not_drift_up_when_first_row_is_deleted(self) -> None:
        """删受管区**首行**时起点必须**原地不动**（向下塌到下一存活行的新位置）。"""
        change = plan_delete((REGION_FIRST,))
        assert change is not None
        ranges = [e for e in change.propagations if ":" in e.ref_before]
        assert ranges
        for entry in ranges:
            head_before = _endpoint_rows(entry.ref_before)[0]
            head_after = _endpoint_rows(entry.ref_after)[0]
            if head_before == REGION_FIRST:
                assert head_after == REGION_FIRST, (
                    f"{entry.locator} 起点从 {head_before} 漂到 {head_after} —— "
                    "区间凭空多覆盖一行"
                )


# ═══════════════════════════════════════════════════════════════════════════
# 8. 结构锁：单一扫描真源 · 不复用错函数 · insert 门面签名逐字不变
# ═══════════════════════════════════════════════════════════════════════════


class TestStructuralLocks:
    """**Validates: Requirements 1.4, 1.5, 10.1, 10.2**"""

    def test_both_facades_call_the_single_scan_helper(self) -> None:
        """🔴 AST：两个门面都调 `_scan_from_entries`，模块内不存在第二份扫描序列。"""
        src = (
            _BACKEND / "app/services/workpaper_sync/excel_workbook_row_change.py"
        ).read_bytes().decode("utf-8")
        tree = ast.parse(src)
        calls: dict[str, set[str]] = {}

        def _walk(node: ast.AST, current: str) -> None:
            for child in ast.iter_child_nodes(node):
                name = current
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = child.name
                if isinstance(child, ast.Call):
                    called = getattr(child.func, "id", None) or getattr(
                        child.func, "attr", None
                    )
                    if called:
                        calls.setdefault(name, set()).add(called)
                _walk(child, name)

        _walk(tree, "<module>")
        for facade in (
            "plan_workbook_row_change_for_insert",
            "plan_workbook_row_change_for_delete",
        ):
            assert "_scan_from_entries" in calls.get(facade, set()), (
                f"{facade} 没调 `_scan_from_entries`：{sorted(calls.get(facade, set()))}"
            )
        # 模块内 `scan_reference_carriers` 的调用方**只有** `_scan_from_entries`
        scanners = {fn for fn, names in calls.items() if "scan_reference_carriers" in names}
        assert scanners == {"_scan_from_entries"}, (
            f"扫描器有第二个调用方：{scanners} —— 抄第二份必然与执行侧漂移"
        )

    def test_insert_facade_signature_is_byte_identical(self) -> None:
        """🔴 插行门面签名逐字不变 ⇒ B2 的 2 个生产调用方零改动。"""
        sig = inspect.signature(N1.plan_workbook_row_change_for_insert)
        assert list(sig.parameters) == [
            "entries",
            "managed_sheet_name",
            "managed_sheet_part",
            "insert_at",
            "count",
            "style_from",
            "region_first_row",
            "region_last_row",
        ], list(sig.parameters)
        for name in list(sig.parameters)[1:]:
            assert sig.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
            assert sig.parameters[name].default is inspect.Parameter.empty, (
                f"{name} 有了默认值 —— 漏传会从 TypeError 降级成深埋的域错误"
            )

    def test_delete_facade_does_not_call_build_delete_plan(self) -> None:
        """🔴 不整体调 `build_delete_plan` —— 它会顺带构造一个不成立的 at/count 计划。"""
        src = textwrap.dedent(inspect.getsource(N1.plan_workbook_row_change_for_delete))
        tree = ast.parse(src)
        called = {
            getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
        }
        assert "build_delete_plan" not in called, called
        # 但三个判据函数必须各自被调到
        for needed in (
            "find_dangling_sites",
            "find_bare_dangling_rows",
            "resolve_deleted_row_keys",
            "build_propagation_entry",
        ):
            assert needed in called, f"{needed} 没被调用：{sorted(c for c in called if c)}"

    def test_delete_facade_never_passes_allow_ref_errors_true(self) -> None:
        """🔴 上游 §更正 4：不得在实现里硬写 `allow_ref_errors=True` 绕过悬空门。"""
        src = textwrap.dedent(inspect.getsource(N1.plan_workbook_row_change_for_delete))
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg == "allow_ref_errors":
                    assert not (
                        isinstance(kw.value, ast.Constant) and kw.value.value is True
                    ), "实现里硬写了 allow_ref_errors=True"
        sig = inspect.signature(N1.plan_workbook_row_change_for_delete)
        assert sig.parameters["allow_ref_errors"].default is False

    def test_zero_regression_observed_symbols_are_untouched(self) -> None:
        """🔴 Requirement 10.1/10.2：`_rewrite_formula_refs` 不在本 spec 的改动面里。

        判据形态是「删行侧的反向映射由**实参**传入」：模块里对
        `_rewrite_formula_refs` 的调用必须带 `remap=` 关键字实参，
        而不是让那个函数内部认识删行。
        """
        from app.services.workpaper_sync import excel_row_shift as RS

        src = textwrap.dedent(inspect.getsource(RS._rewrite_formula_refs))
        for forbidden in ("RowDeletionShift", "deleted_rows", "shift_range_end"):
            assert forbidden not in src, (
                f"`_rewrite_formula_refs` 里出现了 {forbidden} —— "
                "删行语义被塞进了 Property 28 的被观测对象"
            )
        entry_src = textwrap.dedent(inspect.getsource(N1.build_propagation_entry))
        tree = ast.parse(entry_src)
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if called != "_rewrite_formula_refs":
                continue
            assert any(kw.arg == "remap" for kw in node.keywords), (
                "`remap` 不是实参 —— 反向映射被写进了函数内部常量"
            )
            found = True
        assert found, "`build_propagation_entry` 里找不到对 `_rewrite_formula_refs` 的调用"
