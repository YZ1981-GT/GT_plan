"""confirmation-coverage-single-source: 科目审定总额(population)解析与注入单测。

覆盖 design.md Correctness Properties：
- Property4：负债科目 population 取绝对值（恒非负）
- Property7：注入加法式（不改 rows/_format/其它字段）
- Property8：无匹配 account_type → population_amount === None
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.wp_render_config_helpers import (
    _ACCOUNT_TYPE_TO_CODE_PREFIX,
    _resolve_confirmation_population,
    _inject_confirmation_population,
)


def _mock_db(scalar_values: list):
    """构造 db，其 execute().scalar() 依次返回 scalar_values（每前缀一次）。"""
    db = MagicMock()
    results = []
    for v in scalar_values:
        r = MagicMock()
        r.scalar.return_value = v
        results.append(r)
    db.execute = AsyncMock(side_effect=results)
    return db


PID = uuid.uuid4()


# ─── Property8：无匹配 / 缺失 → None ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_matching_account_type_returns_none():
    db = _mock_db([])
    rows = [{"account_type": "未知科目名"}, {"account_type": ""}]
    result = await _resolve_confirmation_population(db, PID, 2025, rows)
    assert result is None
    db.execute.assert_not_called()  # 无前缀匹配则不触库


@pytest.mark.asyncio
async def test_empty_rows_returns_none():
    db = _mock_db([])
    assert await _resolve_confirmation_population(db, PID, 2025, []) is None


@pytest.mark.asyncio
async def test_year_none_returns_none():
    db = _mock_db([])
    rows = [{"account_type": "应收账款"}]
    assert await _resolve_confirmation_population(db, PID, None, rows) is None
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_sum_zero_returns_none():
    """SUM 为 0（科目无余额）→ None，不用 0 冒充。"""
    db = _mock_db([0])
    rows = [{"account_type": "应收账款"}]
    assert await _resolve_confirmation_population(db, PID, 2025, rows) is None


# ─── 正常解析 ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_single_account_type_resolves_sum():
    db = _mock_db([1000000.0])
    rows = [{"account_type": "应收账款"}, {"account_type": "应收账款"}]
    result = await _resolve_confirmation_population(db, PID, 2025, rows)
    assert result == 1000000.0
    # distinct 前缀去重 → 仅 1 次查询
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_multiple_account_types_accumulate():
    # 应收账款(1122)=600000 + 银行存款(1002)=400000
    db = _mock_db([600000.0, 400000.0])
    rows = [{"account_type": "应收账款"}, {"account_type": "银行存款"}]
    result = await _resolve_confirmation_population(db, PID, 2025, rows)
    assert result == 1000000.0
    assert db.execute.await_count == 2


# ─── Property4：负债科目取绝对值 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_liability_negative_sum_taken_absolute():
    """应付账款审定净额为负（贷方）时 population 取绝对值 → 恒非负。"""
    db = _mock_db([-800000.0])
    rows = [{"account_type": "应付账款"}]
    result = await _resolve_confirmation_population(db, PID, 2025, rows)
    assert result == 800000.0


# ─── fail-open ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_exception_returns_none():
    db = MagicMock()
    db.execute = AsyncMock(side_effect=RuntimeError("db down"))
    rows = [{"account_type": "应收账款"}]
    assert await _resolve_confirmation_population(db, PID, 2025, rows) is None


# ─── 映射覆盖 ────────────────────────────────────────────────────────────────

def test_account_type_prefix_map_covers_core_types():
    for name in ("应收账款", "应付账款", "银行存款", "其他应收款", "预付账款"):
        assert name in _ACCOUNT_TYPE_TO_CODE_PREFIX
    assert _ACCOUNT_TYPE_TO_CODE_PREFIX["应收账款"] == "1122"
    assert _ACCOUNT_TYPE_TO_CODE_PREFIX["应付账款"] == "2202"


# ─── Property7：注入加法式 ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_inject_additive_preserves_rows_and_format():
    db = _mock_db([500000.0])
    html = {
        "_format": "confirmation-v1",
        "rows": [{"account_type": "应收账款", "amount": 1000}],
        "sampling": {"x": 1},
        "notes": {},
        "conclusion": {},
    }
    original_rows = html["rows"]
    await _inject_confirmation_population(db, PID, 2025, html)
    # 加法式：新增 project_context.population_amount，不改 rows/_format/sampling
    assert html["project_context"]["population_amount"] == 500000.0
    assert html["_format"] == "confirmation-v1"
    assert html["rows"] is original_rows
    assert html["sampling"] == {"x": 1}


@pytest.mark.asyncio
async def test_inject_unresolvable_writes_null():
    db = _mock_db([])
    html = {"_format": "confirmation-v1", "rows": [{"account_type": "未知"}]}
    await _inject_confirmation_population(db, PID, 2025, html)
    assert html["project_context"]["population_amount"] is None


@pytest.mark.asyncio
async def test_inject_non_dict_noop():
    db = _mock_db([])
    # 不应抛错
    await _inject_confirmation_population(db, PID, 2025, None)  # type: ignore[arg-type]
