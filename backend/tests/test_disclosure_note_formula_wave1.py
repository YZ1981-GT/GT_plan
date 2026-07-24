"""Wave1 单测 + PBT — 附注表内公式求值内核（resolve_formula + prior value）.

Spec:   .kiro/specs/disclosure-note-formula-and-report-sync/ Wave1 (Task 2.4)
Reqs:   1.1 / 1.2 / 1.3 / 1.4 / 1.5 / 2.1 / 2.2 / 2.3 / 2.4 / 8.3 / 8.4 / 9.1

覆盖正确性属性：
- Property 1（幂等）：同 ctx 二次求值一致。
- Property 2（fail-open）：任意 binding/ctx 返 None 或数值，绝不抛出。
- Property 3（REPORT 一致）：== ctx.report_data[row_code]；缺失 → None。
- Property 4（SUM 复用内核）：结果 == 既有 evaluate_formula 对同坐标区间求和。
- Property 5（上年 value/text）：value 反查上年坐标值；无表/坐标 → None；text 不回归。
- Property 12（开关关闭零回归）：flag=False 时 resolve_formula 返 None、value 模式返 None。
"""

from __future__ import annotations

import asyncio
import warnings
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from hypothesis import given, settings as hsettings
from hypothesis import strategies as st

from app.services.note_source_resolvers import (
    resolve_formula,
    resolve_prior_year_note,
)

_ENABLE = "app.services.note_source_resolvers._formula_enabled"


@pytest.fixture
def formula_on(monkeypatch):
    """开启灰度开关（自动恢复）。"""
    monkeypatch.setattr(_ENABLE, lambda: True)
    yield


def _sum_ctx(cell_values: dict) -> dict:
    return {
        "cell_values": dict(cell_values),
        "project_id": uuid4(),
        "year": 2025,
        "db": None,
    }


# ===========================================================================
# Property 4 — SUM 复用既有 evaluate_formula 内核（不另算）
# ===========================================================================


class TestSumReuseKernel:
    @pytest.mark.asyncio
    async def test_sum_equals_evaluate_formula(self, formula_on):
        from app.services.formula_parse_utils import evaluate_formula

        cells = ["R2C2", "R3C2"]
        cv = {"R2C2": 100.0, "R3C2": 50.5}
        pid = uuid4()
        ctx = {"cell_values": cv, "project_id": pid, "year": 2025, "db": None}

        got = await resolve_formula({"source": "sum", "cells": cells}, ctx)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            exp = await evaluate_formula(
                "ROW('R2C2') + ROW('R3C2')",
                None,
                pid,
                2025,
                row_values={"R2C2": Decimal("100.0"), "R3C2": Decimal("50.5")},
            )
        assert got == exp["value"] == pytest.approx(150.5)

    @pytest.mark.asyncio
    async def test_sum_from_table_data_fallback(self, formula_on):
        table = {
            "rows": [
                {"values": ["表头1", "表头2"]},
                {"values": ["甲", 100.0]},
                {"values": ["乙", 200.0]},
            ]
        }
        ctx = {"table_data": table, "project_id": uuid4(), "year": 2025, "db": None}
        got = await resolve_formula({"source": "sum", "cells": ["R2C2", "R3C2"]}, ctx)
        assert got == pytest.approx(300.0)

    @pytest.mark.asyncio
    async def test_sum_missing_cells_returns_none(self, formula_on):
        ctx = _sum_ctx({})
        assert await resolve_formula({"source": "sum", "cells": ["R1C1"]}, ctx) is None
        assert await resolve_formula({"source": "sum", "cells": []}, ctx) is None
        assert await resolve_formula({"source": "sum"}, ctx) is None


# ===========================================================================
# Property 1 — 幂等
# ===========================================================================


class TestIdempotent:
    @pytest.mark.asyncio
    async def test_sum_idempotent(self, formula_on):
        binding = {"source": "sum", "cells": ["R1C1", "R1C2"]}
        ctx = _sum_ctx({"R1C1": 10, "R1C2": 20})
        a = await resolve_formula(binding, ctx)
        b = await resolve_formula(binding, ctx)
        assert a == b == pytest.approx(30.0)

    @pytest.mark.asyncio
    async def test_report_idempotent(self, formula_on):
        binding = {"source": "report", "row_code": "BS-015"}
        ctx = {"report_data": {"BS-015": Decimal("777")}}
        a = await resolve_formula(binding, ctx)
        b = await resolve_formula(binding, ctx)
        assert a == b == 777.0


