"""F2 审定表预填灰度测试.

Property 14: 灰度关时输出与 characterization 基线逐字段等价（只含 opening/closing）
Property 1: 灰度开时只汇总叶子防双算
Property 3: 灰度开 + 1471 负值 → abs
"""
from __future__ import annotations

import types
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.wp_render_strategies._f2_inventory_main import (
    _build_adjudication_prefill,
)


def _make_ctx(rows):
    """构造最小 RenderContext mock."""
    ctx = types.SimpleNamespace()
    ctx.project_id = "test-project-id"
    ctx.year = 2025
    ctx.wp_id = "test-wp-id"

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = rows
    db.execute = AsyncMock(return_value=result_mock)
    ctx.db = db
    return ctx


def _make_row(account_code, opening, closing, level=None):
    """构造 tb_balance 行 mock."""
    row = types.SimpleNamespace()
    row.account_code = account_code
    row.opening_balance = opening
    row.closing_balance = closing
    row.level = level
    return row


@pytest.fixture
def mock_active_filter():
    """Mock get_active_filter 返回简单条件."""
    with patch(
        "app.routers.wp_render_strategies._f2_inventory_main.get_active_filter",
        new_callable=AsyncMock,
        return_value=MagicMock(),
    ) as m:
        yield m


# ---------------------------------------------------------------------------
# Property 14: 灰度关时输出只含 opening/closing，不含 increase/decrease
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gray_off_output_equals_characterization(mock_active_filter):
    """灰度关：输出与旧路径逐字段等价（只含 opening/closing，不含 increase/decrease）."""
    rows = [
        _make_row("1401", 1000.0, 2000.0, level=1),
        _make_row("1471", -500.0, -800.0, level=1),
    ]
    ctx = _make_ctx(rows)

    # sa.select(...).where(active_filter) 需要 active_filter 是有效 SA 表达式
    # 用 patch sa.select 让整条链可通
    select_mock = MagicMock()
    select_mock.where.return_value = select_mock  # chainable

    with patch(
        "app.core.config.settings",
    ) as mock_settings, patch(
        "app.routers.wp_render_strategies._f2_inventory_main.sa.select",
        return_value=select_mock,
    ):
        mock_settings.F2_FOUR_TABLE_EXTRACTION_ENABLED = False

        result = await _build_adjudication_prefill(ctx)

    # 旧路径只含 opening/closing
    assert "raw-materials" in result
    assert set(result["raw-materials"].keys()) == {"opening", "closing"}
    assert result["raw-materials"]["opening"] == 1000.0
    assert result["raw-materials"]["closing"] == 2000.0

    # 跌价准备取绝对值
    assert "impairment-provision" in result
    assert result["impairment-provision"]["opening"] == 500.0
    assert result["impairment-provision"]["closing"] == 800.0

    # 不含 increase/decrease/formulas/source_codes
    assert "increase" not in result["raw-materials"]
    assert "decrease" not in result["raw-materials"]
    assert "formulas" not in result["raw-materials"]
    assert "source_codes" not in result["raw-materials"]


