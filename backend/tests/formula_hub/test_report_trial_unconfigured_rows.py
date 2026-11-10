"""报表试算与报表生成同口径：未配置公式的行按 0 参与 ``ROW()`` 引用（2026-11-09 浏览器走查发现）。

原状：试算只发带公式的行，合计行 ``ROW('BS-013')`` 引用未配置公式的行即「引用的行次不存在或尚未计算」整行失败；
报表生成对空公式行记 0（``ReportFormulaParser.execute`` / ``execute_result``），同一张表合计算得出数。
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.report_config_execute import BatchFormula, _pure, _run_batch


@pytest.mark.asyncio
async def test_unconfigured_row_counts_as_zero_for_row_refs():
    items = [
        BatchFormula(row_code="BS-002", formula="100"),
        BatchFormula(row_code="BS-013", formula=""),
        BatchFormula(row_code="BS-015", formula="ROW('BS-002') + ROW('BS-013')"),
    ]
    results, row_values = await _run_batch(items, _pure)
    by_code = {r["row_code"]: r for r in results}
    assert by_code["BS-015"]["ok"] is True
    assert by_code["BS-015"]["value"] == 100.0
    # 未配置公式的行自身不出结果
    assert "BS-013" not in by_code
    assert row_values["BS-013"] == Decimal("0")


@pytest.mark.asyncio
async def test_row_not_sent_still_fails_as_missing():
    """本批没有的行（不是「未配置」而是根本没带）仍按缺行失败，不补 0。"""
    items = [BatchFormula(row_code="BS-015", formula="ROW('BS-999')")]
    results, _ = await _run_batch(items, _pure)
    assert results[0]["ok"] is False
    assert "BS-999" in results[0]["error"]


@pytest.mark.asyncio
async def test_configured_row_value_is_not_overwritten_by_zero_seed():
    """同一行次既有公式行也有空公式行：以公式算出的值为准。"""
    items = [
        BatchFormula(row_code="BS-002", formula="7"),
        BatchFormula(row_code="BS-002", formula=""),
        BatchFormula(row_code="BS-015", formula="ROW('BS-002')"),
    ]
    results, _ = await _run_batch(items, _pure)
    assert {r["row_code"]: r["value"] for r in results}["BS-015"] == 7.0
