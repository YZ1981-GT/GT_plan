"""J2 AI 生成端点（spec llm-ocr-local-first-routing R5.1 / R5.4）。

旧实现 import 了不存在的 ``ai_service.chat_completion`` ⇒ 恒走占位分支，且端点未鉴权。
现在走平台统一入口（本机优先路由）并要求登录。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.deps import get_current_user, get_db
from app.routers.wp_render_strategies import _j2_ai_generate as j2

URL = "/api/workpapers/wp-1/j2/ai/generate"


def _client(*, logged_in: bool) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(j2.router)

    async def _db():
        yield None

    app.dependency_overrides[get_db] = _db
    if logged_in:
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4(), username="auditor")
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_requires_login(monkeypatch):
    llm = AsyncMock(return_value="不该被调用")
    monkeypatch.setattr(j2, "chat_completion", llm)
    async with _client(logged_in=False) as client:
        response = await client.post(URL, json={"section": "assumption-analysis"})
    assert response.status_code in (401, 403)
    llm.assert_not_awaited()


@pytest.mark.asyncio
async def test_generates_through_the_unified_entry(monkeypatch):
    llm = AsyncMock(return_value="折现率与国债收益率一致，假设合理。")
    monkeypatch.setattr(j2, "chat_completion", llm)
    async with _client(logged_in=True) as client:
        response = await client.post(URL, json={
            "section": "assumption-analysis", "context": {"折现率": "2.5%"}, "existing_content": "初稿",
        })
    assert response.status_code == 200, response.text
    assert response.json() == {"content": "折现率与国债收益率一致，假设合理。", "section": "assumption-analysis"}
    messages = llm.await_args.kwargs["messages"]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "折现率" in messages[1]["content"] and "初稿" in messages[1]["content"]


@pytest.mark.asyncio
async def test_unavailable_model_is_not_returned_as_content(monkeypatch):
    monkeypatch.setattr(j2, "chat_completion", AsyncMock(return_value="[LLM 服务暂不可用，请检查模型配置和网络]"))
    async with _client(logged_in=True) as client:
        response = await client.post(URL, json={"section": "isa620-evaluation"})
    assert response.status_code == 200
    assert response.json()["content"] == "[AI生成暂时不可用] 请手动填写isa620-evaluation相关内容。"
