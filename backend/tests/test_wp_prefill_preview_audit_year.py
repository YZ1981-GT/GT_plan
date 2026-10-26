"""预填充预览 / 应用端点的审计年度门禁。

端点通过真实 ASGI HTTP 请求验证：
- 有项目年度时，两个端点都把统一年度传给预填充业务函数；
- 项目年度无法解析时，两个端点都在进入预填充业务前返回 422。

SQLite 测试用 ORM 解析器适配 ``fetch_project_audit_year`` 的 PostgreSQL SQL，
不伪造年度值；项目记录和底稿记录仍由真实 ORM 落库后再走 HTTP 路由。
"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import openpyxl
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, UserRole
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType
from app.routers import wp_prefill_preview as prefill_module
from app.services.project_audit_year import resolve_project_audit_year


# SQLite 不识别 PG JSONB；映射到 JSON，与同域 endpoint 测试保持一致。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


class _FakeAdmin:
    id = uuid.uuid4()
    role = UserRole.admin
    email = "prefill-year-test@example.com"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _seed_project_and_workpaper(
    db: AsyncSession,
    tmp_path: Path,
    *,
    audit_year: int | None,
) -> tuple[uuid.UUID, uuid.UUID]:
    project_id = uuid.uuid4()
    project = Project(
        id=project_id,
        name="预填充年度端点测试项目",
        client_name="预填充年度端点测试项目",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=_FakeAdmin.id,
        audit_year=audit_year,
        audit_period_start=None,
        audit_period_end=None,
        wizard_state=None,
    )
    db.add(project)
    await db.flush()

    wp_index = WpIndex(
        project_id=project_id,
        wp_code="PREFILL-YEAR",
        wp_name="预填充年度端点测试底稿",
    )
    db.add(wp_index)
    await db.flush()

    workbook_path = tmp_path / f"{project_id}.xlsx"
    workbook = openpyxl.Workbook()
    workbook.save(workbook_path)
    workbook.close()

    workpaper = WorkingPaper(
        project_id=project_id,
        wp_index_id=wp_index.id,
        file_path=str(workbook_path),
        source_type=WpSourceType.template,
        file_version=1,
    )
    db.add(workpaper)
    await db.commit()
    return project_id, workpaper.id


def _build_app(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    # SQLite 不支持 PG ``SET LOCAL``；跳过 RLS context 设置，但保留真实权限依赖链。
    async def _noop_rls(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.deps.set_rls_context", _noop_rls)
    monkeypatch.setattr("app.core.database.set_rls_context", _noop_rls)

    app = FastAPI()
    # 与 router_registry/workpaper.py 注册的生产 router 使用同一个 router 对象。
    app.include_router(prefill_module.router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeAdmin()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


async def _sqlite_fetch_project_audit_year(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> int | None:
    """在 SQLite 测试中执行同一 canonical ORM 年度解析。"""
    project = await db.get(Project, project_id)
    return resolve_project_audit_year(project) if project is not None else None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "request_body"),
    [("preview", None), ("apply", {"accepted_cells": []})],
)
async def test_prefill_endpoints_pass_resolved_year_to_business_logic(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    request_body: dict | None,
):
    """年度已设置时，preview/apply 均使用项目年度而非日历或写死值。"""
    project_id, wp_id = await _seed_project_and_workpaper(
        db_session, tmp_path, audit_year=2024
    )
    monkeypatch.setattr(
        prefill_module,
        "fetch_project_audit_year",
        _sqlite_fetch_project_audit_year,
    )

    from app.services import prefill_engine

    observed_years: list[int] = []
    real_prefill = prefill_engine.prefill_workpaper_real

    async def _observe_prefill(db, pid, year, workpaper_id):
        observed_years.append(year)
        return await real_prefill(db, pid, year, workpaper_id)

    monkeypatch.setattr(prefill_engine, "prefill_workpaper_real", _observe_prefill)
    app = _build_app(db_session, monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/projects/{project_id}/working-papers/{wp_id}/prefill/{operation}",
            json=request_body,
        ) if request_body is not None else await client.post(
            f"/api/projects/{project_id}/working-papers/{wp_id}/prefill/{operation}"
        )

    assert response.status_code == 200, response.text
    assert observed_years == [2024]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "request_body"),
    [("preview", None), ("apply", {"accepted_cells": []})],
)
async def test_prefill_endpoints_return_422_without_entering_business_logic(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    request_body: dict | None,
):
    """年度五级来源均为空时，两个端点都在预填充前失败且不调用业务函数。"""
    project_id, wp_id = await _seed_project_and_workpaper(
        db_session, tmp_path, audit_year=None
    )
    monkeypatch.setattr(
        prefill_module,
        "fetch_project_audit_year",
        _sqlite_fetch_project_audit_year,
    )

    from app.services import prefill_engine

    business_calls: list[tuple[uuid.UUID, int, uuid.UUID]] = []

    async def _should_not_run(db, pid, year, workpaper_id):
        business_calls.append((pid, year, workpaper_id))
        return {"status": "ok", "formulas_filled": 0, "formulas_found": 0, "errors": []}

    monkeypatch.setattr(prefill_engine, "prefill_workpaper_real", _should_not_run)
    app = _build_app(db_session, monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/projects/{project_id}/working-papers/{wp_id}/prefill/{operation}",
            json=request_body,
        ) if request_body is not None else await client.post(
            f"/api/projects/{project_id}/working-papers/{wp_id}/prefill/{operation}"
        )

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "未设置审计年度，请先在项目基本信息中填写"
    assert business_calls == []
