"""Property test P21 — 两入口角色门禁（advanced-query-module Task 16.2）

Feature: advanced-query-module, Property 21: 两入口角色门禁
Validates: Requirements 11.1, 11.2, 11.3, 11.4

*For any* 请求角色，在没有任何项目成员行时，Whitelist_Query_Builder 的可访问与执行权限成立当且仅当系统角色属于
{admin, manager, partner}；Business_View_Query 对所有已认证角色开放；未认证请求对任一入口返回 HTTP 401。

（平台既有约定：partner 为 manager 权限超集，纳入构建器可访问集合 `_QUERY_BUILDER_ROLES`。）

2026-10-27 advanced-query-linkage-closure 任务 12（ADR-AQL-08，AQ-21）：门禁改为 async 依赖、判定移到
``services/custom_query/builder_access``，另认「任一未删除项目的项目经理 / 合伙人（edit 级）」——该分支查成员表，
由 ``tests/advanced_query_linkage/test_aql_builder_access.py`` 在真实权限世界里覆盖；本文件的桩库对成员查询恒返回无行，
并断言系统角色命中时根本不查库。
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from fastapi import HTTPException
from hypothesis import given, settings
from hypothesis import strategies as st

from app.deps import get_current_user
from app.routers import custom_query as cq_mod
from app.routers.query_builder import (
    _QUERY_BUILDER_ROLES,
    require_query_builder_access,
)
from app.routers.query_builder import router as builder_router

# 构建器可访问角色（R11.2）
_PRIVILEGED = {"admin", "manager", "partner"}

# 角色生成器：privileged + 常见非特权角色 + 任意随机字符串
_ROLE_POOL = st.one_of(
    st.sampled_from(
        ["admin", "manager", "partner", "auditor", "qc", "readonly", "staff", "reviewer", ""]
    ),
    st.text(min_size=0, max_size=12),
)


def _fake_user(role: str):
    """构造带 role 的用户桩（_get_role_value 兼容 str / enum.value）。"""
    u = MagicMock()
    u.role = role
    u.id = "user-001"
    u.username = "tester"
    return u


class _NoMembershipDB:
    """成员查询恒返回无行的会话桩；记录是否被查过（系统角色命中时不应查库）。"""

    def __init__(self) -> None:
        self.executed = 0

    async def execute(self, _stmt):
        self.executed += 1
        return SimpleNamespace(first=lambda: None)


# ─── P21 主属性：无成员行时构建器门禁 IFF role ∈ {admin, manager, partner} ─────


@settings(max_examples=5)
@given(role=_ROLE_POOL)
def test_p21_builder_gate_iff_privileged_role(role):
    """Feature: advanced-query-module, Property 21: 两入口角色门禁

    Validates: Requirements 11.1, 11.2, 11.3, 11.4

    没有任何项目成员行时，白名单构建器可访问当且仅当 role ∈ {admin, manager, partner}；否则 403 ROLE_FORBIDDEN，
    原因写明合伙人与项目经理（AQ-29）。
    """
    user = _fake_user(role)
    db = _NoMembershipDB()
    privileged = role in _PRIVILEGED

    if privileged:
        # 通过 → 依赖返回用户本身，且系统角色命中时不查成员表
        assert asyncio.run(require_query_builder_access(current_user=user, db=db)) is user
        assert db.executed == 0
    else:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(require_query_builder_access(current_user=user, db=db))
        assert exc.value.status_code == 403
        detail = exc.value.detail
        assert isinstance(detail, dict)
        assert detail.get("error_code") == "ROLE_FORBIDDEN"
        assert "合伙人" in detail.get("message", "") and "项目经理" in detail.get("message", "")
        assert db.executed == 1, "非系统角色必须查一次成员表（项目经理分支）"


def test_p21_privileged_role_set_is_exactly_admin_manager_partner():
    """`_QUERY_BUILDER_ROLES` 单一真源即 {admin, manager, partner}。"""
    assert set(_QUERY_BUILDER_ROLES) == _PRIVILEGED


# ─── R11.1：业务视图对所有已认证角色开放（无角色门禁）──────────────────────


def _flatten_dep_calls(dependant) -> list:
    calls = []
    if getattr(dependant, "call", None) is not None:
        calls.append(dependant.call)
    for sub in getattr(dependant, "dependencies", []):
        calls.extend(_flatten_dep_calls(sub))
    return calls


def _find_route(router, endpoint_name):
    for route in router.routes:
        if getattr(route, "endpoint", None) is not None and route.endpoint.__name__ == endpoint_name:
            return route
    return None


def test_p21_business_view_execute_has_no_role_gate():
    """R11.1：Business_View_Query（execute_query）仅依赖 get_current_user，无构建器角色门禁。"""
    route = _find_route(cq_mod.router, "execute_query")
    assert route is not None, "custom_query.execute_query route not found"
    calls = _flatten_dep_calls(route.dependant)
    assert get_current_user in calls, "业务视图必须要求已认证（get_current_user）"
    assert require_query_builder_access not in calls, "业务视图不得施加构建器角色门禁"


def test_p21_builder_routes_enforce_role_gate():
    """R11.2/R11.3：白名单构建器执行类端点统一注入 require_query_builder_access 门禁。"""
    gated = 0
    for route in builder_router.routes:
        ep = getattr(route, "endpoint", None)
        if ep is None:
            continue
        calls = _flatten_dep_calls(route.dependant)
        if require_query_builder_access in calls:
            gated += 1
    assert gated >= 1, "白名单构建器至少一个端点应注入角色门禁依赖"


# ─── R11.4：未认证请求 → 401 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_p21_unauthenticated_returns_401():
    """R11.4：未认证（无效 token）访问查询入口 → HTTP 401。

    直接验证两入口共用的认证依赖 get_current_user 对无效凭据抛 401。
    """
    creds = SimpleNamespace(credentials="not-a-valid-jwt-token")
    with pytest.raises(HTTPException) as exc:
        await get_current_user(credentials=creds, db=MagicMock())
    assert exc.value.status_code == 401
