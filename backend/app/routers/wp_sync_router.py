# -*- coding: utf-8 -*-
"""底稿 HTML ↔ OnlyOffice 双向回写的**显式 scope** 用户端 router。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 28
Requirements: 3.1, 3.6, 3.7, 5.8, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 11.4
Properties: **P10 / P11 / P45**

═══ 本模块只做三件事 ═══

1. **搬运参数** —— 路径/查询/body → service 的入参；service 的结果 → JSON。
2. **过 guard** —— 每个 handler 的第一句可执行语句都是 `await _guard(...)`；
   拿不到 :class:`~app.services.workpaper_sync.endpoint_guard.GuardedScope` 就调不到
   任何 service（业务调用面以它为必需入参，是**类型**约束而不是约定）。
3. **映射状态码** —— 每一族异常各有唯一映射点，未登记即 500 而不是「按最近似码猜」。

**不做**的事（做了就是第二套业务逻辑，必然与 service 漂移）：

* 不自己 `jwt.decode` 后比字段（callback 的校验在 `callback_route` + Task 22）；
* 不自己算 idempotency key、不自己比 `frozen_request_fingerprint`（Task 23 的复合唯一键）；
* 不自己判 room 状态/lease/fence/bundle（Task 21 的八条资格门）；
* 不自己拼第二份 OnlyOffice config（Property 11：descriptor 是唯一凭证）。

═══ descriptor 的 `document.url` 为什么在**响应时**签 ═══

Task 25 的 `EditorLaunchDescriptor` 刻意**不含**签名下载 URL。把 URL 签进 descriptor
会让签名 TTL 与 descriptor 生命周期绑死：descriptor 是 room 代际的身份快照（可被
confirm-descriptor 重放比对），而下载签名必须短 TTL（AC 10.7）。两者一旦同寿，
要么签名长到不安全，要么 descriptor 提前失效导致 confirm 永远 409。
所以签名发生在**本模块**（响应时），descriptor 只带身份。

═══ 统一 404 / 403 / 401 ═══

* 404 —— **唯一**构造点 :func:`_not_found`，响应体逐字节等于平台统一不可见响应
  （`EXTERNAL_NOT_FOUND_DETAIL`）。不存在、已 retire、跨 scope、无 visibility 四种
  原因共用它，且都在 guard 阶段 ④ 之前跑完同一串工作（见 `endpoint_guard` 模块
  docstring 的「常量工作量」）。
* 403 —— scope 已确认可见但 action/workflow/lease/generation/fence/bundle 不允许。
* 401 —— **只**表示未认证，由 `get_current_user` 产生。

═══ callback 兼容 ═══

`onlyoffice-callback` 用**独立签名**的 room/generation/doc_key/route token 服务凭证
（`callback_route.verify_callback_route`），不走用户 404/403 契约、不接受用户 Bearer、
不把 URL 里的 participant hint 当聚合 artifact 的作者。它挂在 `public_router` 上
（DocServer 不发用户 Bearer），路径含 `onlyoffice-callback` 以命中
`ResponseWrapperMiddleware._SKIP_CONTAINS` —— OO 协议要求 `{"error": N}` 是顶层。
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.wp_visibility.action_matrix import (
    _DEDICATED_ENTRYPOINT as _MATRIX_DEDICATED_ENTRYPOINT,
    _DEDICATED_READ_ACTION as _MATRIX_DEDICATED_READ_ACTION,
)
from app.services.workpaper_sync.adapters.registry import (
    WorkpaperSyncAdapterRegistry,
    build_production_registry,
)
from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
from app.services.workpaper_sync.callback_delivery import CallbackDeliveryService
from app.services.workpaper_sync.callback_download import (
    build_download_policy,
    build_httpx_transport,
)
from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT
from app.services.workpaper_sync.close_intent import CloseIntentService
from app.services.workpaper_sync.command_service import (
    CommandServiceClient,
    build_httpx_command_transport,
)
from app.services.workpaper_sync.conflict_resolution import ConflictResolutionService
from app.services.workpaper_sync.content_mutation import ContentMutationService
from app.services.workpaper_sync.endpoint_payloads import (
    build_projection,
    build_resolution_choices,
    build_resolve_fence,
)
from app.services.workpaper_sync.endpoint_guard import (
    GuardedScope,
    ScopeClaimCodec,
    ScopeRef,
    SyncActionForbiddenError,
    SyncEndpointGuard,
    SyncEndpointRequest,
    SyncScopeInvisibleError,
    VisibilityProbeFailedError,
    declared_refs,
    http_status_for_refusal,
)
from app.services.workpaper_sync.materialize_coordinator import (
    MaterializeRequest,
    build_materialize_coordinator,
    classify_materialize_rejection,
)
from app.services.workpaper_sync.models import (
    OperationShape,
    RequestKind,
    ScopeResourceKind,
    SyncDomainError,
    IdempotencyConflictError,
)
from app.services.workpaper_sync.oo_to_html import (
    OoToHtmlCoordinator,
    OoToHtmlResult,
)
from app.services.workpaper_sync.metrics import sync_metrics
from app.services.workpaper_sync.repository import WorkpaperSyncRepository
from app.services.workpaper_sync.request_application import RequestApplicationService
from app.services.workpaper_sync.resolution import CanonicalResolutionService
from app.services.workpaper_sync.rooms import RoomScope, RoomService
from app.services.workpaper_sync.timeline import SyncTimelineService
from app.services.wp_visibility.denial import (
    EXTERNAL_NOT_FOUND_DETAIL,
    ExternalNotFound,
    RateLimited,
)

logger = logging.getLogger(__name__)

#: design §API 的统一前缀。**唯一**真源 —— 每个路由装饰器都从它拼接，
#: 于是「某个端点少了 entry 段」在源码里立刻可见，而不是靠逐个 code review。
#:
#: 🔴 `entry_id` 必须用 `:path` 转换器。`backend/data/workpaper_sync_entry_manifest.json`
#: 里 **186 条 entry_id 全部含 `/`**，最深三段（`xlsx/d4/analysis/d4-tab-customer-price`），
#: 而默认转换器是 `[^/]+` ⇒ 写成 `{entry_id}` 时**每一个**端点在生产上都恒 404
#: （Starlette 路由不匹配，返回它自己的 `{"detail":"Not Found"}`，连 guard 都进不去）。
#: 本 spec 首轮实测正是如此：13 个场景全部拿到 Starlette 的 404 而不是 guard 的 404，
#: 而「路径模板长得对」的形态判据全绿。因此另有一条**路由匹配**判据钉住它
#: （`test_task28_sync_router.py::TestRouterShape::test_a_real_slashed_entry_id_routes`）。
#:
#: 贪婪匹配不会吞掉后缀：整条正则以 `$` 锚定，`.*` 会回溯到让 `/materialize`
#: 之类的字面后缀成立的位置。`operation_id` / `room_id` / `case_id` 仍是 `[^/]+`，
#: 所以 `/operations/{id}` 与 `/operations/{id}/conflicts` 不会互相抢。
USER_SYNC_PREFIX = (
    "/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}"
)

#: 统一门（`wp_visibility`）里本域用的 entrypoint / action。
#:
#: 🔴 **从 `action_matrix` 现取，不抄字面量**：矩阵是九维精确匹配且「未登记即拒绝」
#: （Req 7.4），所以这两个值必须与登记侧同源。抄一份字面量的后果不是「更清晰」，
#: 而是矩阵那边改名后本域**恒 404** 且没有任何测试会红 —— 这正是本行修复前的形态
#: （`entrypoint="workpaper.sync"` 全域零登记，每个 sync 端点对每个用户恒 404）。
_VISIBILITY_ENTRYPOINT: str = _MATRIX_DEDICATED_ENTRYPOINT
_VISIBILITY_READ_ACTION: str = _MATRIX_DEDICATED_READ_ACTION

router = APIRouter(prefix="", tags=["wp-sync"])

#: DocServer 调用面：不发用户 Bearer，自带 room/generation/doc_key 服务凭证。
public_router = APIRouter(prefix="", tags=["wp-sync"])


# ═══════════════════════════════════════════════════════════════════════════
# 1. 统一拒绝
# ═══════════════════════════════════════════════════════════════════════════


def _not_found() -> HTTPException:
    """404 的**唯一**构造点。

    响应体逐字节等于平台统一不可见响应：不存在、已 retire、跨 scope、无 visibility
    四种原因不得从文案上被区分（Property 45 的「同 envelope」）。
    """
    return HTTPException(status_code=404, detail=EXTERNAL_NOT_FOUND_DETAIL)


def _forbidden(exc: SyncActionForbiddenError) -> HTTPException:
    """403 的唯一构造点。带 `error_code` 让前端能区分「工作流锁定」与「无权限」。"""
    return HTTPException(
        status_code=403,
        detail={"error_code": exc.error_code, "message": str(exc)},
    )


def _conflict(exc: BaseException, *, error_code: str | None = None) -> HTTPException:
    """409 的唯一构造点。**刻意不放任何既有资源 id**。

    AC 4.1 / Property 45：另一 participant、不同 kind 或不同 frozen payload 复用同
    Idempotency-Key 一律 409 **且不得返回已有标识**。把旧 request/operation id 放进
    冲突响应，等于把别人的资源 id 交给冲突方 —— 而那在只断言「返回 409」的守卫下全绿。
    """
    return HTTPException(
        status_code=409,
        detail={
            "error_code": error_code
            or str(getattr(exc, "error_code", "") or "conflict"),
            "message": str(exc),
        },
    )


def _domain_error(exc: SyncDomainError, *, status: int) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"error_code": exc.error_code, "message": str(exc)},
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 生产装配
# ═══════════════════════════════════════════════════════════════════════════


class WpGateVisibilityProbe:
    """用平台统一门实现 project visibility / workflow lock 的观测。

    🔴 复用 `enforce_wp_gate` 而不是自己查 project.is_deleted：可见性规则（委派、
    历史版本、reviewer 白名单、跨项目）住在 `wp_visibility` 域，抄第二份的后果不是
    「偶尔不一致」，而是「同步域比平台门更宽松」—— 那正是横向越权的入口。

    `ExternalNotFound` 被**翻译**成 `project_visible=False` 而不是穿透：穿透会绕过
    本 spec 的 404 oracle（阶段/时序桶都不同），而 AC 10.6 要求同一个桶。
    `RateLimited` 原样穿透 —— 限流与资源存在性无关，不该被折叠成 404。
    """

    def __init__(self, db: AsyncSession, user: User) -> None:
        self._db = db
        self._user = user

    async def observe(
        self, *, project_id: uuid.UUID, wp_id: uuid.UUID, entry_id: str
    ) -> Mapping[str, Any]:
        from app.routers._wp_gate import enforce_wp_gate

        try:
            ctx = await enforce_wp_gate(
                self._db,
                self._user,
                # 🔴 entrypoint 必须是 **ActionMatrix 已登记**的那一个。
                #
                #    此前这里写 `entrypoint="workpaper.sync"`，而 `wp_visibility` 全域
                #    对该字符串**零登记** ⇒ `ActionMatrix.lookup()` 恒返回 None ⇒
                #    `_match_grants()` 恒空 ⇒ 统一门按 Req 7.4「未登记 action / route /
                #    method 一律默认拒绝」记 `action_denied` 并抛 `ExternalNotFound`
                #    ⇒ 本探针把它翻成 `project_visible=False` ⇒ guard 抛
                #    `ScopeProjectNotVisibleError` ⇒ **每个 sync 端点对每个用户恒 404**。
                #
                #    这是接线缺口而非权限数据问题：真库实测 admin 在目标项目有
                #    `project_assignments`（role=manager，未删）、底稿与项目均未软删，
                #    四个 action（read/write/dedicated_read/dedicated_write）却全部
                #    deny，安全 outbox 里 reason 逐条为 `action_denied` 而**不是**
                #    `not_delegated` —— 后者才是「没派工」的编码。
                #
                #    改用 `workpaper.dedicated_subroute` 不放宽任何权限：该族的登记
                #    语义正是「wp 绑定的专属组件子路由，按 HTTP method 分类」——
                #    full_power（lead/admin/supervisor_scope）与 assignee 可读可写，
                #    reviewer / History_Only 只授 `dedicated_read`（`_entry(..., "read")`）
                #    且 `g.readonly and entry.access_mode == "mutation"` 那条继续拦写。
                #    sync 端点全部形如 `/api/projects/{p}/workpapers/{wp}/sync/...`，
                #    与该族的资源绑定形态一致。
                entrypoint=_VISIBILITY_ENTRYPOINT,
                action=_VISIBILITY_READ_ACTION,
                method="GET",
                wp_id=wp_id,
                project_id=project_id,
                route_name=USER_SYNC_PREFIX,
                entry_family="workpaper",
            )
        except ExternalNotFound:
            return {"project_visible": False, "workflow_locked": False, "readonly": True}
        except RateLimited:
            raise
        return {
            "project_visible": True,
            # 统一门的 `readonly`（归档 / 复核通过 / History_Only / reviewer）就是
            # 同步域的 workflow lock：可见但不可写。
            "workflow_locked": bool(getattr(ctx, "readonly", False)),
            "readonly": bool(getattr(ctx, "readonly", False)),
            "role": str(getattr(ctx, "role", "")),
            "access_kinds": sorted(str(k) for k in (getattr(ctx, "access_kinds", ()) or ())),
        }


#: 只读 action 名单 —— 这些 action 在 `workflow_locked`（归档/复核通过/reviewer 只读）
#: 下**仍允许**。
#:
#: 🔴 必须有这份名单，是真库实测出来的：第一版让 guard 无条件按 `workflow_locked`
#: 拒绝，于是归档底稿连 conflicts/timeline 都 403（AC 11.6「显示阻断原因」与 11.11
#: 「可追溯」直接落空），而离线守卫只测了写 action 的否定侧 ⇒ 全绿。
_READ_ONLY_ACTIONS: frozenset[str] = frozenset(
    {
        "read_recovery_cases",
        "read_operation",
        "read_conflicts",
        "read_timeline",
        "download_recovery_artifact",
    }
)

#: 写 action 名单。与上一份合起来是本 router 的**全部** action 词汇表。
_WRITE_ACTIONS: frozenset[str] = frozenset(
    {
        "create_pending_mutation",
        "materialize",
        "confirm_descriptor",
        "forcesave",
        "close_intent",
        "claim_recovery_case",
        "download_only",
        "resolve_conflicts",
        "retry_apply",
        "rollback",
    }
)

#: 词汇表全集。未登记的 action 名一律 403（fail closed）。
_KNOWN_ACTIONS: frozenset[str] = _READ_ONLY_ACTIONS | _WRITE_ACTIONS


@dataclass(frozen=True)
class _SyncServices:
    """一次请求内的服务装配。**per-request**（持 session），刻意不是模块级单例。"""

    session: AsyncSession
    user_id: uuid.UUID
    repo: WorkpaperSyncRepository
    artifacts: CanonicalArtifactRepository
    resolution: CanonicalResolutionService
    content: ContentMutationService
    rooms: RoomService
    requests: RequestApplicationService
    guard: SyncEndpointGuard
    registry: WorkpaperSyncAdapterRegistry
    probe: WpGateVisibilityProbe

    @property
    def oo_to_html(self) -> OoToHtmlCoordinator:
        return OoToHtmlCoordinator(
            repo=self.repo,
            artifacts=self.artifacts,
            resolution=self.resolution,
            content=self.content,
            rooms=self.rooms,
            requests=self.requests,
            probe=self.probe,
        )

    @property
    def conflicts(self) -> ConflictResolutionService:
        return ConflictResolutionService(
            repo=self.repo,
            resolution=self.resolution,
            content=self.content,
            requests=self.requests,
            coordinator=self.oo_to_html,
        )

    def delivery(self) -> CallbackDeliveryService:
        from app.core.config import settings

        return CallbackDeliveryService(
            self.repo,
            artifacts=self.artifacts,
            download_policy=build_download_policy(
                onlyoffice_url=str(getattr(settings, "ONLYOFFICE_URL", "") or "")
            ),
            transport=build_httpx_transport(),
        )

    def close_intents(self) -> CloseIntentService:
        return CloseIntentService(
            self.repo,
            self.command_client(),
            rooms=self.rooms,
            requests=self.requests,
        )

    def command_client(self) -> CommandServiceClient:
        from app.core.config import settings

        return CommandServiceClient(
            onlyoffice_url=str(getattr(settings, "ONLYOFFICE_URL", "") or ""),
            jwt_secret=_onlyoffice_secret(),
            transport=build_httpx_command_transport(),
        )


def _secret() -> str:
    from app.core.config import settings

    # 🔴 属性名是 `JWT_SECRET_KEY`（`app/core/config.Settings`）。写成 `SECRET_KEY` 时
    # `getattr(..., "")` 恒得空串 ⇒ 本函数恒抛 ⇒ **每个**端点 500。
    # 这正是 Task 25 `build_materialize_coordinator` 里同一处笔误的形态，
    # 它在「没有生产调用方」时完全不可观测。
    key = str(getattr(settings, "JWT_SECRET_KEY", "") or "")
    if not key:
        raise SyncDomainError(
            "缺少 settings.JWT_SECRET_KEY —— 空密钥等于不签名，伪造 token/claim 即可跨 scope"
        )
    return key


def build_sync_services(
    db: AsyncSession,
    user: User,
    *,
    registry: WorkpaperSyncAdapterRegistry | None = None,
) -> _SyncServices:
    """本 router 的**唯一**装配点（与 `build_materialize_coordinator` 同理由：函数不是单例）。"""
    repo = WorkpaperSyncRepository(db)
    artifacts = CanonicalArtifactRepository(BACKEND_ROOT)
    resolution = CanonicalResolutionService(db, artifacts)
    content = ContentMutationService(
        session=db, repository=repo, artifacts=artifacts, resolution=resolution
    )
    rooms = RoomService(repo)
    probe = WpGateVisibilityProbe(db, user)
    return _SyncServices(
        session=db,
        user_id=user.id,
        repo=repo,
        artifacts=artifacts,
        resolution=resolution,
        content=content,
        rooms=rooms,
        requests=RequestApplicationService(repo, rooms),
        guard=SyncEndpointGuard(
            repository=repo,
            visibility=probe,
            authorize=_action_authorizer,
            claim_codec=ScopeClaimCodec(_secret()),
            read_only_actions=_READ_ONLY_ACTIONS,
        ),
        registry=registry if registry is not None else build_production_registry(),
        probe=probe,
    )


def _action_authorizer(scope: GuardedScope) -> bool:
    """action 名词汇表校验（guard 阶段 ⑤ 的回调）。

    只拿 :class:`GuardedScope`（显式归属 + 已观测的 visibility 事实），拿不到业务行 ——
    需要业务行才能判权限就说明 scope 模型漏了字段。

    职责刻意收窄成**一件**事：`action` 必须在本 router 登记的词汇表内。
    这不是形式主义 —— `_guard(action="reslove_conflicts")` 这种笔误在没有词汇表时
    会被当成一个**未登记的写 action**（`workflow_locked` 白名单查不到它 ⇒ 归档下
    403，其他情况一路放行），而端到端测试照样通过。有词汇表时它立刻 403 且
    `test_read_only_actions_match_the_read_endpoints_exactly` 会打红。

    * workflow 锁定 → guard 阶段 ⑤ 按注入的只读名单判（唯一实现，不在此抄第二份）；
    * lease/generation/fence/bundle 的逐条重验 → Task 21 的八条资格门（唯一实现）。
    """
    return str(scope.action) in _KNOWN_ACTIONS


async def _services(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> _SyncServices:
    """FastAPI 依赖。`get_current_user` 是**唯一** 401 产生点。"""
    return build_sync_services(db, current_user)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 固定 guard 的唯一调用面
# ═══════════════════════════════════════════════════════════════════════════


async def _guard(
    svc: _SyncServices,
    *,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    action: str,
    refs: tuple[ScopeRef, ...] = (),
    signed_claim: str | None = None,
    claim_purpose: str | None = None,
) -> GuardedScope:
    """每个 handler 的第一句。把 guard 的三族拒绝翻成 HTTP，**并且只在这里翻**。"""
    try:
        scope = await svc.guard.enforce(
            SyncEndpointRequest(
                project_id=project_id,
                wp_id=wp_id,
                entry_id=entry_id,
                action=action,
                user_id=svc.user_id,
                refs=refs,
                signed_claim=signed_claim,
                claim_purpose=claim_purpose,
            )
        )
    except SyncScopeInvisibleError as exc:
        logger.info("sync guard 404 action=%s error_code=%s", action, exc.error_code)
        raise _not_found() from exc
    except SyncActionForbiddenError as exc:
        logger.info("sync guard 403 action=%s error_code=%s", action, exc.error_code)
        raise _forbidden(exc) from exc
    except VisibilityProbeFailedError as exc:
        raise _domain_error(exc, status=http_status_for_refusal(exc)) from exc
    scope.assert_complete()
    return scope


def _room_ref(room_id: uuid.UUID) -> tuple[ScopeRef, ...]:
    return declared_refs(((ScopeResourceKind.room, room_id),))


def _entry_scope(scope: GuardedScope) -> RoomScope:
    return RoomScope(
        project_id=scope.project_id, wp_id=scope.wp_id, entry_id=scope.entry_id
    )


async def _attach_pilot_adapters(svc: _SyncServices) -> tuple[str, ...]:
    """Task 40 起的**生产接线点**：把已 finalize 的 pilot entry 接进 registry。

    放在这里（而不是 `build_sync_services`）的唯一原因是它必须读库：bundle 快照只能按
    representation 冻结的 FK 解析，不能按 registry alias 取"最新版"。`build_sync_services`
    是同步装配点，拿不到 await。

    🔴 **不吞异常**：接线失败必须让端点以可诊断错误码收场，而不是退回"registry 零注册"
    的表象 —— 后者会把「pilot 接线坏了」伪装成「这个 entry 还没做 adapter」。
    """
    # Task 41 起：每个 pilot 各自一份 contract/bundle/candidate，接线也各自一条 ——
    # 复用另一个 pilot 的 attach 就等于复用它的契约（任务正文明令禁止）。
    from app.services.workpaper_sync.pilot_d2_large_json import (
        attach_pilot_adapters as attach_d2_pilot_adapters,
    )
    # Task 42 追加（只加不动）：H1 pilot 各自一条 attach，不复用别的 pilot 的契约。
    from app.services.workpaper_sync.pilot_h1_grouped_dynamic import (
        attach_pilot_adapters as attach_h1_pilot_adapters,
    )
    from app.services.workpaper_sync.pilot_simple_checklist import attach_pilot_adapters
    # Task 43 追加（只加不动）：G7 pilot 各自一条 attach，不复用别的 pilot 的契约。
    from app.services.workpaper_sync.pilot_g7_two_level_dynamic import (
        attach_pilot_adapters as attach_g7_pilot_adapters,
    )

    explicit = (
        await attach_pilot_adapters(svc.registry, session=svc.session)
        + await attach_d2_pilot_adapters(svc.registry, session=svc.session)
        + await attach_h1_pilot_adapters(svc.registry, session=svc.session)
        + await attach_g7_pilot_adapters(svc.registry, session=svc.session)
    )
    # Task 75 追加（只加不动）：manifest 驱动的注册 —— 覆盖**全部** 186 条 entry，
    # 并为每条未注册 entry 给出显式原因（`outcome.reasons`）。四条 pilot attach 保留在
    # 上面：计划里每个 entry 仍派发到它**自己**的 attach（不共用），本次 pass 会发现它们
    # 已注册并原样计入。零注册不再是「没人来注册」，而是可读的供给原因。
    outcome = await svc.registry.register_from_manifest(session=svc.session)
    return tuple(dict.fromkeys((*explicit, *outcome.registered_adapter_ids)))


async def _registration(svc: _SyncServices, scope: GuardedScope):
    """按 entry 解析唯一 adapter + approved bundle；未注册即 422（fail visible）。

    🔴 不写 `try: ... except: return None` 兜底：registry 的逐 entry 注册由
    Tasks 40~57 / 62~64 接线，兜底会把「这个 entry 还没做 adapter」表现成
    「同步成功但什么都没变」。
    """
    from app.services.workpaper_sync.adapters.registry import RegistryError

    await _attach_pilot_adapters(svc)
    try:
        return svc.registry.assert_bidirectional_ready(scope.entry_id)
    except (RegistryError, SyncDomainError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": str(getattr(exc, "error_code", "adapter_not_ready")),
                "message": str(exc),
            },
        ) from exc


# ═══════════════════════════════════════════════════════════════════════════
# 4. HTML → OO
# ═══════════════════════════════════════════════════════════════════════════


@router.post(USER_SYNC_PREFIX + "/pending-mutations")
async def create_pending_mutation(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    payload: Mapping[str, Any] = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """`flushHtml()` 的落点。**不推进 revision**（AC 3.1）。

    create 端点没有 opaque resource id 可查 ⇒ `refs=()`（见 `endpoint_guard` 模块
    docstring）。显式 route scope、visibility 与 action 三关照旧。
    """
    scope = await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="create_pending_mutation",
    )
    coordinator = build_materialize_coordinator(svc.session, secret=_secret())
    request = await _materialize_request(
        svc,
        scope=scope,
        payload=payload,
        idempotency_key=idempotency_key,
        pending_mutation_token=None,
    )
    try:
        authorized = await coordinator.authorize_create(request)
        receipt = await coordinator.create_pending_mutation(authorized)
    except SyncDomainError as exc:
        raise _domain_error(
            exc, status=classify_materialize_rejection(exc)
        ) from exc
    return receipt.as_dict()


@router.post(USER_SYNC_PREFIX + "/materialize")
async def materialize(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    payload: Mapping[str, Any] = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """唯一 `EditorLaunchDescriptor`（Property 11）。签名 `document.url` 在**本处**加。"""
    token = str(payload.get("pending_mutation_token") or "").strip() or None
    scope = await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="materialize",
    )
    coordinator = build_materialize_coordinator(svc.session, secret=_secret())
    request = await _materialize_request(
        svc,
        scope=scope,
        payload=payload,
        idempotency_key=idempotency_key,
        pending_mutation_token=token,
    )
    try:
        authorized = await coordinator.authorize(request)
        outcome = await coordinator.materialize(authorized)
    except SyncDomainError as exc:
        raise _domain_error(exc, status=classify_materialize_rejection(exc)) from exc
    if outcome.descriptor is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "descriptor_unavailable",
                "message": "materialize 未产出 descriptor —— 不得挂载半个 descriptor",
            },
        )
    body = outcome.descriptor.as_dict()
    body["replayed"] = bool(outcome.replayed)
    return body


async def _materialize_request(
    svc: _SyncServices,
    *,
    scope: GuardedScope,
    payload: Mapping[str, Any],
    idempotency_key: str,
    pending_mutation_token: str | None,
) -> MaterializeRequest:
    """body → :class:`MaterializeRequest`。

    route 已显式给出 project/wp/entry；payload 若**保留** `entry_id` 必须逐字相等
    （design §API）。不相等时按 404 oracle 处理：那是「用另一个 entry 的 scope 组合
    本 entry 的 route」，与横向越权同型。

    `capability` 从 manifest 取、`value_type`/`mode` 从 approved contract 取 ——
    两者都**不从客户端读**：capability 决定「这个 entry 能不能产出 OO artifact」
    （AC 3.9），contract 决定金额口径与保护策略（AC 6.1/6.5）。让客户端声明它们
    等于让它自己开门。
    """
    declared = payload.get("entry_id")
    if declared is not None and str(declared) != scope.entry_id:
        raise _not_found()
    registration = await _registration(svc, scope)
    contract = registration.contract
    if contract is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "per_entry_contract_required",
                "message": (
                    f"entry {scope.entry_id!r} 的 registration 没有 approved contract —— "
                    "projection 无法按 stable key 解释（AC 3.3）"
                ),
            },
        )
    try:
        projection = build_projection(payload=payload.get("projection"), contract=contract)
    except SyncDomainError as exc:
        raise _sync_http(exc) from exc
    return MaterializeRequest(
        project_id=scope.project_id,
        wp_id=scope.wp_id,
        entry_id=scope.entry_id,
        sheet_key=str(payload.get("sheet_key") or ""),
        user_id=scope.user_id,
        expected_revision=int(payload.get("expected_revision") or 0),
        idempotency_key=str(idempotency_key),
        capability=_capability_of(scope.entry_id),
        projection=projection,
        contract=contract,
        adapter=registration.adapter,
        adapter_id=str(registration.adapter_id),
        pending_mutation_token=pending_mutation_token,
        client_edit_epoch=int(payload.get("client_edit_epoch") or 0),
    )


def _scope_only_request(
    *, scope: GuardedScope, sheet_key: str, idempotency_key: str
) -> MaterializeRequest:
    """只带 scope 的 :class:`MaterializeRequest`（`confirm-descriptor` 用）。

    `confirm_descriptor` 只需要 `authorized.request.scope` 与显式 project/wp/entry；
    它比对的是**服务端事实 vs 前端回传的 identity**，与 projection 内容无关。

    🔴 因此这里刻意**不**查 adapter registry：confirm-descriptor 是身份确认端点，
    把它耦合到 registry 会让「模板刚升级、adapter 还没重注册」变成「已打开的编辑器
    无法完成 ready 确认」，而那条路径本来完全合法（bundle identity 仍是旧的那一份）。
    """
    from app.services.workpaper_sync.endpoint_payloads import scope_only_projection

    return MaterializeRequest(
        project_id=scope.project_id,
        wp_id=scope.wp_id,
        entry_id=scope.entry_id,
        sheet_key=sheet_key,
        user_id=scope.user_id,
        expected_revision=0,
        idempotency_key=idempotency_key,
        capability=_capability_of(scope.entry_id),
        projection=scope_only_projection(),
        pending_mutation_token=None,
    )


def _capability_of(entry_id: str):
    """entry 的 capability 只从 manifest 取（AC 1.1 的单一真源）。

    manifest 里没有这个 entry ⇒ 422 而不是「按 bidirectional 处理」：
    未登记 entry 被当双向处理会创建空白 OO artifact（AC 3.9 明令禁止）。
    """
    from app.services.workpaper_sync.entry_profile import (
        capability_of,
        manifest_entries_by_id,
    )

    entry = manifest_entries_by_id().get(str(entry_id))
    if entry is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "entry_not_in_manifest",
                "message": (
                    f"entry {entry_id!r} 不在 workpaper_sync_entry_manifest 中 —— "
                    "未登记 entry 不得按 bidirectional 处理（AC 1.1 / 3.9）"
                ),
            },
        )
    return capability_of(entry)


@router.post(USER_SYNC_PREFIX + "/rooms/{room_id}/confirm-descriptor")
async def confirm_descriptor(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    room_id: uuid.UUID,
    payload: Mapping[str, Any] = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """`onDocumentReady` 之后的幂等确认。成功前不得 forcesave（Property 11）。"""
    scope = await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="confirm_descriptor",
        refs=_room_ref(room_id),
    )
    participant_id = _uuid_field(payload, "participant_id")
    coordinator = build_materialize_coordinator(svc.session, secret=_secret())
    authorized = await coordinator.authorize_create(
        _scope_only_request(
            scope=scope,
            sheet_key=str(payload.get("sheet_key") or scope.entry_id),
            idempotency_key=str(idempotency_key),
        )
    )
    try:
        confirmation = await coordinator.confirm_descriptor(
            authorized,
            room_id=room_id,
            participant_id=participant_id,
            echoed=payload,
            idempotency_key=str(idempotency_key),
        )
    except SyncDomainError as exc:
        raise _sync_http(exc) from exc
    return confirmation.as_dict()


# ═══════════════════════════════════════════════════════════════════════════
# 5. OO 侧写请求：forcesave / close-intents
# ═══════════════════════════════════════════════════════════════════════════


@router.post(USER_SYNC_PREFIX + "/rooms/{room_id}/forcesave", status_code=202)
async def request_forcesave(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    room_id: uuid.UUID,
    payload: Mapping[str, Any] = Body(default={}),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """202 accepted：frozen request + `application_id=NULL` shell 先落库，再出站。

    幂等范围是 `(room, generation, initiated_by_participant_id, kind, key)`，且只有
    `frozen_request_fingerprint` 逐项等值才返回同 request/operation ——
    两者都由 Task 23 的复合唯一键实现，本处**不**自己比一遍（抄第二份必然漂移）。
    跨 participant / 不同 kind / 不同 frozen payload ⇒ 409 且不返回旧标识。
    """
    scope = await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="forcesave",
        refs=_room_ref(room_id),
    )
    participant_id = _uuid_field(payload, "participant_id")
    kind = str(payload.get("kind") or RequestKind.forcesave.value)
    if kind != RequestKind.forcesave.value:
        # AC 4.4：客户端不得直接创建 `close_capture` —— 那只能由 room arbiter 在锁内 CAS。
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "close_capture_forbidden",
                "message": "clean close 必须走 close-intents 仲裁，不得直接发起 close_capture",
            },
        )
    try:
        accepted = await svc.requests.freeze_and_persist_request(
            _entry_scope(scope),
            room_id=room_id,
            participant_id=participant_id,
            idempotency_key=str(idempotency_key),
            client_edit_epoch=int(payload.get("client_edit_epoch") or 0),
            kind=RequestKind.forcesave,
            contributor_user_ids=tuple(payload.get("contributor_user_ids") or ()),
            expected_write_fence_epoch=_int_or_none(payload.get("expected_write_fence_epoch")),
            created_by=scope.user_id,
        )
        await svc.session.commit()
    except IdempotencyConflictError as exc:
        await svc.session.rollback()
        # 409 是**协议要求的拒绝**，不是 error：跨 participant / 不同 kind / 不同 frozen
        # payload 复用同一 Idempotency-Key 时必须拒绝且不返回旧标识。压进通用 error 会让
        # 值班按重试 runbook 处理一个「前端在串键」的接线缺陷（Task 29 明文禁止压平）。
        sync_metrics.record_outcome(
            "workpaper_sync_forcesave_fingerprint_conflict_total",
            result="cross_participant",
            landed=False,
            room_id=room_id,
            generation=_int_or_none(payload.get("generation")) or 0,
            participant_id=participant_id,
        )
        raise _conflict(exc) from exc
    except SyncDomainError as exc:
        await svc.session.rollback()
        raise _sync_http(exc) from exc
    dispatch_error: str | None = None
    try:
        room = await svc.requests.room_of(room_id)
        await svc.command_client().forcesave(
            accepted, target=_command_target(accepted, room=room)
        )
    except SyncDomainError as exc:
        # 出站失败不回滚已落库的 frozen request/shell：AC 4.1 的顺序是「先落库再出站」，
        # 回滚会让重放拿到新的 request id，复合幂等键就白写了。失败原样透出。
        dispatch_error = exc.error_code
        logger.warning("forcesave 出站失败 room=%s error_code=%s", room_id, exc.error_code)
    # 🔴 `result` 从 `dispatch_error` **显式**推导，不是「没抛异常就 accepted」：
    # Command Service HTTP 200 都不等于保存完成（AC 4.1 末句），出站失败更不等于。
    sync_metrics.record_outcome(
        "workpaper_sync_forcesave_accepted_total",
        result="accepted" if dispatch_error is None else "rejected",
        landed=False,
        room_id=room_id,
        generation=int(accepted.request.generation),
        participant_id=participant_id,
    )
    return {
        "forcesave_request_id": str(accepted.request.id),
        "operation_id": str(accepted.operation.id),
        "request_sequence": int(accepted.request_sequence),
        "state": "accepted",
        "poll_after_ms": 500,
        "replayed": bool(accepted.cache_hit),
        "dispatch_error": dispatch_error,
    }


def _command_target(accepted: Any, *, room: Any):
    """出站目标的 doc_key 只能取自 **room 行**。

    🔴 不从 request 上取：`working_paper_forcesave_request` 没有 doc_key 列，而
    「冻结身份」里对应的是 room 的 `(room_id, generation, doc_key)` 三元组 ——
    `CommandServiceClient` 会拿 target 与凭据里冻结的 room/generation 逐项比对，
    doc_key 与 generation 不同源时它就抓不到「跨代际出站」这一类错误。
    """
    from app.services.workpaper_sync.command_service import CommandTarget

    return CommandTarget(
        doc_key=str(room.doc_key),
        room_id=room.id,
        generation=int(accepted.request.generation),
    )


def _onlyoffice_secret() -> str:
    from app.core.config import settings

    secret = str(getattr(settings, "ONLYOFFICE_JWT_SECRET", "") or "")
    if not secret:
        raise SyncDomainError(
            "缺少 ONLYOFFICE_JWT_SECRET —— 未签名的 Command Service 调用一律不发"
        )
    return secret


@router.post(USER_SYNC_PREFIX + "/rooms/{room_id}/close-intents", status_code=202)
async def create_close_intent(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    room_id: uuid.UUID,
    payload: Mapping[str, Any] = Body(default={}),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """clean close 的唯一入口。leader 仲裁与 exactly-one close-capture 在 Task 24。"""
    scope = await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="close_intent",
        refs=_room_ref(room_id),
    )
    participant_id = _uuid_field(payload, "participant_id")
    try:
        opened = await svc.close_intents().open_close_intent(
            _entry_scope(scope),
            room_id=room_id,
            participant_id=participant_id,
            idempotency_key=str(idempotency_key),
            client_edit_epoch=int(payload.get("client_edit_epoch") or 0),
            adapter_build_digest=str(payload.get("adapter_build_digest") or ""),
            contributor_snapshot_digest=str(payload.get("contributor_snapshot_digest") or ""),
            contributor_user_ids=tuple(payload.get("contributor_user_ids") or ()),
            expected_write_fence_epoch=_int_or_none(payload.get("expected_write_fence_epoch")),
            created_by=scope.user_id,
            actor_id=scope.user_id,
        )
        await svc.session.commit()
    except IdempotencyConflictError as exc:
        await svc.session.rollback()
        raise _conflict(exc) from exc
    except SyncDomainError as exc:
        await svc.session.rollback()
        raise _sync_http(exc) from exc
    await _record_close_metrics(
        svc.session,
        room_id=room_id,
        participant_id=participant_id,
        opened=opened,
    )
    return {
        "close_intent_id": str(opened.intent_id),
        "intent_sequence": int(opened.intent_sequence),
        "participant_id": str(opened.participant_id),
        "remaining_active_editors": int(opened.remaining_active_editors),
        # 仍有其他 active editor 时，本 participant 先出一个普通 forcesave predecessor。
        "ordinary_forcesave_request_id": (
            None
            if opened.predecessor is None
            else str(opened.predecessor.accepted.request.id)
        ),
        # exactly-one close-capture 的可观测事实（`>1` 由 Task 24 在锁内即抛）。
        "open_capture_count": int(opened.reconcile.open_capture_count),
        "live_intent_count": int(opened.reconcile.live_intent_count),
    }


async def _record_close_metrics(
    db: AsyncSession,
    *,
    room_id: uuid.UUID,
    participant_id: uuid.UUID,
    opened: Any,
) -> None:
    """close barrier 的三条指标。

    🔴 **三个专用指标而不是一个 error**（Task 29 明文禁止压平）：

    * `close_capture_total{result=promoted}` —— exactly-one 的观测面。同 (room,
      generation) 出现第二条 `promoted` 就是 AC 4.10 被破坏，规则阈值正好是 2；
    * `close_leader_authorization_stale_total` —— leader promotion 前失去资格并选出
      successor。这是**正常运行态**（协同里撤权随时发生）；
    * `close_leader_recovery_required_total{result=no_successor}` —— 无合法 successor，
      generation supersede + 显式 `recovery_required`。它的 runbook 是「重新授权后从新
      generation 恢复」，与任何重试类 error 无关。

    `generation` 取自 **close intent 行**：`CloseIntentOpened` 不带 generation，而
    post-commit 去读 room 行可能已经轮转（no-successor 分支恰恰会 supersede
    generation）—— intent 行记的是本次仲裁发生时的那个 generation，是不可变事实。
    """
    from app.models.workpaper_sync_models import WorkpaperOoCloseIntent

    generation = (
        await db.execute(
            sa.select(WorkpaperOoCloseIntent.generation).where(
                WorkpaperOoCloseIntent.id == opened.intent_id
            )
        )
    ).scalar_one_or_none()
    if generation is None:
        logger.error("close 指标记录失败：intent %s 不存在", opened.intent_id)
        return
    reconcile = opened.reconcile
    labels = {
        "room_id": room_id,
        "generation": int(generation),
        "participant_id": participant_id,
    }
    if reconcile.no_successor:
        sync_metrics.record_outcome(
            "workpaper_sync_close_leader_recovery_required_total",
            result="no_successor",
            landed=False,
            **labels,
        )
    elif reconcile.leader_intent_id is not None:
        sync_metrics.record_outcome(
            "workpaper_sync_close_capture_total",
            result="promoted" if reconcile.capture_created else "cache_hit",
            landed=False,
            **labels,
        )
    if reconcile.repository.authorization_stale_intent_ids:
        sync_metrics.record_outcome(
            "workpaper_sync_close_leader_authorization_stale_total",
            result="successor_selected" if not reconcile.no_successor else "leader_promoted_then_stale",
            landed=False,
            value=float(len(reconcile.repository.authorization_stale_intent_ids)),
            **labels,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 6. recovery cases
# ═══════════════════════════════════════════════════════════════════════════


@router.get(USER_SYNC_PREFIX + "/recovery-cases")
async def list_recovery_cases(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    room_id: uuid.UUID = Query(...),
    generation: int = Query(...),
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """read-mode guard 通过后才查 case（AC 5.8 / Property 45）。

    🔴 `room_id` / `generation` 是**必填** query：AC 10.6 明文「recovery list 明确
    entry/room scope」。可选化会让「列出这个 wp 下所有 case」成为存在性泄露面。
    `generation` 必须与 room 的 scope row 逐项相符 —— 那是 scope index 里的非敏感字段，
    不需要读 room 行。
    """
    room_ref = ScopeRef(resource_kind=ScopeResourceKind.room, resource_id=str(room_id))
    scope = await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="read_recovery_cases",
        refs=(room_ref,),
    )
    indexed_generation = scope.generation_of(room_ref)
    if indexed_generation is None or int(indexed_generation) != int(generation):
        # 显式 generation 与 scope index 的归属不符 ⇒ 同 404 oracle（跨 scope 同型）。
        raise _not_found()
    cases = await _load_recovery_cases(svc, room_id=room_id, generation=int(generation))
    return {
        "room_id": str(room_id),
        "generation": int(generation),
        "cases": cases,
    }


async def _load_recovery_cases(
    svc: _SyncServices, *, room_id: uuid.UUID, generation: int
) -> list[dict[str, Any]]:
    """候选 prior confirmation 摘要 + `claim/download-only` 能力，**零业务内容**。

    AC 5.8：不返回业务内容或未授权资源存在性。因此这里只投影 reason/state/
    候选 confirmation id 与能力布尔 —— 没有 hash、没有整稿、没有 artifact 路径。
    """
    from app.models.workpaper_sync_models import (
        WorkpaperCallbackRecoveryCase,
        WorkpaperOoClientConfirmation,
    )

    rows = list(
        (
            await svc.session.execute(
                sa.select(WorkpaperCallbackRecoveryCase)
                .where(
                    WorkpaperCallbackRecoveryCase.room_id == room_id,
                    WorkpaperCallbackRecoveryCase.generation == generation,
                )
                .order_by(WorkpaperCallbackRecoveryCase.created_at)
            )
        ).scalars()
    )
    if not rows:
        return []
    candidates = list(
        (
            await svc.session.execute(
                sa.select(
                    WorkpaperOoClientConfirmation.id,
                    WorkpaperOoClientConfirmation.participant_id,
                    WorkpaperOoClientConfirmation.content_version_id,
                    WorkpaperOoClientConfirmation.confirmed_at,
                )
                .where(WorkpaperOoClientConfirmation.room_id == room_id)
                .order_by(WorkpaperOoClientConfirmation.confirmed_at.desc())
            )
        ).all()
    )
    summary = [
        {
            "confirmation_id": str(c[0]),
            "participant_id": str(c[1]),
            "content_version_id": str(c[2]),
            "confirmed_at": c[3].isoformat() if c[3] is not None else None,
        }
        for c in candidates
    ]
    # 🔴 终态集从**状态机登记表**取，不写字符串字面量。
    # 第一版写死了 `("claimed", "download_only", "quarantined", "expired")`，
    # 而 `RecoveryCaseState` 里根本没有 `claimed`（真实值是 `application_created`）——
    # 后果是「已 claim 的 case 仍然显示可 claim/可 download-only」，前端据此给出两个
    # 按钮，点下去才由服务端拒绝。字面量与枚举漂移在功能测试里完全看不出来。
    from app.services.workpaper_sync.models import RecoveryCaseState, TERMINAL_STATES

    terminal_states = {s.value for s in TERMINAL_STATES["recovery_case"]} | {
        RecoveryCaseState.application_created.value
    }
    out: list[dict[str, Any]] = []
    for case in rows:
        terminal = str(case.state) in terminal_states
        out.append(
            {
                "case_id": str(case.id),
                "reason": str(case.reason),
                "state": str(case.state),
                # claim 前三实体全空 —— 这三个 None 就是 AC 5.8 的可观测事实。
                "operation_id": (
                    None if case.operation_id is None else str(case.operation_id)
                ),
                "application_id": (
                    None if case.application_id is None else str(case.application_id)
                ),
                "forcesave_request_id": (
                    None
                    if case.recovery_request_id is None
                    else str(case.recovery_request_id)
                ),
                "candidate_prior_confirmations": summary,
                "actions": {
                    "claim": not terminal,
                    "download_only": not terminal,
                },
            }
        )
    return out


@router.post(USER_SYNC_PREFIX + "/recovery-cases/{case_id}/claim", status_code=202)
async def claim_recovery_case(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    case_id: uuid.UUID,
    payload: Mapping[str, Any] = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """authorization-first claim：一个事务里 request + shell + application + scope rows。

    claim **之前** request/application/operation 三者为空；commit **之前** shell 必须
    已落成 primary 或 direct terminal duplicate（Task 23 的 `assert_recovery_claim_shape`
    在 commit 前跑）。客户端不得提交任意 base/bundle —— 服务端自行从候选 confirmation
    与 approved bundle 冻结。
    """
    case_ref = ScopeRef(
        resource_kind=ScopeResourceKind.recovery_case, resource_id=str(case_id)
    )
    scope = await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="claim_recovery_case",
        refs=(case_ref,),
    )
    # 🔴 room 归属取自 **scope index 的非敏感字段**，不取客户端提交值：
    # 客户端给的 `room_id` 只做**事后**一致性核对（不符 ⇒ 同 404 oracle）。
    # 反过来（拿客户端 room_id 去查 scope index）等于让它选择授权对象。
    declared_room = payload.get("room_id")
    indexed_room = scope.room_id_of(case_ref)
    if declared_room is not None and (
        indexed_room is None or str(indexed_room) != str(declared_room)
    ):
        raise _not_found()
    prior_confirmation_id = _uuid_field(payload, "prior_confirmation_id")
    adapter_id, adapter_build_digest = await _frozen_adapter_of_confirmation(
        svc, confirmation_id=prior_confirmation_id
    )
    # 🔴 contributor snapshot digest 由**服务端**从 room 的现存 participant 算出，
    # 不从请求体读：design §API 明文「客户端不得提交任意 base/bundle」，而 contributor
    # 集合决定 AC 10.10 最终 fence 的第 8 条（contributor 漂移必须阻止提交）。
    # 让客户端提交它 = 让它自己决定「谁参与了这次写入」。
    contributor_digest = await _contributor_digest_of_room(
        svc, room_id=indexed_room, generation=scope.generation_of(case_ref)
    )
    try:
        outcome = await svc.requests.claim_recovery(
            case_id=case_id,
            claiming_participant_id=_uuid_field(payload, "participant_id"),
            prior_confirmation_id=prior_confirmation_id,
            idempotency_key=str(idempotency_key),
            adapter_id=adapter_id,
            adapter_build_digest=adapter_build_digest,
            contributor_snapshot_digest=contributor_digest,
            current_revision=int(payload.get("expected_current_revision") or 0),
            actor_id=scope.user_id,
        )
        await svc.session.commit()
    except IdempotencyConflictError as exc:
        await svc.session.rollback()
        raise _conflict(exc) from exc
    except SyncDomainError as exc:
        await svc.session.rollback()
        raise _sync_http(exc) from exc
    # claim 的结果分型来自 outcome 本身（新建 application 还是命中既有同 key
    # application），不是「有没有抛异常」。room/generation 取自 **case 行**：它是这次
    # 恢复所属 generation 的不可变事实。
    # `shape` 是**真实存在**的判别字段：`primary` = 本 shell 新建并绑定了 application，
    # `duplicate` = 命中既有同 key application 并落成 direct terminal duplicate。
    # 刻意不用 `getattr(outcome, "...", False)` —— 默认值会把「字段名写错」变成
    # 「永远记成 created」，而四层静态检查全绿（本 spec 反复踩过的形态）。
    sync_metrics.record_outcome(
        "workpaper_sync_recovery_claim_total",
        result=(
            "application_hit"
            if outcome.shape is OperationShape.duplicate
            else "application_created"
        ),
        landed=True,
        room_id=outcome.case.room_id,
        generation=int(outcome.case.generation),
        participant_id=outcome.case.claimed_by_participant_id,
    )
    return {
        "case_id": str(case_id),
        "forcesave_request_id": str(outcome.request.id),
        "operation_id": str(outcome.operation.id),
        "application_id": (
            None if outcome.application is None else str(outcome.application.id)
        ),
        "state": str(outcome.case.state),
    }


async def _contributor_digest_of_room(
    svc: _SyncServices, *, room_id: uuid.UUID | None, generation: int | None
) -> str:
    """按 room 现存 **edit** participant 的 user 集合算 contributor snapshot digest。

    复用 `rooms.compute_contributor_snapshot_digest`（唯一实现）—— 抄第二份的后果是
    「claim 冻结的 digest 与 forcesave 路径算出来的不同」，于是 AC 10.10 第 8 条
    （contributor 漂移阻止提交）会在**所有** recovery claim 上误报。
    """
    from app.models.workpaper_sync_models import WorkpaperOoParticipant
    from app.services.workpaper_sync.models import ParticipantMode, ParticipantState
    from app.services.workpaper_sync.rooms import compute_contributor_snapshot_digest

    if room_id is None or generation is None:
        raise _not_found()
    user_ids = sorted(
        {
            str(uid)
            for uid in (
                await svc.session.execute(
                    sa.select(WorkpaperOoParticipant.user_id).where(
                        WorkpaperOoParticipant.room_id == room_id,
                        WorkpaperOoParticipant.mode == ParticipantMode.edit.value,
                        WorkpaperOoParticipant.state.in_(
                            (
                                ParticipantState.active.value,
                                ParticipantState.closing.value,
                            )
                        ),
                    )
                )
            ).scalars()
        }
    )
    return compute_contributor_snapshot_digest(
        room_id=room_id, generation=int(generation), contributor_user_ids=user_ids
    )


async def _frozen_adapter_of_confirmation(
    svc: _SyncServices, *, confirmation_id: uuid.UUID | None
) -> tuple[str, str]:
    """claim 冻结的 adapter identity 只能来自**候选 confirmation 的 representation**。

    🔴 不取 registry 的当前 alias、也不接受客户端提交：AC 5.8 / 7.10 要求历史 retry
    只读 frozen identity。用当前 registry 会让「模板已升级」的 case claim 出一个与
    incoming 不同代际的 adapter build，extract 出来的字段少一半而没有任何报错。
    与 `rooms.py` 的 `rep.adapter_build_digest` 是**同一个真源**。
    """
    from app.models.workpaper_sync_models import (
        WorkpaperContentRepresentation,
        WorkpaperOoClientConfirmation,
    )

    if confirmation_id is None:
        raise _not_found()
    row = (
        await svc.session.execute(
            sa.select(
                WorkpaperContentRepresentation.adapter_id,
                WorkpaperContentRepresentation.adapter_build_digest,
            )
            .join(
                WorkpaperOoClientConfirmation,
                WorkpaperOoClientConfirmation.representation_id
                == WorkpaperContentRepresentation.id,
            )
            .where(WorkpaperOoClientConfirmation.id == confirmation_id)
        )
    ).first()
    if row is None:
        raise _not_found()
    return str(row[0]), str(row[1])


@router.post(USER_SYNC_PREFIX + "/recovery-cases/{case_id}/download-only")
async def terminate_recovery_download_only(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    case_id: uuid.UUID,
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """只终结 case 并签发**短期最小权限**下载 claim；三实体保持为 0（AC 5.8）。"""
    case_ref = ScopeRef(
        resource_kind=ScopeResourceKind.recovery_case, resource_id=str(case_id)
    )
    scope = await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="download_only",
        refs=(case_ref,),
    )
    try:
        case = await svc.delivery().terminate_download_only(
            case_id=case_id, actor_id=scope.user_id
        )
        await svc.session.commit()
    except SyncDomainError as exc:
        await svc.session.rollback()
        raise _sync_http(exc) from exc
    claim = svc.guard.mint_claim(
        scope=scope,
        ref=case_ref,
        purpose="recovery_download",
        ttl=timedelta(minutes=10),
    )
    # download-only 的判据是「三实体保持为 0」，所以指标也从 **case 行**读这三个 FK 再
    # 记，而不是无条件记 `terminated`：真出现三实体不为 0 时必须能从指标看出来。
    terminated_cleanly = (
        case.recovery_request_id is None
        and case.application_id is None
        and case.operation_id is None
    )
    sync_metrics.record_outcome(
        "workpaper_sync_recovery_download_only_total",
        result="terminated" if terminated_cleanly else "rejected",
        landed=True,
        room_id=case.room_id,
        generation=int(case.generation),
    )
    return {
        "case_id": str(case.id),
        "state": str(case.state),
        "download_claim": claim,
        "expires_in_seconds": 600,
    }


@router.get(USER_SYNC_PREFIX + "/recovery-cases/{case_id}/download")
async def download_recovery_artifact(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    case_id: uuid.UUID,
    claim: str = Query(...),
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """download-only 签发的 claim 的**唯一**消费方。

    没有消费方的签名就是死代码：签发端会一直「看起来安全」，而没人证明验签真的发生。
    guard 在此额外做 signed-claim 三向比对（route ↔ claim ↔ index）。
    """
    case_ref = ScopeRef(
        resource_kind=ScopeResourceKind.recovery_case, resource_id=str(case_id)
    )
    await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="download_recovery_artifact",
        refs=(case_ref,),
        signed_claim=claim,
        claim_purpose="recovery_download",
    )
    from app.models.workpaper_sync_models import (
        WorkpaperArtifact,
        WorkpaperCallbackRecoveryCase,
    )

    row = (
        await svc.session.execute(
            sa.select(WorkpaperCallbackRecoveryCase).where(
                WorkpaperCallbackRecoveryCase.id == case_id
            )
        )
    ).scalar_one_or_none()
    if row is None or row.incoming_artifact_id is None:
        raise _not_found()
    artifact = (
        await svc.session.execute(
            sa.select(WorkpaperArtifact).where(
                WorkpaperArtifact.id == row.incoming_artifact_id
            )
        )
    ).scalar_one_or_none()
    if artifact is None:
        raise _not_found()
    return {
        "case_id": str(case_id),
        "artifact_id": str(artifact.id),
        "artifact_sha256": str(artifact.sha256),
        "document_type": str(artifact.document_type),
        "size_bytes": int(artifact.size_bytes or 0),
        "relative_path": str(artifact.relative_path),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 7. operation 查询 / 冲突 / timeline
# ═══════════════════════════════════════════════════════════════════════════


def _operation_ref(operation_id: uuid.UUID) -> ScopeRef:
    return ScopeRef(
        resource_kind=ScopeResourceKind.sync_operation, resource_id=str(operation_id)
    )


@router.get(USER_SYNC_PREFIX + "/operations/{operation_id}")
async def get_operation(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    operation_id: uuid.UUID,
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """按**调用方给的** id 授权，再 canonicalize（禁止授权前 canonical 跳转）。"""
    await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="read_operation",
        refs=(_operation_ref(operation_id),),
    )
    try:
        canonical = await svc.requests.read_operation(
            operation_id=operation_id,
            declared_project_id=project_id,
            declared_wp_id=wp_id,
            declared_entry_id=entry_id,
            action="read_operation",
            require_application=False,
        )
    except SyncDomainError as exc:
        raise _sync_http(exc) from exc
    op = canonical.canonical_operation
    # 🔴 result revision / bundle identity / 冲突数只在 primary **绑定 application 之后**
    # 才存在（design §API：「primary 绑定后从 application 解析」）。pre-correlation shell
    # 的 `application_id` 为 NULL 是**正确**形态，此处必须投影成 null 而不是 0/""——
    # 0 会被前端读成「零冲突已完成」，那正是 shell 阶段最不该显示的结论。
    app_facts: dict[str, Any] = {
        "result_revision": None,
        "conflict_count": None,
        "logical_result_code": None,
        "definition_bundle_id": None,
        "definition_bundle_sha256": None,
        "authority_model_definition_sha256": None,
        "durable_at": None,
        "finished_at": None,
    }
    if op.application_id is not None:
        from app.models.workpaper_sync_models import WorkpaperContentApplication

        row = (
            await svc.session.execute(
                sa.select(WorkpaperContentApplication).where(
                    WorkpaperContentApplication.id == op.application_id
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            app_facts = {
                "result_revision": (
                    None if row.result_revision is None else int(row.result_revision)
                ),
                "conflict_count": int(row.conflict_count or 0),
                "logical_result_code": (
                    None
                    if row.logical_result_code is None
                    else str(row.logical_result_code)
                ),
                "definition_bundle_id": str(row.definition_bundle_id),
                "definition_bundle_sha256": str(row.definition_bundle_sha256),
                "authority_model_definition_sha256": str(
                    row.authority_model_definition_sha256
                ),
                "durable_at": row.durable_at.isoformat() if row.durable_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            }
    return {
        "requested_operation_id": str(canonical.requested_operation.id),
        "canonical_operation_id": str(op.id),
        "followed_duplicate": bool(canonical.followed_duplicate),
        "state": str(op.state),
        "application_id": (None if op.application_id is None else str(op.application_id)),
        "duplicate_of_operation_id": (
            None
            if canonical.requested_operation.duplicate_of_operation_id is None
            else str(canonical.requested_operation.duplicate_of_operation_id)
        ),
        "error_code": (None if op.error_code is None else str(op.error_code)),
        "error_stage": (None if op.error_stage is None else str(op.error_stage)),
        "accepted_at": op.accepted_at.isoformat() if op.accepted_at else None,
        "application_bound_at": (
            op.application_bound_at.isoformat() if op.application_bound_at else None
        ),
        "operation_finished_at": op.finished_at.isoformat() if op.finished_at else None,
        **app_facts,
    }


@router.get(USER_SYNC_PREFIX + "/operations/{operation_id}/conflicts")
async def get_operation_conflicts(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    operation_id: uuid.UUID,
    include_superseded: bool = Query(default=False),
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """canonical primary 的冲突分组。requested/canonical ids 都留在响应里。"""
    scope = await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="read_conflicts",
        refs=(_operation_ref(operation_id),),
    )
    registration = await _registration(svc, scope)
    try:
        preview = await svc.conflicts.preview(
            operation_id=operation_id,
            declared_project_id=project_id,
            declared_wp_id=wp_id,
            declared_entry_id=entry_id,
            contract=registration.contract,
            include_superseded=include_superseded,
        )
    except SyncDomainError as exc:
        raise _sync_http(exc) from exc
    return preview.as_dict()


@router.get(USER_SYNC_PREFIX + "/operations/{operation_id}/timeline")
async def get_operation_timeline(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    operation_id: uuid.UUID,
    limit: int = Query(default=200, ge=1, le=1000),
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """脱敏 append-only timeline。

    Task 29 起投影由 :class:`SyncTimelineService` 负责：字段 allowlist 走版本化
    `RedactionPolicy`（原先是本处手写的白名单字面量，加一个 detail 列就会原样出网），
    并附带 operation/application 两条流的 **projection 一致性判定**（Property 68）——
    「current state 与 append-only timeline 分叉」在这里对用户可见，而不是只在守卫里可见。
    """
    await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="read_timeline",
        refs=(_operation_ref(operation_id),),
    )
    try:
        canonical = await svc.requests.read_operation(
            operation_id=operation_id,
            declared_project_id=project_id,
            declared_wp_id=wp_id,
            declared_entry_id=entry_id,
            action="read_timeline",
            require_application=False,
        )
        timeline = await SyncTimelineService(svc.session).operation_timeline(
            operation_id=canonical.requested_operation.id,
            declared_project_id=project_id,
            declared_wp_id=wp_id,
            declared_entry_id=entry_id,
            canonical_operation_id=canonical.canonical_operation.id,
            limit=limit,
        )
    except SyncDomainError as exc:
        raise _sync_http(exc) from exc
    return timeline.as_dict()


@router.get(USER_SYNC_PREFIX + "/recovery-cases/{case_id}/timeline")
async def get_recovery_case_timeline(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    case_id: uuid.UUID,
    limit: int = Query(default=200, ge=1, le=1000),
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """recovery case 的**独立** timeline（AC 13.5 / 13.6）。

    🔴 与 operation timeline 分成两个端点、两种返回结构：claim 之前根本没有 operation，
    合成一个「统一 timeline」端点就必须给 recovery 事件编一个 operation id ——
    那正是 AC 13.5 后半句禁止的「借 operation timeline 伪造 operation」。
    """
    await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="read_timeline",
        refs=(
            ScopeRef(
                resource_kind=ScopeResourceKind.recovery_case, resource_id=str(case_id)
            ),
        ),
    )
    try:
        timeline = await SyncTimelineService(svc.session).recovery_case_timeline(
            case_id=case_id,
            declared_project_id=project_id,
            declared_wp_id=wp_id,
            declared_entry_id=entry_id,
            limit=limit,
        )
    except SyncDomainError as exc:
        raise _sync_http(exc) from exc
    return timeline.as_dict()


# ═══════════════════════════════════════════════════════════════════════════
# 8. resolve / retry / rollback
# ═══════════════════════════════════════════════════════════════════════════


@router.post(USER_SYNC_PREFIX + "/operations/{operation_id}/resolve")
async def resolve_conflicts(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    operation_id: uuid.UUID,
    payload: Mapping[str, Any] = Body(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """人工裁决。八项乐观锁 → 折叠 → 唯一 commit 边界发布（Task 27）。"""
    scope = await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="resolve_conflicts",
        refs=(_operation_ref(operation_id),),
    )
    registration = await _registration(svc, scope)
    try:
        fence = build_resolve_fence(payload)
    except SyncDomainError as exc:
        raise _sync_http(exc) from exc
    resolutions = await _resolution_choices(
        svc,
        operation_id=operation_id,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        items=tuple(payload.get("resolutions") or ()),
    )
    try:
        outcome = await svc.conflicts.resolve(
            operation_id=operation_id,
            declared_project_id=project_id,
            declared_wp_id=wp_id,
            declared_entry_id=entry_id,
            fence=fence,
            resolutions=resolutions,
            adapter=registration.adapter,
            contract=registration.contract,
            actor_id=scope.user_id,
        )
        await svc.session.commit()
    except SyncDomainError as exc:
        await svc.session.rollback()
        raise _sync_http(exc) from exc
    return outcome.as_dict()


async def _resolution_choices(
    svc: _SyncServices,
    *,
    operation_id: uuid.UUID,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    items: tuple[Mapping[str, Any], ...],
):
    """design §API 的 `{conflict_id, choice, value}` → 域内 :class:`ResolutionChoice`。

    🔴 前端只有 `conflict_id`（preview 给它的 opaque id），而 merge 域按
    `(stable_field_key, row_key, oo_location)` 去重 —— 两者之间的翻译**必须在服务端**：
    让前端提交 stable key 等于让它决定裁决落在哪个字段，而那正是 AC 8.3「服务端自行
    校验」要禁的形态（改一个字符就能把裁决落到另一行）。

    翻译前先走 Task 23 的授权四步读路径拿 canonical primary：conflict 行永远挂在
    canonical primary 上，requested 是合法 duplicate 时它自己没有冲突行。
    翻译本体在 `endpoint_payloads`（服务层）—— 见那个模块 docstring 的两条理由。
    """
    if not items:
        return ()
    try:
        canonical = await svc.requests.read_operation(
            operation_id=operation_id,
            declared_project_id=project_id,
            declared_wp_id=wp_id,
            declared_entry_id=entry_id,
            action="resolve_conflicts",
            require_application=True,
        )
        return build_resolution_choices(
            items=items,
            conflict_rows=await svc.repo.load_conflicts(
                operation_id=canonical.canonical_operation.id
            ),
        )
    except SyncDomainError as exc:
        raise _sync_http(exc) from exc


@router.post(USER_SYNC_PREFIX + "/operations/{operation_id}/retry", status_code=202)
async def retry_operation(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    operation_id: uuid.UUID,
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """从 `application.incoming_artifact_id` 重试 —— 零 forcesave、不新建 operation。

    `operation_id=NULL` 的 unmatched/ambiguous recovery case 不得走这里
    （Task 27 的 `assert_retry_operation_eligible`）—— 它必须先 authorization-first claim。
    """
    scope = await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="retry_apply",
        refs=(_operation_ref(operation_id),),
    )
    registration = await _registration(svc, scope)
    try:
        outcome = await svc.conflicts.retry(
            operation_id=operation_id,
            declared_project_id=project_id,
            declared_wp_id=wp_id,
            declared_entry_id=entry_id,
            adapter=registration.adapter,
            contract=registration.contract,
            actor_id=scope.user_id,
        )
    except SyncDomainError as exc:
        raise _sync_http(exc) from exc
    return _apply_outcome_body(outcome)


@router.post(USER_SYNC_PREFIX + "/versions/{version_id}/rollback")
async def rollback_version(
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    version_id: str,
    payload: Mapping[str, Any] = Body(...),
    svc: _SyncServices = Depends(_services),
) -> dict[str, Any]:
    """`version_id` 是 immutable opaque content-version UUID。

    🔴 路径参数刻意声明为 `str` 而不是 `uuid.UUID`：声明成 UUID 时，
    `/versions/11/rollback`（numeric revision 当 route key）会被 FastAPI 的请求校验
    拦成 **422**，于是「numeric revision 不得作 route key」这条判据由框架顺手实现、
    本模块无从证伪，而且 422 与统一 404 oracle 不同桶（存在性泄露）。声明成 `str`
    后由 guard 的 `OpaqueResourceIdRequiredError` 判定，走同一个 404。
    """
    version_ref = ScopeRef(
        resource_kind=ScopeResourceKind.content_version, resource_id=str(version_id)
    )
    scope = await _guard(
        svc,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        action="rollback",
        refs=(version_ref,),
    )
    if not bool(payload.get("confirmed")):
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "rollback_confirmation_required",
                "message": "rollback 需要二次确认（design §API：需编辑权限和二次确认）",
            },
        )
    registration = await _registration(svc, scope)
    try:
        outcome = await svc.conflicts.rollback(
            version_id=uuid.UUID(str(version_id)),
            declared_project_id=project_id,
            declared_wp_id=wp_id,
            declared_entry_id=entry_id,
            expected_current_revision=int(payload["expected_current_revision"]),
            adapter=registration.adapter,
            contract=registration.contract,
            actor_id=scope.user_id,
        )
        await svc.session.commit()
    except SyncDomainError as exc:
        await svc.session.rollback()
        raise _sync_http(exc) from exc
    return outcome.as_dict()


# ═══════════════════════════════════════════════════════════════════════════
# 9. callback（服务凭证；不走用户 404/403 契约）
# ═══════════════════════════════════════════════════════════════════════════


@public_router.post("/api/workpaper-sync/rooms/{room_id}/onlyoffice-callback")
async def post_room_onlyoffice_callback(
    room_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """DocServer 回调。**只**委派 Task 22 的 `CallbackDeliveryService`。

    本 handler 不做任何判定：不 `jwt.decode`、不比字段、不判 status 语义、
    不伪造 participant attribution（route claim 的 participant hint 只是审计线索）。
    room/generation/doc_key/route token 的逐项校验在 `callback_route`。

    🔴 durable 之后必须 `error=0`：非零等于让 OO 静默丢件（Task 4 实测 OO 不重投），
    AC 5.7/5.8 因此要求「durable 后的失败留在 operation/recovery 上可重试」。
    `handle_callback` **刻意不抛**（失败在 `outcome.response_error` 里），所以本处
    读的是它的返回值，而不是「没抛异常就算成功」。
    """
    body = await request.json()
    repo = WorkpaperSyncRepository(db)
    artifacts = CanonicalArtifactRepository(BACKEND_ROOT)
    from app.core.config import settings

    service = CallbackDeliveryService(
        repo,
        artifacts=artifacts,
        download_policy=build_download_policy(
            onlyoffice_url=str(getattr(settings, "ONLYOFFICE_URL", "") or "")
        ),
        transport=build_httpx_transport(),
    )
    try:
        outcome = await service.handle_callback(
            authorization_header=request.headers.get("Authorization"),
            callback_url=str(request.url),
            body=body,
            room_id=room_id,
            secret=_onlyoffice_secret(),
        )
    except SyncDomainError as exc:
        await db.rollback()
        logger.warning(
            "sync callback pre-durable 拒绝 room=%s error_code=%s", room_id, exc.error_code
        )
        return {"error": 1}
    await db.commit()
    await _record_callback_metrics(db, room_id=room_id, outcome=outcome)
    if outcome.response_error != 0:
        return {"error": int(outcome.response_error)}
    if outcome.application_id is None or outcome.operation_id is None:
        # durable 但未归组（unmatched/ambiguous）⇒ recovery case 已建，三实体保持为 0。
        return {"error": 0}
    await _apply_durable_incoming(db, outcome=outcome)
    return {"error": 0}


async def _record_callback_metrics(
    db: AsyncSession, *, room_id: uuid.UUID, outcome: Any
) -> None:
    """callback 的 route 级指标。

    🔴 三条不可省的形态：

    1. **`landed` 从 `durable_at` 读，不从「有没有抛异常」推**。`handle_callback` 在
       incoming durable 之后刻意不抛（AC 5.7/5.8），失败落在 `outcome.response_error`
       里；「走到这一行」证明不了成功 —— Task 27/28 都为同一形态补过 landed-check。
       用 `durable_at IS NULL` 而不是 state 名单，是 AC 5.4 明文要求的判据。
    2. **不带 `participant_id`**。callback 是 room/generation 级聚合事件，route
       participant 不是作者（AC 5.1 / 10.9）；指标目录把这两个指标定成
       `route_scoped`，多传 participant 会被 `FORBIDDEN_DIMS` 直接拒。
    3. `generation` 取自 delivery 行而不是请求参数：请求里没有 generation，而 room 行
       可能在 callback 处理期间已经轮转 —— delivery 是这次投递的不可变事实。
    """
    from app.models.workpaper_sync_models import WorkpaperCallbackDelivery

    delivery = (
        await db.execute(
            sa.select(WorkpaperCallbackDelivery).where(
                WorkpaperCallbackDelivery.id == outcome.delivery_id
            )
        )
    ).scalar_one_or_none()
    if delivery is None:
        logger.error("callback 指标记录失败：delivery %s 不存在", outcome.delivery_id)
        return
    landed = delivery.durable_at is not None
    if landed:
        result = "durable"
    elif outcome.quarantined_artifact_id is not None:
        result = "quarantined"
    else:
        result = "pre_durable_failed"
    sync_metrics.record_outcome(
        "workpaper_sync_incoming_durable_total",
        result=result,
        landed=landed,
        room_id=room_id,
        generation=int(delivery.generation),
    )
    if landed and delivery.callback_recovery_case_id is not None:
        reason = getattr(outcome.plan.recovery_reason, "value", None) or "missing_request"
        sync_metrics.record_outcome(
            "workpaper_sync_recovery_case_total",
            result=reason,
            landed=True,
            room_id=room_id,
            generation=int(delivery.generation),
        )


async def _apply_durable_incoming(db: AsyncSession, *, outcome: Any) -> None:
    """durable incoming → merged projection（Task 26 的**生产调用点**）。

    这是 `oo_to_html.OoToHtmlCoordinator.apply_durable_incoming` 的第一条生产调用链：
    callback → delivery（durable + correlate）→ 本函数 → coordinator。Task 26 落地时
    它「非死代码」只由 `merge.RETIRED_DEFERRALS` 的登记表结构性背书；本函数把它翻转成
    **真实调用链**（`test_task28_sync_router` 的 AST 判据从本模块出发反查）。

    🔴 失败**不**上抛：incoming 已 durable，向 OO 返回非零会让它丢件。失败留在
    operation/recovery 上（coordinator 已写 error_code/error_stage），由用户显式 retry。
    这也是为什么这里读 `outcome.result` 而不是「没抛异常就算成功」—— coordinator
    在 durable 之后**刻意不抛**。
    """
    from app.models.workpaper_sync_models import WorkpaperContentApplication

    app_row = (
        await db.execute(
            sa.select(WorkpaperContentApplication).where(
                WorkpaperContentApplication.id == outcome.application_id
            )
        )
    ).scalar_one_or_none()
    if app_row is None:
        logger.error("callback 归组后找不到 application %s", outcome.application_id)
        return
    registry = build_production_registry()
    from app.services.workpaper_sync.adapters.registry import RegistryError
    from app.services.workpaper_sync.pilot_d2_large_json import (
        attach_pilot_adapters as attach_d2_pilot_adapters,
    )
    from app.services.workpaper_sync.pilot_h1_grouped_dynamic import (
        attach_pilot_adapters as attach_h1_pilot_adapters,
    )
    from app.services.workpaper_sync.pilot_simple_checklist import attach_pilot_adapters
    from app.services.workpaper_sync.pilot_g7_two_level_dynamic import (
        attach_pilot_adapters as attach_g7_pilot_adapters,
    )

    # Task 40 的第二个生产接线点：callback 之后的 apply 也必须能解析到 pilot adapter，
    # 否则「HTML 侧能开 OO、OO 回写却找不到 adapter」会形成半接线。
    await attach_pilot_adapters(registry, session=db)
    # Task 41：D2 pilot 各自一条（同上，不复用别的 pilot 的 attach/契约）。
    await attach_d2_pilot_adapters(registry, session=db)
    # Task 42：H1 pilot 各自一条（同上）。
    await attach_h1_pilot_adapters(registry, session=db)
    # Task 43：G7 pilot 各自一条（同上）。
    await attach_g7_pilot_adapters(registry, session=db)
    # Task 75 追加（只加不动）：manifest 驱动的注册，覆盖全部 entry 并留显式原因。
    await registry.register_from_manifest(session=db)

    try:
        registration = registry.assert_bidirectional_ready(str(app_row.entry_id))
    except (RegistryError, SyncDomainError) as exc:
        logger.error(
            "callback 后 apply 无可用 adapter entry=%s error_code=%s",
            app_row.entry_id,
            getattr(exc, "error_code", type(exc).__name__),
        )
        return
    repo = WorkpaperSyncRepository(db)
    artifacts = CanonicalArtifactRepository(BACKEND_ROOT)
    resolution = CanonicalResolutionService(db, artifacts)
    rooms = RoomService(repo)
    coordinator = OoToHtmlCoordinator(
        repo=repo,
        artifacts=artifacts,
        resolution=resolution,
        content=ContentMutationService(
            session=db, repository=repo, artifacts=artifacts, resolution=resolution
        ),
        rooms=rooms,
        requests=RequestApplicationService(repo, rooms),
        probe=_ServiceScopeVisibilityProbe(db),
    )
    # `initiated_by_participant_id` 取自 **operation 行**：AC 10.10 要求最终 fence 校验
    # 「非空 initiating participant」，所以它在 primary 上必然非空。application 行上没有
    # participant（AC 10.9 刻意不把作者塞进 application），因此不能从那里拿。
    from app.models.workpaper_sync_models import WorkpaperSyncOperation

    initiator = (
        await db.execute(
            sa.select(WorkpaperSyncOperation.initiated_by_participant_id).where(
                WorkpaperSyncOperation.id == outcome.operation_id
            )
        )
    ).scalar_one_or_none()
    started = time.monotonic()
    result = await coordinator.apply_durable_incoming(
        operation_id=outcome.operation_id,
        declared_project_id=app_row.project_id,
        declared_wp_id=app_row.wp_id,
        declared_entry_id=str(app_row.entry_id),
        adapter=registration.adapter,
        contract=registration.contract,
        attempt=1,
    )
    labels = {
        "room_id": app_row.room_id,
        "generation": int(app_row.generation),
        "requested_operation_id": result.requested_operation_id,
        "canonical_operation_id": result.canonical_operation_id,
        "application_id": app_row.id,
        "participant_id": initiator,
    }
    if initiator is None:
        # 不 emit 比 emit 一个编造的归因好：`operation_scoped` 的六维缺一即拒（会抛），
        # 而这里若真拿不到 initiator，说明 AC 10.10 的前置条件已经不成立 —— 记 ERROR 让
        # 它可见，而不是塞个占位 UUID 让看板看起来正常。
        logger.error(
            "apply 指标缺 initiating participant operation=%s —— AC 10.10 要求它非空",
            outcome.operation_id,
        )
        return
    sync_metrics.observe(
        "workpaper_sync_apply_seconds", seconds=time.monotonic() - started, **labels
    )
    if result.result is not OoToHtmlResult.applied:
        logger.warning(
            "callback 后 apply 未 applied operation=%s result=%s error_code=%s stage=%s",
            outcome.operation_id,
            result.result.value,
            result.error_code,
            result.error_stage,
        )
        # 🔴 `apply_durable_incoming` 在 durable 之后**刻意不抛**（AC 5.7/5.8），失败只在
        # `result.result` 里。因此这里读的是 result 而不是「没抛异常」——
        # 后者会把 refresh_required / conflict / error 全记成成功。
        # 且这三类各有专用指标，不能压成通用 error（Task 29 明文禁止）。
        if result.result is OoToHtmlResult.refresh_required:
            sync_metrics.record_outcome(
                "workpaper_sync_refresh_required_total",
                result="entered",
                landed=True,
                **labels,
            )
        elif result.result is not OoToHtmlResult.conflict:
            sync_metrics.record_outcome(
                "workpaper_sync_post_durable_failure_total",
                result=_POST_DURABLE_STAGES.get(str(result.error_stage), "commit"),
                landed=True,
                **labels,
            )


class _ServiceScopeVisibilityProbe:
    """callback 路径的 visibility 探针。

    callback 没有用户身份（DocServer 不发 Bearer），所以**不能**复用
    :class:`WpGateVisibilityProbe`（它按调用者判定）。这里查的是与用户无关的两条事实：
    project 未软删、wp 未归档/复核锁定。

    🔴 不返回硬编码 `True` —— 那会让 Task 26 的最终 authorization fence 变成空操作
    （AC 10.10 的十条重验第 1、2 条）。
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def observe(
        self, *, project_id: uuid.UUID, wp_id: uuid.UUID, entry_id: str
    ) -> Mapping[str, Any]:
        from app.models.workpaper_models import WorkingPaper, WpFileStatus
        from app.models.project import Project

        project_visible = bool(
            (
                await self._db.execute(
                    sa.select(sa.func.count())
                    .select_from(Project)
                    .where(Project.id == project_id, Project.is_deleted.is_(False))
                )
            ).scalar_one()
        )
        status = (
            await self._db.execute(
                sa.select(WorkingPaper.status).where(WorkingPaper.id == wp_id)
            )
        ).scalar_one_or_none()
        locked = status in (WpFileStatus.review_passed, WpFileStatus.archived)
        return {
            "project_visible": project_visible,
            "workflow_locked": bool(locked),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 10. 小工具
# ═══════════════════════════════════════════════════════════════════════════


#: `oo_to_html` 的 `error_stage` → `post_durable_failure_total` 的封闭 result 域。
#:
#: 未登记的 stage 落 `commit` 而**不是**静默丢弃：一个记不上号的阶段仍然是一次
#: post-durable 失败，漏记会让告警阈值永远达不到。
_POST_DURABLE_STAGES: Mapping[str, str] = {
    "extract": "extract",
    "merge": "merge",
    "rematerialize": "rematerialize",
    "authorization_fence": "authorization_fence",
    "final_authorization": "authorization_fence",
    "post_durable": "commit",
    "commit": "commit",
}


def _apply_outcome_body(outcome: Any) -> dict[str, Any]:
    return {
        "requested_operation_id": str(outcome.requested_operation_id),
        "canonical_operation_id": str(outcome.canonical_operation_id),
        "result": outcome.result.value,
        "conflict_count": int(outcome.conflict_count or 0),
        "conflict_set_digest": outcome.conflict_set_digest,
        "error_code": outcome.error_code,
        "error_stage": outcome.error_stage,
    }


def _uuid_field(
    payload: Mapping[str, Any], key: str, *, required: bool = True
) -> uuid.UUID | None:
    raw = payload.get(key)
    if raw is None:
        if not required:
            return None
        raise HTTPException(
            status_code=422,
            detail={"error_code": "missing_field", "message": f"缺少字段 {key!r}"},
        )
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "invalid_uuid",
                "message": f"字段 {key!r}={raw!r} 不是合法 UUID",
            },
        ) from exc


