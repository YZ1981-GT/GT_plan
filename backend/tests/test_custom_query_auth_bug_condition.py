"""Bug condition exploration test: custom-query authorization IDOR & cross-project write.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**

This test encodes the EXPECTED behavior after fix:
  - execute/batch-execute with invisible project_id → 403
  - cell-writeback without edit permission → 403
  - workpaper lookup must filter by project_id (no cross-project hit)

On UNFIXED code, these tests MUST FAIL — confirming the bugs exist.

Bug Condition:
  §5.12: execute/batch-execute have no project_id ∈ get_visible_project_ids check
  §5.13: cell-writeback has zero auth for workpaper module, wp lookup ignores project_id
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
st_non_admin_role = st.sampled_from(["manager", "auditor", "qc", "readonly"])
st_source = st.sampled_from([
    "trial_balance", "report", "workpaper:D2", "disclosure", "account_balance",
])
st_wp_code = st.sampled_from(["D2-1", "E1-1", "F3-1", "A1"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(role: str = "auditor", user_id=None):
    """Create a mock user object."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.username = f"test_{role}"
    mock_role = MagicMock()
    mock_role.value = role
    user.role = mock_role
    return user


# ---------------------------------------------------------------------------
# Property 1a: IDOR on execute — no visibility check exists
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    invisible_project_id=st_project_id,
    role=st_non_admin_role,
    source=st_source,
)
async def test_execute_rejects_invisible_project(
    invisible_project_id, role, source
):
    """Property 1a: Bug Condition — execute with invisible project_id must return 403.

    For any (user, project_id) where project_id NOT IN get_visible_project_ids(user),
    execute_query SHALL return 403 without executing any query or touching cache.

    **Validates: Requirements 1.1, 1.3**

    EXPECTED: This test FAILS on unfixed code (no visibility check exists).
    """
    from fastapi import HTTPException
    from app.routers.custom_query import execute_query

    user = _make_user(role=role)

    # Create a request body
    body = MagicMock()
    body.project_id = invisible_project_id
    body.source = source
    body.year = 2024
    body.filters = {}
    body.limit = 100

    response = MagicMock()
    response.headers = {}

    # Mock db — get_visible_project_ids will query db.execute().all()
    # User is non-admin so it queries ProjectUser — return empty (no projects visible)
    db = AsyncMock()
    mock_exec_result = MagicMock()
    mock_exec_result.all.return_value = []  # user sees no projects
    db.execute.return_value = mock_exec_result

    # Mock dependencies that execute_query calls internally:
    # - query_cache: make it miss so the query actually runs
    # - gin_index_monitor: not building
    # - the _query_* functions: return some data
    with patch("app.services.gin_index_monitor.is_index_building", return_value=False), \
         patch("app.services.query_cache.compute_cache_key", return_value="test_key"), \
         patch("app.services.query_cache.get_cached_result", new_callable=AsyncMock, return_value=None), \
         patch("app.services.query_cache.set_cached_result", new_callable=AsyncMock):

        # On UNFIXED code: execute_query will proceed to query dispatch and return data.
        # On FIXED code: it should raise HTTPException(403) BEFORE any query.
        try:
            result = await execute_query(body=body, response=response, db=db, current_user=user)
            # If we reach here, the endpoint did NOT raise 403 → BUG CONFIRMED
            got_403 = False
        except HTTPException as e:
            got_403 = (e.status_code == 403)
            if not got_403:
                raise  # unexpected error

    assert got_403, (
        f"BUG CONFIRMED: execute_query did NOT return 403 for invisible project! "
        f"User role={role}, project_id={invisible_project_id}. "
        f"The endpoint has no project visibility check — any logged-in user "
        f"can query any project's data (IDOR read)."
    )


# ---------------------------------------------------------------------------
# Property 1b: IDOR on batch-execute — no visibility check exists
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    invisible_project_id=st_project_id,
    role=st_non_admin_role,
)
async def test_batch_execute_rejects_invisible_project(
    invisible_project_id, role
):
    """Property 1b: Bug Condition — batch-execute with invisible project_id must return 403.

    For any (user, project_id) where project_id NOT IN get_visible_project_ids(user),
    batch_execute SHALL return 403 before executing any wp_code sub-query.

    **Validates: Requirements 1.2**

    EXPECTED: This test FAILS on unfixed code.
    """
    from fastapi import HTTPException
    from app.routers.custom_query import batch_execute

    user = _make_user(role=role)

    body = MagicMock()
    body.project_id = invisible_project_id
    body.wp_codes = ["D2-1"]
    body.year = 2024
    body.filters = {}
    body.sheet_name = None
    body.cell_range = None

    response = MagicMock()
    response.headers = {}

    db = AsyncMock()
    mock_exec_result = MagicMock()
    mock_exec_result.all.return_value = []  # user sees no projects
    db.execute.return_value = mock_exec_result

    with patch("app.services.gin_index_monitor.is_index_building", return_value=False):
        try:
            result = await batch_execute(body=body, response=response, db=db, current_user=user)
            got_403 = False
        except HTTPException as e:
            got_403 = (e.status_code == 403)
            if not got_403:
                raise

    assert got_403, (
        f"BUG CONFIRMED: batch_execute did NOT return 403 for invisible project! "
        f"User role={role}, project_id={invisible_project_id}. "
        f"The endpoint has no project visibility check (IDOR read)."
    )


