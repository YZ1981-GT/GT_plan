"""``attachment_lineage.project_id`` 列未就绪（迁移 V227 未执行 / 失败）⇒ 附件三端点 503、溯源附件子源记 503。

spec formula-hub-integrity-closure 任务 3；需求 7.1；ADR-FHIC-13。

做法同任务 2：TestClient 真发请求，应用按生产注册只挂 ``attachment_lineage`` 与 ``lineage`` 两个 router，只替换
``get_current_user`` / ``get_db``（身份 = 夹具里的合伙人 + 本项目 edit 成员行）；``pg_tx`` 会话建在 TestClient 的
事件循环线程里（``client.portal``），夹具、请求、对账共用同一外层事务，用例结束回滚。

判据：
1. 正向对照（列存在）：POST / GET / DELETE 照常 200，溯源 ``errors`` 为空且附件子源取到关联行。
2. 回滚事务内按 R227 删列、清缓存后：三端点 503 ``ATTACHMENT_LINEAGE_MIGRATION_PENDING``；溯源 200、
   ``attachments`` 为空、``errors`` 记附件子源 503；期间该连接上没有任何触达 ``attachment_lineage`` 的语句
   （就绪判定查 ``information_schema`` 除外），关联行原样（POST 没写入、DELETE 没删）。
3. 只缓存「已就绪」：未就绪时每次请求都重查；补回列后判定为就绪并缓存，之后不再查。
4. SQLite 分支（``PRAGMA table_info``）同口径；SQLite 内存库不缓存（非 PG 用例）。
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.routers.attachment_lineage as attachment_lineage_router
import app.routers.lineage as lineage_router
from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import PermissionLevel, ProjectUserRole, UserRole
from app.models.core import ProjectUser, User
from app.services import attachment_lineage_schema as schema
from tests.authz_world import assert_world_overrides, build_app
from tests.formula_hub._lineage_fixtures import R227, insert_lineage, lineage_state, make_attachment, make_project, replay
from tests.formula_hub._pg_harness import pg_tx_session

REF = "FH-T3-COL!B5"
PENDING = {"error_code": "ATTACHMENT_LINEAGE_MIGRATION_PENDING", "message": "附件溯源迁移 V227 未完成，请先执行迁移"}


@pytest.fixture(autouse=True)
def _fresh_schema_cache():
    schema.clear_lineage_schema_cache()
    yield
    schema.clear_lineage_schema_cache()


@dataclass
class Case:
    project_id: uuid.UUID
    attachment_id: uuid.UUID
    link_id: uuid.UUID
    user: User


async def _seed(session) -> Case:
    tag = uuid.uuid4().hex[:10]
    user = User(username=f"fh_lineage_{tag}", email=f"fh_lineage_{tag}@example.test",
                hashed_password="x", role=UserRole.partner)
    session.add(user)
    project_id = await make_project(session, "lineage_col")
    session.add(ProjectUser(project_id=project_id, user_id=user.id, role=ProjectUserRole.partner,
                            permission_level=PermissionLevel.edit))
    attachment_id = await make_attachment(session, project_id)
    link_id = await insert_lineage(session, attachment_id=attachment_id, target_ref=REF, project_id=project_id)
    await session.commit()  # pg_tx：只释放保存点
    return Case(project_id, attachment_id, link_id, user)


async def _links_of(session, attachment_id: uuid.UUID) -> dict[uuid.UUID, dict]:
    ids = (await session.execute(text("SELECT id FROM attachment_lineage WHERE attachment_id = :aid"),
                                 {"aid": attachment_id})).scalars().all()
    return await lineage_state(session, list(ids))


async def _alter(session, sql: str) -> None:
    await session.execute(text(sql))


@contextmanager
def _endpoint() -> Iterator[tuple[TestClient, AsyncSession, object]]:
    api = build_app(attachment_lineage_router.router, lineage_router.router)
    with TestClient(api) as client:
        with client.portal.wrap_async_context_manager(pg_tx_session()) as session:
            yield client, session, api


def _authenticate(api, session, user: User) -> None:
    async def _db():
        yield session

    async def _user():
        return user

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    assert_world_overrides(api)


@contextmanager
def _statements(session) -> Iterator[list[str]]:
    seen: list[str] = []

    def hook(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        seen.append(statement)

    connection = session.bind.sync_connection
    event.listen(connection, "before_cursor_execute", hook)
    try:
        yield seen
    finally:
        event.remove(connection, "before_cursor_execute", hook)


def _readiness_queries(statements: list[str]) -> list[str]:
    return [s for s in statements if "information_schema.columns" in s]


def _lineage_touches(statements: list[str]) -> list[str]:
    return [s for s in statements if "attachment_lineage" in s and "information_schema" not in s]


def _calls(client: TestClient, case: Case, delete_id: uuid.UUID) -> dict[str, object]:
    base = f"/api/attachments/{case.attachment_id}"
    return {
        "post": client.post(f"{base}/link", json={"target_type": "wp_cell", "target_ref": REF}),
        "get": client.get(f"{base}/links"),
        "delete": client.delete(f"{base}/link/{delete_id}"),
        "lineage": client.get(f"/api/projects/{case.project_id}/lineage",
                              params={"object_type": "wp_cell", "object_id": REF, "direction": "both"}),
    }


@pytest.mark.pg_only
def test_three_endpoints_and_lineage_subsource_return_503_when_column_missing():
    with _endpoint() as (client, session, api):
        case = client.portal.call(_seed, session)
        _authenticate(api, session, case.user)

        # 1. 正向对照：列存在 ⇒ 三端点照常，溯源附件子源取到关联行
        created = client.post(f"/api/attachments/{case.attachment_id}/link",
                              json={"target_type": "wp_cell", "target_ref": REF})
        assert created.status_code == 200, created.text
        listed = client.get(f"/api/attachments/{case.attachment_id}/links")
        assert listed.status_code == 200, listed.text
        assert {item["id"] for item in listed.json()} == {str(case.link_id), created.json()["id"]}
        removed = client.delete(f"/api/attachments/{case.attachment_id}/link/{created.json()['id']}")
        assert removed.status_code == 200, removed.text
        lineage = client.get(f"/api/projects/{case.project_id}/lineage",
                             params={"object_type": "wp_cell", "object_id": REF, "direction": "both"})
        assert lineage.status_code == 200, lineage.text
        assert lineage.json()["errors"] == []
        assert str(case.link_id) in {item["id"] for item in lineage.json()["attachments"]}

        # 2. 回滚事务内删列（R227）、清缓存 ⇒ 三端点 503、子源记 503，且不触达 attachment_lineage
        client.portal.call(replay, session, R227)
        schema.clear_lineage_schema_cache()
        before = client.portal.call(_links_of, session, case.attachment_id)
        with _statements(session) as statements:
            responses = _calls(client, case, case.link_id)
        after = client.portal.call(_links_of, session, case.attachment_id)

        # 3. 只缓存「已就绪」：未就绪每次重查；补回列后就绪并缓存
        with _statements(session) as pending_checks:
            pending_results = [client.portal.call(schema.lineage_project_column_ready, session) for _ in range(2)]
        client.portal.call(_alter, session, "ALTER TABLE attachment_lineage ADD COLUMN project_id uuid")
        with _statements(session) as ready_checks:
            ready_results = [client.portal.call(schema.lineage_project_column_ready, session) for _ in range(2)]

    for name in ("post", "get", "delete"):
        response = responses[name]
        assert response.status_code == 503, (name, response.text)
        assert response.json()["detail"] == PENDING, name
    lineage = responses["lineage"]
    assert lineage.status_code == 200, lineage.text
    assert lineage.json()["attachments"] == []
    assert lineage.json()["errors"] == [{"source": "attachments", "status": 503, **PENDING}]
    assert _lineage_touches(statements) == [], _lineage_touches(statements)
    assert len(_readiness_queries(statements)) == 4, statements  # 四个请求各判定一次，未就绪不缓存
    assert before and after == before  # 关联行原样：POST 没写入、DELETE 没删

    assert pending_results == [False, False] and len(_readiness_queries(pending_checks)) == 2
    assert ready_results == [True, True] and len(_readiness_queries(ready_checks)) == 1


async def test_sqlite_branch_reads_pragma_and_caches_only_ready(tmp_path):
    statements: list[str] = []
    for url in ("sqlite+aiosqlite:///:memory:", f"sqlite+aiosqlite:///{(tmp_path / 'lineage.db').as_posix()}"):
        engine = create_async_engine(url)
        event.listen(engine.sync_engine, "before_cursor_execute",
                     lambda _c, _cur, statement, *_rest: statements.append(statement))
        try:
            async with AsyncSession(engine) as session:
                await session.execute(text("CREATE TABLE attachment_lineage (id TEXT PRIMARY KEY, attachment_id TEXT)"))
                statements.clear()
                assert [await schema.lineage_project_column_ready(session) for _ in range(2)] == [False, False]
                assert sum("PRAGMA table_info(attachment_lineage)" in s for s in statements) == 2
                await session.execute(text("ALTER TABLE attachment_lineage ADD COLUMN project_id TEXT"))
                statements.clear()
                assert [await schema.lineage_project_column_ready(session) for _ in range(2)] == [True, True]
                pragma_calls = sum("PRAGMA table_info(attachment_lineage)" in s for s in statements)
                # 内存库每个引擎各是一个库、URL 却相同 ⇒ 不缓存；文件库只缓存「已就绪」⇒ 只查一次
                assert pragma_calls == (2 if url.endswith(":memory:") else 1), (url, statements)
        finally:
            await engine.dispose()
