"""合并附注内容摘要 CAS 的真实服务/ASGI 回归。

测试直接调用生产 ``save_scoped_note_record``，并通过真实 FastAPI 路由、
SQLite ORM 会话和响应包装中间件验证 R2 对外契约。
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import tests.conftest  # noqa: F401  注册模型与 SQLite 方言补丁
from app.core.database import get_db
from app.deps import get_current_user
from app.middleware.response import ResponseWrapperMiddleware
from app.models.base import Base, ProjectStatus, UserRole
from app.models.consol_note_data_models import ConsolNoteData
from app.models.core import Project
from app.services.consol_node_scope import digest_of
from tests.test_consol_push import Y, db, factory, group  # noqa: F401  复用真实合并公式夹具


@pytest_asyncio.fixture
async def cas_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@dataclass
class _Actor:
    id: uuid.UUID
    username: str
    role: UserRole = UserRole.admin
    is_active: bool = True
    is_deleted: bool = False


def _project(label: str) -> Project:
    return Project(
        id=uuid.uuid4(),
        name=f"CAS-{label}",
        client_name=f"CAS-{label}",
        status=ProjectStatus.execution,
        audit_year=Y,
        report_scope="consolidated",
    )


def _app_for(session: AsyncSession, actor: _Actor | None = None) -> FastAPI:
    from app.routers.consol_note_sections import router

    app = FastAPI()
    app.add_middleware(ResponseWrapperMiddleware)
    app.include_router(router)
    current = actor or _Actor(uuid.uuid4(), "consol-note-cas-admin")

    async def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: current
    return app


def _unwrap(body: dict) -> dict:
    assert body.get("code") == 200, body
    assert body.get("message") == "success", body
    assert isinstance(body.get("data"), dict), body
    return body["data"]


def _note_path(project: Project) -> str:
    return f"/api/consol-note-sections/data/{project.id}/{Y}/五-1-1"


@pytest.mark.asyncio
async def test_http_get_put_digest_and_conflict_use_real_orm_chain(cas_factory):
    project = _project("get-put")
    async with cas_factory() as session:
        session.add(project)
        await session.commit()
        app = _app_for(session)
        path = _note_path(project)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            empty = await client.get(path)
            assert empty.status_code == 200, empty.text
            empty_data = _unwrap(empty.json())
            assert empty_data["content"] == {}
            assert empty_data["data_digest"] is None

            first_payload = {"headers": ["项目", "金额"], "rows": [["现金", "1"]]}
            created = await client.put(
                path,
                json={"data": first_payload, "expected_digest": None},
            )
            assert created.status_code == 200, created.text
            created_data = _unwrap(created.json())
            first_digest = created_data["data_digest"]
            assert first_digest == digest_of(first_payload)
            assert created_data["node_key"] is None

            loaded = await client.get(path)
            assert loaded.status_code == 200, loaded.text
            loaded_data = _unwrap(loaded.json())
            assert loaded_data["content"] == first_payload
            assert loaded_data["data_digest"] == first_digest

            replacement = {"headers": ["项目", "金额"], "rows": [["现金", "2"]]}
            forced = await client.put(
                path,
                json={"data": replacement, "force_overwrite": True},
            )
            assert forced.status_code == 200, forced.text
            forced_data = _unwrap(forced.json())
            current_digest = forced_data["data_digest"]
            assert current_digest == digest_of(replacement)

            conflict = await client.put(
                path,
                json={
                    "data": {"headers": ["项目", "金额"], "rows": [["现金", "3"]]},
                    "expected_digest": first_digest,
                },
            )
            assert conflict.status_code == 409, conflict.text
            detail = conflict.json()["detail"]
            assert detail["error_code"] == "CONSOL_NOTE_CONFLICT"
            assert detail["current_digest"] == current_digest
            assert detail["last_write_source"] == "manual"
            assert detail["updated_at"]

            after = await client.get(path)
            after_data = _unwrap(after.json())
            assert after_data["content"] == replacement
            assert after_data["data_digest"] == current_digest

        stored = (
            await session.execute(
                sa.select(ConsolNoteData).where(
                    ConsolNoteData.project_id == project.id,
                    ConsolNoteData.year == Y,
                    ConsolNoteData.section_id == "五-1-1",
                    ConsolNoteData.node_key.is_(None),
                )
            )
        ).scalar_one()
        assert stored.data == replacement
        assert digest_of(stored) == current_digest


@pytest.mark.asyncio
async def test_http_requires_exactly_one_digest_option(cas_factory):
    project = _project("validation")
    async with cas_factory() as session:
        session.add(project)
        await session.commit()
        app = _app_for(session)
        path = _note_path(project)
        payload = {"data": {"rows": [["现金", "1"]]}}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            missing = await client.put(path, json=payload)
            assert missing.status_code == 428, missing.text
            assert missing.json()["detail"]["error_code"] == "CONSOL_NOTE_DIGEST_REQUIRED"

            both = await client.put(
                path,
                json={**payload, "expected_digest": None, "force_overwrite": True},
            )
            assert both.status_code == 422, both.text
            assert both.json()["detail"]["error_code"] == "CONSOL_NOTE_SAVE_INVALID"

            for invalid in ("ABC", "0" * 63, "A" * 64, 123):
                response = await client.put(
                    path,
                    json={**payload, "expected_digest": invalid},
                )
                assert response.status_code == 422, response.text
                assert response.json()["detail"]["error_code"] == "CONSOL_NOTE_SAVE_INVALID"

            false_force = await client.put(
                path,
                json={**payload, "force_overwrite": False},
            )
            assert false_force.status_code == 422, false_force.text
            assert false_force.json()["detail"]["error_code"] == "CONSOL_NOTE_SAVE_INVALID"

        assert (
            await session.execute(
                sa.select(sa.func.count()).select_from(ConsolNoteData).where(
                    ConsolNoteData.project_id == project.id,
                )
            )
        ).scalar_one() == 0


@pytest.mark.asyncio
async def test_http_lock_and_scope_errors_remain_unchanged(cas_factory):
    project = _project("errors")
    async with cas_factory() as session:
        session.add(project)
        await session.commit()
        app = _app_for(session)
        path = _note_path(project)
        payload = {"data": {"rows": [["现金", "1"]]}, "force_overwrite": True}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            current = await client.put(path, json=payload)
            assert current.status_code == 200, current.text

            project.consol_lock = True
            await session.commit()
            locked = await client.put(path, json={**payload, "data": {"rows": [["现金", "2"]]}})
            assert locked.status_code == 423, locked.text
            assert locked.json()["detail"] == "项目已被合并锁定，无法修改"

            project.consol_lock = False
            await session.commit()
            wrong_year = await client.put(
                f"/api/consol-note-sections/data/{project.id}/{Y - 1}/五-1-1",
                json=payload,
            )
            assert wrong_year.status_code == 400, wrong_year.text
            assert wrong_year.json()["detail"] == f"请求年度 {Y - 1} 与项目有效审计年度 {Y} 不一致"


@pytest.mark.asyncio
async def test_fill_by_formula_returns_digest_from_persisted_production_data(db, group):
    """公式填入走真实合并上下文、公式种子和 ORM 写入，并回传同源摘要。"""
    from app.services.consol_note_formula_service import consol_note_tables
    from app.services.consol_report_service import generate_consol_reports_sync

    project = group["G"]
    await generate_consol_reports_sync(db, project.id, Y)
    await db.commit()

    table = next(item for item in consol_note_tables("soe") if item["section_id"] == "五-1-1")
    saved_data = {
        "headers": deepcopy(table["headers"]),
        "rows": deepcopy(table["rows"]),
        "manual_cells": [{"row": 0, "col": 1}],
    }
    original_manual_value = saved_data["rows"][0][1]
    db.add(ConsolNoteData(
        project_id=project.id,
        year=Y,
        section_id="五-1-1",
        node_key=None,
        data=saved_data,
        is_stale=True,
    ))
    await db.commit()

    app = _app_for(db)
    path = f"/api/consol-note-sections/fill-by-formula/{project.id}/{Y}/五-1-1"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path)

    assert response.status_code == 200, response.text
    result = _unwrap(response.json())
    assert isinstance(result.get("data"), dict)
    assert result["data_digest"] == digest_of(result["data"])
    assert result["data"]["rows"][0][1] == original_manual_value
    assert result["is_stale"] is False

    stored = (
        await db.execute(
            sa.select(ConsolNoteData).where(
                ConsolNoteData.project_id == project.id,
                ConsolNoteData.year == Y,
                ConsolNoteData.section_id == "五-1-1",
                ConsolNoteData.node_key.is_(None),
            )
        )
    ).scalar_one()
    assert stored.data == result["data"]
    assert digest_of(stored) == result["data_digest"]
