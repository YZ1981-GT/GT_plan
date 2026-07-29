"""F2 presets.py 单元测试 (mock DB 不真连 PG)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.f2_extraction.anchor_registry import F2_ANCHORS
from app.services.f2_extraction.presets import (
    SOURCE_CUSTOM,
    SOURCE_DISABLED,
    SOURCE_PRESET,
    f2_tier_a_semantic,
    load_f2_presets,
    resolve_effective,
)


# ─── load_f2_presets ───────────────────────────────────────────────────────────


def test_load_f2_presets_returns_39():
    """加载 JSON 预设应返回 39 条绑定."""
    presets = load_f2_presets()
    assert len(presets) == 39


def test_load_f2_presets_all_anchors_valid():
    """每条预设 anchor 必须属于 F2_ANCHORS."""
    presets = load_f2_presets()
    for p in presets:
        assert p["anchor"] in F2_ANCHORS, f"未知锚点: {p['anchor']}"


# ─── resolve_effective ─────────────────────────────────────────────────────────


def _make_mock_db(user_formulas: list | None = None):
    """构造 AsyncMock DB session."""
    db = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = user_formulas or []
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    db.execute = AsyncMock(return_value=result_mock)
    return db


def _make_wp_formula(
    *,
    target_cell: str,
    expression: str = "TB('1401','期初余额')",
    category: str | None = None,
    formula_type: str = "auto_calc",
    description: str = "",
    sheet_name: str = "F2-1",
):
    """构造 WpFormula mock 对象."""
    f = MagicMock()
    f.target_cell = target_cell
    f.expression = expression
    f.category = category
    f.formula_type = formula_type
    f.description = description
    f.sheet_name = sheet_name
    return f


@pytest.mark.asyncio
async def test_resolve_effective_preset_only():
    """无用户 wp_formula 时全部 source=preset."""
    db = _make_mock_db(user_formulas=[])
    wp_id = uuid.uuid4()
    project_id = uuid.uuid4()

    result = await resolve_effective(db, wp_id, project_id)

    assert len(result) == 39
    assert all(b["source"] == SOURCE_PRESET for b in result)


@pytest.mark.asyncio
async def test_resolve_effective_custom_overrides_preset():
    """用户 wp_formula 同 anchor → source=custom 覆盖预设."""
    anchor = "F2-1-gross-raw-materials-opening"
    custom_expr = "TB('1401','年初余额')"
    formula = _make_wp_formula(target_cell=anchor, expression=custom_expr)
    db = _make_mock_db(user_formulas=[formula])

    result = await resolve_effective(db, uuid.uuid4(), uuid.uuid4())

    matched = [b for b in result if b["anchor"] == anchor]
    assert len(matched) == 1
    assert matched[0]["source"] == SOURCE_CUSTOM
    assert matched[0]["expression"] == custom_expr


@pytest.mark.asyncio
async def test_resolve_effective_disabled_hides():
    """用户 category=__disabled__ → source=disabled."""
    anchor = "F2-1-gross-raw-materials-opening"
    formula = _make_wp_formula(
        target_cell=anchor,
        expression="",
        category="__disabled__",
    )
    db = _make_mock_db(user_formulas=[formula])

    result = await resolve_effective(db, uuid.uuid4(), uuid.uuid4())

    matched = [b for b in result if b["anchor"] == anchor]
    assert len(matched) == 1
    assert matched[0]["source"] == SOURCE_DISABLED


@pytest.mark.asyncio
async def test_resolve_effective_unknown_anchor_discarded():
    """用户 wp_formula anchor 不在 F2_ANCHORS → 丢弃."""
    formula = _make_wp_formula(
        target_cell="F2-1-FAKE-unknown-opening",
        expression="TB('9999','期初余额')",
    )
    db = _make_mock_db(user_formulas=[formula])

    result = await resolve_effective(db, uuid.uuid4(), uuid.uuid4())

    anchors = [b["anchor"] for b in result]
    assert "F2-1-FAKE-unknown-opening" not in anchors
    # 仍有 39 条预设
    assert len(result) == 39


@pytest.mark.asyncio
async def test_resolve_effective_restore_default():
    """无用户覆盖 → 回落预设（Property 13 恢复默认）."""
    db = _make_mock_db(user_formulas=[])

    result = await resolve_effective(db, uuid.uuid4(), uuid.uuid4())

    # 所有锚点都有 source=preset
    for b in result:
        assert b["source"] == SOURCE_PRESET
    # 数量等于预设数
    assert len(result) == 39


# ─── f2_tier_a_semantic ────────────────────────────────────────────────────────


def test_f2_tier_a_semantic():
    """返回含 'tb_balance' 的字符串."""
    result = f2_tier_a_semantic("TB('1401','期初余额')")
    assert "tb_balance" in result
    assert len(result) > 0


def test_f2_tier_a_semantic_empty():
    """空表达式返回空字符串."""
    assert f2_tier_a_semantic("") == ""
    assert f2_tier_a_semantic(None) == ""
