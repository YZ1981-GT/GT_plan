# -*- coding: utf-8 -*-
"""用户端 sync API 的**唯一**固定 guard：authorization-before-resource/cache。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 28
Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 3.1, 3.6, 3.7, 5.8, 11.4
Properties: **P10 / P11 / P45**

═══ 为什么 guard 是一个模块而不是每个端点各写一段 ═══

AC 10.6 要求的是**顺序**（「不可交换」），而顺序是最容易在复制粘贴中丢掉的东西：
十四个端点各写一遍「先查 scope index 再读业务行」，只要有一个人图省事先 `lock_room`
拿 room 反推 project/wp，横向越权就打开了 —— 而那个端点的功能测试**全绿**（它拿到的
room 确实存在、确实能读）。

因此本模块把这条链固化成**一个协程 + 一个只能由它产出的令牌**：

* :meth:`SyncEndpointGuard.enforce` 是取得 :class:`GuardedScope` 的唯一途径；
* 服务调用面（router 侧的每个 handler）以 `GuardedScope` 为必需入参，
  于是「忘记过 guard」在**类型**上就写不出来，而不是靠 code review 发现。

═══ 五个阶段（顺序即协议）═══

::

    ① authenticated        —— 未认证才 401，且**只有**这一处产生 401
    ② route_scope_parsed   —— 显式 project/wp/entry + 端点 opaque id + 可选 signed claim
    ③ scope_index_resolved —— **只**查 `working_paper_sync_scope_index`（非敏感归属）
    ④ visibility_verified  —— route/signed/index 三向交叉比对 + 当前 project visibility
    ⑤ action_authorized    —— action/workflow/lease/generation/write-fence/bundle 重验

业务 resource read 与 Idempotency-Key/cache lookup 一律在 ⑤ **之后**，由调用方
（router → service）完成；本模块**不碰**任何业务表。这一点由
:func:`assert_guard_authorization_first_shape` 的 AST 判据钉死，而不是靠本段说明。

═══ 「同一 404」为什么要**常量工作量**而不是提前 return ═══

AC 10.6 的原文是「不存在、跨 scope 或无 project visibility SHALL 在业务读取前返回
**同形态、同阶段且满足统一时序预算**的 404」。三种原因分别发生在阶段 ③（scope row
不存在 / 跨 scope）与阶段 ④（project 不可见）—— 若各自就地 `raise`，「不存在」会比
「无 visibility」少跑一次 visibility 探针，于是**响应时间**本身成了存在性预言机：
攻击者拿两个 id 各打一次，快的那个 = scope row 不存在、慢的那个 = 资源存在但他没权限。

所以本模块的形态是：阶段 ②③④ 只**构造并登记**拒绝（`_record`），阶段 ④ 末尾在
**唯一一处** raise 第一条登记项。三条路径跑完全同一串工作，时序落进同一个桶。

登记而不是立即抛，也让「envelope 唯一」与「分支可分辨」两个需求同时成立：

* envelope 唯一 —— HTTP 层只有一个 404 构造点（见 `wp_sync_router._NOT_FOUND_DETAIL`）；
* 分支可分辨 —— 每条分支是**独立的异常类型 + 独立 error_code**，定向变异（把某个
  `if` 短路成 `if False:`）会让**那一条**判据打红。共用一个类型时，靠前的分支被短路后
  靠后的分支会抛出同一类型顶上来，变异检验判 GREEN（本 spec 已三次踩到）。

═══ create 端点为什么不查 scope index（而不是硬造一次查询）═══

`pending-mutations` 是 create 端点：此刻还不存在任何 opaque resource id，
`working_paper_sync_scope_index` 里没有行可查（每行都随 child 同事务创建）。硬造一次
查询只会得到「查不到 ⇒ 404」，把「第一次 flush」变成永远失败。因此该端点声明
`refs=()`：阶段 ③ 对**零个** ref 完成（`scope_index_resolved` 仍然记入阶段链），
显式 route scope、visibility 与 action 三关照旧。
`MaterializeCoordinator.authorize_create` 的 docstring 说的是同一件事。
"""

from __future__ import annotations

import ast
import base64
import hashlib
import hmac
import inspect
import json
import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Final, Protocol, runtime_checkable

from app.services.workpaper_sync.models import (
    ScopeResourceKind,
    SyncDomainError,
    is_opaque_resource_id,
    is_uuid_text,
)
from app.services.workpaper_sync.repository import WorkpaperSyncRepository

__all__ = [
    "GuardPhase",
    "REQUIRED_PHASES",
    "ScopeRef",
    "ScopeAttribution",
    "GuardedScope",
    "SyncEndpointRequest",
    "SyncEndpointGuard",
    "ProjectVisibilityProbe",
    "ActionAuthorizer",
    "ScopeClaim",
    "ScopeClaimCodec",
    "SyncEndpointGuardError",
    "SyncEndpointUnauthenticatedError",
    "SyncScopeInvisibleError",
    "RouteScopeIncompleteError",
    "OpaqueResourceIdRequiredError",
    "VersionIdNotUuidError",
    "ScopeIndexMissError",
    "ScopeCrossBoundaryError",
    "ScopeClaimMismatchError",
    "ScopeProjectNotVisibleError",
    "SyncActionForbiddenError",
    "SyncWorkflowLockedError",
    "ActionNotPermittedError",
    "VisibilityProbeFailedError",
    "assert_guard_authorization_first_shape",
    "assert_single_refusal_site",
    "http_status_for_refusal",
]


