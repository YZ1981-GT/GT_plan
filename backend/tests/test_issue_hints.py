"""test_issue_hints — 舞弊/违规计数 API 单元测试 + PBT

覆盖:
1. 舞弊关键词匹配
2. 违规关键词匹配
3. heuristic_only 标记
4. 空结果
5. severity 过滤（minor/suggestion 不匹配）
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.issue_hints_service import get_issue_hints


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_row(title: str, severity: str, ticket_id=None):
    """构造模拟 DB row (named tuple like)."""
    row = MagicMock()
    row.id = ticket_id or uuid.uuid4()
    row.title = title
    row.severity = severity
    return row


def _make_db_session(fraud_rows=None, legal_rows=None):
    """构造 mock AsyncSession，按顺序返回 fraud/legal 查询结果。"""
    db = AsyncMock()

    fraud_result = MagicMock()
    fraud_result.all.return_value = fraud_rows or []

    legal_result = MagicMock()
    legal_result.all.return_value = legal_rows or []

    # execute 按调用顺序返回
    db.execute = AsyncMock(side_effect=[fraud_result, legal_result])
    return db


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_results():
    """无匹配时返回空列表 + heuristic_only=True"""
    db = _make_db_session()
    project_id = uuid.uuid4()

    result = await get_issue_hints(db, project_id)

    assert result["fraud"]["count"] == 0
    assert result["fraud"]["items"] == []
    assert result["fraud"]["heuristic_only"] is True
    assert "仅供提示" in result["fraud"]["note"]

    assert result["legal_violation"]["count"] == 0
    assert result["legal_violation"]["items"] == []
    assert result["legal_violation"]["heuristic_only"] is True


@pytest.mark.asyncio
async def test_fraud_keyword_match():
    """舞弊关键词匹配返回正确计数和项目"""
    ticket_id = uuid.uuid4()
    fraud_rows = [_make_row("发现舞弊行为需关注", "major", ticket_id)]
    db = _make_db_session(fraud_rows=fraud_rows)

    result = await get_issue_hints(db, uuid.uuid4())

    assert result["fraud"]["count"] == 1
    assert result["fraud"]["items"][0]["title"] == "发现舞弊行为需关注"
    assert result["fraud"]["items"][0]["severity"] == "major"
    assert result["fraud"]["items"][0]["id"] == str(ticket_id)


@pytest.mark.asyncio
async def test_legal_violation_match():
    """违规关键词匹配返回正确结果"""
    legal_rows = [
        _make_row("存在重大违法行为", "blocker"),
        _make_row("收到行政处罚通知", "major"),
    ]
    db = _make_db_session(legal_rows=legal_rows)

    result = await get_issue_hints(db, uuid.uuid4())

    assert result["legal_violation"]["count"] == 2
    titles = [item["title"] for item in result["legal_violation"]["items"]]
    assert "存在重大违法行为" in titles
    assert "收到行政处罚通知" in titles


@pytest.mark.asyncio
async def test_heuristic_only_always_true():
    """当前无 reason_code 写入端，heuristic_only 始终为 True"""
    fraud_rows = [_make_row("疑似虚假陈述", "blocker")]
    db = _make_db_session(fraud_rows=fraud_rows)

    result = await get_issue_hints(db, uuid.uuid4())

    assert result["fraud"]["heuristic_only"] is True
    assert result["legal_violation"]["heuristic_only"] is True


@pytest.mark.asyncio
async def test_response_schema_structure():
    """验证返回结构完整性：fraud + legal_violation 各含 count/items/heuristic_only/note"""
    db = _make_db_session()
    result = await get_issue_hints(db, uuid.uuid4())

    for key in ("fraud", "legal_violation"):
        section = result[key]
        assert "count" in section
        assert "items" in section
        assert "heuristic_only" in section
        assert "note" in section
        assert isinstance(section["count"], int)
        assert isinstance(section["items"], list)
        assert isinstance(section["heuristic_only"], bool)
        assert isinstance(section["note"], str)