# ---------------------------------------------------------------------------
# Property 1c: cell-writeback workpaper module zero auth
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    project_id=st_project_id,
    role=st_non_admin_role,
    wp_code=st_wp_code,
)
async def test_cell_writeback_rejects_no_edit_permission(
    project_id, role, wp_code
):
    """Property 1c: Bug Condition — cell-writeback (workpaper) without edit permission → 403.

    For any (user, project_id) where user has NO edit permission on project_id,
    cell_writeback SHALL return 403 without writing any data.

    **Validates: Requirements 1.4, 1.5**

    EXPECTED: This test FAILS on unfixed code because:
    - workpaper module has ZERO auth check (role check is only for non-workpaper)
    """
    from fastapi import HTTPException
    from app.routers.custom_query import cell_writeback

    user = _make_user(role=role)

    body = MagicMock()
    body.wp_code = wp_code
    body.sheet_name = "审定表"
    body.cell_ref = "B7"
    body.new_value = 12345.67
    body.module = "workpaper"
    # NOTE: On unfixed code, CellWritebackRequest has no project_id field.
    # After fix, project_id will be required. For now we set it as attribute.
    body.project_id = project_id

    response = MagicMock()
    response.headers = {}

    request = MagicMock()
    request.headers = {"X-File-Opened-At": "2024-01-01T00:00:00Z"}

    db = AsyncMock()
    # get_visible_project_ids will call db.execute().all() → return empty (no visibility)
    mock_exec_result = MagicMock()
    mock_exec_result.all.return_value = []  # user sees no projects
    db.execute.return_value = mock_exec_result

    # Mock snapshot_writer to not actually write
    with patch("app.services.custom_query.snapshot_writer.snapshot_writer") as mock_sw:
        mock_sw.write_cell = AsyncMock(return_value={"success": True, "updated_at": "2024-01-01T00:00:01Z", "old_value": None})

        try:
            result = await cell_writeback(body=body, response=response, request=request, db=db, current_user=user)
            got_403 = False
        except HTTPException as e:
            got_403 = (e.status_code == 403)
            if not got_403:
                raise

    assert got_403, (
        f"BUG CONFIRMED: cell_writeback (module=workpaper) did NOT return 403! "
        f"User role={role}, project_id={project_id}. "
        f"Workpaper module has ZERO authorization check — any logged-in user "
        f"can write to any project's workpaper."
    )


# ---------------------------------------------------------------------------
# Property 1d: Cross-project wp_code collision — SQL has no project_id filter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    project_a_id=st_project_id,
    project_b_id=st_project_id,
    wp_code=st_wp_code,
)
async def test_workpaper_lookup_ignores_project_id(
    project_a_id, project_b_id, wp_code
):
    """Property 1d: Bug Condition — workpaper lookup must filter by project_id.

    Current code: SELECT id FROM working_paper WHERE wp_code = :code LIMIT 1
    (no project_id filter → may hit wrong project's workpaper).

    **Validates: Requirements 1.6**

    EXPECTED: This test FAILS on unfixed code because the SQL has no project_id filter.
    """
    assume(project_a_id != project_b_id)

    from app.routers.custom_query import cell_writeback

    user = _make_user(role="manager")

    body = MagicMock()
    body.wp_code = wp_code
    body.sheet_name = "审定表"
    body.cell_ref = "B7"
    body.new_value = 12345.67
    body.module = "workpaper"
    body.project_id = project_a_id

    response = MagicMock()
    response.headers = {}
    request = MagicMock()
    request.headers = {"X-File-Opened-At": "2024-01-01T00:00:00Z"}

    db = AsyncMock()
    # Sequential calls to db.execute:
    # 1. get_visible_project_ids → .all() returns [(project_a_id,)]
    # 2. ProjectUser check → .scalar_one_or_none() returns member with edit
    # 3. workpaper lookup → .first() returns (wp_b_id,)
    wp_b_id = uuid.uuid4()

    visibility_result = MagicMock()
    visibility_result.all.return_value = [(uuid.UUID(project_a_id),)]

    permission_result = MagicMock()
    mock_member = MagicMock()
    mock_member.permission_level = MagicMock()
    mock_member.permission_level.value = "edit"
    permission_result.scalar_one_or_none.return_value = mock_member

    wp_lookup_result = MagicMock()
    wp_lookup_result.first.return_value = (wp_b_id,)

    db.execute.side_effect = [visibility_result, permission_result, wp_lookup_result]

    # Mock snapshot_writer
    with patch("app.services.custom_query.snapshot_writer.snapshot_writer") as mock_sw:
        mock_sw.write_cell = AsyncMock(return_value={"success": True, "updated_at": "2024-01-01T00:00:01Z", "old_value": None})

        try:
            await cell_writeback(body=body, response=response, request=request, db=db, current_user=user)
        except Exception:
            pass

    # Verify the SQL executed contains project_id in the query
    assert db.execute.called, "db.execute was never called"

    # The workpaper lookup is the THIRD db.execute call (after visibility + permission)
    # Find the call that contains "working_paper" in its SQL
    wp_lookup_sql = None
    for call in db.execute.call_args_list:
        sql_text = str(call[0][0])
        if "working_paper" in sql_text.lower():
            wp_lookup_sql = sql_text
            break

    assert wp_lookup_sql is not None, "No db.execute call found with 'working_paper' SQL"

    assert "project_id" in wp_lookup_sql.lower(), (
        f"BUG CONFIRMED: Workpaper lookup SQL does NOT filter by project_id! "
        f"SQL: {sql_text}. "
        f"This allows cross-project wp_code collision — "
        f"multiple projects with same {wp_code} may cause LIMIT 1 to hit "
        f"the wrong project's workpaper. "
        f"Expected: WHERE wp_code = :code AND project_id = :pid"
    )
