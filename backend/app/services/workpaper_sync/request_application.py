# -*- coding: utf-8 -*-
"""Task 23：frozen request 持久化、content application 去重与 sequence 收敛的**唯一组合点**。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 23
Requirements: 2.9, 4.1, 4.3, 4.10, 4.11, 5.4, 5.5, 5.10, 8.5, 10.5, 10.11, 14.3
Properties: **P18 / P36 / P56 / P62 / P64**

═══ 为什么需要这个模块（它不是又一层转发）═══

Task 21 给了 room 侧策略（`assert_can_initiate_request` / `build_request_freeze` /
canonical fence 推进），Task 10/22 给了仓储侧原子写（`create_forcesave_request_with_shell`
的复合幂等键、`correlate_durable_incoming` 的 primary/duplicate 收敛）。两侧都完整，
但**没有任何生产代码把它们按正确顺序串起来** —— 开工时全部调用点都是测试各自手工拼装：

    assert_can_initiate_request(...)   # 授权
    build_request_freeze(...)          # 冻结
    create_forcesave_request_with_shell(...)   # 落库

手工拼装的问题不是「重复」而是**顺序与完整性无法被证明**：调用点可以先落库再授权、
可以跳过 freeze 自己拼冻结值、可以在 accepted 之前先建 application。AC 4.1 的措辞
（「**先**在一个数据库事务中持久化冻结…的 forcesave request，并创建 operation shell，
**再**由后端调用 Command Service」）说的正是顺序，而顺序只能由**唯一入口**保证。

因此本模块承担四件顺序敏感的事，每件都做成不可绕过的形态：

1. :meth:`RequestApplicationService.freeze_and_persist_request` —— authorization-first →
   freeze → 同一事务落 request + `application_id=NULL, duplicate_of_operation_id=NULL`
   shell。返回 :class:`AcceptedRequest`，它是 Task 24 调 Command Service 的**唯一凭据**，
   且构造时会**真读一次库**确认「零 application」（见该类 docstring）。
2. :meth:`RequestApplicationService.authorize_operation_scope` +
   :meth:`RequestApplicationService.canonicalize_authorized` —— GET/timeline/conflict/
   retry/resolve 的固定四步。拆成两个方法而不是一个带 flag 的方法，是为了让
   「authorization-first」由**参数类型**强制：`canonicalize_authorized` 只接受
   :class:`AuthorizedOperationRef`，而后者只能由前者产出。
3. :func:`arbitrate_resolve` —— resolve 的裁决顺序：**先** canonical application identity，
   **后** `effective_request_sequence`。同 app 更高 sequence 只 fold、永不 stale。
4. :meth:`RequestApplicationService.claim_recovery` —— recovery claim 的 authorization-first
   包装；commit 前断言 shell 必为 primary 或 direct terminal duplicate。

本模块**不 commit**（事务边界属 coordinator），**不含任何 HTTP/Command Service 依赖** ——
后者是结构判据：本模块 import 图里若出现 httpx/Command Service 符号，就说明有人把
「调 OO」挪到了「落库」之前或之内，而那正是 AC 4.1 禁止的。
"""
from __future__ import annotations

import ast
import inspect
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Iterable

import sqlalchemy as sa

from app.models.workpaper_sync_models import (
    WorkpaperContentApplication,
    WorkpaperForcesaveRequest,
    WorkpaperOoRoom,
    WorkpaperSyncOperation,
    WorkpaperSyncScopeIndex,
)

from .models import (
    ActorType,
    OperationDirection,
    OperationShape,
    OperationState,
    RequestKind,
    ScopeResourceKind,
    SyncDomainError,
    classify_operation_shape,
    fold_effective_sequence,
)
from .repository import (
    CorrelationOutcome,
    RecoveryClaimOutcome,
    WorkpaperSyncRepository,
)
from .rooms import FrozenBundleIdentity, RequestFreeze, RoomScope, RoomService

__all__ = [
    "AcceptedRequest",
    "ApplicationPrecreatedError",
    "AuthorizedOperationRef",
    "CanonicalBindingError",
    "CanonicalPrimaryUnboundError",
    "CanonicalRead",
    "ConvergenceError",
    "OperationScopeNotVisibleError",
    "ReadStage",
    "RecoveryClaimShapeError",
    "RequestApplicationDomainError",
    "RequestApplicationService",
    "ResolveArbitration",
    "ResolveFence",
    "ResolveVerdict",
    "ScopeAuthorizationDeniedError",
    "arbitrate_resolve",
    "assert_authorization_first_source_shape",
    "assert_correlation_convergence",
    "assert_recovery_claim_shape",
]


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常：每条拒绝一个独立类型
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 拒绝理由必须**分型**而不是共用一个 error_code。本 spec 已经为此付过两次代价
# （Task 22 的 M04/M10）：两条拒绝共用一个异常类型时，靠 `pytest.raises(T)` 的守卫
# 无法区分是哪条在工作 ⇒ 先声明的那条被永久遮蔽，定向变异判 GREEN。


class RequestApplicationDomainError(SyncDomainError):
    """Task 23 域基类。"""

    error_code = "request_application_error"


class ScopeAuthorizationDeniedError(RequestApplicationDomainError):
    """requested id 的显式 scope 与调用方声明不符，或当前权限已不允许该 action。

    与 :class:`OperationScopeNotVisibleError` **分型**：前者是「可见但不允许」（403），
    后者是「不可见/不存在」（统一 404 envelope）。合成一类会让 403/404 的区分无法被守卫
    证明，而 AC 10.5 恰恰要求二者语义不同。
    """

    error_code = "scope_authorization_denied"


