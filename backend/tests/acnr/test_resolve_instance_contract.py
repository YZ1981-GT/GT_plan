"""Resolve-Instance 端点 API 契约基线测试 — Task 1 [Req-1, Req-3]

记录 GET /api/acnr/resolve-instance 公共端点当前返回值 baseline（3 场景）：
  1. 正常解析 — 单匹配返回 wp_id + jump_route
  2. 无权限 — 当前端点无项目授权校验（baseline: 不做 403）
  3. Binding 不匹配 — 当前端点无 wp_id↔project/sheet binding 校验

目的：Task 4 接入 auth.check_project_access + verify_wp_binding 后，
场景 2/3 应返回 403。本 baseline 记录改造前行为以便对比。

当前行为：
- 端点直接调 resolver.resolve_instance，无授权校验
- explicit_wp_id 传入时直接查 WorkingPaper 表，不校验归属

Validates: Requirements 3.1, 3.2, 3.3, 3.4
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.acnr.resolver import (
    ResolveInstanceResult,
    resolve_instance,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_wp_index(
    project_id: uuid.UUID,
    wp_code: str = "D2-2",
    wp_name: str = "明细表D2-2",
    idx_id: uuid.UUID | None = None,
) -> MagicMock:
    """Create a mock WpIndex row."""
    idx = MagicMock()
    idx.id = idx_id or uuid.uuid4()
    idx.project_id = project_id
    idx.wp_code = wp_code
    idx.wp_name = wp_name
    idx.is_deleted = False
    return idx


def _make_db_session(
    wp_indices: list | None = None,
    wp_id: uuid.UUID | None = None,
) -> AsyncMock:
    """Create a mock AsyncSession with configurable query results."""
    db = AsyncMock()
    call_count = [0]

    async def mock_execute(stmt):
        result_mock = MagicMock()
        call_count[0] += 1

        if call_count[0] == 1:
            # WpIndex lookup
            scalars_mock = MagicMock()
            scalars_mock.all.return_value = wp_indices or []
            result_mock.scalars.return_value = scalars_mock
        elif call_count[0] == 2:
            # WorkingPaper.id lookup
            result_mock.scalar_one_or_none.return_value = wp_id
        else:
            result_mock.scalar_one_or_none.return_value = None

        return result_mock

    db.execute = mock_execute
    return db


def _make_db_session_explicit_wp(
    wp_id: uuid.UUID,
    project_id: uuid.UUID,
    wp_index_id: uuid.UUID,
) -> AsyncMock:
    """Create mock session for explicit_wp_id path."""
    db = AsyncMock()

    async def mock_execute(stmt):
        result_mock = MagicMock()
        wp_mock = MagicMock()
        wp_mock.id = wp_id
        wp_mock.project_id = project_id
        wp_mock.wp_index_id = wp_index_id
        wp_mock.is_deleted = False
        result_mock.scalar_one_or_none.return_value = wp_mock
        return result_mock

    db.execute = mock_execute
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# 场景 1: 正常解析 — 单匹配成功
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioNormalResolve:
    """场景 1: 正常请求 — project_id + parent + sheet_code 单匹配。

    Baseline 行为：返回 found=True + wp_id + jump_route。

    Validates: Requirements 3.1 (正常路径)
    """

    @pytest.mark.asyncio
    async def test_normal_resolve_returns_found_true(self):
        """正常单匹配 → found=True。"""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        idx = _make_wp_index(project_id, wp_code="D2-2")

        db = _make_db_session(wp_indices=[idx], wp_id=wp_id)

        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
        )

        assert result.found is True
        assert result.wp_id == wp_id
        assert result.error is None

    @pytest.mark.asyncio
    async def test_normal_resolve_returns_jump_route(self):
        """正常解析返回 jump_route（含 wp_id）。"""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        idx = _make_wp_index(project_id, wp_code="D2-2")

        db = _make_db_session(wp_indices=[idx], wp_id=wp_id)

        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
        )

        assert result.jump_route is not None
        assert str(wp_id) in result.jump_route

    @pytest.mark.asyncio
    async def test_normal_resolve_returns_binding_metadata(self):
        """正常解析返回完整 binding 元数据。"""
        project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        idx = _make_wp_index(project_id, wp_code="D2-2")

        db = _make_db_session(wp_indices=[idx], wp_id=wp_id)

        result = await resolve_instance(
            db=db,
            project_id=project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
        )

        assert result.binding is not None
        assert result.binding.parent_wp_code == "D2"
        assert result.binding.sheet_code == "D2-2"
        assert result.binding.wp_id == wp_id


# ═══════════════════════════════════════════════════════════════════════════════
# 场景 2: 无权限 — 当前无授权校验（baseline: 不做 403）
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioNoPermission:
    """场景 2: 用户对 project 无访问权 — 记录当前无校验 baseline。

    当前行为：resolve_instance 不做项目授权校验，即使用户无权访问该 project，
    仍然返回 wp_id + jump_route（安全缺口）。

    Task 4 接入 auth.check_project_access 后应返回 403。

    Validates: Requirements 3.1, 3.3 (baseline: 无校验状态)
    """

    @pytest.mark.asyncio
    async def test_no_auth_check_still_resolves(self):
        """Baseline: 无授权校验 → 任意 project_id 都能解析成功。"""
        # 使用一个"不属于用户"的 project_id（当前无校验，仍成功）
        other_project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        idx = _make_wp_index(other_project_id, wp_code="K1-12")

        db = _make_db_session(wp_indices=[idx], wp_id=wp_id)

        result = await resolve_instance(
            db=db,
            project_id=other_project_id,
            parent_wp_code="K1",
            sheet_code="K1-12",
        )

        # Baseline: 不做授权检查 → 仍然返回 found=True
        assert result.found is True
        assert result.wp_id == wp_id
        # Baseline: 不返回 403（当前无 HTTPException 抛出机制）
        assert result.error is None

    @pytest.mark.asyncio
    async def test_no_auth_check_returns_full_metadata(self):
        """Baseline: 即使无权限也返回完整项目级数据（wp_id/jump_route）。

        Task 4 后，无权限时应不返回 wp_id/jump_route（Req-3.4）。
        """
        other_project_id = uuid.uuid4()
        wp_id = uuid.uuid4()
        idx = _make_wp_index(other_project_id, wp_code="F1-1")

        db = _make_db_session(wp_indices=[idx], wp_id=wp_id)

        result = await resolve_instance(
            db=db,
            project_id=other_project_id,
            parent_wp_code="F1",
            sheet_code="F1-1",
        )

        # Baseline: 完整返回项目级数据（改造后应隐藏）
        assert result.wp_id is not None
        assert result.jump_route is not None
        assert result.binding is not None
        assert result.binding.wp_id == wp_id


# ═══════════════════════════════════════════════════════════════════════════════
# 场景 3: Binding 不匹配 — 当前无 wp_id↔project 归属校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestScenarioBindingMismatch:
    """场景 3: explicit_wp_id 不属于请求的 project — 记录当前无校验 baseline。

    当前行为：传入 explicit_wp_id 时，仅查 WorkingPaper 表确认存在，
    不校验其 project_id 是否与请求的 project_id 一致（IDOR 风险）。

    Task 4 接入 verify_wp_binding 后应返回 403。

    Validates: Requirements 3.2, 3.3 (baseline: 无 binding 校验)
    """

    @pytest.mark.asyncio
    async def test_mismatched_wp_id_still_resolves(self):
        """Baseline: explicit_wp_id 属于另一 project → 当前仍解析成功。"""
        requesting_project_id = uuid.uuid4()
        actual_project_id = uuid.uuid4()  # wp 实际属于的 project
        explicit_wp_id = uuid.uuid4()
        wp_index_id = uuid.uuid4()

        # 模拟 WorkingPaper 存在但属于 actual_project_id（非 requesting）
        db = _make_db_session_explicit_wp(
            wp_id=explicit_wp_id,
            project_id=actual_project_id,
            wp_index_id=wp_index_id,
        )

        result = await resolve_instance(
            db=db,
            project_id=requesting_project_id,  # 请求方的 project_id
            parent_wp_code="D2",
            sheet_code="D2-2",
            explicit_wp_id=explicit_wp_id,
        )

        # Baseline: 不校验 wp 归属 → 仍返回 found=True
        assert result.found is True
        assert result.wp_id == explicit_wp_id
        # Baseline: 不做 binding 校验，不返回 403
        assert result.error is None

    @pytest.mark.asyncio
    async def test_mismatched_binding_returns_jump_route(self):
        """Baseline: binding 不匹配时仍返回 jump_route（IDOR 泄露）。

        Task 4 后，binding 不匹配应返回 403 且不泄露 jump_route。
        """
        requesting_project_id = uuid.uuid4()
        actual_project_id = uuid.uuid4()
        explicit_wp_id = uuid.uuid4()
        wp_index_id = uuid.uuid4()

        db = _make_db_session_explicit_wp(
            wp_id=explicit_wp_id,
            project_id=actual_project_id,
            wp_index_id=wp_index_id,
        )

        result = await resolve_instance(
            db=db,
            project_id=requesting_project_id,
            parent_wp_code="D2",
            sheet_code="D2-2",
            explicit_wp_id=explicit_wp_id,
        )

        # Baseline: 返回 jump_route（改造后应隐藏）
        assert result.jump_route is not None
        assert str(explicit_wp_id) in result.jump_route
