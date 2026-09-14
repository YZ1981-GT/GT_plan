"""带符号 sum + formula_kind 子类型分派（Wave 2 / Task 3.1 + 3.1b + 3.2）.

Spec:   .kiro/specs/disclosure-note-formula-data-population/
Design: 决策 3（source='formula' + formula_kind）/ 决策 6（不动 VALID_SOURCES）
Props:  Property 8（向后兼容 + 带符号）/ Property 9（fail-open）/ Property 10（灰度）
"""

from __future__ import annotations

import pytest

from app.services.note_formula_evaluator import (
    FORMULA_FAMILY_SOURCES,
    NoteFormulaEvaluator,
    _RESOLVE_FORMULA_DIRECT,
)
from app.services.note_source_resolvers import (
    SOURCE_RESOLVERS,
    VALID_SOURCES,
    _resolve_formula_sum,
    resolve_formula,
)


@pytest.fixture()
def flag_on(monkeypatch):
    from app.core import config

    monkeypatch.setattr(
        config.settings, "DISCLOSURE_NOTE_FORMULA_ENABLED", True, raising=False
    )


@pytest.fixture()
def flag_off(monkeypatch):
    from app.core import config

    monkeypatch.setattr(
        config.settings, "DISCLOSURE_NOTE_FORMULA_ENABLED", False, raising=False
    )


def _ctx(**cells: float) -> dict:
    return {
        "cell_values": dict(cells),
        "db": None,
        "project_id": None,
        "year": 2025,
    }


# ---------------------------------------------------------------------------
# Property 8 —— 纯字符串写法向后兼容 + 带符号项
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pure_string_cells_unchanged(flag_on):
    ctx = _ctx(R2C1=100.0, R2C2=30.0, R2C3=10.0)
    assert await _resolve_formula_sum(
        {"cells": ["R2C1", "R2C2", "R2C3"]}, ctx
    ) == pytest.approx(140.0)


@pytest.mark.asyncio
async def test_signed_cells_subtract(flag_on):
    """期末 = 期初 + 增 − 减。"""
    ctx = _ctx(R2C1=100.0, R2C2=30.0, R2C3=10.0)
    binding = {
        "cells": [
            {"cell": "R2C1", "sign": "+"},
            {"cell": "R2C2", "sign": "+"},
            {"cell": "R2C3", "sign": "-"},
        ]
    }
    assert await _resolve_formula_sum(binding, ctx) == pytest.approx(120.0)


@pytest.mark.asyncio
async def test_signed_and_string_mixed(flag_on):
    ctx = _ctx(R2C1=50.0, R2C2=5.0)
    binding = {"cells": ["R2C1", {"cell": "R2C2", "sign": "-"}]}
    assert await _resolve_formula_sum(binding, ctx) == pytest.approx(45.0)


@pytest.mark.asyncio
async def test_leading_negative_term(flag_on):
    """首项为减号时表达式仍合法（-ROW(...)）。"""
    ctx = _ctx(R2C1=10.0, R2C2=3.0)
    binding = {
        "cells": [{"cell": "R2C1", "sign": "-"}, {"cell": "R2C2", "sign": "+"}]
    }
    assert await _resolve_formula_sum(binding, ctx) == pytest.approx(-7.0)


@pytest.mark.asyncio
async def test_signed_item_missing_cell_or_bad_sign_skipped(flag_on):
    ctx = _ctx(R2C1=8.0, R2C2=2.0)
    binding = {
        "cells": [
            {"cell": "R2C1", "sign": "+"},
            {"cell": "R2C2", "sign": "*"},  # 非法符号 → 跳过
            {"sign": "-"},  # 缺 cell → 跳过
            42,  # 非法项类型 → 跳过
        ]
    }
    assert await _resolve_formula_sum(binding, ctx) == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# Property 9 —— fail-open
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_signed_cell_value_is_skipped(flag_on):
    ctx = _ctx(R2C1=7.0)
    binding = {
        "cells": [
            {"cell": "R2C1", "sign": "+"},
            {"cell": "R9C9", "sign": "-"},
        ]
    }
    assert await _resolve_formula_sum(binding, ctx) == pytest.approx(7.0)


@pytest.mark.asyncio
async def test_all_signed_cells_missing_returns_none(flag_on):
    ctx = _ctx()
    binding = {"cells": [{"cell": "R2C1", "sign": "+"}]}
    assert await _resolve_formula_sum(binding, ctx) is None


# ---------------------------------------------------------------------------
# Task 3.1b —— formula_kind 子类型分派
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_formula_with_kind_sum(flag_on):
    ctx = _ctx(R2C1=100.0, R2C2=20.0, R2C3=5.0)
    binding = {
        "source": "formula",
        "formula_kind": "sum",
        "cells": [
            {"cell": "R2C1", "sign": "+"},
            {"cell": "R2C2", "sign": "+"},
            {"cell": "R2C3", "sign": "-"},
        ],
    }
    assert await resolve_formula(binding, ctx) == pytest.approx(115.0)


