# -*- coding: utf-8 -*-
"""HTML → OO materialize coordinator 与**唯一** `EditorLaunchDescriptor`。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 25
Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 6.18
Properties: P8（flush 失败阻断 OO）/ P9（临时校验 + 原子发布）/
P10（单次业务 commit 与 representation 幂等）/ P11（唯一 descriptor + ready 后服务端确认）/
P67（upgrader 先 candidate、approved bundle 后 finalize）

═══ 一、这个模块**不**做什么（复用而非重写）═══

Task 25 是**编排**，不是新引擎。每一步都委派已落地的唯一实现：

| 关注点                          | 唯一实现                                              |
|---------------------------------|-------------------------------------------------------|
| 业务内容提交（单事务、单 revision）| Task 15 `ContentMutationService.commit`               |
| canonical artifact / bundle 解析 | Task 12 `CanonicalResolutionService.resolve`          |
| bundle typed slot 形态           | Task 15 `assert_bundle_snapshot_finalizable`          |
| room / lease / descriptor 确认    | Task 21 `RoomService`                                 |
| candidate → finalize            | Task 15 `RepresentationService.finalize_candidate`    |
| adapter 契约与 capability        | Task 13 `WorkpaperSyncAdapterRegistry`                |

本模块自己只持有四件事：**pending mutation token 的签名与逐项校验**、
**preflight 拒绝分类（422/403/409）**、**operation 终态记账**、
**descriptor 字段完整性**。

═══ 二、为什么 operation 必须在业务 commit **之前**单独落库 ═══

Requirement 3.8：「HTML→OO 任一失败 SHALL 产生终态明确的 operation 与 transition
events，不得用 warning 后继续打开旧文件」。而 Task 15 的 `commit()` 在任何异常上
`session.rollback()` —— 如果 operation 与业务内容同事务创建，失败时它会一起消失，
用户就只看到一个 5xx，没有可查的终态。

因此顺序固定为**三段事务**（与 Task 23 的 request-shell 同形）：

1. `_open_operation()` —— 冻结 approved bundle/authority model identity，落
   `direction=html_to_oo, state=created` 的 operation + scope row + `created` event，
   **提交**。此后无论发生什么，用户都能查到这次尝试。
2. `ContentMutationService.commit()` —— **唯一**业务事务：projection + 兼容
   representation staging/roundtrip/publish + revision CAS + pointer + outbox。
3. `_settle_operation()` —— 终态记账（`applied` / `error` / `rejected`）+ event，
   room/participant 创建也在这一段。

第 1 段之所以能安全地先提交：operation **不是**业务内容。它 `application_id=NULL`、
不动 `content_revision`、不切 pointer，纯粹是审计与轮询容器（Property 18/64 已锁死
「operation 不承担 application identity」）。

🔴 反过来说，preflight 失败（bundle 未 approved / 缺 per-entry contract /
representation 仍是 candidate）**不可能**有 operation ——
`working_paper_sync_operation.definition_bundle_id` 是 NOT NULL，而这些失败的定义就是
「没有一个合法 bundle 可冻结」。它们是 Requirement 3.3 的 422：零 operation、零 room、
零 descriptor。本模块把这条边界写成显式的 :class:`MaterializePreflightError` 家族，
而不是含糊地宣称「所有失败都有 operation」（那句话在这一类失败上做不到，写了就是假绿）。

═══ 三、authorization-before-idempotency：顺序由**参数类型**强制 ═══

Task 25 正文：「任何重放先经过 authorization-before-idempotency guard；仅当前
project/workflow/lease/generation/fence/bundle 仍有效时成功重放才返回同
operation/content version/representation，撤权后不得泄露 cached descriptor」。

判据不能是「我在代码里先写了授权」—— 那是可读性约定，改个顺序没人打红。这里沿用
Task 23 `AuthorizedOperationRef` 的做法：:meth:`MaterializeCoordinator.materialize`
**只**接受 :class:`AuthorizedMaterializeRequest`，而后者只能由
:meth:`MaterializeCoordinator.authorize` 产出，且带 `stages` 阶段链。缺阶段即拒绝。
于是「先查 idempotency cache 再授权」在**构造上**不可表达。

授权阶段只读 `working_paper_sync_scope_index`（非敏感归属），
:func:`assert_authorization_first_shape` 用 AST 复核这一点 —— 与 Task 23 的
`assert_authorization_first_source_shape` 同一套判据形态。

═══ 四、Property 8 的两个计数是**可观测量**，不是叙述 ═══

「flush 抛错或未返回 revision 时 materialize API 调用次数为 0、编辑器挂载次数为 0」。

后端侧的对应事实：

* **materialize 调用数为 0** —— 由前端 bridge（Task 32）保证；本模块提供的是它的
  必要条件：没有合法 pending token 时 :meth:`materialize` 在**任何**写入之前抛
  :class:`PendingTokenRequiredError`（token 为空/签名不符/scope 不符/过期/digest 不符/
  revision 不符，五类各一个异常类型）。
* **挂载数为 0** —— :class:`MaterializeOutcome.descriptor` 为 `None` 时前端没有任何
  可挂载对象；而 :class:`EditorLaunchDescriptor` 的 `__post_init__` 拒绝任何缺字段的
  构造，所以「半个 descriptor」也不可能被挂上去。

守卫另外直接数库里的 `working_paper_oo_room` 行数 —— 那是不受本模块自述影响的判据。

═══ 五、Requirement 3.6 的幂等复用比「同 token 重放」更宽 ═══

原文：「WHEN business projection、immutable definition bundle 与 canonical substrate
identity 均相同 THEN materialize SHALL 幂等复用现有 content version/representation/
room，不产生重复 content revision 或 representation」。

所以有**两条**幂等路径，判据不同、必须各自可 falsify：

1. **token 重放** —— 同一个 pending mutation 被消费两次。判据在 Task 15 的
   `_replay_if_committed`（`state=committed` ⇒ 返回既有 version/operation）。
2. **不同 token、相同业务身份** —— 用户 flush 了两次但内容一字未改。判据是
   :meth:`_find_business_identity_reuse`：按 `(projection digest, bundle digest,
   substrate digest)` 三元组找既有 content version + representation。命中即**不进入**
   `commit()`，于是 revision 一次都不动。

第 2 条的 projection digest 必须与 Task 15 落盘用的**完全同一套** canonicalization，
否则永远命中不了（而「永远命中不了」在只测第 1 条的守卫下是全绿的）。因此这里直接
复用 `content_mutation._projection_payload`，并有一条守卫实测
「coordinator 预算的 digest == commit 后 receipt.projection_sha256」。

═══ 六、definitions-only 升级不经本模块的业务路径 ═══

Requirement 3.6 后半 / Requirement 6.18 / Property 67：只有隐形载体升级时，必须走
`template → instrumentation → contract → bundle → representation`，产生**新
representation generation** 而 `content_revision` **不变**。

:meth:`MaterializeCoordinator.finalize_definition_upgrade` 是本模块对这条路径的**唯一**
出口，它做三件事：委派 `RepresentationService.finalize_candidate`、断言
`revision_unchanged`、把结果换成新 descriptor。它拿不到业务 commit 能力
（`RepresentationService` 构造时被 `RevisionLockedRepository` 包住），所以「纯定义升级
递增 business revision」在构造上不可能。
"""

from __future__ import annotations

import ast
import base64
import hashlib
import hmac
import inspect
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Final, Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import (
    WorkpaperArtifact,
    WorkpaperContentRepresentation,
    WorkpaperContentVersion,
    WorkpaperOoParticipant,
    WorkpaperOoRoom,
    WorkpaperPendingMutation,
    WorkpaperSyncOperation,
)
from app.services.workpaper_sync.adapters.base import (
    Projection,
    SubstrateRole,
    assert_no_mutation_surface,
    assert_substrate_usable,
)
from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
from app.services.workpaper_sync.content_mutation import (
    HTML,
    BusinessMutation,
    ContentCommitPlan,
    ContentCommitReceipt,
    ContentMutationService,
    RevisionLockedRepository,
    _projection_payload,  # 单一 canonicalization：见模块文档 §五
)
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.entry_profile import Capability
from app.services.workpaper_sync.models import (
    ActorType,
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    BundleIntegrityError,
    OperationDirection,
    OperationState,
    PendingMutationState,
    RoomState,
    ScopeResourceKind,
    SyncDomainError,
    assert_transition,
    is_digest,
)
from app.services.workpaper_sync.repository import WorkpaperSyncRepository
from app.services.workpaper_sync.representations import (
    RepresentationBundleError,
    RepresentationFinalizeOutcome,
    RepresentationService,
    RepresentationSlotError,
    assert_bundle_snapshot_finalizable,
)
from app.services.workpaper_sync.resolution import (
    CandidateNotFinalizableError,
    CanonicalResolution,
    CanonicalResolutionService,
    DefinitionBundleSnapshot,
    EntryPointerMissingError,
    ResolutionIntent,
)
from app.services.workpaper_sync.rooms import (
    BundleAliasDriftError,
    FrozenBundleIdentity,
    RepresentationNotPublishedError,
    RoomScope,
    RoomService,
)

__all__ = [
    # 异常
    "MaterializeCoordinatorError",
    "PendingTokenRequiredError",
    "PendingTokenSignatureError",
    "PendingTokenScopeError",
    "PendingTokenExpiredError",
    "PendingTokenPayloadError",
    "PendingTokenRevisionError",
    "PendingTokenStateError",
    "IdempotencyKeyMismatchError",
    "MaterializePreflightError",
    "EntryNotMaterializableError",
    "PerEntryContractMissingError",
    "BundleNotApprovedError",
    "RepresentationStillCandidateError",
    "SubstrateNotPublishedError",
    "MaterializeAuthorizationError",
    "MaterializeScopeNotVisibleError",
    "DescriptorFieldMissingError",
    "DescriptorStaleIdentityError",
    "DescriptorSubstrateStaleError",
    "DefinitionUpgradeRevisionError",
    "FlushRevisionDriftError",
    "SingleCommitAccountingError",
    "RevisionTargetAccountingError",
    "RevisionDeltaAccountingError",
    "assert_flush_revision_neutral",
    "assert_single_business_commit",
    "assert_revision_target",
    "assert_revision_delta",
    # 值对象
    "MaterializeStage",
    "PendingMutationTokenPayload",
    "PendingMutationReceipt",
    "MaterializeRequest",
    "AuthorizedMaterializeRequest",
    "EditorLaunchDescriptor",
    "MaterializeOutcome",
    "DescriptorConfirmation",
    "MaterializePreflight",
    # 服务与判据
    "MaterializeCoordinator",
    "PendingMutationTokenCodec",
    "DESCRIPTOR_REQUIRED_FIELDS",
    "MATERIALIZE_REJECTION_STATUS",
    "STALE_ON_REPLAY_MARKER",
    "STALE_ON_ROOM_OPEN_MARKER",
    "assert_authorization_first_shape",
    "assert_descriptor_mountable",
    "classify_materialize_rejection",
    "build_materialize_coordinator",
]


def _now() -> datetime:
    """服务端时钟（aware）。timestamptz 一律在 Python 侧构造 datetime。"""
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 0. 异常 —— 每条拒绝一个类型、一个 error_code
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 本 spec 已为「两条拒绝共用一个 error_code / 共用继承关系」付过三次代价：
#    第一条分支会变成**永久不可达**，它的定向变异也就永久 GREEN。因此下面每一个
#    子类都是 `MaterializeCoordinatorError` 的**直接**子类（除显式标注的两处分组
#    基类），且 `error_code` 两两不同 —— `test_refusals_are_pairwise_disjoint`
#    逐对实测这一点。


class MaterializeCoordinatorError(SyncDomainError):
    error_code = "materialize_failed"


# ── pending mutation token：五类拒绝（Property 10 逐条点名）───────────────


class PendingTokenRequiredError(MaterializeCoordinatorError):
    """没有 pending mutation token —— flush 失败或压根没 flush（Property 8）。

    这是 Requirement 3.2 的落点：HTML flush 未得到服务端成功响应时，模式切换必须
    停留在 HTML，room 创建与编辑器挂载调用次数**均为 0**。本异常在 coordinator
    的**第一行**抛出，此前一行数据库都没写。
    """

    error_code = "pending_mutation_token_required"


class PendingTokenSignatureError(MaterializeCoordinatorError):
    """token 签名不符 / 结构损坏 —— 伪造或截断。

    🔴 与 :class:`PendingTokenScopeError` 分两类：签名不符时**根本不该去读库**
    （否则伪造 token 就能探测某个 pending_mutation_id 是否存在）；scope 不符是
    「签名有效但用在了别的底稿上」。共用类型会让前者的 fail-closed 被后者遮蔽。
    """

    error_code = "pending_mutation_token_signature_invalid"


class PendingTokenScopeError(MaterializeCoordinatorError):
    """token 的 project/wp/entry/sheet/user 与本次 materialize 不同 scope。"""

    error_code = "pending_mutation_token_scope_mismatch"


class PendingTokenExpiredError(MaterializeCoordinatorError):
    """token 已过 TTL（Property 10 的「过期必须拒绝」）。"""

    error_code = "pending_mutation_token_expired"


class PendingTokenPayloadError(MaterializeCoordinatorError):
    """同 Idempotency-Key 但 payload digest 不同（Property 10 的「同 key 不同 payload」）。"""

    error_code = "pending_mutation_token_payload_mismatch"


class PendingTokenRevisionError(MaterializeCoordinatorError):
    """token 冻结的 expected revision 与当前 content base 不符。

    🔴 与 :class:`PendingTokenPayloadError` 分两类：payload 不同是「用户改了内容」，
    expected revision 不同是「别人在这期间提交过」。两者的用户动作完全不同
    （重新 flush vs 先刷新再编辑），共用 error_code 前端就只能给一句废话。
    """

    error_code = "pending_mutation_token_revision_mismatch"


class PendingTokenStateError(MaterializeCoordinatorError):
    """token 处于不可消费状态（`expired` / `invalidated` / 已被别的 commit 占用）。"""

    error_code = "pending_mutation_token_state_invalid"


class IdempotencyKeyMismatchError(MaterializeCoordinatorError):
    """请求头 Idempotency-Key 与 token 冻结的 key 不同。

    Requirement 3.1 要求 pending mutation 绑定 Idempotency-Key。两者不等意味着调用方
    把 A 次 flush 的 token 配上了 B 次请求的 key —— 那样「相同 key + 相同 payload 才
    返回同结果」的语义就断了。
    """

    error_code = "materialize_idempotency_key_mismatch"


# ── preflight：Requirement 3.3 的 422 家族（零 operation / 零 room）────────


class MaterializePreflightError(MaterializeCoordinatorError):
    """preflight 阶段的拒绝**分组基类** —— 全部映射 HTTP 422。

    🔴 它是本模块**唯一**允许存在的分组基类，理由是 router（Task 28）需要一个
    「这一类失败都是 422 且都零 operation」的可捕获边界。为了不让分组基类遮蔽子类，
    :data:`MATERIALIZE_REJECTION_STATUS` 按**具体子类**登记状态码，
    `test_refusals_are_pairwise_disjoint` 也只在同层子类之间比对。
    """

    error_code = "materialize_preflight_rejected"


