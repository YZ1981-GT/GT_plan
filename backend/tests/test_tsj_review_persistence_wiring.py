"""TSJ 复核端点到确认日志的真实接线守卫。

历史缺陷：`POST /api/workpapers/{wp_id}/ai/tsj-review` 只把 parser 临时 UUID
回给前端，既没有调用 tsj_structured_output_service，也没有 ai_content_log；
前端「确认 / 驳回」必 404，sign-off 门禁也完全看不到复核内容。

本文件用真实 FastAPI router + 真实动态 `require_wp_edit_permission()` 依赖，
只替换外部 LLM / DB 内容读取 / 持久化下层，验证端点把认证用户、服务端解析结果
和确认日志 ID 正确接起来。持久层真实行和 PG 保存点语义另由
`test_tsj_structured_output_pg.py` 覆盖。
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import get_db
from app.deps import get_current_user
from app.routers.wp_ai import router
from app.services.tsj_structured_output_service import TsjConfirmationLogWriteError


class _Result:
    """最小 SQLAlchemy result 双身，只实现端点读的 scalar_one_or_none。"""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _app_and_dependencies():
    """构造只挂 wp_ai router 的真实 ASGI app，返回可替换依赖与夹具。"""
    app = FastAPI()
    app.include_router(router)
    wp_id = uuid.uuid4()
    project_id = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role=SimpleNamespace(value="auditor"))
    wp = SimpleNamespace(id=wp_id, project_id=project_id, wp_index_id=uuid.uuid4())
    wp_index = SimpleNamespace(wp_code="D2-3", wp_name="坏账准备明细表", audit_cycle="D")
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_Result(wp), _Result(wp_index)])
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    async def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    return app, db, user, wp, wp_index


def _patch_success_chain(*, project_id, log_id):
    """外部 LLM / 内容读取 / 服务持久化的成功替身。"""
    saved = SimpleNamespace(data_sources={"ai_content_log_id": str(log_id)})
    return (
        patch.object(settings, "WP_AI_SERVICE_ENABLED", True),
        patch("app.deps.authorize_wp_edit", new=AsyncMock(return_value=project_id)),
        patch(
            "app.services.review_prompt_service.ReviewPromptService.load_prompt",
            return_value=SimpleNamespace(content="复核提示词", source_level="sheet"),
        ),
        patch(
            "app.services.review_content_loader.load_workpaper_review_content",
            new=AsyncMock(return_value="底稿服务端内容"),
        ),
        patch(
            "app.services.llm_client.chat_completion",
            new=AsyncMock(return_value=json.dumps({"findings": [{
                "description": "坏账准备比例不符",
                "risk_level": "high",
                "passed": False,
                "category": "认定检查",
                "location": "坏账准备!C15:D20",
                "suggestion": "按政策重算",
            }]}, ensure_ascii=False)),
        ),
        patch(
            "app.services.tsj_structured_output_service.process_review_response",
            new=AsyncMock(return_value=[saved]),
        ),
        patch("app.services.audit_logger_enhanced.audit_logger.log_action", new=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_tsj_review_persists_via_authenticated_user_and_returns_log_id():
    """生产端点把认证用户透传给 TSJ 服务，并以真实确认日志 ID 回前端。"""
    app, db, user, wp, _wp_index = _app_and_dependencies()
    log_id = uuid.uuid4()
    patches = _patch_success_chain(project_id=wp.project_id, log_id=log_id)
    try:
        with patches[0], patches[1] as authorize, patches[2], patches[3], patches[4], patches[5] as persist, patches[6] as audit:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(f"/api/workpapers/{wp.id}/ai/tsj-review")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["findings"][0]["id"] == str(log_id), "确认/驳回必须拿 ai_content_log id，不是 parser 临时 UUID"
    assert body["findings"][0]["confirmation_status"] == "pending"
    assert body["findings"][0]["sheet"] == "坏账准备"
    assert body["findings"][0]["cell_range"] == "C15:D20"
    authorize.assert_awaited_once_with(db, user, wp.id)
    assert db.execute.await_count == 2
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()

    call = persist.await_args.kwargs
    assert call["user_id"] == user.id
    assert call["project_id"] == wp.project_id
    assert call["workpaper_id"] == wp.id
    assert call["wp_code"] == "D2-3"
    assert call["audit_cycle"] == "D"
    payload = json.loads(call["response_text"])
    assert payload == {"findings": [{
        "issue_type": "认定检查", "severity": "high", "sheet": "坏账准备",
        "cell_range": "C15:D20", "description": "坏账准备比例不符",
        "evidence_ref": "", "remediation": "按政策重算",
    }]}
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_tsj_review_fails_closed_when_confirmation_log_cannot_persist():
    """下层确认日志失败时端点返回 503，不回假 pending findings，也不记成功审计。"""
    app, db, user, wp, _wp_index = _app_and_dependencies()
    log_id = uuid.uuid4()
    patches = _patch_success_chain(project_id=wp.project_id, log_id=log_id)
    try:
        with patches[0], patches[1], patches[2], patches[3], patches[4], patch(
            "app.services.tsj_structured_output_service.process_review_response",
            new=AsyncMock(side_effect=TsjConfirmationLogWriteError("日志失败")),
        ) as persist, patches[6] as audit:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(f"/api/workpapers/{wp.id}/ai/tsj-review")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "AI 复核结果未能进入确认流程，请稍后重试"
    persist.assert_awaited_once()
    audit.assert_not_awaited(), "持久化失败不能记成已完成的复核审计"
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_tsj_review_rolls_back_unknown_persistence_failure():
    """服务层不持有事务：未知异常原样冒泡，由路由 rollback 并返回 503，不记成功审计。"""
    app, db, _user, wp, _wp_index = _app_and_dependencies()
    patches = _patch_success_chain(project_id=wp.project_id, log_id=uuid.uuid4())
    try:
        with patches[0], patches[1], patches[2], patches[3], patches[4], patch(
            "app.services.tsj_structured_output_service.process_review_response",
            new=AsyncMock(side_effect=RuntimeError("注入：flush 失败")),
        ) as persist, patches[6] as audit:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(f"/api/workpapers/{wp.id}/ai/tsj-review")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "AI 复核结果保存失败，请稍后重试"
    persist.assert_awaited_once()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_tsj_review_runs_workpaper_edit_gate_before_handler():
    """端点是写入确认流，未获目标底稿编辑权时不得先调用 LLM 或查询业务内容。"""
    app, db, _user, wp, _wp_index = _app_and_dependencies()
    try:
        with patch(
            "app.deps.authorize_wp_edit",
            new=AsyncMock(side_effect=HTTPException(status_code=403, detail="无底稿编辑权限")),
        ) as authorize, patch.object(settings, "WP_AI_SERVICE_ENABLED", True):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(f"/api/workpapers/{wp.id}/ai/tsj-review")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403, response.text
    authorize.assert_awaited_once()
    db.execute.assert_not_awaited(), "门禁必须在读取底稿、调用 LLM 和写日志前拒绝"


@pytest.mark.asyncio
async def test_tsj_review_rolls_back_when_response_contract_is_inconsistent():
    """服务已 flush 但 DTO 数量不一致时，路由必须 rollback，不能先 commit 后返 500。"""
    app, db, _user, wp, _wp_index = _app_and_dependencies()
    log_id = uuid.uuid4()
    patches = _patch_success_chain(project_id=wp.project_id, log_id=log_id)
    try:
        with patches[0], patches[1], patches[2], patches[3], patches[4], patch(
            "app.services.tsj_structured_output_service.process_review_response",
            new=AsyncMock(return_value=[]),
        ) as persist, patches[6] as audit:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(f"/api/workpapers/{wp.id}/ai/tsj-review")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500, response.text
    assert response.json()["detail"] == "AI 复核结果持久化数量不一致"
    persist.assert_awaited_once()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()
    audit.assert_not_awaited()