# ===========================================================================
# Property 3 — REPORT source 取值一致
# ===========================================================================


class TestReportSource:
    @pytest.mark.asyncio
    async def test_report_hit_and_miss(self, formula_on):
        ctx = {"report_data": {"BS-015": Decimal("500")}}
        assert await resolve_formula({"source": "report", "row_code": "BS-015"}, ctx) == 500.0
        assert await resolve_formula({"source": "report", "row_code": "NOPE"}, ctx) is None
        assert await resolve_formula({"source": "report", "row_code": "X"}, {}) is None
        assert await resolve_formula({"source": "report"}, ctx) is None

    @hsettings(max_examples=5)
    @given(
        code=st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789", min_size=1, max_size=8
        ),
        amount=st.decimals(
            allow_nan=False, allow_infinity=False, places=2,
            min_value=Decimal("-1000000"), max_value=Decimal("1000000"),
        ),
    )
    def test_report_source_pbt(self, code, amount):
        with patch(_ENABLE, return_value=True):
            got = asyncio.run(
                resolve_formula(
                    {"source": "report", "row_code": code},
                    {"report_data": {code: amount}},
                )
            )
            missing = asyncio.run(
                resolve_formula(
                    {"source": "report", "row_code": code + "_x"},
                    {"report_data": {code: amount}},
                )
            )
        assert got == float(amount)
        assert missing is None


# ===========================================================================
# Property 2 — fail-open：绝不抛出，返 None 或数值
# ===========================================================================


class TestFailOpen:
    @hsettings(max_examples=10)
    @given(
        binding=st.dictionaries(
            st.sampled_from(
                ["source", "cells", "row_code", "band", "cell", "table_index", "row", "col"]
            ),
            st.one_of(
                st.none(),
                st.integers(min_value=-3, max_value=6),
                st.text(max_size=6),
                st.lists(st.text(max_size=4), max_size=4),
            ),
            max_size=6,
        ),
    )
    def test_resolve_formula_never_raises(self, binding):
        ctx = {
            "report_data": {"BS-015": Decimal("1")},
            "aging_data": {"1-2年": 5.0},
            "cell_values": {"R1C1": 3.0},
            "project_id": uuid4(),
            "year": 2025,
            "db": None,
        }
        with patch(_ENABLE, return_value=True):
            res = asyncio.run(resolve_formula(binding, ctx))
        assert res is None or isinstance(res, (int, float))

    @pytest.mark.asyncio
    async def test_non_dict_binding(self, formula_on):
        assert await resolve_formula(None, {}) is None  # type: ignore[arg-type]
        assert await resolve_formula("junk", {}) is None  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_unknown_source_returns_none(self, formula_on):
        assert await resolve_formula({"source": "weird"}, {}) is None


# ===========================================================================
# Property (aging)
# ===========================================================================


class TestAgingSource:
    @pytest.mark.asyncio
    async def test_aging_hit_and_miss(self, formula_on):
        ctx = {"aging_data": {"1-2年": 250.0}}
        assert await resolve_formula({"source": "aging", "band": "1-2年"}, ctx) == 250.0
        assert await resolve_formula({"source": "aging", "band": "缺失段"}, ctx) is None
        assert await resolve_formula({"source": "aging", "band": "x"}, {}) is None
        assert await resolve_formula({"source": "aging"}, ctx) is None


# ===========================================================================
# Property 5 — 上年 value 反查 / text 不回归
# ===========================================================================