def _now() -> datetime:
    """服务端时钟（aware）。timestamptz 一律在 Python 侧构造 datetime。"""
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 拒绝类型：401 一处、404 六条、403 两条，逐条独立可变异
# ═══════════════════════════════════════════════════════════════════════════


class SyncEndpointGuardError(SyncDomainError):
    """guard 域基类。"""

    error_code = "sync_endpoint_guard_failed"


class SyncEndpointUnauthenticatedError(SyncEndpointGuardError):
    """未认证 —— **唯一**产生 401 的原因（AC 10.6「401 只表示未认证」）。"""

    error_code = "sync_unauthenticated"


class SyncScopeInvisibleError(SyncEndpointGuardError):
    """404 家族基类：不存在 / 已 retire / 跨 scope / 无 project visibility。

    🔴 家族成员共用 HTTP 404 与**逐字节相同**的响应体，但**各有独立 error_code**。
    共用一个类型时，把靠前的分支短路掉之后靠后的分支会抛同一类型顶上来 ——
    变异检验判 GREEN，即那条判据从未被守卫锁住。
    """

    error_code = "sync_scope_not_visible"


class RouteScopeIncompleteError(SyncScopeInvisibleError):
    """路由没有显式携带 project/wp/entry（AC 10.6「每个用户路由 SHALL 显式携带」）。

    与「查不到」分型的理由：缺 entry 的 rollback 是**客户端契约**错误（Property 45
    点名「让 rollback 缺 entry/version_id 均须失败」），而查不到是数据事实。
    对外仍是同一个 404，但守卫要能分别证伪。
    """

    error_code = "sync_route_scope_incomplete"


class OpaqueResourceIdRequiredError(SyncScopeInvisibleError):
    """把 numeric revision（或任何非 opaque 值）当 route/scope key。

    AC 10.6 / 8.7：numeric `revision` 只作显示与乐观锁。两个 wp 都有 revision 1，
    用它当 `resource_id` 会在授权索引里碰撞成同一行。

    🔴 对**所有** resource kind 生效（room/operation/recovery case/version…），
    与下面只管 content_version 的 :class:`VersionIdNotUuidError` 分型 —— 详见那里。
    """

    error_code = "sync_opaque_resource_id_required"


class VersionIdNotUuidError(SyncScopeInvisibleError):
    """rollback 的 `version_id` 是 opaque 的但不是 immutable UUID（例如 `"rev-11"`）。

    🔴 **必须**与 :class:`OpaqueResourceIdRequiredError` 分型，这是变异检验实测出来的：
    两者原本共用一个类型，而唯一覆盖「非 opaque」那一支的判据用的是
    `resource_kind=content_version`。于是把 `is_opaque_resource_id(...)` 短路成
    `if False:` 之后，本条（`not is_uuid_text("11")` 恒真）会抛出**同一个**类型顶上来
    ⇒ 判据照旧通过 ⇒ 变异判 GREEN，即「numeric revision 不得作 scope key」这条对
    room/operation/recovery case 等**全部其他 kind** 从未被任何判据锁住。

    这正是本 spec 反复强调的形态：共用 error_code 会让靠前的分支变成事实上的死代码。
    """

    error_code = "sync_version_id_must_be_uuid"


class ScopeIndexMissError(SyncScopeInvisibleError):
    """scope index 无非 retired 行 —— 不存在与已 retire **共用**同一语义。

    tombstone 仍然存在（防 id 复用），但用户侧不得据此区分「从未存在」与「已退役」。
    """

    error_code = "sync_scope_index_miss"


class ScopeCrossBoundaryError(SyncScopeInvisibleError):
    """scope row 存在，但属于另一个 project/wp/entry —— 横向越权（Property 45）。"""

    error_code = "sync_scope_cross_boundary"


class ScopeClaimMismatchError(SyncScopeInvisibleError):
    """短期 signed scope claim 与 route/index scope 不一致，或已过期/被篡改。"""

    error_code = "sync_scope_claim_mismatch"


class ScopeProjectNotVisibleError(SyncScopeInvisibleError):
    """当前 project 对调用者不可见 —— 与「不存在」同 404 envelope/阶段/时序桶。"""

    error_code = "sync_project_not_visible"


class SyncActionForbiddenError(SyncEndpointGuardError):
    """403 家族基类：scope 已确认可见，但 action/workflow/lease/fence/bundle 不允许。"""

    error_code = "sync_action_forbidden"


class SyncWorkflowLockedError(SyncActionForbiddenError):
    """工作流/复核锁定/归档 —— 可见但不可写。"""

    error_code = "sync_workflow_locked"


class ActionNotPermittedError(SyncActionForbiddenError):
    """action/edit 权限、lease、generation、write fence 或 bundle 重验不通过。

    「撤权后原 key 重放」落在这里：首次成功之后撤销 access/lease、改 workflow/
    generation/fence/bundle，重放同 Idempotency-Key 必须在**业务/cache lookup 之前**
    被本条拦下，于是「不得泄露 cached descriptor / 不得产生新副作用」有可执行判据。
    """

    error_code = "sync_action_not_permitted"


class VisibilityProbeFailedError(SyncEndpointGuardError):
    """visibility 探针自身失败 —— **不得**降级为「无此限制」。

    🔴 与 403/404 分型且**不**归入任一家族：探针崩了既不能判「可见」（fail-open，
    等于取消整道门），也不能判「不可见」（把平台故障说成越权，运维会去查错误的地方）。
    它必须是第三种终态（500 级），并在 metrics 上单独可归因。
    """

    error_code = "sync_visibility_probe_failed"


