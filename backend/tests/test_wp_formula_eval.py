# Feature: custom-workpaper-formula-binding — 公式求值写回
"""evaluate_wp_formula_expression + write_cell_to_parsed_data 单元测试。"""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.workpaper_models import WorkingPaper
from app.services.wp_formula_eval_service import evaluate_wp_formula_expression
from app.services.wp_parsed_data_service import write_cell_to_parsed_data


def test_write_cell_preserves_dict_shape():
    wp = WorkingPaper(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        wp_index_id=uuid.uuid4(),
        parsed_data={
            "html_data": {
                "审定表": {
                    "cells": {
                        "A5": {"value": "货币资金", "label": "货币资金"},
                        "B5": {"value": 1, "v": 1, "label": "amount"},
                    }
                }
            }
        },
    )
    write_cell_to_parsed_data(wp, sheet_name="审定表", cell_ref="b5", value=8888)
    cell = wp.parsed_data["html_data"]["审定表"]["cells"]["B5"]
    assert isinstance(cell, dict)
    assert cell["value"] == 8888
    assert cell["label"] == "amount"


import pytest


@pytest.mark.asyncio
async def test_evaluate_literal_decimal():
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        val, errs = await evaluate_wp_formula_expression(
            db,
            project_id=uuid.uuid4(),
            year=2025,
            expression="123.45",
        )
        assert errs == []
        assert val == Decimal("123.45")
    await engine.dispose()
