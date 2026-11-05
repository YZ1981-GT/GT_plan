"""账号「允许修改」：科目映射写接口与调整分录导入（spec citar-manual-edit-permission R2）。

SQLite 内存库 + 真实路由与真实项目鉴权链（只替换 ``get_db`` / ``get_current_user``）：
关闭开关的管理员账号 → 403（先于任何写入），映射表不动；开着的账号照常放行（对照，证明 403 来自开关而非鉴权）。
"""

from __future__ import annotations

import io
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.models.audit_platform_models import AccountMapping  # noqa: E402
from app.models.base import Base, UserRole  # noqa: E402
from app.models.core import Project, ProjectStatus, ProjectType, User  # noqa: E402
from app.routers.import_templates import router as import_router  # noqa: E402
from app.routers.mapping import router as mapping_router  # noqa: E402

P = uuid.UUID("00000000-0000-0000-0000-00000000e101")
ADMIN = uuid.UUID("00000000-0000-0000-0000-00000000e001")


class _Actor:
    def __init__(self, allow: bool) -> None:
        self.id = ADMIN
        self.role = UserRole.admin
        self.username = "admin-e"
        self.is_active = True
        self.allow_manual_edit = allow


@pytest_asyncio.fixture
async def env() -> AsyncGenerator[dict, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[User.__table__, Project.__table__, AccountMapping.__table__]))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add(Project(id=P, name="项目E", client_name="戊公司", project_type=ProjectType.annual,
                      status=ProjectStatus.execution, created_by=ADMIN))
        await s.commit()
    current = {"actor": _Actor(False)}
    app = FastAPI()
    app.include_router(mapping_router)
    app.include_router(import_router)

    async def _db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: current["actor"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"c": client, "f": factory, "allow": lambda v: current.update(actor=_Actor(v))}
    await engine.dispose()


async def _mapping_count(f) -> int:
    async with f() as s:
        return (await s.execute(sa.select(sa.func.count()).select_from(AccountMapping))).scalar_one()


@pytest.mark.asyncio
async def test_mapping_writes_and_adjustment_import_require_allow_manual_edit(env):
    c, f = env["c"], env["f"]
    one = {"original_account_code": "1001", "original_account_name": "库存现金", "standard_account_code": "1001"}
    calls = [
        ("POST", f"/api/projects/{P}/mapping", {"json": one}),
        ("PUT", f"/api/projects/{P}/mapping/{uuid.uuid4()}", {"json": {"standard_account_code": "1002"}}),
        ("POST", f"/api/projects/{P}/mapping/batch-confirm", {"json": [one]}),
        ("POST", f"/api/projects/{P}/mapping/auto-match", {"json": {"year": 2025}}),
        ("POST", f"/api/import-templates/adjustments/import?project_id={P}&year=2025",
         {"files": {"file": ("adj.xlsx", io.BytesIO(b"x"), "application/octet-stream")}}),
    ]
    for method, url, kw in calls:
        r = await c.request(method, url, **kw)
        assert r.status_code == 403 and "允许修改" in r.text, (method, url, r.status_code, r.text)
    assert await _mapping_count(f) == 0
    # 查看照常
    assert (await c.get(f"/api/projects/{P}/mapping")).status_code == 200

    # 对照：开着开关的同一账号能保存映射（403 来自开关，不是鉴权链）
    env["allow"](True)
    r = await c.post(f"/api/projects/{P}/mapping", json=one)
    assert r.status_code == 200, r.text
    assert await _mapping_count(f) == 1


def test_manual_edit_allowed_only_false_is_denied():
    """只有明确 False 才算关闭：内存里新建、尚未写库的 ORM User（列默认值写库时才生效，属性为 None）按允许。"""
    from app.services.manual_edit_permission import manual_edit_allowed

    transient = User(id=uuid.uuid4(), username="t", email="t@t.local", hashed_password="x", role=UserRole.auditor)
    assert transient.allow_manual_edit is None and manual_edit_allowed(transient) is True
    assert manual_edit_allowed(object()) is True
    assert manual_edit_allowed(_Actor(True)) is True
    assert manual_edit_allowed(_Actor(False)) is False
