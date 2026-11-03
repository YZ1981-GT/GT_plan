"""Runtime typed_eval 单元测试（需求 1.3、1.4、1.7；ADR-FHIC-06 第 3~5、7 点）。

SQLite / mock 测试——plan_batch 注入 read_ref / eval_fn。
"""
from __future__ import annotations

import asyncio
import types
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.formula_management.stable_key import normalize_sheet_key
from app.services.formula_runtime.typed_eval import (
    BatchDefinition,
    PlanOutcome,
    PlanResult,
    plan_batch,
)
from app.services.wp_cell_reader import WpCellRead
from app.services.wp_ref_strict import classify_wp_ref
from app.services.wp_parsed_data_service import write_cell_to_parsed_data

# 任务 24 在 worktree 中加入 TargetSheet / resolve_target_sheet，主树可能尚未合入
try:
    from app.services.wp_parsed_data_service import TargetSheet, resolve_target_sheet
    _HAS_TARGET_SHEET = True
except ImportError:
    _HAS_TARGET_SHEET = False


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ok(val: Decimal | float | int, **kw) -> WpCellRead:
    return WpCellRead("ok", Decimal(str(val)), None, None, None, **kw)


def _missing(reason: str = "missing") -> WpCellRead:
    return WpCellRead("missing", None, reason, None, None)


def _blocked(reason: str = "blocked") -> WpCellRead:
    return WpCellRead("blocked", None, reason, None, None)


def _run(coro):
    # 每次新建事件循环：get_event_loop() 依赖「当前线程恰好留着一个循环」，与先跑的用例（asyncio.run 用完即关）
    # 同进程时报 RuntimeError: There is no current event loop（2026-10-30 按文件顺序重排复现）
    return asyncio.run(coro)


class MockReadRef:
    """可编程的读取函数替身。"""

    def __init__(self, table: dict[tuple, WpCellRead] | None = None):
        self._table = table or {}
        self._default = _missing("not configured")

    def set(self, wp_code: str, second: str, third: str | None, result: WpCellRead):
        self._table[(wp_code, second, third)] = result

    async def __call__(self, wp_code: str, second: str, third: str | None) -> WpCellRead:
        return self._table.get((wp_code, second, third), self._default)


class MockEvalFn:
    """把 wp_values 里的值加到表达式求值结果中的简单模拟。"""

    async def __call__(self, expr: str, wp_values: dict[str, Decimal]) -> tuple[Decimal, list[str]]:
        # 简单：如果 wp_values 非空，取其所有值之和
        total = sum(wp_values.values(), Decimal("0"))
        return total, []


# ---------------------------------------------------------------------------
# resolve_target_sheet（任务 24 已有，保留）
# ---------------------------------------------------------------------------


def _make_wp(parsed_data: dict | None = None) -> Any:
    return types.SimpleNamespace(parsed_data=parsed_data)


@pytest.mark.skipif(not _HAS_TARGET_SHEET, reason="resolve_target_sheet not merged")
class TestResolveTargetSheet:
    def test_found_unique(self):
        parsed = {"html_data": {"Sheet1": {"cells": {}}, "Sheet2": {"cells": {}}}}
        result = resolve_target_sheet(parsed, "sheet1")
        assert result.state == "found"
        assert result.sheet_name == "Sheet1"

    def test_blocked_not_found(self):
        parsed = {"html_data": {"Sheet1": {"cells": {}}}}
        result = resolve_target_sheet(parsed, "不存在的表")
        assert result.state == "blocked_not_found"

    def test_blocked_ambiguous(self):
        parsed = {"html_data": {"sheet1": {"cells": {}}, "Sheet1": {"cells": {}}}}
        result = resolve_target_sheet(parsed, "sheet1")
        assert result.state == "blocked_ambiguous"

    def test_none_parsed_data(self):
        result = resolve_target_sheet(None, "any")
        assert result.state == "blocked_not_found"

    def test_empty_html_data(self):
        result = resolve_target_sheet({"html_data": {}}, "sheet1")
        assert result.state == "blocked_not_found"