# ---------------------------------------------------------------------------
# 灰度开时输出含 opening/increase/decrease/closing/formulas/source_codes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gray_on_output_has_increase_decrease():
    """灰度开：输出含 opening/increase/decrease/closing/formulas/source_codes."""
    # Mock extract_f2_category_values 返回结构
    mock_raw = {
        "F2-1-gross-raw-materials-opening": {
            "value": 1000.0,
            "account": "1401",
            "column": "期初余额",
            "is_abs": False,
            "source_codes": ["1401.01", "1401.02"],
        },
        "F2-1-gross-raw-materials-increase": {
            "value": 500.0,
            "account": "1401",
            "column": "借方发生额",
            "is_abs": False,
            "source_codes": ["1401.01", "1401.02"],
        },
        "F2-1-gross-raw-materials-decrease": {
            "value": 200.0,
            "account": "1401",
            "column": "贷方发生额",
            "is_abs": False,
            "source_codes": ["1401.01", "1401.02"],
        },
    }

    ctx = types.SimpleNamespace(
        db=AsyncMock(), project_id="pid", year=2025, wp_id="wid"
    )

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.F2_FOUR_TABLE_EXTRACTION_ENABLED = True

        with patch(
            "app.services.f2_extraction.extract.extract_f2_category_values",
            new_callable=AsyncMock,
            return_value=mock_raw,
        ):
            result = await _build_adjudication_prefill(ctx)

    assert "raw-materials" in result
    entry = result["raw-materials"]
    assert entry["opening"] == 1000.0
    assert entry["increase"] == 500.0
    assert entry["decrease"] == 200.0
    # closing = opening + increase - decrease
    assert entry["closing"] == 1300.0
    assert "formulas" in entry
    assert "source_codes" in entry
    assert "1401.01" in entry["source_codes"]
    assert "1401.02" in entry["source_codes"]


# ---------------------------------------------------------------------------
# Property 1: 灰度开 + 父子科目 → 只取叶子
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gray_on_leaf_only():
    """灰度开 + 父子科目 → 只取叶子（Property 1，由 extract_f2_category_values 保证）."""
    # 构造 extract 返回的 source_codes 只含叶子
    mock_raw = {
        "F2-1-gross-raw-materials-opening": {
            "value": 800.0,
            "account": "1401",
            "column": "期初余额",
            "is_abs": False,
            "source_codes": ["1401.01", "1401.02"],  # 叶子，不含父 1401
        },
    }

    ctx = types.SimpleNamespace(
        db=AsyncMock(), project_id="pid", year=2025, wp_id="wid"
    )

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.F2_FOUR_TABLE_EXTRACTION_ENABLED = True

        with patch(
            "app.services.f2_extraction.extract.extract_f2_category_values",
            new_callable=AsyncMock,
            return_value=mock_raw,
        ):
            result = await _build_adjudication_prefill(ctx)

    assert "raw-materials" in result
    # source_codes 只含叶子
    assert "1401" not in result["raw-materials"]["source_codes"]
    assert "1401.01" in result["raw-materials"]["source_codes"]


# ---------------------------------------------------------------------------
# Property 3: 灰度开 + 1471 负值 → abs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gray_on_impairment_abs():
    """灰度开 + 1471 负值 → abs（Property 3，由 extract_f2_category_values 的 is_abs 保证）."""
    # 跌价准备 1471 期初为负值，经 ABS 后为正
    mock_raw = {
        "F2-1-impairment-impairment-provision-opening": {
            "value": 500.0,  # extract 已经 abs 过了
            "account": "1471",
            "column": "期初余额",
            "is_abs": True,
            "source_codes": ["1471.01"],
        },
        "F2-1-impairment-impairment-provision-increase": {
            "value": 100.0,
            "account": "1471",
            "column": "贷方发生额",
            "is_abs": False,
            "source_codes": ["1471.01"],
        },
        "F2-1-impairment-impairment-provision-decrease": {
            "value": 50.0,
            "account": "1471",
            "column": "借方发生额",
            "is_abs": False,
            "source_codes": ["1471.01"],
        },
    }

    ctx = types.SimpleNamespace(
        db=AsyncMock(), project_id="pid", year=2025, wp_id="wid"
    )

    with patch("app.core.config.settings") as mock_settings:
        mock_settings.F2_FOUR_TABLE_EXTRACTION_ENABLED = True

        with patch(
            "app.services.f2_extraction.extract.extract_f2_category_values",
            new_callable=AsyncMock,
            return_value=mock_raw,
        ):
            result = await _build_adjudication_prefill(ctx)

    assert "impairment-provision" in result
    entry = result["impairment-provision"]
    # value 已经 abs 过
    assert entry["opening"] == 500.0
    assert entry["increase"] == 100.0
    assert entry["decrease"] == 50.0
    # closing = 500 + 100 - 50 = 550
    assert entry["closing"] == 550.0
