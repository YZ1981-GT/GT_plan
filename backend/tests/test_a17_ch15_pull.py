"""test_a17_ch15_pull — ch15 其他特殊考虑事项 拉取服务单元测试

覆盖:
- issue_hints 舞弊计数集成
- A13 错报计数
- A14 缺陷计数
- 异常降级（graceful fallback）
"""

import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.a17_summary_service import pull_chapter_data


def _make_scalar_result(value):
    """构建 mock execute result，.scalar() 返回指定值"""
    result = MagicMock()
    result.scalar.return_value = value
    return result


@pytest.fixture
def mock_db():
    """构造 mock db session"""
    return AsyncMock()


@pytest.mark.asyncio
async def test_ch15_zero_counts(mock_db):
    """无舞弊/错报/缺陷时返回 0 条计数"""
    hints_return = {
        "fraud": {"count": 0, "items": [], "heuristic_only": True, "note": ""},
        "legal_violation": {"count": 0, "items": [], "heuristic_only": True, "note": ""},
    }

    with patch("app.services.a17_summary_service.get_issue_hints", return_value=hints_return):
        mock_db.execute = AsyncMock(side_effect=[
            _make_scalar_result(0),  # A13 count
            _make_scalar_result(0),  # A14 count
        ])

        result = await pull_chapter_data(mock_db, uuid.uuid4(), "A17-1-ch15")

    assert result["content"] is not None
    assert "舞弊相关问题单：0 条" in result["content"]
    assert "A13 未更正错报：0 项" in result["content"]
    assert "A14 内控缺陷：0 项" in result["content"]
    assert result["source_label"] == "issue_hints+A13+A14"


@pytest.mark.asyncio
async def test_ch15_with_fraud_items(mock_db):
    """有舞弊问题单时显示计数+标题列表"""
    hints_return = {
        "fraud": {
            "count": 2,
            "items": [
                {"id": "1", "title": "管理层涉嫌舞弊行为", "severity": "major"},
                {"id": "2", "title": "伪造银行流水记录", "severity": "blocker"},
            ],
            "heuristic_only": True,
            "note": "",
        },
        "legal_violation": {"count": 0, "items": [], "heuristic_only": True, "note": ""},
    }

    with patch("app.services.a17_summary_service.get_issue_hints", return_value=hints_return):
        mock_db.execute = AsyncMock(side_effect=[
            _make_scalar_result(3),  # A13 count
            _make_scalar_result(1),  # A14 count
        ])

        result = await pull_chapter_data(mock_db, uuid.uuid4(), "A17-1-ch15")

    content = result["content"]
    assert "舞弊相关问题单：2 条" in content
    assert "管理层涉嫌舞弊行为" in content
    assert "伪造银行流水记录" in content
    assert "A13 未更正错报：3 项" in content
    assert "A14 内控缺陷：1 项" in content


@pytest.mark.asyncio
async def test_ch15_issue_hints_failure_graceful(mock_db):
    """issue_hints 查询失败时 graceful 降级"""
    with patch(
        "app.services.a17_summary_service.get_issue_hints",
        side_effect=Exception("DB connection lost"),
    ):
        mock_db.execute = AsyncMock(side_effect=[
            _make_scalar_result(0),  # A13 count
            _make_scalar_result(0),  # A14 count
        ])

        result = await pull_chapter_data(mock_db, uuid.uuid4(), "A17-1-ch15")

    assert result["content"] is not None
    assert "查询失败" in result["content"]
    # A13/A14 should still work
    assert "A13 未更正错报：0 项" in result["content"]
    assert "A14 内控缺陷：0 项" in result["content"]


@pytest.mark.asyncio
async def test_ch15_heuristic_warning_displayed(mock_db):
    """确认启发式警告文字出现在输出中"""
    hints_return = {
        "fraud": {"count": 1, "items": [{"id": "x", "title": "舞弊嫌疑", "severity": "major"}], "heuristic_only": True, "note": ""},
        "legal_violation": {"count": 0, "items": [], "heuristic_only": True, "note": ""},
    }

    with patch("app.services.a17_summary_service.get_issue_hints", return_value=hints_return):
        mock_db.execute = AsyncMock(side_effect=[
            _make_scalar_result(0),
            _make_scalar_result(0),
        ])

        result = await pull_chapter_data(mock_db, uuid.uuid4(), "A17-1-ch15")

    assert "仅标题关键词启发式" in result["content"]
    assert "仅供提示" in result["content"]
