"""PBT: 项目隔离 — 交叉 project → 403 [P3]

Property 3 (P3): 当用户无权访问某 project 时，resolve/resolve-instance
    携带该 project_id 必须返回 403，不泄露 wp_id/jump_route 元数据。

测试策略:
- Hypothesis 生成随机 project_id (非用户所属)
- Mock DB 查询使 project_users / project_assignments 均返回 None
- 验证 check_project_access 对无权限用户 raise 403
- 验证 admin/partner 角色始终放行

Validates: Requirements 3.1, 3.3
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from fastapi import HTTPException

from app.services.acnr.auth import check_project_access, verify_wp_binding


# ─── Hypothesis Strategies ────────────────────────────────────────────────────

# 随机生成 UUID (模拟跨项目访问)
_uuid_strategy = st.uuids()

# 非特权角色（这些角色需要项目关联才能访问）
_non_privileged_roles = st.sampled_from(["auditor", "preparer", "reviewer", "manager"])

# 特权角色（无需项目关联即可访问）
_privileged_roles = st.sampled_from(["admin", "partner"])


def _make_user(role: str, user_id: UUID | None = None) -> SimpleNamespace:
    """构造模拟用户对象。"""
    return SimpleNamespace(
        id=user_id or uuid4(),
        role=SimpleNamespace(value=role),
    )


def _mock_session_no_access() -> AsyncMock:
    """构造模拟 DB session — 两次查询均返回 None（无权限）。"""
    session = AsyncMock()
    # fetchone 返回 None → 无 project_users 和 project_assignments 记录
    mock_result = MagicMock()
    mock_result.fetchone.return_value = None
    session.execute.return_value = mock_result
    return session


def _mock_session_has_access() -> AsyncMock:
    """构造模拟 DB session — 第一次查询返回命中（有权限）。"""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (1,)  # 命中
    session.execute.return_value = mock_result
    return session


# ═══════════════════════════════════════════════════════════════════════════════
# Property 3: 项目隔离 — PBT 交叉 project → 403
# ═══════════════════════════════════════════════════════════════════════════════


class TestP3ProjectIsolation:
    """P3: 项目隔离 — 无权限用户访问跨项目资源 → 403。

    **Validates: Requirements 3.1**
    """

    @settings(max_examples=5, deadline=None)
    @given(
        project_id=_uuid_strategy,
        role=_non_privileged_roles,
        user_id=_uuid_strategy,
    )
    def test_non_privileged_user_cross_project_gets_403(
        self, project_id: UUID, role: str, user_id: UUID
    ):
        """非特权用户访问无关联的 project → 403 Forbidden。"""
        import asyncio

        user = _make_user(role, user_id)
        session = _mock_session_no_access()

        with pytest.raises(HTTPException) as exc_info:
            asyncio.new_event_loop().run_until_complete(
                check_project_access(user, project_id, session)
            )

        assert exc_info.value.status_code == 403
        # Req-3.3: 不泄露元数据 — detail 不含 project_id / wp_id
        assert str(project_id) not in str(exc_info.value.detail)

    @settings(max_examples=5, deadline=None)
    @given(
        project_id=_uuid_strategy,
        role=_privileged_roles,
        user_id=_uuid_strategy,
    )
    def test_privileged_user_always_passes(
        self, project_id: UUID, role: str, user_id: UUID
    ):
        """admin/partner 角色无论项目 → 始终放行（无 DB 查询）。"""
        import asyncio

        user = _make_user(role, user_id)
        session = AsyncMock()

        # 不应 raise
        asyncio.new_event_loop().run_until_complete(
            check_project_access(user, project_id, session)
        )

        # admin/partner 跳过 DB 查询
        session.execute.assert_not_called()

    @settings(max_examples=5, deadline=None)
    @given(
        project_id=_uuid_strategy,
        role=_non_privileged_roles,
        user_id=_uuid_strategy,
    )
    def test_user_with_access_passes(
        self, project_id: UUID, role: str, user_id: UUID
    ):
        """有项目关联的非特权用户 → 正常放行。"""
        import asyncio

        user = _make_user(role, user_id)
        session = _mock_session_has_access()

        # 不应 raise
        asyncio.new_event_loop().run_until_complete(
            check_project_access(user, project_id, session)
        )

    @settings(max_examples=5, deadline=None)
    @given(
        project_id=_uuid_strategy,
        role=_non_privileged_roles,
    )
    def test_403_does_not_leak_metadata(self, project_id: UUID, role: str):
        """403 响应不泄露 wp_id / jump_route 等项目级数据 (Req-3.3)。"""
        import asyncio

        user = _make_user(role)
        session = _mock_session_no_access()

        with pytest.raises(HTTPException) as exc_info:
            asyncio.new_event_loop().run_until_complete(
                check_project_access(user, project_id, session)
            )

        detail = str(exc_info.value.detail)
        # 不应包含任何 UUID 或路由信息
        assert "wp_id" not in detail
        assert "jump_route" not in detail
        assert "/workpapers/" not in detail