class EntryNotMaterializableError(MaterializePreflightError):
    """capability 不允许产出 OO artifact（Requirement 3.9）。

    `single_html` 入口按定义没有 OO 侧内容，凭空造一个空白 xlsx 正是 3.9 明令禁止的；
    `unreachable` 入口不该有任何写入（Requirement 1.7）。
    """

    error_code = "entry_not_materializable"


class PerEntryContractMissingError(MaterializePreflightError):
    """`projection_contract` 入口缺 approved per-entry contract（Requirement 3.3）。

    🔴 与 :class:`BundleNotApprovedError` 分两类：前者是「bundle 本身合法但这个
    projection-based 入口没给 contract 对象」，后者是「bundle/typed slot 形态非法」。
    两条都会让 materialize 变成「按当前 alias 补齐」，但用户要做的事不同
    （发布 contract vs 批准 bundle）。
    """

    error_code = "per_entry_contract_required"


class BundleNotApprovedError(MaterializePreflightError):
    """bundle 未 approved、typed slot 缺失或使用非法空值（Requirement 2.3 / 3.3）。"""

    error_code = "definition_bundle_not_approved"


class RepresentationStillCandidateError(MaterializePreflightError):
    """entry 的当前 representation 仍是（或挂着）未 finalize 的 upgrade candidate。

    Requirement 6.18 / Property 67：candidate 不得被 resolver、room、download、
    current pointer 或 evidence 使用。
    """

    error_code = "representation_still_candidate"


class SubstrateNotPublishedError(MaterializePreflightError):
    """entry 还没有 published representation 可作 materialize 的 substrate。

    Requirement 3.5 要求 materialize「只写 adapter 声明的受管字段，保留模板公式、样式、
    合并单元格、图片、图表」—— 也就是说它必须**改写**一个既有 OOXML 底稿，而不是凭空
    生成一个。首个 representation 只能来自 Requirement 6.18 的版本化 template upgrader
    （`candidate → approved bundle → finalize`），HTML→OO 不是它的替代路径。

    🔴 与 :class:`RepresentationStillCandidateError` 分两类：前者是「一个都还没有」，
    后者是「有但还没 finalize」。用户要做的事不同（跑 upgrader 首次迁移 vs 批准
    contract/bundle 后 finalize），共用 error_code 前端只能给一句废话。
    """

    error_code = "materialize_substrate_not_published"


# ── 授权与 descriptor ─────────────────────────────────────────────────────


class MaterializeScopeNotVisibleError(MaterializeCoordinatorError):
    """显式 scope 在 `working_paper_sync_scope_index` 中不可见（统一 404 语义）。"""

    error_code = "materialize_scope_not_visible"


class MaterializeAuthorizationError(MaterializeCoordinatorError):
    """scope 可见但当前 project/workflow/lease/generation/fence/bundle 不允许（403）。

    重放路径也走这里：Task 25 正文「撤权后不得泄露 cached descriptor」。
    """

    error_code = "materialize_authorization_denied"


class DescriptorFieldMissingError(MaterializeCoordinatorError):
    """descriptor 字段不完整 —— 半个 descriptor 不得被构造，更不得被挂载（Property 11）。"""

    error_code = "launch_descriptor_incomplete"


class DescriptorStaleIdentityError(MaterializeCoordinatorError):
    """confirm-descriptor 回传的 identity 已陈旧或被篡改（409）。"""

    error_code = "launch_descriptor_stale_identity"


class DescriptorSubstrateStaleError(MaterializeCoordinatorError):
    """要下发的 representation 已不是该 entry 的 published 代际（409）。

    两个 raise 点、**同一个事实**：

    * **token 重放**：上次 commit 之后又发生过别的 commit 或 definition finalize，
      pending mutation 记下的 result representation 已被新代际取代；
    * **room 打开竞态**：preflight 通过之后、`open_or_reuse_room` 之前，
      entry pointer 被并发推进。

    Task 25 正文：「仅当前 project/workflow/lease/generation/fence/bundle 仍有效时
    成功重放才返回同 operation/content version/representation」。世界已经变了就**不许**
    成功重放 —— 必须显式 409 让前端重新 flush，而不是把一个陈旧 descriptor 挂上去，
    更不是让 `RoomPolicyError` 原样漏出去（那会被 router 记成 500）。

    🔴 与 :class:`DescriptorStaleIdentityError` 分两类：后者判的是**客户端回传值**
    与服务端事实不符（篡改/陈旧 echo），前者判的是**服务端自己**要下发的 substrate
    已过期。两者的用户动作不同（重开编辑器 vs 重新 flush）。
    """

    error_code = "launch_descriptor_substrate_stale"


class DefinitionUpgradeRevisionError(MaterializeCoordinatorError):
    """纯 definitions 升级改动了 business revision（Property 67 的反面）。"""

    error_code = "definition_upgrade_changed_revision"


# ── 记账自证：四条**互不遮蔽**的一致性判据 ─────────────────────────────────
#
# 🔴 为什么它们是模块级**纯函数**而不是内联 `if`：内联形态在正确实现下**恒不触发**，
# 于是「短路它」在任何真实场景里都观察不到差异 ⇒ 定向变异必判 GREEN（本任务首轮实测
# M28~M31/M51 五条全 GREEN）。抽成纯函数后可以用**合成输入**喂它们，判据才可证伪。
# 这与 Task 24 把 `assert_at_most_one_open_capture` 抽出来是同一个决定。


class FlushRevisionDriftError(MaterializeCoordinatorError):
    """flush 期间 business revision 发生了变化（Requirement 3.1 的反面）。"""

    error_code = "flush_advanced_content_revision"


class SingleCommitAccountingError(MaterializeCoordinatorError):
    """一次业务 commit 的提交次数或事务数不是 1（Requirement 3.1 / 2.4）。"""

    error_code = "materialize_not_single_commit"


class RevisionTargetAccountingError(MaterializeCoordinatorError):
    """commit 后的 revision 不等于 `base + 1`。

    🔴 与 :class:`SingleCommitAccountingError` 分两类：前者判「提交了几次」，后者判
    「提交到了哪个版本」。artifact 文件名里带 revision，错位后历史读取会取到别的版本。
    """

    error_code = "materialize_revision_target_mismatch"


class RevisionDeltaAccountingError(MaterializeCoordinatorError):
    """整次 materialize 的 revision 变化量不等于协议规定值。

    🔴 与 :class:`RevisionTargetAccountingError` 分两类：后者只看 receipt 里的目标值
    （commit 自己报的），前者看**数据库前后差**（外部观察）。二者不等价 —— 「receipt 说
    推进到 12」与「库里真的只多了 1」是两件事，而 Requirement 3.1 禁止的「两次 revision」
    只有后者能抓到。
    """

    error_code = "materialize_revision_delta_mismatch"


def assert_flush_revision_neutral(before: int, after: int) -> None:
    """flush 前后 business revision 必须逐字相等（Requirement 3.1）。"""
    if int(after) != int(before):
        raise FlushRevisionDriftError(
            f"flush 推进了 business content revision（{before} → {after}）—— "
            "Requirement 3.1 规定 flush 只创建 pending mutation，revision 只由 "
            "ContentMutationService.commit(...) 的唯一业务事务推进"
        )


def assert_single_business_commit(
    *, commit_count: int, transaction_ids: Sequence[str]
) -> None:
    """一次 materialize 恰一次 commit、恰一个数据库事务（Requirement 3.1 / 2.4）。"""
    if int(commit_count) != 1 or len(tuple(transaction_ids)) != 1:
        raise SingleCommitAccountingError(
            f"业务 commit 的提交次数={commit_count}、事务数={len(tuple(transaction_ids))}"
            f"（{list(transaction_ids)}）—— projection 与兼容 representation 必须在"
            "**一次** commit、一个事务内发布，不得先提交 projection-only revision 再补 artifact"
        )


def assert_revision_target(*, actual: int, base_revision: int) -> None:
    """commit 报告的 revision 必须恰为 `base + 1`。"""
    if int(actual) != int(base_revision) + 1:
        raise RevisionTargetAccountingError(
            f"commit 后 revision={actual}，与 base+1={int(base_revision) + 1} 不符 —— "
            "一次 materialize 只能推进一次 revision，且 artifact 文件名里的 revision "
            "必须与数据库一致"
        )


def assert_revision_delta(
    *, delta: int, replayed: bool, business_identity_reused: bool
) -> None:
    """数据库侧观察到的 revision 变化量必须符合协议：重放/复用为 0，提交为 1。"""
    expected = 0 if (replayed or business_identity_reused) else 1
    if int(delta) != expected:
        raise RevisionDeltaAccountingError(
            f"materialize 让 business revision 变化了 {delta} 次（expected {expected}；"
            f"replayed={replayed} reused={business_identity_reused}）—— "
            "Requirement 3.1 禁止「先提交 projection-only revision 再补 artifact」，"
            "AC 3.6 要求业务身份相同时幂等复用且不产生重复 revision"
        )


#: 拒绝类型 → HTTP 状态码。**按具体子类登记**，不靠 `isinstance` 走继承链 ——
#: 后者会让分组基类吞掉子类的语义（design §API：422 / 403 / 409 三者必须可分）。
MATERIALIZE_REJECTION_STATUS: Final[Mapping[type, int]] = {
    PendingTokenRequiredError: 409,
    PendingTokenSignatureError: 409,
    PendingTokenScopeError: 409,
    PendingTokenExpiredError: 409,
    PendingTokenPayloadError: 409,
    PendingTokenRevisionError: 409,
    PendingTokenStateError: 409,
    IdempotencyKeyMismatchError: 409,
    EntryNotMaterializableError: 422,
    PerEntryContractMissingError: 422,
    BundleNotApprovedError: 422,
    RepresentationStillCandidateError: 422,
    SubstrateNotPublishedError: 422,
    MaterializeScopeNotVisibleError: 404,
    MaterializeAuthorizationError: 403,
    DescriptorFieldMissingError: 422,
    DescriptorStaleIdentityError: 409,
    DescriptorSubstrateStaleError: 409,
    DefinitionUpgradeRevisionError: 422,
    FlushRevisionDriftError: 500,
    SingleCommitAccountingError: 500,
    RevisionTargetAccountingError: 500,
    RevisionDeltaAccountingError: 500,
}


