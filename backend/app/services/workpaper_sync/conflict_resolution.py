# -*- coding: utf-8 -*-
"""冲突预览 / resolve fence / recovery-aware retry / opaque-version rollback。

spec: `.kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/`
Wave 2 · Task 27 · Requirements 6.18, 8.1~8.12, 10.10
Properties: **P35 / P36 / P37 / P38 / P43 / P65 / P67**

═══ 一、本模块在链路上的位置 ═══

Task 26 的 :class:`~.oo_to_html.OoToHtmlCoordinator` 负责「durable incoming →
merged projection → 新 revision」；本模块负责它**外面那一圈**：

```
GET  …/operations/{id}/conflicts   → preview()    冲突预览（AC 8.1 / 8.2）
POST …/operations/{id}/resolve     → resolve()    fence → 折叠裁决 → 发布（AC 8.3~8.6）
POST …/operations/{id}/retry       → retry()      从 durable incoming 重试（AC 8.9）
POST …/versions/{version_id}/rollback → rollback() 不可变 opaque UUID 定位（AC 8.7 / 8.8）
```

四个入口共用**同一条固定读路径**（Task 23 的四步，AC 5.5 末段 / 8.5）::

    requested id authorization-first guard
      → direct primary 同 scope/bundle invariant
      → canonicalize
      → 只要求 canonical primary 唯一绑定 application

顺序不可交换，且本模块**不自己抄一份**：授权走
:meth:`~.request_application.RequestApplicationService.authorize_operation_scope`
（只读非敏感 scope index），归一走
:meth:`~.request_application.RequestApplicationService.canonicalize_authorized`
（只接受 :class:`~.request_application.AuthorizedOperationRef`，「先授权后 canonicalize」
由参数类型强制）。

═══ 二、Task 26 那笔欠账在这里还完 ═══

Task 26 收口审计抓到的第四个真实缺陷是「人工裁决被校验覆盖率后丢弃」：
`apply_durable_incoming` 收下 `resolutions` 却把它丢掉，分派走无冲突分支发布
`merge.merged` —— 而 `merge.merged` 对**每个冲突字段保留 current 侧值**。于是审计师点
「取 incoming」，落库的是 current，而 extract 等值（两边同为错值）、roundtrip、最终
fence 全部照常通过。Task 26 因此加了 fail-closed 闸门并把欠账登记成
`DEFERRED_ADJUDICATION_CONSUMER`。

Task 27 把它接线，落点是**三层**（缺任何一层都会退回静默错值）：

1. :func:`~.oo_to_html.settle_adjudicated_projection` —— 「要发布哪份 projection」的
   唯一决策点，带裁决时走 :func:`~.merge.apply_resolutions`；
2. `ContentMutationService._settle_projection` —— **独立重算**同一个折叠并逐字节比对，
   折叠错/忘折叠一律 `AdjudicationNotFoldedError`（唯一 commit 边界上的第二把锁）；
3. `merge.projection_requires_client_refresh` —— refresh 判据从 `MergeOutcome.merged`
   切到真正落库的那份 projection，否则 client-confirmed 基线会被推进到客户端从未见过
   的内容上（AC 8.12 末句）。

登记随之从 `deferred` 翻转成 :data:`~.oo_to_html.RETIRED_ADJUDICATION_CONSUMER`
（`retired`），而不是被删掉 —— 删掉之后没人能证明欠账真的还了。

═══ 三、fence 判据不在本模块 ═══

AC 8.5 的不可交换顺序（duplicate direct-primary invariant → canonical identity →
generation/write fence/permission/client epoch → refresh-required → identity ↔ room
latest durable → conflict digest → current revision）是 Task 14 的纯函数
:func:`~.conflicts.evaluate_resolve_fence`。本模块只做三件事：

* 在 room lock 内**读出**服务端真值（:class:`~.conflicts.FrozenApplicationFence` /
  :class:`~.conflicts.RoomDurableFence`）；
* 把 :class:`~.conflicts.FenceDecision` 映射成 HTTP 语义（:data:`RESOLVE_DECISION_STATUS`）
  与**可分辨的异常类型**；
* proceed/fold 时把裁决交给 Task 26 的 coordinator，并在写裁决轨迹**之前**自证它真的
  落地了（:func:`assert_resolve_apply_landed`）。

🔴 第三点不是防御性代码：coordinator 在 incoming **已 durable** 之后刻意不抛异常
（AC 5.7/5.8：durable 之后返回非零 ack 等于静默丢件），失败只体现在 `outcome.result`
上。不查它时「复核锁定/归档/项目不可见」会让 resolve 回 200 并把冲突行标成「已裁决」，
而内容一个字都没发布 —— 这三条 fence 只活在 `AuthorizationProbe` 后面，room fence 读不到，
所以本模块自己那道 fence 也拦不住（2026-08-28 真库实测）。

🔴 `fold` 与 `superseded` 必须分成两个异常/两条路：同一 canonical application 因
same-key duplicate 抬高 effective sequence 时只能 fold（规范化后继续同一 conflict set），
绝不能判自己 stale —— 那是 AC 5.5 明令禁止的 duplicate→primary→stale 循环。

═══ 四、rollback 只认不可变 opaque UUID ═══

路由是 `/versions/{version_id}/rollback`，`version_id` 是 content version 的 immutable
opaque UUID。per-wp numeric `revision` 只做展示与 expected-current 乐观锁，**禁止**作
route/scope/resource key —— 两个 wp 都有 `revision 1`，用它定位必然跨 scope 碰撞。
scope 缺失、跨 project/wp/entry 与「不存在」共用**同一** 404 语义
（:class:`ContentVersionNotFoundError`），不得用错误类型泄露「该 id 存在」。

rollback source 只能是该 UUID 定位到的**已发布** representation artifact
（`kind=canonical, state=published`）：`incoming`（durable 或 quarantined）与 upgrade
candidate 都不可作源，判据走 Task 13 的
:func:`~.adapters.base.assert_substrate_usable`（三层拒绝的复用，不另写一套）。

业务 projection 未变化时 **revision 保持不变**（AC 6.18 / 9.10 / Property 67）：
「回滚到当前内容」与「回滚到另一个 projection 相同的版本」都只可能是表示层差异，
本入口零写入并把结果标 `revision_unchanged=True`，纯 representation rollback 走
:class:`~.representations.RepresentationService`。

═══ 五、本模块不做的事 ═══

* **不注册路由**（Task 28）。它只提供服务方法 + `RESOLVE_DECISION_STATUS` 映射；
  route scope 的解析、`Idempotency-Key`、统一 404/403 envelope 归 router。
* **不 commit 业务内容**：唯一 commit 边界仍是
  :meth:`~.content_mutation.ContentMutationService.commit`（Property 61）。本模块只在
  写「裁决轨迹」这一件审计事实时提交自己的短事务。
* **不调 OnlyOffice Command Service**（Property 38：retry 一律不再 forcesave）。
  本模块源码里不得出现任何 Command Service 符号，判据在守卫侧用 AST 反查。
* 不实现任何 Excel/Word 载体逻辑：adapter 由调用方按 Task 13 的 registry 提供。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, Mapping, Sequence

import sqlalchemy as sa

from app.models.workpaper_sync_models import (
    WorkpaperContentApplication,
    WorkpaperContentRepresentation,
    WorkpaperContentVersion,
    WorkpaperForcesaveRequest,
    WorkpaperOoParticipant,
    WorkpaperOoRoom,
    WorkpaperSyncConflict,
)
from app.services.workpaper_sync.adapters.base import (
    Projection,
    SubstrateRole,
    WorkpaperSyncAdapter,
    assert_substrate_usable,
)
from app.services.workpaper_sync.conflicts import (
    ConflictKind,
    FenceDecision,
    FenceEvaluation,
    FenceReason,
    FieldSource,
    FrozenApplicationFence,
    ProtectionPolicy,
    RequestedOperationLink,
    ResolutionChoice,
    ResolveFenceRequest,
    RoomDurableFence,
    SuggestedAction,
    assert_all_conflicts_resolved,
    evaluate_resolve_fence,
    resolved_value_for,
)
from app.services.workpaper_sync.content_mutation import (
    ROLLBACK,
    BusinessMutation,
    ContentCommitPlan,
    ContentMutationService,
    projection_canonical_digest,
)
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.merge import ContractIndex
from app.services.workpaper_sync.models import (
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    BundleSlot,
    OperationScope,
    OperationShape,
    OperationState,
    RoomState,
    ScopeResourceKind,
    SyncDomainError,
    classify_operation_shape,
)
from app.services.workpaper_sync.oo_to_html import OoToHtmlCoordinator, OoToHtmlOutcome
from app.services.workpaper_sync.repository import WorkpaperSyncRepository
from app.services.workpaper_sync.request_application import (
    RequestApplicationService,
)
from app.services.workpaper_sync.resolution import (
    CanonicalResolutionService,
    ResolutionIntent,
)

__all__ = [
    # 异常
    "ConflictResolutionError",
    "ResolveFenceRejectedError",
    "ResolveSupersededError",
    "ResolveRebaseRequiredError",
    "ResolveWithoutConflictError",
    "ResolveAuthorizationStaleError",
    "ResolveApplyFailedError",
    "FrozenContractDriftError",
    "RecoveryCaseRetryForbiddenError",
    "ContentVersionNotFoundError",
    "RollbackSourceNotPublishedError",
    "RollbackSourceQuarantinedError",
    "RollbackRevisionRewindError",
    # 常量 / 映射
    "RESOLVE_DECISION_STATUS",
    "RESOLVE_REJECT_HTTP_CODE",
    "ROLLBACK_INTENT",
    "REFUSED_AT_SCOPE_INDEX",
    "REFUSED_AT_BUSINESS_ROW",
    "REFUSED_AT_STAGES",
    # 值对象
    "ConflictPreviewItem",
    "ConflictPreviewGroup",
    "ConflictPreview",
    "ResolveOutcome",
    "RollbackOutcome",
    # 纯判据
    "http_status_for",
    "RESOLVE_LANDED_RESULTS",
    "REBASE_ADMISSIBLE_RESULTS",
    "assert_resolve_apply_landed",
    "assert_retry_operation_eligible",
    "assert_rollback_source_publishable",
    "assert_frozen_contract_matches_bundle",
    # 服务
    "ConflictResolutionService",
]


def _now() -> datetime:
    """服务端时钟（aware）。timestamptz 必须在 Python 侧构造 datetime。"""
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 0. 异常：每条拒绝原因一个类型（共用 error_code 会让靠前的分支永久不可达）
# ═══════════════════════════════════════════════════════════════════════════


class ConflictResolutionError(SyncDomainError):
    error_code = "conflict_resolution_failed"


#: 统一 404 的两道门。共用一个 `error_code`（不得泄露存在性），但**守卫**必须能分辨
#: 是哪一道在起作用 —— 否则删掉前一道时后一道接住同一输入、抛同一类型 ⇒ 判 GREEN。
REFUSED_AT_SCOPE_INDEX: Final[str] = "scope_index"
REFUSED_AT_BUSINESS_ROW: Final[str] = "business_row"
REFUSED_AT_STAGES: Final[frozenset[str]] = frozenset(
    {REFUSED_AT_SCOPE_INDEX, REFUSED_AT_BUSINESS_ROW}
)


class ResolveFenceRejectedError(ConflictResolutionError):
    """fence 判定 `rejected`：授权/generation/write fence/epoch/冲突集身份变化。

    携带 `reason` 与 `fence_reason`，让 router 能把**哪一条**乐观锁失配透出去
    （AC 8.5 要求逐项可分辨，不是笼统「409 冲突」）。
    """

    error_code = "resolve_fence_rejected"

    def __init__(self, message: str, *, evaluation: FenceEvaluation) -> None:
        super().__init__(message)
        self.evaluation = evaluation
        #: 三类 resolve 拒绝**都**带 `fence_reason`：router 与守卫按它归因到具体哪一条
        #: 乐观锁。只在其中一类上带的话，另一类的归因只能靠读文案（不可机器核对）。
        self.fence_reason = evaluation.reason


class ResolveSupersededError(ConflictResolutionError):
    """room latest durable 指向**另一个**更新的 canonical application ⇒ 旧 conflict 作废。

    🔴 与 :class:`ResolveFenceRejectedError` 分型的必要性：superseded 的用户动作是
    「对最新 operation 重建裁决」，而 rejected 的动作是「重开编辑器/重新授权」。
    共用一个 error_code 时前端只能给同一句话，而两者的补救路径完全不同。
    """

    error_code = "resolve_conflict_superseded"

    def __init__(
        self,
        message: str,
        *,
        evaluation: FenceEvaluation,
        superseding_application_id: uuid.UUID | None,
    ) -> None:
        super().__init__(message)
        self.evaluation = evaluation
        self.fence_reason = evaluation.reason
        self.superseding_application_id = superseding_application_id


class ResolveRebaseRequiredError(ConflictResolutionError):
    """current revision 已推进但没有不同的较新 application ⇒ 按**原** frozen bundle rebase。

    异常携带 rebase 之后的冲突集摘要与条数：AC 8.5 要求「返回按原 immutable definition
    bundle/authority model 重建的 rebased conflict」，光说「409」等于让客户端自己猜。
    """

    error_code = "resolve_rebase_required"

    def __init__(
        self,
        message: str,
        *,
        evaluation: FenceEvaluation,
        rebased_conflict_set_digest: str | None,
        rebased_conflict_count: int,
        rebased_attempt: int,
    ) -> None:
        super().__init__(message)
        self.evaluation = evaluation
        self.fence_reason = evaluation.reason
        self.rebased_conflict_set_digest = rebased_conflict_set_digest
        self.rebased_conflict_count = rebased_conflict_count
        self.rebased_attempt = rebased_attempt


class ResolveWithoutConflictError(ConflictResolutionError):
    """resolve 请求一条裁决都没带 —— 那不是裁决，是普通 apply。

    与引擎层的 :class:`~.oo_to_html.AdjudicationWithoutConflictError`（带裁决但零冲突）
    正好是**反向**的两条判据，各自独立可证伪。
    """

    error_code = "resolve_requires_resolutions"


class FrozenContractDriftError(ConflictResolutionError):
    """传入 contract 与 application frozen bundle 的 contract slot digest 不一致。

    冲突预览与裁决折叠都必须按**历史 operation 冻结的那份** contract 进行；按 registry
    当前 alias 渲染预览，审计师看到的业务标签/单元格地址就可能已经漂移到新模板上
    （AC 6.2 / 7.10「历史 retry 不得加载 registry 当前 alias」的预览侧）。
    """

    error_code = "frozen_contract_digest_drift"


class ResolveAuthorizationStaleError(ConflictResolutionError):
    """裁决落地时最终授权 fence 失败（复核锁定 / 归档 / 项目不可见 / generation
    supersede / write fence 提升 / contributor 漂移 / approved bundle 被换）。

    🔴 这条判据的由来（2026-08-28 真库实测抓到的生产缺陷）：Task 26 的
    `apply_durable_incoming` 在 incoming **已 durable** 之后**刻意不抛异常** ——
    它把失败落成 `OoToHtmlResult.authorization_stale / error` 终态并保留 incoming
    （AC 5.7/5.8：durable 之后返回非零 ack 等于静默丢件）。于是 `resolve` 若不看
    `outcome.result` 就会：

    * 照常调 `mark_conflicts_resolved` ⇒ 冲突行被标成「已裁决」，而内容**一个字都没发布**；
    * 照常返回 `decision=proceed` / `http_status=200` ⇒ 审计师看到「裁决成功」。

    实测形态：`workflow_locked=True` 的 resolve 返回 `conflict_rows_marked=1`、
    revision 不变、version/pointer 全不动。AC 8.4（复核锁定/归档必须拒）、AC 8.5
    （期间 fence 变化必须拒）、AC 8.6（轨迹要记前后 revision）与 Property 43 同时被破。

    与 :class:`ResolveFenceRejectedError` **分型**：那一条是 resolve **自己的** fence
    在调 coordinator **之前**拒（零副作用、可重试），本条是落地阶段的最终 fence 在
    durable **之后**拒 —— 不可重试，只能走 supersede/recovery（AC 10.10 末句）。
    共用一个 `error_code` 会让前端只能给同一句话，而两者的补救路径完全不同。
    """

    error_code = "resolve_authorization_stale"

    def __init__(
        self, message: str, *, apply_result: str, apply_error_code: str | None
    ) -> None:
        super().__init__(message)
        self.apply_result = apply_result
        self.apply_error_code = apply_error_code


class ResolveApplyFailedError(ConflictResolutionError):
    """裁决折叠/rematerialize/发布阶段失败（`OoToHtmlResult.error`）。

    与 :class:`ResolveAuthorizationStaleError` 分型：本条**可**在修掉原因后重试
    （extract/merge/materialize 失败、等值校验不通过、artifact digest 不符…），
    而授权失效不可重试。两者都必须在写裁决轨迹**之前**拦下 —— 轨迹是审计事实，
    不能记在一次没有落地的应用上。
    """

    error_code = "resolve_apply_failed"

    def __init__(
        self, message: str, *, apply_result: str, apply_error_code: str | None
    ) -> None:
        super().__init__(message)
        self.apply_result = apply_result
        self.apply_error_code = apply_error_code


class RecoveryCaseRetryForbiddenError(ConflictResolutionError):
    """`operation_id=NULL` 的 unmatched/ambiguous recovery case 进了普通 retry。

    AC 8.9 原文：「download-only 永不创建 operation，不得把 nullable operation id 传给
    普通 retry」。这条判据必须在**任何**资源查找之前生效 —— 它不读任何行，因此也不泄露
    任何存在性。
    """

    error_code = "recovery_case_requires_claim_before_retry"


class ContentVersionNotFoundError(ConflictResolutionError):
    """rollback 目标 content version 不可见 —— **不存在与越权共用同一语义**。

    🔴 故意只有一个类型、一个 `error_code`：跨 project/wp/entry 与「UUID 不存在」必须
    无法区分，否则「换个 wp 试同一个 UUID，看报什么错」就能探测别的项目有哪些版本
    （AC 8.7 末句 / 10.6 的统一 404）。

    但两个 raise 点（scope index 门 / 业务行门）必须能被**守卫**分辨 —— 否则前一道门被
    删掉时后一道会接住同一个输入、抛同一个类型，变异检验判 GREEN（本任务首轮实测如此）。
    因此带一个**内部**标记 :attr:`refused_at`：它不进 `error_code`、不进响应信封，
    只供守卫断言「是哪一道门在起作用」。
    """

    error_code = "content_version_not_found"

    def __init__(self, message: str, *, refused_at: str) -> None:
        super().__init__(message)
        if refused_at not in REFUSED_AT_STAGES:
            raise ConflictResolutionError(
                f"refused_at={refused_at!r} 不在封闭词表 {sorted(REFUSED_AT_STAGES)} 内 —— "
                "标记必须是可枚举的门，不是自由文本"
            )
        #: 哪一道门拒绝的。**不对外暴露**（router 只映射 `error_code` → 404）。
        self.refused_at = refused_at


class RollbackSourceNotPublishedError(ConflictResolutionError):
    """rollback 源 representation 不是已发布 canonical artifact（candidate / staged / incoming）。"""

    error_code = "rollback_source_not_published"


class RollbackSourceQuarantinedError(ConflictResolutionError):
    """rollback 源 artifact 处于 quarantined —— 只允许 download-only/expire/retention。

    与 :class:`RollbackSourceNotPublishedError` 分型：前者是「状态不对，可能还能修」，
    本条是**安全隔离**，永不 release、永不转 durable（Requirement 5.6 / 8.10）。
    """

    error_code = "rollback_source_quarantined"


class RollbackRevisionRewindError(ConflictResolutionError):
    """rollback 试图让 current revision 倒退。

    AC 8.7：回滚**创建新版本**指向历史内容，绝不删除或原地改写历史，也不把 revision
    往回拨（否则 `UNIQUE(wp_id, revision)` 与全部历史读取的定位都会错位）。
    """

    error_code = "rollback_revision_rewind_forbidden"


# ═══════════════════════════════════════════════════════════════════════════
# 1. decision → HTTP 语义（Task 28 的 router 直接消费这张表）
# ═══════════════════════════════════════════════════════════════════════════

#: `FenceDecision` → HTTP status。**必须覆盖枚举全集**，守卫按 `set(FenceDecision)` 反查：
#: 漏一个成员意味着某条判定在 router 层没有映射，而 `dict.get(x, 200)` 这种写法会把
#: 未映射的拒绝静默变成成功（fail-open 的经典形态）。
RESOLVE_DECISION_STATUS: Final[Mapping[FenceDecision, int]] = {
    FenceDecision.proceed: 200,
    FenceDecision.fold: 200,
    FenceDecision.rebase: 409,
    FenceDecision.superseded: 409,
    FenceDecision.rejected: 409,
}

#: 每个 `FenceReason` 的机器可读拒绝码（前端按它选补救动作）。同样必须覆盖枚举全集。
RESOLVE_REJECT_HTTP_CODE: Final[Mapping[FenceReason, str]] = {
    FenceReason.ok: "OK",
    FenceReason.same_application_sequence_fold: "SEQUENCE_FOLDED",
    FenceReason.canonical_application_mismatch: "CANONICAL_APPLICATION_MISMATCH",
    FenceReason.room_generation_changed: "ROOM_GENERATION_CHANGED",
    FenceReason.write_fence_changed: "WRITE_FENCE_CHANGED",
    FenceReason.permission_epoch_changed: "PERMISSION_EPOCH_CHANGED",
    FenceReason.client_edit_epoch_changed: "CLIENT_EDIT_EPOCH_CHANGED",
    FenceReason.room_refresh_required: "ROOM_REFRESH_REQUIRED",
    FenceReason.newer_canonical_application: "CONFLICT_SUPERSEDED",
    FenceReason.conflict_set_changed: "CONFLICT_SET_CHANGED",
    FenceReason.current_revision_changed: "CONFLICT_REBASED",
    FenceReason.requested_duplicate_link_invalid: "DUPLICATE_LINK_INVALID",
}

#: rollback 的 canonical resolver 意图。写成常量而不是每处传字面量：
#: `INTENT_POLICY[rollback]` 是 `requires_frozen_identity=True`，也就是「必须显式给
#: frozen representation_id、禁止按 entry current pointer 重组 bundle」。
ROLLBACK_INTENT: Final[ResolutionIntent] = ResolutionIntent.rollback


def http_status_for(decision: FenceDecision) -> int:
    """decision → HTTP status，**未映射即抛**。

    刻意不写 `RESOLVE_DECISION_STATUS.get(decision, 200)`：默认值会把新增的拒绝判定
    静默变成 200（fail-open）。新增 `FenceDecision` 成员时这里必须一起改。
    """
    try:
        return RESOLVE_DECISION_STATUS[decision]
    except KeyError as exc:  # pragma: no cover - 守卫按枚举全集反查，正常不可达
        raise ConflictResolutionError(
            f"FenceDecision {decision!r} 没有 HTTP 映射 —— 新增判定必须同时登记，"
            "否则 router 会把它当成功返回"
        ) from exc


# ═══════════════════════════════════════════════════════════════════════════
# 2. 纯判据（可用合成输入逐条喂 ⇒ 变异检验能证伪）
# ═══════════════════════════════════════════════════════════════════════════


def assert_retry_operation_eligible(operation_id: uuid.UUID | None) -> uuid.UUID:
    """普通 retry 的准入闸：`operation_id` 为 NULL 一律拒绝（AC 8.9 / Property 38）。

    返回非空 id，让调用点无法「查了却不用」—— 写成 `-> None` 时把调用行删掉不会有任何
    类型错误，而返回值被后续步骤消费时删调用点立刻炸。

    做成模块级纯函数而不是调用点一行 `if`：散落在四个入口时少写一处，claim 之前的
    recovery case 就会被当成普通 operation 重试，从而伪造出一条本不该存在的 operation
    timeline（AC 5.8 / 14.3）。
    """
    if operation_id is None:
        raise RecoveryCaseRetryForbiddenError(
            "unmatched/ambiguous recovery case 在 claim 之前 `operation_id/application_id` "
            "都是 NULL，不得进入普通 retry —— 必须先经 authorization-first claim 在一个"
            "事务里创建 request + shell 并创建/命中 application、落为 primary 或 direct "
            "duplicate；download-only 永远零 operation（AC 5.8 / 8.9）"
        )
    return operation_id


#: 允许写裁决轨迹并回 2xx 的 apply 终态。
#:
#: 只有这两个：`applied` = 内容与指针都推进了；`refresh_required` = 内容**已发布**
#: 但 merged≠incoming，于是 client-confirmed 基线不推进并轮转 generation
#: （AC 8.12 末句）—— 裁决本身确实落地了，轨迹该写。
#:
#: 其余三个终态（`authorization_stale` / `error` / `conflict`）都意味着**什么都没发布**，
#: 此时写轨迹 = 把「已裁决」这条审计事实记在一次没有发生的应用上。
RESOLVE_LANDED_RESULTS: Final[frozenset[str]] = frozenset(
    {"applied", "refresh_required"}
)


#: rebase 探测允许的终态 = 落地态 + `conflict`。
#:
#: rebase 分支只为「按**原** frozen bundle 重建 conflict set」，因此 `conflict` 是它的
#: 正常结果；`applied`/`refresh_required` 也可达（重算后字段级不再冲突 ⇒ 自动合并并发布，
#: 客户端手里那份 conflict set 随之作废，仍需按 409 重新取）。只有失败终态必须原样透出，
#: 不得包成 409 rebase-required —— 那会让「授权已失效」表现成「刷新一下再来」。
REBASE_ADMISSIBLE_RESULTS: Final[frozenset[str]] = RESOLVE_LANDED_RESULTS | {"conflict"}


def assert_resolve_apply_landed(
    *,
    result: str,
    error_code: str | None,
    error_stage: str | None,
    where: str,
    landed: frozenset[str] = RESOLVE_LANDED_RESULTS,
) -> None:
    """裁决落地自证：apply **没有真正落地**时一律拒，且按不可重试/可重试分型。

    🔴 为什么必须有这道判据（2026-08-28 真库实测抓到的生产缺陷）：Task 26 的
    `apply_durable_incoming` 在 incoming 已 durable 之后**不抛异常** —— 它把失败落成
    终态并保留 incoming（AC 5.7/5.8）。`resolve` 因此拿到的是一个「长得像成功」的
    outcome：不看 `result` 就会写裁决轨迹并回 200，而 revision、version、pointer
    一个都没动。实测触发路径：复核锁定 / 归档 / 项目不可见（这三样只活在
    `AuthorizationProbe` 后面，room fence 读不到，所以 resolve 自己的 fence 拦不住）。

    做成模块级纯函数而不是 `resolve` 里两行 `if`：纯函数能用合成输入逐个终态喂，
    于是「删掉这道判据」在变异检验里必然打红；内嵌 `if` 在正确实现下大部分终态不可达。
    """
    if result in landed:
        return
    if result == "authorization_stale":
        raise ResolveAuthorizationStaleError(
            f"{where}：裁决在落地阶段被最终授权 fence 拒绝"
            f"（{error_code or 'unknown'} @ {error_stage or 'unknown'}）—— "
            "内容一个字都没发布，裁决轨迹不得写入；该终态不可重试，"
            "只能走 supersede/recovery（AC 8.4 / 8.5 / 10.10 / Property 43）",
            apply_result=result,
            apply_error_code=error_code,
        )
    raise ResolveApplyFailedError(
        f"{where}：裁决落地失败（result={result}，{error_code or 'unknown'} @ "
        f"{error_stage or 'unknown'}）—— 内容未发布，裁决轨迹不得写入；"
        "incoming 仍保留，可在修掉原因后按同一 application 重试（AC 8.9 / 8.11）",
        apply_result=result,
        apply_error_code=error_code,
    )


def assert_rollback_source_publishable(
    *,
    artifact_kind: ArtifactKind | str,
    artifact_state: ArtifactState | str,
) -> None:
    """rollback source 准入：quarantined / incoming / candidate / 未发布一律 fail closed。

    判据**复用** Task 13 的 :func:`~.adapters.base.assert_substrate_usable`
    （`role=published_representation`）而不是另写一套 kind/state 组合表 —— 两套表
    必然漂移，而这条路径上「incoming 冒充历史版本」是最贵的错。本函数只把它的三类
    异常翻译成本域可分辨的类型，让 router 能给出不同的用户文案。
    """
    from app.services.workpaper_sync.models import (
        QuarantinedIncomingError as _Quarantined,
    )

    try:
        assert_substrate_usable(
            role=SubstrateRole.published_representation,
            artifact_kind=artifact_kind,
            artifact_state=artifact_state,
        )
    except _Quarantined as exc:
        raise RollbackSourceQuarantinedError(
            f"rollback source 处于 quarantined，只允许 authorization-first download-only、"
            f"expire 与 retention/legal-hold：{exc}"
        ) from exc
    except SyncDomainError as exc:
        raise RollbackSourceNotPublishedError(
            f"rollback source 必须是 `kind=canonical, state=published` 的历史 "
            f"representation artifact —— incoming（durable 或 quarantined）与 upgrade "
            f"candidate 均不可作源（AC 8.7 / 6.18）：{exc}"
        ) from exc


def assert_frozen_contract_matches_bundle(
    *, contract: SyncContract, slot_digest: str, where: str
) -> None:
    """传入 contract 必须等于 frozen bundle 的 contract slot digest。

    预览与裁决折叠都按它进行，所以「拿 registry 当前 alias 渲染历史 operation」必须在
    入口就被拒（AC 6.2 / 7.10）。
    """
    if (contract.canonical_sha256 or "").strip() != (slot_digest or "").strip():
        raise FrozenContractDriftError(
            f"{where}: 传入 contract 的 canonical digest "
            f"{contract.canonical_sha256!r} 与 frozen bundle 的 contract slot "
            f"{slot_digest!r} 不一致 —— 历史 operation 只读 frozen bundle，"
            "不得按 registry 当前 alias 重组"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 冲突预览（AC 8.1 / 8.2 / Property 35）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ConflictPreviewItem:
    """一条可下钻的冲突（AC 8.1 的九个要素 + AC 8.5 的两个 fence 字段）。

    `value_type` 供前端选格式化口径：金额必须走平台 `displayPrefs.fmtAmount()`
    （千分符 + 2 位小数 + 默认「元」），而它只能从 **frozen contract** 推出来 ——
    冲突行里不存这一列，按 registry 当前 alias 推会漂移。
    """

    conflict_id: uuid.UUID
    stable_field_key: str
    business_label: str
    sheet_key: str | None
    table_key: str | None
    row_key: str
    json_pointer: str
    oo_location: str
    kind: ConflictKind
    field_source: FieldSource
    protection_policy: ProtectionPolicy
    suggested_action: SuggestedAction
    value_type: str
    base: Mapping[str, Any] | None
    current: Mapping[str, Any] | None
    incoming: Mapping[str, Any] | None
    #: AC 8.5 的两个乐观锁字段，逐条随冲突返回（客户端提交裁决时要原样带回）。
    client_edit_epoch: int
    incoming_sequence: int | None
    resolved: bool

    @property
    def is_protected(self) -> bool:
        return self.protection_policy.is_protected

    @property
    def adjudicable_by_value_choice(self) -> bool:
        """能否靠「选一侧 / 输入合并值」收敛（结构类冲突不能）。"""
        return self.kind is not ConflictKind.schema

    def as_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": str(self.conflict_id),
            "stable_field_key": self.stable_field_key,
            "business_label": self.business_label,
            "sheet_key": self.sheet_key,
            "table_key": self.table_key,
            "row_key": self.row_key,
            "json_pointer": self.json_pointer,
            "oo_location": self.oo_location,
            "kind": self.kind.value,
            "field_source": self.field_source.value,
            "protection_policy": self.protection_policy.value,
            "suggested_action": self.suggested_action.value,
            "value_type": self.value_type,
            "base": self.base,
            "current": self.current,
            "incoming": self.incoming,
            "client_edit_epoch": self.client_edit_epoch,
            "incoming_sequence": self.incoming_sequence,
            "resolved": self.resolved,
            "is_protected": self.is_protected,
            "adjudicable_by_value_choice": self.adjudicable_by_value_choice,
        }


@dataclass(frozen=True)
class ConflictPreviewGroup:
    """AC 8.2 的分组：sheet / table / row 三级，组内保持稳定序。"""

    sheet_key: str
    table_key: str
    row_key: str
    items: tuple[ConflictPreviewItem, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sheet_key": self.sheet_key,
            "table_key": self.table_key,
            "row_key": self.row_key,
            "items": [item.as_dict() for item in self.items],
        }


@dataclass(frozen=True)
class ConflictPreview:
    """一次冲突预览的完整响应。

    `requested_operation_id` 与 `canonical_operation_id` **同时**返回：requested 是
    duplicate 时前端仍按自己发出的 id 对账，而冲突挂在 canonical primary 上
    （AC 5.5 末段 / design §conflicts endpoint「响应保留 requested/canonical ids」）。
    """

    requested_operation_id: uuid.UUID
    canonical_operation_id: uuid.UUID
    followed_duplicate: bool
    canonical_application_id: uuid.UUID
    client_edit_epoch: int
    incoming_sequence: int
    room_id: uuid.UUID
    room_generation: int
    current_revision: int
    conflict_set_digest: str | None
    #: frozen identity —— 预览必须说得出「按哪份 bundle/authority model 渲染的」。
    definition_bundle_id: uuid.UUID
    definition_bundle_sha256: str
    authority_model: AuthorityModel
    authority_model_definition_sha256: str
    contract_id: str
    contract_semantic_version: str
    groups: tuple[ConflictPreviewGroup, ...]

    @property
    def conflict_count(self) -> int:
        return sum(len(group.items) for group in self.groups)

    @property
    def items(self) -> tuple[ConflictPreviewItem, ...]:
        return tuple(item for group in self.groups for item in group.items)

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_operation_id": str(self.requested_operation_id),
            "canonical_operation_id": str(self.canonical_operation_id),
            "followed_duplicate": self.followed_duplicate,
            "canonical_application_id": str(self.canonical_application_id),
            "client_edit_epoch": self.client_edit_epoch,
            "incoming_sequence": self.incoming_sequence,
            "room_id": str(self.room_id),
            "room_generation": self.room_generation,
            "current_revision": self.current_revision,
            "conflict_set_digest": self.conflict_set_digest,
            "definition_bundle_id": str(self.definition_bundle_id),
            "definition_bundle_sha256": self.definition_bundle_sha256,
            "authority_model": self.authority_model.value,
            "authority_model_definition_sha256": self.authority_model_definition_sha256,
            "contract_id": self.contract_id,
            "contract_semantic_version": self.contract_semantic_version,
            "conflict_count": self.conflict_count,
            "groups": [group.as_dict() for group in self.groups],
        }


@dataclass(frozen=True)
class ResolveOutcome:
    """一次成功裁决的结果（AC 8.6 的审计要素齐备）。"""

    decision: FenceDecision
    fence_reason: FenceReason
    normalized_effective_request_sequence: int
    requested_operation_id: uuid.UUID
    canonical_operation_id: uuid.UUID
    canonical_application_id: uuid.UUID
    resolutions_applied: int
    conflict_rows_marked: int
    revision_before: int
    revision_after: int | None
    apply: OoToHtmlOutcome
    actor_id: uuid.UUID
    resolved_at: datetime

    @property
    def http_status(self) -> int:
        return http_status_for(self.decision)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "fence_reason": self.fence_reason.value,
            "reject_code": RESOLVE_REJECT_HTTP_CODE[self.fence_reason],
            "http_status": self.http_status,
            "normalized_effective_request_sequence": (
                self.normalized_effective_request_sequence
            ),
            "requested_operation_id": str(self.requested_operation_id),
            "canonical_operation_id": str(self.canonical_operation_id),
            "canonical_application_id": str(self.canonical_application_id),
            "resolutions_applied": self.resolutions_applied,
            "conflict_rows_marked": self.conflict_rows_marked,
            "revision_before": self.revision_before,
            "revision_after": self.revision_after,
            "result": self.apply.result.value,
            "actor_id": str(self.actor_id),
            "resolved_at": self.resolved_at.isoformat(),
        }


@dataclass(frozen=True)
class RollbackOutcome:
    """一次 rollback 的结果。

    `revision_unchanged=True` 时**零写入**：业务 projection 与 current 等值，属纯表示层
    差异，AC 6.18/9.10 明令 content revision 保持不变（伪业务 revision 会污染 evidence
    与全部历史读取的定位）。
    """

    source_version_id: uuid.UUID
    source_revision: int
    source_representation_id: uuid.UUID
    source_artifact_sha256: str
    definition_bundle_id: uuid.UUID
    definition_bundle_sha256: str
    projection_sha256: str
    revision_before: int
    revision_after: int
    revision_unchanged: bool
    new_content_version_id: uuid.UUID | None
    new_representation_id: uuid.UUID | None
    new_artifact_sha256: str | None
    actor_id: uuid.UUID
    rolled_back_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_version_id": str(self.source_version_id),
            "source_revision": self.source_revision,
            "source_representation_id": str(self.source_representation_id),
            "source_artifact_sha256": self.source_artifact_sha256,
            "definition_bundle_id": str(self.definition_bundle_id),
            "definition_bundle_sha256": self.definition_bundle_sha256,
            "projection_sha256": self.projection_sha256,
            "revision_before": self.revision_before,
            "revision_after": self.revision_after,
            "revision_unchanged": self.revision_unchanged,
            "new_content_version_id": (
                None
                if self.new_content_version_id is None
                else str(self.new_content_version_id)
            ),
            "new_representation_id": (
                None
                if self.new_representation_id is None
                else str(self.new_representation_id)
            ),
            "new_artifact_sha256": self.new_artifact_sha256,
            "actor_id": str(self.actor_id),
            "rolled_back_at": self.rolled_back_at.isoformat(),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 4. 服务
# ═══════════════════════════════════════════════════════════════════════════


class ConflictResolutionService:
    """冲突预览 / resolve / retry / rollback 的唯一编排入口。

    依赖全部显式注入且没有一个是「可选的默认放行」：

    * `repo` —— Task 10 的仓储（唯一写入入口，不 commit）
    * `resolution` —— Task 12 的 canonical resolver（rollback 的历史定位）
    * `content` —— Task 15 的唯一 business commit 边界（rollback 走它）
    * `requests` —— Task 23 的授权→canonicalize 读路径
    * `coordinator` —— Task 26 的 OO→HTML 编排（resolve/retry 的执行体）
    """

    def __init__(
        self,
        *,
        repo: WorkpaperSyncRepository,
        resolution: CanonicalResolutionService,
        content: ContentMutationService,
        requests: RequestApplicationService,
        coordinator: OoToHtmlCoordinator,
    ) -> None:
        self._repo = repo
        self._session = repo.session
        self._resolution = resolution
        self._content = content
        self._requests = requests
        self._coordinator = coordinator

    # ─────────────────────────────────────────────────────────────────
    # 4.1 冲突预览
    # ─────────────────────────────────────────────────────────────────

    async def preview(
        self,
        *,
        operation_id: uuid.UUID,
        declared_project_id: uuid.UUID,
        declared_wp_id: uuid.UUID,
        declared_entry_id: str,
        contract: SyncContract,
        authorize: Any = None,
        include_superseded: bool = False,
    ) -> ConflictPreview:
        """AC 8.1 / 8.2 / Property 35：每条冲突双侧可追溯、三值与 kind 非空。

        读路径固定四步（与 retry/resolve 完全相同的一条），冲突永远从 **canonical
        primary** 读 —— requested 是合法 duplicate 时它自身没有 application，
        「要求 requested duplicate 先绑定 application」是 AC 5.5 明令禁止的形态。
        """
        canonical = await self._requests.read_operation(
            operation_id=operation_id,
            declared_project_id=declared_project_id,
            declared_wp_id=declared_wp_id,
            declared_entry_id=declared_entry_id,
            action="read_conflicts",
            authorize=authorize,
            require_application=True,
        )
        application_id = canonical.canonical_application_id
        assert application_id is not None  # require_application=True 已保证
        app = await self._load_application(application_id)
        bundle = await self._resolution.load_bundle_snapshot(app.definition_bundle_id)
        assert_frozen_contract_matches_bundle(
            contract=contract,
            slot_digest=bundle.slots[BundleSlot.contract].slot_digest,
            where=f"conflict preview of application {application_id}",
        )
        rows = await self._repo.load_conflicts(
            operation_id=canonical.canonical_operation.id,
            include_superseded=include_superseded,
        )
        index = ContractIndex(contract)
        groups: dict[tuple[str, str, str], list[ConflictPreviewItem]] = {}
        for row in rows:
            item = self._preview_item(row, index=index)
            key = (item.sheet_key or "", item.table_key or "", item.row_key or "")
            groups.setdefault(key, []).append(item)
        room = await self._load_room(app.room_id)
        return ConflictPreview(
            requested_operation_id=canonical.requested_operation.id,
            canonical_operation_id=canonical.canonical_operation.id,
            followed_duplicate=canonical.followed_duplicate,
            canonical_application_id=application_id,
            client_edit_epoch=int(app.client_edit_epoch),
            incoming_sequence=int(app.effective_request_sequence),
            room_id=app.room_id,
            room_generation=int(room.generation),
            current_revision=await self._current_revision(app.wp_id),
            conflict_set_digest=app.conflict_set_digest,
            definition_bundle_id=app.definition_bundle_id,
            definition_bundle_sha256=str(app.definition_bundle_sha256),
            authority_model=bundle.authority_model,
            authority_model_definition_sha256=str(
                app.authority_model_definition_sha256
            ),
            contract_id=contract.contract_id,
            contract_semantic_version=contract.semantic_version,
            groups=tuple(
                ConflictPreviewGroup(
                    sheet_key=key[0],
                    table_key=key[1],
                    row_key=key[2],
                    items=tuple(items),
                )
                for key, items in sorted(groups.items())
            ),
        )

    def _preview_item(
        self, row: WorkpaperSyncConflict, *, index: ContractIndex
    ) -> ConflictPreviewItem:
        """一行冲突 → 预览项。`value_type` 由 frozen contract 推出（AC 8.2 的金额口径）。"""
        locator = index.resolve(
            row.stable_field_key, declared_row_key=(row.row_key or None) or None
        )
        return ConflictPreviewItem(
            conflict_id=row.id,
            stable_field_key=row.stable_field_key,
            business_label=row.business_label,
            sheet_key=row.sheet_key,
            table_key=row.table_key,
            row_key=row.row_key or "",
            json_pointer=row.json_pointer,
            oo_location=row.oo_location,
            kind=ConflictKind(row.conflict_kind),
            field_source=FieldSource(row.field_source),
            protection_policy=ProtectionPolicy(row.protection_policy),
            suggested_action=SuggestedAction(row.suggested_action),
            value_type=locator.value_type.value,
            base=row.base_value,
            current=row.current_value,
            incoming=row.incoming_value,
            client_edit_epoch=int(row.client_edit_epoch),
            incoming_sequence=(
                None
                if row.effective_request_sequence is None
                else int(row.effective_request_sequence)
            ),
            resolved=row.resolved_at is not None,
        )

    # ─────────────────────────────────────────────────────────────────
    # 4.2 resolve：fence → 折叠裁决 → 发布
    # ─────────────────────────────────────────────────────────────────

    async def resolve(
        self,
        *,
        operation_id: uuid.UUID,
        declared_project_id: uuid.UUID,
        declared_wp_id: uuid.UUID,
        declared_entry_id: str,
        fence: ResolveFenceRequest,
        resolutions: Sequence[ResolutionChoice],
        adapter: WorkpaperSyncAdapter,
        contract: SyncContract,
        actor_id: uuid.UUID,
        authorize: Any = None,
        attempt: int = 2,
    ) -> ResolveOutcome:
        """AC 8.3~8.6 / Property 36：八项乐观锁 → 折叠裁决 → 唯一 commit 边界发布。

        步骤顺序即判据：

        1. requested id 的 authorization-first guard（**只**查 scope index）；
        2. requested 是 terminal duplicate ⇒ 备好 direct-primary invariant 输入，
           由 :func:`~.conflicts.evaluate_resolve_fence` 的第 0 步验证后再 canonicalize；
        3. 读服务端真值（application 冻结侧 + room durable 侧）；
        4. `evaluate_resolve_fence` 判定（顺序在 Task 14 域内，本模块不抄）；
        5. rejected/superseded ⇒ 抛可分辨异常，**零副作用**；
           rebase ⇒ 用**原 frozen bundle** 重跑一次 merge 重建 conflict，再抛 409；
        6. proceed/fold ⇒ 把裁决交给 Task 26 的 coordinator 折叠并发布；
        7. **落地自证**（:func:`assert_resolve_apply_landed`）—— coordinator 在 durable
           之后不抛异常（AC 5.7/5.8），所以「成功」必须自己查 `outcome.result`：
           复核锁定/归档/项目不可见只活在 `AuthorizationProbe` 后面，第 3 步读的
           room fence 看不到它们；
        8. 落地后才写 AC 8.6 的裁决轨迹（选择结果 + 落地值 + actor + 时间）。
        """
        if not resolutions:
            raise ResolveWithoutConflictError(
                "resolve 请求必须携带至少一条裁决 —— 零裁决的调用属普通 apply/retry，"
                "混用会让「裁决成功」的审计事实落在一次没有任何人工选择的应用上（AC 8.3）"
            )
        ref = await self._requests.authorize_operation_scope(
            operation_id=operation_id,
            declared_project_id=declared_project_id,
            declared_wp_id=declared_wp_id,
            declared_entry_id=declared_entry_id,
            action="resolve_conflicts",
            authorize=authorize,
        )
        canonical = await self._requests.canonicalize_authorized(
            ref, require_application=True
        )
        application_id = canonical.canonical_application_id
        assert application_id is not None  # require_application=True 已保证
        app = await self._load_application(application_id)
        room = await self._repo.lock_room(app.room_id)
        bundle = await self._resolution.load_bundle_snapshot(app.definition_bundle_id)
        assert_frozen_contract_matches_bundle(
            contract=contract,
            slot_digest=bundle.slots[BundleSlot.contract].slot_digest,
            where=f"resolve of application {application_id}",
        )
        current_revision = await self._current_revision(app.wp_id)
        evaluation = evaluate_resolve_fence(
            request=fence,
            application=await self._frozen_fence(app),
            room=RoomDurableFence(
                generation=int(room.generation),
                write_fence_epoch=int(room.write_fence_epoch),
                initiator_permission_epoch=await self._initiator_permission_epoch(app),
                state_is_refresh_required=(
                    RoomState(room.state) is RoomState.refresh_required
                ),
                latest_durable_application_id=room.latest_durable_application_id,
                latest_durable_sequence=int(room.latest_durable_sequence or 0),
                current_revision=current_revision,
                conflict_set_digest=str(app.conflict_set_digest or ""),
            ),
            duplicate_link=await self._duplicate_link(canonical, application_id),
        )
        if evaluation.decision is FenceDecision.rejected:
            raise ResolveFenceRejectedError(
                f"resolve fence 拒绝（{RESOLVE_REJECT_HTTP_CODE[evaluation.reason]}）："
                f"{evaluation.message}",
                evaluation=evaluation,
            )
        if evaluation.decision is FenceDecision.superseded:
            raise ResolveSupersededError(
                f"冲突集已被 supersede：{evaluation.message}",
                evaluation=evaluation,
                superseding_application_id=room.latest_durable_application_id,
            )
        if evaluation.decision is FenceDecision.rebase:
            rebased = await self._coordinator.apply_durable_incoming(
                operation_id=operation_id,
                declared_project_id=declared_project_id,
                declared_wp_id=declared_wp_id,
                declared_entry_id=declared_entry_id,
                adapter=adapter,
                contract=contract,
                authorize=authorize,
                actor_id=actor_id,
                attempt=attempt,
            )
            # rebase 也要自证：落地阶段的失败终态必须原样透出（见
            # :data:`REBASE_ADMISSIBLE_RESULTS`），否则「授权已失效/归档」会被包成
            # 409 rebase-required，客户端一遍遍重取冲突集而永远不知道真正的原因。
            assert_resolve_apply_landed(
                result=rebased.result.value,
                error_code=rebased.error_code,
                error_stage=rebased.error_stage,
                where=f"rebase of application {application_id}",
                landed=REBASE_ADMISSIBLE_RESULTS,
            )
            raise ResolveRebaseRequiredError(
                f"current revision 已推进，冲突集已按原 frozen bundle 重建："
                f"{evaluation.message}",
                evaluation=evaluation,
                rebased_conflict_set_digest=rebased.conflict_set_digest,
                rebased_conflict_count=rebased.conflict_count,
                rebased_attempt=attempt,
            )

        revision_before = current_revision
        outcome = await self._coordinator.apply_durable_incoming(
            operation_id=operation_id,
            declared_project_id=declared_project_id,
            declared_wp_id=declared_wp_id,
            declared_entry_id=declared_entry_id,
            adapter=adapter,
            contract=contract,
            resolutions=tuple(resolutions),
            authorize=authorize,
            actor_id=actor_id,
            attempt=attempt,
        )
        # 🔴 顺序不可交换：先自证「真的落地了」，再写裁决轨迹。
        # coordinator 在 durable 之后不抛异常（AC 5.7/5.8），所以「成功」必须自己查。
        assert_resolve_apply_landed(
            result=outcome.result.value,
            error_code=outcome.error_code,
            error_stage=outcome.error_stage,
            where=f"resolve of application {application_id}",
        )
        marked = await self._record_resolution_trail(
            operation_id=outcome.canonical_operation_id,
            outcome=outcome,
            resolutions=resolutions,
            actor_id=actor_id,
        )
        return ResolveOutcome(
            decision=evaluation.decision,
            fence_reason=evaluation.reason,
            normalized_effective_request_sequence=(
                evaluation.normalized_effective_request_sequence
            ),
            requested_operation_id=outcome.requested_operation_id,
            canonical_operation_id=outcome.canonical_operation_id,
            canonical_application_id=application_id,
            resolutions_applied=len(resolutions),
            conflict_rows_marked=marked,
            revision_before=revision_before,
            revision_after=outcome.result_revision,
            apply=outcome,
            actor_id=actor_id,
            resolved_at=_now(),
        )

    async def _record_resolution_trail(
        self,
        *,
        operation_id: uuid.UUID,
        outcome: OoToHtmlOutcome,
        resolutions: Sequence[ResolutionChoice],
        actor_id: uuid.UUID,
    ) -> int:
        """AC 8.6：把「谁在什么时候选了什么、落地值是什么」写回冲突行。

        落地值用 Task 14 的 :func:`~.conflicts.resolved_value_for` 重算 —— 不在这里
        抄一份选择求值逻辑（受保护字段只许 keep_current、结构冲突不可裁决等四条禁令都
        在那个函数里）。

        🔴 已知窗口：本轨迹与内容 commit 不在同一事务（唯一 commit 边界在 Task 15，
        它的同事务挂点 `after_pointers` 属 Task 26 的 fence hook）。若进程在两者之间
        崩溃，会留下「application=applied 而 conflict.resolved_at IS NULL」这一**可检测
        且可修复**的不一致（application 上有 `merged_projection_sha256` 可复算）。
        刻意不用 `except` 吞掉失败：那才会让轨迹缺失变成静默。
        """
        merge = outcome.merge
        if merge is None:  # pragma: no cover - resolve 必经 merge
            raise ConflictResolutionError(
                "resolve 的 apply 结果没有 MergeOutcome —— 无法核对裁决与冲突的对应关系"
            )
        by_key = assert_all_conflicts_resolved(merge.conflicts, resolutions)
        records = merge.conflicts.by_key()
        payloads = [
            {
                "stable_field_key": key[0],
                "row_key": key[1],
                "oo_location": key[2],
                "resolution": choice.to_jsonb(),
                "resolved_value": resolved_value_for(records[key], choice).to_jsonb(),
            }
            for key, choice in by_key.items()
        ]
        marked = await self._repo.mark_conflicts_resolved(
            operation_id=operation_id,
            resolutions=payloads,
            actor_id=actor_id,
        )
        await self._session.commit()
        return marked

    # ─────────────────────────────────────────────────────────────────
    # 4.3 recovery-aware retry（AC 8.9 / Property 38）
    # ─────────────────────────────────────────────────────────────────

    async def retry(
        self,
        *,
        operation_id: uuid.UUID | None,
        declared_project_id: uuid.UUID,
        declared_wp_id: uuid.UUID,
        declared_entry_id: str,
        adapter: WorkpaperSyncAdapter,
        contract: SyncContract,
        actor_id: uuid.UUID | None = None,
        authorize: Any = None,
        attempt: int = 2,
    ) -> OoToHtmlOutcome:
        """从 `application.incoming_artifact_id` 重试 extract/merge —— 零 forcesave。

        本方法**没有**自己的执行体：它把 `attempt>1` 交给 Task 26 的同一个
        :meth:`~.oo_to_html.OoToHtmlCoordinator.apply_durable_incoming`。这不是偷懒，
        而是 Property 38 的形态要求 ——「retry 专用捷径」必然绕过某道门（授权、
        substrate 三层准入、frozen bundle、同一 append-only timeline）。

        唯一属于本层的判据是入口的 nullable-operation 闸：unmatched/ambiguous recovery
        case 在 claim 之前三实体全空，必须先走 authorization-first claim。
        """
        confirmed = assert_retry_operation_eligible(operation_id)
        return await self._coordinator.apply_durable_incoming(
            operation_id=confirmed,
            declared_project_id=declared_project_id,
            declared_wp_id=declared_wp_id,
            declared_entry_id=declared_entry_id,
            adapter=adapter,
            contract=contract,
            authorize=authorize,
            actor_id=actor_id,
            attempt=attempt,
        )

    # ─────────────────────────────────────────────────────────────────
    # 4.4 rollback（AC 8.7 / 8.8 / Property 37 / 67）
    # ─────────────────────────────────────────────────────────────────

    async def rollback(
        self,
        *,
        version_id: uuid.UUID,
        declared_project_id: uuid.UUID,
        declared_wp_id: uuid.UUID,
        declared_entry_id: str,
        expected_current_revision: int,
        adapter: WorkpaperSyncAdapter,
        contract: SyncContract,
        actor_id: uuid.UUID,
        authorize: Any = None,
    ) -> RollbackOutcome:
        """以 immutable opaque UUID 定位历史内容，**创建新版本**指向它。

        1. authorization-first：只查 `(resource_kind=content_version, resource_id=uuid)`
           的 scope index，与显式 route scope 交叉比对；缺失/跨 scope/不存在 **同一 404**；
        2. 业务行二次核对（scope index 与 content version 行必须同 wp）；
        3. 该 version 在本 entry 的 published representation → canonical resolver
           （`intent=rollback` 强制 frozen identity，candidate 在 resolver 内即被拒）；
        4. artifact 准入：`kind=canonical, state=published`，incoming/quarantined/
           candidate 全部 fail closed；
        5. 反读目标 projection（AC 8.8「先 stage 并反读目标 artifact/projection」）；
        6. projection 与 current 等值 ⇒ **零写入**、revision 不变（AC 6.18 / 9.10）；
        7. 否则经唯一 commit 边界创建新 content version + published representation。
        """
        scope = await self._repo.resolve_scope(
            resource_kind=ScopeResourceKind.content_version,
            resource_id=str(version_id),
        )
        if scope is None or (
            scope.project_id != declared_project_id
            or scope.wp_id != declared_wp_id
        ):
            raise ContentVersionNotFoundError(
                f"content version {version_id} 不可见 —— 不存在、已 retire 或与显式声明的 "
                "project/wp scope 不符（三者共用同一 404 语义，不得据此推断该 id 是否存在）",
                refused_at=REFUSED_AT_SCOPE_INDEX,
            )
        if authorize is not None:
            verdict = authorize(scope)
            if hasattr(verdict, "__await__"):
                verdict = await verdict
            if not verdict:
                raise ConflictResolutionError(
                    f"content version {version_id} 的 scope 可见，但当前权限不允许 "
                    "rollback（403，与 404 分型）"
                )
        version = (
            await self._session.execute(
                sa.select(WorkpaperContentVersion).where(
                    WorkpaperContentVersion.id == version_id,
                    WorkpaperContentVersion.wp_id == declared_wp_id,
                )
            )
        ).scalar_one_or_none()
        if version is None:
            raise ContentVersionNotFoundError(
                f"content version {version_id} 在 wp={declared_wp_id} 下不存在 —— "
                "numeric revision 不得作为 scope lookup key，两个 wp 的 revision 1 "
                "必须由不同 UUID 无碰撞定位",
                refused_at=REFUSED_AT_BUSINESS_ROW,
            )
        source_rep = await self._published_representation_of(
            version_id=version.id, wp_id=declared_wp_id, entry_id=declared_entry_id
        )
        # 🔴 准入判据必须排在 canonical resolver **之前**。resolver 也会拒绝未发布
        # artifact（`ArtifactNotPublishedError`），但那是通用路径错误：放在它之后时
        # 本判据在所有可达输入上都被遮蔽 ⇒ provably dead（Task 27 真库实测判到），
        # 而且用户看到的原因会变成「artifact 未发布」而不是「这个版本不能作回滚源」。
        artifact_kind, artifact_state = await self._artifact_kind_state(
            source_rep.artifact_id
        )
        assert_rollback_source_publishable(
            artifact_kind=artifact_kind, artifact_state=artifact_state
        )
        resolved = await self._resolution.resolve(
            intent=ROLLBACK_INTENT,
            project_id=declared_project_id,
            wp_id=declared_wp_id,
            entry_id=declared_entry_id,
            representation_id=source_rep.id,
            expected_content_version_id=version.id,
        )
        assert_frozen_contract_matches_bundle(
            contract=contract,
            slot_digest=resolved.bundle.slots[BundleSlot.contract].slot_digest,
            where=f"rollback source representation {source_rep.id}",
        )
        target: Projection = adapter.extract(
            artifact=resolved.artifact_path, contract=contract
        )
        target_digest = projection_canonical_digest(target)
        current_revision = await self._current_revision(declared_wp_id)
        # 🔴 刻意**不**再写 `if version.revision > current_revision`：content version 与
        # `working_paper.content_revision` 在同一事务里推进，「源 revision 高于 current」
        # 在任何可达状态下都不成立 ⇒ 那是一条 provably dead 的防御分支，短路它在变异
        # 检验里判 GREEN（本任务首轮实测如此）。真正有牙的是下面这条乐观锁。
        if expected_current_revision != current_revision:
            raise RollbackRevisionRewindError(
                f"expected_current_revision={expected_current_revision} 与实际 "
                f"{current_revision} 不符 —— numeric revision 只作乐观锁，"
                "失配时必须重读后再确认，不得按旧值创建新版本"
            )
        current_projection_sha256 = await self._current_projection_sha256(declared_wp_id)
        if current_projection_sha256 == target_digest:
            # AC 6.18 / 9.10 / Property 67：业务 projection 未变化 ⇒ revision 不变、零写入。
            return RollbackOutcome(
                source_version_id=version.id,
                source_revision=int(version.revision),
                source_representation_id=source_rep.id,
                source_artifact_sha256=str(resolved.artifact_sha256),
                definition_bundle_id=resolved.bundle.bundle_id,
                definition_bundle_sha256=resolved.bundle.bundle_sha256,
                projection_sha256=target_digest,
                revision_before=current_revision,
                revision_after=current_revision,
                revision_unchanged=True,
                new_content_version_id=None,
                new_representation_id=None,
                new_artifact_sha256=None,
                actor_id=actor_id,
                rolled_back_at=_now(),
            )
        plan = ContentCommitPlan(
            project_id=declared_project_id,
            wp_id=declared_wp_id,
            entry_id=declared_entry_id,
            source=ROLLBACK,
            expected_revision=current_revision,
            bundle=resolved.bundle,
            adapter_id=resolved.adapter_id,
            adapter_build_digest=resolved.adapter_build_digest,
            document_type=resolved.document_type,
            substrate_path=resolved.artifact_path,
            substrate_role=SubstrateRole.published_representation,
            substrate_kind=artifact_kind,
            substrate_state=artifact_state,
            actor_id=actor_id,
            parent_version_id=await self._current_version_id(declared_wp_id),
            contract=contract,
            reason="rollback",
        )
        receipt = await self._content.commit(
            plan=plan,
            mutation=BusinessMutation(projection=target),
            adapter=adapter,
        )
        if int(receipt.revision) <= current_revision:  # pragma: no cover - CAS 已保证
            raise RollbackRevisionRewindError(
                f"rollback 后 revision {receipt.revision} 未高于回滚前 {current_revision}"
            )
        return RollbackOutcome(
            source_version_id=version.id,
            source_revision=int(version.revision),
            source_representation_id=source_rep.id,
            source_artifact_sha256=str(resolved.artifact_sha256),
            definition_bundle_id=resolved.bundle.bundle_id,
            definition_bundle_sha256=resolved.bundle.bundle_sha256,
            projection_sha256=target_digest,
            revision_before=current_revision,
            revision_after=int(receipt.revision),
            revision_unchanged=False,
            new_content_version_id=receipt.content_version_id,
            new_representation_id=receipt.representation_id,
            new_artifact_sha256=receipt.artifact_sha256,
            actor_id=actor_id,
            rolled_back_at=_now(),
        )

    # ─────────────────────────────────────────────────────────────────
    # 4.5 只读辅助
    # ─────────────────────────────────────────────────────────────────

    async def _frozen_fence(
        self, app: WorkpaperContentApplication
    ) -> FrozenApplicationFence:
        """application 冻结侧的 fence 真值。

        `write_fence_epoch` / `initiator_permission_epoch` 取的是 **origin request 冻结
        的那一份**（不是 room 现值）：拿 room 现值跟 room 现值比是重言式，无论谁被撤销
        都永远相等 ⇒ 「fence 变化即拒绝」这条判据 provably dead
        （Task 26 的 `_observed_contributor_digest` 吃过同一个教训）。
        """
        row = (
            await self._session.execute(
                sa.select(
                    WorkpaperForcesaveRequest.write_fence_epoch,
                    WorkpaperForcesaveRequest.initiator_permission_epoch,
                ).where(WorkpaperForcesaveRequest.id == app.origin_request_id)
            )
        ).one()
        return FrozenApplicationFence(
            canonical_application_id=app.id,
            effective_request_sequence=int(app.effective_request_sequence),
            write_fence_epoch=int(row[0]),
            initiator_permission_epoch=int(row[1]),
            client_edit_epoch=int(app.client_edit_epoch),
        )

    async def _initiator_permission_epoch(
        self, app: WorkpaperContentApplication
    ) -> int:
        """发起人**当下**的 permission epoch（fence 的观测侧）。

        participant 行不存在或已撤销时返回 `-1`：它与任何冻结值都不相等 ⇒ fence 拒绝。
        这是**正确**的 fail-closed —— 「查不到发起人」绝不能等于「授权仍有效」。
        """
        row = (
            await self._session.execute(
                sa.select(WorkpaperOoParticipant.permission_epoch)
                .join(
                    WorkpaperForcesaveRequest,
                    WorkpaperForcesaveRequest.initiated_by_participant_id
                    == WorkpaperOoParticipant.id,
                )
                .where(
                    WorkpaperForcesaveRequest.id == app.origin_request_id,
                    WorkpaperOoParticipant.revoked_at.is_(None),
                )
            )
        ).one_or_none()
        return -1 if row is None else int(row[0])

    async def _duplicate_link(
        self, canonical: Any, application_id: uuid.UUID
    ) -> RequestedOperationLink | None:
        """requested 是 terminal duplicate 时给出 `(requested, primary)` 的 scope 对。

        只在**这种**情况下给：`evaluate_resolve_fence` 的第 0 步会拒绝在非 duplicate
        情形下传入它（防「对 primary 也跑一遍 direct-primary 校验」这种误用）。
        """
        requested = canonical.requested_operation
        shape = classify_operation_shape(
            application_id=requested.application_id,
            duplicate_of_operation_id=requested.duplicate_of_operation_id,
            state=requested.state,
        )
        if shape is not OperationShape.duplicate:
            return None
        primary = canonical.canonical_operation
        return RequestedOperationLink(
            requested=_scope_of(requested),
            primary=_scope_of(primary),
        )

    async def _load_application(
        self, application_id: uuid.UUID
    ) -> WorkpaperContentApplication:
        return (
            await self._session.execute(
                sa.select(WorkpaperContentApplication).where(
                    WorkpaperContentApplication.id == application_id
                )
            )
        ).scalar_one()

    async def _load_room(self, room_id: uuid.UUID) -> WorkpaperOoRoom:
        return (
            await self._session.execute(
                sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == room_id)
            )
        ).scalar_one()

    async def _published_representation_of(
        self, *, version_id: uuid.UUID, wp_id: uuid.UUID, entry_id: str
    ) -> WorkpaperContentRepresentation:
        """该 content version 在本 entry 的最新 representation generation。

        找不到时抛 :class:`RollbackSourceNotPublishedError` 而不是 404：scope 已经过了，
        「这个版本在这个 entry 上没有 representation」不是存在性泄露，而是一个可诊断的
        业务事实（例如该 entry 是后来才接上 OO 的）。
        """
        rep = (
            await self._session.execute(
                sa.select(WorkpaperContentRepresentation)
                .where(
                    WorkpaperContentRepresentation.content_version_id == version_id,
                    WorkpaperContentRepresentation.wp_id == wp_id,
                    WorkpaperContentRepresentation.entry_id == entry_id,
                )
                .order_by(WorkpaperContentRepresentation.generation.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if rep is None:
            raise RollbackSourceNotPublishedError(
                f"content version {version_id} 在 entry {entry_id!r} 上没有 published "
                "representation —— candidate 不可作 rollback source（Requirement 6.18）"
            )
        return rep

    async def _artifact_kind_state(
        self, artifact_id: uuid.UUID
    ) -> tuple[ArtifactKind, ArtifactState]:
        row = (
            await self._session.execute(
                sa.text(
                    "SELECT kind, state FROM working_paper_artifact WHERE id = :aid"
                ),
                {"aid": artifact_id},
            )
        ).one()
        return ArtifactKind(str(row[0])), ArtifactState(str(row[1]))

    async def _current_revision(self, wp_id: uuid.UUID) -> int:
        return int(
            (
                await self._session.execute(
                    sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
                    {"wp": wp_id},
                )
            ).scalar_one()
        )

    async def _current_version_id(self, wp_id: uuid.UUID) -> uuid.UUID | None:
        return (
            await self._session.execute(
                sa.text(
                    "SELECT current_content_version_id FROM working_paper WHERE id = :wp"
                ),
                {"wp": wp_id},
            )
        ).scalar_one_or_none()

    async def _current_projection_sha256(self, wp_id: uuid.UUID) -> str | None:
        """current content version 的业务 projection digest（等值判据的另一侧）。"""
        return (
            await self._session.execute(
                sa.text(
                    "SELECT v.projection_sha256 FROM working_paper_content_version v "
                    "JOIN working_paper w ON w.current_content_version_id = v.id "
                    "WHERE w.id = :wp"
                ),
                {"wp": wp_id},
            )
        ).scalar_one_or_none()


def _scope_of(operation: Any) -> OperationScope:
    """ORM operation 行 → Task 10 的 :class:`~.models.OperationScope` 值对象。

    `room_id` 与 `authority_model_definition_sha256` 必须原样带上：
    :func:`~.models.assert_direct_primary` 的跨 scope / 跨 bundle 两条禁令按它们判定，
    漏传（或塞默认值）会让「duplicate 指向另一个 room / 另一份 authority model」通过。
    """
    return OperationScope(
        operation_id=operation.id,
        project_id=operation.project_id,
        wp_id=operation.wp_id,
        entry_id=str(operation.entry_id),
        room_id=operation.room_id,
        definition_bundle_id=operation.definition_bundle_id,
        authority_model_definition_sha256=str(
            operation.authority_model_definition_sha256
        ),
        application_id=operation.application_id,
        duplicate_of_operation_id=operation.duplicate_of_operation_id,
        state=OperationState(str(operation.state)),
    )