#: 拒绝类型 → HTTP status 的**唯一**映射。未登记即抛（禁止「按最近似码猜」）。
_REFUSAL_STATUS: Final[Mapping[type, int]] = {
    SyncEndpointUnauthenticatedError: 401,
    SyncScopeInvisibleError: 404,
    SyncActionForbiddenError: 403,
    VisibilityProbeFailedError: 503,
}


def http_status_for_refusal(exc: BaseException) -> int:
    """guard 拒绝 → HTTP status。**只**认登记的四支，其余一律抛。

    刻意不写 `return 500` 兜底：兜底会让「新增一个拒绝类型但忘了登记」表现为 500，
    而 500 在生产里被当作平台故障处理 —— 真正的原因（授权分型漏登记）永远不会被发现。
    """
    for family, status in _REFUSAL_STATUS.items():
        if isinstance(exc, family):
            return status
    raise SyncEndpointGuardError(
        f"{type(exc).__name__} 未登记 HTTP 映射 —— guard 的拒绝分型必须逐条登记"
        f"（当前登记：{sorted(f.__name__ for f in _REFUSAL_STATUS)}）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 阶段链
# ═══════════════════════════════════════════════════════════════════════════


class GuardPhase(str, Enum):
    """guard 的固定阶段。**顺序即协议**，缺阶段即拒绝。"""

    authenticated = "authenticated"
    route_scope_parsed = "route_scope_parsed"
    scope_index_resolved = "scope_index_resolved"
    visibility_verified = "visibility_verified"
    action_authorized = "action_authorized"


#: 不可交换的阶段序。`GuardedScope.assert_complete()` 逐项按**下标**核对，
#: 因此「阶段齐全但顺序被换」也会红（只查集合包含关系时换序检查不出来）。
REQUIRED_PHASES: Final[tuple[GuardPhase, ...]] = (
    GuardPhase.authenticated,
    GuardPhase.route_scope_parsed,
    GuardPhase.scope_index_resolved,
    GuardPhase.visibility_verified,
    GuardPhase.action_authorized,
)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 值对象
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ScopeRef:
    """一个端点声明的 opaque resource 引用（**调用方提供的 id**，未经业务读）。"""

    resource_kind: ScopeResourceKind
    resource_id: str

    def __post_init__(self) -> None:
        if not str(self.resource_id).strip():
            raise RouteScopeIncompleteError(
                f"{self.resource_kind.value} 的 resource_id 为空 —— "
                "端点必须显式携带 opaque id"
            )

    @property
    def key(self) -> str:
        return f"{self.resource_kind.value}/{self.resource_id}"


@dataclass(frozen=True)
class ScopeAttribution:
    """scope index 行的**非敏感归属投影**。

    刻意不把 ORM 行透出去：AC 10.6 明文「index 不得存业务 payload、状态、hash、
    错误或候选摘要」，而透出 ORM 行会让下游有机会沿关系属性懒加载到业务表 ——
    那正是 authorization-before-resource 想禁止的形态。
    """

    resource_kind: ScopeResourceKind
    resource_id: str
    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    room_id: uuid.UUID | None
    generation: int | None

    @property
    def key(self) -> str:
        return f"{self.resource_kind.value}/{self.resource_id}"


@dataclass(frozen=True)
class GuardedScope:
    """「显式 scope + 当前权限都已重验」这一事实的载体。

    只能由 :meth:`SyncEndpointGuard.enforce` 产出。router 的每个业务调用面都以它
    为必需入参 —— 于是「忘记过 guard」在类型上写不出来。
    """

    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    user_id: uuid.UUID
    action: str
    refs: tuple[ScopeRef, ...]
    attributions: Mapping[str, ScopeAttribution]
    phases: tuple[GuardPhase, ...]
    observed: Mapping[str, Any]

    def assert_complete(self) -> None:
        """阶段链必须**逐位**等于 :data:`REQUIRED_PHASES`。"""
        if tuple(self.phases) != REQUIRED_PHASES:
            raise SyncEndpointGuardError(
                f"guard 阶段链 {[p.value for p in self.phases]} 与协议序 "
                f"{[p.value for p in REQUIRED_PHASES]} 不符 —— 顺序不可交换"
            )

    def attribution(self, ref: ScopeRef) -> ScopeAttribution:
        row = self.attributions.get(ref.key)
        if row is None:
            raise SyncEndpointGuardError(
                f"{ref.key} 没有 scope 归属 —— 它没有经过本次 guard 的阶段 ③"
            )
        return row

    def room_id_of(self, ref: ScopeRef) -> uuid.UUID | None:
        return self.attribution(ref).room_id

    def generation_of(self, ref: ScopeRef) -> int | None:
        return self.attribution(ref).generation


@dataclass(frozen=True)
class ScopeClaim:
    """短期 signed scope claim（download-only 签发、download 端点消费）。"""

    schema_version: int
    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    resource_kind: ScopeResourceKind
    resource_id: str
    user_id: uuid.UUID
    purpose: str
    expires_at: datetime

    def canonical_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "project_id": str(self.project_id),
            "wp_id": str(self.wp_id),
            "entry_id": str(self.entry_id),
            "resource_kind": self.resource_kind.value,
            "resource_id": str(self.resource_id),
            "user_id": str(self.user_id),
            "purpose": str(self.purpose),
            "expires_at": self.expires_at.isoformat(),
        }


#: claim schema 版本。改 claim 结构必须同时 +1，否则旧 token 会被按新语义解读。
CLAIM_SCHEMA_VERSION: Final[int] = 1