class OperationScopeNotVisibleError(RequestApplicationDomainError):
    """scope index 里查不到该 operation（不存在 / 已 retire / 跨 scope）—— 统一 404。"""

    error_code = "operation_scope_not_found"


class ApplicationPrecreatedError(RequestApplicationDomainError):
    """accepted 之前已经存在 application —— AC 4.1「不得预建 application」被违反。"""

    error_code = "application_precreated"


class RecoveryClaimShapeError(RequestApplicationDomainError):
    """recovery claim 在 commit 前 shell 既不是 primary 也不是 direct terminal duplicate。"""

    error_code = "recovery_claim_shape_invalid"


class CanonicalPrimaryUnboundError(RequestApplicationDomainError):
    """canonical primary 尚未绑定 application（pre-correlation shell 被当作已绑定态读）。

    🔴 与 :class:`CanonicalBindingError` **必须分型**，且二者互不为子类。
    首轮把两条拒绝合成一个类型，结果「未绑定」那条永久不可达：
    `app_id is None` 时若不拒，紧接着的 `count(... application_id == app_id)` 会被
    SQLAlchemy 渲染成 `IS NULL` ⇒ 统计到全部 pre-correlation shell ⇒ `bound != 1`
    照样抛**同一个**类型。定向变异实测判 GREEN —— 守卫无法证明第一条有效。
    """

    error_code = "canonical_primary_unbound"


class CanonicalBindingError(RequestApplicationDomainError):
    """application 被 ≠1 个 operation 绑定（多绑）。"""

    error_code = "canonical_primary_binding_invalid"


class ConvergenceError(RequestApplicationDomainError):
    """correlation 后 shell 未落成 primary / direct duplicate 的应有形态。"""

    error_code = "correlation_convergence_invalid"


def assert_correlation_convergence(
    *,
    reported_shape: OperationShape,
    application_id: uuid.UUID | None,
    duplicate_of_operation_id: uuid.UUID | None,
    state: OperationState | str,
    canonical_application_id: uuid.UUID,
    canonical_primary_operation_id: uuid.UUID,
    origin_request_sequence: int,
    effective_request_sequence: int,
) -> OperationShape:
    """correlation 之后 shell 的收敛形态（Property 18 的四条不变量）。

    与 :func:`assert_recovery_claim_shape` 同理抽成纯函数：四条分支只有合成输入
    才能逐条证明，而真实 correlation 永远走 happy path。

    1. 报告的 shape 与行的实际形态一致（防「报 primary 实为 duplicate」）；
    2. primary ⇒ `application_id` 等于本次 canonical application；
    3. duplicate ⇒ `application_id` 为空且 `duplicate_of` **直指** canonical primary；
    4. 任何情况下 `effective >= origin`（GREATEST fold 语义）。

    停在 `pre_correlation` 一律拒绝 —— 那正是 Task 23 正文禁止的
    「停在 waiting_application」。
    """
    shape = classify_operation_shape(
        application_id=application_id,
        duplicate_of_operation_id=duplicate_of_operation_id,
        state=state,
    )
    if shape is not reported_shape:
        raise ConvergenceError(
            f"correlation 报告 shape={reported_shape.value} 但行实际是 {shape.value}"
        )
    if shape is OperationShape.primary:
        if application_id != canonical_application_id:
            raise ConvergenceError(
                "primary 的 application_id 必须等于本次 canonical application"
            )
    elif shape is OperationShape.duplicate:
        if application_id is not None:
            raise ConvergenceError("duplicate shell 不得绑定 application")
        if duplicate_of_operation_id != canonical_primary_operation_id:
            raise ConvergenceError("duplicate 必须**直指** canonical primary（禁链/环）")
    else:
        raise ConvergenceError(
            f"correlation 后 shell 仍是 {shape.value} —— 禁止停在 waiting_application"
        )
    if int(effective_request_sequence) < int(origin_request_sequence):
        raise ConvergenceError(
            f"effective_request_sequence {effective_request_sequence} < "
            f"origin {origin_request_sequence} —— GREATEST fold 语义被破坏"
        )
    return shape


