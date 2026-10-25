"""底稿指导对话：项目以底稿自身所属项目为准（spec knowledge-base-retrieval-and-authz-closure 5.3）。

router 级 ``dedicated_wp_gate`` 只证明当前用户能访问该底稿；端点若照用客户端传来的
``project_id``，就能把任意项目的客户名称 / 审计期间注入提示词，并以该项目范围检索知识库。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers.wp_guidance_chat import WpAiChatRequest, workpaper_ai_chat


def _db_with_wp(project_id: uuid.UUID):
    db = AsyncMock()
    wp_result = MagicMock()
    wp_result.first.return_value = SimpleNamespace(wp_code="D2-1", wp_name="应收账款", project_id=project_id)
    db.execute = AsyncMock(return_value=wp_result)
    return db


@pytest.mark.asyncio
async def test_mismatched_project_id_is_rejected_before_any_context_is_built():
    wp_project = uuid.uuid4()
    other_project = uuid.uuid4()
    db = _db_with_wp(wp_project)
    req = WpAiChatRequest(query="怎么编制", project_id=str(other_project))

    with pytest.raises(HTTPException) as exc_info:
        await workpaper_ai_chat(str(uuid.uuid4()), req, db, MagicMock())

    assert exc_info.value.status_code == 422
    assert "不一致" in exc_info.value.detail
    # 只查了底稿本身；没有去读另一个项目的客户信息
    assert db.execute.await_count == 1


def test_empty_project_id_rejected_by_schema():
    with pytest.raises(ValidationError):
        WpAiChatRequest(query="x", project_id="")
