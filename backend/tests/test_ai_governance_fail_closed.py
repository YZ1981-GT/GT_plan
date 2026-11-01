"""AI 待确认状态读不到时，签字门禁与可用动作都必须阻断（ADR-LLM-016）。

spec llm-linkage-audit-practice-closure 任务 12：“治理状态未知视为未就绪”。
原实现两处都在异常时放行：签字门禁 ``return None``，可用动作按“没有 AI 草稿”放行。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.services import ai_content_log_service
from app.services.allowed_actions_service import _check_transition, _evaluate_guards
from app.services.gate_rules_ai_content import AIContentMustBeConfirmedRule
from app.services.state_machines.base import Transition


@pytest_asyncio.fixture
async def empty_db():
    """没有任何业务表的库：读 ai_content_log 必然失败，用来模拟状态不可读。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_sign_off_gate_blocks_when_ai_state_unreadable(empty_db, monkeypatch):
    async def broken(**_kwargs):
        raise RuntimeError("ai_content_log 不可读")

    monkeypatch.setattr(ai_content_log_service, "list_pending_by_project", broken)
    hit = await AIContentMustBeConfirmedRule().check(empty_db, {"project_id": uuid.uuid4()})
    assert hit is not None, "状态读不到时不得放行签字"
    assert hit.severity == "blocking"
    assert hit.error_code == "AI_CONTENT_STATE_UNKNOWN"
    assert hit.location["via"] == "state_unavailable"


@pytest.mark.asyncio
async def test_sign_off_gate_failure_does_not_poison_transaction(empty_db, monkeypatch):
    """失败只回滚到保存点：同一会话里后续规则的查询仍可执行。"""
    from sqlalchemy import text

    async def broken(**_kwargs):
        await empty_db.execute(text("SELECT * FROM table_that_does_not_exist"))

    monkeypatch.setattr(ai_content_log_service, "list_pending_by_project", broken)
    await AIContentMustBeConfirmedRule().check(empty_db, {"project_id": uuid.uuid4()})
    assert (await empty_db.execute(text("SELECT 1"))).scalar() == 1


@pytest.mark.asyncio
async def test_allowed_actions_deny_when_ai_state_unreadable(empty_db):
    guards = await _evaluate_guards(
        empty_db, uuid.uuid4(), uuid.uuid4(), "disclosure", False
    )
    assert guards["no_pending_ai_content"] is False
    assert guards["ai_pending_state_unknown"] is True
    allowed, code, message = _check_transition(
        Transition(from_="draft", action="submit", to="review", guards=["no_pending_ai_content"]),
        "manager",
        guards,
    )
    assert allowed is False
    assert code == "AI_STATE_UNKNOWN"
    assert "无法读取" in message


def test_known_pending_state_keeps_original_reason():
    allowed, code, _ = _check_transition(
        Transition(from_="draft", action="submit", to="review", guards=["no_pending_ai_content"]),
        "manager",
        {"no_pending_ai_content": False},
    )
    assert allowed is False
    assert code == "AI_PENDING"
