"""Preservation property tests: legitimate same-project access unchanged.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

These tests capture BASELINE behavior on unfixed code for cases where
the bug condition does NOT hold (legitimate access). They must PASS both
before and after the fix to confirm no regressions.

Preservation = when NOT isBugCondition(X), the behavior must remain identical.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

st_project_id = st.uuids().map(str)
st_source = st.sampled_from([
    "trial_balance", "report", "workpaper:D2", "disclosure", "account_balance",
])
st_wp_code = st.sampled_from(["D2-1", "E1-1", "F3-1", "A1"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(role: str = "admin", user_id=None):
    """Create a mock user object."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.username = f"test_{role}"
    mock_role = MagicMock()
    mock_role.value = role
    user.role = mock_role
    return user


def _mock_db_for_admin(project_id: str):
    """Create a mock db that passes visibility for admin (returns all projects)."""
    db = AsyncMock()
    # admin path in get_visible_project_ids queries Project.id → .all() returns project list
    mock_exec_result = MagicMock()
    mock_exec_result.all.return_value = [(uuid.UUID(project_id),)]
    db.execute.return_value = mock_exec_result
    # OwnershipGuard.assert_target_accessible 成功路径会调用 set_rls_context(db, pid)，
    # 后者读取 db.get_bind().dialect.name。真实 AsyncSession.get_bind() 是同步返回；
    # AsyncMock 默认会把 get_bind() 变成协程 → set_rls_context 取 .dialect 抛错。
    # 用同步 MagicMock 提供 sqlite dialect 使 set_rls_context 早返回（跳过 SET LOCAL）。
    _bind = MagicMock()
    _bind.dialect.name = "sqlite"
    db.get_bind = MagicMock(return_value=_bind)
    return db


# ---------------------------------------------------------------------------
# Property 2a: Admin/partner visibility — sees all projects (3.6)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    project_id=st_project_id,
    source=st_source,
)
async def test_admin_execute_returns_result(project_id, source):
    """Property 2a: Preservation — admin user on any project returns query results.

    Admin/partner are never subject to visibility restriction (get_visible_project_ids
    returns all projects for them). Their execute calls must continue to work.

    **Validates: Requirements 3.1, 3.6**

    EXPECTED: This test PASSES on both unfixed and fixed code.
    """
    from app.routers.custom_query import execute_query

    user = _make_user(role="admin")

    body = MagicMock()
    body.project_id = project_id
    body.source = source
    body.year = 2024
    body.filters = {}
    body.limit = 100

    response = MagicMock()
    response.headers = {}

    db = _mock_db_for_admin(project_id)

    with patch("app.services.gin_index_monitor.is_index_building", return_value=False), \
         patch("app.services.query_cache.compute_cache_key", return_value="test_key"), \
         patch("app.services.query_cache.get_cached_result", new_callable=AsyncMock, return_value=None), \
         patch("app.services.query_cache.set_cached_result", new_callable=AsyncMock):

        # Admin should always get a result (not 403)
        result = await execute_query(body=body, response=response, db=db, current_user=user)

        # Result should be a dict with rows/columns/total structure (possibly with error if source unknown)
        assert isinstance(result, dict), (
            f"Admin execute should return a dict result, got {type(result)}"
        )


# ---------------------------------------------------------------------------
# Property 2b: Partner visibility — same as admin (3.6)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    project_id=st_project_id,
    source=st_source,
)
async def test_partner_execute_returns_result(project_id, source):
    """Property 2b: Preservation — partner user on any project returns query results.

    **Validates: Requirements 3.6**

    EXPECTED: This test PASSES on both unfixed and fixed code.
    """
    from app.routers.custom_query import execute_query

    user = _make_user(role="partner")

    body = MagicMock()
    body.project_id = project_id
    body.source = source
    body.year = 2024
    body.filters = {}
    body.limit = 100

    response = MagicMock()
    response.headers = {}

    db = _mock_db_for_admin(project_id)  # partner also gets all projects

    with patch("app.services.gin_index_monitor.is_index_building", return_value=False), \
         patch("app.services.query_cache.compute_cache_key", return_value="test_key"), \
         patch("app.services.query_cache.get_cached_result", new_callable=AsyncMock, return_value=None), \
         patch("app.services.query_cache.set_cached_result", new_callable=AsyncMock):

        result = await execute_query(body=body, response=response, db=db, current_user=user)
        assert isinstance(result, dict), (
            f"Partner execute should return a dict result, got {type(result)}"
        )


