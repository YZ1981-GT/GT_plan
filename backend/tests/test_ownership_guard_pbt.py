"""Property-based tests for OwnershipGuard — advanced-query-module Tasks 5.2 / 5.3.

覆盖两条设计属性：

- **Property 15: 归属过滤完整性与跨项目拒绝**（Task 5.2）
  Validates: Requirements 4.7, 9.2, 9.6, 13.5
  对任意「多项目数据行集 + 任意可访问项目子集」：查询/模板执行返回的所有行的
  project_id 都属于可访问集合，且不遗漏任何可访问行；对不属于可访问集合的
  下钻/访问目标一律 HTTP 403 且不泄露内容。

- **Property 16: 归属校验单点强制**（Task 5.3）
  Validates: Requirements 9.5
  对任意查询注册/覆盖/回写入口，请求在通过 Ownership_Check 之前都不触达任何数据
  读写层；不存在绕过 Ownership_Check 的路径（契约测试）。

铁律：每条属性 `@settings(max_examples=5)`；redis/DB 全部以 fakeredis / AsyncMock /
stub 隔离，不触真实基础设施；ACNR 出口不重写。
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest
from fastapi import HTTPException
from hypothesis import assume, given, settings, strategies as st

from app.services.custom_query.addressing_service import ResolvedTarget
from app.services.custom_query.ownership_guard import OwnershipGuard, ownership_guard
from app.services.custom_query.query_orchestrator import (
    ENTRY_BUSINESS,
    ENTRY_BUILDER,
    QueryOrchestrator,
    QueryRequest,
)

# 模块级 patch 目标（在 ownership_guard 命名空间内）
_CACHED_PERM = "app.services.custom_query.ownership_guard._get_cached_permission"
_SET_RLS = "app.services.custom_query.ownership_guard.set_rls_context"
_AUDIT_LOG = "app.services.custom_query.ownership_guard.audit_logger.log_action"


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _user(role_value: str = "staff", uid: str = "user-1"):
    """构造一个普通（非全访问）用户；role.value 不在 admin/partner。"""
    u = MagicMock()
    u.id = uid
    u.role = SimpleNamespace(value=role_value)
    return u


class _FixedAccessGuard(OwnershipGuard):
    """把「可访问项目集合」固定为给定值的守卫子类。

    仅覆盖 `_accessible_project_ids`（唯一数据源），从而无需真实 project_users /
    project_assignments 查询即可驱动 `filter_accessible_rows` /
    `assert_target_accessible` / `assert_all_targets` 的真实归属逻辑。
    传入 None 表示「可访问全部」（admin / partner 语义）。
    """

    def __init__(self, accessible: set[UUID] | None):
        super().__init__()
        self._fixed = accessible

    async def _accessible_project_ids(self, user, db):  # type: ignore[override]
        return self._fixed


@st.composite
def _multi_project_rows(draw):
    """生成 (universe, accessible_subset, rows)。

    universe：≥1 个去重 project_id；accessible：universe 的任意子集；
    rows：project_id 取自 universe 的数据行（含内容字段）。
    """
    universe = draw(st.lists(st.uuids(), min_size=1, max_size=6, unique=True))
    accessible = set(draw(st.lists(st.sampled_from(universe), max_size=len(universe))))
    rows = draw(
        st.lists(
            st.builds(
                lambda p, v: {"project_id": p, "amount": v, "secret": "content"},
                st.sampled_from(universe),
                st.integers(min_value=-1000, max_value=1000),
            ),
            max_size=25,
        )
    )
    return universe, accessible, rows


# ═══════════════════════════════════════════════════════════════════════════
# Property 15: 归属过滤完整性与跨项目拒绝 (Task 5.2)
# Validates: Requirements 4.7, 9.2, 9.6, 13.5
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@settings(max_examples=5)
@given(scenario=_multi_project_rows())
async def test_p15_cross_project_filter_completeness_and_soundness(scenario):
    """Feature: advanced-query-module, Property 15: 归属过滤完整性与跨项目拒绝

    跨项目聚合仅保留可访问项目行（R9.6）：
      - soundness：返回行的 project_id 全部 ∈ 可访问集合（无越权泄露）。
      - completeness：所有可访问项目的输入行均被保留（不遗漏、保持顺序）。

    **Validates: Requirements 4.7, 9.2, 9.6, 13.5**
    """
    _universe, accessible, rows = scenario
    guard = _FixedAccessGuard(set(accessible))
    user = _user()
    db = AsyncMock()

    kept = await guard.filter_accessible_rows(rows, user=user, db=db)

    # soundness：无任一不可访问行泄露
    assert all(r["project_id"] in accessible for r in kept)
    # completeness + 顺序：恰等于输入中所有可访问行（不遗漏、不重排、不去重）
    expected = [r for r in rows if r["project_id"] in accessible]
    assert kept == expected


@pytest.mark.asyncio
@settings(max_examples=5)
@given(
    accessible=st.lists(st.uuids(), max_size=5, unique=True),
    denied=st.uuids(),
)
async def test_p15_over_privilege_target_rejected_403(accessible, denied):
    """Feature: advanced-query-module, Property 15: 归属过滤完整性与跨项目拒绝

    对不属于可访问集合的访问/回写目标一律 HTTP 403 且不泄露内容（R9.2 / R4.7）；
    可访问目标放行。

    **Validates: Requirements 4.7, 9.2, 9.6, 13.5**
    """
    acc = set(accessible)
    assume(denied not in acc)  # 保证 denied 确为越权目标
    guard = _FixedAccessGuard(acc)
    user = _user()
    db = AsyncMock()

    with patch(_CACHED_PERM, new=AsyncMock(return_value=None)), patch(
        _SET_RLS, new=AsyncMock()
    ), patch(_AUDIT_LOG, new=AsyncMock()):
        # (1) 越权 project → 403，且 detail 不含任何数据内容（无泄露）
        with pytest.raises(HTTPException) as ei:
            await guard.assert_target_accessible(user=user, project_id=denied, db=db)
        assert ei.value.status_code == 403
        detail = ei.value.detail
        assert isinstance(detail, dict)
        assert set(detail.keys()) <= {"error_code", "message", "addr_id"}
        assert "secret" not in str(detail) and "amount" not in str(detail)

        # (2) 跨 sheet 回写含越权目标 → 整体 403（R9.3 / R9.4）
        denied_target = SimpleNamespace(project_id=denied, addr_id="D2/D2-2/A1")
        with pytest.raises(HTTPException) as ei2:
            await guard.assert_all_targets([denied_target], user=user, db=db)
        assert ei2.value.status_code == 403

        # (3) 可访问 project → 放行（无异常）
        if acc:
            ok_pid = next(iter(acc))
            await guard.assert_target_accessible(user=user, project_id=ok_pid, db=db)
            ok_target = SimpleNamespace(project_id=ok_pid, addr_id="D2/D2-2/A1")
            await guard.assert_all_targets([ok_target], user=user, db=db)


@pytest.mark.asyncio
async def test_p15_admin_all_access_passthrough():
    """单元补充：admin/partner 视为可访问全部项目，聚合行不被过滤。"""
    guard = _FixedAccessGuard(None)  # None = 全访问哨兵
    user = _user(role_value="admin")
    db = AsyncMock()
    rows = [{"project_id": uuid4(), "amount": 1} for _ in range(4)]
    kept = await guard.filter_accessible_rows(rows, user=user, db=db)
    assert kept == rows


# ═══════════════════════════════════════════════════════════════════════════
# Property 16: 归属校验单点强制 (Task 5.3)
# Validates: Requirements 9.5
# ═══════════════════════════════════════════════════════════════════════════


class _RecordingGuard:
    """记录 Ownership_Check 调用时点的守卫桩；可配置为拒绝。"""

    def __init__(self, events: list[str], deny: bool):
        self.events = events
        self.deny = deny

    async def assert_target_accessible(self, *, user, project_id, db):
        self.events.append("ownership_check")
        if self.deny:
            raise HTTPException(
                status_code=403,
                detail={"error_code": "FORBIDDEN_PROJECT", "message": "denied"},
            )

    async def filter_accessible_rows(self, rows, *, user, db):
        return rows


class _RecordingAddressing:
    """记录 resolve（数据读层前置寻址）调用时点的寻址桩。"""

    def __init__(self, events: list[str]):
        self.events = events

    async def resolve_many(self, raws, *, project_id=None, db=None, timeout_s=5.0):
        self.events.append("resolve")
        return [ResolvedTarget(raw=r, found=True, addr_id=r) for r in raws]


class _RecordingCache:
    """记录 cache（数据读写层）调用时点的缓存桩。"""

    def __init__(self, events: list[str]):
        self.events = events

    def cache_key(self, query_def, project_id, scope_sig):
        return "k"

    async def get_or_compute(self, key, compute, ttl=30):
        self.events.append("cache")
        return await compute()


@pytest.mark.asyncio
@settings(max_examples=5)
@given(
    entry=st.sampled_from([ENTRY_BUSINESS, ENTRY_BUILDER]),
    deny=st.booleans(),
    n_targets=st.integers(min_value=0, max_value=3),
)
async def test_p16_ownership_check_single_point_no_bypass(entry, deny, n_targets):
    """Feature: advanced-query-module, Property 16: 归属校验单点强制

    统一编排两入口（业务视图注册/覆盖 + 白名单构建器）在执行链中：
      - Ownership_Check 未通过（403）时，resolve / cache / fetch 数据层一概不触达
        （无绕过路径，R9.5）。
      - Ownership_Check 通过时，其调用严格先于任何 resolve / cache / fetch。

    **Validates: Requirements 9.5**
    """
    events: list[str] = []

    async def fetcher(req, resolved, db):
        events.append("fetch")
        return [], []

    orch = QueryOrchestrator(
        addressing=_RecordingAddressing(events),
        guard=_RecordingGuard(events, deny),
        cache=_RecordingCache(events),
        business_fetcher=fetcher,
        builder_fetcher=fetcher,
    )

    targets = (
        [f"D2/D2-2/A{i}" for i in range(n_targets)]
        if entry == ENTRY_BUSINESS
        else []
    )
    req = QueryRequest(entry=entry, project_id=str(uuid4()), targets=targets)
    user = MagicMock()
    user.id = "u1"
    db = AsyncMock()

    if deny:
        with pytest.raises(HTTPException) as ei:
            await orch.execute(req, user=user, db=db)
        assert ei.value.status_code == 403
        # 未通过 Ownership_Check → 数据读写层零触达（无绕过）
        assert events == ["ownership_check"]
        assert "resolve" not in events
        assert "cache" not in events
        assert "fetch" not in events
    else:
        await orch.execute(req, user=user, db=db)
        # Ownership_Check 是数据链的第一步
        assert events[0] == "ownership_check"
        oc = events.index("ownership_check")
        for marker in ("resolve", "cache", "fetch"):
            if marker in events:
                assert events.index(marker) > oc


def test_p16_default_orchestrator_wires_shared_guard():
    """契约补充：默认 QueryOrchestrator 注入共享 ownership_guard 单例（单点、无旁路）。"""
    orch = QueryOrchestrator()
    assert orch._guard is ownership_guard
    assert isinstance(orch._guard, OwnershipGuard)