#: download claim 的默认 TTL —— 最小权限、短 TTL（AC 10.7）。
DEFAULT_CLAIM_TTL: Final[timedelta] = timedelta(minutes=10)


class ScopeClaimCodec:
    """scope claim 的签名与解码。**唯一**实现 —— 两套编解码必然漂移。"""

    __slots__ = ("_secret",)

    def __init__(self, secret: str | bytes) -> None:
        raw = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
        if not raw:
            raise ScopeClaimMismatchError(
                "scope claim 密钥为空 —— 空密钥等于不签名，伪造 claim 即可跨 scope 下载"
            )
        self._secret = raw

    @staticmethod
    def _b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _unb64(text: str) -> bytes:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))

    def _mac(self, body: bytes) -> bytes:
        return hmac.new(self._secret, body, hashlib.sha256).digest()

    def encode(self, claim: ScopeClaim) -> str:
        body = json.dumps(
            claim.canonical_mapping(), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return f"{self._b64(body)}.{self._b64(self._mac(body))}"

    def decode(self, token: str | None) -> ScopeClaim:
        """解码 + 常量时间验签。任何形态问题都是 :class:`ScopeClaimMismatchError`。"""
        if not token or not str(token).strip():
            raise ScopeClaimMismatchError("缺少 signed scope claim")
        parts = str(token).split(".")
        if len(parts) != 2:
            raise ScopeClaimMismatchError("scope claim 结构损坏（应为 body.mac）")
        try:
            body = self._unb64(parts[0])
            mac = self._unb64(parts[1])
        except (ValueError, TypeError) as exc:
            raise ScopeClaimMismatchError("scope claim base64 解码失败") from exc
        if not hmac.compare_digest(mac, self._mac(body)):
            raise ScopeClaimMismatchError("scope claim 签名不符 —— 伪造或截断")
        try:
            raw = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ScopeClaimMismatchError("scope claim body 不是合法 JSON") from exc
        if not isinstance(raw, Mapping):
            raise ScopeClaimMismatchError("scope claim body 不是对象")
        if int(raw.get("schema_version") or 0) != CLAIM_SCHEMA_VERSION:
            raise ScopeClaimMismatchError(
                f"scope claim schema 版本 {raw.get('schema_version')!r} != "
                f"{CLAIM_SCHEMA_VERSION} —— 旧 token 不得按新语义解读"
            )
        try:
            return ScopeClaim(
                schema_version=CLAIM_SCHEMA_VERSION,
                project_id=uuid.UUID(str(raw["project_id"])),
                wp_id=uuid.UUID(str(raw["wp_id"])),
                entry_id=str(raw["entry_id"]),
                resource_kind=ScopeResourceKind(str(raw["resource_kind"])),
                resource_id=str(raw["resource_id"]),
                user_id=uuid.UUID(str(raw["user_id"])),
                purpose=str(raw["purpose"]),
                expires_at=datetime.fromisoformat(str(raw["expires_at"])),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise ScopeClaimMismatchError(f"scope claim 字段非法：{exc}") from exc

    def mint(
        self,
        *,
        scope: GuardedScope,
        ref: ScopeRef,
        purpose: str,
        ttl: timedelta = DEFAULT_CLAIM_TTL,
    ) -> tuple[str, ScopeClaim]:
        """按**已通过 guard** 的 scope 签发短期 claim。

        入参是 :class:`GuardedScope` 而不是散装 id：签发面若接受散装 id，就能在未过
        guard 的地方铸出一个跨 scope 的合法 claim，而它之后每次都能通过验签。
        """
        scope.assert_complete()
        claim = ScopeClaim(
            schema_version=CLAIM_SCHEMA_VERSION,
            project_id=scope.project_id,
            wp_id=scope.wp_id,
            entry_id=scope.entry_id,
            resource_kind=ref.resource_kind,
            resource_id=str(ref.resource_id),
            user_id=scope.user_id,
            purpose=str(purpose),
            expires_at=_now() + ttl,
        )
        return self.encode(claim), claim


# ═══════════════════════════════════════════════════════════════════════════
# 4. 注入面
# ═══════════════════════════════════════════════════════════════════════════


@runtime_checkable
class ProjectVisibilityProbe(Protocol):
    """project visibility / workflow lock 的**外部**观测口。

    与 `oo_to_html.AuthorizationProbe` **刻意同签名**：同一份生产实现同时喂给 guard
    的阶段 ④⑤ 与 Task 26 的最终 fence。两套实现必然漂移，而漂移的表现是「入口放行、
    最终 fence 拒绝」——用户看到的是「保存到最后才失败」。
    """

    async def observe(
        self, *, project_id: uuid.UUID, wp_id: uuid.UUID, entry_id: str
    ) -> Mapping[str, Any]: ...


#: action 重验回调：拿到**已确认可见**的 scope 与 action 名，返回是否允许。
#:
#: 只拿 scope（显式归属）与 action 名，拿不到任何业务行 —— 需要业务行才能判权限
#: 就说明 scope 模型漏了字段（与 Task 23/25/26 同一约定）。
ActionAuthorizer = Callable[[GuardedScope], "bool | Awaitable[bool]"]


@dataclass(frozen=True)
class SyncEndpointRequest:
    """guard 的唯一入参（未授权形态）。"""

    project_id: uuid.UUID | None
    wp_id: uuid.UUID | None
    entry_id: str | None
    action: str
    user_id: uuid.UUID | None
    refs: tuple[ScopeRef, ...] = ()
    signed_claim: str | None = None
    claim_purpose: str | None = None


# ═══════════════════════════════════════════════════════════════════════════
# 5. guard
# ═══════════════════════════════════════════════════════════════════════════

#: 阶段 ②③④ 禁止出现的业务表 ORM 符号（与 Task 23/25 同一份名单形态）。
_BUSINESS_TABLES: Final[tuple[str, ...]] = (
    "WorkpaperOoRoom",
    "WorkpaperOoParticipant",
    "WorkpaperOoClientConfirmation",
    "WorkpaperForcesaveRequest",
    "WorkpaperSyncOperation",
    "WorkpaperContentApplication",
    "WorkpaperContentVersion",
    "WorkpaperContentRepresentation",
    "WorkpaperCallbackDelivery",
    "WorkpaperCallbackRecoveryCase",
    "WorkpaperSyncConflict",
    "WorkpaperPendingMutation",
    "WorkpaperArtifact",
    "WorkpaperOoCloseIntent",
)

#: guard 阶段允许调用的仓储方法（**只**读非敏感 scope index）。
_SCOPE_ONLY_REPO_CALLS: Final[frozenset[str]] = frozenset({"resolve_scope"})

#: guard 的**全部**阶段方法。判据必须覆盖整条链，不只入口。
_GUARD_PHASE_METHODS: Final[tuple[str, ...]] = (
    "enforce",
    "_parse_route_scope",
    "_resolve_scope_index",
    "_verify_visibility",
)


def _dedent_source(src: str) -> str:
    lines = src.splitlines()
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    cut = min(indents) if indents else 0
    return "\n".join(l[cut:] if len(l) >= cut else l for l in lines)


def assert_guard_authorization_first_shape() -> tuple[str, ...]:
    """AST 反查 guard 阶段：只许读非敏感 scope index。

    返回阶段链实际调用到的仓储方法名（正常恰为 ``('resolve_scope',)``）。

    🔴 为什么必须是**源码**判据：AC 10.5/10.6 禁止的是代码形态（「严禁先查 room/
    operation/recovery/application 来反推 scope」）。行为观察只能证明「这次没查」——
    把一次 `sa.select(WorkpaperOoRoom)` 加回阶段 ③ 后，功能测试大概率仍然通过
    （结果一样），只有源码判据会红。

    两条判据合一，因为它们是同一件事的两面：多引一个业务表符号（第 1 条），
    或者不引符号而多调一个仓储方法（第 2 条）—— 只查其一必留缺口。
    """
    repo_calls: set[str] = set()
    for method_name in _GUARD_PHASE_METHODS:
        method = getattr(SyncEndpointGuard, method_name)
        tree = ast.parse(_dedent_source(inspect.getsource(method)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in _BUSINESS_TABLES:
                raise SyncEndpointGuardError(
                    f"{method_name}() 引用了业务表 {node.id} —— guard 阶段**只**读非敏感 "
                    "working_paper_sync_scope_index（AC 10.5 / 10.6）"
                )
            if isinstance(node, ast.Attribute) and node.attr in _BUSINESS_TABLES:
                raise SyncEndpointGuardError(
                    f"{method_name}() 引用了业务表属性 {node.attr}"
                )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = node.func.value
                if (
                    isinstance(owner, ast.Attribute)
                    and isinstance(owner.value, ast.Name)
                    and owner.value.id == "self"
                    and owner.attr in ("_repo", "_session", "_rooms", "_requests")
                ):
                    repo_calls.add(node.func.attr)
    extra = sorted(repo_calls - _SCOPE_ONLY_REPO_CALLS)
    if extra:
        raise SyncEndpointGuardError(
            f"guard 阶段额外调用了 {extra} —— 只允许 {sorted(_SCOPE_ONLY_REPO_CALLS)}"
            "（先查 scope index，禁止先查 room/operation/recovery/application 反推 scope，"
            "也禁止先命中幂等缓存）"
        )
    return tuple(sorted(repo_calls))


#: 404 家族的全部类名。判据按名字扫源码，因此新增成员必须登记到这里 ——
#: 漏登记时 `assert_single_refusal_site` 会漏掉它，那正是本常量存在的风险，
#: 由 `test_every_404_subclass_is_registered` 用 `__subclasses__()` 反向锁死。
_NOT_FOUND_FAMILY_NAMES: Final[frozenset[str]] = frozenset(
    {
        "SyncScopeInvisibleError",
        "RouteScopeIncompleteError",
        "OpaqueResourceIdRequiredError",
        "VersionIdNotUuidError",
        "ScopeIndexMissError",
        "ScopeCrossBoundaryError",
        "ScopeClaimMismatchError",
        "ScopeProjectNotVisibleError",
    }
)

#: 只**登记**拒绝（`refusals.append(...)`）、不得就地 raise 404 的阶段方法。
_RECORDING_PHASE_METHODS: Final[tuple[str, ...]] = (
    "_parse_route_scope",
    "_resolve_scope_index",
    "_verify_visibility",
    "_verify_claim",
)


def _raised_type_name(node: ast.Raise) -> str | None:
    """`raise Foo(...)` / `raise Foo` → `"Foo"`；`raise x[0]` / 裸 `raise` → None。"""
    exc = node.exc
    if exc is None:
        return None
    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
        return exc.func.id
    if isinstance(exc, ast.Name):
        return exc.id
    return None


def assert_single_refusal_site() -> int:
    """404 家族在整个 guard 里只许有**一个**抛出点，且它在 :meth:`enforce` 内。

    返回 404 家族的间接抛出点数量（正常为 1，即 ``raise refusals[0]``）。

    🔴 这条判据守的是「同一 envelope」：多个 raise 点意味着多份文案，而多份文案迟早
    出现「资源不存在」与「无权访问」两种措辞 —— 存在性预言机就是这么泄露的。
    分支本身仍是**独立类型**（阶段方法构造它们并 `append`），只是抛出动作收在一处；
    同时也保证「常量工作量」：就地 raise 会让某些 404 少跑一次 visibility 探针。

    刻意**不**只数 `enforce` 里的 raise 总数：那个数字里混着 1 个 401 与 2 个 403，
    任何 403 分支的增删都会误伤本判据（假红），而真正要禁的是**404 家族**的直接抛出。
    """
    direct: list[str] = []
    for method_name in ("enforce",) + _RECORDING_PHASE_METHODS:
        method = getattr(SyncEndpointGuard, method_name)
        tree = ast.parse(_dedent_source(inspect.getsource(method)))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise):
                continue
            name = _raised_type_name(node)
            if name in _NOT_FOUND_FAMILY_NAMES:
                direct.append(f"{method_name}(): raise {name}")
    if direct:
        raise SyncEndpointGuardError(
            f"404 家族被就地抛出：{direct} —— 必须 `refusals.append(...)` 登记，"
            "由 enforce() 的唯一抛出点统一抛，否则「同 envelope / 同阶段 / 同时序桶」"
            "三条全部落空"
        )
    tree = ast.parse(_dedent_source(inspect.getsource(SyncEndpointGuard.enforce)))
    indirect = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise) and _raised_type_name(node) is None
    ]
    if len(indirect) != 1:
        raise SyncEndpointGuardError(
            f"enforce() 的间接抛出点有 {len(indirect)} 个（应为 1，即 "
            "`raise refusals[0]`）—— 0 个意味着登记的 404 永远不会被抛出"
            "（fail-open），>1 个意味着多个 envelope"
        )
    return len(indirect)


class SyncEndpointGuard:
    """用户端 sync API 的固定 guard。**不 commit、不碰业务表**。

    依赖全部显式注入且没有一个是「可选的默认放行」：

    * `repository` —— Task 10 的仓储；本 guard 只用它的 `resolve_scope`
    * `visibility` —— project visibility / workflow lock 的外部观测口（必填）
    * `authorize` —— action/lease/generation/fence/bundle 重验回调（必填）

    两个依赖都**没有默认值**：忘记接线时会在**构造**处 `TypeError`，
    而不是在运行时静默放行（「没配就放行」是 fail-open 的经典形态）。
    """

    def __init__(
        self,
        *,
        repository: WorkpaperSyncRepository,
        visibility: ProjectVisibilityProbe,
        authorize: ActionAuthorizer,
        claim_codec: ScopeClaimCodec | None = None,
        read_only_actions: frozenset[str] = frozenset(),
    ) -> None:
        self._repo = repository
        if visibility is None:
            raise SyncEndpointGuardError(
                "ProjectVisibilityProbe 是必填依赖：可选即等于默认放行，"
                "而 AC 10.1/10.6 没有例外"
            )
        if authorize is None:
            raise SyncEndpointGuardError(
                "action 重验回调是必填依赖：可选即等于默认放行"
            )
        self._visibility = visibility
        self._authorize = authorize
        self._claims = claim_codec
        #: workflow 锁定（归档 / 复核通过 / History_Only / reviewer 只读）下**仍允许**的
        #: action。默认空集 = 一律拒绝（fail closed）。
        #:
        #: 🔴 名单由调用方注入而不是在本模块写死：action 名字是 router 的词汇表，
        #: 在这里抄一份必然漂移。而**必须有这个名单**是真库实测出来的 ——
        #: 第一版无条件按 `workflow_locked` 拒绝，于是归档底稿连 conflicts/timeline 都
        #: 403（AC 11.6「显示阻断原因」、11.11「可追溯」直接落空），而离线守卫只测了
        #: 写 action 的否定侧，全绿。
        self._read_only_actions = frozenset(str(a) for a in read_only_actions)
        #: 只增不减的可观测计数（守卫读它，而不是读本模块的自述）。
        self.enforced: int = 0
        self.refused: int = 0

    # ─────────────────────────────────────────────────────────────────
    # 5.1 唯一入口
    # ─────────────────────────────────────────────────────────────────

    async def enforce(self, request: SyncEndpointRequest) -> GuardedScope:
        """五阶段固定链。**唯一**产出 :class:`GuardedScope` 的方法。

        阶段 ②③④ 只**登记**拒绝，阶段 ④ 末尾在唯一一处抛第一条 —— 见模块 docstring
        「常量工作量」一节：三种 404 原因必须跑完同一串工作，否则响应时间成了存在性
        预言机。
        """
        refusals: list[SyncScopeInvisibleError] = []

        # ── ① 认证：唯一的 401 产生点
        if request.user_id is None:
            raise SyncEndpointUnauthenticatedError(
                "未认证请求不得进入 sync 端点 —— 401 只表示未认证"
            )
        phases = [GuardPhase.authenticated]

        # ── ② 显式 route scope + 端点 opaque ids + 可选 signed claim
        project_id, wp_id, entry_id = self._parse_route_scope(request, refusals)
        phases.append(GuardPhase.route_scope_parsed)

        # ── ③ **只**查 scope index
        attributions = await self._resolve_scope_index(
            request, project_id=project_id, wp_id=wp_id, entry_id=entry_id,
            refusals=refusals,
        )
        phases.append(GuardPhase.scope_index_resolved)

        # ── ④ 三向交叉比对 + 当前 project visibility
        observed = await self._verify_visibility(
            request, project_id=project_id, wp_id=wp_id, entry_id=entry_id,
            refusals=refusals,
        )
        phases.append(GuardPhase.visibility_verified)

        self.enforced += 1
        if refusals:
            self.refused += 1
            raise refusals[0]

        # ── ⑤ action / workflow / lease / generation / write fence / bundle
        candidate = GuardedScope(
            project_id=project_id,  # type: ignore[arg-type]
            wp_id=wp_id,  # type: ignore[arg-type]
            entry_id=str(entry_id),
            user_id=request.user_id,
            action=str(request.action),
            refs=tuple(request.refs),
            attributions=attributions,
            phases=tuple(phases),
            observed=observed,
        )
        if (
            bool(observed.get("workflow_locked"))
            and str(request.action) not in self._read_only_actions
        ):
            self.refused += 1
            raise SyncWorkflowLockedError(
                f"wp {wp_id} 的 workflow 已锁定（复核锁定/归档）—— "
                f"scope 可见但写 action={request.action!r} 不被允许（403，与 404 分型）；"
                f"只读 action（{sorted(self._read_only_actions)}）仍放行，"
                "否则归档底稿连冲突/timeline 都看不了"
            )
        verdict = self._authorize(candidate)
        if inspect.isawaitable(verdict):
            verdict = await verdict
        if not verdict:
            self.refused += 1
            raise ActionNotPermittedError(
                f"entry {entry_id!r} 的 scope 可见，但当前 project/workflow/lease/"
                f"generation/write-fence/bundle 不允许 action={request.action!r}"
                "（403）—— 撤权后原 Idempotency-Key 重放不得返回 cached 结果"
            )
        return GuardedScope(
            project_id=candidate.project_id,
            wp_id=candidate.wp_id,
            entry_id=candidate.entry_id,
            user_id=candidate.user_id,
            action=candidate.action,
            refs=candidate.refs,
            attributions=candidate.attributions,
            phases=tuple(phases) + (GuardPhase.action_authorized,),
            observed=observed,
        )

    # ─────────────────────────────────────────────────────────────────
    # 5.2 阶段 ②
    # ─────────────────────────────────────────────────────────────────

    def _parse_route_scope(
        self,
        request: SyncEndpointRequest,
        refusals: list[SyncScopeInvisibleError],
    ) -> tuple[uuid.UUID | None, uuid.UUID | None, str | None]:
        """显式 project/wp/entry 三者缺一即登记 404；opaque id 形态同时核验。"""
        missing = [
            name
            for name, value in (
                ("project_id", request.project_id),
                ("wp_id", request.wp_id),
                ("entry_id", (request.entry_id or "").strip() or None),
            )
            if value is None
        ]
        if missing:
            refusals.append(
                RouteScopeIncompleteError(
                    f"路由缺显式 scope 字段 {missing} —— 每个用户端点都必须显式携带 "
                    "project/wp/entry（recovery list 另含 room/generation，"
                    "rollback 另含 opaque version_id）"
                )
            )
        for ref in request.refs:
            if not is_opaque_resource_id(str(ref.resource_id)):
                refusals.append(
                    OpaqueResourceIdRequiredError(
                        f"{ref.resource_kind.value} 的 route key "
                        f"{ref.resource_id!r} 不是 opaque id —— numeric revision "
                        "只作显示与乐观锁，禁止作 route/scope key（AC 10.6 / 8.7）"
                    )
                )
            elif (
                ref.resource_kind is ScopeResourceKind.content_version
                and not is_uuid_text(str(ref.resource_id))
            ):
                refusals.append(
                    VersionIdNotUuidError(
                        f"rollback 的 version_id={ref.resource_id!r} 不是 immutable "
                        "opaque UUID —— 两个 wp 的 revision 1 必须由不同 UUID 无碰撞定位"
                    )
                )
        return request.project_id, request.wp_id, (request.entry_id or None)

    # ─────────────────────────────────────────────────────────────────
    # 5.3 阶段 ③
    # ─────────────────────────────────────────────────────────────────

    async def _resolve_scope_index(
        self,
        request: SyncEndpointRequest,
        *,
        project_id: uuid.UUID | None,
        wp_id: uuid.UUID | None,
        entry_id: str | None,
        refusals: list[SyncScopeInvisibleError],
    ) -> Mapping[str, ScopeAttribution]:
        """**只**查 `working_paper_sync_scope_index`，并与显式 route scope 交叉比对。

        create 端点声明 `refs=()` ⇒ 本阶段对零个 ref 完成（见模块 docstring）。
        """
        attributions: dict[str, ScopeAttribution] = {}
        for ref in request.refs:
            row = await self._repo.resolve_scope(
                resource_kind=ref.resource_kind, resource_id=str(ref.resource_id)
            )
            if row is None:
                refusals.append(
                    ScopeIndexMissError(
                        f"{ref.key} 在 scope index 中不可见（不存在或已 retire）—— "
                        "与「跨 scope 使用」共用同一 404 语义，不得据此推断该 id 是否存在"
                    )
                )
                continue
            attribution = ScopeAttribution(
                resource_kind=ref.resource_kind,
                resource_id=str(ref.resource_id),
                project_id=row.project_id,
                wp_id=row.wp_id,
                entry_id=str(row.entry_id),
                room_id=row.room_id,
                generation=(None if row.generation is None else int(row.generation)),
            )
            attributions[ref.key] = attribution
            if (
                attribution.project_id != project_id
                or attribution.wp_id != wp_id
                or attribution.entry_id != str(entry_id)
            ):
                refusals.append(
                    ScopeCrossBoundaryError(
                        f"{ref.key} 与显式声明的 project/wp/entry scope 不符 —— "
                        "横向越权与「不存在」共用同一 404 语义"
                    )
                )
        return attributions

    # ─────────────────────────────────────────────────────────────────
    # 5.4 阶段 ④
    # ─────────────────────────────────────────────────────────────────

    async def _verify_visibility(
        self,
        request: SyncEndpointRequest,
        *,
        project_id: uuid.UUID | None,
        wp_id: uuid.UUID | None,
        entry_id: str | None,
        refusals: list[SyncScopeInvisibleError],
    ) -> Mapping[str, Any]:
        """signed claim 三向比对 + 当前 project visibility。

        探针**必须真查**：`observe()` 抛出时转 :class:`VisibilityProbeFailedError`
        并立即穿透（不登记、不继续）—— 探针故障既不能当「可见」也不能当「不可见」。
        """
        if request.signed_claim is not None:
            self._verify_claim(
                request,
                project_id=project_id,
                wp_id=wp_id,
                entry_id=entry_id,
                refusals=refusals,
            )
        if project_id is None or wp_id is None or entry_id is None:
            # route scope 不完整时无从探测；阶段 ② 已登记 404，此处返回空观测。
            return {}
        try:
            observed = await self._visibility.observe(
                project_id=project_id, wp_id=wp_id, entry_id=str(entry_id)
            )
        except SyncEndpointGuardError:
            raise
        except BaseException as exc:  # noqa: BLE001 - 转型后立即穿透，非 fail-open
            raise VisibilityProbeFailedError(
                f"project visibility 探针失败（{type(exc).__name__}: {exc}）—— "
                "不得降级为「无此限制」，也不得当作越权"
            ) from exc
        if not isinstance(observed, Mapping):
            raise VisibilityProbeFailedError(
                f"visibility 探针返回 {type(observed).__name__}，应为 Mapping"
            )
        if "project_visible" not in observed:
            raise VisibilityProbeFailedError(
                "visibility 探针未返回 `project_visible` —— 缺字段时按缺省值放行"
                "等于取消整道门"
            )
        if not bool(observed.get("project_visible")):
            refusals.append(
                ScopeProjectNotVisibleError(
                    f"project {project_id} 当前对调用者不可见 —— 与「不存在」"
                    "同 envelope、同阶段、同时序桶"
                )
            )
        return observed

    def _verify_claim(
        self,
        request: SyncEndpointRequest,
        *,
        project_id: uuid.UUID | None,
        wp_id: uuid.UUID | None,
        entry_id: str | None,
        refusals: list[SyncScopeInvisibleError],
    ) -> None:
        """signed claim 必须与 route scope、声明的 ref、调用者与用途逐项一致。"""
        if self._claims is None:
            refusals.append(
                ScopeClaimMismatchError(
                    "请求携带 signed scope claim，但 guard 未装配 ScopeClaimCodec —— "
                    "未验签的 claim 一律不得放行"
                )
            )
            return
        try:
            claim = self._claims.decode(request.signed_claim)
        except ScopeClaimMismatchError as exc:
            refusals.append(exc)
            return
        if claim.expires_at <= _now():
            refusals.append(
                ScopeClaimMismatchError(
                    f"signed scope claim 已过期（expires_at="
                    f"{claim.expires_at.isoformat()}）"
                )
            )
            return
        if (
            claim.project_id != project_id
            or claim.wp_id != wp_id
            or claim.entry_id != str(entry_id)
            or claim.user_id != request.user_id
        ):
            refusals.append(
                ScopeClaimMismatchError(
                    "signed scope claim 的 project/wp/entry/user 与本次请求不符 —— "
                    "跨 scope 复用 claim 与「不存在」同 404 语义"
                )
            )
            return
        if request.claim_purpose is not None and claim.purpose != str(
            request.claim_purpose
        ):
            refusals.append(
                ScopeClaimMismatchError(
                    f"signed scope claim 的 purpose={claim.purpose!r} 与端点要求的 "
                    f"{request.claim_purpose!r} 不符 —— 最小权限凭证不得跨用途"
                )
            )
            return
        declared = {ref.key for ref in request.refs}
        if f"{claim.resource_kind.value}/{claim.resource_id}" not in declared:
            refusals.append(
                ScopeClaimMismatchError(
                    "signed scope claim 指向的资源不在本次端点声明的 refs 内"
                )
            )

    # ─────────────────────────────────────────────────────────────────
    # 5.5 便利构造
    # ─────────────────────────────────────────────────────────────────

    def mint_claim(
        self,
        *,
        scope: GuardedScope,
        ref: ScopeRef,
        purpose: str,
        ttl: timedelta = DEFAULT_CLAIM_TTL,
    ) -> str:
        """签发短期 scope claim（download-only 用）。未装配 codec 即抛。"""
        if self._claims is None:
            raise SyncEndpointGuardError(
                "guard 未装配 ScopeClaimCodec —— 不得签发未签名的下载凭证"
            )
        token, _claim = self._claims.mint(
            scope=scope, ref=ref, purpose=purpose, ttl=ttl
        )
        return token


def declared_refs(
    pairs: Iterable[tuple[ScopeResourceKind, object | None]],
) -> tuple[ScopeRef, ...]:
    """把 `(kind, id|None)` 序列压成 refs 元组，跳过 None（可选 ref）。"""
    out: list[ScopeRef] = []
    for kind, raw in pairs:
        if raw is None:
            continue
        out.append(ScopeRef(resource_kind=kind, resource_id=str(raw)))
    return tuple(out)