# ---------------------------------------------------------------------------
# Property 2c: Cache HIT behavior preserved (3.2)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    project_id=st_project_id,
    source=st_source,
)
async def test_cache_hit_returns_cached_data(project_id, source):
    """Property 2c: Preservation — Redis cache HIT returns cached data with X-Cache header.

    When a query hits cached results, the response must include X-Cache: HIT
    and return the cached data directly.

    **Validates: Requirements 3.2**

    EXPECTED: This test PASSES on both unfixed and fixed code.

    🔴 2026-08-23（advanced-query-hardening-wiring-closure R3.1）缓存**位置**变更：
    改造前 router 自己做一层 Redis 缓存（`query_cache.compute_cache_key` +
    `get_cached_result`），与编排器内部的缓存构成**两条并行缓存路径**。执行链收敛到
    `ExecuteCompatibilityAdapter` 后，缓存统一由 `QueryOrchestrator` 经
    `CanonicalRedisQueryCache` 负责，router 只依据结果的 `cache_hit` 落 X-Cache 头。

    故本测试改为 mock **新位置**的缓存层；断言的行为不变 ——
    命中缓存时返回缓存数据、且响应带 `X-Cache: HIT`。
    """
    from app.routers.custom_query import execute_query
    from app.services.query_cache import CanonicalRedisQueryCache

    user = _make_user(role="admin")
    # 缓存里存的是 QueryResult.to_payload() 形态
    cached_payload = {
        "rows": [{"col1": "val1"}],
        "columns": [{"key": "col1", "title": "col1"}],
        "total": 1,
        "limit": 100,
        "offset": 0,
        "warnings": [],
    }

    body = MagicMock()
    body.project_id = project_id
    body.source = source
    body.year = 2024
    body.filters = {}
    body.limit = 100

    response = MagicMock()
    response.headers = {}

    db = _mock_db_for_admin(project_id)

    with patch("app.services.gin_index_monitor.is_index_building", return_value=False), \
         patch.object(
             CanonicalRedisQueryCache, "get_or_compute",
             new_callable=AsyncMock, return_value=cached_payload,
         ):
        result = await execute_query(body=body, response=response, db=db, current_user=user)

        # 命中缓存 → 返回缓存中的行与总数（不触达取数层）
        assert result["rows"] == cached_payload["rows"], (
            f"Cache hit should return cached rows. Got: {result}"
        )
        assert result["total"] == 1, f"Cache hit should return cached total. Got: {result}"
        assert result["cache_hit"] is True, f"cache_hit 应为 True。Got: {result}"
        assert response.headers.get("X-Cache") == "HIT", (
            f"Cache hit should set X-Cache: HIT header. Got: {response.headers}"
        )


# ---------------------------------------------------------------------------
# Property 2d: cell-writeback optimistic lock 409 preserved (3.4)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(wp_code=st_wp_code)
async def test_cell_writeback_optimistic_lock_conflict(wp_code):
    """Property 2d: Preservation — cell-writeback with stale X-File-Opened-At returns 409.

    When the workpaper's updated_at is newer than the client's opened_at,
    the endpoint must return 409 conflict response.

    **Validates: Requirements 3.4**

    EXPECTED: This test PASSES on both unfixed and fixed code.
    """
    from app.routers.custom_query import cell_writeback
    from app.services.custom_query.snapshot_writer import WritebackConflict

    user = _make_user(role="admin")
    project_id = str(uuid.uuid4())

    body = MagicMock()
    body.wp_code = wp_code
    body.sheet_name = "审定表"
    body.cell_ref = "B7"
    body.new_value = 12345.67
    body.module = "workpaper"
    body.project_id = project_id

    response = MagicMock()
    response.headers = {}
    request = MagicMock()
    request.headers = {"X-File-Opened-At": "2024-01-01T00:00:00Z"}

    # db mock: admin visibility check + wp lookup
    db = AsyncMock()
    visibility_result = MagicMock()
    visibility_result.all.return_value = [(uuid.UUID(project_id),)]

    wp_lookup_result = MagicMock()
    wp_lookup_result.first.return_value = (uuid.uuid4(),)

    db.execute.side_effect = [visibility_result, wp_lookup_result]

    # Mock snapshot_writer to raise WritebackConflict
    conflict = WritebackConflict(
        latest_updated_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        latest_editor="other_user",
    )

    with patch("app.services.custom_query.snapshot_writer.snapshot_writer") as mock_sw:
        mock_sw.write_cell = AsyncMock(side_effect=conflict)

        result = await cell_writeback(
            body=body, response=response, request=request, db=db, current_user=user
        )

        # Should return 409 response with conflict info
        assert hasattr(result, 'status_code') and result.status_code == 409, (
            f"Optimistic lock conflict should return 409 Response. Got: {result}"
        )


# ---------------------------------------------------------------------------
# Property 2e: tb / adj / report 写回已删除 → 请求模型 422，写入方不被调用
# （advanced-query-linkage-closure 任务 13，ADR-AQL-02。原用例断言「tb 模块写非 G 列 → 403」，
#  而 tb 写入实现绕开了 TB 发布门、已删除；保留的契约是：这三个模块在请求层即被拒收）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("module", ["tb", "adj", "report"])
async def test_removed_writeback_modules_rejected_with_422(module, monkeypatch):
    """Property 2e: cell-writeback 的 module=tb / adj / report → 422（真发 HTTP 请求），写入方零调用。

    **Validates: Requirements 3.7**（advanced-query-linkage-closure R4.1）
    """
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import custom_query
    from app.services.custom_query.snapshot_writer import snapshot_writer
    from tests.authz_world import build_app

    calls: list[dict] = []

    async def _spy(**kwargs):
        calls.append(kwargs)
        return {"success": True, "updated_at": None, "old_value": None}

    monkeypatch.setattr(snapshot_writer, "write_cell", _spy)
    api = build_app(custom_query.router)
    user = _make_user(role="admin")

    async def _user():
        return user

    async def _db():
        yield AsyncMock()

    api.dependency_overrides[get_current_user] = _user
    api.dependency_overrides[get_db] = _db
    body = {
        "project_id": str(uuid.uuid4()), "wp_code": "TB-001", "sheet_name": "试算表", "cell_ref": "G2",
        "new_value": 999.99, "module": module,
    }
    async with AsyncClient(transport=ASGITransport(app=api), base_url="http://aql-b4") as client:
        response = await client.post(
            "/api/custom-query/cell-writeback", json=body, headers={"X-File-Opened-At": "2024-01-01T00:00:00Z"},
        )

    assert response.status_code == 422, response.text
    errors = response.json()["detail"]
    assert any(err.get("loc", [None])[-1] == "module" for err in errors), errors
    assert calls == [], f"module={module} 被拒收前不应调用写入方：{calls}"