def classify_materialize_rejection(exc: BaseException) -> int:
    """把拒绝异常映射成 HTTP 状态码（router 的唯一映射点）。

    未登记的类型返回 500 而**不是**默认 400：未知失败必须 fail visible，
    静默降级成 4xx 会让「协议缺一条」看起来像「用户输入错了」。
    """
    return MATERIALIZE_REJECTION_STATUS.get(type(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════
# 1. pending mutation token
# ═══════════════════════════════════════════════════════════════════════════

#: token 载荷 schema 版本。结构变化必须 +1，否则新旧代码对同一份载荷算出同一签名。
TOKEN_SCHEMA_VERSION: Final[str] = "wp-sync-pending-mutation:v1"

#: token 默认 TTL。短 TTL 是 Requirement 3.1 的显式要求（「具有短 TTL」）。
DEFAULT_PENDING_TTL: Final[timedelta] = timedelta(minutes=10)


@dataclass(frozen=True)
class PendingMutationTokenPayload:
    """token 里冻结的全部身份。**没有**业务内容 —— 内容在 payload artifact 里。

    为什么 token 要自带 scope 而不是只带一个 id：签名校验必须能在**读库之前**完成
    （见 :class:`PendingTokenSignatureError` 的说明）。只带 id 的话，任何伪造 id 都会
    先触发一次数据库查询，把「该 id 是否存在」变成可探测信息。
    """

    schema_version: str
    pending_mutation_id: uuid.UUID
    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    sheet_key: str
    user_id: uuid.UUID
    expected_revision: int
    payload_sha256: str
    idempotency_key: str
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.schema_version != TOKEN_SCHEMA_VERSION:
            raise PendingTokenSignatureError(
                f"token schema_version={self.schema_version!r} 未登记"
                f"（当前 {TOKEN_SCHEMA_VERSION!r}）—— 未知版本一律 fail closed"
            )
        if not is_digest(self.payload_sha256):
            raise PendingTokenSignatureError(
                f"token payload_sha256 非法: {self.payload_sha256!r}"
            )
        if not str(self.entry_id).strip() or not str(self.sheet_key).strip():
            raise PendingTokenSignatureError("token 的 entry_id / sheet_key 不得为空")
        if not str(self.idempotency_key).strip():
            raise PendingTokenSignatureError("token 的 idempotency_key 不得为空")
        if int(self.expected_revision) < 0:
            raise PendingTokenSignatureError(
                f"token expected_revision 不得为负: {self.expected_revision}"
            )

    def canonical_mapping(self) -> dict[str, Any]:
        """签名输入。字段顺序无关（canonical JSON 递归排序键）。"""
        return {
            "schema_version": self.schema_version,
            "pending_mutation_id": str(self.pending_mutation_id),
            "project_id": str(self.project_id),
            "wp_id": str(self.wp_id),
            "entry_id": str(self.entry_id),
            "sheet_key": str(self.sheet_key),
            "user_id": str(self.user_id),
            "expected_revision": int(self.expected_revision),
            "payload_sha256": str(self.payload_sha256),
            "idempotency_key": str(self.idempotency_key),
            "expires_at": self.expires_at.astimezone(timezone.utc).isoformat(),
        }


class PendingMutationTokenCodec:
    """token 的签名与解码。**唯一**实现 —— 两套编解码必然漂移。

    形态：`base64url(canonical_json) + "." + base64url(hmac_sha256)`。
    刻意不用 JWT：这里不需要 issuer/audience/exp 那套语义（TTL 的权威在数据库行上，
    不在 token 里），多引一层库只会多一个可漂移的解析口径。
    """

    __slots__ = ("_secret",)

    def __init__(self, secret: str | bytes) -> None:
        raw = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
        if not raw:
            raise MaterializeCoordinatorError(
                "pending mutation token 签名密钥为空 —— 空密钥等于不签名"
            )
        self._secret = raw

    @staticmethod
    def _b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _unb64(text: str) -> bytes:
        pad = "=" * (-len(text) % 4)
        return base64.urlsafe_b64decode(text + pad)

    def _mac(self, body: bytes) -> bytes:
        return hmac.new(self._secret, body, hashlib.sha256).digest()

    def encode(self, payload: PendingMutationTokenPayload) -> str:
        body = json.dumps(
            payload.canonical_mapping(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"{self._b64(body)}.{self._b64(self._mac(body))}"

    def decode(self, token: str | None) -> PendingMutationTokenPayload:
        """解码 + 常量时间验签。任何形态问题都是 :class:`PendingTokenSignatureError`。

        空 token 单独抛 :class:`PendingTokenRequiredError` —— 「没 flush」与「flush 了但
        token 坏了」是两件事，Property 8 只关心前者。
        """
        if token is None or not str(token).strip():
            raise PendingTokenRequiredError(
                "materialize 缺 pending_mutation_token —— HTML flush 未成功时模式切换"
                "必须停留在 HTML，room 创建与编辑器挂载次数均为 0"
                "（Requirement 3.2 / Property 8）"
            )
        text = str(token).strip()
        if text.count(".") != 1:
            raise PendingTokenSignatureError(
                "pending mutation token 结构非法（应为 body.signature 两段）"
            )
        body_b64, sig_b64 = text.split(".", 1)
        try:
            body = self._unb64(body_b64)
            signature = self._unb64(sig_b64)
        except Exception as exc:  # noqa: BLE001 - base64 形态错一律 fail closed
            raise PendingTokenSignatureError(
                f"pending mutation token base64 解码失败: {type(exc).__name__}"
            ) from exc
        if not hmac.compare_digest(signature, self._mac(body)):
            raise PendingTokenSignatureError(
                "pending mutation token 签名不符 —— 伪造/篡改的 token 在**读库之前**即被"
                "拒绝，不得据此探测 pending_mutation_id 是否存在"
            )
        try:
            raw = json.loads(body.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise PendingTokenSignatureError(
                f"pending mutation token 载荷不是合法 JSON: {type(exc).__name__}"
            ) from exc
        if not isinstance(raw, Mapping):
            raise PendingTokenSignatureError("pending mutation token 载荷不是对象")
        missing = sorted(
            key
            for key in (
                "schema_version", "pending_mutation_id", "project_id", "wp_id",
                "entry_id", "sheet_key", "user_id", "expected_revision",
                "payload_sha256", "idempotency_key", "expires_at",
            )
            if key not in raw
        )
        if missing:
            raise PendingTokenSignatureError(
                f"pending mutation token 载荷缺字段 {missing}"
            )
        try:
            return PendingMutationTokenPayload(
                schema_version=str(raw["schema_version"]),
                pending_mutation_id=uuid.UUID(str(raw["pending_mutation_id"])),
                project_id=uuid.UUID(str(raw["project_id"])),
                wp_id=uuid.UUID(str(raw["wp_id"])),
                entry_id=str(raw["entry_id"]),
                sheet_key=str(raw["sheet_key"]),
                user_id=uuid.UUID(str(raw["user_id"])),
                expected_revision=int(raw["expected_revision"]),
                payload_sha256=str(raw["payload_sha256"]),
                idempotency_key=str(raw["idempotency_key"]),
                expires_at=datetime.fromisoformat(str(raw["expires_at"])),
            )
        except (ValueError, TypeError) as exc:
            raise PendingTokenSignatureError(
                f"pending mutation token 字段类型非法: {exc}"
            ) from exc


@dataclass(frozen=True)
class PendingMutationReceipt:
    """`POST .../pending-mutations` 的响应体 —— `flushHtml()` 的**全部**返回值。

    四个字段与 design §API 的 JSON 逐项对应。刻意**不含** revision 推进结果、
    content version id 或 representation id：flush 按定义不产生业务版本
    （Requirement 3.1「flush pending 编辑并创建服务端 pending_mutation」），
    多返回一个字段就会诱使前端把 flush 当成提交。
    """

    pending_mutation_id: uuid.UUID
    pending_mutation_token: str
    expected_revision: int
    payload_sha256: str
    expires_at: datetime
    idempotency_key: str
    replayed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "pending_mutation_token": self.pending_mutation_token,
            "expected_revision": int(self.expected_revision),
            "payload_sha256": self.payload_sha256,
            "expires_at": self.expires_at.astimezone(timezone.utc).isoformat(),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 2. 授权阶段链（authorization-before-idempotency 由类型强制）
# ═══════════════════════════════════════════════════════════════════════════


class MaterializeStage(str, Enum):
    """`materialize` 固定阶段链。**顺序即协议**，缺阶段即拒绝。

    与 Task 23 `ReadStage` 同形：把「不可交换的顺序」变成参数类型上的事实，
    而不是靠调用点自觉。
    """

    scope_resolved = "scope_resolved"
    action_authorized = "action_authorized"
    token_verified = "token_verified"
    preflight_passed = "preflight_passed"


@dataclass(frozen=True)
class MaterializeRequest:
    """`POST .../materialize` 的入参（未授权形态）。

    `contract` / `adapter` 在这里出现是因为 Task 13 的 adapter 是**纯函数**
    （`SyncContext` 不含 session/repository/outbox），由调用方装配后传入；
    coordinator 只做校验与编排，不去 import 具体 adapter 实现。
    """

    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    sheet_key: str
    user_id: uuid.UUID
    pending_mutation_token: str | None
    idempotency_key: str
    expected_revision: int
    capability: Capability
    projection: Projection
    document_type: str = "xlsx"
    contract: SyncContract | None = None
    adapter: Any = None
    adapter_id: str = ""
    adapter_build_digest: str = ""
    lease_token: str = ""
    permission_epoch: int = 0
    client_edit_epoch: int = 0

    def __post_init__(self) -> None:
        assert_no_mutation_surface(self, label="MaterializeRequest")
        if not str(self.entry_id).strip():
            raise MaterializeCoordinatorError("materialize 请求缺 entry_id")
        if not str(self.idempotency_key).strip():
            raise MaterializeCoordinatorError(
                "materialize 请求缺 Idempotency-Key —— Requirement 3.1 要求 pending "
                "mutation 与 commit 共用同一个 key"
            )
        object.__setattr__(
            self,
            "capability",
            self.capability
            if isinstance(self.capability, Capability)
            else Capability(self.capability),
        )

    @property
    def scope(self) -> RoomScope:
        return RoomScope(
            project_id=self.project_id, wp_id=self.wp_id, entry_id=str(self.entry_id)
        )


@dataclass(frozen=True)
class AuthorizedMaterializeRequest:
    """已完成 scope 解析 + 当前权限重验的请求。**只能**由 `authorize()` 产出。

    :meth:`MaterializeCoordinator.materialize` 的签名只接受它 —— 于是「先查 pending
    mutation cache、再判权限」在构造上不可表达（Task 25 正文：任何重放先经过
    authorization-before-idempotency guard）。
    """

    request: MaterializeRequest
    stages: tuple[MaterializeStage, ...]

    def __post_init__(self) -> None:
        assert_no_mutation_surface(self, label="AuthorizedMaterializeRequest")

    def with_stage(self, stage: MaterializeStage) -> "AuthorizedMaterializeRequest":
        return AuthorizedMaterializeRequest(
            request=self.request, stages=self.stages + (stage,)
        )

    def assert_authorized(self) -> None:
        for required in (
            MaterializeStage.scope_resolved,
            MaterializeStage.action_authorized,
        ):
            if required not in self.stages:
                raise MaterializeAuthorizationError(
                    f"AuthorizedMaterializeRequest 缺阶段 {required.value} —— "
                    "未完成 scope 解析与当前权限重验的请求不得进入 idempotency/cache "
                    "查询（Task 25 正文：authorization-before-idempotency）"
                )

    def assert_token_verified(self) -> None:
        """`materialize` 额外要求 token 已在授权阶段验签并逐项比对。

        🔴 与 :meth:`assert_authorized` 分成两个方法：`create` 路径（flush）**没有**
        token，它只需要前两个阶段。合成一个方法就得给 create 路径开一个例外分支，
        而例外分支一旦存在，「materialize 必须带已验 token」这条判据就可以被绕过 ——
        把 `authorize_create` 的产物直接喂给 `materialize` 即可，而那正是
        「未验签 token 消费 pending mutation」。
        """
        self.assert_authorized()
        if MaterializeStage.token_verified not in self.stages:
            raise MaterializeAuthorizationError(
                "AuthorizedMaterializeRequest 缺阶段 token_verified —— materialize 只接受 "
                "`authorize()`（read 路径）的产物；`authorize_create()` 的产物只能用于 "
                "flush，不得用来消费 pending mutation"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 唯一 launch descriptor
# ═══════════════════════════════════════════════════════════════════════════

#: descriptor 必须齐备的字段（Requirement 3.7 逐项点名 + design §API 的 JSON）。
#:
#: 🔴 这不是「文档里列一下」：:func:`assert_descriptor_mountable` 按本元组逐项实测，
#: 而 :class:`EditorLaunchDescriptor.__post_init__` 又无条件调用它。于是「字段完整后
#: 才 mount」不是前端自觉，而是**半个 descriptor 造不出来**。
DESCRIPTOR_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "operation_id",
    "room_id",
    "participant_id",
    "doc_key",
    "generation",
    "server_applied_revision",
    "client_confirmed_base_revision",
    "content_version_id",
    "representation_id",
    "representation_generation",
    "artifact_sha256",
    "write_fence_epoch",
    "authority_model",
    "authority_model_definition_sha256",
    "definition_bundle_id",
    "definition_bundle_sha256",
    "definition_bundle_slots",
    "document_type",
    "mode",
    "onlyoffice_config",
)

#: `definition_bundle_slots` 必须齐备的三个 typed slot（Requirement 2.3）。
_REQUIRED_SLOT_KEYS: Final[tuple[str, ...]] = ("template", "instrumentation", "contract")

#: :class:`DescriptorSubstrateStaleError` 的两个 raise 点标记。
#:
#: 🔴 存在的理由（本任务实测）：两处是**同一个事实**、共用同一个异常类型，于是只断言
#: 类型的守卫会让它们互相遮蔽 —— 删掉重放侧那条判据后，流程会往下走到 room 打开侧，
#: 抛出**同样**的类型，守卫判 GREEN。标记让「哪一条在起作用」可分辨（与
#: `resolution.py` 断言消息含 ``frozen `representation_id``` 同一手法）。
STALE_ON_REPLAY_MARKER: Final[str] = "stale-substrate/replay"
STALE_ON_ROOM_OPEN_MARKER: Final[str] = "stale-substrate/room-open"


@dataclass(frozen=True)
class EditorLaunchDescriptor:
    """服务端返回的**唯一** OO 启动凭证（Requirement 3.7 / Property 11）。

    前端拿到它之前不得创建 DocEditor，拿到之后也不得再自行请求 config
    —— `onlyoffice_config` 就在里面，没有第二个来源。
    """

    operation_id: uuid.UUID
    room_id: uuid.UUID
    participant_id: uuid.UUID
    doc_key: str
    generation: int
    server_applied_revision: int
    client_confirmed_base_revision: int | None
    content_version_id: uuid.UUID
    representation_id: uuid.UUID
    representation_generation: int
    artifact_sha256: str
    write_fence_epoch: int
    authority_model: str
    authority_model_definition_sha256: str
    definition_bundle_id: uuid.UUID
    definition_bundle_sha256: str
    definition_bundle_slots: Mapping[str, Mapping[str, str]]
    document_type: str
    mode: str
    onlyoffice_config: Mapping[str, Any]

    def __post_init__(self) -> None:
        assert_no_mutation_surface(self, label="EditorLaunchDescriptor")
        assert_descriptor_mountable(self)

    @property
    def mountable(self) -> bool:
        """恒为 `True` —— 不可挂载的 descriptor 在 `__post_init__` 就构造不出来。

        保留这个属性是为了让调用点读起来是「先问能不能挂」而不是「反正拿到就挂」；
        它的真值由构造期判据保证，不是第二套判断。
        """
        return True

    def confirm_payload(self) -> dict[str, Any]:
        """前端 `confirm-descriptor` 必须逐项回传的 identity（design §API）。"""
        return {
            "participant_id": str(self.participant_id),
            "generation": int(self.generation),
            "doc_key": self.doc_key,
            "representation_id": str(self.representation_id),
            "artifact_sha256": self.artifact_sha256,
            "content_revision": int(self.server_applied_revision),
            "write_fence_epoch": int(self.write_fence_epoch),
            "authority_model_definition_sha256": self.authority_model_definition_sha256,
            "definition_bundle_id": str(self.definition_bundle_id),
            "definition_bundle_sha256": self.definition_bundle_sha256,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": str(self.operation_id),
            "room_id": str(self.room_id),
            "participant_id": str(self.participant_id),
            "doc_key": self.doc_key,
            "generation": int(self.generation),
            "server_applied_revision": int(self.server_applied_revision),
            "client_confirmed_base_revision": (
                None
                if self.client_confirmed_base_revision is None
                else int(self.client_confirmed_base_revision)
            ),
            "content_version_id": str(self.content_version_id),
            "representation_id": str(self.representation_id),
            "representation_generation": int(self.representation_generation),
            "artifact_sha256": self.artifact_sha256,
            "write_fence_epoch": int(self.write_fence_epoch),
            "authority_model": self.authority_model,
            "authority_model_definition_sha256": self.authority_model_definition_sha256,
            "definition_bundle_id": str(self.definition_bundle_id),
            "definition_bundle_sha256": self.definition_bundle_sha256,
            "definition_bundle_slots": {
                slot: dict(spec) for slot, spec in self.definition_bundle_slots.items()
            },
            "document_type": self.document_type,
            "mode": self.mode,
            "onlyoffice_config": dict(self.onlyoffice_config),
        }


def assert_descriptor_mountable(descriptor: Any) -> None:
    """descriptor 字段完整性（Property 11 的「字段完整后才 mount」）。

    逐类判据，**不是**「非空即可」：

    * UUID 字段不得是全零 UUID（`uuid.UUID(int=0)` 是「我还没拿到」的常见占位，
      它非 `None` 却毫无意义 —— Task 15 的 `SyncContext` 就用它当事务前占位）；
    * digest 字段必须过 `is_digest`（64 位小写 hex 且非全零）；
    * `generation` / `representation_generation` >= 1，`server_applied_revision` >= 1，
      `write_fence_epoch` >= 1；
    * `definition_bundle_slots` 必须**三个 slot 全在**，每个都带非空 `type` 与合法
      `sha256`（Requirement 2.3：字段缺失/空串/全零 hash 均不得进入 canonical bytes）；
    * `onlyoffice_config` 非空 —— 空 config 意味着前端仍需自行请求 config，
      那正是 Property 11 禁止的「组件不得再次请求 config」。
    """
    missing = [
        name for name in DESCRIPTOR_REQUIRED_FIELDS if not hasattr(descriptor, name)
    ]
    if missing:
        raise DescriptorFieldMissingError(
            f"launch descriptor 缺字段 {missing} —— Requirement 3.7 要求 room/participant/"
            "doc_key/generation、server+client revision、representation id/generation、"
            "artifact、authority model、非空 bundle id/digest/typed slots、fence 与 config "
            "全部具备后前端才能挂载 DocEditor"
        )
    for name in (
        "operation_id", "room_id", "participant_id", "content_version_id",
        "representation_id", "definition_bundle_id",
    ):
        value = getattr(descriptor, name)
        if not isinstance(value, uuid.UUID) or value.int == 0:
            raise DescriptorFieldMissingError(
                f"launch descriptor 的 {name}={value!r} 不是有效 UUID —— 全零 UUID 是"
                "「尚未取得」的占位值，不得作为 descriptor identity 下发"
            )
    for name in (
        "artifact_sha256", "authority_model_definition_sha256", "definition_bundle_sha256",
    ):
        value = getattr(descriptor, name)
        if not is_digest(value):
            raise DescriptorFieldMissingError(
                f"launch descriptor 的 {name}={value!r} 不是合法 digest"
                "（64 位小写 hex 且非全零）"
            )
    for name, minimum in (
        ("generation", 1),
        ("representation_generation", 1),
        ("server_applied_revision", 1),
        ("write_fence_epoch", 1),
    ):
        value = getattr(descriptor, name)
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise DescriptorFieldMissingError(
                f"launch descriptor 的 {name}={value!r} 必须是 >= {minimum} 的整数"
            )
    for name in ("doc_key", "authority_model", "document_type", "mode"):
        value = getattr(descriptor, name)
        if not isinstance(value, str) or not value.strip():
            raise DescriptorFieldMissingError(
                f"launch descriptor 的 {name} 为空 —— 不得下发半个 descriptor"
            )
    slots = getattr(descriptor, "definition_bundle_slots")
    if not isinstance(slots, Mapping):
        raise DescriptorFieldMissingError(
            f"definition_bundle_slots 必须是映射，实得 {type(slots).__name__}"
        )
    absent = [key for key in _REQUIRED_SLOT_KEYS if key not in slots]
    if absent:
        raise DescriptorFieldMissingError(
            f"definition_bundle_slots 缺 typed slot {absent} —— 三个 slot 必须全部出现，"
            "可选 child 只能使用版本化 typed null marker（Requirement 2.3）"
        )
    for key in _REQUIRED_SLOT_KEYS:
        spec = slots[key]
        if not isinstance(spec, Mapping):
            raise DescriptorFieldMissingError(
                f"definition_bundle_slots[{key!r}] 必须是映射，实得 {type(spec).__name__}"
            )
        slot_type = str(spec.get("type") or "").strip()
        if not slot_type:
            raise DescriptorFieldMissingError(
                f"definition_bundle_slots[{key!r}].type 为空 —— 禁以缺字段/空串代替 "
                "typed null marker"
            )
        if not is_digest(spec.get("sha256")):
            raise DescriptorFieldMissingError(
                f"definition_bundle_slots[{key!r}].sha256={spec.get('sha256')!r} "
                "非法（空串/全零/非小写 hex）"
            )
    config = getattr(descriptor, "onlyoffice_config")
    if not isinstance(config, Mapping) or not config:
        raise DescriptorFieldMissingError(
            "launch descriptor 的 onlyoffice_config 为空 —— descriptor 是编辑器 config 的"
            "唯一来源，空 config 会逼组件自行再请求一次（Property 11 明令禁止）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. preflight / 结果值对象
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class MaterializePreflight:
    """preflight 通过后冻结下来的全部身份。

    它是「commit/operation 冻结 approved authority model 与 definition bundle
    id/digest/typed slots」这句话的载体：一旦构造成功，后续每一步都从**它**取值，
    没有任何一步再去问「现在 registry 里 alias 指向谁」（Requirement 2.10）。
    """

    resolution: CanonicalResolution
    bundle: DefinitionBundleSnapshot
    bundle_identity: FrozenBundleIdentity
    substrate_path: Path
    substrate_sha256: str
    base_content_version_id: uuid.UUID
    base_revision: int
    capability: Capability

    def __post_init__(self) -> None:
        assert_no_mutation_surface(self, label="MaterializePreflight")

    @property
    def authority_model(self) -> AuthorityModel:
        return self.bundle.authority_model

    @property
    def typed_slot_inventory(self) -> tuple[tuple[str, str, str], ...]:
        return self.bundle.typed_slot_inventory

    def descriptor_slots(self) -> dict[str, dict[str, str]]:
        """bundle typed slots → descriptor 形态（design §API 的 `definition_bundle_slots`）。"""
        return {
            slot: {"type": slot_type, "sha256": digest}
            for slot, slot_type, digest in self.typed_slot_inventory
        }


@dataclass(frozen=True)
class MaterializeOutcome:
    """一次 HTML→OO 编排的结果。

    `descriptor is None` 是**合法**结果形态吗？不是 —— 成功路径必然带 descriptor。
    它可为 `None` 只因为 :meth:`MaterializeCoordinator.materialize` 在失败时抛异常而不
    返回半成品；保留 `Optional` 类型是为了让 `rooms_opened == 0 and descriptor is None`
    这条 Property 8 断言在**类型层面**说得通。
    """

    descriptor: EditorLaunchDescriptor | None
    operation_id: uuid.UUID
    content_version_id: uuid.UUID
    revision: int
    representation_id: uuid.UUID
    representation_generation: int
    replayed: bool
    business_identity_reused: bool
    commit_count: int
    transaction_ids: tuple[str, ...]
    rooms_opened: int
    revision_delta: int
    receipt: ContentCommitReceipt | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "descriptor": None if self.descriptor is None else self.descriptor.as_dict(),
            "operation_id": str(self.operation_id),
            "content_version_id": str(self.content_version_id),
            "revision": int(self.revision),
            "representation_id": str(self.representation_id),
            "representation_generation": int(self.representation_generation),
            "replayed": bool(self.replayed),
            "business_identity_reused": bool(self.business_identity_reused),
            "commit_count": int(self.commit_count),
            "rooms_opened": int(self.rooms_opened),
            "revision_delta": int(self.revision_delta),
        }


@dataclass(frozen=True)
class DescriptorConfirmation:
    """`confirm-descriptor` 的结果（Property 11 的服务端确认侧）。"""

    confirmation_id: uuid.UUID
    room_id: uuid.UUID
    participant_id: uuid.UUID
    generation: int
    representation_id: uuid.UUID
    content_version_id: uuid.UUID
    room_state: str
    replayed: bool
    forcesave_unlocked: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "confirmation_id": str(self.confirmation_id),
            "room_id": str(self.room_id),
            "participant_id": str(self.participant_id),
            "generation": int(self.generation),
            "representation_id": str(self.representation_id),
            "content_version_id": str(self.content_version_id),
            "room_state": self.room_state,
            "replayed": bool(self.replayed),
            "forcesave_unlocked": bool(self.forcesave_unlocked),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 5. authorization-first 的源码形态判据
# ═══════════════════════════════════════════════════════════════════════════

#: 授权阶段禁止出现的业务表 ORM 符号（与 Task 23 同一份名单形态）。
_BUSINESS_TABLES: Final[tuple[str, ...]] = (
    "WorkpaperPendingMutation",
    "WorkpaperSyncOperation",
    "WorkpaperContentVersion",
    "WorkpaperContentRepresentation",
    "WorkpaperOoRoom",
    "WorkpaperOoParticipant",
)

#: 授权阶段允许调用的 repository 方法（**只**读非敏感 scope index）。
_SCOPE_ONLY_REPO_CALLS: Final[frozenset[str]] = frozenset({"resolve_scope"})


def _dedent_source(src: str) -> str:
    lines = src.splitlines()
    indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
    cut = min(indents) if indents else 0
    return "\n".join(l[cut:] if len(l) >= cut else l for l in lines)


#: 授权阶段的**全部**方法。判据必须覆盖整条阶段，不只入口方法。
#:
#: 🔴 只扫 `authorize` 是不够的：把一次 `sa.select(WorkpaperPendingMutation)` 挪进它
#: 调用的 helper（`_assert_token_matches_request`）里，只扫入口的判据就分辨不出来。
#: 名单显式登记而不是自动跟随调用图 —— 自动跟随会把 `RoomService` 整棵树拖进来，
#: 判据范围反而变得不可解释。
_AUTHORIZATION_PHASE_METHODS: Final[tuple[str, ...]] = (
    "authorize",
    "_assert_token_matches_request",
)


def assert_authorization_first_shape() -> tuple[str, ...]:
    """AST 反查授权阶段：只许读非敏感 scope index。

    返回授权阶段实际调用到的 repository 方法名（正常恰为 ``('resolve_scope',)``）。

    🔴 为什么必须是源码判据而不是行为判据：Requirement 10.5 禁止的是**代码形态**
    （「严禁先查 room/operation/recovery/application 来反推 scope」）。行为观察只能证明
    「这次没查」；把 `sa.select(WorkpaperPendingMutation)` 加回授权阶段后，行为测试
    大概率仍然通过（结果一样），只有源码判据会红。

    两条判据合一，因为它们是同一件事的两面：多引一个业务表符号（第 1 条），或者
    不引符号而多调一个仓储方法（第 2 条）—— 只查其一必留缺口。
    """
    repo_calls: set[str] = set()
    for method_name in _AUTHORIZATION_PHASE_METHODS:
        method = getattr(MaterializeCoordinator, method_name)
        tree = ast.parse(_dedent_source(inspect.getsource(method)))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in _BUSINESS_TABLES:
                raise MaterializeAuthorizationError(
                    f"{method_name}() 引用了业务表 {node.id} —— authorization-first 要求"
                    "授权阶段**只**读非敏感 working_paper_sync_scope_index"
                    "（Requirement 10.5）"
                )
            if isinstance(node, ast.Attribute) and node.attr in _BUSINESS_TABLES:
                raise MaterializeAuthorizationError(
                    f"{method_name}() 引用了业务表属性 {node.attr}"
                )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = node.func.value
                if (
                    isinstance(owner, ast.Attribute)
                    and isinstance(owner.value, ast.Name)
                    and owner.value.id == "self"
                    and owner.attr
                    in ("_repo", "_rooms", "_session", "_mutations", "_resolution")
                ):
                    repo_calls.add(node.func.attr)
    extra = sorted(repo_calls - _SCOPE_ONLY_REPO_CALLS)
    if extra:
        raise MaterializeAuthorizationError(
            f"授权阶段额外调用了 {extra} —— 只允许 "
            f"{sorted(_SCOPE_ONLY_REPO_CALLS)}（先查 scope index，禁止先查 "
            "pending mutation/room/operation 反推 scope 或先命中幂等缓存）"
        )
    return tuple(sorted(repo_calls))


# ═══════════════════════════════════════════════════════════════════════════
# 6. coordinator
# ═══════════════════════════════════════════════════════════════════════════

#: 不允许 materialize 的 capability（Requirement 3.9 / 1.7）。
_NON_MATERIALIZABLE: Final[frozenset[Capability]] = frozenset(
    {Capability.single_html, Capability.unreachable}
)

#: pending mutation 里可被 materialize 消费的状态。
_CONSUMABLE_PENDING_STATES: Final[frozenset[PendingMutationState]] = frozenset(
    {PendingMutationState.pending, PendingMutationState.committing}
)

#: `materialize` 允许复用的 room 状态（新 generation 的 room 从 `opening` 起）。
_REUSABLE_ROOM_STATES: Final[frozenset[RoomState]] = frozenset(
    {RoomState.opening, RoomState.active, RoomState.close_barrier}
)


class MaterializeCoordinator:
    """HTML → OO 的唯一编排入口。

    **不写第二套业务逻辑**：projection 提交走 Task 15、artifact/bundle 解析走 Task 12、
    room/lease/confirmation 走 Task 21、candidate finalize 走 Task 15 的
    `RepresentationService`。本类持有的是**顺序**与**拒绝分类**。
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: WorkpaperSyncRepository,
        artifacts: CanonicalArtifactRepository,
        resolution: CanonicalResolutionService,
        mutations: ContentMutationService,
        rooms: RoomService | None = None,
        token_codec: PendingMutationTokenCodec,
        representations: RepresentationService | None = None,
        room_ttl: timedelta | None = None,
        pending_ttl: timedelta = DEFAULT_PENDING_TTL,
    ) -> None:
        self._session = session
        self._repo = repository
        self._artifacts = artifacts
        self._resolution = resolution
        self._mutations = mutations
        self._rooms = rooms if rooms is not None else RoomService(repository)
        self._tokens = token_codec
        self._representations = representations
        self._room_ttl = room_ttl
        self._pending_ttl = pending_ttl
        #: 🔴 只增不减的可观测计数。Property 8 的「编辑器挂载次数为 0」在后端侧的
        #: 对应事实就是「一个 descriptor 都没发出去」；守卫读它，而不是读本模块的自述。
        self.descriptors_issued: int = 0
        self.commits_invoked: int = 0

    # ─────────────────────────────────────────────────────────────────
    # 6.1 授权：**只**读非敏感 scope index
    # ─────────────────────────────────────────────────────────────────

    async def authorize_create(
        self,
        request: MaterializeRequest,
        *,
        authorize: Callable[[MaterializeRequest], Awaitable[bool] | bool] | None = None,
    ) -> AuthorizedMaterializeRequest:
        """flush（create）路径的授权。**刻意不读 scope index。**

        pending-mutations 是 create 端点：此刻还不存在任何 opaque resource id，
        `working_paper_sync_scope_index` 里没有行可查（它的每一行都随 child 同事务创建）。
        硬造一次查询只会得到「查不到 ⇒ 404」，把「第一次 flush」变成永远失败。

        因此这条路径的授权面是**显式 route scope + 调用方回调**：project visibility 与
        workflow/编辑锁由 router（Task 28）在 authenticate 之后判定，本方法只保证
        「没有回调放行就没有 pending mutation」。

        🔴 与 :meth:`authorize` 分成两个方法而不是加一个 `create: bool` 开关：
        后者会让 :func:`assert_authorization_first_shape` 的 AST 判据同时覆盖两条语义
        不同的路径 —— 一旦 read 路径的 scope-index 查询被删掉，只要 create 分支还在，
        判据就分辨不出来。
        """
        if authorize is not None:
            verdict = authorize(request)
            if inspect.isawaitable(verdict):
                verdict = await verdict
            if not verdict:
                raise MaterializeAuthorizationError(
                    f"entry {request.entry_id!r} 的当前 project/workflow/编辑锁不允许 "
                    "flush（403）"
                )
        return AuthorizedMaterializeRequest(
            request=request,
            stages=(
                MaterializeStage.scope_resolved,
                MaterializeStage.action_authorized,
            ),
        )

    async def authorize(
        self,
        request: MaterializeRequest,
        *,
        authorize: Callable[[MaterializeRequest], Awaitable[bool] | bool] | None = None,
    ) -> AuthorizedMaterializeRequest:
        """materialize 路径的授权：固定顺序 **token → scope index → 当前权限**。

        端点的 opaque resource id 是 **pending mutation id**，它来自签名 token ——
        解码与逐项比对全在内存里完成（零业务读、零数据库往返），所以先做它不违反
        authorization-first：design §API 的顺序正是「解析显式 route scope 与端点 opaque
        ids/可选短期 signed scope claim → **只查询** scope index → visibility →
        action/workflow/lease/generation/fence/bundle → business resource/cache lookup」。

        随后**只**查 `working_paper_sync_scope_index` 的 `pending_mutation` 行
        （Task 10 在 `create_pending_mutation` 里与 child 同事务写入）。查不到、已 retire
        与跨 scope 使用共用同一 :class:`MaterializeScopeNotVisibleError`（404 语义），
        不得据此推断该 id 是否存在。

        `authorize` 回调只拿到 :class:`MaterializeRequest`（显式 scope + 声明），
        拿不到任何业务行 —— 需要业务行才能判权限就说明 scope 模型漏了字段。
        撤权后原 Idempotency-Key 重放在这里就被拦下，:meth:`materialize` 根本到不了，
        于是「不得泄露 cached descriptor」有可执行判据。
        """
        token = self._tokens.decode(request.pending_mutation_token)
        self._assert_token_matches_request(token, request)
        row = await self._repo.resolve_scope(
            resource_kind=ScopeResourceKind.pending_mutation,
            resource_id=str(token.pending_mutation_id),
        )
        if row is None:
            raise MaterializeScopeNotVisibleError(
                f"pending mutation {token.pending_mutation_id} 在 scope index 中不可见"
                "（不存在或已 retire）—— 与「跨 scope 使用」共用同一 404 语义"
            )
        if (
            row.project_id != request.project_id
            or row.wp_id != request.wp_id
            or str(row.entry_id) != str(request.entry_id)
        ):
            raise MaterializeScopeNotVisibleError(
                f"pending mutation {token.pending_mutation_id} 与显式声明的 "
                "project/wp/entry scope 不符 —— 同 404 语义"
            )
        stages = (MaterializeStage.scope_resolved,)
        if authorize is not None:
            verdict = authorize(request)
            if inspect.isawaitable(verdict):
                verdict = await verdict
            if not verdict:
                raise MaterializeAuthorizationError(
                    f"entry {request.entry_id!r} 的 scope 可见，但当前 project/workflow/"
                    "lease/generation/fence/bundle 不允许 materialize（403，与 404 分型）"
                    " —— 撤权后原 Idempotency-Key 重放不得返回 cached descriptor"
                )
        return AuthorizedMaterializeRequest(
            request=request,
            stages=stages
            + (MaterializeStage.action_authorized, MaterializeStage.token_verified),
        )

    # ─────────────────────────────────────────────────────────────────
    # 6.2 flush：只创建 pending mutation，**不推进 revision**
    # ─────────────────────────────────────────────────────────────────

    async def create_pending_mutation(
        self, authorized: AuthorizedMaterializeRequest
    ) -> PendingMutationReceipt:
        """`POST .../pending-mutations` 的服务端 —— `flushHtml()` 的**唯一**落点。

        Requirement 3.1：flush 只「创建服务端 `pending_mutation`」。因此本方法：

        * 通过 :class:`RevisionLockedRepository` 访问仓储 ⇒ `bump_content_revision` /
          `create_content_version` / `set_current_content_version` **调用即抛**。
          这不是「我没写那三行」，是构造上碰不到（Property 4 同一机制）；
        * commit 前后各读一次 `working_paper.content_revision` 并断言相等 ⇒
          即便有人绕过门面走裸 SQL，行为判据也会红；
        * 幂等：同 `(wp, entry, user, Idempotency-Key)` 且 payload digest 与 expected
          revision 逐项相同 ⇒ 返回**同一个** token；payload 不同 ⇒ 409。

        入参必须来自 :meth:`authorize_create`（create 路径无 opaque resource 可查）。
        """
        authorized.assert_authorized()
        request = authorized.request
        locked = RevisionLockedRepository(self._repo)

        payload_bytes = _canonical_projection_bytes(request.projection)
        payload_digest = hashlib.sha256(payload_bytes).hexdigest()
        revision_before = await self._read_content_revision(request.wp_id)

        existing = await self._find_pending_mutation(
            wp_id=request.wp_id,
            entry_id=str(request.entry_id),
            user_id=request.user_id,
            idempotency_key=request.idempotency_key,
        )
        if existing is not None:
            self._assert_pending_row_matches(
                existing,
                request=request,
                payload_digest=payload_digest,
                where="flush-replay",
            )
            if PendingMutationState(existing.state) in (
                PendingMutationState.expired,
                PendingMutationState.invalidated,
            ):
                raise PendingTokenStateError(
                    f"pending mutation {existing.id} state={existing.state}，不可复用 —— "
                    "请重新 flush"
                )
            return self._receipt_of(existing, replayed=True)

        staged = self._artifacts.stage_bytes(
            project_id=request.project_id,
            wp_id=request.wp_id,
            payload=payload_bytes,
            document_type="json.gz",
            filename="pending-mutation.tmp",
        )
        published = self._artifacts.publish_projection(
            revision=int(request.expected_revision), staged=staged
        )
        artifact = await self._register_or_reuse_artifact(
            project_id=request.project_id,
            wp_id=request.wp_id,
            relative_path=published.relative_path,
            sha256=published.sha256,
            size_bytes=published.size_bytes,
        )
        row = await locked.create_pending_mutation(
            project_id=request.project_id,
            wp_id=request.wp_id,
            entry_id=str(request.entry_id),
            sheet_key=str(request.sheet_key),
            user_id=request.user_id,
            expected_revision=int(request.expected_revision),
            payload_artifact_id=artifact.id,
            payload_sha256=published.sha256,
            idempotency_key=request.idempotency_key,
            ttl=self._pending_ttl,
        )
        revision_after = await self._read_content_revision(request.wp_id)
        assert_flush_revision_neutral(revision_before, revision_after)
        await self._session.commit()
        return self._receipt_of(row, replayed=False)

    # ─────────────────────────────────────────────────────────────────
    # 6.3 preflight：Requirement 3.3 的 422 家族（零 operation / 零 room）
    # ─────────────────────────────────────────────────────────────────

    async def preflight(
        self, authorized: AuthorizedMaterializeRequest
    ) -> MaterializePreflight:
        """冻结 approved authority model + bundle id/digest/typed slots，或 422 拒绝。

        顺序即判据，**每一步都在下一步之前失败**，所以 error_code 总指向真正的第一个原因：

        1. capability —— `single_html` / `unreachable` 不得产出 OO artifact（AC 3.9 / 1.7）；
        2. canonical resolver（intent=`materialize`）—— 它已经拒绝 candidate id、
           unapproved bundle、digest 漂移、跨 scope、路径逃逸与文档类型不符；
        3. `assert_bundle_snapshot_finalizable` —— approved + 三 typed slot 形态 +
           `projection_contract` 的 contract slot 必须是 approved definition
           （不得用 typed null marker 冒充）；
        4. per-entry contract 对象 —— `projection_contract` 缺它即拒，
           **不得**按当前 alias 补齐；
        5. `RoomService.assert_representation_admissible` —— published/current +
           无未 finalize candidate + 无 bundle alias 漂移；
        6. substrate 准入 —— kind=canonical/state=published（candidate/incoming/
           quarantined 全部 fail closed）。

        前四步是**纯判据**（capability 声明 + resolver 结果 + bundle 形态 + 调用方是否
        给了 contract），第 5~6 步才读数据库。纯判据在前不是风格问题：调用方忘传
        contract 时，「缺 contract」比「representation 不可用」更接近真正的第一原因。

        🔴 第 3 与第 5 步看起来重叠，其实判的是两件事：第 3 步判 bundle **自身形态**，
        第 5 步判 bundle 与 **representation 行上冻结的 digest** 是否仍一致（alias 漂移）。
        删掉任何一步都有独立的定向变异能打红。
        """
        authorized.assert_authorized()
        request = authorized.request

        if request.capability in _NON_MATERIALIZABLE:
            raise EntryNotMaterializableError(
                f"entry {request.entry_id!r} 的 capability={request.capability.value} "
                "不得产出 OO artifact —— `single_html` 入口按定义没有 OO 侧内容"
                "（Requirement 3.9 禁止创建空白 OO artifact），`unreachable` 入口不该有"
                "任何业务写入（Requirement 1.7）"
            )

        try:
            resolution = await self._resolution.resolve(
                intent=ResolutionIntent.materialize,
                project_id=request.project_id,
                wp_id=request.wp_id,
                entry_id=str(request.entry_id),
                expected_document_type=request.document_type,
            )
        except EntryPointerMissingError as exc:
            raise SubstrateNotPublishedError(
                f"entry {request.entry_id!r} 还没有 published representation 可作 "
                f"materialize 的 substrate（{exc}）—— 首个 representation 只能由 "
                "Requirement 6.18 的版本化 template upgrader 经 candidate → approved "
                "bundle → finalize 产生"
            ) from exc
        except CandidateNotFinalizableError as exc:
            raise RepresentationStillCandidateError(
                f"entry {request.entry_id!r} 的解析目标仍是未 finalize 的 upgrade "
                f"candidate（{exc}）—— candidate 不得成为 resolver/room/current pointer "
                "的 substrate（Requirement 6.18 / Property 67）"
            ) from exc
        except BundleIntegrityError as exc:
            raise BundleNotApprovedError(
                f"entry {request.entry_id!r} 的 definition bundle 不可用（{exc}）—— "
                "unapproved bundle、非法空 typed slot 或 alias 漂移一律 422，"
                "不得按当前 alias 补齐"
            ) from exc

        bundle = resolution.bundle
        try:
            assert_bundle_snapshot_finalizable(bundle)
        except RepresentationSlotError as exc:
            raise BundleNotApprovedError(
                f"entry {request.entry_id!r} 的 bundle typed slot 形态非法（{exc}）"
            ) from exc
        except RepresentationBundleError as exc:
            raise BundleNotApprovedError(
                f"entry {request.entry_id!r} 的 bundle 不是 approved（{exc}）"
            ) from exc

        # per-entry contract 是**纯声明**判据（调用方给没给对象），放在任何数据库读取
        # **之前**：调用方忘传 contract 时，「缺 contract」比「representation 不可用」
        # 更接近真正的第一原因，也更可操作。
        if bundle.authority_model is AuthorityModel.projection_contract and (
            request.contract is None
        ):
            raise PerEntryContractMissingError(
                f"projection-based entry {request.entry_id!r} 缺 per-entry contract —— "
                "不得降级为 contract-less 模式，也不得按当前 alias 补齐"
                "（Requirement 3.3）"
            )

        representation = (
            await self._session.execute(
                sa.select(WorkpaperContentRepresentation).where(
                    WorkpaperContentRepresentation.id == resolution.representation_id
                )
            )
        ).scalar_one()
        try:
            bundle_identity = await self._rooms.assert_representation_admissible(
                representation
            )
        except RepresentationNotPublishedError as exc:
            raise RepresentationStillCandidateError(
                f"entry {request.entry_id!r} 的 representation 不可进入 active room"
                f"（{exc}）"
            ) from exc
        except BundleAliasDriftError as exc:
            raise BundleNotApprovedError(
                f"entry {request.entry_id!r} 的 bundle 在发布之后被 alias 换过内容"
                f"（{exc}）—— 历史读取不得按当前 registry alias 重组 bundle（AC 2.10）"
            ) from exc

        substrate = (
            await self._session.execute(
                sa.select(WorkpaperArtifact).where(
                    WorkpaperArtifact.id == resolution.artifact_id
                )
            )
        ).scalar_one_or_none()
        if substrate is None:
            raise SubstrateNotPublishedError(
                f"substrate artifact {resolution.artifact_id} 行不存在"
            )
        assert_substrate_usable(
            role=SubstrateRole.published_representation,
            artifact_kind=str(substrate.kind),
            artifact_state=str(substrate.state),
        )

        return MaterializePreflight(
            resolution=resolution,
            bundle=bundle,
            bundle_identity=bundle_identity,
            substrate_path=resolution.artifact_path,
            substrate_sha256=resolution.artifact_sha256,
            base_content_version_id=resolution.content_version_id,
            base_revision=int(resolution.content_revision),
            capability=request.capability,
        )

    # ─────────────────────────────────────────────────────────────────
    # 6.4 materialize：三段事务
    # ─────────────────────────────────────────────────────────────────

    async def materialize(
        self, authorized: AuthorizedMaterializeRequest
    ) -> MaterializeOutcome:
        """HTML→OO 的唯一编排（Requirement 3.1~3.9）。

        ```
        ① authorize（调用方已完成，类型强制）
        ② token 逐项校验（scope / TTL / digest / expected revision / Idempotency-Key）
        ③ preflight（bundle/authority model/contract/candidate/substrate → 422）
        ④ 已 committed ⇒ 重放：返回既有 operation/version/representation，revision 不动
        ⑤ 业务身份相同 ⇒ 幂等复用既有 version/representation，revision 不动（AC 3.6）
        ⑥ 事务 A：开 operation（冻结 bundle identity）并提交 —— 此后失败也有终态可查
        ⑦ 事务 B：ContentMutationService.commit(...) —— 唯一业务事务、恰一次 revision
        ⑧ 事务 C：终态记账 + room/participant + descriptor
        ```

        `revision_delta` 由 ⑥ 之前与 ⑧ 之后各读一次 `working_paper.content_revision`
        算得，并在返回前断言：commit 路径恰为 1、重放/复用路径恰为 0。这是「禁止两次
        revision」的**行为**判据（不看调用次数、不看源码）。
        """
        authorized.assert_token_verified()
        request = authorized.request

        # token 已在 `authorize()` 里验签并逐项比对过；这里只取回载荷（纯内存）。
        token = self._tokens.decode(request.pending_mutation_token)
        pending = await self._load_pending_mutation_for_token(token, request)
        pre = await self.preflight(authorized)
        checked = authorized.with_stage(MaterializeStage.preflight_passed)

        revision_before = await self._read_content_revision(request.wp_id)
        rooms_before = await self._count_rooms(request.wp_id, str(request.entry_id))

        if PendingMutationState(pending.state) is PendingMutationState.committed:
            outcome = await self._replay_committed(checked, pending=pending, pre=pre)
        else:
            reuse = await self._find_business_identity_reuse(
                request=request, pre=pre, payload_sha256=token.payload_sha256
            )
            operation = await self._open_operation(request=request, pre=pre)
            if reuse is not None:
                outcome = await self._settle_reuse(
                    checked,
                    pending=pending,
                    pre=pre,
                    operation_id=operation.id,
                    version=reuse[0],
                    representation=reuse[1],
                )
            else:
                outcome = await self._commit_and_settle(
                    checked, pending=pending, pre=pre, operation_id=operation.id
                )

        revision_after = await self._read_content_revision(request.wp_id)
        rooms_after = await self._count_rooms(request.wp_id, str(request.entry_id))
        delta = revision_after - revision_before
        assert_revision_delta(
            delta=delta,
            replayed=outcome.replayed,
            business_identity_reused=outcome.business_identity_reused,
        )
        return MaterializeOutcome(
            descriptor=outcome.descriptor,
            operation_id=outcome.operation_id,
            content_version_id=outcome.content_version_id,
            revision=outcome.revision,
            representation_id=outcome.representation_id,
            representation_generation=outcome.representation_generation,
            replayed=outcome.replayed,
            business_identity_reused=outcome.business_identity_reused,
            commit_count=outcome.commit_count,
            transaction_ids=outcome.transaction_ids,
            rooms_opened=max(0, rooms_after - rooms_before),
            revision_delta=delta,
            receipt=outcome.receipt,
        )

    # ─────────────────────────────────────────────────────────────────
    # 6.5 三条终结路径
    # ─────────────────────────────────────────────────────────────────

    async def _commit_and_settle(
        self,
        authorized: AuthorizedMaterializeRequest,
        *,
        pending: WorkpaperPendingMutation,
        pre: MaterializePreflight,
        operation_id: uuid.UUID,
    ) -> MaterializeOutcome:
        """事务 B + C：唯一业务 commit，然后 room/participant/descriptor。"""
        request = authorized.request
        plan = ContentCommitPlan(
            project_id=request.project_id,
            wp_id=request.wp_id,
            entry_id=str(request.entry_id),
            source=HTML,
            expected_revision=int(pre.base_revision),
            bundle=pre.bundle,
            adapter_id=(request.adapter_id or pre.resolution.adapter_id),
            adapter_build_digest=(
                request.adapter_build_digest or pre.resolution.adapter_build_digest
            ),
            document_type=pre.resolution.document_type,
            substrate_path=pre.substrate_path,
            substrate_role=SubstrateRole.published_representation,
            substrate_kind=ArtifactKind.canonical,
            substrate_state=ArtifactState.published,
            actor_id=request.user_id,
            operation_id=operation_id,
            parent_version_id=pre.base_content_version_id,
            contract=request.contract,
            pending_mutation_id=pending.id,
            idempotency_key=request.idempotency_key,
            reason="content_commit",
        )
        try:
            self.commits_invoked += 1
            receipt = await self._mutations.commit(
                plan=plan,
                mutation=BusinessMutation(projection=request.projection),
                adapter=request.adapter,
            )
        except Exception as exc:  # noqa: BLE001 - 记终态后原样抛出，绝不降级
            await self._fail_operation(operation_id, exc, stage="content_commit")
            raise
        try:
            assert_single_business_commit(
                commit_count=receipt.commit_count,
                transaction_ids=receipt.transaction_ids,
            )
            assert_revision_target(
                actual=receipt.revision, base_revision=pre.base_revision
            )
        except MaterializeCoordinatorError as exc:
            await self._fail_operation(operation_id, exc, stage="commit_accounting")
            raise
        try:
            descriptor = await self._open_room_and_descriptor(
                authorized,
                pre=pre,
                operation_id=operation_id,
                content_version_id=receipt.content_version_id,
                revision=receipt.revision,
                representation_id=receipt.representation_id,
                representation_generation=receipt.representation_generation,
                artifact_sha256=receipt.artifact_sha256,
            )
        except Exception as exc:  # noqa: BLE001
            await self._fail_operation(operation_id, exc, stage="room_open")
            raise
        await self._apply_operation(operation_id, room_id=descriptor.room_id)
        return MaterializeOutcome(
            descriptor=descriptor,
            operation_id=operation_id,
            content_version_id=receipt.content_version_id,
            revision=receipt.revision,
            representation_id=receipt.representation_id,
            representation_generation=receipt.representation_generation,
            replayed=False,
            business_identity_reused=False,
            commit_count=receipt.commit_count,
            transaction_ids=receipt.transaction_ids,
            rooms_opened=0,  # 由 materialize() 用真实行数差覆盖
            revision_delta=0,
            receipt=receipt,
        )

    async def _replay_committed(
        self,
        authorized: AuthorizedMaterializeRequest,
        *,
        pending: WorkpaperPendingMutation,
        pre: MaterializePreflight,
    ) -> MaterializeOutcome:
        """同 token 重放：返回既有 operation/content version/representation。

        Requirement 3.1 / Property 10：「失败重试返回同 operation，成功后重放返回既有
        结果」。授权已在 :meth:`authorize` 与 :meth:`preflight` 里重验过 —— 于是
        「撤权后不得泄露 cached descriptor」有落点：撤权时 `authorize` 抛 403，
        本方法根本到不了。
        """
        request = authorized.request
        version_id = pending.result_content_version_id
        operation_id = pending.result_operation_id
        if version_id is None or operation_id is None:
            raise PendingTokenStateError(
                f"pending mutation {pending.id} 标记 committed 但缺 result "
                f"(operation={operation_id}, content_version={version_id}) —— "
                "这正是「projection-only commit」留下的半成功态"
            )
        version = (
            await self._session.execute(
                sa.select(WorkpaperContentVersion).where(
                    WorkpaperContentVersion.id == version_id
                )
            )
        ).scalar_one()
        representation = await self._latest_representation(
            wp_id=request.wp_id, entry_id=str(request.entry_id), version_id=version_id
        )
        # 🔴 重放只有在**世界没变**时才算成功：pending mutation 记下的 result
        #    representation 必须仍是 preflight 解析到的 published 代际。此后又发生过
        #    别的 commit 或 definition finalize 时，那份 identity 已被取代 ——
        #    此时把它照原样下发就等于挂载一个陈旧 descriptor（Task 25 正文明确要求
        #    「仅当前 …/generation/…/bundle 仍有效时成功重放才返回同 …representation」）。
        if representation.id != pre.resolution.representation_id:
            raise DescriptorSubstrateStaleError(
                f"{STALE_ON_REPLAY_MARKER}: pending mutation {pending.id} 记录的 "
                f"representation {representation.id} 已不是 entry {request.entry_id!r} 的 "
                f"published 代际（current={pre.resolution.representation_id}）—— "
                "重放不得下发陈旧 descriptor，请重新 flush"
            )
        descriptor = await self._open_room_and_descriptor(
            authorized,
            pre=pre,
            operation_id=operation_id,
            content_version_id=version.id,
            revision=int(version.revision),
            representation_id=representation.id,
            representation_generation=int(representation.generation),
            artifact_sha256=str(representation.artifact_sha256),
        )
        return MaterializeOutcome(
            descriptor=descriptor,
            operation_id=operation_id,
            content_version_id=version.id,
            revision=int(version.revision),
            representation_id=representation.id,
            representation_generation=int(representation.generation),
            replayed=True,
            business_identity_reused=False,
            commit_count=0,
            transaction_ids=(),
            rooms_opened=0,
            revision_delta=0,
            receipt=None,
        )

    async def _settle_reuse(
        self,
        authorized: AuthorizedMaterializeRequest,
        *,
        pending: WorkpaperPendingMutation,
        pre: MaterializePreflight,
        operation_id: uuid.UUID,
        version: WorkpaperContentVersion,
        representation: WorkpaperContentRepresentation,
    ) -> MaterializeOutcome:
        """AC 3.6 的第二条幂等路径：不同 token、相同业务身份 ⇒ 复用，零 revision。

        pending row 仍要落 `committed` 并指向被复用的 version —— 否则同一个 token 再来
        一次又会走一遍「查复用」，而 `ck_wppm_committed_result` 也要求 committed 行必须
        留下可重放的 (operation, content version) 对。
        """
        assert_transition(
            "pending_mutation", PendingMutationState(pending.state),
            PendingMutationState.committing,
        )
        pending.state = PendingMutationState.committing.value
        await self._session.flush()
        assert_transition(
            "pending_mutation", PendingMutationState.committing,
            PendingMutationState.committed,
        )
        pending.state = PendingMutationState.committed.value
        pending.result_operation_id = operation_id
        pending.result_content_version_id = version.id
        pending.committed_at = _now()
        await self._session.flush()
        await self._session.commit()

        descriptor = await self._open_room_and_descriptor(
            authorized,
            pre=pre,
            operation_id=operation_id,
            content_version_id=version.id,
            revision=int(version.revision),
            representation_id=representation.id,
            representation_generation=int(representation.generation),
            artifact_sha256=str(representation.artifact_sha256),
        )
        await self._apply_operation(
            operation_id, room_id=descriptor.room_id, stage="business_identity_reused"
        )
        return MaterializeOutcome(
            descriptor=descriptor,
            operation_id=operation_id,
            content_version_id=version.id,
            revision=int(version.revision),
            representation_id=representation.id,
            representation_generation=int(representation.generation),
            replayed=False,
            business_identity_reused=True,
            commit_count=0,
            transaction_ids=(),
            rooms_opened=0,
            revision_delta=0,
            receipt=None,
        )

    # ─────────────────────────────────────────────────────────────────
    # 6.6 operation 生命周期（Requirement 3.8：任一失败都有终态）
    # ─────────────────────────────────────────────────────────────────

    async def _open_operation(
        self, *, request: MaterializeRequest, pre: MaterializePreflight
    ) -> WorkpaperSyncOperation:
        """事务 A：冻结 approved bundle/authority model 的 `html_to_oo` operation shell。

        **独立提交**。理由见模块文档 §二：Task 15 的 `commit()` 在任何异常上 rollback，
        operation 与业务内容同事务就会一起消失，用户只剩一个 5xx。

        `room_id` 此刻必为 NULL（room 在 commit 成功后才开）—— 那正是
        Requirement 3.2「commit 未成功 ⇒ room 创建次数为 0」的记账形态。
        `application_id` / `duplicate_of_operation_id` 也必为 NULL：HTML→OO 方向没有
        incoming artifact，永远不产生 content application（Property 64）。
        """
        op = WorkpaperSyncOperation(
            id=uuid.uuid4(),
            project_id=request.project_id,
            wp_id=request.wp_id,
            entry_id=str(request.entry_id),
            room_id=None,
            forcesave_request_id=None,
            application_id=None,
            duplicate_of_operation_id=None,
            initiated_by_participant_id=None,
            direction=OperationDirection.html_to_oo.value,
            state=OperationState.created.value,
            definition_bundle_id=pre.bundle.bundle_id,
            definition_bundle_sha256=pre.bundle.bundle_sha256,
            authority_model_definition_id=pre.bundle.authority_model_definition_id,
            authority_model_definition_sha256=pre.bundle.authority_model_definition_sha256,
            created_by=request.user_id,
        )
        self._session.add(op)
        await self._session.flush()
        await self._repo.register_scope(
            resource_kind=ScopeResourceKind.sync_operation,
            resource_id=str(op.id),
            project_id=request.project_id,
            wp_id=request.wp_id,
            entry_id=str(request.entry_id),
        )
        await self._repo.append_operation_event(
            operation_id=op.id,
            from_state=None,
            to_state=OperationState.created,
            stage="materialize_frozen",
            actor_type=ActorType.user,
            actor_id=request.user_id,
            detail_digest=canonical_digest(
                {
                    "bundle": pre.bundle.bundle_sha256,
                    "authority_model": pre.bundle.authority_model.value,
                    "typed_slots": [list(item) for item in pre.typed_slot_inventory],
                    "base_revision": int(pre.base_revision),
                    "substrate_sha256": pre.substrate_sha256,
                }
            ),
        )
        await self._session.commit()
        return op

    async def _apply_operation(
        self,
        operation_id: uuid.UUID,
        *,
        room_id: uuid.UUID,
        stage: str = "descriptor_issued",
    ) -> None:
        """终态 `applied` + append-only event（先写 event，再投影 current state）。"""
        op = await self._load_operation(operation_id)
        await self._repo.append_operation_event(
            operation_id=operation_id,
            from_state=OperationState(op.state),
            to_state=OperationState.applied,
            stage=stage,
            actor_type=ActorType.system,
        )
        op.state = OperationState.applied.value
        op.room_id = room_id
        op.finished_at = _now()
        await self._session.flush()
        await self._session.commit()

    async def _fail_operation(
        self, operation_id: uuid.UUID, exc: BaseException, *, stage: str
    ) -> None:
        """终态 `error` + append-only event。**绝不**吞掉原异常。

        🔴 这里的 `except Exception` 只包住「记账本身」，且失败时 rollback 后原样返回，
        让调用点把**原始**异常抛出去。记账失败不得把内容失败改写成成功，也不得把
        原因换成「记账挂了」—— 那正是 fail-open 掩盖接线错误的形态。
        """
        code = str(getattr(exc, "error_code", "") or type(exc).__name__)[:60]
        try:
            await self._session.rollback()
            op = await self._load_operation(operation_id)
            current = OperationState(op.state)
            if current in (
                OperationState.error,
                OperationState.rejected,
                OperationState.applied,
            ):
                return
            await self._repo.append_operation_event(
                operation_id=operation_id,
                from_state=current,
                to_state=OperationState.error,
                stage=stage,
                actor_type=ActorType.system,
                error_code=code,
            )
            op.state = OperationState.error.value
            op.error_code = code
            op.error_stage = stage[:40]
            op.error_detail = f"{type(exc).__name__}: {exc}"[:4000]
            op.finished_at = _now()
            await self._session.flush()
            await self._session.commit()
        except Exception:  # noqa: BLE001 - 记账失败不得改写内容失败的成因
            await self._session.rollback()

    # ─────────────────────────────────────────────────────────────────
    # 6.7 room / participant / descriptor
    # ─────────────────────────────────────────────────────────────────

    async def _open_room_and_descriptor(
        self,
        authorized: AuthorizedMaterializeRequest,
        *,
        pre: MaterializePreflight,
        operation_id: uuid.UUID,
        content_version_id: uuid.UUID,
        revision: int,
        representation_id: uuid.UUID,
        representation_generation: int,
        artifact_sha256: str,
    ) -> EditorLaunchDescriptor:
        """事务 C：开/复用 room + participant lease，然后组装**唯一** descriptor。

        room 与 participant 全部委派 Task 21（doc_key 派生、published/candidate/alias 三门、
        lease token hash 都在那里）。本方法只负责：把 descriptor 的每个字段从**冻结的**
        preflight 与刚发布的 representation 上取出来，然后交给
        :class:`EditorLaunchDescriptor` 的构造期判据。
        """
        request = authorized.request
        representation = (
            await self._session.execute(
                sa.select(WorkpaperContentRepresentation).where(
                    WorkpaperContentRepresentation.id == representation_id
                )
            )
        ).scalar_one()
        try:
            room, room_bundle = await self._rooms.open_or_reuse_room(
                request.scope,
                representation=representation,
                opened_base_version_id=content_version_id,
                ttl=self._room_ttl,
            )
        except (RepresentationNotPublishedError, BundleAliasDriftError) as exc:
            # preflight 通过之后、开 room 之前，entry pointer 或 bundle alias 被并发推进。
            # 不得让 `RoomPolicyError` 原样漏出去（router 会记成 500）—— 它是一个明确的
            # 409：substrate 已过期，请重新 flush。
            raise DescriptorSubstrateStaleError(
                f"{STALE_ON_ROOM_OPEN_MARKER}: 开 room 时 representation "
                f"{representation.id} 已不可用（{exc}）—— preflight 与 room 打开之间"
                "发生了并发推进，请重新 flush"
            ) from exc
        # 冻结 identity 与 room 侧现算身份逐项比对：不等即 alias 漂移（AC 2.10）。
        pre.bundle_identity.assert_same_as(room_bundle, where="materialize-room")
        participant = await self._join_or_reuse_participant(request, room=room)
        await self._session.commit()

        descriptor = EditorLaunchDescriptor(
            operation_id=operation_id,
            room_id=room.id,
            participant_id=participant.id,
            doc_key=str(room.doc_key),
            generation=int(room.generation),
            server_applied_revision=int(revision),
            client_confirmed_base_revision=await self._revision_of(
                room.client_confirmed_base_version_id
            ),
            content_version_id=content_version_id,
            representation_id=representation_id,
            representation_generation=int(representation_generation),
            artifact_sha256=str(artifact_sha256),
            write_fence_epoch=int(room.write_fence_epoch),
            authority_model=pre.bundle.authority_model.value,
            authority_model_definition_sha256=(
                pre.bundle.authority_model_definition_sha256
            ),
            definition_bundle_id=pre.bundle.bundle_id,
            definition_bundle_sha256=pre.bundle.bundle_sha256,
            definition_bundle_slots=pre.descriptor_slots(),
            document_type=str(representation.document_type),
            mode="edit",
            onlyoffice_config=self._onlyoffice_config(
                room=room,
                representation=representation,
                document_type=str(representation.document_type),
            ),
        )
        self.descriptors_issued += 1
        return descriptor

    async def _join_or_reuse_participant(
        self, request: MaterializeRequest, *, room: WorkpaperOoRoom
    ) -> WorkpaperOoParticipant:
        """同 `(room, user)` 已有未终结 lease 时复用它，否则新建。

        🔴 这不是「容错」，是 V151 的 `uq_wpoop_active_lease`
        （`(room_id, user_id) WHERE state IN ('active','closing')`）定义的语义：
        **一个用户在一个 room 里只有一个 lease**。无条件 `join_participant` 会让
        「同 token 重放」「相同业务身份复用」「同一用户第二次切到 OO」三条完全正常的
        路径撞唯一约束 —— 表现为莫名 500，而 AC 3.6 明确要求这三条都幂等成功。

        复用前必须比对 fence：lease 记录的 `joined_write_fence_epoch` 与 room 当前
        `write_fence_epoch` 不等意味着期间有 participant 被撤销（AC 2.8），旧会话
        必须重开 —— 这与 `RoomService.assert_can_initiate_request` 的第 ④ 条同判据，
        在这里就拒，而不是等到 forcesave 才发现。
        """
        live = (
            await self._session.execute(
                sa.select(WorkpaperOoParticipant)
                .where(
                    WorkpaperOoParticipant.room_id == room.id,
                    WorkpaperOoParticipant.user_id == request.user_id,
                    WorkpaperOoParticipant.state.in_(("active", "closing")),
                )
                .with_for_update()
            )
        ).scalars().first()
        if live is None:
            return await self._rooms.join_participant(
                request.scope,
                room_id=room.id,
                user_id=request.user_id,
                mode="edit",
                permission_epoch=int(request.permission_epoch),
                lease_token=(request.lease_token or uuid.uuid4().hex),
            )
        if int(live.joined_write_fence_epoch) != int(room.write_fence_epoch):
            raise MaterializeAuthorizationError(
                f"participant {live.id} 加入时 fence={live.joined_write_fence_epoch}，"
                f"room 当前 fence={room.write_fence_epoch} —— 期间有 participant 被撤销或 "
                "generation 被旋转，旧会话必须重开（AC 2.8 / 4.7）"
            )
        if live.revoked_at is not None or (
            live.expires_at is not None and live.expires_at <= _now()
        ):
            raise MaterializeAuthorizationError(
                f"participant {live.id} 的 lease 已撤销/过期 —— 不得复用，也不得在唯一"
                "约束下新建第二个；必须先由 room 侧终结该 lease"
            )
        return live

    def _onlyoffice_config(
        self,
        *,
        room: WorkpaperOoRoom,
        representation: WorkpaperContentRepresentation,
        document_type: str,
    ) -> dict[str, Any]:
        """descriptor 内嵌的 OO config —— 编辑器的**唯一** config 来源。

        刻意不含下载 URL 的签名：URL 签名有独立 TTL，放进 descriptor 会让 descriptor 的
        有效期被签名 TTL 绑住。`document.url` 由 Task 28 的 router 在响应时补签
        （descriptor 提供 `key/title/fileType` 这些**不随签名变化**的部分）。
        """
        return {
            "document": {
                "key": str(room.doc_key),
                "fileType": document_type,
                "title": f"{representation.entry_id}.{document_type}",
                "permissions": {"edit": True, "download": True},
            },
            "documentType": "cell" if document_type == "xlsx" else "word",
            "editorConfig": {
                "mode": "edit",
                "customization": {
                    # 🔴 `forcesave` 必须为 false：AC 4.1 明确「不得把
                    # `customization.forcesave=true` 当成保存完成」。平台的 forcesave 由
                    # 后端 Command Service 发起并等 durable ack（Task 23/24），
                    # 编辑器侧的自动 forcesave 只会产生无 request 的孤儿 callback。
                    "forcesave": False,
                },
            },
            "generation": int(room.generation),
            "write_fence_epoch": int(room.write_fence_epoch),
        }

    # ─────────────────────────────────────────────────────────────────
    # 6.8 ready 之后的服务端确认（Property 11 后半）
    # ─────────────────────────────────────────────────────────────────

    async def confirm_descriptor(
        self,
        authorized: AuthorizedMaterializeRequest,
        *,
        room_id: uuid.UUID,
        participant_id: uuid.UUID,
        echoed: Mapping[str, Any],
        idempotency_key: str,
    ) -> DescriptorConfirmation:
        """`onDocumentReady` 之后的幂等确认。确认成功前 room 不 active、不得 forcesave。

        `echoed` 是前端逐项回传的 :meth:`EditorLaunchDescriptor.confirm_payload`。
        十项**全部**参与比对；任一不等即 409（:class:`DescriptorStaleIdentityError`），
        因为「篡改」与「陈旧」在协议上是同一处理：都不许进入 editing/forcesave。

        room/lease/bundle 的实际校验委派 Task 21 的 `RoomService.confirm_descriptor`
        （它锁 room、验 lease、比对 bundle identity 并原子推进 client-confirmed 基线，
        `opening → active` 也在那里）。本方法只做「回传值 vs 服务端事实」的逐项比对。
        """
        authorized.assert_authorized()
        request = authorized.request

        # authorization-before-resource：**先**只查非敏感 scope index，再锁业务行。
        # 反过来（先 lock_room 再比 scope）等于用业务行反推归属 —— AC 10.5 明令禁止，
        # 而且会让「room 不存在」与「room 属于别人」暴露成两种不同时序。
        scope_row = await self._repo.resolve_scope(
            resource_kind=ScopeResourceKind.room, resource_id=str(room_id)
        )
        if (
            scope_row is None
            or scope_row.project_id != request.project_id
            or scope_row.wp_id != request.wp_id
            or str(scope_row.entry_id) != str(request.entry_id)
        ):
            raise MaterializeScopeNotVisibleError(
                f"room {room_id} 在 scope index 中不可见或与显式声明的 project/wp/entry "
                "不符 —— 同 404 语义"
            )
        room = await self._repo.lock_room(room_id)
        state_before = RoomState(room.state)
        representation_id = _uuid_of(echoed, "representation_id")
        representation = (
            await self._session.execute(
                sa.select(WorkpaperContentRepresentation).where(
                    WorkpaperContentRepresentation.id == representation_id
                )
            )
        ).scalar_one_or_none()
        if representation is None:
            raise DescriptorStaleIdentityError(
                f"confirm-descriptor 回传的 representation {representation_id} 不存在"
            )
        try:
            bundle_identity = await self._rooms.assert_representation_admissible(
                representation
            )
        except (RepresentationNotPublishedError, BundleAliasDriftError) as exc:
            raise DescriptorStaleIdentityError(
                f"confirm-descriptor 回传的 representation 已不是 entry 的 published "
                f"代际或 bundle 已漂移（{exc}）—— candidate/陈旧 descriptor 必须 409"
            ) from exc

        for key, actual in (
            ("participant_id", str(participant_id)),
            ("generation", int(room.generation)),
            ("doc_key", str(room.doc_key)),
            ("artifact_sha256", str(representation.artifact_sha256)),
            ("write_fence_epoch", int(room.write_fence_epoch)),
            (
                "authority_model_definition_sha256",
                bundle_identity.authority_model_definition_sha256,
            ),
            ("definition_bundle_id", str(bundle_identity.definition_bundle_id)),
            ("definition_bundle_sha256", bundle_identity.definition_bundle_sha256),
        ):
            if key not in echoed:
                raise DescriptorStaleIdentityError(
                    f"confirm-descriptor 回传缺字段 {key!r} —— 十项 identity 必须逐项回传"
                )
            echoed_value = echoed[key]
            same = (
                int(echoed_value) == actual
                if isinstance(actual, int)
                else str(echoed_value) == actual
            )
            if not same:
                raise DescriptorStaleIdentityError(
                    f"confirm-descriptor 的 {key}={echoed_value!r} 与服务端事实 "
                    f"{actual!r} 不符 —— 篡改或陈旧 generation/representation/bundle/fence "
                    "一律 409，不得进入 editing/forcesave（AC 3.7）"
                )
        content_version_id = representation.content_version_id
        echoed_revision = echoed.get("content_revision")
        actual_revision = await self._revision_of(content_version_id)
        if echoed_revision is None or int(echoed_revision) != int(actual_revision or -1):
            raise DescriptorStaleIdentityError(
                f"confirm-descriptor 的 content_revision={echoed_revision!r} 与 "
                f"representation 所属 content version 的 revision={actual_revision!r} 不符"
            )

        version = (
            await self._session.execute(
                sa.select(WorkpaperContentVersion).where(
                    WorkpaperContentVersion.id == content_version_id
                )
            )
        ).scalar_one()
        confirmation, room = await self._rooms.confirm_descriptor(
            request.scope,
            room_id=room_id,
            participant_id=participant_id,
            representation_id=representation_id,
            content_version_id=content_version_id,
            projection_sha256=str(version.projection_sha256 or representation.artifact_sha256),
            idempotency_key=idempotency_key,
            expected_bundle=bundle_identity,
        )
        await self._session.commit()
        return DescriptorConfirmation(
            confirmation_id=confirmation.id,
            room_id=room_id,
            participant_id=participant_id,
            generation=int(room.generation),
            representation_id=representation_id,
            content_version_id=content_version_id,
            room_state=str(room.state),
            replayed=state_before is RoomState.active,
            forcesave_unlocked=RoomState(room.state) is RoomState.active,
        )

    # ─────────────────────────────────────────────────────────────────
    # 6.9 definitions-only 升级：唯一出口是 Task 15 的 finalize（Property 67）
    # ─────────────────────────────────────────────────────────────────

    async def finalize_definition_upgrade(
        self, **kwargs: Any
    ) -> RepresentationFinalizeOutcome:
        """把纯定义升级委派 `RepresentationService.finalize_candidate`，并断言 revision 不变。

        Requirement 3.6 后半 / 6.18 / Property 67：只有隐形载体升级时按
        `template → instrumentation → contract → bundle → representation` finalize
        **新 representation generation**，而 `content_revision` **不变**。

        本方法刻意只做三件事 —— 委派、断言、不多写一行：`RepresentationService` 构造时
        被 `RevisionLockedRepository` 包住，拿不到 revision 域写入面，所以「纯定义升级
        递增 business revision」在构造上不可能；这里的断言是它的**行为**复核，
        两者少任何一个都留缺口。
        """
        if self._representations is None:
            raise MaterializeCoordinatorError(
                "coordinator 未装配 RepresentationService —— definitions-only 升级不得由"
                " materialize 路径顺手发布 representation（Property 67）"
            )
        outcome = await self._representations.finalize_candidate(**kwargs)
        if not outcome.revision_unchanged:
            raise DefinitionUpgradeRevisionError(
                f"candidate finalize 改动了 business revision"
                f"（{outcome.content_revision_before} → {outcome.content_revision_after}）"
                " —— 纯 definitions/representation 升级不得推进 content revision"
                "（Requirement 3.6 / Property 67）"
            )
        return outcome

    # ─────────────────────────────────────────────────────────────────
    # 6.10 私有：token / pending row / 幂等复用 / 计数
    # ─────────────────────────────────────────────────────────────────

    def _assert_token_matches_request(
        self, token: PendingMutationTokenPayload, request: MaterializeRequest
    ) -> None:
        """token 与本次请求逐项比对。**五类拒绝各一个异常类型**（Property 10 逐条点名）。

        顺序刻意是 scope → Idempotency-Key → TTL → expected revision → payload digest：
        scope 不符时不该继续泄露「这个 token 的 TTL 还剩多久」之类信息。
        """
        if (
            token.project_id != request.project_id
            or token.wp_id != request.wp_id
            or str(token.entry_id) != str(request.entry_id)
            or str(token.sheet_key) != str(request.sheet_key)
            or token.user_id != request.user_id
        ):
            raise PendingTokenScopeError(
                f"pending mutation token 属于 scope ({token.project_id}/{token.wp_id}/"
                f"{token.entry_id}/{token.sheet_key}/user={token.user_id})，与本次 "
                f"materialize ({request.project_id}/{request.wp_id}/{request.entry_id}/"
                f"{request.sheet_key}/user={request.user_id}) 不同 —— token 跨 "
                "project/wp/entry/sheet/user 一律拒绝"
            )
        if token.idempotency_key != request.idempotency_key:
            raise IdempotencyKeyMismatchError(
                f"token 冻结的 Idempotency-Key={token.idempotency_key!r} 与请求头的 "
                f"{request.idempotency_key!r} 不同 —— 两者必须同源，否则「同 key + 同 "
                "payload 才返回同结果」的语义不成立"
            )
        if token.expires_at <= _now():
            raise PendingTokenExpiredError(
                f"pending mutation token 已过期（expires_at="
                f"{token.expires_at.isoformat()}）—— 过期 token 不得被消费，请重新 flush"
            )
        if int(token.expected_revision) != int(request.expected_revision):
            raise PendingTokenRevisionError(
                f"token 冻结 expected_revision={token.expected_revision}，请求声明 "
                f"{request.expected_revision} —— 同 Idempotency-Key 不同 content base "
                "必须拒绝"
            )
        actual = hashlib.sha256(
            _canonical_projection_bytes(request.projection)
        ).hexdigest()
        if actual != token.payload_sha256:
            raise PendingTokenPayloadError(
                f"token 冻结 payload digest={token.payload_sha256}，本次请求的 projection "
                f"digest={actual} —— 同 Idempotency-Key 不同 payload 必须拒绝"
                "（flush 之后又改了内容，请重新 flush）"
            )

    async def _load_pending_mutation_for_token(
        self, token: PendingMutationTokenPayload, request: MaterializeRequest
    ) -> WorkpaperPendingMutation:
        """按 token 里的 id 取行并**再**逐项比对 —— 数据库行才是 TTL/state 的权威。

        为什么 token 校验过了还要比一遍：token 是签名快照，行是可变状态。
        TTL 可能在签发后被 invalidate（Task 21 的 revoke 路径）、payload artifact 可能被
        retention 清掉。只信 token 就等于把「单次逻辑消费」建在客户端持有的字节上。
        """
        row = (
            await self._session.execute(
                sa.select(WorkpaperPendingMutation)
                .where(WorkpaperPendingMutation.id == token.pending_mutation_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            raise PendingTokenStateError(
                f"pending mutation {token.pending_mutation_id} 不存在（已消费清理或从未创建）"
            )
        self._assert_pending_row_matches(
            row,
            request=request,
            payload_digest=token.payload_sha256,
            where="materialize",
        )
        state = PendingMutationState(row.state)
        if state in (PendingMutationState.expired, PendingMutationState.invalidated):
            raise PendingTokenStateError(
                f"pending mutation {row.id} state={state.value}，不可消费 —— 请重新 flush"
            )
        if row.expires_at <= _now() and state is not PendingMutationState.committed:
            raise PendingTokenExpiredError(
                f"pending mutation {row.id} 已过 TTL（expires_at="
                f"{row.expires_at.isoformat()}）—— 数据库行才是 TTL 权威"
            )
        if state not in _CONSUMABLE_PENDING_STATES and (
            state is not PendingMutationState.committed
        ):
            raise PendingTokenStateError(
                f"pending mutation {row.id} state={state.value} 不在可消费集合 "
                f"{sorted(s.value for s in _CONSUMABLE_PENDING_STATES)} 内"
            )
        return row

    def _assert_pending_row_matches(
        self,
        row: WorkpaperPendingMutation,
        *,
        request: MaterializeRequest,
        payload_digest: str,
        where: str,
    ) -> None:
        """pending row 的 scope / expected revision / payload digest 三条逐项比对。"""
        if (
            row.project_id != request.project_id
            or row.wp_id != request.wp_id
            or str(row.entry_id) != str(request.entry_id)
            or str(row.sheet_key) != str(request.sheet_key)
            or row.user_id != request.user_id
        ):
            raise PendingTokenScopeError(
                f"{where}: pending mutation {row.id} 属于 scope ({row.project_id}/"
                f"{row.wp_id}/{row.entry_id}/{row.sheet_key}/user={row.user_id})，"
                "与本次请求不同"
            )
        if int(row.expected_revision) != int(request.expected_revision):
            raise PendingTokenRevisionError(
                f"{where}: pending mutation {row.id} 冻结 expected_revision="
                f"{row.expected_revision}，请求声明 {request.expected_revision}"
            )
        if str(row.payload_sha256) != str(payload_digest):
            raise PendingTokenPayloadError(
                f"{where}: pending mutation {row.id} 的 payload digest="
                f"{row.payload_sha256} 与本次 {payload_digest} 不同"
            )

    async def _find_pending_mutation(
        self, *, wp_id: uuid.UUID, entry_id: str, user_id: uuid.UUID, idempotency_key: str
    ) -> WorkpaperPendingMutation | None:
        return (
            await self._session.execute(
                sa.select(WorkpaperPendingMutation).where(
                    WorkpaperPendingMutation.wp_id == wp_id,
                    WorkpaperPendingMutation.entry_id == entry_id,
                    WorkpaperPendingMutation.user_id == user_id,
                    WorkpaperPendingMutation.idempotency_key == idempotency_key,
                )
            )
        ).scalars().first()

    async def _find_business_identity_reuse(
        self,
        *,
        request: MaterializeRequest,
        pre: MaterializePreflight,
        payload_sha256: str,
    ) -> tuple[WorkpaperContentVersion, WorkpaperContentRepresentation] | None:
        """AC 3.6 第一句的判据：business projection + bundle + substrate 三者全同即复用。

        三元组逐项对应 AC 原文，比较对象都是**当前状态**（preflight 冻结的那一份）：

        * **business projection** —— 当前 content version 的 `projection_sha256`
          是否已经等于本次要提交的 projection digest。两侧走**同一套**
          canonicalization（见模块文档 §五），所以「内容一字未改」在这里是逐字节可判的；
        * **canonical substrate identity + immutable definition bundle** ——
          `representation.id == pre.resolution.representation_id`。这**一个**条件同时
          固定了两项：substrate 就是当前 published representation 本身，而 bundle 是
          该行上冻结的属性（`definition_bundle_id/sha256` 是它的列）。

        🔴 这里刻意**不再**额外比一次 `definition_bundle_sha256 == pre.bundle.bundle_sha256`：
        `pre.bundle` 正是**从这一行**解析出来的，所以那个比较在任何输入下都恒真 ——
        一条永不可能失败的判据（本任务变异检验实测：把它改成恒真的自比较，
        61 条里唯一那条 GREEN）。真正的 bundle 漂移判据是 preflight 第 5 步的
        `assert_representation_admissible`：它比的是 representation 行上**冻结**的 digest
        与 bundle 行**现在**算出来的 digest（AC 2.10 的 alias 漂移），那条是可失败的。
        多留一个恒真判据只会让读者以为 bundle 被独立校验过。

        🔴 为什么**不是**「找一个 `parent_version_id == base` 且 projection 相同的历史
        version」：那种写法把「上一次提交的结果」和「这一次的基线」错配成同一层 ——
        上次 commit 产生的 cv 的 parent 是**更早**的 base，而这次的 base 正是那个 cv 自己，
        于是条件恒不成立、幂等复用永远命中不了。这个缺陷在只测 token 重放的守卫下**全绿**
        （2026-08-27 真库实测：第二次同内容 flush 又提交了一个 revision）。

        🔴 entry 维度只在 **representation** 上出现，不在 content version 上：
        `working_paper_content_version` 是 **wp 级** immutable 行，压根没有 `entry_id`
        列（entry 维度住在 representation 与 `working_paper_sync_entry_state` 上）。
        写 `WorkpaperContentVersion.entry_id` 会是一个 `AttributeError` —— 它在
        Volar/vitest/`get_diagnostics` 下全绿，只有真跑一次才暴露。
        """
        version = (
            await self._session.execute(
                sa.select(WorkpaperContentVersion).where(
                    WorkpaperContentVersion.id == pre.base_content_version_id,
                    WorkpaperContentVersion.wp_id == request.wp_id,
                    WorkpaperContentVersion.projection_sha256 == payload_sha256,
                )
            )
        ).scalar_one_or_none()
        if version is None:
            return None
        representation = (
            await self._session.execute(
                sa.select(WorkpaperContentRepresentation).where(
                    WorkpaperContentRepresentation.id == pre.resolution.representation_id,
                    WorkpaperContentRepresentation.content_version_id == version.id,
                    WorkpaperContentRepresentation.entry_id == str(request.entry_id),
                )
            )
        ).scalar_one_or_none()
        if representation is None:
            return None
        return version, representation

    async def _latest_representation(
        self, *, wp_id: uuid.UUID, entry_id: str, version_id: uuid.UUID
    ) -> WorkpaperContentRepresentation:
        row = (
            await self._session.execute(
                sa.select(WorkpaperContentRepresentation)
                .where(
                    WorkpaperContentRepresentation.wp_id == wp_id,
                    WorkpaperContentRepresentation.entry_id == entry_id,
                    WorkpaperContentRepresentation.content_version_id == version_id,
                )
                .order_by(WorkpaperContentRepresentation.generation.desc())
            )
        ).scalars().first()
        if row is None:
            raise PendingTokenStateError(
                f"content version {version_id} 在 entry {entry_id!r} 上没有 representation"
                " —— 这正是「projection-only commit」留下的半成功态"
            )
        return row

    async def _load_operation(self, operation_id: uuid.UUID) -> WorkpaperSyncOperation:
        row = (
            await self._session.execute(
                sa.select(WorkpaperSyncOperation).where(
                    WorkpaperSyncOperation.id == operation_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise MaterializeCoordinatorError(f"operation 不存在: {operation_id}")
        return row

    async def _register_or_reuse_artifact(
        self,
        *,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        relative_path: str,
        sha256: str,
        size_bytes: int,
    ) -> WorkpaperArtifact:
        """内容寻址 artifact 行的幂等登记。

        `uq_wpa_relative_path` 是唯一索引，而内容寻址路径 = f(revision, sha256) ⇒
        同一份 payload 二次 flush 必然撞路径。复用既有行而不是插一条新的 —— 这不是
        「容错」，是内容寻址存储的定义：同路径同内容就是同一个 artifact。
        """
        existing = (
            await self._session.execute(
                sa.select(WorkpaperArtifact).where(
                    WorkpaperArtifact.relative_path == relative_path
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if str(existing.sha256) != str(sha256):
                raise MaterializeCoordinatorError(
                    f"artifact 路径 {relative_path} 已存在但 digest 不同"
                    f"（existing={existing.sha256} incoming={sha256}）—— "
                    "不可变命名空间不允许覆盖"
                )
            return existing
        return await self._repo.register_artifact(
            project_id=project_id,
            wp_id=wp_id,
            kind=ArtifactKind.projection,
            state=ArtifactState.published,
            relative_path=relative_path,
            sha256=sha256,
            size_bytes=size_bytes,
            document_type="json.gz",
        )

    def _receipt_of(
        self, row: WorkpaperPendingMutation, *, replayed: bool
    ) -> PendingMutationReceipt:
        return PendingMutationReceipt(
            pending_mutation_id=row.id,
            pending_mutation_token=self._tokens.encode(
                PendingMutationTokenPayload(
                    schema_version=TOKEN_SCHEMA_VERSION,
                    pending_mutation_id=row.id,
                    project_id=row.project_id,
                    wp_id=row.wp_id,
                    entry_id=str(row.entry_id),
                    sheet_key=str(row.sheet_key),
                    user_id=row.user_id,
                    expected_revision=int(row.expected_revision),
                    payload_sha256=str(row.payload_sha256),
                    idempotency_key=str(row.idempotency_key),
                    expires_at=row.expires_at,
                )
            ),
            expected_revision=int(row.expected_revision),
            payload_sha256=str(row.payload_sha256),
            expires_at=row.expires_at,
            idempotency_key=str(row.idempotency_key),
            replayed=replayed,
        )

    async def _read_content_revision(self, wp_id: uuid.UUID) -> int:
        return int(
            (
                await self._session.execute(
                    sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
                    {"wp": wp_id},
                )
            ).scalar_one()
        )

    async def _revision_of(self, version_id: uuid.UUID | None) -> int | None:
        if version_id is None:
            return None
        return int(
            (
                await self._session.execute(
                    sa.select(WorkpaperContentVersion.revision).where(
                        WorkpaperContentVersion.id == version_id
                    )
                )
            ).scalar_one()
        )

    async def _count_rooms(self, wp_id: uuid.UUID, entry_id: str) -> int:
        return int(
            (
                await self._session.execute(
                    sa.select(sa.func.count())
                    .select_from(WorkpaperOoRoom)
                    .where(
                        WorkpaperOoRoom.wp_id == wp_id,
                        WorkpaperOoRoom.entry_id == entry_id,
                    )
                )
            ).scalar_one()
        )


# ═══════════════════════════════════════════════════════════════════════════
# 7. 模块级工具
# ═══════════════════════════════════════════════════════════════════════════


def _canonical_projection_bytes(projection: Projection) -> bytes:
    """projection 的 canonical 字节 —— 与 Task 15 落盘用的**完全同一套**实现。

    🔴 单一实现是 AC 3.6 能成立的前提：flush 算 digest、commit 算 digest、
    幂等复用比 digest，三处必须逐字节一致。写第二套 canonicalizer 的后果不是
    「偶尔不等」，而是「幂等复用永远命中不了」—— 而那在只测 token 重放的守卫下**全绿**。
    因此这里直接调用 `content_mutation._projection_payload`，并有一条守卫实测
    「coordinator 预算的 digest == commit 后 receipt.projection_sha256」。
    """
    from app.services.workpaper_sync.definitions import canonical_json_bytes

    return canonical_json_bytes(_projection_payload(projection))


def _uuid_of(payload: Mapping[str, Any], key: str) -> uuid.UUID:
    raw = payload.get(key)
    if raw is None:
        raise DescriptorStaleIdentityError(f"confirm-descriptor 回传缺 {key!r}")
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError) as exc:
        raise DescriptorStaleIdentityError(
            f"confirm-descriptor 的 {key}={raw!r} 不是合法 UUID"
        ) from exc


def build_materialize_coordinator(
    session: AsyncSession, *, secret: str | None = None
) -> MaterializeCoordinator:
    """生产装配（Task 28 的 router 唯一构造处）。

    🔴 与 `build_html_content_mutation_service` 同理：**函数而不是模块级单例** ——
    coordinator 持有 session，而 session 是 per-request 的。做成单例会让第一个请求的
    事务边界被后续请求复用，那类缺陷在单测里看不见，只在并发下表现为「偶发提交到
    别人的事务」。
    """
    from app.core.config import settings
    from app.services.workpaper_sync.canonical_paths import BACKEND_ROOT

    artifacts = CanonicalArtifactRepository(BACKEND_ROOT)
    repository = WorkpaperSyncRepository(session)
    resolution = CanonicalResolutionService(session, artifacts)
    mutations = ContentMutationService(
        session=session,
        repository=repository,
        artifacts=artifacts,
        resolution=resolution,
    )
    # 🔴 平台的签名密钥叫 `JWT_SECRET_KEY`（见 `app/core/config.Settings`）。
    # Task 25 落地时这里写的是 `SECRET_KEY` —— 那个属性**根本不存在**，
    # `getattr(..., "")` 恒得空串 ⇒ 本函数恒抛 ⇒ materialize 端点在生产上恒 500。
    # Task 25 没有生产调用方，所以这条在当时不可观测；Task 28 接线后第一次真跑就暴露。
    # 仍然 fail closed（空密钥等于不签名），只是读对了属性名。
    key = secret or str(getattr(settings, "JWT_SECRET_KEY", "") or "")
    if not key:
        raise MaterializeCoordinatorError(
            "缺少 pending mutation token 签名密钥（settings.JWT_SECRET_KEY）—— "
            "空密钥等于不签名，伪造 token 即可跨 scope 消费"
        )
    return MaterializeCoordinator(
        session=session,
        repository=repository,
        artifacts=artifacts,
        resolution=resolution,
        mutations=mutations,
        rooms=RoomService(repository),
        token_codec=PendingMutationTokenCodec(key),
        representations=RepresentationService(
            session=session,
            repository=repository,
            artifacts=artifacts,
            resolution=resolution,
        ),
    )
