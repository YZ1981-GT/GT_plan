# Feature: editing-lock-v1-v2-consolidation, Property 10: force-acquire SSE 事件完整性
"""
Property 10: force-acquire SSE 事件完整性

For any resource_type='workpaper' 的 force-acquire 操作，系统应广播恰一个
event_type='editing_lock.force_acquired' 事件，且其 payload 同时包含
wp_id、resource_type='workpaper'、resource_id，满足 wp_id == resource_id == 源 wp_id::text。
非 workpaper resource_type → payload 不包含 wp_id 键。

**Validates: Requirements 5.1, 5.2**

使用 in-process ASGI httpx + mock event_bus 测试。
"""
import uuid

import pytest
import pytest_asyncio
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st
from unittest.mock import patch, MagicMock
from sqlalchemy import event as sa_event, select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# 确保所有模型注册（含 users 等被 FK 引用的表）
import app.models  # noqa: F401
from app.models.base import Base
from app.models.editing_lock_models import EditingLock

# SQLite 兼容 PG 类型
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

# hypothesis 调速: max_examples=3（加速本地迭代）
SETTINGS = settings(
    max_examples=3,
    deadline=30000,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)

# 独立 SQLite 引擎
_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_SessionFactory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@sa_event.listens_for(_engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=OFF")
    cursor.close()


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with _SessionFactory() as session:
        yield session


@pytest_asyncio.fixture
async def make_client(db_session):
    """返回一个工厂函数，传入 user_id 生成对应用户的 httpx client"""
    from tests._test_auth_helper import override_auth, FakeAuthUser
    from app.main import app

    async def _factory(user_id: uuid.UUID, username: str = "tester"):
        user = FakeAuthUser(user_id=user_id, username=username)
        return override_auth(app, db_session=db_session, user=user)

    yield _factory


async def _seed_working_paper(db_session, wp_id: uuid.UUID, project_id: uuid.UUID):
    """在 DB 中创建 WorkingPaper 记录以便 _resolve_project_id 查询。

    FK 已关闭(PRAGMA foreign_keys=OFF)。
    SQLAlchemy UUID type 在 SQLite 中以 32-char hex（无短横）存储。
    用 raw SQL 插入以避免 ORM 对 Date/Enum 类型的严格验证。
    """
    from sqlalchemy import text as sa_text
    from datetime import date

    wp_index_id = uuid.uuid4()

    # SQLite UUID 存储格式: 32 char hex (no hyphens)
    pid_hex = project_id.hex
    wpid_hex = wp_id.hex
    wpiid_hex = wp_index_id.hex

    # project
    await db_session.execute(
        sa_text(
            "INSERT OR IGNORE INTO projects (id, name, client_name, audit_period_start, audit_period_end, status) "
            "VALUES (:id, :name, :client, :start, :end, :status)"
        ),
        {
            "id": pid_hex,
            "name": "test_project",
            "client": "test_client",
            "start": "2025-01-01",
            "end": "2025-12-31",
            "status": "active",
        },
    )
    # wp_index
    await db_session.execute(
        sa_text(
            "INSERT OR IGNORE INTO wp_index (id, project_id, wp_code, wp_name) "
            "VALUES (:id, :pid, :code, :name)"
        ),
        {
            "id": wpiid_hex,
            "pid": pid_hex,
            "code": "D2",
            "name": "test_wp",
        },
    )
    # working_paper
    await db_session.execute(
        sa_text(
            "INSERT OR IGNORE INTO working_paper (id, project_id, wp_index_id, file_path, source_type, status, review_status) "
            "VALUES (:id, :pid, :wid, :fp, :st, :status, :rs)"
        ),
        {
            "id": wpid_hex,
            "pid": pid_hex,
            "wid": wpiid_hex,
            "fp": "/test/path",
            "st": "builtin_template",
            "status": "draft",
            "rs": "not_submitted",
        },
    )
    await db_session.commit()


# --------------------------------------------------------------------------
# Property 10: force-acquire SSE 事件完整性
# Feature: editing-lock-v1-v2-consolidation, Property 10: force-acquire SSE 事件完整性
# --------------------------------------------------------------------------


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_a_id=st.uuids(),
    holder_b_id=st.uuids(),
    wp_id=st.uuids(),
    project_id=st.uuids(),
)
async def test_force_acquire_workpaper_broadcasts_sse(
    db_session, make_client, holder_a_id, holder_b_id, wp_id, project_id
):
    """force-acquire for workpaper → broadcast_raw called once with correct payload fields"""
    assume(holder_a_id != holder_b_id)

    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    resource_id = str(wp_id)

    # 创建 WorkingPaper 记录使 _resolve_project_id 能解析 project_id
    await _seed_working_paper(db_session, wp_id, project_id)

    # holder_a 先获取锁
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200

    # holder_b force-acquire，mock event_bus singleton
    # 注意：router 内 `from app.services.event_bus import event_bus` 是懒导入
    # 因此需要 patch 模块级 singleton `app.services.event_bus.event_bus`
    mock_broadcast = MagicMock()
    with patch("app.services.event_bus.event_bus.broadcast_raw", mock_broadcast):
        async with await make_client(holder_b_id, "holder_b") as client_b:
            resp_b = await client_b.post(f"/api/editing-locks/workpaper/{resource_id}/force")
            assert resp_b.status_code == 200

    # broadcast_raw 必须被调用恰好一次
    mock_broadcast.assert_called_once()

    # 验证 payload 字段
    call_args = mock_broadcast.call_args
    event_type_arg = call_args[0][0]
    payload = call_args[0][1]

    assert event_type_arg == "editing_lock.force_acquired"
    # project_id 应匹配 WorkingPaper 所属 project
    assert payload["project_id"] == str(project_id)
    # resource_type = 'workpaper'
    assert payload["resource_type"] == "workpaper"
    # resource_id = wp_id
    assert payload["resource_id"] == resource_id
    # new_holder_id = holder_b
    assert payload["new_holder_id"] == str(holder_b_id)
    # previous_holder_id from result (holder_a)
    assert payload["previous_holder_id"] == str(holder_a_id)
    # workpaper 时必须有 wp_id == resource_id
    assert "wp_id" in payload
    assert payload["wp_id"] == resource_id


