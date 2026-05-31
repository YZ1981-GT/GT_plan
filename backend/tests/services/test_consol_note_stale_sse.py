"""合并附注 stale → SSE 广播单测（consol-phase3-frontend-drilldown / 需求 7 / 6A.1 / ADR-CONSOL-304）.

覆盖：
- mark_consol_sections_stale 标记 >0 行后调 _emit_consol_note_stale → broadcast_raw("consol.note_stale", ...)
- 标记 0 行时不广播（无变化不打扰）
- _emit_consol_note_stale 异常静默回退（不阻断）

Validates: Requirements 7.1, 7.2; ADR-CONSOL-304 (复用 SSE 不轮询).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services import consol_note_stale_handler as h


def _mock_db_rowcount(n: int):
    """构造 db.execute 返回 rowcount=n 的 mock。"""
    mock_result = MagicMock()
    mock_result.rowcount = n
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


@pytest.mark.asyncio
async def test_mark_stale_emits_sse_when_rows_affected():
    """标记 >0 行 → 广播 consol.note_stale SSE。"""
    pid = uuid4()
    db = _mock_db_rowcount(3)
    with patch.object(h, "_emit_consol_note_stale") as mock_emit:
        count = await h.mark_consol_sections_stale(pid, "sec-1", 2025, db)

    assert count == 3
    mock_emit.assert_called_once_with(pid, 2025, "sec-1", 3)


@pytest.mark.asyncio
async def test_mark_stale_no_emit_when_zero_rows():
    """标记 0 行 → 不广播（无变化不打扰）。"""
    pid = uuid4()
    db = _mock_db_rowcount(0)
    with patch.object(h, "_emit_consol_note_stale") as mock_emit:
        count = await h.mark_consol_sections_stale(pid, None, 2025, db)

    assert count == 0
    mock_emit.assert_not_called()


def test_emit_consol_note_stale_broadcasts_raw():
    """_emit_consol_note_stale 以正确事件名 + payload 调 broadcast_raw。"""
    pid = uuid4()
    mock_bus = MagicMock()
    with patch("app.services.event_bus.event_bus", mock_bus):
        h._emit_consol_note_stale(pid, 2025, "sec-货币资金", 5)

    mock_bus.broadcast_raw.assert_called_once()
    args, _ = mock_bus.broadcast_raw.call_args
    assert args[0] == "consol.note_stale"
    assert args[1] == {
        "project_id": str(pid),
        "year": 2025,
        "section_id": "sec-货币资金",
        "stale_count": 5,
    }


def test_emit_consol_note_stale_swallows_errors():
    """broadcast_raw 抛错时静默回退，不向上抛。"""
    pid = uuid4()
    mock_bus = MagicMock()
    mock_bus.broadcast_raw.side_effect = RuntimeError("no loop")
    with patch("app.services.event_bus.event_bus", mock_bus):
        h._emit_consol_note_stale(pid, 2025, None, 1)  # 不抛即通过
