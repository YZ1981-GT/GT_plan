"""LinkageFacadeService 单元测试（P1-1）

验证 facade 正确包装各子服务并附加 conflict/stale 状态。
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.linkage_facade_service import LinkageFacadeService


@pytest.fixture
def mock_db():
    """Mock AsyncSession"""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: []))
    return db


@pytest.fixture
def facade(mock_db):
    return LinkageFacadeService(mock_db)


@pytest.mark.asyncio
async def test_trace_tb_returns_contracts(facade, mock_db):
    """试算表来源应返回底稿/调整分录 contract。"""
    project_id = uuid.uuid4()

    # Mock get_workpapers_for_tb_row
    with patch.object(
        facade._linkage_svc, "get_workpapers_for_tb_row",
        new_callable=AsyncMock,
        return_value=[{"id": "wp-001", "wp_code": "D1", "wp_name": "收入"}],
    ), patch.object(
        facade._linkage_svc, "get_adjustments_for_tb_row",
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await facade.trace(
            project_id=project_id,
            source_type="trial_balance",
            source_id="row-code-1",
            year=2025,
        )

    assert len(result) >= 1
    assert result[0]["source_type"] == "trial_balance"
    assert result[0]["target_type"] == "workpaper"
    assert result[0]["target_id"] == "wp-001"
    assert result[0]["status"] == "current"


@pytest.mark.asyncio
async def test_trace_note_returns_contracts(facade, mock_db):
    """附注来源应溯源到底稿/试算表。"""
    project_id = uuid.uuid4()

    mock_trace_result = {
        "section_number": "sec-1",
        "note_data": {"wp_code": "D1", "account_codes": None, "note_title": "收入"},
        "workpaper_data": None,
        "trial_balance_data": [
            {"account_code": "6001", "account_name": "营业收入", "opening": 0, "audited": 1000000},
        ],
        "top_ledger_entries": [],
    }

    with patch.object(
        facade._report_trace_svc, "trace_section",
        new_callable=AsyncMock,
        return_value=mock_trace_result,
    ):
        result = await facade.trace(
            project_id=project_id,
            source_type="note",
            source_id="sec-1",
            year=2025,
        )

    assert len(result) >= 1
    # 应有底稿链接
    wp_contracts = [c for c in result if c["target_type"] == "workpaper"]
    assert len(wp_contracts) == 1
    assert wp_contracts[0]["target_id"] == "D1"


@pytest.mark.asyncio
async def test_trace_unknown_source_type_returns_empty(facade):
    """不支持的 source_type 应返回空列表。"""
    result = await facade.trace(
        project_id=uuid.uuid4(),
        source_type="unknown_type",
        source_id="x",
    )
    assert result == []


@pytest.mark.asyncio
async def test_enrich_conflict_stale(facade, mock_db):
    """有 pending 冲突时，应附加 conflict 状态。"""
    project_id = uuid.uuid4()
    conflict_id = str(uuid.uuid4())

    # Mock conflict query
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        (conflict_id, "workpaper", "wp-001"),
    ]
    mock_db.execute = AsyncMock(return_value=mock_result)

    contracts = [
        {
            "source_type": "trial_balance",
            "source_id": "row-1",
            "target_type": "workpaper",
            "target_id": "wp-001",
            "status": "current",
        }
    ]

    enriched = await facade._enrich_conflict_stale(project_id, contracts)
    assert enriched[0]["status"] == "conflict"
    assert enriched[0]["conflict_id"] == conflict_id


@pytest.mark.asyncio
async def test_trace_exception_handled_gracefully(facade):
    """子服务异常不应导致 facade 崩溃。"""
    with patch.object(
        facade._linkage_svc, "get_workpapers_for_tb_row",
        new_callable=AsyncMock,
        side_effect=Exception("DB 连接失败"),
    ), patch.object(
        facade._linkage_svc, "get_adjustments_for_tb_row",
        new_callable=AsyncMock,
        side_effect=Exception("DB 连接失败"),
    ):
        result = await facade.trace(
            project_id=uuid.uuid4(),
            source_type="trial_balance",
            source_id="row-1",
            year=2025,
        )
    # 不崩溃，返回空列表
    assert result == []