@pytest.mark.asyncio
@SETTINGS
@given(
    holder_a_id=st.uuids(),
    holder_b_id=st.uuids(),
    resource_id=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
        min_size=3,
        max_size=20,
    ),
)
async def test_force_acquire_non_workpaper_no_wp_id(
    db_session, make_client, holder_a_id, holder_b_id, resource_id
):
    """force-acquire for non-workpaper resource_type → payload should NOT have wp_id key"""
    assume(holder_a_id != holder_b_id)

    # 每次 hypothesis 迭代重建表
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # holder_a 先获取锁（resource_type='disclosure_note'）
    async with await make_client(holder_a_id, "holder_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/disclosure_note/{resource_id}")
        assert resp_a.status_code == 200

    # holder_b force-acquire，mock event_bus singleton
    mock_broadcast = MagicMock()
    with patch("app.services.event_bus.event_bus.broadcast_raw", mock_broadcast):
        async with await make_client(holder_b_id, "holder_b") as client_b:
            resp_b = await client_b.post(f"/api/editing-locks/disclosure_note/{resource_id}/force")
            assert resp_b.status_code == 200

    # broadcast_raw 必须被调用恰好一次
    mock_broadcast.assert_called_once()

    # 验证 payload 字段
    call_args = mock_broadcast.call_args
    event_type_arg = call_args[0][0]
    payload = call_args[0][1]

    assert event_type_arg == "editing_lock.force_acquired"
    # resource_type != 'workpaper' → payload 不应有 wp_id 键
    assert payload["resource_type"] == "disclosure_note"
    assert payload["resource_id"] == resource_id
    assert payload["new_holder_id"] == str(holder_b_id)
    assert payload["previous_holder_id"] == str(holder_a_id)
    # 关键断言：非 workpaper 不应有 wp_id 键
    assert "wp_id" not in payload


# --------------------------------------------------------------------------
# Unit Tests (known examples): force SSE payload 精确匹配
# Feature: editing-lock-v1-v2-consolidation
# **Validates: Requirements 5.1, 5.2**
# --------------------------------------------------------------------------

# Fixed UUIDs for deterministic unit tests
_HOLDER_A_ID = uuid.UUID("aaaaaaaa-1111-2222-3333-444444444444")
_HOLDER_B_ID = uuid.UUID("bbbbbbbb-5555-6666-7777-888888888888")
_WP_ID = uuid.UUID("cccccccc-9999-aaaa-bbbb-cccccccccccc")
_PROJECT_ID = uuid.UUID("dddddddd-eeee-ffff-0000-111111111111")
_DISCLOSURE_RESOURCE_ID = "disc-note-001"