@pytest.mark.skipif(not _HAS_TARGET_SHEET, reason="require_existing_sheet not merged")
class TestWriteCellRequireExistingSheet:
    def test_missing_target_sheet_blocked(self, monkeypatch):
        import app.services.wp_parsed_data_service as svc
        monkeypatch.setattr(svc, "flag_modified", lambda *a, **kw: None)
        wp = _make_wp({"html_data": {"Sheet1": {"cells": {}, "max_row": 3, "max_col": 2}}})
        with pytest.raises(ValueError, match="目标工作表不存在"):
            write_cell_to_parsed_data(wp, sheet_name="不存在的表", cell_ref="A1", value=100, require_existing_sheet=True)

    def test_existing_sheet_no_error(self, monkeypatch):
        import app.services.wp_parsed_data_service as svc
        monkeypatch.setattr(svc, "flag_modified", lambda *a, **kw: None)
        wp = _make_wp({"html_data": {"Sheet1": {"cells": {}, "max_row": 3, "max_col": 2}}})
        write_cell_to_parsed_data(wp, sheet_name="Sheet1", cell_ref="B5", value=42, require_existing_sheet=True)
        assert wp.parsed_data["html_data"]["Sheet1"]["cells"]["B5"] == 42

    def test_default_false_allows_new_sheet(self, monkeypatch):
        import app.services.wp_parsed_data_service as svc
        monkeypatch.setattr(svc, "flag_modified", lambda *a, **kw: None)
        wp = _make_wp({"html_data": {}})
        write_cell_to_parsed_data(wp, sheet_name="NewSheet", cell_ref="A1", value=99)
        assert "NewSheet" in wp.parsed_data["html_data"]


@pytest.mark.skipif(not _HAS_TARGET_SHEET, reason="require_existing_sheet not merged")
class TestWriteBeyondExtent:
    def test_write_beyond_extent_allowed(self, monkeypatch):
        import app.services.wp_parsed_data_service as svc
        monkeypatch.setattr(svc, "flag_modified", lambda *a, **kw: None)
        wp = _make_wp({"html_data": {"Sheet1": {"cells": {"A1": 1}, "max_row": 3, "max_col": 2}}})
        write_cell_to_parsed_data(wp, sheet_name="Sheet1", cell_ref="Z100", value="远方")
        sheet = wp.parsed_data["html_data"]["Sheet1"]
        assert sheet["cells"]["Z100"] == "远方"
        assert sheet["max_row"] == 100
        assert sheet["max_col"] == 26

    def test_write_within_extent_no_shrink(self, monkeypatch):
        import app.services.wp_parsed_data_service as svc
        monkeypatch.setattr(svc, "flag_modified", lambda *a, **kw: None)
        wp = _make_wp({"html_data": {"Sheet1": {"cells": {}, "max_row": 50, "max_col": 10}}})
        write_cell_to_parsed_data(wp, sheet_name="Sheet1", cell_ref="A1", value="小格")
        sheet = wp.parsed_data["html_data"]["Sheet1"]
        assert sheet["max_row"] == 50
        assert sheet["max_col"] == 10


# ---------------------------------------------------------------------------
# classify_wp_ref 四种写法分类
# ---------------------------------------------------------------------------


class TestClassifyWpRef:
    """四种 WP 写法分类（ADR-FHIC-06 第 3 点）。"""

    def test_cell_3(self):
        assert classify_wp_ref("Sheet1", "B5") == "cell_3"

    def test_cell_2(self):
        assert classify_wp_ref("B5", None) == "cell_2"

    def test_column_2(self):
        assert classify_wp_ref("审定数", None) == "column_2"

    def test_d23_3(self):
        assert classify_wp_ref("坏账准备明细表D2-3", "本期计提合计") == "d23_3"

    def test_unknown_no_args(self):
        assert classify_wp_ref("", None) == "unknown"

    def test_unknown_non_a1_three_param(self):
        assert classify_wp_ref("Sheet1", "非A1") == "unknown"


# ---------------------------------------------------------------------------
# plan_batch：needs_review → blocked
# ---------------------------------------------------------------------------


class TestNeedsReview:
    """stable_key_needs_review=True ⇒ blocked「公式位置待复核」（需求 1.3）。"""

    def test_needs_review_blocked(self):
        defn = BatchDefinition(
            formula_id="f1", wp_code="D1", expression="WP('D1','B5')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
            stable_key_needs_review=True,
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=MockReadRef()))
        assert result.outcomes[0].state == "blocked"
        assert "待复核" in (result.outcomes[0].reason or "")