class TestPriorYearValue:
    @pytest.mark.asyncio
    async def test_value_reverse_lookup_single_table(self, formula_on):
        table = {
            "rows": [
                {"values": ["项目", "期末", "期初"]},
                {"values": ["货币资金", 1000.0, 900.0]},
            ]
        }
        ctx = {
            "_prior_notes_cache": {
                "五、1": {"text": "上年文本足够长足够长足够长足够长足够长", "table": table}
            }
        }
        # R2C2 → row idx1, col idx1 → 1000.0
        assert (
            await resolve_prior_year_note(
                {"section": "五、1", "field": "value", "cell": "R2C2"}, ctx
            )
            == 1000.0
        )
        # R2C3 → 900.0
        assert (
            await resolve_prior_year_note(
                {"section": "五、1", "field": "value", "cell": "R2C3"}, ctx
            )
            == 900.0
        )
        # 坐标越界 → None
        assert (
            await resolve_prior_year_note(
                {"section": "五、1", "field": "value", "cell": "R9C9"}, ctx
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_value_multi_table_index(self, formula_on):
        t0 = {"rows": [{"values": ["a", 1.0]}]}
        t1 = {"rows": [{"values": ["b", 2.0]}]}
        ctx = {
            "_prior_notes_cache": {
                "五、2": {"text": None, "table": {"_tables": [t0, t1]}}
            }
        }
        assert (
            await resolve_prior_year_note(
                {"section": "五、2", "field": "value", "cell": "R1C2", "table_index": 1},
                ctx,
            )
            == 2.0
        )
        # 默认 table_index=0
        assert (
            await resolve_prior_year_note(
                {"section": "五、2", "field": "value", "cell": "R1C2"}, ctx
            )
            == 1.0
        )

    @pytest.mark.asyncio
    async def test_value_no_table_returns_none(self, formula_on):
        ctx = {"_prior_notes_cache": {"五、1": {"text": "t", "table": None}}}
        assert (
            await resolve_prior_year_note(
                {"section": "五、1", "field": "value", "cell": "R1C1"}, ctx
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_value_flat_string_cache_returns_none(self, formula_on):
        # 旧扁平字符串缓存无单元格数据 → value 模式 None
        ctx = {"_prior_notes_cache": {"五、1": "上年扁平文本"}}
        assert (
            await resolve_prior_year_note(
                {"section": "五、1", "field": "value", "cell": "R1C1"}, ctx
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_text_mode_dict_cache(self, formula_on):
        ctx = {"_prior_notes_cache": {"五、1": {"text": "上年文本内容", "table": {}}}}
        assert (
            await resolve_prior_year_note({"section": "五、1", "field": "text"}, ctx)
            == "上年文本内容"
        )

    @pytest.mark.asyncio
    async def test_text_mode_flat_string_compat(self):
        # text 模式不受开关约束、兼容旧扁平字符串（不回归）
        ctx = {"_prior_notes_cache": {"五、1": "上年扁平文本"}}
        assert (
            await resolve_prior_year_note({"section": "五、1", "field": "text"}, ctx)
            == "上年扁平文本"
        )

    @pytest.mark.asyncio
    async def test_row_col_int_coords(self, formula_on):
        table = {"rows": [{"values": [10.0, 20.0]}, {"values": [30.0, 40.0]}]}
        ctx = {"_prior_notes_cache": {"五、3": {"text": None, "table": table}}}
        assert (
            await resolve_prior_year_note(
                {"section": "五、3", "field": "value", "row": 1, "col": 0}, ctx
            )
            == 30.0
        )


# ===========================================================================
# Property 12 — 开关关闭零回归
# ===========================================================================


class TestFlagOffZeroRegression:
    @pytest.mark.asyncio
    async def test_resolve_formula_none_when_disabled(self):
        # 默认 DISCLOSURE_NOTE_FORMULA_ENABLED=False
        assert (
            await resolve_formula({"source": "sum", "cells": ["R1C1"]},
                                  {"cell_values": {"R1C1": 5.0}})
            is None
        )
        assert (
            await resolve_formula({"source": "report", "row_code": "X"},
                                  {"report_data": {"X": Decimal("1")}})
            is None
        )
        assert (
            await resolve_formula({"source": "aging", "band": "1-2年"},
                                  {"aging_data": {"1-2年": 5.0}})
            is None
        )

    @pytest.mark.asyncio
    async def test_prior_value_none_when_disabled(self):
        table = {"rows": [{"values": [1.0]}]}
        ctx = {"_prior_notes_cache": {"S": {"text": None, "table": table}}}
        # value 模式关闭 → None（即使有 table）
        assert (
            await resolve_prior_year_note(
                {"section": "S", "field": "value", "cell": "R1C1"}, ctx
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_prior_text_not_gated_by_flag(self):
        # text 模式不受开关约束
        ctx = {"_prior_notes_cache": {"S": {"text": "上年文本", "table": None}}}
        assert (
            await resolve_prior_year_note({"section": "S", "field": "text"}, ctx)
            == "上年文本"
        )
