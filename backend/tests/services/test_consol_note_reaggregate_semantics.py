"""重新汇总 kept_manual 结果语义的纯单元测试。"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.consol_note_subtree_reaggregate import _Outcome, _Run, reaggregate_subtree
from app.services.consol_note_table_totals import build_note_rows
from tests.services.test_consol_note_subtree_reaggregate import (
    _SECTION,
    _YEAR,
    _rec,
    _setup,
    db,
    factory,
    group,
    user,
)


def test_build_note_rows_kept_cell_contains_computed_value():
    built = build_note_rows(
        [("银行存款", "data")],
        {0: {1: Decimal("100.00")}},
        width=2,
        protected={(0, 1)},
        existing_rows=[["银行存款", "999.00"]],
    )
    assert built.rows == [["银行存款", "999.00"]]
    assert built.kept == [{
        "row": 0,
        "col": 1,
        "kept_value": "999.00",
        "computed_value": "100.00",
    }]


def test_all_protected_cells_become_kept_manual_with_difference_count():
    node = SimpleNamespace(node_key="G:consol")
    outcome = _Outcome(
        "五、1", node, "aggregate", "persisted",
        detail={
            "filled_count": 0,
            "kept_manual_count": 2,
            "kept_manual": [
                {"kept_value": "999.00", "computed_value": "100.00"},
                {"kept_value": "200.00", "computed_value": "200.00"},
            ],
        },
    )

    result = _Run._classify_protected_outcome(outcome)
    assert result.status == "kept_manual"
    assert result.reason == "全部为手工格，汇总值未写入（其中 1 格与汇总值不同）"
    assert result.detail["manual_differs_count"] == 1


def test_manual_difference_uses_amounts_to_cents_not_string_format():
    node = SimpleNamespace(node_key="G:consol")
    outcome = _Outcome(
        "五、1", node, "aggregate", "persisted",
        detail={
            "filled_count": 0,
            "kept_manual_count": 1,
            "kept_manual": [{"kept_value": "1.0", "computed_value": "1.00"}],
        },
    )
    result = _Run._classify_protected_outcome(outcome)
    assert result.status == "kept_manual"
    assert result.detail["manual_differs_count"] == 0


@pytest.mark.asyncio
async def test_reaggregate_clears_stale_reason_after_automatic_write(db, user, group):
    await _setup(db, user, group)
    await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_SECTION])
    root = await _rec(db, group, "G:consol")
    root.is_stale = True
    root.stale_reason = "consol_push"
    root.stale_at = datetime.now(timezone.utc)
    await db.commit()

    await reaggregate_subtree(db, group["G"].id, _YEAR, node_key="G:consol", section_ids=[_SECTION])
    root = await _rec(db, group, "G:consol")
    assert root.is_stale is False
    assert root.stale_reason is None
    assert root.stale_at is None