# ---------------------------------------------------------------------------
# plan_batch：空三元组（从 sheet_name/target_cell 推导）
# ---------------------------------------------------------------------------


class TestEmptyTriple:
    """三元组为空的旧行从 stable_key 推导（需求 1.3）。"""

    def test_derive_from_sheet_name_target_cell(self):
        """stable_sheet_key 为 None → 从 sheet_name+target_cell 推导。"""
        reader = MockReadRef()
        defn = BatchDefinition(
            formula_id="f1", wp_code="D1", expression="100",
            sheet_name="五、1 审定表D1-1", target_cell="B5",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=reader))
        o = result.outcomes[0]
        assert o.identity is not None
        assert o.identity[0] == "D1"  # wp_code.upper()
        assert o.identity[1] == normalize_sheet_key("五、1 审定表D1-1")
        assert o.identity[2] == "B5"  # field_key + row_key = "B" + "5"

    def test_derive_needs_review_if_not_a1(self):
        """target_cell 无法解析为 A1 → blocked。"""
        defn = BatchDefinition(
            formula_id="f1", wp_code="D1", expression="100",
            sheet_name="Sheet1", target_cell="净额",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=MockReadRef()))
        assert result.outcomes[0].state == "blocked"
        assert "待复核" in (result.outcomes[0].reason or "")


# ---------------------------------------------------------------------------
# plan_batch：四种写法取到 / 取不到
# ---------------------------------------------------------------------------