def assert_recovery_claim_shape(
    *,
    operation_shape: OperationShape,
    application_id: uuid.UUID | None,
    case_application_id: uuid.UUID | None,
) -> None:
    """recovery claim 在 **commit 前** 的形态断言（AC 4.1 / 5.8）。

    抽成纯函数而不是内嵌在 :meth:`RequestApplicationService.claim_recovery` 里：
    三条分支各自需要一个合成输入才能证明有效，而内嵌形态只能靠真实 claim 场景触发
    ——真实场景永远是 happy path，三条分支于是全部无判据（「用合成输入证明分支覆盖」
    是本 spec 已付过代价的教训）。

    * shell 必须已是 primary 或 direct terminal duplicate（禁止停在 pre-correlation）；
    * 必须在同一事务内创建/命中 application；
    * case 与 delivery 必须绑定**同一** canonical application。
    """
    if operation_shape not in (OperationShape.primary, OperationShape.duplicate):
        raise RecoveryClaimShapeError(
            f"recovery claim 的 shell 在 commit 前是 {operation_shape.value} —— "
            "必须已落成 primary 或 direct terminal duplicate"
        )
    if application_id is None:
        raise RecoveryClaimShapeError(
            "recovery claim 必须在同一事务内创建/命中 application"
        )
    if case_application_id != application_id:
        raise RecoveryClaimShapeError(
            f"recovery case 绑定 {case_application_id!r} 而 claim 得到 {application_id!r}"
            " —— case/delivery 必须绑定同一 canonical application"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. accepted 凭据
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AcceptedRequest:
    """`freeze_and_persist_request` 的结果 —— Task 24 调 Command Service 的唯一凭据。

    🔴 为什么要有这个对象、而不是直接返回 `(request, operation)`：

    AC 4.1 要求「先落库、再调 Command Service」，而「先/再」在代码里没有类型。
    做成凭据后，Task 24 的签名可以要求 :class:`AcceptedRequest`，于是「没落库就去调 OO」
    在**类型层**不可表达。凭据自身再带三条自证（构造时已在库里核过，见
    :meth:`RequestApplicationService.freeze_and_persist_request`）：

    * ``operation_shape is OperationShape.pre_correlation`` —— shell 的 `application_id`
      与 `duplicate_of_operation_id` 都是 NULL；
    * ``application_count == 0`` —— **真查了一次** `working_paper_content_application`，
      不是「我没建所以肯定是 0」。二者的差别在并发：另一条路径若抢先给这个 request 建了
      application，只有真查才看得见；
    * ``cache_hit`` —— 逐项等值的幂等重放返回同一 request/operation（AC 4.1），
      不等值时 :class:`~.repository.IdempotencyConflictError` 已在仓储层抛出且
      **不携带旧标识**。
    """

    request: WorkpaperForcesaveRequest
    operation: WorkpaperSyncOperation
    operation_shape: OperationShape
    application_count: int
    cache_hit: bool
    request_sequence: int
    frozen_request_fingerprint: str

    def assert_dispatchable(self) -> None:
        """调 Command Service 之前的最后一道自证（Task 24 必须调用）。"""
        if self.operation_shape is not OperationShape.pre_correlation:
            raise ApplicationPrecreatedError(
                "accepted 凭据的 shell 不是 pre-correlation（application_id 与 "
                f"duplicate_of_operation_id 必须都为空），实得 {self.operation_shape.value}"
            )
        if self.application_count != 0:
            raise ApplicationPrecreatedError(
                f"accepted 之前已存在 {self.application_count} 个 application —— "
                "AC 4.1：accepted 前不得预建 application 或 application key"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 读路径：固定四步
# ═══════════════════════════════════════════════════════════════════════════


class ReadStage(str, Enum):
    """GET/timeline/conflict/retry/resolve 的固定阶段序。

    顺序本身就是判据（AC 5.5 末段 / AC 8.5 / AC 5.10）：
    requested-id 授权 → direct-primary invariant → canonicalize →
    只要求 canonical primary 唯一绑定 application。
    """

    requested_scope_resolved = "requested_scope_resolved"
    requested_action_authorized = "requested_action_authorized"
    requested_operation_loaded = "requested_operation_loaded"
    direct_primary_verified = "direct_primary_verified"
    canonicalized = "canonicalized"
    canonical_application_bound = "canonical_application_bound"


@dataclass(frozen=True)
class AuthorizedOperationRef:
    """「requested operation 的显式 scope 与当前权限都已重验」这一事实的**载体**。

    只由 :meth:`RequestApplicationService.authorize_operation_scope` 产出。
    :meth:`RequestApplicationService.canonicalize_authorized` 只接受本类型 ⇒
    「先授权后 canonicalize」由参数类型强制，而不是靠调用点自觉。

    刻意**不**携带 operation 行本身：授权阶段只允许读非敏感
    `working_paper_sync_scope_index`（AC 10.5「严禁先查 room/operation/recovery/
    application 来反推 scope」）。业务行在 canonicalize 阶段才加载。
    """

    operation_id: uuid.UUID
    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    room_id: uuid.UUID | None
    generation: int | None
    action: str
    stages: tuple[ReadStage, ...]


@dataclass(frozen=True)
class CanonicalRead:
    """canonicalize 的结果。

    `requested_shape is duplicate` 时 `requested_operation.application_id` 必为 NULL
    而 `canonical_operation.application_id` 非空 —— 这正是 AC 5.5 末段
    「只要求 canonical primary 唯一绑定 application，不得要求合法 duplicate 自身绑定」。
    """

    requested_operation: WorkpaperSyncOperation
    requested_shape: OperationShape
    canonical_operation: WorkpaperSyncOperation
    canonical_application_id: uuid.UUID | None
    effective_request_sequence: int | None
    stages: tuple[ReadStage, ...]

    @property
    def followed_duplicate(self) -> bool:
        return self.requested_shape is OperationShape.duplicate

    @property
    def canonical_is_primary(self) -> bool:
        return self.canonical_operation.application_id is not None


# ═══════════════════════════════════════════════════════════════════════════
# 4. resolve 裁决：identity 先，sequence 后
# ═══════════════════════════════════════════════════════════════════════════


class ResolveVerdict(str, Enum):
    """裁决结论（AC 8.5 / Property 36）。"""

    proceed = "proceed"
    """canonical application 相同且 effective sequence 等值 —— 直接继续。"""

    fold_and_proceed = "fold_and_proceed"
    """canonical application **相同**但 effective sequence 更高 —— 只规范化到最新
    sequence 后继续**同一** conflict set；**绝不** stale、绝不 self-supersede。"""

    superseded = "superseded"
    """room latest durable 指向**另一个** canonical application 且其 effective sequence
    更高 —— 旧 conflict/operation 被 supersede。"""

    rebase_required = "rebase_required"
    """没有不同的较新 application，但 current revision 变了 —— 按原 frozen bundle rebase。"""

    conflict_digest_stale = "conflict_digest_stale"
    """conflict set digest 不等值 —— 客户端看到的冲突集已不是当前那一份。"""

    fence_changed = "fence_changed"
    """generation / write fence / client edit epoch 变化 —— 按协议拒绝。"""


@dataclass(frozen=True)
class ResolveFence:
    """一次 resolve 请求携带的乐观锁全集（AC 8.5 逐字段）。"""

    expected_current_revision: int
    room_generation: int
    client_edit_epoch: int
    canonical_application_id: uuid.UUID
    application_effective_request_sequence: int
    room_latest_durable_application_id: uuid.UUID | None
    room_latest_durable_sequence: int
    conflict_set_digest: str


@dataclass(frozen=True)
class ResolveArbitration:
    """裁决结果 + **比较顺序的可观测轨迹**。

    `compared` 记录实际比较了哪几项、按什么次序。它不是日志：AC 8.5 要求
    「先比较 canonical application identity，再比较 effective sequence」，
    把顺序做成返回值的一部分，才能让「有人调换两者」被守卫看见 —— 只断言最终
    verdict 时，`fold_and_proceed` 与 `superseded` 在多数场景下互不重叠，
    但存在一类输入（同 app + 更高 sequence）两种顺序会给出**不同**结论，
    而那正是 self-supersede 的入口。
    """

    verdict: ResolveVerdict
    compared: tuple[str, ...]
    normalized_effective_sequence: int
    reason: str

    @property
    def stale(self) -> bool:
        """是否判定为「旧的、需要放弃」。fold 永远不是 stale。"""
        return self.verdict is ResolveVerdict.superseded


def arbitrate_resolve(
    *,
    fence: ResolveFence,
    current_revision: int,
    current_room_generation: int,
    current_write_fence_epoch: int,
    request_write_fence_epoch: int,
    current_client_edit_epoch: int,
    canonical_application_id: uuid.UUID,
    canonical_effective_request_sequence: int,
    room_latest_durable_application_id: uuid.UUID | None,
    room_latest_durable_sequence: int,
    current_conflict_set_digest: str,
) -> ResolveArbitration:
    """resolve 的裁决顺序（AC 8.5 / Property 36 / Property 18 的 no-self-supersede 面）。

    固定顺序，每一步独立可变异：

    0. fence（generation / write fence / client edit epoch）—— 变化即按协议拒绝；
    1. conflict set digest —— 不等值即 stale（客户端手里的冲突集已不是这一份）；
    2. **canonical application identity**：room latest durable 指向的 application
       是否与本次 canonical application **同一个**；
    3. 只有在 identity **不同**时才比较 effective sequence 决定 supersede；
       identity **相同**时只能 fold（`GREATEST`）或 proceed，
       **永不** stale、**永不** self-supersede；
    4. 无不同较新 application 而 current revision 变了 ⇒ rebase。

    🔴 第 2 步在第 3 步之前，不是风格问题。反过来（先比 sequence）时，
    「同一个 canonical application 因 same-key duplicate 把 effective sequence 抬高」
    会被读成「有更高 sequence ⇒ 我 stale」—— 这就是 AC 5.5 明令禁止的
    self-supersede 与 duplicate→primary→stale 循环。
    """
    compared: list[str] = []

    compared.append("room_generation")
    if int(fence.room_generation) != int(current_room_generation):
        return ResolveArbitration(
            verdict=ResolveVerdict.fence_changed,
            compared=tuple(compared),
            normalized_effective_sequence=int(canonical_effective_request_sequence),
            reason=(
                f"room generation {fence.room_generation} → {current_room_generation}"
            ),
        )
    compared.append("write_fence_epoch")
    if int(request_write_fence_epoch) != int(current_write_fence_epoch):
        return ResolveArbitration(
            verdict=ResolveVerdict.fence_changed,
            compared=tuple(compared),
            normalized_effective_sequence=int(canonical_effective_request_sequence),
            reason=(
                f"write fence {request_write_fence_epoch} → {current_write_fence_epoch}"
            ),
        )
    compared.append("client_edit_epoch")
    if int(fence.client_edit_epoch) != int(current_client_edit_epoch):
        return ResolveArbitration(
            verdict=ResolveVerdict.fence_changed,
            compared=tuple(compared),
            normalized_effective_sequence=int(canonical_effective_request_sequence),
            reason=(
                f"client edit epoch {fence.client_edit_epoch} → {current_client_edit_epoch}"
            ),
        )

    compared.append("conflict_set_digest")
    if fence.conflict_set_digest.strip() != current_conflict_set_digest.strip():
        return ResolveArbitration(
            verdict=ResolveVerdict.conflict_digest_stale,
            compared=tuple(compared),
            normalized_effective_sequence=int(canonical_effective_request_sequence),
            reason="conflict set digest 不等值",
        )

    # ── 第 2 步：canonical application identity（**先于** sequence）──────────
    compared.append("canonical_application_identity")
    durable_pointer = room_latest_durable_application_id
    same_canonical = (
        durable_pointer is None or durable_pointer == canonical_application_id
    )

    if not same_canonical:
        # ── 第 3 步：identity 不同，才轮到 sequence ──────────────────────
        compared.append("effective_request_sequence")
        if int(room_latest_durable_sequence) > int(canonical_effective_request_sequence):
            return ResolveArbitration(
                verdict=ResolveVerdict.superseded,
                compared=tuple(compared),
                normalized_effective_sequence=int(canonical_effective_request_sequence),
                reason=(
                    f"room latest durable 指向不同 canonical application {durable_pointer} "
                    f"且 sequence {room_latest_durable_sequence} > "
                    f"{canonical_effective_request_sequence}"
                ),
            )
        # 不同 application 但并不更新 ⇒ 不 supersede（只有「较新且不同」才可）
        return ResolveArbitration(
            verdict=ResolveVerdict.proceed,
            compared=tuple(compared),
            normalized_effective_sequence=int(canonical_effective_request_sequence),
            reason=(
                f"room latest durable 指向不同 application 但 sequence "
                f"{room_latest_durable_sequence} 不高于 "
                f"{canonical_effective_request_sequence} —— 不构成 supersede"
            ),
        )

    # ── identity 相同：只能 fold 或 proceed，永不 stale ─────────────────────
    compared.append("same_application_sequence_fold")
    folded = fold_effective_sequence(
        int(fence.application_effective_request_sequence),
        int(canonical_effective_request_sequence),
    )
    if folded != int(fence.application_effective_request_sequence):
        return ResolveArbitration(
            verdict=ResolveVerdict.fold_and_proceed,
            compared=tuple(compared),
            normalized_effective_sequence=folded,
            reason=(
                "同 canonical application 的 effective sequence 由 same-key duplicate "
                f"抬高（{fence.application_effective_request_sequence} → {folded}）——"
                "只规范化后继续同一 conflict set，不得 self-supersede"
            ),
        )

    compared.append("current_revision")
    if int(fence.expected_current_revision) != int(current_revision):
        return ResolveArbitration(
            verdict=ResolveVerdict.rebase_required,
            compared=tuple(compared),
            normalized_effective_sequence=folded,
            reason=(
                f"current revision {fence.expected_current_revision} → {current_revision}"
                "；无不同较新 application ⇒ 按原 frozen bundle/authority model rebase"
            ),
        )
    return ResolveArbitration(
        verdict=ResolveVerdict.proceed,
        compared=tuple(compared),
        normalized_effective_sequence=folded,
        reason="canonical application 相同、sequence 等值、revision 未变",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 5. 结构判据：授权阶段只许读 scope index
# ═══════════════════════════════════════════════════════════════════════════

_BUSINESS_TABLES = (
    "WorkpaperSyncOperation",
    "WorkpaperContentApplication",
    "WorkpaperForcesaveRequest",
    "WorkpaperOoRoom",
    "WorkpaperCallbackRecoveryCase",
    "WorkpaperCallbackDelivery",
    "WorkpaperOoParticipant",
)


_SCOPE_ONLY_REPO_CALLS = frozenset({"resolve_scope"})


def assert_authorization_first_source_shape() -> tuple[str, ...]:
    """AST 反查：授权阶段只许读非敏感 scope index。

    返回授权阶段实际调用到的 **repository 方法名**（正常恰为 ``('resolve_scope',)``）。

    两条判据合在一个函数里，因为它们是同一件事的两面：

    1. 源码里不得出现任何业务表 ORM 符号（`_BUSINESS_TABLES`）；
    2. 对 `self._repo` 的调用集合必须是 :data:`_SCOPE_ONLY_REPO_CALLS` 的子集 ——
       多调一个仓储方法就等于多读一张业务表，而那种写法**不会**出现业务表符号，
       只看第 1 条会漏掉（例如 `await self._repo.lock_room(...)`）。

    🔴 为什么要 AST 而不是「跑一遍看它查了什么」：AC 10.5 禁止的是**代码形态**
    （「严禁先查 room/operation/recovery/application 来反推 scope」）。运行期观察
    只能证明「这次没查」；把 `sa.select(WorkpaperSyncOperation)` 加回授权阶段后，
    行为测试大概率仍然通过（结果一样），只有源码判据会红。

    与之配套的是 :class:`AuthorizedOperationRef` 的类型强制：前者管「授权阶段不许多读」，
    后者管「不授权不许 canonicalize」。少任何一半，「authorization-first」都只是注释。
    """
    src = inspect.getsource(RequestApplicationService.authorize_operation_scope)
    tree = ast.parse(_dedent_source(src))
    repo_calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _BUSINESS_TABLES:
            raise ScopeAuthorizationDeniedError(
                f"authorize_operation_scope 引用了业务表 {node.id} —— "
                "authorization-first 要求授权阶段**只**读非敏感 "
                "working_paper_sync_scope_index（AC 10.5）"
            )
        if isinstance(node, ast.Attribute) and node.attr in _BUSINESS_TABLES:
            raise ScopeAuthorizationDeniedError(
                f"authorize_operation_scope 引用了业务表属性 {node.attr}"
            )
        # `self._repo.<name>(...)` / `self._rooms.<name>(...)` 的调用名
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if (
                isinstance(owner, ast.Attribute)
                and isinstance(owner.value, ast.Name)
                and owner.value.id == "self"
                and owner.attr in ("_repo", "_rooms", "_session")
            ):
                repo_calls.add(node.func.attr)
    extra = sorted(repo_calls - _SCOPE_ONLY_REPO_CALLS)
    if extra:
        raise ScopeAuthorizationDeniedError(
            f"authorize_operation_scope 在授权阶段额外调用了 {extra} —— "
            f"只允许 {sorted(_SCOPE_ONLY_REPO_CALLS)}（AC 10.5：先查 scope index，"
            "禁止先查 room/operation/recovery/application 反推 scope）"
        )
    return tuple(sorted(repo_calls))


def _dedent_source(src: str) -> str:
    """去掉方法源码的公共缩进，让 :func:`ast.parse` 能接受。"""
    lines = src.splitlines()
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    cut = min(indents) if indents else 0
    return "\n".join(l[cut:] if len(l) >= cut else l for l in lines)


# ═══════════════════════════════════════════════════════════════════════════
# 6. 服务
# ═══════════════════════════════════════════════════════════════════════════

AuthorizeAction = Callable[[AuthorizedOperationRef], Awaitable[bool] | bool]


class RequestApplicationService:
    """frozen request / application 去重 / sequence 收敛的组合层。**不 commit**。"""

    def __init__(self, repo: WorkpaperSyncRepository, rooms: RoomService | None = None) -> None:
        self._repo = repo
        self._session = repo.session
        self._rooms = rooms if rooms is not None else RoomService(repo)

    @property
    def repo(self) -> WorkpaperSyncRepository:
        return self._repo

    @property
    def rooms(self) -> RoomService:
        return self._rooms

    # ─────────────────────────────────────────────────────────────────
    # 6.1 accepted 前：authorization-first → freeze → 同事务落 request + shell
    # ─────────────────────────────────────────────────────────────────

    async def freeze_and_persist_request(
        self,
        scope: RoomScope,
        *,
        room_id: uuid.UUID,
        participant_id: uuid.UUID,
        idempotency_key: str,
        client_edit_epoch: int,
        kind: RequestKind | str = RequestKind.forcesave,
        contributor_user_ids: Iterable[uuid.UUID | str] = (),
        expected_write_fence_epoch: int | None = None,
        expected_bundle: FrozenBundleIdentity | None = None,
        direction: OperationDirection | str = OperationDirection.oo_to_html,
        created_by: uuid.UUID | None = None,
    ) -> AcceptedRequest:
        """Command Service **之前**的全部工作，一个事务内完成（AC 4.1 / Property 64）。

        顺序固定且不可绕过：

        1. :meth:`RoomService.assert_can_initiate_request` —— room/participant/mode/
           fence/confirmation/baseline/bundle 八条资格门（authorization-first：
           在**任何**写之前）；
        2. :meth:`RoomService.build_request_freeze` —— 从**已通过门**的三行冻结全部值，
           算出 canonical `frozen_request_fingerprint`；
        3. :meth:`WorkpaperSyncRepository.create_forcesave_request_with_shell` ——
           同一事务落 request 与 `application_id=NULL, duplicate_of_operation_id=NULL`
           shell，复合唯一键 `(room, generation, initiator, kind, idempotency_key)`；
           跨 participant / 跨 kind / fingerprint 不等值 ⇒
           :class:`~.repository.IdempotencyConflictError`（409，**不返回旧标识**）；
        4. 真查一次 application 计数并自证为 0。

        第 4 步不是形式主义：它把「accepted 前不得预建 application」从「我没写那行代码」
        变成「库里真的没有」。二者在并发下不等价。
        """
        room, participant, confirmation = await self._rooms.assert_can_initiate_request(
            room_id=room_id,
            participant_id=participant_id,
            kind=kind,
            expected_write_fence_epoch=expected_write_fence_epoch,
            expected_bundle=expected_bundle,
        )
        freeze = await self._rooms.build_request_freeze(
            room=room,
            participant=participant,
            confirmation=confirmation,
            kind=kind,
            client_edit_epoch=client_edit_epoch,
            contributor_user_ids=contributor_user_ids,
        )
        outcome = await self._repo.create_forcesave_request_with_shell(
            **freeze.as_repository_kwargs(scope=scope),
            idempotency_key=idempotency_key,
            direction=direction,
            created_by=created_by,
        )
        shape = classify_operation_shape(
            application_id=outcome.operation.application_id,
            duplicate_of_operation_id=outcome.operation.duplicate_of_operation_id,
            state=outcome.operation.state,
        )
        app_count = int(
            (
                await self._session.execute(
                    sa.select(sa.func.count())
                    .select_from(WorkpaperContentApplication)
                    .where(
                        WorkpaperContentApplication.origin_request_id == outcome.request.id
                    )
                )
            ).scalar_one()
        )
        accepted = AcceptedRequest(
            request=outcome.request,
            operation=outcome.operation,
            operation_shape=shape,
            application_count=app_count,
            cache_hit=outcome.cache_hit,
            request_sequence=int(outcome.request.request_sequence),
            frozen_request_fingerprint=str(outcome.request.frozen_request_fingerprint),
        )
        accepted.assert_dispatchable()
        return accepted

    # ─────────────────────────────────────────────────────────────────
    # 6.2 读路径第一步：只读 scope index 的授权
    # ─────────────────────────────────────────────────────────────────

    async def authorize_operation_scope(
        self,
        *,
        operation_id: uuid.UUID,
        declared_project_id: uuid.UUID,
        declared_wp_id: uuid.UUID,
        declared_entry_id: str,
        action: str,
        authorize: AuthorizeAction | None = None,
    ) -> AuthorizedOperationRef:
        """固定四步的第 1 步：**只**查 `working_paper_sync_scope_index`。

        `declared_*` 是调用方从 URL 显式带来的 scope（AC 10.1/10.5：显式 scope，
        不得从 resource 反推）。不匹配与查不到都走**同一** 404 语义
        （:class:`OperationScopeNotVisibleError`），避免用错误类型泄露「该 id 存在」。

        `authorize` 只拿到 :class:`AuthorizedOperationRef`（scope 事实），拿不到
        operation 行 —— 「当前权限」的判定不需要业务行，需要业务行才能判就说明
        scope 模型漏了字段。
        """
        row = await self._repo.resolve_scope(
            resource_kind=ScopeResourceKind.sync_operation,
            resource_id=str(operation_id),
        )
        if row is None:
            raise OperationScopeNotVisibleError(
                f"operation {operation_id} 在 scope index 中不可见（不存在或已 retire）"
            )
        if (
            row.project_id != declared_project_id
            or row.wp_id != declared_wp_id
            or str(row.entry_id) != str(declared_entry_id)
        ):
            raise OperationScopeNotVisibleError(
                f"operation {operation_id} 与显式声明的 project/wp/entry scope 不符 ——"
                "与「不存在」共用同一 404 语义，不得据此推断该 id 是否存在"
            )
        stages = (ReadStage.requested_scope_resolved,)
        ref = AuthorizedOperationRef(
            operation_id=operation_id,
            project_id=row.project_id,
            wp_id=row.wp_id,
            entry_id=str(row.entry_id),
            room_id=row.room_id,
            generation=(None if row.generation is None else int(row.generation)),
            action=str(action),
            stages=stages,
        )
        if authorize is not None:
            verdict = authorize(ref)
            if inspect.isawaitable(verdict):
                verdict = await verdict
            if not verdict:
                raise ScopeAuthorizationDeniedError(
                    f"operation {operation_id} 的 scope 可见，但当前权限不允许 "
                    f"action={action!r}（403，与 404 分型）"
                )
        return AuthorizedOperationRef(
            operation_id=ref.operation_id,
            project_id=ref.project_id,
            wp_id=ref.wp_id,
            entry_id=ref.entry_id,
            room_id=ref.room_id,
            generation=ref.generation,
            action=ref.action,
            stages=stages + (ReadStage.requested_action_authorized,),
        )

    # ─────────────────────────────────────────────────────────────────
    # 6.3 读路径第 2~4 步：direct-primary → canonicalize → 只要求 primary 绑定
    # ─────────────────────────────────────────────────────────────────

    async def canonicalize_authorized(
        self, ref: AuthorizedOperationRef, *, require_application: bool = True
    ) -> CanonicalRead:
        """固定四步的第 2~4 步。只接受已授权的 :class:`AuthorizedOperationRef`。

        * 第 2 步 direct-primary invariant 与第 3 步 canonicalize 都委派
          :meth:`WorkpaperSyncRepository.resolve_canonical_operation`（唯一实现，
          不在此重写一份链校验）；
        * 第 4 步只要求 **canonical primary** 唯一绑定 application。
          `requested` 是合法 duplicate 时，它自身 `application_id` 为 NULL 是**正确**
          形态，绝不能因此报错（AC 5.5 末段）。

        本方法**不创建**任何 operation/application：retry 复用既有 timeline
        （AC 4.1「不得新建 application/operation」）。
        """
        if not isinstance(ref, AuthorizedOperationRef):
            raise ScopeAuthorizationDeniedError(
                "canonicalize 只接受 authorize_operation_scope 产出的 "
                f"AuthorizedOperationRef，实得 {type(ref).__name__} —— "
                "authorization-first 由参数类型强制"
            )
        if ReadStage.requested_action_authorized not in ref.stages:
            raise ScopeAuthorizationDeniedError(
                "AuthorizedOperationRef 缺 requested_action_authorized 阶段 —— "
                "未完成当前权限重验的引用不得进入 canonicalize"
            )
        requested = (
            await self._session.execute(
                sa.select(WorkpaperSyncOperation).where(
                    WorkpaperSyncOperation.id == ref.operation_id
                )
            )
        ).scalar_one_or_none()
        if requested is None:
            raise OperationScopeNotVisibleError(
                f"operation {ref.operation_id} 行不存在（scope index 与业务行不一致）"
            )
        requested_shape = classify_operation_shape(
            application_id=requested.application_id,
            duplicate_of_operation_id=requested.duplicate_of_operation_id,
            state=requested.state,
        )
        stages = ref.stages + (ReadStage.requested_operation_loaded,)

        canonical, _shape = await self._repo.resolve_canonical_operation(ref.operation_id)
        if requested_shape is OperationShape.duplicate:
            stages = stages + (ReadStage.direct_primary_verified,)
        stages = stages + (ReadStage.canonicalized,)

        app_id = canonical.application_id
        if require_application:
            if app_id is None:
                raise CanonicalPrimaryUnboundError(
                    f"canonical primary {canonical.id} 未绑定 application —— "
                    "只要求 canonical primary 唯一绑定，但它必须绑定"
                )
            bound = int(
                (
                    await self._session.execute(
                        sa.select(sa.func.count())
                        .select_from(WorkpaperSyncOperation)
                        .where(WorkpaperSyncOperation.application_id == app_id)
                    )
                ).scalar_one()
            )
            if bound != 1:
                raise CanonicalBindingError(
                    f"application {app_id} 被 {bound} 个 operation 绑定 —— "
                    "canonical primary 必须**唯一**绑定"
                )
            stages = stages + (ReadStage.canonical_application_bound,)

        effective: int | None = None
        if app_id is not None:
            effective = int(
                (
                    await self._session.execute(
                        sa.select(WorkpaperContentApplication.effective_request_sequence)
                        .where(WorkpaperContentApplication.id == app_id)
                    )
                ).scalar_one()
            )
        return CanonicalRead(
            requested_operation=requested,
            requested_shape=requested_shape,
            canonical_operation=canonical,
            canonical_application_id=app_id,
            effective_request_sequence=effective,
            stages=stages,
        )

    async def read_operation(
        self,
        *,
        operation_id: uuid.UUID,
        declared_project_id: uuid.UUID,
        declared_wp_id: uuid.UUID,
        declared_entry_id: str,
        action: str,
        authorize: AuthorizeAction | None = None,
        require_application: bool = True,
    ) -> CanonicalRead:
        """四步合一的便利入口（GET / timeline / conflict / retry / resolve 共用）。

        便利入口存在的前提是**两段仍然分开可用**：Task 27/28 的 resolve 需要在授权后、
        canonicalize 前插入 fence 比对，若只提供合一入口，那些调用点就会绕过本模块
        自己拼一遍顺序 —— 那正是本模块要消灭的东西。
        """
        ref = await self.authorize_operation_scope(
            operation_id=operation_id,
            declared_project_id=declared_project_id,
            declared_wp_id=declared_wp_id,
            declared_entry_id=declared_entry_id,
            action=action,
            authorize=authorize,
        )
        return await self.canonicalize_authorized(ref, require_application=require_application)

    # ─────────────────────────────────────────────────────────────────
    # 6.4 durable correlation 的服务包装
    # ─────────────────────────────────────────────────────────────────

    async def correlate(
        self,
        *,
        operation_id: uuid.UUID,
        incoming_artifact_id: uuid.UUID,
        current_revision: int,
        adapter_id: str,
        delivery_id: uuid.UUID | None = None,
        actor_type: ActorType = ActorType.callback,
        actor_id: uuid.UUID | None = None,
    ) -> CorrelationOutcome:
        """委派 :meth:`WorkpaperSyncRepository.correlate_durable_incoming` 并**自证收敛形态**。

        自证的是 commit 前的三条 P18 不变量（仓储层已保证，这里再验一次是因为
        本模块是 Task 24/26/27 的入口，入口处失败比下游 DB 约束失败可诊断得多）：

        * winner ⇒ shape=primary 且 `application_id` 非空、`duplicate_of` 为空；
        * loser ⇒ shape=duplicate 且 `application_id` 为空、`duplicate_of` 直指 primary；
        * 无论哪种，`effective_request_sequence >= origin_request_sequence`。
        """
        outcome = await self._repo.correlate_durable_incoming(
            operation_id=operation_id,
            incoming_artifact_id=incoming_artifact_id,
            current_revision=current_revision,
            adapter_id=adapter_id,
            delivery_id=delivery_id,
            actor_type=actor_type,
            actor_id=actor_id,
        )
        self._assert_convergence(outcome)
        return outcome

    @staticmethod
    def _assert_convergence(outcome: CorrelationOutcome) -> None:
        op = outcome.operation
        app = outcome.application
        assert_correlation_convergence(
            reported_shape=outcome.shape,
            application_id=op.application_id,
            duplicate_of_operation_id=op.duplicate_of_operation_id,
            state=op.state,
            canonical_application_id=app.id,
            canonical_primary_operation_id=outcome.canonical_primary_operation_id,
            origin_request_sequence=int(app.origin_request_sequence),
            effective_request_sequence=int(app.effective_request_sequence),
        )

    # ─────────────────────────────────────────────────────────────────
    # 6.5 recovery claim（authorization-first 包装）
    # ─────────────────────────────────────────────────────────────────

    async def claim_recovery(
        self,
        *,
        case_id: uuid.UUID,
        claiming_participant_id: uuid.UUID,
        prior_confirmation_id: uuid.UUID,
        idempotency_key: str,
        adapter_id: str,
        adapter_build_digest: str,
        contributor_snapshot_digest: str,
        current_revision: int,
        actor_id: uuid.UUID | None = None,
    ) -> RecoveryClaimOutcome:
        """recovery claim：一个事务内建 request + shell + application，commit 前定形。

        `claim` 之前 request/application/operation 三者全空（Task 22 已实测）；本方法
        只在 commit **前**加一条断言：shell 必须已落成 primary 或 direct terminal
        duplicate。AC 4.1/5.8 的原文是「commit 前 shell 必须成为 primary 或 direct
        terminal duplicate」—— 若只在 commit 后查，`nullable-operation` 的 case 已经
        进入普通 retry 队列，为时已晚。
        """
        outcome = await self._repo.claim_recovery_case(
            case_id=case_id,
            claiming_participant_id=claiming_participant_id,
            prior_confirmation_id=prior_confirmation_id,
            idempotency_key=idempotency_key,
            adapter_id=adapter_id,
            adapter_build_digest=adapter_build_digest,
            contributor_snapshot_digest=contributor_snapshot_digest,
            current_revision=current_revision,
            actor_id=actor_id,
        )
        shape = classify_operation_shape(
            application_id=outcome.operation.application_id,
            duplicate_of_operation_id=outcome.operation.duplicate_of_operation_id,
            state=outcome.operation.state,
        )
        assert_recovery_claim_shape(
            operation_shape=shape,
            application_id=(None if outcome.application is None else outcome.application.id),
            case_application_id=outcome.case.application_id,
        )
        return outcome

    # ─────────────────────────────────────────────────────────────────
    # 6.6 只读投影：nullable-operation recovery case 不得进普通 retry
    # ─────────────────────────────────────────────────────────────────

    async def retry_eligibility(self, *, operation_id: uuid.UUID | None) -> bool:
        """普通 retry 的准入：`operation_id` 为 NULL 的 recovery case 一律不得进入。

        做成显式方法而不是让调用点写 `if op_id:` —— 后者散落在每个入口，
        少写一处就是「claim 前的 case 被当成普通 operation 重试」，
        而那会伪造出一条 claim 之前不该存在的 operation timeline（AC 5.8 / 14.3）。
        """
        return operation_id is not None

    async def room_of(self, room_id: uuid.UUID) -> WorkpaperOoRoom:
        """读 room 行（fence 比对用；不加锁）。"""
        return (
            await self._session.execute(
                sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == room_id)
            )
        ).scalar_one()

    async def scope_rows_of(
        self, *, resource_kind: ScopeResourceKind, resource_ids: Iterable[str]
    ) -> list[WorkpaperSyncScopeIndex]:
        """批量 scope 行（只读，供 timeline 查询做 scope 过滤）。"""
        ids = [str(r) for r in resource_ids]
        if not ids:
            return []
        return list(
            (
                await self._session.execute(
                    sa.select(WorkpaperSyncScopeIndex).where(
                        WorkpaperSyncScopeIndex.resource_kind == resource_kind.value,
                        WorkpaperSyncScopeIndex.resource_id.in_(ids),
                    )
                )
            )
            .scalars()
            .all()
        )


_ = OperationState  # 显式保留：状态枚举供调用方比对 shell 终态，不做 re-export 门面