@pytest.mark.asyncio
async def test_source_formula_with_kind_report(flag_on):
    ctx = {"report_data": {"BS-002": 123.0}}
    binding = {"source": "formula", "formula_kind": "report", "row_code": "BS-002"}
    assert await resolve_formula(binding, ctx) == pytest.approx(123.0)


@pytest.mark.asyncio
async def test_source_formula_without_kind_stays_none(flag_on):
    """无 formula_kind 的历史 'formula' binding 行为不变（返 None）。"""
    ctx = _ctx(R2C1=1.0)
    assert await resolve_formula({"source": "formula", "cells": ["R2C1"]}, ctx) is None


@pytest.mark.asyncio
async def test_legacy_source_sum_still_works(flag_on):
    """旧写法 source='sum' 逐字节保留。"""
    ctx = _ctx(R2C1=1.0, R2C2=2.0)
    assert await resolve_formula(
        {"source": "sum", "cells": ["R2C1", "R2C2"]}, ctx
    ) == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_kind_alias_field_supported(flag_on):
    ctx = _ctx(R2C1=4.0)
    assert await resolve_formula(
        {"source": "formula", "kind": "sum", "cells": ["R2C1"]}, ctx
    ) == pytest.approx(4.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["sum", "report", "aging"])
async def test_flag_off_returns_none_for_formula_kind(flag_off, kind):
    ctx = {
        "cell_values": {"R2C1": 1.0},
        "report_data": {"BS-002": 2.0},
        "aging_data": {"1年以内": 3.0},
        "db": None,
        "project_id": None,
        "year": 2025,
    }
    binding = {
        "source": "formula",
        "formula_kind": kind,
        "cells": ["R2C1"],
        "row_code": "BS-002",
        "band": "1年以内",
    }
    assert await resolve_formula(binding, ctx) is None


# ---------------------------------------------------------------------------
# 决策 6 —— 不动 VALID_SOURCES / SOURCE_RESOLVERS 契约
# ---------------------------------------------------------------------------


def test_no_new_source_enum_added():
    assert "sum" not in VALID_SOURCES
    assert "formula" in VALID_SOURCES
    assert set(SOURCE_RESOLVERS.keys()) == set(VALID_SOURCES)


def test_evaluator_formula_family_includes_formula():
    assert "formula" in FORMULA_FAMILY_SOURCES
    assert "formula" in _RESOLVE_FORMULA_DIRECT


# ---------------------------------------------------------------------------
# 第二遍求值：source='formula' 经 evaluator 命中 sum
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluator_resolves_formula_kind_sum(flag_on):
    """期末列由同行期初/增/减派生（内嵌 _cell_meta.binding 路径）。"""
    table_data = {
        "headers": ["项目", "期初", "增", "减", "期末"],
        "rows": [
            {
                "label": "甲",
                "values": [100.0, 30.0, 10.0, None],
                "_cell_modes": {"0": "auto", "1": "auto", "2": "auto", "3": "auto"},
                "_cell_meta": {
                    "3": {
                        "binding": {
                            "source": "formula",
                            "formula_kind": "sum",
                            "cells": [
                                {"cell": "R1C1", "sign": "+"},
                                {"cell": "R1C2", "sign": "+"},
                                {"cell": "R1C3", "sign": "-"},
                            ],
                        }
                    }
                },
            }
        ],
    }
    out = await NoteFormulaEvaluator().evaluate_table(
        table_data, {"db": None, "project_id": None, "year": 2025}
    )
    assert out["rows"][0]["values"][3] == pytest.approx(120.0)
    # 不就地改入参
    assert table_data["rows"][0]["values"][3] is None


@pytest.mark.asyncio
async def test_evaluator_keeps_manual_cell(flag_on):
    table_data = {
        "rows": [
            {
                "label": "甲",
                "values": [1.0, 2.0, 0.0, 999.0],
                "_cell_modes": {"3": "manual"},
                "_cell_meta": {
                    "3": {
                        "binding": {
                            "source": "formula",
                            "formula_kind": "sum",
                            "cells": ["R1C1", "R1C2"],
                        }
                    }
                },
            }
        ]
    }
    out = await NoteFormulaEvaluator().evaluate_table(table_data, {})
    assert out["rows"][0]["values"][3] == pytest.approx(999.0)


@pytest.mark.asyncio
async def test_evaluator_flag_off_keeps_original(flag_off):
    table_data = {
        "rows": [
            {
                "label": "甲",
                "values": [1.0, 2.0, 0.0, None],
                "_cell_modes": {"3": "auto"},
                "_cell_meta": {
                    "3": {
                        "binding": {
                            "source": "formula",
                            "formula_kind": "sum",
                            "cells": ["R1C1", "R1C2"],
                        }
                    }
                },
            }
        ]
    }
    out = await NoteFormulaEvaluator().evaluate_table(table_data, {})
    assert out["rows"][0]["values"][3] is None
