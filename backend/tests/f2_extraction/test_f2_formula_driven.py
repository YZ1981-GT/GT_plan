"""F2 公式驱动取数测试.

Property 8: 公式驱动—改 binding account 改变取数值
Property 9: _build_adjudication_prefill_v2 不 import evaluate_wp_formula_expression
"""
from __future__ import annotations

import inspect
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.wp_render_strategies._f2_inventory_main import (
    _build_adjudication_prefill_v2,
)


def _make_ctx():
    """构造最小 RenderContext mock."""
    ctx = types.SimpleNamespace()
    ctx.project_id = "test-project-id"
    ctx.year = 2025
    ctx.wp_id = "test-wp-id"
    ctx.db = AsyncMock()
    return ctx


# ---------------------------------------------------------------------------
# Property 8: resolve_effective 返回自定义 binding → extract 用该 account 取数
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_effective_drives_extract():
    """mock resolve_effective 返回改 account 1401→1402 的 binding，
    验证 extract 被调用时使用的 bindings 含 account 1402 而非 1401。
    """
    ctx = _make_ctx()

    # 自定义 binding：原材料 opening 改用 1402 而非默认 1401
    custom_bindings = [
        {
            "anchor": "F2-1-gross-raw-materials-opening",
            "expression": "TB('1402','期初余额')",
            "formula_type": "auto_calc",
            "description": "测试自定义",
            "sheet_name": "",
            "source": "custom",
        },
    ]

    # mock resolve_effective 返回自定义 binding
    with patch(
        "app.services.f2_extraction.presets.resolve_effective",
        new_callable=AsyncMock,
        return_value=custom_bindings,
    ) as mock_resolve:
        # mock extract_f2_category_values 返回对应结果
        extract_result = {
            "F2-1-gross-raw-materials-opening": {
                "value": 99999.99,
                "account": "1402",
                "column": "期初余额",
                "is_abs": False,
                "source_codes": ["1402.01"],
            },
        }
        with patch(
            "app.services.f2_extraction.extract.extract_f2_category_values",
            new_callable=AsyncMock,
            return_value=extract_result,
        ) as mock_extract:
            result = await _build_adjudication_prefill_v2(ctx)

            # resolve_effective 被调用
            mock_resolve.assert_called_once_with(ctx.db, ctx.wp_id, ctx.project_id)

            # extract 被调用时用了 custom_bindings（含 1402）
            mock_extract.assert_called_once()
            call_bindings = mock_extract.call_args[0][1]
            assert call_bindings == custom_bindings

            # 结果反映 1402 的值
            assert "raw-materials" in result
            assert result["raw-materials"]["opening"] == 99999.99


# ---------------------------------------------------------------------------
# Property 9: _build_adjudication_prefill_v2 函数体不 import evaluate_wp_formula_expression
# ---------------------------------------------------------------------------


def test_f2_does_not_call_generic_evaluator():
    """断言 _build_adjudication_prefill_v2 函数体不引用 evaluate_wp_formula_expression。

    确保 F2 取数走专属 extract 路径，不走通用公式评估器。
    """
    source = inspect.getsource(_build_adjudication_prefill_v2)
    assert "evaluate_wp_formula_expression" not in source, (
        "_build_adjudication_prefill_v2 不应 import 或引用 evaluate_wp_formula_expression"
    )