@pytest.mark.asyncio
async def test_workpaper_force_acquire_exact_payload(db_session, make_client):
    """Known example: workpaper force-acquire broadcasts exact payload including project_id from WorkingPaper.

    Scenario: user A holds lock on workpaper, user B force-acquires.
    Verify broadcast_raw is called once with precise payload fields.

    **Validates: Requirements 5.1, 5.2**
    """
    # Setup: clean tables
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    resource_id = str(_WP_ID)

    # Seed WorkingPaper so _resolve_project_id can resolve project_id
    await _seed_working_paper(db_session, _WP_ID, _PROJECT_ID)

    # User A acquires the lock
    async with await make_client(_HOLDER_A_ID, "user_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/workpaper/{resource_id}")
        assert resp_a.status_code == 200, f"Acquire failed: {resp_a.text}"

    # User B force-acquires with mocked event_bus
    mock_broadcast = MagicMock()
    with patch("app.services.event_bus.event_bus.broadcast_raw", mock_broadcast):
        async with await make_client(_HOLDER_B_ID, "user_b") as client_b:
            resp_b = await client_b.post(f"/api/editing-locks/workpaper/{resource_id}/force")
            assert resp_b.status_code == 200, f"Force-acquire failed: {resp_b.text}"

    # Assert broadcast_raw called exactly once
    mock_broadcast.assert_called_once()

    # Extract call arguments
    call_args = mock_broadcast.call_args
    event_type_arg = call_args[0][0]
    payload = call_args[0][1]

    # Exact assertions on event type
    assert event_type_arg == "editing_lock.force_acquired"

    # Exact assertions on payload fields
    assert payload["project_id"] == str(_PROJECT_ID)
    assert payload["resource_type"] == "workpaper"
    assert payload["resource_id"] == resource_id
    assert payload["new_holder_id"] == str(_HOLDER_B_ID)
    assert payload["new_holder_name"] == "user_b"
    assert payload["previous_holder_id"] == str(_HOLDER_A_ID)

    # workpaper MUST have wp_id == resource_id (Requirement 5.2)
    assert "wp_id" in payload
    assert payload["wp_id"] == resource_id


@pytest.mark.asyncio
async def test_non_workpaper_force_acquire_no_wp_id_key(db_session, make_client):
    """Known example: non-workpaper (disclosure_note) force-acquire payload has NO wp_id key.

    Scenario: user A holds lock on disclosure_note, user B force-acquires.
    Verify payload does NOT contain wp_id (Requirement 5.2: non-workpaper SHALL omit wp_id).

    **Validates: Requirements 5.1, 5.2**
    """
    # Setup: clean tables
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # User A acquires lock on disclosure_note resource
    async with await make_client(_HOLDER_A_ID, "user_a") as client_a:
        resp_a = await client_a.post(f"/api/editing-locks/disclosure_note/{_DISCLOSURE_RESOURCE_ID}")
        assert resp_a.status_code == 200, f"Acquire failed: {resp_a.text}"

    # User B force-acquires with mocked event_bus
    mock_broadcast = MagicMock()
    with patch("app.services.event_bus.event_bus.broadcast_raw", mock_broadcast):
        async with await make_client(_HOLDER_B_ID, "user_b") as client_b:
            resp_b = await client_b.post(
                f"/api/editing-locks/disclosure_note/{_DISCLOSURE_RESOURCE_ID}/force"
            )
            assert resp_b.status_code == 200, f"Force-acquire failed: {resp_b.text}"

    # Assert broadcast_raw called exactly once
    mock_broadcast.assert_called_once()

    # Extract call arguments
    call_args = mock_broadcast.call_args
    event_type_arg = call_args[0][0]
    payload = call_args[0][1]

    # Exact assertions on event type
    assert event_type_arg == "editing_lock.force_acquired"

    # Exact assertions on payload fields
    assert payload["resource_type"] == "disclosure_note"
    assert payload["resource_id"] == _DISCLOSURE_RESOURCE_ID
    assert payload["new_holder_id"] == str(_HOLDER_B_ID)
    assert payload["new_holder_name"] == "user_b"
    assert payload["previous_holder_id"] == str(_HOLDER_A_ID)

    # KEY ASSERTION: non-workpaper MUST NOT have wp_id key (Requirement 5.2)
    assert "wp_id" not in payload, (
        f"Non-workpaper payload should NOT contain wp_id, but got: {payload}"
    )
