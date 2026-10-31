"""Route-level Wp_Bound_Gate 接入 helper（Task 9 / 组件 C10 EntryIntegration）

Feature: procedure-delegation-visibility-isolation
Requirements: 8.1–8.19（全入口前置统一门）、5.8–5.18（页面隔离 / 历史只读）、7.5（reviewer 白名单）、
  9.x（统一 404）、12.7–12.9（前端拒绝行为）。

本模块是 Task 9–11 各 route handler 接入 ``resolve_wp_binding_and_access()`` 的**唯一薄封装**：
把 route 的原始参数（wp_id / project_id / sheet / version / state / token_claims）装配成
``WpBoundRequest`` 并调用 gate，在读取业务正文或产生副作用**之前**完成授权判定。

- allow → 返回 ``WpAccessContext``（含 project_id / wp_index_id / role / access_kinds /
  allowed_sheet_keys / resolved_sheet_key / current_version / readonly / wp_id）。
- deny → 抛 ``ExternalNotFound``（对外 404 + ``{"detail":"资源不存在或不可访问"}``）。
- 资源无关限流 → 抛 ``RateLimited``（对外 429 + Retry-After）。

无 project_id 的 route 无需自行反查：gate 从 wp_id / wp_index_id / task / instance 反查资源真实
project（Binding_Minimum）。route 只需把已知的最强 identity（通常 wp_id）传入即可。

约定：service 纯读，不 flush/commit 业务写；helper 不吞异常（gate 的 404/429 必须冒泡到 FastAPI）。
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal, Mapping
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.routers._wp_edit_lock_scope import EditLockScope, edit_lock_scope
from app.services.wp_visibility.contracts import WpAccessContext
from app.services.wp_visibility.wp_bound_gate import (
    BindingAdapters,
    resolve_wp_binding_and_access,
)

__all__ = [
    "enforce_wp_gate",
    "enforce_task_gate",
    "dedicated_wp_gate",
    "enforce_edit_lock_for_content_write",
    "enforce_edit_lock_at_write_point",
    "raise_if_edit_locked",
    "client_instance_of",
    "wp_gate_dep",
    "include_router_with_wp_gate",
]

# 单例 adapters（无状态；仅构造 WpBoundRequest 的 shape）。
_HTTP_ADAPTERS = BindingAdapters(entry_kind="http")


async def enforce_wp_gate(
    db: AsyncSession,
    current_user,
    *,
    entrypoint: str,
    action: str,
    method: str,
    wp_id: UUID | None = None,
    wp_index_id: UUID | None = None,
    wp_code: str | None = None,
    project_id: UUID | None = None,
    route_name: str | None = None,
    entry_family: str | None = None,
    requested_sheet_key: str | None = None,
    requested_version: str | None = None,
    source_state: str = "none",
    target_state: str = "none",
    client_wp_id: UUID | None = None,
    client_wp_index_id: UUID | None = None,
    token_claims: Mapping[str, str] | None = None,
    review_reason: str | None = None,
    request_id: str | None = None,
) -> WpAccessContext:
    """wp_id/wp_index_id 绑定资源的统一门判定（HTTP 入口）。

    在 route handler 读取业务正文或产生副作用之前调用。deny → 404，限流 → 429 自动冒泡。
    """
    req = _HTTP_ADAPTERS.wp(
        entrypoint=entrypoint,
        action=action,
        method=method,
        wp_id=wp_id,
        wp_index_id=wp_index_id,
        wp_code=wp_code,
        project_id=project_id,
        route_name=route_name,
        entry_family=entry_family,
        requested_sheet_key=requested_sheet_key,
        requested_version=requested_version,
        source_state=source_state,
        target_state=target_state,
        client_wp_id=client_wp_id,
        client_wp_index_id=client_wp_index_id,
        token_claims=token_claims,
        review_reason=review_reason,
        request_id=request_id,
    )
    # procedure-mainline-convergence Task 7.1: 注入持久 epoch cache，撤权 ≤1s 收敛
    from app.services.wp_visibility.epoch_cache import get_epoch_cache
    return await resolve_wp_binding_and_access(db, current_user, req, epoch_cache=get_epoch_cache())


async def enforce_task_gate(
    db: AsyncSession,
    current_user,
    *,
    entrypoint: str,
    action: str,
    method: str,
    task_id: UUID,
    project_id: UUID | None = None,
    route_name: str | None = None,
    entry_family: str | None = None,
    requested_sheet_key: str | None = None,
    source_state: str = "none",
    target_state: str = "none",
    review_reason: str | None = None,
    request_id: str | None = None,
) -> WpAccessContext:
    """ProcedureRowTask 绑定资源的统一门判定（task detail / transition / deep-link）。

    gate 从 task 反查 project + 唯一 wp_index；row-only 身份只授权映射 sheet。
    """
    req = _HTTP_ADAPTERS.task(
        entrypoint=entrypoint,
        action=action,
        method=method,
        task_id=task_id,
        project_id=project_id,
        route_name=route_name,
        entry_family=entry_family,
        requested_sheet_key=requested_sheet_key,
        source_state=source_state,
        target_state=target_state,
        review_reason=review_reason,
        request_id=request_id,
    )
    return await resolve_wp_binding_and_access(db, current_user, req)


# ---------------------------------------------------------------------------
# 专属组件 /{wp_id}/... 通用 router-level 依赖（Task 9 DEDICATED-SUB-ROUTE）
#
# 作为 **额外** 的服务端可见性隔离检查（defense in depth）——不移除任何既有项目级/原生授权。
# 以 ``dependencies=[Depends(dedicated_wp_gate)]`` 注册到专属科目组件 APIRouter（其路由全部形如
# ``/{wp_id}/...``），一处覆盖该 router 全部 wp_id 绑定子路由，无需逐路由手工接线。
#
# 分类（按 HTTP method，九维精确命中 Action_Matrix 的 ``workpaper.dedicated_subroute`` 族）：
#   - GET/HEAD          → ``dedicated_read``（只读；outsider/未委派/跨项目/历史版本统一 404）。
#   - POST/PUT/PATCH    → ``dedicated_write``（内容写；reviewer / History_Only 拒绝）。
#   - DELETE            → ``dedicated_delete``（内容删）。
#
# **安全 no-op 语义**：请求 path_params 无 ``wp_id`` / ``wp_index_id``（或非合法 UUID）时直接返回，
# 不做任何判定——使该依赖即便挂到混合 router 也只影响 wp_id 绑定路由，绝不误拒非 wp 路由。
# ---------------------------------------------------------------------------

_DEDICATED_ENTRYPOINT = "workpaper.dedicated_subroute"
_DEDICATED_ENTRY_FAMILY = "workpaper"


# ── 编辑锁（spec workpaper-multi-window-lock-gaps R2.3 / R3）────────────────────────────
# 哪些写路由在门里校验、哪些不校验，单一来源是 `_wp_edit_lock_scope`（默认校验）。

EditLockPurpose = Literal["save", "online_edit"]

_LOCK_MESSAGES: dict[str, tuple[str, str]] = {
    "save": (
        "这张底稿正在你的另一个窗口编辑，本窗口为只读，本次修改未保存。请在正在编辑的窗口里操作，或关掉那个窗口后刷新本页。",
        "{name} 正在编辑这张底稿，当前为只读，本次修改未保存。",
    ),
    "online_edit": (
        "这张底稿正在你的另一个窗口编辑，本窗口为只读，不能进入在线编辑。请在正在编辑的窗口里操作，或关掉那个窗口后刷新本页。",
        "{name} 正在编辑这张底稿，当前为只读，不能进入在线编辑。",
    ),
}


@dataclass(frozen=True)
class _WriteRequester:
    user_id: UUID
    instance: str | None
    wp_id: UUID


#: 门对写请求记下请求人，供处理函数深处的写回点（如计算后 `apply_to_sheet` 写回）校验。
_WRITE_REQUESTER: ContextVar[_WriteRequester | None] = ContextVar("gt_wp_write_requester", default=None)


def client_instance_of(request: Request) -> str | None:
    """请求头 ``X-Client-Instance``（窗口编号）；没带返回 None。"""
    return (request.headers.get("x-client-instance") or "").strip() or None


async def raise_if_edit_locked(
    db: AsyncSession, user_id: UUID, instance: str | None, wp_id: UUID, *, purpose: EditLockPurpose = "save",
) -> None:
    """有效锁的持有人（用户 + 窗口）以外 ⇒ 423，detail 说明谁在编辑。判定见 ``find_blocking_lock``。"""
    from app.services.editing_lock_service import find_blocking_lock

    lock = await find_blocking_lock(db, "workpaper", str(wp_id), user_id, instance)
    if lock is None:
        return
    own_window, other_user = _LOCK_MESSAGES[purpose]
    message = own_window if lock.holder_id == user_id else other_user.format(name=lock.holder_name or "其他用户")
    raise HTTPException(status_code=423, detail=message)


async def enforce_edit_lock_for_content_write(
    db: AsyncSession, current_user, request: Request, wp_id: UUID, *, purpose: EditLockPurpose = "save",
) -> None:
    """底稿内容写入前校验编辑锁：有效锁的持有人（用户 + 窗口）以外的请求 423，本次写入不落库。

    原先保存 / 导入接口都不看编辑锁，「第二窗只读」只靠前端：只读窗口工具栏「导入」照样能把数据写进库
    （spec workpaper-multi-window-lock-gaps，2026-10-31 实测）。窗口编号取请求头 ``X-Client-Instance``。
    不经底稿门禁的写接口（版本回滚、在线编辑入口等）在处理函数里直接调本函数。
    """
    await raise_if_edit_locked(db, current_user.id, client_instance_of(request), wp_id, purpose=purpose)


async def enforce_edit_lock_at_write_point(db: AsyncSession, wp_id) -> None:
    """写回点校验：门记下的请求人（同一张底稿）以外持锁 ⇒ 423。

    给「计算后可选写回」这类路由用：门里不知道这次要不要写（看请求体的 ``apply_to_sheet``），只算不写要放行，
    写回函数在真正写之前调本函数。没经过门（没有请求人）或底稿对不上 ⇒ 不判（守卫保证这些路由都经门）。
    """
    requester = _WRITE_REQUESTER.get()
    try:
        wid = UUID(str(wp_id))
    except (ValueError, TypeError, AttributeError):
        return
    if requester is None or requester.wp_id != wid:
        return
    await raise_if_edit_locked(db, requester.user_id, requester.instance, wid)


def _classify_dedicated(method: str) -> tuple[str, str]:
    """(entrypoint, action) —— 按 HTTP method 分类（与 Action_Matrix dedicated 族登记一致）。"""
    m = (method or "").upper()
    if m in ("GET", "HEAD"):
        return _DEDICATED_ENTRYPOINT, "dedicated_read"
    if m == "DELETE":
        return _DEDICATED_ENTRYPOINT, "dedicated_delete"
    # POST / PUT / PATCH / 其它写
    return _DEDICATED_ENTRYPOINT, "dedicated_write"


async def dedicated_wp_gate(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> None:
    """专属组件 /{wp_id}/... 子路由的统一门（router-level 依赖）。

    在路由处理函数读取业务正文或产生副作用之前完成可见性授权判定：deny → 404，限流 → 429
    自动冒泡（``ExternalNotFound`` / ``RateLimited`` 均为 ``HTTPException``，FastAPI 直接返回）。

    仅当 path 携带 ``wp_id`` 或 ``wp_index_id`` 且为合法 UUID 时判定；否则 no-op（安全放行给原生授权）。
    """
    pp = request.path_params or {}
    raw_wp = pp.get("wp_id")
    raw_idx = pp.get("wp_index_id")
    raw = raw_wp if raw_wp is not None else raw_idx
    if raw is None:
        return  # 非 wp_id 绑定路由 → no-op（不改变原生授权）
    try:
        wp_uuid = UUID(str(raw))
    except (ValueError, TypeError, AttributeError):
        return  # 非 UUID 路径段（静态段被通配捕获等）→ no-op，交原生逻辑处理

    entrypoint, action = _classify_dedicated(request.method)
    # path 参数名为 wp_index_id 时按 wp_index 绑定；否则按 wp_id（专属组件均传 working_paper.id）。
    is_index_param = raw_wp is None and raw_idx is not None
    route = request.scope.get("route")
    route_name = getattr(route, "path", None)

    await enforce_wp_gate(
        db,
        current_user,
        entrypoint=entrypoint,
        action=action,
        method=(request.method or "").upper(),
        wp_id=None if is_index_param else wp_uuid,
        wp_index_id=wp_uuid if is_index_param else None,
        route_name=route_name,
        entry_family=_DEDICATED_ENTRY_FAMILY,
    )
    # 可见性通过后再看编辑锁：写底稿内容只许持锁的那个窗口（编辑锁按 working_paper.id 记，wp_index_id 路由不适用）。
    # 默认校验；不写底稿 / 协作与流程 / sheet 锁 / 计算后可选写回不在这里判（`_wp_edit_lock_scope`）。
    if action != "dedicated_read" and not is_index_param:
        _WRITE_REQUESTER.set(_WriteRequester(current_user.id, client_instance_of(request), wp_uuid))
        if edit_lock_scope(route_name) is EditLockScope.CHECK:
            await enforce_edit_lock_for_content_write(db, current_user, request, wp_uuid)


# ---------------------------------------------------------------------------
# Cross-cutting registry helpers (Task 16 CROSS-CUTTING-WP-GATE)
# ---------------------------------------------------------------------------
def wp_gate_dep():
    """A FastAPI ``Depends(dedicated_wp_gate)`` for cross-cutting wp_id routers.

    ``dedicated_wp_gate`` is a safe no-op for routes without ``{wp_id}``/
    ``{wp_index_id}`` path params, so attaching it to a mixed router only gates
    the wp_id-bound subroutes (defense in depth; additive to native authz).
    """
    return Depends(dedicated_wp_gate)


def include_router_with_wp_gate(app, router, **kw) -> None:
    """``app.include_router`` that attaches ``dedicated_wp_gate`` iff the router
    has any ``{wp_id}``/``{wp_index_id}`` route (else includes unchanged)."""
    from app.security.dedicated_component_routers import (
        router_has_dedicated_module,
        router_has_wp_id_route,
    )

    if router_has_dedicated_module(router) or router_has_wp_id_route(router):
        deps = list(kw.pop("dependencies", []) or [])
        deps.append(Depends(dedicated_wp_gate))
        kw["dependencies"] = deps
    app.include_router(router, **kw)