def _int_or_none(raw: Any) -> int | None:
    return None if raw is None else int(raw)


def _build_error_code_status(
    spec: tuple[tuple[int, tuple[type, ...]], ...] | None = None,
) -> Mapping[str, int]:
    """service 域异常 → HTTP status 的**唯一**映射表。

    🔴 键从**异常类的 `error_code` 属性**取，不手写字面量。第一版是手写的，
    16 条里 **5 条拼错**（`descriptor_stale_identity` 实际是
    `launch_descriptor_stale_identity`、`operation_scope_not_visible` 实际是
    `operation_scope_not_found`、`materialize_authorization_failed` 实际是
    `materialize_authorization_denied`、`recovery_retry_forbidden` 实际是
    `recovery_case_requires_claim_before_retry`、`descriptor_substrate_stale` 实际是
    `launch_descriptor_substrate_stale`）。后果不是「映射不准」而是**统一 404 oracle
    被破**：`OperationScopeNotVisibleError` 会落到 422，于是「跨 scope 读 operation」
    与「不存在」在响应上可区分 —— 那正是 Property 45 要禁的存在性泄露。
    拼错在功能测试里完全看不见（每条路径都还是「返回了一个错误」）。

    键仍是 `error_code` 而不是类型：跨模块的同义拒绝用同一个 code，按类型登记会漏掉
    一半；但**取值来源**必须是类属性，这样服务层重命名 error_code 时映射跟着走。

    🔴 `spec` 只为**判据可达性**存在，生产调用一律不传。下面那条「同一 code 登记两个
    status 即抛」的分支在真实映射表上恒不触发 ⇒ 从测试侧**不可达** ⇒ 把它短路掉的定向
    变异会永久判 GREEN（守卫缺陷的经典形态：分支存在但没有任何判据锁着它）。开一个
    注入口之后 `test_the_mapping_table_refuses_contradictory_registration` 才能真的
    喂进一份矛盾登记并断言它抛。
    """
    from app.services.workpaper_sync.conflict_resolution import (
        ContentVersionNotFoundError,
        RecoveryCaseRetryForbiddenError,
        ResolveApplyFailedError,
        ResolveAuthorizationStaleError,
        ResolveFenceRejectedError,
        ResolveRebaseRequiredError,
        ResolveSupersededError,
        ResolveWithoutConflictError,
        RollbackRevisionRewindError,
        RollbackSourceNotPublishedError,
        RollbackSourceQuarantinedError,
    )
    from app.services.workpaper_sync.materialize_coordinator import (
        DescriptorStaleIdentityError,
        DescriptorSubstrateStaleError,
        MaterializeAuthorizationError,
        MaterializeScopeNotVisibleError,
    )
    from app.services.workpaper_sync.models import (
        IdempotencyConflictError,
        QuarantinedIncomingError,
        RevisionConflictError,
        StateTransitionError,
    )
    from app.services.workpaper_sync.oo_to_html import (
        FinalFenceError,
        QuarantinedOperationForbiddenError,
        ReapplyForbiddenError,
    )
    from app.services.workpaper_sync.request_application import (
        OperationScopeNotVisibleError,
        ScopeAuthorizationDeniedError,
    )

    production_spec: tuple[tuple[int, tuple[type, ...]], ...] = (
        # 404 —— 统一 oracle（`_sync_http` 把它们全部换成 `_not_found()`）。
        (404, (ContentVersionNotFoundError, OperationScopeNotVisibleError,
               MaterializeScopeNotVisibleError)),
        # 403 —— scope 可见但当前授权/工作流不允许。
        (403, (ScopeAuthorizationDeniedError, MaterializeAuthorizationError,
               ResolveAuthorizationStaleError, FinalFenceError)),
        # 409 —— 乐观锁/身份陈旧/幂等冲突/状态机不允许。
        (409, (IdempotencyConflictError, RevisionConflictError,
               DescriptorStaleIdentityError, DescriptorSubstrateStaleError,
               ResolveFenceRejectedError, ResolveSupersededError,
               ResolveRebaseRequiredError, StateTransitionError,
               ReapplyForbiddenError, RollbackRevisionRewindError)),
        # 422 —— 请求本身不适配（客户端可读的拒绝）。
        (422, (QuarantinedIncomingError, QuarantinedOperationForbiddenError,
               RecoveryCaseRetryForbiddenError, ResolveWithoutConflictError,
               ResolveApplyFailedError, RollbackSourceNotPublishedError,
               RollbackSourceQuarantinedError)),
    )
    table: dict[str, int] = {}
    for status, classes in (production_spec if spec is None else spec):
        for cls in classes:
            code = str(cls.error_code)
            if code in table and table[code] != status:
                raise SyncDomainError(
                    f"error_code {code!r} 同时登记为 {table[code]} 与 {status}"
                )
            table[code] = status
    return table


_ERROR_CODE_STATUS: Mapping[str, int] = _build_error_code_status()


def _sync_http(exc: SyncDomainError) -> HTTPException:
    """service 域异常 → HTTPException。404 一律走统一 envelope。"""
    code = str(getattr(exc, "error_code", "") or "")
    status = int(getattr(exc, "http_status", 0) or 0) or _ERROR_CODE_STATUS.get(code, 422)
    if status == 404:
        return _not_found()
    if status == 409:
        return _conflict(exc, error_code=code)
    return _domain_error(exc, status=status)
