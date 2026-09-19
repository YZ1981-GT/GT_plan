"""Wave2 单测 + PBT — NoteFormulaEvaluator 编排层（Task 3.3）.

Spec:   .kiro/specs/disclosure-note-formula-and-report-sync/ Wave2 (Task 3.3)
Reqs:   1.1 / 1.4 / 1.5 / 3.2 / 8.2 / 8.3 / 8.4 / 9.1

覆盖正确性属性 / 特征化：
- Property 6（manual/locked 保留）：evaluate_table 后 manual/locked 单元格值不变
  —— 含 hypothesis PBT（随机 table + 随机 mode + 随机 binding）。
- 幂等：同 table_data + ctx 二次求值一致，且 f(f(x)) == f(x)。
- fail-open：resolver 抛异常 → 保留原值 + 记 issue，不冒泡到调用方。
- 无 binding 表 → 无操作（原样返回）。
- 开关关闭旁路 characterization：flag=False 时 evaluate_table 对公式家族单元格
  无操作（保留原值，零回归）；DISCLOSURE_NOTE_FORMULA_ENABLED 默认 False。
- 多表 _tables 支持；返回新对象不就地改；ctx 回调 binding 重建路径。
- generate_notes 集成旁路：_evaluate_note_formulas 委托 evaluate_table。
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from hypothesis import given, settings as hsettings
from hypothesis import strategies as st

from app.services.note_formula_evaluator import (
    FORMULA_FAMILY_SOURCES,
    NoteFormulaEvaluator,
)

_ENABLE = "app.services.note_source_resolvers._formula_enabled"


@pytest.fixture
def formula_on(monkeypatch):
    """开启灰度开关（自动恢复）。"""
    monkeypatch.setattr(_ENABLE, lambda: True)
    yield


def _sum_table():
    """一张含 sum 公式合计单元格的单表：合计=甲+乙。

    - R2C2(rows[1].values[1])=100.0（甲/期末）
    - R3C2(rows[2].values[1])=200.0（乙/期末）
    - 合计行 rows[3].values[1] auto + 内嵌 sum binding → 期望 300.0
    """
    return {
        "headers": ["项目", "期末"],
        "rows": [
            {"values": ["项目", "期末"]},
            {"values": ["甲", 100.0], "_cell_modes": {}, "_cell_meta": {}},
            {"values": ["乙", 200.0], "_cell_modes": {}, "_cell_meta": {}},
            {
                "values": ["合计", None],
                "is_total": True,
                "_cell_modes": {"1": "auto"},
                "_cell_meta": {
                    "1": {
                        "manual_value": None,
                        "semantic": "period_end",
                        "binding": {"source": "sum", "cells": ["R2C2", "R3C2"]},
                    }
                },
            },
        ],
    }


def _base_ctx():
    return {"project_id": uuid4(), "year": 2025, "db": None}


# ===========================================================================
# 基本求值（sum 内嵌 binding） + 返回新对象
# ===========================================================================


class TestBasicEvaluate:
    @pytest.mark.asyncio
    async def test_sum_cell_filled(self, formula_on):
        td = _sum_table()
        ev = NoteFormulaEvaluator()
        out = await ev.evaluate_table(td, _base_ctx())
        assert out["rows"][3]["values"][1] == pytest.approx(300.0)

    @pytest.mark.asyncio
    async def test_returns_new_object_not_in_place(self, formula_on):
        td = _sum_table()
        ev = NoteFormulaEvaluator()
        out = await ev.evaluate_table(td, _base_ctx())
        # 入参未被就地修改（合计仍是 None）
        assert td["rows"][3]["values"][1] is None
        assert out is not td

    @pytest.mark.asyncio
    async def test_non_dict_returns_as_is(self, formula_on):
        ev = NoteFormulaEvaluator()
        assert await ev.evaluate_table(None, _base_ctx()) is None  # type: ignore[arg-type]
        assert await ev.evaluate_table("junk", {}) == "junk"  # type: ignore[arg-type]


# ===========================================================================
# Property 6 — manual / locked 保留
# ===========================================================================


class TestManualLockedPreserved:
    @pytest.mark.asyncio
    async def test_manual_total_not_overwritten(self, formula_on):
        td = _sum_table()
        td["rows"][3]["_cell_modes"] = {"1": "manual"}
        td["rows"][3]["values"][1] = 999.0  # 用户手填
        ev = NoteFormulaEvaluator()
        out = await ev.evaluate_table(td, _base_ctx())
        assert out["rows"][3]["values"][1] == 999.0  # 未被 sum 覆盖

    @pytest.mark.asyncio
    async def test_locked_total_not_overwritten(self, formula_on):
        td = _sum_table()
        td["rows"][3]["_cell_modes"] = {"1": "locked"}
        td["rows"][3]["values"][1] = 888.0
        ev = NoteFormulaEvaluator()
        out = await ev.evaluate_table(td, _base_ctx())
        assert out["rows"][3]["values"][1] == 888.0

    @hsettings(max_examples=5)
    @given(
        modes=st.lists(
            st.sampled_from(["auto", "manual", "locked", None]),
            min_size=1,
            max_size=5,
        ),
        vals=st.lists(
            st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
            min_size=1,
            max_size=5,
        ),
    )
    def test_manual_locked_preserved_pbt(self, modes, vals):
        """随机 table + 随机 mode + 每格内嵌 sum binding：manual/locked 值不变。"""
        n = min(len(modes), len(vals))
        modes, vals = modes[:n], vals[:n]
        cell_modes = {str(i): m for i, m in enumerate(modes) if m is not None}
        cell_meta = {
            str(i): {
                "binding": {"source": "sum", "cells": ["R1C1"]},
            }
            for i in range(n)
        }
        td = {
            "headers": ["c"] * n,
            "rows": [
                {"values": list(vals), "_cell_modes": cell_modes, "_cell_meta": cell_meta}
            ],
        }
        ev = NoteFormulaEvaluator()
        with_patch = "app.services.note_source_resolvers._formula_enabled"
        from unittest.mock import patch

        with patch(with_patch, return_value=True):
            out = asyncio.run(ev.evaluate_table(td, _base_ctx()))

        for i in range(n):
            if cell_modes.get(str(i)) in ("manual", "locked"):
                assert out["rows"][0]["values"][i] == vals[i], (
                    f"col {i} mode={cell_modes.get(str(i))} 被改动"
                )


# ===========================================================================
# 幂等
# ===========================================================================


class TestIdempotent:
    @pytest.mark.asyncio
    async def test_same_input_twice(self, formula_on):
        td = _sum_table()
        ev = NoteFormulaEvaluator()
        a = await ev.evaluate_table(td, _base_ctx())
        b = await ev.evaluate_table(td, _base_ctx())
        assert a == b

    @pytest.mark.asyncio
    async def test_fixpoint(self, formula_on):
        td = _sum_table()
        ev = NoteFormulaEvaluator()
        once = await ev.evaluate_table(td, _base_ctx())
        twice = await ev.evaluate_table(once, _base_ctx())
        assert once == twice


# ===========================================================================
# fail-open — resolver 抛异常不冒泡
# ===========================================================================


class TestFailOpen:
    @pytest.mark.asyncio
    async def test_resolver_raises_keeps_original(self, formula_on, monkeypatch):
        async def _boom(binding, ctx):
            raise RuntimeError("resolver blew up")

        # 让 sum 求值抛异常 → evaluate_table 应保留原值 + 记 issue
        monkeypatch.setattr(
            "app.services.note_source_resolvers.resolve_formula", _boom
        )
        td = _sum_table()
        td["rows"][3]["values"][1] = 42.0  # 原值
        ev = NoteFormulaEvaluator()
        out = await ev.evaluate_table(td, _base_ctx())  # 不抛出
        assert out["rows"][3]["values"][1] == 42.0  # 保留原值
        assert len(ev.issues) >= 1
        assert ev.issues[0]["error"]

    @hsettings(max_examples=5)
    @given(
        modes=st.lists(st.sampled_from(["auto", "manual", "locked"]), max_size=4),
    )
    def test_never_raises_pbt(self, modes):
        """任意 mode 组合 + 随机 binding，evaluate_table 绝不抛出。"""
        from unittest.mock import patch

        n = max(1, len(modes))
        cell_meta = {
            str(i): {"binding": {"source": "sum", "cells": ["R1C1", "R2C2"]}}
            for i in range(n)
        }
        cell_modes = {str(i): m for i, m in enumerate(modes)}
        td = {
            "headers": ["c"] * n,
            "rows": [
                {"values": [1.0] * n, "_cell_modes": cell_modes, "_cell_meta": cell_meta},
                {"values": [2.0] * n},
            ],
        }
        ev = NoteFormulaEvaluator()
        with patch("app.services.note_source_resolvers._formula_enabled", return_value=True):
            out = asyncio.run(ev.evaluate_table(td, _base_ctx()))
        assert isinstance(out, dict)


# ===========================================================================
# 无 binding 表 → 无操作
# ===========================================================================


class TestNoBindingNoOp:
    @pytest.mark.asyncio
    async def test_no_binding_table_unchanged(self, formula_on):
        td = {
            "headers": ["项目", "金额"],
            "rows": [
                {"values": ["甲", 100.0], "_cell_modes": {"1": "auto"}, "_cell_meta": {}},
                {"values": ["乙", 200.0]},
            ],
        }
        ev = NoteFormulaEvaluator()
        out = await ev.evaluate_table(td, _base_ctx())
        assert out["rows"][0]["values"][1] == 100.0
        assert out["rows"][1]["values"][1] == 200.0
        assert ev.issues == []

    @pytest.mark.asyncio
    async def test_data_source_cell_not_reresolved(self, formula_on):
        # 数据源 source（trial_balance）不在 formula-family → 跳过不重复求值
        td = {
            "headers": ["项目", "金额"],
            "rows": [
                {
                    "values": ["现金", 500.0],
                    "_cell_modes": {"1": "auto"},
                    "_cell_meta": {
                        "1": {
                            "binding": {
                                "source": "trial_balance",
                                "account_codes": ["1001"],
                            }
                        }
                    },
                }
            ],
        }
        ev = NoteFormulaEvaluator()
        out = await ev.evaluate_table(td, _base_ctx())
        assert out["rows"][0]["values"][1] == 500.0  # 未动


# ===========================================================================
# 开关关闭旁路 characterization（零回归）
# ===========================================================================


class TestFlagOffBypass:
    def test_flag_default_false(self):
        from app.core.config import settings

        assert settings.DISCLOSURE_NOTE_FORMULA_ENABLED is False

    @pytest.mark.asyncio
    async def test_formula_cell_untouched_when_flag_off(self):
        # 不开开关：resolve_formula 内部返 None → evaluate_table 保留原值（零回归）
        td = _sum_table()
        ev = NoteFormulaEvaluator()
        out = await ev.evaluate_table(td, _base_ctx())
        assert out["rows"][3]["values"][1] is None  # 合计仍空，未被求值
        # 分项保持不变
        assert out["rows"][1]["values"][1] == 100.0
        assert out["rows"][2]["values"][1] == 200.0


# ===========================================================================
# 多表 _tables 支持
# ===========================================================================


class TestMultiTable:
    @pytest.mark.asyncio
    async def test_tables_each_evaluated_and_mirrored(self, formula_on):
        t0 = _sum_table()
        t1 = {
            "headers": ["项目", "期末"],
            "rows": [
                {"values": ["丙", 10.0]},
                {"values": ["丁", 20.0]},
                {
                    "values": ["合计", None],
                    "is_total": True,
                    "_cell_modes": {"1": "auto"},
                    "_cell_meta": {
                        "1": {"binding": {"source": "sum", "cells": ["R1C2", "R2C2"]}}
                    },
                },
            ],
        }
        td = {
            "headers": t0["headers"],
            "rows": t0["rows"],
            "_tables": [t0, t1],
        }
        ev = NoteFormulaEvaluator()
        out = await ev.evaluate_table(td, _base_ctx())
        # 表0 合计 = 100+200 = 300
        assert out["_tables"][0]["rows"][3]["values"][1] == pytest.approx(300.0)
        # 表1 合计 = 10+20 = 30
        assert out["_tables"][1]["rows"][2]["values"][1] == pytest.approx(30.0)
        # 顶层镜像首表
        assert out["rows"][3]["values"][1] == pytest.approx(300.0)


# ===========================================================================
# ctx 回调 binding 重建路径（集成路径）
# ===========================================================================


class TestCtxResolverCallback:
    @pytest.mark.asyncio
    async def test_binding_from_ctx_callback(self, formula_on):
        # 单元格无内嵌 binding，但 _cell_meta 有 semantic；经 ctx 回调重建 binding
        td = {
            "headers": ["项目", "期末"],
            "rows": [
                {"label": "甲", "values": ["甲", 100.0]},
                {"label": "乙", "values": ["乙", 200.0]},
                {
                    "label": "合计",
                    "values": ["合计", None],
                    "is_total": True,
                    "_cell_modes": {"1": "auto"},
                    "_cell_meta": {"1": {"semantic": "period_end"}},
                },
            ],
        }

        def _resolver(table_index, label, col_idx, cell_meta):
            if label == "合计" and col_idx == 1:
                return {"source": "sum", "cells": ["R1C2", "R2C2"]}
            return None

        ctx = _base_ctx()
        ctx["_cell_binding_resolver"] = _resolver
        ev = NoteFormulaEvaluator()
        out = await ev.evaluate_table(td, ctx)
        assert out["rows"][2]["values"][1] == pytest.approx(300.0)

    @pytest.mark.asyncio
    async def test_callback_exception_treated_as_no_binding(self, formula_on):
        def _resolver(table_index, label, col_idx, cell_meta):
            raise ValueError("bad")

        td = {
            "headers": ["a", "b"],
            "rows": [{"values": ["x", 5.0], "_cell_modes": {"1": "auto"}}],
        }
        ctx = _base_ctx()
        ctx["_cell_binding_resolver"] = _resolver
        ev = NoteFormulaEvaluator()
        out = await ev.evaluate_table(td, ctx)  # 不抛出
        assert out["rows"][0]["values"][1] == 5.0  # 无 binding → 保留


# ===========================================================================
# generate_notes 集成 — _evaluate_note_formulas 委托 evaluate_table
# ===========================================================================


class TestEngineHelperWiring:
    @pytest.mark.asyncio
    async def test_evaluate_note_formulas_delegates(self, formula_on, monkeypatch):
        from app.services.disclosure_engine import DisclosureEngine

        # 隔离 binding 加载（本用例走内嵌 binding，无需真实 section binding）
        monkeypatch.setattr(
            "app.services.note_template_bindings_loader.get_binding_for_section",
            lambda section: {"tables": []},
        )
        engine = DisclosureEngine(None)  # type: ignore[arg-type]
        td = _sum_table()
        out = await engine._evaluate_note_formulas(uuid4(), 2025, "五、1", td)
        assert out["rows"][3]["values"][1] == pytest.approx(300.0)


# ===========================================================================
# 常量守卫
# ===========================================================================


class TestConstants:
    def test_formula_family_sources(self):
        # spec disclosure-note-formula-data-population 决策 3 追加 'formula'
        # （binding 写 source='formula' + formula_kind 子类型，不新增 source 枚举）。
        assert FORMULA_FAMILY_SOURCES == frozenset(
            {"sum", "report", "aging", "prior_year_note", "formula"}
        )
