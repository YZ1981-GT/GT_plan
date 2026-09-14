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


# ─── deliverable source_type 测试 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trace_deliverable_branch_reachable(facade, mock_db):
    """deliverable 分支可达 + source_id 格式无效返回空列表（需求 1.1）。"""
    result = await facade.trace(
        project_id=uuid.uuid4(),
        source_type="deliverable",
        source_id="invalid-no-colon",
        year=2025,
    )
    # source_id 格式无效（无冒号分隔符）→ 空
    assert result == []


@pytest.mark.asyncio
async def test_trace_deliverable_invalid_uuid(facade, mock_db):
    """deliverable source_id 中 word_export_task_id 非 UUID → 空列表。"""
    result = await facade.trace(
        project_id=uuid.uuid4(),
        source_type="deliverable",
        source_id="not-a-uuid:八、1",
        year=2025,
    )
    assert result == []


@pytest.mark.asyncio
async def test_trace_deliverable_no_matching_note(facade, mock_db):
    """无匹配 disclosure_notes 记录 → 返回"无匹配来源"结果（需求 1.4）。"""
    # Mock empty disclosure_notes query
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None
    mock_execute = MagicMock()
    mock_execute.scalars.return_value = mock_scalars
    mock_db.execute = AsyncMock(return_value=mock_execute)

    word_export_task_id = uuid.uuid4()
    result = await facade.trace(
        project_id=uuid.uuid4(),
        source_type="deliverable",
        source_id=f"{word_export_task_id}:八、99",
        year=2025,
    )

    # 应返回一条"无匹配来源"合约
    assert len(result) == 1
    assert result[0]["source_type"] == "deliverable"
    assert result[0]["target_type"] == "note"
    assert "无匹配来源" in result[0]["basis"]
    assert result[0]["status"] == "stale"
    assert result[0]["route"] is None


@pytest.mark.asyncio
async def test_trace_deliverable_with_matching_note(facade, mock_db):
    """有匹配 disclosure_notes 记录 → 返回溯源合约含 route（需求 1.2, 1.3）。"""
    project_id = uuid.uuid4()
    word_export_task_id = uuid.uuid4()
    note_id = uuid.uuid4()

    # Mock disclosure_notes query - return a matching note
    mock_note = MagicMock()
    mock_note.id = note_id
    mock_note.note_section = "八、1"
    mock_note.section_title = "货币资金"
    mock_note.is_stale = False

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_note

    mock_execute_note = MagicMock()
    mock_execute_note.scalars.return_value = mock_scalars

    # Mock stale query - return None (not stale)
    mock_stale_result = MagicMock()
    mock_stale_result.scalar_one_or_none.return_value = None

    # Setup mock_db.execute to return different results per call
    call_count = [0]
    original_results = [mock_execute_note, mock_stale_result]

    async def side_effect_execute(*args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(original_results):
            return original_results[idx]
        return MagicMock(scalars=lambda: MagicMock(first=lambda: None))

    mock_db.execute = AsyncMock(side_effect=side_effect_execute)

    with patch(
        "app.services.wp_trace_service.trace_upstream",
        new_callable=AsyncMock,
    ) as mock_trace_upstream:
        # Mock trace_upstream to return empty result
        from app.services.wp_trace_service import TraceResult
        mock_trace_upstream.return_value = TraceResult(
            source="disclosure", identifier="八、1", direction="upstream"
        )

        result = await facade.trace(
            project_id=project_id,
            source_type="deliverable",
            source_id=f"{word_export_task_id}:八、1",
            year=2025,
        )

    # 应有至少一条合约
    assert len(result) >= 1
    first_contract = result[0]
    assert first_contract["source_type"] == "deliverable"
    assert first_contract["target_type"] == "note"
    assert first_contract["target_id"] == str(note_id)
    assert first_contract["route"] is not None
    assert "disclosure-notes" in first_contract["route"]
    assert first_contract["status"] == "current"
    # 有 route 字段（需求 1.3 LinkageContract.route 支持跨层跳转）
    assert "route" in first_contract
