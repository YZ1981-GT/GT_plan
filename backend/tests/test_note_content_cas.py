"""单体附注跨会话 CAS 与无变化保存去噪（2026-11-26 穿透复盘 P0/P2）。

SQLite 内存库 + 真 ORM + 真路由（门禁 / 合并锁 / Redis / EventBus 打桩）：
1. GET 下发 content_digest（按库中原始值，投影前）；
2. PUT 带 expected_digest 匹配 → 200，回传新 content_digest，事件发布；
3. expected_digest 过期（他人先保存）→ 409 NOTE_CONTENT_CONFLICT + current_digest + current 内容；
4. 缺省 expected_digest → 兼容旧调用（自动写入 / AI 写回）正常保存；
5. 内容无变化（同正文同表格）→ 200 no_change=true、不盖编辑时间、不发 NOTE_SECTION_SAVED；
6. status / guidance 变化仍算“变化”（盖章 + 发事件）。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.core.database import get_db
from app.deps import check_consol_lock, get_current_user
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectUserRole
from app.models.core import Project, ProjectUser, User
from app.models.report_models import DisclosureNote
from app.routers import disclosure_notes
from app.services.disclosure_mutation_coordinator import DisclosureMutationCoordinator

YEAR = 2025
SECTION = "四、会计期间"
OLD = datetime(2020, 1, 1, tzinfo=timezone.utc)


class _Actor:
    def __init__(self, uid):
        self.id = uid
        self.username = "tester"
        from app.models.core import UserRole
        self.role = UserRole.manager
        self.is_active = True


@pytest_asyncio.fixture
async def cas_env() -> AsyncGenerator[dict, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[User.__table__, Project.__table__, ProjectUser.__table__, DisclosureNote.__table__]))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ids = {k: uuid.uuid4() for k in ("me", "p", "note")}
    async with factory() as s:
        s.add(Project(id=ids["p"], name="甲_2025", client_name="甲公司", template_type="soe",
                      report_scope="standalone", status=ProjectStatus.execution))
        await s.flush()
        s.add_all([
            ProjectUser(project_id=ids["p"], user_id=ids["me"], role=ProjectUserRole.auditor,
                        permission_level=PermissionLevel.edit),
            DisclosureNote(id=ids["note"], project_id=ids["p"], year=YEAR, note_section=SECTION,
                           section_title="会计期间", text_content="<p>旧</p>", updated_at=OLD, updated_by=None),
        ])
        await s.commit()

    app = FastAPI()
    app.include_router(disclosure_notes.router)

    async def _override_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: _Actor(ids["me"])
    app.dependency_overrides[check_consol_lock] = lambda: None
    published: list = []
    with patch("app.services.note_edit_gate.assert_note_edit_access", new=AsyncMock()), \
            patch("app.routers.disclosure_notes.assert_note_edit_access", new=AsyncMock()), \
            patch.object(DisclosureMutationCoordinator, "_redis", new=AsyncMock(return_value=None)), \
            patch("app.services.event_bus.event_bus.publish", new=AsyncMock(side_effect=lambda p: published.append(p))):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield {"client": client, "ids": ids, "factory": factory, "published": published}
    await engine.dispose()


async def _stamp(ctx: dict) -> tuple[datetime, uuid.UUID | None]:
    async with ctx["factory"]() as db:
        note = await db.get(DisclosureNote, ctx["ids"]["note"])
        at = note.updated_at
        if at is not None and at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)  # SQLite 返回 naive，统一为 UTC
        return at, note.updated_by


def _note_url(ctx: dict) -> str:
    return f"/api/disclosure-notes/{ctx['ids']['note']}"


def _unwrap(resp_json: dict) -> dict:
    return resp_json.get("data", resp_json) if isinstance(resp_json, dict) else resp_json


def _detail_url(ctx: dict) -> str:
    return f"/api/disclosure-notes/{ctx['ids']['p']}/{YEAR}/{SECTION}"


class TestContentCas:
    @pytest.mark.asyncio
    async def test_get_detail_returns_digest_then_matching_put_succeeds(self, cas_env):
        detail = _unwrap((await cas_env["client"].get(_detail_url(cas_env))).json())
        digest = detail["content_digest"]
        assert isinstance(digest, str) and len(digest) == 16

        resp = await cas_env["client"].put(
            _note_url(cas_env), json={"text_content": "<p>新</p>", "expected_digest": digest},
            headers={"X-Mutation-Id": "cas-1"})
        assert resp.status_code == 200, resp.text
        body = _unwrap(resp.json())
        assert body["no_change"] is False
        assert isinstance(body["content_digest"], str) and len(body["content_digest"]) == 16, (
            f"保存响应必须回传 16 位新摘要（下次保存的起点），得到 {body.get('content_digest')!r}")
        assert body["content_digest"] != digest, "保存后必须回传新摘要（下一次保存的起点）"
        assert body["event_delivery"] == "published"

    @pytest.mark.asyncio
    async def test_stale_digest_returns_409_with_current(self, cas_env):
        detail = _unwrap((await cas_env["client"].get(_detail_url(cas_env))).json())
        stale = detail["content_digest"]
        # 他人先保存：摘要推进。
        await cas_env["client"].put(_note_url(cas_env), json={"text_content": "<p>他人</p>"},
                                    headers={"X-Mutation-Id": "other-1"})
        resp = await cas_env["client"].put(
            _note_url(cas_env), json={"text_content": "<p>我</p>", "expected_digest": stale},
            headers={"X-Mutation-Id": "cas-2"})
        assert resp.status_code == 409, resp.text
        detail_body = resp.json()["detail"]
        assert detail_body["error_code"] == "NOTE_CONTENT_CONFLICT"
        assert detail_body["current_digest"]
        assert detail_body["current"]["text_content"] == "<p>他人</p>"
        # 冲突请求不落库：正文仍是他人保存的版本。
        async with cas_env["factory"]() as db:
            note = await db.get(DisclosureNote, cas_env["ids"]["note"])
            assert note.text_content == "<p>他人</p>"

    @pytest.mark.asyncio
    async def test_missing_digest_keeps_legacy_semantics(self, cas_env):
        """自动写入 / AI 写回不带 digest：照旧保存，不 409。"""
        resp = await cas_env["client"].put(_note_url(cas_env), json={"text_content": "<p>自动</p>"},
                                           headers={"X-Mutation-Id": "auto-1"})
        assert resp.status_code == 200, resp.text
        assert _unwrap(resp.json())["event_delivery"] == "published"

    @pytest.mark.asyncio
    async def test_replay_with_same_digest_and_mutation_id_is_idempotent(self, cas_env):
        detail = _unwrap((await cas_env["client"].get(_detail_url(cas_env))).json())
        payload = {"text_content": "<p>重试</p>", "expected_digest": detail["content_digest"]}
        first = await cas_env["client"].put(_note_url(cas_env), json=payload, headers={"X-Mutation-Id": "retry-1"})
        replay = await cas_env["client"].put(_note_url(cas_env), json=payload, headers={"X-Mutation-Id": "retry-1"})
        assert first.status_code == replay.status_code == 200
        assert _unwrap(replay.json())["mutation_id"] == "retry-1"


class TestNoChangeDedup:
    @pytest.mark.asyncio
    async def test_identical_save_is_no_change_no_stamp_no_event(self, cas_env):
        cas_env["published"].clear()
        detail = _unwrap((await cas_env["client"].get(_detail_url(cas_env))).json())
        resp = await cas_env["client"].put(
            _note_url(cas_env),
            json={"text_content": detail["text_content"], "table_data": detail["table_data"]},
            headers={"X-Mutation-Id": "nc-1"})
        assert resp.status_code == 200, resp.text
        body = _unwrap(resp.json())
        assert body["no_change"] is True
        assert body["event_delivery"] == "skipped"
        assert await _stamp(cas_env) == (OLD, None), "无变化不得盖编辑时间"
        assert cas_env["published"] == [], "无变化不得发 NOTE_SECTION_SAVED"

    @pytest.mark.asyncio
    async def test_status_change_still_counts(self, cas_env):
        """text/table 不变但 status 变：仍盖章 + 发事件（状态推进是业务变化）。"""
        since = datetime.now(timezone.utc) - timedelta(seconds=1)
        detail = _unwrap((await cas_env["client"].get(_detail_url(cas_env))).json())
        resp = await cas_env["client"].put(
            _note_url(cas_env),
            json={"text_content": detail["text_content"], "status": "confirmed"},
            headers={"X-Mutation-Id": "st-1"})
        assert resp.status_code == 200, resp.text
        assert _unwrap(resp.json())["no_change"] is False
        at, by = await _stamp(cas_env)
        assert at > since and by == cas_env["ids"]["me"]
