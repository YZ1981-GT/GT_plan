"""test_a17_chapter_pull_extended — A17-1 扩展章节拉取"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.a17_summary_service import pull_chapter_data


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.mark.asyncio
async def test_ch02_independence_no_tasks(mock_db):
    with patch(
        "app.services.a17_summary_service._wp_progress_line",
        return_value="A10-1：项目内无底稿",
    ):
        mock_db.execute = AsyncMock(side_effect=[
            MagicMock(scalar=lambda: 0),
            MagicMock(scalar=lambda: 0),
            MagicMock(scalar=lambda: 0),
            MagicMock(scalar=lambda: 0),
        ])
        result = await pull_chapter_data(mock_db, uuid.uuid4(), "A17-1-ch02")

    assert "尚未发起独立性签署" in result["content"]
    assert result["source_label"] == "A17-7+A10-1"


@pytest.mark.asyncio
async def test_ch12_kam_no_entries(mock_db):
    wp_id = uuid.uuid4()
    mock_db.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=lambda: wp_id),
        MagicMock(fetchall=lambda: []),
    ])
    result = await pull_chapter_data(mock_db, uuid.uuid4(), "A17-1-ch12")
    assert result["content"] is None
    assert "KAM" in result["message"]


@pytest.mark.asyncio
async def test_ch14_audit_report_stub(mock_db):
    with patch(
        "app.services.a17_summary_service.get_workpaper_summary",
        return_value={"ready": True, "summary_text": "A13 未更正错报：2 项"},
    ):
        report = MagicMock()
        report.opinion_type = MagicMock(value="unqualified")
        report.year = 2025
        report.status = "draft"
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: report))
        result = await pull_chapter_data(mock_db, uuid.uuid4(), "A17-1-ch14")

    assert "拟出具审计意见" in result["content"]
    assert "A13 未更正错报" in result["content"]


@pytest.mark.asyncio
async def test_governance_communication_no_wp():
    from app.services.workpaper_summaries_service import get_workpaper_summary

    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))
    result = await get_workpaper_summary(db, uuid.uuid4(), "governance_communication")
    assert result["ready"] is False
    assert "A10-2" in result["reason"]


@pytest.mark.asyncio
async def test_ch08_analytical_review_fallback(mock_db):
    wp_id = uuid.uuid4()

    async def fake_execute(stmt, params=None):
        sql = str(stmt)
        result = MagicMock()
        if "audit_period_end" in sql:
            result.scalar_one_or_none = lambda: MagicMock(year=2025)
        elif "wp.id" in sql:
            code = (params or {}).get("code")
            result.scalar_one_or_none = lambda: wp_id if code == "A1-13" else None
        elif "COUNT(*)" in sql and "conclusion" in sql:
            result.scalar = lambda: 0
        elif "COUNT(*)" in sql:
            result.scalar = lambda: 0
        else:
            result.scalar = lambda: 0
            result.scalar_one_or_none = lambda: None
        return result

    with patch(
        "app.services.analytical_review_service.get_analytical_review_data",
        side_effect=RuntimeError("no financial data"),
    ):
        mock_db.execute = fake_execute
        result = await pull_chapter_data(mock_db, uuid.uuid4(), "A17-1-ch08")

    assert "A1-13" in result["content"]
    assert "尚无 checklist" in result["content"] or "底稿已关联" in result["content"]


@pytest.mark.asyncio
async def test_ch09_related_party_ready(mock_db):
    with patch(
        "app.services.a17_summary_service.get_workpaper_summary",
        return_value={
            "ready": True,
            "summary_text": "A7-1 关联交易及往来：已填写 2 条",
        },
    ):
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: uuid.uuid4()))

        result = await pull_chapter_data(mock_db, uuid.uuid4(), "A17-1-ch09")

    assert "A7-1 关联交易" in result["content"]
    assert result["source_label"] == "A7+A7-1"


@pytest.mark.asyncio
async def test_ch10_going_concern_not_ready(mock_db):
    with patch(
        "app.services.a17_summary_service.get_workpaper_summary",
        return_value={"ready": False, "reason": "项目内无 A15-1 底稿"},
    ):
        result = await pull_chapter_data(mock_db, uuid.uuid4(), "A17-1-ch10")

    assert result["content"] is None
    assert "A15-1" in result["message"]


@pytest.mark.asyncio
async def test_ch05_consultation_progress(mock_db):
    wp_id = uuid.uuid4()

    async def fake_execute(stmt, params=None):
        sql = str(stmt)
        result = MagicMock()
        if "wp.id" in sql:
            code = (params or {}).get("code")
            result.scalar_one_or_none = lambda: wp_id if code == "A17-3" else None
        elif "COUNT(*)" in sql and "conclusion" in sql:
            result.scalar = lambda: 1
        elif "COUNT(*)" in sql:
            result.scalar = lambda: 3
        else:
            result.scalar = lambda: 0
        return result

    mock_db.execute = fake_execute

    result = await pull_chapter_data(mock_db, uuid.uuid4(), "A17-1-ch05")

    assert "A17-3" in result["content"]
    assert "A17-4：项目内无底稿" in result["content"]