class TestFourWriteStyles:
    """四种 WP 写法各取到/取不到（需求 1.3）。"""

    def test_cell_3_found(self):
        reader = MockReadRef()
        reader.set("D1", "Sheet1", "B5", _ok(100))
        defn = BatchDefinition(
            formula_id="f1", wp_code="E1", expression="WP('D1','Sheet1','B5')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=reader, eval_fn=MockEvalFn()))
        assert result.outcomes[0].state == "ok"
        assert result.outcomes[0].value == Decimal("100")

    def test_cell_3_missing(self):
        reader = MockReadRef()
        reader.set("D1", "Sheet1", "B5", _missing("单元格未录入"))
        defn = BatchDefinition(
            formula_id="f1", wp_code="E1", expression="WP('D1','Sheet1','B5')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=reader))
        assert result.outcomes[0].state == "blocked"
        assert "单元格未录入" in result.outcomes[0].errors[0]

    def test_cell_2_found(self):
        reader = MockReadRef()
        reader.set("D1", "B5", None, _ok(200))
        defn = BatchDefinition(
            formula_id="f1", wp_code="E1", expression="WP('D1','B5')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=reader, eval_fn=MockEvalFn()))
        assert result.outcomes[0].state == "ok"
        assert result.outcomes[0].value == Decimal("200")

    def test_cell_2_missing(self):
        reader = MockReadRef()
        reader.set("D1", "B5", None, _missing("未录入"))
        defn = BatchDefinition(
            formula_id="f1", wp_code="E1", expression="WP('D1','B5')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=reader))
        assert result.outcomes[0].state == "blocked"

    def test_column_2_found(self):
        reader = MockReadRef()
        reader.set("D1", "审定数", None, _ok(300))
        defn = BatchDefinition(
            formula_id="f1", wp_code="E1", expression="WP('D1','审定数')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=reader, eval_fn=MockEvalFn()))
        assert result.outcomes[0].state == "ok"
        assert result.outcomes[0].value == Decimal("300")

    def test_column_2_missing(self):
        reader = MockReadRef()
        reader.set("D1", "审定数", None, _missing("无字段"))
        defn = BatchDefinition(
            formula_id="f1", wp_code="E1", expression="WP('D1','审定数')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=reader))
        assert result.outcomes[0].state == "blocked"

    def test_d23_3_found(self):
        reader = MockReadRef()
        reader.set("D2", "坏账准备明细表D2-3", "本期计提合计", _ok(400))
        defn = BatchDefinition(
            formula_id="f1", wp_code="E1", expression="WP('D2','坏账准备明细表D2-3','本期计提合计')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=reader, eval_fn=MockEvalFn()))
        assert result.outcomes[0].state == "ok"
        assert result.outcomes[0].value == Decimal("400")

    def test_d23_3_missing(self):
        reader = MockReadRef()
        reader.set("D2", "坏账准备明细表D2-3", "本期计提合计", _missing("无坏账数据"))
        defn = BatchDefinition(
            formula_id="f1", wp_code="E1", expression="WP('D2','坏账准备明细表D2-3','本期计提合计')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=reader))
        assert result.outcomes[0].state == "blocked"


# ---------------------------------------------------------------------------
# plan_batch：环（含自引用）→ blocked / 歧义 → blocked / 0 mutation
# ---------------------------------------------------------------------------


class TestCycleAndAmbiguity:
    """环和歧义检测（需求 1.4）。"""

    def test_self_reference_blocked(self):
        """自引用 WP('D1','Sheet1','B5') 引用自己 → blocked 循环引用、0 mutation。"""
        defn = BatchDefinition(
            formula_id="f1", wp_code="D1", expression="WP('D1','Sheet1','B5')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=MockReadRef()))
        assert result.outcomes[0].state == "blocked"
        assert "循环引用" in (result.outcomes[0].reason or "")
        assert len(result.mutations) == 0

    def test_mutual_cycle_blocked(self):
        """A → B → A 循环 → 两个都 blocked。"""
        a = BatchDefinition(
            formula_id="fa", wp_code="D1", expression="WP('D1','Sheet2','C3')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        b = BatchDefinition(
            formula_id="fb", wp_code="D1", expression="WP('D1','Sheet1','B5')",
            stable_sheet_key="Sheet2", row_key="3", field_key="C",
        )
        result = _run(plan_batch([a, b], year_verdict=None, read_ref=MockReadRef()))
        assert all(o.state == "blocked" for o in result.outcomes)
        assert all("循环引用" in (o.reason or "") for o in result.outcomes)
        assert len(result.mutations) == 0

    def test_cell_2_ambiguity_blocked(self):
        """两参 WP 命中多个批内目标 → blocked「引用有歧义」。"""
        # 两个定义在同一 wp_code 同一 cell (B5) 但不同 sheet
        target1 = BatchDefinition(
            formula_id="t1", wp_code="D1", expression="100",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        target2 = BatchDefinition(
            formula_id="t2", wp_code="D1", expression="200",
            stable_sheet_key="Sheet2", row_key="5", field_key="B",
        )
        referrer = BatchDefinition(
            formula_id="ref", wp_code="E1", expression="WP('D1','B5')",
            stable_sheet_key="SheetX", row_key="1", field_key="A",
        )
        result = _run(plan_batch([target1, target2, referrer], year_verdict=None, read_ref=MockReadRef()))
        ref_outcome = [o for o in result.outcomes if str(o.formula_id) == "ref"][0]
        assert ref_outcome.state == "blocked"
        assert "歧义" in (ref_outcome.reason or "")


# ---------------------------------------------------------------------------
# plan_batch：目标表缺失 → blocked
# ---------------------------------------------------------------------------


class TestTargetSheetMissing:
    """目标工作表不存在 → blocked（需求 1.8）。"""

    def test_target_sheet_not_found(self):
        parsed = {"html_data": {"Sheet1": {"cells": {}}}}
        defn = BatchDefinition(
            formula_id="f1", wp_code="D1", expression="100",
            stable_sheet_key="不存在的表",
            row_key="5", field_key="B",
            target_parsed_data=parsed,
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=MockReadRef()))
        assert result.outcomes[0].state == "blocked"
        assert "目标工作表不存在" in (result.outcomes[0].reason or "")

    @pytest.mark.parametrize("parsed", [{}, {"html_data": {}}, {"html_data": None}, {"other": 1}],
                             ids=["empty", "empty_html_data", "null_html_data", "no_html_data"])
    def test_loaded_but_empty_parsed_data_is_blocked_at_plan(self, parsed):
        """底稿已读到但没有任何工作表 ⇒ 计划阶段 blocked，不得放行到 apply 再失败（2026-10-30 修）。"""
        defn = BatchDefinition(
            formula_id="f1", wp_code="D1", expression="100",
            stable_sheet_key="sheet1", row_key="5", field_key="B",
            target_parsed_data=parsed,
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=MockReadRef()))
        assert result.outcomes[0].state == "blocked"
        assert result.outcomes[0].reason == "目标工作表不存在"

    def test_parsed_data_not_provided_is_not_checked(self):
        """反向：调用方没有提供底稿数据（None）⇒ 不做目标表校验，照常求值。"""
        defn = BatchDefinition(
            formula_id="f1", wp_code="D1", expression="100",
            stable_sheet_key="sheet1", row_key="5", field_key="B",
            target_parsed_data=None,
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=MockReadRef(), eval_fn=MockEvalFn()))
        assert result.outcomes[0].state == "ok", result.outcomes[0].reason


# ---------------------------------------------------------------------------
# plan_batch：非 WP 金标准（TB/NOTE/REPORT 引用）
# ---------------------------------------------------------------------------


class TestNonWpRefs:
    """TB/NOTE/REPORT 引用走 eval_fn，不建 WP 依赖边（需求 1.7 路径测试）。

    真正的非 WP 金标准断言在 test_runtime_replay_29_pg.py（PG）。
    这里只验证 plan_batch 对不含 WP 引用的表达式正确传给 eval_fn。
    """

    def test_tb_ref_through_eval_fn(self):
        """TB 引用不被 plan_batch 当作 WP 引用。"""
        async def eval_fn(expr: str, wp_values: dict) -> tuple[Decimal, list[str]]:
            assert "TB" in expr
            return Decimal("1234"), []

        defn = BatchDefinition(
            formula_id="f1", wp_code="D1", expression="TB('1001','审定数')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=MockReadRef(), eval_fn=eval_fn))
        assert result.outcomes[0].state == "ok"
        assert result.outcomes[0].value == Decimal("1234")

    def test_note_ref_through_eval_fn(self):
        async def eval_fn(expr: str, wp_values: dict) -> tuple[Decimal, list[str]]:
            return Decimal("567"), []

        defn = BatchDefinition(
            formula_id="f1", wp_code="D1", expression="NOTE('五、1','合计')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=MockReadRef(), eval_fn=eval_fn))
        assert result.outcomes[0].value == Decimal("567")

    def test_report_ref_through_eval_fn(self):
        async def eval_fn(expr: str, wp_values: dict) -> tuple[Decimal, list[str]]:
            return Decimal("890"), []

        defn = BatchDefinition(
            formula_id="f1", wp_code="D1", expression="REPORT('BS-001')",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        result = _run(plan_batch([defn], year_verdict=None, read_ref=MockReadRef(), eval_fn=eval_fn))
        assert result.outcomes[0].value == Decimal("890")


# ---------------------------------------------------------------------------
# plan_batch：跨底稿（E1 → D1）金标准路径
# ---------------------------------------------------------------------------


class TestCrossWpGold:
    """跨底稿引用——E1 底稿公式引用 D1 的 B5，D1 是字面量 1001。"""

    def test_cross_wp_chain(self):
        """D1.B5 = 1001 → E1 引用 WP('D1','Sheet1','B5') = 1001。"""
        reader = MockReadRef()

        d1 = BatchDefinition(
            formula_id="d1", wp_code="D1", expression="1001",
            stable_sheet_key="Sheet1", row_key="5", field_key="B",
        )
        e1 = BatchDefinition(
            formula_id="e1", wp_code="E1", expression="WP('D1','Sheet1','B5')",
            stable_sheet_key="SheetE", row_key="1", field_key="A",
        )

        async def eval_fn(expr: str, wp_values: dict) -> tuple[Decimal, list[str]]:
            if wp_values:
                return sum(wp_values.values(), Decimal("0")), []
            # 字面量
            try:
                return Decimal(expr), []
            except Exception:
                return Decimal("0"), [f"无法求值：{expr}"]

        result = _run(plan_batch([d1, e1], year_verdict=None, read_ref=reader, eval_fn=eval_fn))
        d1_out = [o for o in result.outcomes if str(o.formula_id) == "d1"][0]
        e1_out = [o for o in result.outcomes if str(o.formula_id) == "e1"][0]
        assert d1_out.state == "ok"
        assert d1_out.value == Decimal("1001")
        assert e1_out.state == "ok"
        assert e1_out.value == Decimal("1001")
