# -*- coding: utf-8 -*-
"""OO→HTML coordinator：只读 incoming substrate、canonical rematerialize 与最终授权 fence。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 26
Requirements: 2.9, 4.2, 4.3, 4.5, 4.6, 4.11, 4.12, 5.8, 6.8, 6.9, 6.11,
8.9, 8.10, 8.11, 8.12, 10.10
Properties: P14 / P19 / P25 / P26 / P27 / P29 / P38 / P43 / P62 / P65

═══ 一、substrate 只有一个合法来源，且三层各自拒绝 quarantined ═══

AC 8.10 的原文是「只以该 application 固定且 `kind=incoming,state=durable` 的 artifact
为只读基底」。这句话有两个独立的承诺，本模块把它们落成两套不同的判据：

1. **来源唯一** —— 只能是 `application.incoming_artifact_id`。禁止用 callback 到达时的
   room pointer（`room.last_applied_version_id` / `latest_durable_application_id`）、
   registry 当前 alias、upgrade candidate 或 operation 上的任何路径「猜」出 substrate。
   这条是**代码形态**判据，运行期观察不到（猜错时照样能读出一个文件），所以由
   :func:`assert_substrate_resolution_source_shape` 做 AST 反查：解析函数体里不得出现
   被禁符号，且对 repository 的调用集合必须是白名单子集。
2. **kind/state 准入** —— 三层各自独立拒绝：

   | 层 | 实现 | quarantined 时抛 |
   |---|---|---|
   | application FK / DB | V151 `wpsync_check_application_identity` + :meth:`WorkpaperSyncRepository.assert_incoming_durable` | `QuarantinedIncomingError` |
   | coordinator 入口 | :meth:`OoToHtmlCoordinator.open_substrate` → :func:`assert_coordinator_substrate_admissible` | :class:`SubstrateQuarantinedError` |
   | engine | Task 13 `assert_substrate_usable(role=incoming, …)` | `QuarantinedIncomingError` |

   三层不是冗余：DB 层保护「有人手写 SQL 造 application」，coordinator 层保护
   「有人绕过 application 直接把 artifact id 塞进来」，engine 层保护「有人自己拼
   `ContentCommitPlan`」。删掉任一层都有一条真实的进入路径。三层的异常类型刻意不同 ——
   共用一个类型时，删掉中间层会被上下游遮蔽而在变异检验里判 GREEN。

quarantined 只允许 `download-only / expire / retention`，永不 release、永不转 durable
（Requirement 5.6）。本模块**没有**任何 release 面：唯一相关方法
:func:`assert_quarantined_operation_allowed` 是白名单闸，`release` / `promote` /
`application` / `extract` / `merge` / `retry` / `rematerialize` 一律恒抛。

═══ 二、rematerialize 的不可交换顺序 ═══

```text
open substrate(incoming,durable)
  → extract(base   ← application.base_representation_id)      # frozen client base
  → extract(current← entry current pointer representation)      # 服务器现状
  → extract(incoming ← substrate)                               # OO 回写
  → merge_projections(base, current, incoming)                  # Task 14
  ├─ 有冲突且无裁决 ⇒ application/operation=conflict，指针一律不动（AC 8.11）
  └─ 无冲突/已裁决
       → ContentMutationService.commit(substrate=incoming, role=incoming)   # Task 15
           ├ materialize(merged 写到独立 staging 的新 result)
           ├ extract(result) 与 merged 逐字段等值            # P29 / P65 / AC 6.11
           ├ verify_unmanaged_regions(before=incoming, after=result)  # AC 8.11
           ├ ★ fence.before_publish：final authorization / generation·write fence /
           │   eligibility / bundle identity —— **通过后才 publish**
           ├ publish_representation（新 canonical artifact；incoming 行一字不动）
           ├ wp advisory+row lock → ★ fence.before_write（写库前再验一次）
           ├ revision CAS → content version → representation → entry pointer
           ├ room server last-applied（+ canonical fence）
           ├ ★ fence.after_pointers：application result + operation timeline（同事务）
           └ outbox → 恰一次 commit
       → settle client baseline（merged==incoming 才推进；否则 refresh-required+supersede）
```

「★」三处就是 Task 15 新增的 :class:`~.content_mutation.CommitFenceHook` 三个回调点。
为什么把 fence 挂进 Task 15 而不是在 coordinator 里自建事务：Requirement 2.1 /
Property 61 要求全平台**唯一** commit 边界。coordinator 若为了「publish 前再验一次」
自己开事务，`_CommitLatch`（恰一次 commit）与 `_TransactionWitness`（单事务见证）
这两道自证就被绕过了 —— 那正是 Task 20 门要求为 0 的形态。

═══ 三、incoming 永不晋升 ═══

result 是**新生成**的 content-addressed canonical artifact（`.versions/…`），与 incoming
（`.incoming/{wp}/{delivery}/…`）是两行、两条路径。本模块从不调用
`artifacts.promote_incoming_to_published()`（它恒抛），也从不把 incoming 的
`artifact_id` 写进 representation。:meth:`OoToHtmlCoordinator._assert_incoming_untouched`
在 commit 后**重读 incoming 行**核对 `kind/state/published_at/relative_path` 逐项未变 ——
判据落在数据库行上，不是「我没写那行代码」。

═══ 四、没有 fail-open ═══

「project/visibility/workflow lock」这三样活在同步域之外，因此由调用方注入
:class:`AuthorizationProbe`。它是**必填**构造参数，不是「给了就查、没给就放行」的可选项：
可选即等于默认放行，而 AC 10.10 没有例外。probe 自身抛异常时不吞成 WARNING，而是包成
:class:`AuthorizationProbeFailedError`（error_code 独立），让「探针接线错了」表现为
可诊断失败而不是「本项目无此限制」。

═══ 五、本模块不做的事 ═══

* 不调 OnlyOffice Command Service（Property 38：durable incoming 的 retry 一律不再
  forcesave）。:func:`assert_no_command_service_reference` 用 AST 钉死这一点。
* 不建 room/participant/request/application/operation（分属 Task 21/23/24）。
  retry 复用既有 primary timeline，`operation`/`application` 计数必须逐个不变。
* 不做 conflict 预览 API、resolve fence 与 rollback 的**编排与授权**（Task 27 的
  `conflict_resolution.py` / Task 28 的 router）。但**人工裁决的落地面在本模块**：
  Task 27 已把它接线（:data:`RETIRED_ADJUDICATION_CONSUMER`）。接线形态是
  「有冲突且带裁决 ⇒ 用 :func:`~merge.apply_resolutions` 折叠后发布」，而不是
  「校验裁决覆盖率后仍发布 `merge.merged`」—— 后者对每个冲突字段保留的是 **current**
  侧值，等于把审计师的选择静默换成 current，而 extract 等值、roundtrip 与 fence
  全部照常通过（Task 26 收口审计抓到的第四个真实缺陷）。
* 不实现任何 Excel/Word 载体逻辑（Tasks 36~38 / 59~61）。adapter 由调用方按 Task 13
  的 registry 提供。
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Final, Mapping, Protocol, Sequence, runtime_checkable

import sqlalchemy as sa

from app.models.workpaper_sync_models import (
    WorkpaperArtifact,
    WorkpaperContentApplication,
    WorkpaperForcesaveRequest,
    WorkpaperOoCloseIntent,
    WorkpaperOoCloseIntentEvent,
    WorkpaperOoParticipant,
    WorkpaperOoRoom,
    WorkpaperSyncOperation,
)
from app.services.workpaper_sync.adapters.base import (
    Projection,
    SubstrateRole,
    WorkpaperSyncAdapter,
    assert_substrate_usable,
)
from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
from app.services.workpaper_sync.conflicts import (
    ConflictSet,
    ResolutionChoice,
    UnresolvedConflictError,
)
from app.services.workpaper_sync.content_mutation import (
    CONFLICT_RESOLUTION,
    ONLYOFFICE,
    BusinessMutation,
    CommitTransactionFacts,
    ContentCommitPlan,
    ContentCommitReceipt,
    ContentMutationService,
    projection_canonical_digest,
)
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.merge import (
    MergeOutcome,
    apply_resolutions,
    merge_projections,
)
from app.services.workpaper_sync.models import (
    APPLICATION_EDGES,
    OPERATION_EDGES,
    ActorType,
    ApplicationEventType,
    ApplicationState,
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    BundleSlot,
    CloseIntentState,
    OperationShape,
    OperationState,
    ParticipantState,
    RequestKind,
    SyncDomainError,
    classify_operation_shape,
    compute_contributor_snapshot_digest,
    is_digest,
)
from app.services.workpaper_sync.repository import WorkpaperSyncRepository
from app.services.workpaper_sync.request_application import (
    CanonicalRead,
    RequestApplicationService,
)
from app.services.workpaper_sync.resolution import (
    CanonicalResolutionService,
    DefinitionBundleSnapshot,
    ResolutionIntent,
)
from app.services.workpaper_sync.rooms import FrozenBundleIdentity, RoomService

__all__ = [
    # 异常
    "OoToHtmlError",
    "SubstrateOriginForbiddenError",
    "SubstrateNotIncomingError",
    "SubstrateNotDurableError",
    "SubstrateQuarantinedError",
    "SubstrateFileMissingError",
    "QuarantinedOperationForbiddenError",
    "ApprovedContractChildMissingError",
    "AdjudicationContractRequiredError",
    "AdjudicationWithoutConflictError",
    "CanonicalPrimaryRequiredError",
    "ApplicationScopeMismatchError",
    "FinalFenceError",
    "ProjectNotVisibleError",
    "WorkflowLockedError",
    "GenerationSupersededError",
    "WriteFenceAdvancedError",
    "FrozenInitiatorMissingError",
    "InitiatorMissingError",
    "InitiatorEpochChangedError",
    "InitiatorNotLiveError",
    "ContributorSnapshotDriftError",
    "ApprovedBundleReplacedError",
    "CloseCaptureEligibilityUnprovenError",
    "EligibilityEpochAdvancedError",
    "AuthorizationProbeFailedError",
    "ResultArtifactDigestError",
    "ResultBundleIdentityError",
    "IncomingMutatedError",
    "PreBindResultRevisionError",
    "ApplyStageOrderError",
    "ReapplyForbiddenError",
    "ApplicationTerminalStaleError",
    # 枚举 / 常量
    "SubstrateOrigin",
    "LEGAL_SUBSTRATE_ORIGIN",
    "QUARANTINE_ALLOWED_OPERATIONS",
    "ApplyStage",
    "OoToHtmlResult",
    "REFRESH_REASON_MERGED_DIFFERS",
    "SUPERSEDE_REASON_MERGED_DIFFERS",
    "SUPERSEDE_REASON_CLOSE_CAPTURE_STALE",
    "APPLY_ADMISSIBLE_APPLICATION_STATES",
    "RETIRED_ADJUDICATION_CONSUMER",
    # 值对象
    "FrozenApplicationIdentity",
    "ReadOnlySubstrate",
    "LiveAuthorizationFacts",
    "AuthorizationProbe",
    "ThreeWayInputs",
    "ApplyJournal",
    "OoToHtmlOutcome",
    # 纯判据
    "assert_quarantined_operation_allowed",
    "assert_application_state_admits_apply",
    "settle_adjudicated_projection",
    "assert_coordinator_substrate_admissible",
    "assert_projection_result_has_approved_contract",
    "assert_final_authorization",
    "assert_incoming_row_unchanged",
    "assert_published_digest_was_approved",
    "assert_canonical_fence_points_at",
    "settlement_digest_pair",
    "assert_substrate_resolution_source_shape",
    "assert_fence_callbacks_assert_order_first",
    "assert_no_command_service_reference",
    # 服务
    "OoToHtmlCoordinator",
]


def _now() -> datetime:
    """服务端时钟（aware）。timestamptz 必须在 Python 侧构造 datetime。"""
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 0. 异常：每条拒绝原因一个类型 + 一个 error_code
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么每条都单列：本 spec 已为「两条拒绝共用 error_code」付过三次代价。共用时
# 靠前的分支变成 provably-dead —— 短路它，靠后的分支抛同一 code，守卫看不出差别，
# 变异检验判 GREEN，下一个人据此以为守卫有缺陷而去放宽判据。


class OoToHtmlError(SyncDomainError):
    error_code = "oo_to_html_failed"


class SubstrateOriginForbiddenError(OoToHtmlError):
    """substrate 不是从 `application.incoming_artifact_id` 取的（AC 8.10 / 4.3）。"""

    error_code = "substrate_origin_forbidden"


class SubstrateNotIncomingError(OoToHtmlError):
    """substrate artifact 的 kind 不是 `incoming`。"""

    error_code = "substrate_not_incoming_kind"


class SubstrateNotDurableError(OoToHtmlError):
    """incoming 尚未 sealing 为 durable（**暂态**，与隔离终态分型）。"""

    error_code = "substrate_incoming_not_durable"


class SubstrateQuarantinedError(OoToHtmlError):
    """coordinator 入口拒绝 quarantined incoming（**永久安全终态**）。

    与 :class:`~.models.QuarantinedIncomingError`（DB/engine 层）刻意不同类型：
    三层拒绝必须可分辨，否则删掉 coordinator 这一层会被另两层遮蔽（GREEN）。
    """

    error_code = "substrate_incoming_quarantined_coordinator"


class SubstrateFileMissingError(OoToHtmlError):
    """artifact 行存在但磁盘文件缺失（Task 7 db6 证明这在物理上可能）。"""

    error_code = "substrate_file_missing"


class QuarantinedOperationForbiddenError(OoToHtmlError):
    """对 quarantined incoming 做了白名单之外的动作（release/转 durable/进 engine …）。"""

    error_code = "quarantined_operation_forbidden"


class ApprovedContractChildMissingError(OoToHtmlError):
    """projection-based result 的 frozen bundle 缺 approved contract child（AC 8.12）。"""

    error_code = "projection_result_missing_approved_contract"


class AdjudicationContractRequiredError(OoToHtmlError):
    """带人工裁决却没有 per-entry contract —— 折叠无从进行（AC 8.3）。

    🔴 与 :class:`ApprovedContractChildMissingError` 分两个类型：后者说的是「frozen
    bundle 的 contract child 不 approved / digest 与传入 contract 不符」，本条说的是
    「调用方一条 contract 都没传，而裁决折叠必须按 contract 的行身份与保护策略重算」。
    共用一个 `error_code` 会让靠前那条判据永久不可达。
    """

    error_code = "adjudication_requires_contract"


class AdjudicationWithoutConflictError(OoToHtmlError):
    """收到裁决但本次 merge 零冲突 —— 客户端手里的 conflict set 已经不是这一份。

    🔴 不能「静默忽略」：忽略等于把一次 resolve 请求当成普通 apply 处理，审计师会看到
    「裁决成功」而实际上他选的那些字段根本没参与本次发布（conflict set 已被 rebase 或
    supersede 掉了）。fence 层（Task 27 的 `conflict_resolution.py`）会先按
    `conflict_set_digest` 拒绝，本条是**引擎层**的第二道锁 —— 两层都要能独立证伪。
    """

    error_code = "adjudication_without_conflict"


class CanonicalPrimaryRequiredError(OoToHtmlError):
    """requested operation canonicalize 后仍不是绑定 application 的 primary。"""

    error_code = "canonical_primary_required"


class ApplicationScopeMismatchError(OoToHtmlError):
    """application 的 project/wp/entry/room 与显式声明的 scope 不符。"""

    error_code = "application_scope_mismatch"


# ── 最终授权 fence：十个独立分支，逐条可变异 ────────────────────────────────


class FinalFenceError(OoToHtmlError):
    """最终授权 fence 的基类。**不要**直接抛它 —— 抛具体子类。"""

    error_code = "final_authorization_fence_failed"


class ProjectNotVisibleError(FinalFenceError):
    error_code = "final_fence_project_not_visible"


class WorkflowLockedError(FinalFenceError):
    error_code = "final_fence_workflow_locked"


class GenerationSupersededError(FinalFenceError):
    error_code = "final_fence_generation_superseded"


class WriteFenceAdvancedError(FinalFenceError):
    error_code = "final_fence_write_fence_advanced"


class FrozenInitiatorMissingError(FinalFenceError):
    """**request 侧**冻结的 initiating participant 为空。

    与 :class:`InitiatorMissingError`（观测侧看不到人）刻意分型：两者共用一个
    error_code 时，本条会被后者遮蔽 ⇒ 「删掉 frozen 侧的 null 检查」在变异检验里判
    GREEN（M14 首轮实测正是如此）。语义也确实不同：本条是「平台自己冻结时就没记下
    发起人」= system/route identity 冒充用户授权（AC 10.10 明令禁止），
    后者是「记下了，但那个人现在不在了」。
    """

    error_code = "final_fence_frozen_initiator_missing"


class InitiatorMissingError(FinalFenceError):
    """观测侧看不到冻结的那个 initiating participant（被删/换人/不属于本 room）。"""

    error_code = "final_fence_initiator_missing"


class InitiatorEpochChangedError(FinalFenceError):
    error_code = "final_fence_initiator_epoch_changed"


class InitiatorNotLiveError(FinalFenceError):
    error_code = "final_fence_initiator_not_live"


class ContributorSnapshotDriftError(FinalFenceError):
    error_code = "final_fence_contributor_snapshot_drift"


class ApprovedBundleReplacedError(FinalFenceError):
    error_code = "final_fence_approved_bundle_replaced"


class CloseCaptureEligibilityUnprovenError(FinalFenceError):
    """`kind=close_capture` 的 origin request 找不到 promotion 时冻结的 eligibility epoch。

    与 :class:`EligibilityEpochAdvancedError` **分型**：前者是「无从证明它曾合法」
    （append-only promotion event 缺失 ⇒ 这个 close-capture 不是 reconciler 在锁内
    CAS 产出的），后者是「曾合法但已失效」。合成一个 error_code 时靠前的分支会变成
    provably-dead：促成 unproven 的输入也会让 epoch 比对失败，于是「缺 promotion
    event」这条判据删掉照样绿（本 spec 已为共用 error_code 付过三次代价）。
    """

    error_code = "final_fence_close_capture_eligibility_unproven"


class EligibilityEpochAdvancedError(FinalFenceError):
    error_code = "final_fence_eligibility_epoch_advanced"


class AuthorizationProbeFailedError(OoToHtmlError):
    """外部授权探针本身失败（**不得**降级为「无此限制」）。

    这条存在的唯一理由是禁 fail-open：`except Exception: logger.warning(...)` 会把
    「函数名写错」「列名写错」「单参调用 async 签名」全部吞成「本项目无此限制」，
    而四层静态检查都是绿的（Requirement 5.12）。
    """

    error_code = "authorization_probe_failed"


class ResultArtifactDigestError(OoToHtmlError):
    """publish 出去的 artifact digest 与 fence 放行的那一份不一致。"""

    error_code = "result_artifact_digest_mismatch"


class ResultBundleIdentityError(OoToHtmlError):
    """result representation 的 bundle identity 与 application 冻结值不一致。"""

    error_code = "result_bundle_identity_mismatch"


class IncomingMutatedError(OoToHtmlError):
    """commit 后 incoming artifact 行被改动（晋升/改路径/改 state）。"""

    error_code = "incoming_artifact_mutated"


class PreBindResultRevisionError(OoToHtmlError):
    """pre-bind shell（`application_id=NULL`）被问 result revision（P14）。"""

    error_code = "pre_bind_shell_has_no_result_revision"


class ApplyStageOrderError(OoToHtmlError):
    """执行轨迹违反不可交换顺序。"""

    error_code = "apply_stage_order_violation"


class ReapplyForbiddenError(OoToHtmlError):
    """application 已经应用过一次（`applied` / `refresh_required`），不得再应用。

    AC 4.3 末句：「同一 frozen application 才能应用**一次**」。AC 8.12 进一步要求
    applied content version 与 result representation/artifact/bundle 一对一绑定，
    Property 65 要求 「content version、representation、application identity 与 bundle
    均不可原地改写」。

    🔴 为什么必须在**入口**拦，而不是靠状态机「自然报错」——
    2026-08-27 真库实测（短路本判据后跑 `_pg` 的 `TestReapplyIsRefused`）：

    * `APPLICATION_EDGES[applied]` 是空集，于是 :meth:`OoToHtmlCoordinator.
      _walk_application` 的「到不了这一站就跳过」把整条 `validating → … →
      rematerializing` 静默跳过，`_advance_application` 又在 `from == to` 时提前返回
      ⇒ **流程一路跑到底**：三侧 extract、materialize 写出一份新的 staged result、
      未管理区域比对全部真实发生（adapter 调用清单实测 6 次）；
    * 直到写库阶段才撞出 `StateTransitionError:illegal_state_transition` ——
      一个**不带业务语义**的状态机错误，操作者看不出「这个 application 已经应用过」；
    * 更糟的是它连失败都记不下来：`_record_post_durable_failure` 自己也要走
      `applied → error`（同样是非法边）⇒ 异常**穿透**整个入口，application/operation
      的 timeline 一条 event 都没有。

    没有观测到第二个 business revision（状态机在写库前偶然拦住了它）—— 但这份保护是
    **偶然的**：它依赖「`applied` 恰好没有出边」这个与本判据无关的事实。AC 4.3
    「同一 frozen application 才能应用一次」必须有自己的判据。
    """

    error_code = "application_already_applied"


class ApplicationTerminalStaleError(OoToHtmlError):
    """application 已落不可重试终态（`superseded` / `authorization_stale`）。

    与 :class:`ReapplyForbiddenError` **分型**：那一条是「已经成功过」，本条是
    「已经作废」。后续动作完全不同 —— 前者要前端去 reload 既有 revision，后者只能走
    supersede/recovery（AC 10.10 末句）。共用一个 error_code 时，靠前的分支永远
    provably-dead。
    """

    error_code = "application_terminal_not_retryable"


# ═══════════════════════════════════════════════════════════════════════════
# 1. substrate 来源封闭枚举
# ═══════════════════════════════════════════════════════════════════════════


class SubstrateOrigin(str, Enum):
    """substrate 的来源。**只有第一个合法**，其余四个是 AC 8.10/4.3 逐条点名的禁法。

    做成枚举而不是布尔，是为了让「我用的是哪一种」在运行期可观测：
    :class:`ReadOnlySubstrate` 携带它，:func:`assert_coordinator_substrate_admissible`
    逐值判定。只留一个布尔 `from_application` 时，「猜出来的路径」也可以把它设成 True。
    """

    application_incoming_fk = "application_incoming_fk"
    """唯一合法：`working_paper_content_application.incoming_artifact_id`。"""

    callback_room_pointer = "callback_room_pointer"
    """禁：callback 到达时的 room `last_applied` / `latest_durable_application_id`。"""

    registry_current_alias = "registry_current_alias"
    """禁：definition registry 的当前 alias（历史读取不得按 alias 重组）。"""

    upgrade_candidate = "upgrade_candidate"
    """禁：representation upgrade candidate（Requirement 6.18）。"""

    operation_path = "operation_path"
    """禁：operation 行上的任何路径/指针反猜。"""


LEGAL_SUBSTRATE_ORIGIN: Final[SubstrateOrigin] = SubstrateOrigin.application_incoming_fk

#: quarantined incoming 的**唯一**允许动作集合（Requirement 5.6 原文三项）。
QUARANTINE_ALLOWED_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"download_only", "expire", "retention"}
)

REFRESH_REASON_MERGED_DIFFERS: Final[str] = "merged_projection_differs_from_incoming"
SUPERSEDE_REASON_MERGED_DIFFERS: Final[str] = "merged_differs_reopen_required"

#: close-capture 的 leader 在 **promotion 之后**授权失效时的 supersede 原因（AC 10.10）。
SUPERSEDE_REASON_CLOSE_CAPTURE_STALE: Final[str] = "close_capture_authorization_stale"


def _states_that_can_still_reach(target: ApplicationState) -> frozenset[ApplicationState]:
    """`APPLICATION_EDGES` 上能（传递地）到达 `target` 的状态集合，含 `target` 自身。

    🔴 判据只有**一份**登记表：`APPLICATION_EDGES`。手写第二份「哪些状态还能 apply」
    的名单等于第二真源 —— 状态机哪天加一条边，两份就会分叉，而分叉的那天两边都
    「全绿」。反向可达性是从同一张表推出来的，因此不可能与它不一致。
    """
    reverse: dict[ApplicationState, set[ApplicationState]] = {}
    for src, dsts in APPLICATION_EDGES.items():
        for dst in dsts:
            reverse.setdefault(dst, set()).add(src)
    seen = {target}
    frontier = [target]
    while frontier:
        node = frontier.pop()
        for pred in reverse.get(node, ()):
            if pred not in seen:
                seen.add(pred)
                frontier.append(pred)
    return frozenset(seen)


#: 允许进入 :meth:`OoToHtmlCoordinator.apply_durable_incoming` 的 application 状态。
#: = 仍能（传递地）到达 `applying` 的状态。首跑（`queued/validating/extracting/merging`）、
#: resolve（`conflict`）、崩溃续跑（`rematerializing/applying`）与 retry（`error`）都在内。
APPLY_ADMISSIBLE_APPLICATION_STATES: Final[frozenset[ApplicationState]] = (
    _states_that_can_still_reach(ApplicationState.applying)
)

#: 已经成功应用过一次 ⇒ :class:`ReapplyForbiddenError`。
_ALREADY_APPLIED_STATES: Final[frozenset[ApplicationState]] = frozenset(
    {ApplicationState.applied, ApplicationState.refresh_required}
)

#: 已作废、不可重试 ⇒ :class:`ApplicationTerminalStaleError`。
_STALE_TERMINAL_STATES: Final[frozenset[ApplicationState]] = frozenset(
    {ApplicationState.superseded, ApplicationState.authorization_stale}
)

# 🔴 双向锁死：两个具名集合必须**恰好**等于登记表推出来的不可准入集合。
# 状态机新增一个终态而这里没分类时，import 就失败 —— 而不是让新终态悄悄落进
# 「允许 apply」或落进某个兜底分支（兜底分支今天不可达 ⇒ 永远 GREEN）。
_INADMISSIBLE: Final[frozenset[ApplicationState]] = (
    frozenset(ApplicationState) - APPLY_ADMISSIBLE_APPLICATION_STATES
)
if _INADMISSIBLE != (_ALREADY_APPLIED_STATES | _STALE_TERMINAL_STATES):  # pragma: no cover
    raise SyncDomainError(
        "APPLICATION_EDGES 推出的不可准入状态 "
        f"{sorted(s.value for s in _INADMISSIBLE)} 与本模块的分类 "
        f"{sorted(s.value for s in (_ALREADY_APPLIED_STATES | _STALE_TERMINAL_STATES))} "
        "不一致 —— 新增 application 终态必须显式归类到「已应用过」或「已作废」"
    )


def assert_application_state_admits_apply(
    state: ApplicationState, *, application_id: uuid.UUID, attempt: int
) -> None:
    """apply 入口的状态准入（AC 4.3「同一 frozen application 只应用一次」）。

    两个拒绝分支各一个类型、各一个 error_code；准入集合由
    :data:`APPLY_ADMISSIBLE_APPLICATION_STATES` 从 `APPLICATION_EDGES` 反向可达性推出。
    """
    if state in APPLY_ADMISSIBLE_APPLICATION_STATES:
        return
    if state in _ALREADY_APPLIED_STATES:
        raise ReapplyForbiddenError(
            f"application {application_id} 已是 {state.value}（attempt={attempt}）—— "
            "同一 frozen application 只能应用一次（AC 4.3 / 8.12 / Property 65）；"
            "再跑一次会用同一个 incoming 产出第二个 business revision 与第二份 "
            "published representation，并原地改写 result_revision"
        )
    raise ApplicationTerminalStaleError(
        f"application {application_id} 已是 {state.value}（attempt={attempt}）—— "
        "不可重试终态只能走 supersede/recovery，不得重新 apply（AC 10.10）"
    )


def assert_quarantined_operation_allowed(operation: str) -> None:
    """quarantined incoming 的白名单闸（与 Task 22 同名判据的 coordinator 侧）。

    白名单而不是黑名单：黑名单漏一个动作就是一条放行路径，而新增动作时没人会记得
    去补黑名单。`release` / `promote_to_durable` / `create_application` / `extract` /
    `merge` / `retry` / `rematerialize` 因此**不需要**逐个登记就已被拒。
    """
    if operation not in QUARANTINE_ALLOWED_OPERATIONS:
        raise QuarantinedOperationForbiddenError(
            f"quarantined incoming 只允许 {sorted(QUARANTINE_ALLOWED_OPERATIONS)}，"
            f"实得 {operation!r} —— 永不 release、永不转 durable、永不创建 application 或"
            "进入 extract/merge/retry/rematerialize（Requirement 5.6 / 8.10）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 从 application 行冻结出来的身份
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FrozenApplicationIdentity:
    """application 行的**逐列**快照。coordinator 只认这一个身份来源。

    刻意把它做成独立值对象而不是「传 application ORM 行」：ORM 行在同一 session 里是
    **活的**，`await session.flush()` 之后它的字段可能已经被别处改写。fence 要比对的是
    「这次 apply 开始时冻结的那一份」，拿活对象比等于自己跟自己比，永远相等。
    """

    application_id: uuid.UUID
    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    room_id: uuid.UUID
    generation: int
    origin_request_id: uuid.UUID
    origin_request_sequence: int
    effective_request_sequence: int
    client_edit_epoch: int
    incoming_artifact_id: uuid.UUID
    incoming_sha256: str
    base_version_id: uuid.UUID
    base_representation_id: uuid.UUID
    current_revision: int
    definition_bundle_id: uuid.UUID
    definition_bundle_sha256: str
    authority_model_definition_id: uuid.UUID
    authority_model_definition_sha256: str
    adapter_id: str
    adapter_build_digest: str
    contributor_snapshot_digest: str
    state: ApplicationState
    #: 来自 origin request 的冻结值（fence 的期望侧）。
    frozen_write_fence_epoch: int
    frozen_initiator_participant_id: uuid.UUID | None
    frozen_initiator_permission_epoch: int
    frozen_client_base_projection_sha256: str
    #: origin request 的 kind。`close_capture` 与普通 `forcesave` 的 eligibility 语义
    #: 不同（前者有 leader 资格快照，后者没有），因此它必须进冻结身份而不是现场推断。
    frozen_request_kind: RequestKind
    #: promotion 当时的 close leader eligibility epoch。
    #: 只有 `kind=close_capture` 才有值；来源是 append-only 的
    #: `working_paper_oo_close_intent_event(to_state='promoted')`，不是可被改写的
    #: `close_intent.eligibility_epoch`（那一列是 **intent 创建时**的值，前任 leader
    #: 失格会让它落后于 promotion 当时的 epoch）。
    frozen_close_leader_eligibility_epoch: int | None

    def assert_scope(
        self, *, project_id: uuid.UUID, wp_id: uuid.UUID, entry_id: str
    ) -> None:
        """application 必须落在显式声明的 scope 内（AC 10.1/10.5 的 coordinator 侧）。"""
        if (
            self.project_id != project_id
            or self.wp_id != wp_id
            or str(self.entry_id) != str(entry_id)
        ):
            raise ApplicationScopeMismatchError(
                f"application {self.application_id} 属于 "
                f"({self.project_id}/{self.wp_id}/{self.entry_id})，与显式声明的 "
                f"({project_id}/{wp_id}/{entry_id}) 不符"
            )


@dataclass(frozen=True)
class ReadOnlySubstrate:
    """只读 substrate 的运行期事实（含来源）。"""

    artifact_id: uuid.UUID
    kind: ArtifactKind
    state: ArtifactState
    origin: SubstrateOrigin
    path: Path
    relative_path: str
    sha256: str
    size_bytes: int
    document_type: str
    durable_at: datetime | None
    published_at: datetime | None

    @property
    def is_incoming_durable(self) -> bool:
        return (
            self.kind is ArtifactKind.incoming
            and self.state is ArtifactState.durable
            and self.durable_at is not None
        )


def assert_coordinator_substrate_admissible(
    *,
    origin: SubstrateOrigin | str,
    artifact_kind: ArtifactKind | str,
    artifact_state: ArtifactState | str,
    durable_at: datetime | None,
    published_at: datetime | None,
    declared_incoming_artifact_id: uuid.UUID,
    resolved_artifact_id: uuid.UUID,
) -> None:
    """coordinator 入口的 substrate 准入（三层拒绝里的**第二层**）。

    六条判据，各自一个异常类型：

    1. `origin` 必须是 :data:`LEGAL_SUBSTRATE_ORIGIN`；
    2. 解析出的 artifact id 必须**逐字节等于** `application.incoming_artifact_id`；
    3. quarantined ⇒ 永久终态拒绝；
    4. kind 必须 `incoming`；
    5. state 必须 `durable` 且 `durable_at` 非空；
    6. `published_at` 必须为空 —— incoming 一旦有 published 时间戳就说明有人试过晋升它。

    第 2 条不是第 1 条的重复：`origin` 是调用方**声明**的来源，id 相等才是**事实**。
    只有声明时，「从 room pointer 查到一个 artifact 再把 origin 写成
    `application_incoming_fk`」照样过关。
    """
    o = origin if isinstance(origin, SubstrateOrigin) else SubstrateOrigin(origin)
    kind = (
        artifact_kind if isinstance(artifact_kind, ArtifactKind) else ArtifactKind(artifact_kind)
    )
    state = (
        artifact_state
        if isinstance(artifact_state, ArtifactState)
        else ArtifactState(artifact_state)
    )

    if o is not LEGAL_SUBSTRATE_ORIGIN:
        raise SubstrateOriginForbiddenError(
            f"OO→HTML 的 substrate 只能来自 {LEGAL_SUBSTRATE_ORIGIN.value}"
            f"（`application.incoming_artifact_id`），实得 {o.value} —— "
            "不得用 callback 到达时的 room pointer、registry 当前 alias、upgrade "
            "candidate 或 operation 路径猜 substrate（AC 4.3 / 8.10）"
        )
    if resolved_artifact_id != declared_incoming_artifact_id:
        raise SubstrateOriginForbiddenError(
            f"解析出的 substrate artifact {resolved_artifact_id} 与 application 固定的 "
            f"{declared_incoming_artifact_id} 不是同一个 —— 声明 origin 合法但事实不符"
        )
    if state is ArtifactState.quarantined:
        raise SubstrateQuarantinedError(
            f"artifact {resolved_artifact_id} 已 quarantined —— coordinator 入口拒绝："
            "quarantined incoming 永不得进入 extract/merge/retry/rematerialize，"
            f"只允许 {sorted(QUARANTINE_ALLOWED_OPERATIONS)}（Requirement 5.6）"
        )
    if kind is not ArtifactKind.incoming:
        raise SubstrateNotIncomingError(
            f"substrate 必须是 kind=incoming，实得 {kind.value} —— OO→HTML 的只读基底"
            "只能是 application 固定的 incoming artifact"
        )
    if state is not ArtifactState.durable or durable_at is None:
        raise SubstrateNotDurableError(
            f"incoming substrate 必须 state=durable 且 durable_at 非空，实得 "
            f"state={state.value} durable_at={durable_at!r}"
        )
    if published_at is not None:
        raise SubstrateOriginForbiddenError(
            f"incoming artifact {resolved_artifact_id} 带有 published_at={published_at!r} —— "
            "incoming 永不得成为 published/current representation 或被 resolver 采用"
        )


#: 人工裁决落地面的登记 —— Task 26 记为 `deferred`（fail closed），**Task 27 已退役**。
#:
#: 退役不等于删除（与 `merge.RETIRED_DEFERRALS` 同一约定）：这里保留「欠账是什么、谁在
#: 哪个任务还的、还到哪」的可核对记录，让边界判据从「零接线 + 有闸门」**翻转**成
#: 「恰一处接线 + 无闸门」，而不是把判据整段删掉 —— 删掉之后没人能证明当初的欠账真的
#: 被还了，也没人能发现它被悄悄退回去。
#:
#: 两个方向都被守卫锁死（`TestManualAdjudicationIsWired`）：
#: * 登记 `retired` 却在本模块搜不到 `apply_resolutions` 的 import/调用 ⇒ 红；
#: * 闸门函数（`assert_manual_adjudication_not_wired`）又出现 ⇒ 红（回退）。
RETIRED_ADJUDICATION_CONSUMER: Final[Mapping[str, Any]] = {
    "capability": "apply_resolutions（人工裁决 → merged projection）",
    "intended_status": "retired",
    "retired_by_task": "27",
    "consumer": "OoToHtmlCoordinator._apply_settled(...)",
    "expected_consumer_module": "app/services/workpaper_sync/oo_to_html.py",
    "commits_through": "app/services/workpaper_sync/content_mutation.py",
    #: 已被撤除的 fail-closed 闸门函数名。守卫按它反查「闸门没有偷偷回来」。
    "retired_fail_closed_gate": "assert_manual_adjudication_not_wired",
    "wired_by": "apply_resolutions",
    "reason": (
        "Task 27 接线人工裁决落地面。修法是三层而不是一层："
        "①本模块在「有冲突且带裁决」时用 `merge.apply_resolutions` 折叠出 settled "
        "projection 再发布（不再是 `MergeOutcome.merged` —— 它对每个冲突字段保留 "
        "current 侧值）；②Task 15 的 `_settle_projection` 独立重算同一个折叠并逐字节"
        "比对，折叠错/忘折叠一律 `AdjudicationNotFoldedError`；③refresh 判据从 "
        "`MergeOutcome.merged` 切到真正落库的那份 projection"
        "（`merge.projection_requires_client_refresh`），"
        "否则 client-confirmed 基线会被推进到客户端从未见过的内容上（AC 8.12 末句）。"
        "resolve 的 fence 与 409 映射在 `conflict_resolution.py`（Task 27），"
        "router 注册在 Task 28。"
    ),
}


def settle_adjudicated_projection(
    *,
    merge: MergeOutcome,
    resolutions: Sequence[ResolutionChoice],
    contract: SyncContract | None,
) -> Projection:
    """算出**真正要发布的那份**受管 projection —— 裁决在这里落地。

    这是 Task 26 登记、Task 27 退役的那笔欠账的接线点（见
    :data:`RETIRED_ADJUDICATION_CONSUMER`）。四条分支各有独立异常类型，互不遮蔽：

    * 零冲突 + 零裁决 ⇒ `merge.merged`（普通 OO→HTML happy path）；
    * 有冲突 + 有裁决 ⇒ :func:`~merge.apply_resolutions` 的折叠结果 ——
      **绝不**是 `merge.merged`（它对每个冲突字段保留 **current** 侧值）；
    * 有冲突 + 零裁决 ⇒ :class:`~conflicts.UnresolvedConflictError`
      （调度层本应先走 conflict 分支；到这里说明分派被破坏，不得自动选边）；
    * 零冲突 + 有裁决 ⇒ :class:`AdjudicationWithoutConflictError`
      （客户端手里的 conflict set 已被 rebase/supersede，静默忽略等于假成功）。

    做成**模块级纯函数**而不是方法内几行 `if`，理由与本模块其他纯判据一致：它必须能用
    合成输入逐条喂，否则「正确实现下某分支恒不触发」会让短路它的变异判 GREEN。
    """
    if resolutions and not merge.has_conflicts:
        raise AdjudicationWithoutConflictError(
            f"收到 {len(resolutions)} 条人工裁决，但本次三方 merge 零冲突 —— "
            "客户端手里的 conflict set 已被 rebase 或 supersede；静默按普通 apply 处理"
            "会让审计师看到「裁决成功」而他选的字段根本没参与本次发布（AC 8.5）"
        )
    if merge.has_conflicts and not resolutions:
        raise UnresolvedConflictError(
            f"仍有 {merge.conflict_count} 条未裁决冲突却要求产出发布用 projection —— "
            "调度层应先走 conflict 分支登记冲突并冻结指针（AC 8.11）；"
            "域内绝不自动选 current 或 incoming"
        )
    if not resolutions:
        return merge.merged
    if contract is None:
        raise AdjudicationContractRequiredError(
            f"{len(resolutions)} 条裁决需要按 per-entry contract 的行身份与保护策略折叠，"
            "但调用方没有给 contract —— 缺 contract 时无法判定「整行删除」与「受保护字段"
            "只许 keep_current」，只能 fail closed（AC 6.6 / 8.3）"
        )
    return apply_resolutions(merge, resolutions, contract=contract)


def assert_projection_result_has_approved_contract(
    bundle: DefinitionBundleSnapshot,
) -> None:
    """projection-based result **立即**要求 approved contract child（AC 8.12 末句）。

    与 `representations.assert_bundle_snapshot_finalizable` 的同类判据并存且不冗余：

    * 本函数在 coordinator **入口**跑 —— 于是「缺 approved contract」在打开 substrate、
      extract、merge 之前就失败，一次 adapter 调用都没有；
    * `assert_bundle_snapshot_finalizable` 在 Task 15 的 commit 里跑 —— 那已经是
      materialize 之后。

    「立即失败」是 Task 26 正文的原文要求，判据因此是**零 adapter 调用 + 本模块的
    error_code**，而不是「最终有没有报错」。守卫 `test_missing_approved_contract_child_
    fails_before_any_adapter_call` 同时断言这两件事。
    """
    if bundle.authority_model is not AuthorityModel.projection_contract:
        return
    slot = bundle.slots.get(BundleSlot.contract)
    if slot is None:
        raise ApprovedContractChildMissingError(
            f"bundle {bundle.bundle_id} 缺 contract typed slot —— slot omission 必须 "
            "fail closed（Requirement 2.3）"
        )
    if not slot.is_definition:
        raise ApprovedContractChildMissingError(
            f"projection-based result 的 bundle {bundle.bundle_id} 的 contract slot 是 "
            f"typed null marker {slot.slot_type!r} 而不是 approved definition child —— "
            "marker 不得冒充 per-entry contract，立即失败（AC 8.12）"
        )
    if not is_digest(slot.slot_digest):
        raise ApprovedContractChildMissingError(
            f"contract slot digest 非法（空串/全零/非小写 hex）: {slot.slot_digest!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 最终授权 fence
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class LiveAuthorizationFacts:
    """**当下**（不是打开时）的授权事实。由 :class:`AuthorizationProbe` 现场观测。"""

    project_visible: bool
    workflow_locked: bool
    room_generation: int
    room_write_fence_epoch: int
    room_state: str
    room_refresh_required: bool
    initiator_participant_id: uuid.UUID | None
    initiator_permission_epoch: int
    initiator_state: str
    contributor_snapshot_digest: str
    current_definition_bundle_id: uuid.UUID
    current_definition_bundle_sha256: str
    close_leader_eligibility_epoch: int
    #: 观测发生的时刻 —— 进 evidence/timeline，不参与比对。
    observed_at: datetime = field(default_factory=_now)


@runtime_checkable
class AuthorizationProbe(Protocol):
    """project visibility / workflow lock 的**外部**观测口。

    visibility 与 workflow lock 不在同步域里（它们属 procedure/visibility 隔离域），
    因此必须注入。做成 Protocol 而不是可选回调：可选即默认放行，而 AC 10.10 没有例外。

    实现必须**真查**。返回硬编码 `True/False` 的实现会被
    `test_probe_must_actually_execute` 抓到（它注入一个记录调用的探针并断言调用发生，
    且 `observed_at` 落在本次 apply 的时间窗内）。
    """

    async def observe(
        self, *, project_id: uuid.UUID, wp_id: uuid.UUID, entry_id: str
    ) -> Mapping[str, Any]: ...


#: participant 仍可为本次 application 背书的状态。`closing` 在内：clean close 的
#: predecessor forcesave 正是在 participant 已转 `closing` 之后才回调的（AC 4.10）。
_INITIATOR_LIVE_STATES: Final[frozenset[ParticipantState]] = frozenset(
    {ParticipantState.active, ParticipantState.closing}
)


def assert_final_authorization(
    *, frozen: FrozenApplicationIdentity, observed: LiveAuthorizationFacts
) -> tuple[str, ...]:
    """AC 10.10 的十条重验，**顺序固定、逐条独立**。返回实际比较过的项名序列。

    返回值不是日志：Property 43 要求「打开后撤销授权、改变 visibility/workflow lock、
    提升 write fence、supersede generation 或替换 current approved bundle」**每一种**
    都必须失败。只断言「抛了 FinalFenceError」时，把其中九条删掉守卫照样绿（剩下那条
    会顶上来）。守卫因此按 `error_code` 逐条断言，并用本返回值断言「前面几条真的比过了」。
    """
    compared: list[str] = []

    compared.append("project_visible")
    if not observed.project_visible:
        raise ProjectNotVisibleError(
            f"project {frozen.project_id} 当前对本次 application 不可见 —— "
            "打开后撤销授权必须在 DB commit 前失败（AC 10.10 / Property 43）"
        )

    compared.append("workflow_locked")
    if observed.workflow_locked:
        raise WorkflowLockedError(
            f"wp {frozen.wp_id} 的 workflow 已锁定（复核锁定/归档）—— 不得提交内容"
        )

    compared.append("room_generation")
    if int(observed.room_generation) != int(frozen.generation):
        raise GenerationSupersededError(
            f"room generation 已由 {frozen.generation} 变为 {observed.room_generation} —— "
            "generation supersede 后旧 application 不得提交"
        )

    compared.append("write_fence_epoch")
    if int(observed.room_write_fence_epoch) != int(frozen.frozen_write_fence_epoch):
        raise WriteFenceAdvancedError(
            f"write fence 已由 {frozen.frozen_write_fence_epoch} 提升到 "
            f"{observed.room_write_fence_epoch} —— 期间有 writer 被撤销"
        )

    compared.append("initiator_present")
    if frozen.frozen_initiator_participant_id is None:
        raise FrozenInitiatorMissingError(
            f"application {frozen.application_id} 的 origin request 没有 initiating "
            "participant —— system/route identity 不可代替用户授权（AC 10.10）"
        )
    if observed.initiator_participant_id is None:
        raise InitiatorMissingError(
            f"当下已观测不到 initiating participant "
            f"{frozen.frozen_initiator_participant_id}（已被删除或不属于本 room）"
        )
    if observed.initiator_participant_id != frozen.frozen_initiator_participant_id:
        raise InitiatorMissingError(
            f"观测到的 initiator {observed.initiator_participant_id} 与 request 冻结的 "
            f"{frozen.frozen_initiator_participant_id} 不是同一人"
        )

    compared.append("initiator_permission_epoch")
    if int(observed.initiator_permission_epoch) != int(
        frozen.frozen_initiator_permission_epoch
    ):
        raise InitiatorEpochChangedError(
            f"initiator permission epoch 已由 {frozen.frozen_initiator_permission_epoch} "
            f"变为 {observed.initiator_permission_epoch}"
        )

    compared.append("initiator_state")
    initiator_state = ParticipantState(observed.initiator_state)
    if initiator_state not in _INITIATOR_LIVE_STATES:
        raise InitiatorNotLiveError(
            f"initiator participant state={initiator_state.value}，不在 "
            f"{sorted(s.value for s in _INITIATOR_LIVE_STATES)} 内 —— "
            "撤销/过期/离开的用户不得为本次 application 背书"
        )

    compared.append("contributor_snapshot_digest")
    if observed.contributor_snapshot_digest.strip() != (
        frozen.contributor_snapshot_digest.strip()
    ):
        raise ContributorSnapshotDriftError(
            "contributor snapshot digest 与 application 冻结值不符 —— "
            "聚合文档的贡献者集合在期间变化，归属无法判定"
        )

    compared.append("approved_bundle_identity")
    if (
        observed.current_definition_bundle_id != frozen.definition_bundle_id
        or observed.current_definition_bundle_sha256.strip()
        != frozen.definition_bundle_sha256.strip()
    ):
        raise ApprovedBundleReplacedError(
            f"entry 的 current approved bundle 已换成 "
            f"{observed.current_definition_bundle_id}/"
            f"{observed.current_definition_bundle_sha256[:12]}…，与 application 冻结的 "
            f"{frozen.definition_bundle_id}/{frozen.definition_bundle_sha256[:12]}… 不符"
        )

    # ── eligibility（AC 10.10 末句：leader 已 promotion 后授权 stale）─────────
    #
    # 🔴 只有 `kind=close_capture` 有 leader 资格快照。普通 forcesave 从来不经 leader
    # 仲裁，拿 room 的 epoch 跟它比就是拿一个与它无关的量当判据 —— 而「无关量恒相等」
    # 正是重言式。因此两条路径分开，且**各自留下可观测的项名**：只在一条路径上
    # append 时，另一条路径的行为在返回值里看不见 ⇒ 删掉它变异检验判 GREEN。
    if frozen.frozen_request_kind is RequestKind.close_capture:
        compared.append("close_leader_eligibility_epoch")
        if frozen.frozen_close_leader_eligibility_epoch is None:
            raise CloseCaptureEligibilityUnprovenError(
                f"close-capture request {frozen.origin_request_id} 没有 promotion 时的 "
                "eligibility epoch（append-only close intent event 里找不到 "
                "`to_state=promoted`）—— 无从证明该 leader 曾合法，不得提交"
            )
        if int(observed.close_leader_eligibility_epoch) != int(
            frozen.frozen_close_leader_eligibility_epoch
        ):
            raise EligibilityEpochAdvancedError(
                "close leader eligibility epoch 已由 "
                f"{frozen.frozen_close_leader_eligibility_epoch} 变为 "
                f"{observed.close_leader_eligibility_epoch} —— leader 在 promotion 之后"
                "失去资格，唯一 request/application 必须进入 authorization_stale 并 "
                "supersede/recovery，不得接任再造第二个 capture（AC 10.10）"
            )
    else:
        compared.append("close_leader_eligibility_not_applicable")
    return tuple(compared)


def assert_incoming_row_unchanged(
    *,
    artifact_id: uuid.UUID,
    observed_kind: str,
    observed_state: str,
    observed_published_at: datetime | None,
    observed_relative_path: str,
    observed_sha256: str,
    expected_relative_path: str,
    expected_sha256: str,
) -> None:
    """commit 后 incoming artifact 行必须**逐列**与打开时相同（Property 65 / AC 8.10）。

    🔴 为什么是模块级纯函数而不是留在 coordinator 方法里：正确实现下这五条判据在
    happy path 上**全都不触发**，于是短路任何一条都观察不到差别 ⇒ 变异检验判 GREEN
    （M33 首轮实测如此）。抽成纯函数后可以用合成输入逐条喂，每条都可证伪。
    Task 24 为同一形态把三条判据从方法里抽出来过。
    """
    drift: list[str] = []
    if observed_kind != ArtifactKind.incoming.value:
        drift.append(f"kind {ArtifactKind.incoming.value}→{observed_kind}")
    if observed_state != ArtifactState.durable.value:
        drift.append(f"state {ArtifactState.durable.value}→{observed_state}")
    if observed_published_at is not None:
        drift.append(f"published_at 被写成 {observed_published_at!r}")
    if (observed_relative_path or "") != expected_relative_path:
        drift.append(f"relative_path {expected_relative_path!r}→{observed_relative_path!r}")
    if (observed_sha256 or "") != expected_sha256:
        drift.append(f"sha256 {expected_sha256[:12]}…→{(observed_sha256 or '')[:12]}…")
    if drift:
        raise IncomingMutatedError(
            f"incoming artifact {artifact_id} 在本次 apply 中被改动（{'; '.join(drift)}）—— "
            "incoming 永不晋升、永不被复制标记为 published/current、"
            "永不被 resolver 直接采用（AC 8.10 / Property 65）"
        )


def assert_published_digest_was_approved(
    *, approved_sha256: str | None, published_sha256: str
) -> None:
    """落库的 result artifact digest 必须**正是** fence 放行的那一份（AC 8.10）。

    同 :func:`assert_incoming_row_unchanged`：happy path 恒相等 ⇒ 留在方法里不可证伪。
    `approved_sha256` 为 None 表示 publish 前的 fence 根本没跑过 —— 那是顺序被破坏，
    单独一个错误类型（:class:`ApplyStageOrderError`），与「digest 被偷换」分型。
    """
    if approved_sha256 is None:
        raise ApplyStageOrderError(
            "publish 前的 fence 没有记录被放行的 artifact digest —— 顺序被破坏"
        )
    if published_sha256.strip() != approved_sha256.strip():
        raise ResultArtifactDigestError(
            f"落库的 result artifact digest {published_sha256!r} 与 fence 放行的 "
            f"{approved_sha256!r} 不同 —— publish 与 fence 之间被偷换"
        )


def assert_canonical_fence_points_at(
    *, advanced_application_id: uuid.UUID | None, expected_application_id: uuid.UUID
) -> None:
    """room canonical fence 必须与 server last-applied 原子同步（AC 10.11）。

    同上：happy path 恒相等。不同步的后果很具体 —— Task 27 的 resolve **先比 canonical
    application identity**，读到「server 已推进、fence 还指着上一个 application」的中间态
    会把一次合法 resolve 判成 stale。
    """
    if advanced_application_id != expected_application_id:
        raise ResultBundleIdentityError(
            f"room canonical fence 指向 {advanced_application_id}，不是本次 application "
            f"{expected_application_id} —— server last-applied 与 canonical fence 必须"
            "原子同步（AC 10.11）"
        )


def settlement_digest_pair(
    *,
    merge: MergeOutcome,
    incoming: Projection,
    merged_digest: str,
    incoming_digest: str,
) -> tuple[str, str]:
    """把 Task 14 的 **managed 等值裁决** 翻译成 `settle_client_baseline` 的 digest 对。

    为什么需要翻译，而不是直接把两个 digest 丢过去：

    * Task 15 的 `_advance_room` 用 `MergeOutcome.requires_client_refresh(incoming)`
      判断要不要 refresh —— 那是**受管字段级**比较（`values_equal`，排除 `word_only`）；
    * `RoomService.settle_client_baseline` 的判据是两个 digest **字节相等** —— 那是
      **整份 projection** 比较（含 `word_only` 键，且 `Decimal("1.50")` 与
      `Decimal("1.5")` 序列化后不同）。

    两个口径在 Word 底稿与金额格式差异上会分叉，于是同一次 apply 可能出现「Task 15 没
    标 refresh，而 Task 21 标了」的半状态。裁决只能有一个，本函数把它固定为 Task 14 的
    那一个：

    * 裁决「不等值」⇒ 原样给出两个 digest（受管键是 payload 的子集，受管键不同 ⇒
      整份 digest 必不同，故 `settle_client_baseline` 也会判不等）；
    * 裁决「等值」⇒ 两侧都给 `merged_digest`，即**如实告知裁决结果**。
      `settle_client_baseline` 只持久化 `merged_projection_sha256`
      （写入 `room.client_confirmed_projection_sha256`），`incoming_projection_sha256`
      仅参与比较、不落库，因此这样传不会把任何假值写进数据库。
      真实的 incoming digest 由 coordinator 另写进
      `application.incoming_projection_sha256`。
    """
    if merge.requires_client_refresh(incoming):
        return merged_digest, incoming_digest
    return merged_digest, merged_digest


# ═══════════════════════════════════════════════════════════════════════════
# 4. 结构判据：substrate 解析只许读 application FK；retry 不许碰 Command Service
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 为什么这两条只能用 AST，不能用运行期观察：
#
# 「不得用 room pointer / registry alias / candidate / operation path 猜 substrate」
# 禁止的是**代码形态**。猜错的实现在运行期照样能读出一个存在的文件、算出一个合法的
# projection、走完全流程 —— 只有在「room pointer 恰好指向另一个 application」时才会
# 出现事故，而那正是无法在测试里稳定构造的时序。同理，「retry 不得再 forcesave」
# 在没有真实 OO 的测试环境里观察不到（HTTP 调用会失败，但失败也可能被吞）。
#
# Task 23 的 `assert_authorization_first_source_shape` 是同一形态的先例。

#: 解析 substrate 时**允许**调用的 repository 方法。多一个就等于多读一张业务表。
_SUBSTRATE_ALLOWED_REPO_CALLS: Final[frozenset[str]] = frozenset({"assert_incoming_durable"})

#: 解析 substrate 的源码里**禁止**出现的属性名（room pointer / alias / candidate / operation）。
_SUBSTRATE_FORBIDDEN_ATTRS: Final[tuple[str, ...]] = (
    "last_applied_version_id",
    "latest_durable_application_id",
    "latest_durable_sequence",
    "client_confirmed_representation_id",
    "opened_base_version_id",
    "resolve_alias",
    "current_alias",
    "staged_artifact_id",
    "candidate_id",
    "duplicate_of_operation_id",
)

#: 禁止出现在本模块任何位置的 Command Service 符号（Property 38：retry 零 forcesave）。
_COMMAND_SERVICE_SYMBOLS: Final[tuple[str, ...]] = (
    "command_service",
    "CommandService",
    "forcesave",
    "issue_forcesave",
    "OnlyOfficeCommandService",
)


def _dedent_source(obj: Any) -> str:
    return textwrap.dedent(inspect.getsource(obj))


def _repo_calls_in(tree: ast.AST) -> set[str]:
    """`self._repo.X(...)` / `repo.X(...)` 形态的被调方法名集合。"""
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        owner = func.value
        owner_name = ""
        if isinstance(owner, ast.Attribute):
            owner_name = owner.attr
        elif isinstance(owner, ast.Name):
            owner_name = owner.id
        if owner_name in ("_repo", "repo"):
            found.add(func.attr)
    return found


def assert_substrate_resolution_source_shape() -> tuple[str, ...]:
    """AST 反查：substrate 解析只许经 `application.incoming_artifact_id`。

    返回解析函数实际调用到的 repository 方法名（正常恰为 ``('assert_incoming_durable',)``）。

    三条判据合在一起，因为它们是同一件事的三个逃逸口：

    1. 源码里不得出现 :data:`_SUBSTRATE_FORBIDDEN_ATTRS` 里的任何属性名 ——
       「读 room pointer / alias / candidate / operation 指针」的直接形态；
    2. 对 repository 的调用集合必须是 :data:`_SUBSTRATE_ALLOWED_REPO_CALLS` 的子集 ——
       多调一个仓储方法就是多读一张表，而那种写法**不会**出现被禁属性名
       （例如 `await self._repo.lock_room(...)` 之后再取 `.state`）；
    3. 必须真的出现 `incoming_artifact_id` —— 否则「什么都不读」也能通过前两条。
    """
    src = _dedent_source(OoToHtmlCoordinator.open_substrate)
    tree = ast.parse(src)

    hits = [name for name in _SUBSTRATE_FORBIDDEN_ATTRS if name in src]
    if hits:
        raise SubstrateOriginForbiddenError(
            f"`open_substrate` 源码里出现了被禁符号 {hits} —— substrate 只能来自 "
            "`application.incoming_artifact_id`，不得用 callback 到达时的 room pointer、"
            "registry 当前 alias、upgrade candidate 或 operation 路径反猜（AC 4.3 / 8.10）"
        )
    calls = _repo_calls_in(tree)
    extra = sorted(calls - _SUBSTRATE_ALLOWED_REPO_CALLS)
    if extra:
        raise SubstrateOriginForbiddenError(
            f"`open_substrate` 调用了白名单外的 repository 方法 {extra} —— "
            f"只允许 {sorted(_SUBSTRATE_ALLOWED_REPO_CALLS)}"
        )
    if "incoming_artifact_id" not in src:
        raise SubstrateOriginForbiddenError(
            "`open_substrate` 源码里没有出现 `incoming_artifact_id` —— "
            "「什么都不读」不能算通过来源判据"
        )
    return tuple(sorted(calls))


#: fence 回调 → 它**必须首先调用**的轨迹前置断言。
#:
#: 🔴 为什么需要这张表：`ApplyJournal.assert_publish_precondition()` 在正确实现下
#: 恒不触发（happy path 的轨迹永远齐全），所以把那一行删掉在**运行期观察不到**
#: ⇒ 变异检验判 GREEN（M30 首轮实测如此）。它保护的是「代码形态」——
#: 「publish 前必须先证明三方 extract 与 merge 真的发生过」——
#: 因此判据也必须是形态：回调体的**第一条语句**就是那个断言。
_REQUIRED_FIRST_ASSERTION: Final[Mapping[str, str]] = {
    "_fence_before_publish": "assert_publish_precondition",
    "_fence_before_write": "assert_write_precondition",
}


def assert_fence_callbacks_assert_order_first() -> tuple[tuple[str, str], ...]:
    """AST 反查：两个 fence 回调的**第一条语句**必须是对应的轨迹前置断言。

    返回实际观测到的 `(方法名, 首条语句里调用的断言名)` 序列。

    「第一条」不是洁癖：断言若排在 `observe_live_authorization()` 之后，那次探针调用
    与那次 DB 读取就已经发生在一条顺序已被破坏的轨迹上；而 `assert_write_precondition`
    若排在 fence 比对之后，「先写库再验授权」在轨迹上就成立了。
    """
    observed: list[tuple[str, str]] = []
    for method, expected in _REQUIRED_FIRST_ASSERTION.items():
        src = _dedent_source(getattr(OoToHtmlCoordinator, method))
        tree = ast.parse(src)
        func = tree.body[0]
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):  # pragma: no cover
            raise ApplyStageOrderError(f"{method} 不是函数定义")
        body = [
            stmt
            for stmt in func.body
            if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
        ]
        if not body:
            raise ApplyStageOrderError(f"{method} 函数体为空 —— 轨迹前置断言被删除")
        first = body[0]
        called = ""
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Call):
            func_node = first.value.func
            if isinstance(func_node, ast.Attribute):
                called = func_node.attr
        if called != expected:
            raise ApplyStageOrderError(
                f"{method} 的第一条语句是 {ast.unparse(first)[:80]!r}，"
                f"不是 `{expected}()` —— publish/写库前的轨迹前置断言被删除或后移。"
                "该断言在 happy path 上恒不触发，所以只有形态判据能证伪它"
            )
        observed.append((method, called))
    return tuple(observed)


def assert_no_command_service_reference() -> tuple[str, ...]:
    """AST 反查：本模块任何位置都不得引用 Command Service（Property 38）。

    返回模块内出现过的 `import` 模块名（供守卫断言 `command_service` 不在其中）。

    判据用**整模块源码 + import 清单**双重形态，而不是只查 import：`forcesave` 也可能
    通过已注入的 `RoomService`/repository 间接调到（例如
    `await self._rooms._repo.some_forcesave_helper(...)`），那种写法没有新 import。
    """
    src = _dedent_source(_module_self())
    tree = ast.parse(src)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)

    # 判据是**完整标识符相等**，不是子串包含。两条具体理由：
    #   * docstring 里写了 `forcesave`（解释为什么不调它）—— `_collect_identifiers`
    #     从 AST 收集，天然不含字符串与注释；
    #   * `next_forcesave_allowed`（本模块的 outcome 字段）与
    #     `assert_no_command_service_reference`（本函数自己）都**包含**被禁子串。
    #     子串匹配会让这条判据恒红 —— 恒红的守卫和恒绿一样没用。
    identifiers = _collect_identifiers(tree)
    hits = sorted(set(_COMMAND_SERVICE_SYMBOLS) & identifiers)
    if hits:
        raise OoToHtmlError(
            f"本模块出现 Command Service 符号 {hits} —— durable incoming 的 retry 一律"
            "不再调用 OnlyOffice forcesave（Property 38 / AC 8.9）"
        )
    bad_imports = sorted(m for m in modules if "command_service" in m)
    if bad_imports:
        raise OoToHtmlError(f"本模块 import 了 Command Service 模块 {bad_imports}")
    return tuple(sorted(modules))


def _module_self() -> Any:
    """本模块对象（`inspect.getsource` 的入参）。"""
    import sys

    return sys.modules[__name__]


def _collect_identifiers(tree: ast.AST) -> set[str]:
    """AST 里出现过的**完整标识符**集合（不含注释、不含字符串字面量）。

    直接对源码做正则剥注释会漏掉三引号字符串里的 `#`，而本模块的 docstring 里确实
    出现 `forcesave` 这个词（在解释「为什么不调它」）。从 AST 收集
    Name / Attribute / keyword / def / class / import alias，就只剩真正的符号引用。
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.alias):
            names.add(node.name)
            if node.asname:
                names.add(node.asname)
    return names


# ═══════════════════════════════════════════════════════════════════════════
# 5. 执行轨迹（不可交换顺序 = 运行期事实）
# ═══════════════════════════════════════════════════════════════════════════


class ApplyStage(str, Enum):
    """一次 OO→HTML apply 的有序阶段。"""

    authorized = "authorized"
    canonicalized = "canonicalized"
    application_locked = "application_locked"
    frozen_identity_loaded = "frozen_identity_loaded"
    contract_child_verified = "contract_child_verified"
    substrate_opened = "substrate_opened"
    base_extracted = "base_extracted"
    current_extracted = "current_extracted"
    incoming_extracted = "incoming_extracted"
    merged = "merged"
    conflict_recorded = "conflict_recorded"
    fence_verified_before_publish = "fence_verified_before_publish"
    fence_verified_before_write = "fence_verified_before_write"
    application_result_written = "application_result_written"
    business_committed = "business_committed"
    baseline_settled = "baseline_settled"
    generation_superseded = "generation_superseded"
    post_durable_error_recorded = "post_durable_error_recorded"
    responded = "responded"


@dataclass
class ApplyJournal:
    """有序阶段轨迹。把「顺序」变成运行期可断言事实，而不是注释。"""

    entries: list[tuple[ApplyStage, str]] = field(default_factory=list)

    def record(self, stage: ApplyStage, detail: str = "") -> None:
        self.entries.append((stage, detail))

    @property
    def order(self) -> tuple[ApplyStage, ...]:
        return tuple(s for s, _ in self.entries)

    def has(self, stage: ApplyStage) -> bool:
        return stage in self.order

    def index_of(self, stage: ApplyStage) -> int:
        return self.order.index(stage)

    def assert_extract_precondition(self) -> None:
        """extract 之前必须已打开 substrate（不得先 extract 再补准入校验）。"""
        if not self.has(ApplyStage.substrate_opened):
            raise ApplyStageOrderError(
                "extract 必须在 substrate 准入通过之后执行；当前轨迹="
                f"{[s.value for s in self.order]}"
            )

    def assert_publish_precondition(self) -> None:
        """publish 之前：substrate 已开、三方已 merge，且 fence 尚未验过（防重复放行）。"""
        for required in (
            ApplyStage.substrate_opened,
            ApplyStage.base_extracted,
            ApplyStage.current_extracted,
            ApplyStage.incoming_extracted,
            ApplyStage.merged,
        ):
            if not self.has(required):
                raise ApplyStageOrderError(
                    f"publish 前置阶段缺 {required.value}；当前轨迹="
                    f"{[s.value for s in self.order]}"
                )
        if self.has(ApplyStage.fence_verified_before_publish):
            raise ApplyStageOrderError(
                "同一次 apply 里 publish 前的 fence 被验了两次 —— 说明 commit 被重入"
            )

    def assert_write_precondition(self) -> None:
        """写库前的 fence 必须**晚于** publish 前的 fence（两道都不可省）。"""
        if not self.has(ApplyStage.fence_verified_before_publish):
            raise ApplyStageOrderError(
                "写库前的 fence 早于 publish 前的 fence（或后者根本没跑）—— "
                "AC 8.10 要求先 extract 等值/未管理区域，再 fence，再 publish，"
                "最后进 DB commit 前**再**验一次"
            )
        if self.has(ApplyStage.fence_verified_before_write):
            raise ApplyStageOrderError("写库前的 fence 被验了两次 —— commit 被重入")

    def assert_no_publish_after_conflict(self) -> None:
        """有冲突时不得走到 publish/commit（AC 8.11：指针一律不动）。"""
        if not self.has(ApplyStage.conflict_recorded):
            return
        idx = self.index_of(ApplyStage.conflict_recorded)
        for later in (
            ApplyStage.fence_verified_before_publish,
            ApplyStage.business_committed,
        ):
            if self.has(later) and self.index_of(later) > idx:
                raise ApplyStageOrderError(
                    f"冲突已登记却仍执行了 {later.value} —— 未裁决冲突不得提交内容"
                )


class OoToHtmlResult(str, Enum):
    """一次 apply 的终态（与 operation/application 的 logical result 一致）。"""

    applied = "applied"
    conflict = "conflict"
    refresh_required = "refresh_required"
    error = "error"
    authorization_stale = "authorization_stale"


@dataclass(frozen=True)
class ThreeWayInputs:
    """三方 merge 的输入及其**来源身份**（每一侧都必须说得出自哪个 artifact）。"""

    base: Projection
    current: Projection
    incoming: Projection
    base_representation_id: uuid.UUID
    current_representation_id: uuid.UUID
    incoming_artifact_id: uuid.UUID
    contract: SyncContract
    bundle: DefinitionBundleSnapshot


@dataclass(frozen=True)
class OoToHtmlOutcome:
    """一次 OO→HTML apply 的完整结果。

    `callback_response_error` 恒为 0：本模块只在 incoming **已 durable** 之后被调用，
    而 Task 4 实测 OO 对非零 error 不重投 ⇒ durable 之后返回非零等于静默丢件
    （AC 5.7/5.8 / Property 19）。
    """

    result: OoToHtmlResult
    application_id: uuid.UUID
    canonical_operation_id: uuid.UUID
    requested_operation_id: uuid.UUID
    followed_duplicate: bool
    attempt: int
    substrate: ReadOnlySubstrate
    merge: MergeOutcome | None
    conflict_count: int
    conflict_set_digest: str | None
    #: 本次落库/更新的冲突行数（AC 8.1）。只记摘要不落行时它恒为 0 —— 预览就没数据。
    conflict_rows_written: int
    #: 本轮不再出现、被打 `superseded_at` 的旧冲突行数（rebase 后冲突变少的可见证据）。
    conflict_rows_superseded: int
    #: 本次折叠进 merged projection 的裁决条数（AC 8.6 的「选择结果」计数）。
    resolutions_applied: int
    content_version_id: uuid.UUID | None
    result_revision: int | None
    result_representation_id: uuid.UUID | None
    result_artifact_sha256: str | None
    merged_projection_sha256: str | None
    incoming_projection_sha256: str | None
    server_last_applied_advanced: bool
    client_baseline_advanced: bool
    room_refresh_required: bool
    room_superseded: bool
    next_forcesave_allowed: bool
    fence_compared_before_publish: tuple[str, ...]
    fence_compared_before_write: tuple[str, ...]
    callback_response_error: int
    error_code: str | None
    error_stage: str | None
    #: 失败原文（截断）。Requirement 5.12 要求解析异常必须留下可定位诊断，
    #: 只留 `error_code` 时「TypeError 出在哪一行」这类接线错误无从追。
    error_detail: str | None
    stages: tuple[ApplyStage, ...]

    @property
    def reload_floor_revision(self) -> int | None:
        """前端 `reloadHtml` 的最低 revision（P14）。

        `applied` 时等于 `application.result_revision`；其余终态为 None ——
        「没有 applied 结果」与「revision 0」必须可分辨，否则前端会去加载 revision 0。
        """
        return self.result_revision if self.result is OoToHtmlResult.applied else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "result": self.result.value,
            "application_id": str(self.application_id),
            "canonical_operation_id": str(self.canonical_operation_id),
            "requested_operation_id": str(self.requested_operation_id),
            "followed_duplicate": self.followed_duplicate,
            "attempt": self.attempt,
            "substrate_artifact_id": str(self.substrate.artifact_id),
            "substrate_origin": self.substrate.origin.value,
            "conflict_count": self.conflict_count,
            "conflict_set_digest": self.conflict_set_digest,
            "conflict_rows_written": self.conflict_rows_written,
            "conflict_rows_superseded": self.conflict_rows_superseded,
            "resolutions_applied": self.resolutions_applied,
            "content_version_id": (
                str(self.content_version_id) if self.content_version_id else None
            ),
            "result_revision": self.result_revision,
            "result_representation_id": (
                str(self.result_representation_id) if self.result_representation_id else None
            ),
            "result_artifact_sha256": self.result_artifact_sha256,
            "merged_projection_sha256": self.merged_projection_sha256,
            "incoming_projection_sha256": self.incoming_projection_sha256,
            "server_last_applied_advanced": self.server_last_applied_advanced,
            "client_baseline_advanced": self.client_baseline_advanced,
            "room_refresh_required": self.room_refresh_required,
            "room_superseded": self.room_superseded,
            "next_forcesave_allowed": self.next_forcesave_allowed,
            "fence_compared_before_publish": list(self.fence_compared_before_publish),
            "fence_compared_before_write": list(self.fence_compared_before_write),
            "callback_response_error": self.callback_response_error,
            "error_code": self.error_code,
            "error_stage": self.error_stage,
            "error_detail": self.error_detail,
            "reload_floor_revision": self.reload_floor_revision,
            "stages": [s.value for s in self.stages],
        }


# ═══════════════════════════════════════════════════════════════════════════
# 6. coordinator
# ═══════════════════════════════════════════════════════════════════════════


class _ApplyFence:
    """:class:`~.content_mutation.CommitFenceHook` 的实现体。

    三个回调点各自只做一件事，全部委派 coordinator 的方法 —— hook 自身不含判据，
    所以「换一个 hook 实现绕过 fence」在类型层还成立，但在**调用方**不成立：
    :meth:`OoToHtmlCoordinator._apply_no_conflict` 只构造本类。
    """

    def __init__(self, coordinator: "OoToHtmlCoordinator", state: "_ApplyState") -> None:
        self._c = coordinator
        self._s = state

    async def before_publish(
        self,
        *,
        artifact_sha256: str,
        structure_hash: str,
        identity_inventory_sha256: str,
        extracted_key_count: int,
    ) -> None:
        await self._c._fence_before_publish(
            self._s,
            artifact_sha256=artifact_sha256,
            structure_hash=structure_hash,
            identity_inventory_sha256=identity_inventory_sha256,
            extracted_key_count=extracted_key_count,
        )

    async def before_write(self, *, current_revision: int) -> None:
        await self._c._fence_before_write(self._s, current_revision=current_revision)

    async def after_pointers(self, facts: CommitTransactionFacts) -> None:
        await self._c._write_application_result(self._s, facts)


@dataclass
class _ApplyState:
    """一次 apply 的可变工作台（只在本模块内部流转，不外泄）。

    `canonical_operation_id` / `requested_operation_id` 是**纯 UUID 快照**，不是 ORM 行：
    本流程跨多个事务边界，`expire_on_commit=True` 的 session 在 commit 之后访问旧 ORM
    属性（连 PK 也算）会触发隐式 IO，async 下直接 `MissingGreenlet`。
    """

    frozen: FrozenApplicationIdentity
    canonical: CanonicalRead
    canonical_operation_id: uuid.UUID
    requested_operation_id: uuid.UUID
    followed_duplicate: bool
    substrate: ReadOnlySubstrate
    bundle: DefinitionBundleSnapshot
    contract: SyncContract | None
    journal: ApplyJournal
    attempt: int
    actor_id: uuid.UUID | None
    #: 本次调用携带的人工裁决（AC 8.3）。空 = 普通 OO→HTML；非空 = resolve 落地。
    resolutions: tuple[ResolutionChoice, ...] = ()
    merge: MergeOutcome | None = None
    incoming_projection: Projection | None = None
    merged_projection: Projection | None = None
    merged_digest: str | None = None
    incoming_digest: str | None = None
    fence_before_publish: tuple[str, ...] = ()
    fence_before_write: tuple[str, ...] = ()
    approved_result_sha256: str | None = None
    result_facts: CommitTransactionFacts | None = None
    client_baseline_advanced: bool = False
    room_refresh_required: bool = False
    room_superseded: bool = False
    conflict_rows_written: int = 0
    conflict_rows_superseded: int = 0


class OoToHtmlCoordinator:
    """OO→HTML 的唯一编排入口。**不 commit**（唯一 commit 出口在 Task 15）。

    依赖全部显式注入且**没有一个是可选的默认放行**：

    * `repo` / `artifacts` / `resolution` —— Task 10/11/12
    * `content` —— Task 15 的 :class:`ContentMutationService`（唯一 commit 边界）
    * `rooms` —— Task 21 的 :class:`RoomService`（双基线、fence、supersede）
    * `requests` —— Task 23 的 :class:`RequestApplicationService`（授权 → canonicalize）
    * `probe` —— :class:`AuthorizationProbe`，project visibility / workflow lock 的观测口
    """

    def __init__(
        self,
        *,
        repo: WorkpaperSyncRepository,
        artifacts: CanonicalArtifactRepository,
        resolution: CanonicalResolutionService,
        content: ContentMutationService,
        rooms: RoomService,
        requests: RequestApplicationService,
        probe: AuthorizationProbe,
    ) -> None:
        self._repo = repo
        self._session = repo.session
        self._artifacts = artifacts
        self._resolution = resolution
        self._content = content
        self._rooms = rooms
        self._requests = requests
        if probe is None:  # pragma: no cover - 类型层已要求，这里是运行期 fail-closed
            raise AuthorizationProbeFailedError(
                "AuthorizationProbe 是必填依赖：可选即等于默认放行，而 AC 10.10 没有例外"
            )
        self._probe = probe

    # ─────────────────────────────────────────────────────────────────
    # 6.1 substrate：唯一来源 + 三层拒绝的第二层
    # ─────────────────────────────────────────────────────────────────

    async def open_substrate(
        self, frozen: FrozenApplicationIdentity
    ) -> ReadOnlySubstrate:
        """只从 `application.incoming_artifact_id` 打开只读 substrate。

        本方法的源码形态由 :func:`assert_substrate_resolution_source_shape` 钉死：
        不得出现 room pointer / registry alias / candidate / operation 指针，
        对 repository 的调用集合只允许 `assert_incoming_durable`。

        三层拒绝在这里对齐第二层与第三层：

        1. **application FK / DB 层** —— V151 的 `wpsync_check_application_identity`
           与 `repo.assert_incoming_durable`。它的**生产首发位置是 correlate**
           （Task 22/23 创建 application 时），所以 quarantined 根本形不成 application；
           本方法仍再调一次作为 FK 层的当场复核。
        2. **coordinator 入口层** —— :func:`assert_coordinator_substrate_admissible`，
           另有 `origin` / `resolved_id == declared_id` / `published_at` 三条**只属于
           本层**的判据。
        3. **engine 层** —— `assert_substrate_usable(role=incoming, …)`（Task 13），
           保护「有人自己拼 `ContentCommitPlan`」。

        🔴 第 2 步在第 1 步**之前**，不是风格问题。反过来写（先调
        `assert_incoming_durable`）会让本层的 quarantine 分支变成 provably-dead ——
        DB 层先抛 `QuarantinedIncomingError`，于是「删掉本层」在变异检验里判 GREEN，
        下一个人会据此以为本层是冗余的。行不存在时本层无从判断（没有行可看），
        故那一条单独前置。
        """
        artifact_id = frozen.incoming_artifact_id
        row = (
            await self._session.execute(
                sa.select(WorkpaperArtifact).where(WorkpaperArtifact.id == artifact_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise SubstrateOriginForbiddenError(
                f"application 固定的 incoming artifact {artifact_id} 行不存在 —— "
                "FK 已被破坏，不得回退到「按 room pointer 找一个能用的」"
            )
        assert_coordinator_substrate_admissible(
            origin=LEGAL_SUBSTRATE_ORIGIN,
            artifact_kind=row.kind,
            artifact_state=row.state,
            durable_at=row.durable_at,
            published_at=row.published_at,
            declared_incoming_artifact_id=artifact_id,
            resolved_artifact_id=row.id,
        )
        await self._repo.assert_incoming_durable(artifact_id)
        assert_substrate_usable(
            role=SubstrateRole.incoming,
            artifact_kind=row.kind,
            artifact_state=row.state,
        )
        # `relative_path` 是**相对 base_root** 的（`ArtifactStorageLayout.relative_of`
        # 就是这么产出的），所以先按 base_root 解析边界，再单独核对项目归属 ——
        # 与 `resolve_published_artifact` 同一顺序。用 `resolve_within_project`
        # 会把 `storage/{project}/…` 再拼一次项目根，得到一个必然不存在的路径。
        path = self._artifacts.resolve_relative_path(row.relative_path)
        self._artifacts.assert_project_owns(row.project_id, path)
        if not path.exists():
            raise SubstrateFileMissingError(
                f"incoming artifact 行存在但文件缺失: {row.relative_path} —— "
                "durable sealing 与 DB 行不同步（Task 7 db6 证明这在物理上可能）"
            )
        if (row.sha256 or "").strip() != frozen.incoming_sha256.strip():
            raise SubstrateOriginForbiddenError(
                f"incoming artifact digest {row.sha256!r} 与 application 冻结的 "
                f"{frozen.incoming_sha256!r} 不一致 —— 内容身份漂移"
            )
        return ReadOnlySubstrate(
            artifact_id=row.id,
            kind=ArtifactKind(row.kind),
            state=ArtifactState(row.state),
            origin=LEGAL_SUBSTRATE_ORIGIN,
            path=path,
            relative_path=row.relative_path,
            sha256=row.sha256,
            size_bytes=int(row.size_bytes),
            document_type=row.document_type,
            durable_at=row.durable_at,
            published_at=row.published_at,
        )

    # ─────────────────────────────────────────────────────────────────
    # 6.2 frozen identity
    # ─────────────────────────────────────────────────────────────────

    async def load_frozen_identity(
        self, application_id: uuid.UUID
    ) -> FrozenApplicationIdentity:
        """行锁读 application + 其 origin request，逐列冻结成不可变快照。"""
        app = (
            await self._session.execute(
                sa.select(WorkpaperContentApplication)
                .where(WorkpaperContentApplication.id == application_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if app is None:
            raise ApplicationScopeMismatchError(f"application 不存在: {application_id}")
        req = (
            await self._session.execute(
                sa.select(WorkpaperForcesaveRequest).where(
                    WorkpaperForcesaveRequest.id == app.origin_request_id
                )
            )
        ).scalar_one_or_none()
        if req is None:
            raise ApplicationScopeMismatchError(
                f"application {application_id} 的 origin request {app.origin_request_id} 不存在"
            )
        request_kind = RequestKind(req.kind)
        frozen_eligibility = (
            await self._frozen_close_leader_eligibility_epoch(req.id)
            if request_kind is RequestKind.close_capture
            else None
        )
        return FrozenApplicationIdentity(
            application_id=app.id,
            project_id=app.project_id,
            wp_id=app.wp_id,
            entry_id=str(app.entry_id),
            room_id=app.room_id,
            generation=int(app.generation),
            origin_request_id=app.origin_request_id,
            origin_request_sequence=int(app.origin_request_sequence),
            effective_request_sequence=int(app.effective_request_sequence),
            client_edit_epoch=int(app.client_edit_epoch),
            incoming_artifact_id=app.incoming_artifact_id,
            incoming_sha256=str(app.incoming_sha256),
            base_version_id=app.base_version_id,
            base_representation_id=app.base_representation_id,
            current_revision=int(app.current_revision),
            definition_bundle_id=app.definition_bundle_id,
            definition_bundle_sha256=str(app.definition_bundle_sha256),
            authority_model_definition_id=app.authority_model_definition_id,
            authority_model_definition_sha256=str(app.authority_model_definition_sha256),
            adapter_id=str(app.adapter_id),
            adapter_build_digest=str(app.adapter_build_digest),
            contributor_snapshot_digest=str(app.contributor_snapshot_digest),
            state=ApplicationState(app.state),
            frozen_write_fence_epoch=int(req.write_fence_epoch),
            frozen_initiator_participant_id=req.initiated_by_participant_id,
            frozen_initiator_permission_epoch=int(req.initiator_permission_epoch),
            frozen_client_base_projection_sha256=str(req.client_base_projection_sha256),
            frozen_request_kind=request_kind,
            frozen_close_leader_eligibility_epoch=frozen_eligibility,
        )

    async def _frozen_close_leader_eligibility_epoch(
        self, request_id: uuid.UUID
    ) -> int | None:
        """promotion **当时**冻结的 close leader eligibility epoch。

        来源固定为 append-only 的 `working_paper_oo_close_intent_event`：

        * `close_intent.eligibility_epoch` 是 **intent 创建时**的值。前任 leader 在
          promotion 前失格会让 room 的 epoch +1，于是那一列会低于 promotion 当时的
          epoch —— 拿它当冻结侧会让「合法的 successor 提交」被误判成 stale；
        * `request.idempotency_key`（`close-capture:{room}:{gen}:{epoch}`）虽然也含这个
          数，但那要在 fence 里再写一个字符串解析器 = 第二套算法。

        找不到 `to_state=promoted` 的事件时返回 `None`（由 fence 落
        :class:`CloseCaptureEligibilityUnprovenError`），**不**返回 0 兜底：
        0 与「room 从未失格过」的合法值撞在一起，等于把「无从证明」伪造成「通过」。
        """
        return (
            await self._session.execute(
                sa.select(WorkpaperOoCloseIntentEvent.eligibility_epoch)
                .join(
                    WorkpaperOoCloseIntent,
                    WorkpaperOoCloseIntent.id == WorkpaperOoCloseIntentEvent.intent_id,
                )
                .where(
                    WorkpaperOoCloseIntent.promoted_request_id == request_id,
                    WorkpaperOoCloseIntentEvent.to_state
                    == CloseIntentState.promoted.value,
                )
                .order_by(WorkpaperOoCloseIntentEvent.sequence_no.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    # ─────────────────────────────────────────────────────────────────
    # 6.3 授权探针（无 fail-open）
    # ─────────────────────────────────────────────────────────────────

    async def observe_live_authorization(
        self, frozen: FrozenApplicationIdentity, *, canonical_operation_id: uuid.UUID
    ) -> LiveAuthorizationFacts:
        """现场观测 project/workflow（外部探针）+ room/participant/bundle（本域 DB）。

        🔴 探针异常**不**吞：包成 :class:`AuthorizationProbeFailedError` 抛出。
        `except Exception: logger.warning(...)` 会把接线错误（函数名写错、列名写错、
        单参调用 async 签名）表现成「本项目无此限制」，而 Volar/vitest/get_diagnostics/
        HEAD-swap 四层全绿（Requirement 5.12 点名禁止这种降级）。
        """
        try:
            external = await self._probe.observe(
                project_id=frozen.project_id, wp_id=frozen.wp_id, entry_id=frozen.entry_id
            )
        except Exception as exc:  # noqa: BLE001 - 立即重抛为可诊断类型，不降级
            raise AuthorizationProbeFailedError(
                f"AuthorizationProbe.observe 失败（{type(exc).__name__}: {exc}）—— "
                "不得降级为「本项目无此限制」：那会让接线错误表现成授权通过"
                "（Requirement 5.12）"
            ) from exc
        if not isinstance(external, Mapping):
            raise AuthorizationProbeFailedError(
                f"AuthorizationProbe.observe 必须返回 Mapping，实得 {type(external)!r}"
            )
        for key in ("project_visible", "workflow_locked"):
            if key not in external:
                raise AuthorizationProbeFailedError(
                    f"AuthorizationProbe.observe 返回值缺 {key!r} —— 缺字段不得视为放行"
                )

        room = (
            await self._session.execute(
                sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == frozen.room_id)
            )
        ).scalar_one_or_none()
        if room is None:
            raise GenerationSupersededError(f"room 不存在: {frozen.room_id}")
        participant: WorkpaperOoParticipant | None = None
        if frozen.frozen_initiator_participant_id is not None:
            participant = (
                await self._session.execute(
                    sa.select(WorkpaperOoParticipant).where(
                        WorkpaperOoParticipant.id
                        == frozen.frozen_initiator_participant_id,
                        WorkpaperOoParticipant.room_id == frozen.room_id,
                    )
                )
            ).scalar_one_or_none()

        current_bundle_id, current_bundle_sha = await self._current_entry_bundle(frozen)
        contributors = await self._observed_contributor_digest(
            frozen, operation_id=canonical_operation_id
        )
        return LiveAuthorizationFacts(
            project_visible=bool(external["project_visible"]),
            workflow_locked=bool(external["workflow_locked"]),
            room_generation=int(room.generation),
            room_write_fence_epoch=int(room.write_fence_epoch),
            room_state=str(room.state),
            room_refresh_required=room.refresh_required_at is not None,
            initiator_participant_id=(None if participant is None else participant.id),
            initiator_permission_epoch=(
                -1 if participant is None else int(participant.permission_epoch)
            ),
            initiator_state=(
                ParticipantState.revoked.value if participant is None else str(participant.state)
            ),
            contributor_snapshot_digest=contributors,
            current_definition_bundle_id=current_bundle_id,
            current_definition_bundle_sha256=current_bundle_sha,
            close_leader_eligibility_epoch=int(room.close_leader_eligibility_epoch),
        )

    async def _current_entry_bundle(
        self, frozen: FrozenApplicationIdentity
    ) -> tuple[uuid.UUID, str]:
        """entry 当前 published representation 的 approved bundle identity。

        用 `ResolutionIntent.rematerialize` 而不是自己 `SELECT`：Requirement 2.10 要求
        十个意图共用同一解析入口，绕过它就会出现「fence 看到的 bundle」与
        「resolver 返回的 bundle」两套答案。
        """
        resolved = await self._resolution.resolve(
            intent=ResolutionIntent.rematerialize,
            project_id=frozen.project_id,
            wp_id=frozen.wp_id,
            entry_id=frozen.entry_id,
        )
        return resolved.bundle.bundle_id, resolved.bundle.bundle_sha256

    async def _observed_contributor_digest(
        self, frozen: FrozenApplicationIdentity, *, operation_id: uuid.UUID
    ) -> str:
        """**重算**当下的 contributor snapshot digest —— 只算仍然合法的 contributor。

        🔴 这里绝不能去读 request/application 上那个冻结的 digest 再拿来跟自己比。
        那是重言式：无论谁被撤销，两边永远相等，于是「contributor 重验」这条判据
        provably dead，删掉它在变异检验里判 GREEN（假绿第③源的另一面）。

        真实观测口径 = Task 21 落在 `working_paper_sync_operation_contributor` 的那批
        participant，**当下仍然 live** 的那些人的 user_id 集合，按
        `compute_contributor_snapshot_digest` 重算。于是「期间有 contributor 被撤销/
        过期/离开」会让重算结果与冻结值不同 ⇒ fence 拒绝（AC 10.10）。

        contributor 行为空时重算结果是空集合的 digest，与任何非空冻结值都不等 ⇒ 拒绝。
        那是**正确**的 fail-closed：Task 21 的 `record_contributor_snapshot` 是正常路径
        的必经步骤，行不存在说明归属根本没落库。
        """
        rows = (
            (
                await self._session.execute(
                    sa.text(
                        "SELECT c.user_id::text AS uid "
                        "FROM working_paper_sync_operation_contributor c "
                        "JOIN working_paper_oo_participant p ON p.id = c.participant_id "
                        "WHERE c.operation_id = :op "
                        "  AND p.room_id = :room "
                        "  AND p.state IN ('active', 'closing') "
                        "  AND p.revoked_at IS NULL "
                        "  AND p.expires_at > :now"
                    ),
                    {
                        "op": operation_id,
                        "room": frozen.room_id,
                        "now": _now(),
                    },
                )
            )
            .scalars()
            .all()
        )
        return compute_contributor_snapshot_digest(
            room_id=frozen.room_id,
            generation=frozen.generation,
            contributor_user_ids=[str(value) for value in rows],
        )

    # ─────────────────────────────────────────────────────────────────
    # 6.4 三方 extract
    # ─────────────────────────────────────────────────────────────────

    async def extract_three_way(
        self,
        *,
        frozen: FrozenApplicationIdentity,
        substrate: ReadOnlySubstrate,
        adapter: WorkpaperSyncAdapter,
        bundle: DefinitionBundleSnapshot,
        contract: SyncContract,
        journal: ApplyJournal,
    ) -> ThreeWayInputs:
        """按 **application 冻结的** base/representation 与 frozen bundle 取三方投影。

        三侧的来源各不相同，且都必须说得出身份（AC 4.11 / 8.10）：

        * `base`     ← `application.base_representation_id`（= request 冻结的
          client-confirmed representation）。**不是** room 现在的 client-confirmed 指针 ——
          连续 forcesave 只能用 request 冻结的那一份，否则第一次已合入的改动会被当成
          本次新改动再合一遍。
        * `current`  ← entry 当前 published representation（服务器现状）。
        * `incoming` ← 本次 durable incoming substrate。

        三侧共用**同一个** frozen contract：三份 projection 的 `contract_id` 必须一致，
        否则 `merge_projections` 直接拒（Task 14 的 `MergeInputError`）。
        """
        journal.assert_extract_precondition()
        base_resolved = await self._resolution.resolve(
            intent=ResolutionIntent.extract,
            project_id=frozen.project_id,
            wp_id=frozen.wp_id,
            entry_id=frozen.entry_id,
            representation_id=frozen.base_representation_id,
        )
        if base_resolved.bundle.bundle_id != frozen.definition_bundle_id:
            raise ResultBundleIdentityError(
                f"frozen base representation {frozen.base_representation_id} 的 bundle "
                f"{base_resolved.bundle.bundle_id} 与 application 冻结的 "
                f"{frozen.definition_bundle_id} 不同 —— 三方 merge 必须来自同一 frozen bundle"
            )
        base = adapter.extract(artifact=base_resolved.artifact_path, contract=contract)
        journal.record(ApplyStage.base_extracted, str(base_resolved.representation_id))

        current_resolved = await self._resolution.resolve(
            intent=ResolutionIntent.extract,
            project_id=frozen.project_id,
            wp_id=frozen.wp_id,
            entry_id=frozen.entry_id,
        )
        current = adapter.extract(artifact=current_resolved.artifact_path, contract=contract)
        journal.record(ApplyStage.current_extracted, str(current_resolved.representation_id))

        incoming = adapter.extract(artifact=substrate.path, contract=contract)
        journal.record(ApplyStage.incoming_extracted, substrate.sha256)
        return ThreeWayInputs(
            base=base,
            current=current,
            incoming=incoming,
            base_representation_id=base_resolved.representation_id,
            current_representation_id=current_resolved.representation_id,
            incoming_artifact_id=substrate.artifact_id,
            contract=contract,
            bundle=bundle,
        )

    # ─────────────────────────────────────────────────────────────────
    # 6.5 主入口
    # ─────────────────────────────────────────────────────────────────

    async def apply_durable_incoming(
        self,
        *,
        operation_id: uuid.UUID,
        declared_project_id: uuid.UUID,
        declared_wp_id: uuid.UUID,
        declared_entry_id: str,
        adapter: WorkpaperSyncAdapter,
        contract: SyncContract | None = None,
        resolutions: Sequence[ResolutionChoice] = (),
        authorize: Any = None,
        actor_id: uuid.UUID | None = None,
        attempt: int = 1,
        journal: ApplyJournal | None = None,
    ) -> OoToHtmlOutcome:
        """durable incoming → merged projection → 新 content revision（或 conflict）。

        入口顺序固定为 Task 23 的四步读路径（requested 授权 → direct-primary →
        canonicalize → 只要求 canonical primary 绑定 application），随后才是本模块的
        rematerialize 流程。retry 走**同一个**方法（`attempt>1`），因此不存在「retry
        专用捷径」这种绕过授权的形态（AC 8.9 / Property 38）。
        """
        j = journal if journal is not None else ApplyJournal()
        canonical = await self._requests.read_operation(
            operation_id=operation_id,
            declared_project_id=declared_project_id,
            declared_wp_id=declared_wp_id,
            declared_entry_id=declared_entry_id,
            action="apply_incoming" if attempt == 1 else "retry_apply",
            authorize=authorize,
            require_application=True,
        )
        j.record(ApplyStage.authorized, str(operation_id))
        j.record(ApplyStage.canonicalized, str(canonical.canonical_operation.id))
        application_id = canonical.canonical_application_id
        if application_id is None:  # pragma: no cover - require_application 已保证
            raise CanonicalPrimaryRequiredError(
                f"canonical operation {canonical.canonical_operation.id} 未绑定 application"
            )

        frozen = await self.load_frozen_identity(application_id)
        j.record(ApplyStage.application_locked, str(application_id))
        frozen.assert_scope(
            project_id=declared_project_id,
            wp_id=declared_wp_id,
            entry_id=declared_entry_id,
        )
        # 🔴 状态准入必须在 `try` **之外**：`applied` 没有出边，把它当 error 记录会撞
        # `StateTransitionError`；而真正的危险是反过来 —— 不拦时一次异常都不抛，
        # Task 15 照常提交，同一 incoming 产出第二个 revision（AC 4.3 / 8.12 / P65）。
        assert_application_state_admits_apply(
            frozen.state, application_id=application_id, attempt=attempt
        )
        j.record(ApplyStage.frozen_identity_loaded, frozen.definition_bundle_sha256)

        bundle = await self._resolution.load_bundle_snapshot(frozen.definition_bundle_id)
        if bundle.bundle_sha256.strip() != frozen.definition_bundle_sha256.strip():
            raise ResultBundleIdentityError(
                f"frozen bundle {frozen.definition_bundle_id} 的 canonical digest "
                f"{bundle.bundle_sha256!r} 与 application 冻结的 "
                f"{frozen.definition_bundle_sha256!r} 不一致"
            )
        # 🔴 「立即失败」：在打开 substrate 与任何 adapter 调用**之前**。
        assert_projection_result_has_approved_contract(bundle)
        j.record(ApplyStage.contract_child_verified, bundle.bundle_sha256)

        substrate = await self.open_substrate(frozen)
        j.record(ApplyStage.substrate_opened, substrate.sha256)

        state = _ApplyState(
            frozen=frozen,
            canonical=canonical,
            canonical_operation_id=canonical.canonical_operation.id,
            requested_operation_id=canonical.requested_operation.id,
            followed_duplicate=canonical.followed_duplicate,
            substrate=substrate,
            bundle=bundle,
            contract=contract,
            journal=j,
            attempt=attempt,
            actor_id=actor_id,
            resolutions=tuple(resolutions),
        )
        try:
            if bundle.authority_model is not AuthorityModel.projection_contract:
                raise ApprovedContractChildMissingError(
                    f"authority model={bundle.authority_model.value} 的 OO→HTML 回写属 "
                    "custom/opaque 权威路径，尚未接线（Requirement 2.11 / 6.19）—— "
                    "本 coordinator 只处理 projection_contract"
                )
            if contract is None:
                raise ApprovedContractChildMissingError(
                    "projection-based apply 必须给出与 frozen bundle contract slot digest "
                    "一致的 per-entry contract"
                )
            slot = bundle.slots[BundleSlot.contract]
            if slot.slot_digest != contract.canonical_sha256:
                raise ApprovedContractChildMissingError(
                    f"传入 contract 的 canonical digest {contract.canonical_sha256!r} 与 "
                    f"frozen bundle contract slot {slot.slot_digest!r} 不一致 —— "
                    "历史 operation 只读 frozen bundle，不得按 registry 当前 alias 重组"
                )

            inputs = await self.extract_three_way(
                frozen=frozen,
                substrate=substrate,
                adapter=adapter,
                bundle=bundle,
                contract=contract,
                journal=j,
            )
            merge = merge_projections(
                base=inputs.base,
                current=inputs.current,
                incoming=inputs.incoming,
                contract=contract,
            )
            state.merge = merge
            state.incoming_projection = inputs.incoming
            j.record(ApplyStage.merged, f"conflicts={merge.conflict_count}")

            # 三条路（AC 8.11 / 8.3）：
            #   有冲突 + 无裁决 ⇒ 登记冲突，指针一律不动（等 Task 27 的 resolve）；
            #   有冲突 + 有裁决 ⇒ 折叠裁决后 rematerialize（resolve 落地）；
            #   零冲突        ⇒ 直接 rematerialize（普通 OO→HTML）。
            # 🔴 分派**必须**读 `state.resolutions`：修之前它读了 `resolutions` 却把
            # 裁决丢掉（发布 `merge.merged` = current 侧值），所以真正的判据不是
            # 「分派有没有读它」而是「发布的 projection 是不是折叠结果」——
            # 后者由 `settle_adjudicated_projection` + Task 15 的独立重算双向锁死。
            if merge.has_conflicts and not state.resolutions:
                return await self._record_conflict(state)
            return await self._apply_settled(state, adapter=adapter)
        except FinalFenceError as exc:
            # 授权失效是**独立终态**（AC 10.10）：与「解析/合并失败」分型，
            # 因为它不可重试 —— 必须走 supersede/recovery，而不是 retry。
            return await self._record_post_durable_failure(
                state, exc=exc, result=OoToHtmlResult.authorization_stale
            )
        except OoToHtmlError as exc:
            return await self._record_post_durable_failure(
                state, exc=exc, result=OoToHtmlResult.error
            )
        except Exception as exc:  # noqa: BLE001 - durable 后一律落 error 终态并 ack=0
            return await self._record_post_durable_failure(
                state, exc=exc, result=OoToHtmlResult.error
            )

    # ─────────────────────────────────────────────────────────────────
    # 6.6 冲突分支：指针一律不动
    # ─────────────────────────────────────────────────────────────────

    async def _record_conflict(self, state: _ApplyState) -> OoToHtmlOutcome:
        """AC 8.11 / 4.6：登记冲突，**不**动 projection / current pointer / 双基线。"""
        merge = state.merge
        assert merge is not None
        conflicts: ConflictSet = merge.conflicts
        digest = conflicts.digest
        app = await self._lock_application(state.frozen.application_id)
        op_id = state.canonical_operation_id

        await self._walk_application(
            app,
            (
                ApplicationState.validating,
                ApplicationState.extracting,
                ApplicationState.merging,
            ),
            actor_id=state.actor_id,
        )
        app.conflict_count = int(merge.conflict_count)
        app.conflict_set_digest = digest
        app.incoming_projection_sha256 = projection_canonical_digest(
            state.incoming_projection  # type: ignore[arg-type]
        )
        # 🔴 冲突集必须**落行**，不能只留 `conflict_count/digest` 两个标量：
        # AC 8.1/8.2 的冲突预览要逐条给出业务标签、JSON Pointer、OO 地址与三方值，
        # AC 8.6 还要在同一行上留下裁决轨迹。只记摘要 ⇒ 预览只能重新 extract+merge
        # 一遍（而 substrate 可能已过 retention），裁决轨迹无处可写。
        write = await self._repo.record_conflicts(
            operation_id=op_id,
            client_edit_epoch=int(state.frozen.client_edit_epoch),
            canonical_application_id=state.frozen.application_id,
            effective_request_sequence=int(state.frozen.effective_request_sequence),
            rows=[record.to_row() for record in conflicts],
        )
        state.conflict_rows_written = write.inserted + write.updated
        state.conflict_rows_superseded = write.superseded
        await self._advance_application(
            app, to_state=ApplicationState.conflict, actor_id=state.actor_id
        )
        app.logical_result_code = OoToHtmlResult.conflict.value
        await self._walk_operation(
            op_id,
            (
                (OperationState.extracting, "extract"),
                (OperationState.merging, "merge"),
                (OperationState.conflict, "merge"),
            ),
            state=state,
        )
        state.journal.record(ApplyStage.conflict_recorded, digest)
        await self._session.commit()
        state.journal.assert_no_publish_after_conflict()
        state.journal.record(ApplyStage.responded, "conflict")
        return self._outcome(
            state,
            result=OoToHtmlResult.conflict,
            conflict_set_digest=digest,
            next_forcesave_allowed=True,
        )

    # ─────────────────────────────────────────────────────────────────
    # 6.7 无冲突分支：rematerialize → fence → publish → 单事务 commit
    # ─────────────────────────────────────────────────────────────────

    async def _apply_settled(
        self, state: _ApplyState, *, adapter: WorkpaperSyncAdapter
    ) -> OoToHtmlOutcome:
        merge = state.merge
        assert merge is not None and state.incoming_projection is not None
        assert state.contract is not None
        # 🔴 唯一的「要发布什么」决策点。零冲突 ⇒ `merge.merged`；带裁决 ⇒
        # `apply_resolutions` 的折叠结果。绝不能在这里退回 `merge.merged`：它对每个
        # 冲突字段保留 current 侧值，等于把审计师的选择静默换成 current。
        merged = settle_adjudicated_projection(
            merge=merge, resolutions=state.resolutions, contract=state.contract
        )
        state.merged_projection = merged
        state.merged_digest = projection_canonical_digest(merged)
        state.incoming_digest = projection_canonical_digest(state.incoming_projection)

        app = await self._lock_application(state.frozen.application_id)
        await self._walk_application(
            app,
            (
                ApplicationState.validating,
                ApplicationState.extracting,
                ApplicationState.merging,
                ApplicationState.rematerializing,
            ),
            actor_id=state.actor_id,
        )
        op_id = state.canonical_operation_id
        await self._walk_operation(
            op_id,
            (
                (OperationState.extracting, "extract"),
                (OperationState.merging, "merge"),
                (OperationState.rematerializing, "rematerialize"),
            ),
            state=state,
        )
        # 这批 state 转换必须先落地：Task 15 的 commit 会开自己的事务边界，
        # 而 `rematerializing` 是「已经开始改文件」的审计事实，失败时要留下来。
        await self._session.commit()

        plan = ContentCommitPlan(
            project_id=state.frozen.project_id,
            wp_id=state.frozen.wp_id,
            entry_id=state.frozen.entry_id,
            # 🔴 source 是 evidence 与 timeline 的分桶依据（V151 `ck_wpcv_source`）：
            # 带裁决的应用必须记成 `conflict_resolution`，否则事后无法区分「自动合并
            # 落库」与「审计师逐项裁决后落库」（AC 8.6 要求记录选择结果）。
            source=CONFLICT_RESOLUTION if state.resolutions else ONLYOFFICE,
            expected_revision=await self._current_revision(state.frozen.wp_id),
            bundle=state.bundle,
            adapter_id=state.frozen.adapter_id,
            adapter_build_digest=state.frozen.adapter_build_digest,
            document_type=state.substrate.document_type,
            # 🔴 substrate 三件套：路径 + role + kind/state。Task 15 会用它们再跑一次
            # `assert_substrate_usable`（三层拒绝的第三层）。
            substrate_path=state.substrate.path,
            substrate_role=SubstrateRole.incoming,
            substrate_kind=state.substrate.kind,
            substrate_state=state.substrate.state,
            actor_id=state.actor_id,
            operation_id=op_id,
            parent_version_id=await self._current_version_id(state.frozen.wp_id),
            contract=state.contract,
            room_id=state.frozen.room_id,
            application_id=state.frozen.application_id,
            reason="rematerialize",
        )
        mutation = BusinessMutation(
            projection=merged,
            merge=merge,
            incoming=state.incoming_projection,
            # Task 15 会用这批裁决**独立重算**一次折叠并与 `projection` 逐字节比对
            # （`AdjudicationNotFoldedError`）—— 这是「折叠真的发生了」的第二把锁。
            resolution_choices=state.resolutions,
        )
        receipt = await self._content.commit(
            plan=plan, mutation=mutation, adapter=adapter, fence=_ApplyFence(self, state)
        )
        state.journal.record(ApplyStage.business_committed, str(receipt.content_version_id))

        await self._assert_incoming_untouched(state)
        await self._settle_baseline(state, receipt=receipt)
        result = (
            OoToHtmlResult.refresh_required
            if receipt.requires_client_refresh
            else OoToHtmlResult.applied
        )
        state.journal.record(ApplyStage.responded, result.value)
        return self._outcome(
            state,
            result=result,
            receipt=receipt,
            next_forcesave_allowed=not receipt.requires_client_refresh,
        )

    # ─────────────────────────────────────────────────────────────────
    # 6.8 三个 fence 回调点
    # ─────────────────────────────────────────────────────────────────

    async def _fence_before_publish(
        self,
        state: _ApplyState,
        *,
        artifact_sha256: str,
        structure_hash: str,
        identity_inventory_sha256: str,
        extracted_key_count: int,
    ) -> None:
        """publish **之前**：extract 等值与未管理区域已过，现在重验授权与身份。

        AC 8.10 的次序原文：「先按同一 frozen bundle extract 等值并校验未管理区域，
        再重验 final authorization、generation/write fence、eligibility 与
        artifact/bundle digest，全部通过后才发布新的 representation」。

        本回调由 Task 15 在 `verify_unmanaged_regions().assert_equivalent()` 之后、
        `publish_representation()` 之前调用，所以「先/再/才」三段在**代码路径**上成立，
        而不是靠注释。:meth:`ApplyJournal.assert_publish_precondition` 另外把
        「extract 三方与 merge 确实发生过」变成运行期断言。
        """
        state.journal.assert_publish_precondition()
        for name, digest in (
            ("artifact_sha256", artifact_sha256),
            ("structure_hash", structure_hash),
            ("identity_inventory_sha256", identity_inventory_sha256),
        ):
            if not is_digest(digest):
                raise ResultArtifactDigestError(
                    f"rematerialize 产出的 {name} 非法（空串/全零/非小写 hex）: {digest!r}"
                )
        if state.bundle.bundle_id != state.frozen.definition_bundle_id or (
            state.bundle.bundle_sha256.strip()
            != state.frozen.definition_bundle_sha256.strip()
        ):
            raise ResultBundleIdentityError(
                "即将发布的 representation 绑定的 bundle 与 application 冻结值不一致"
            )
        observed = await self.observe_live_authorization(
            state.frozen, canonical_operation_id=state.canonical_operation_id
        )
        state.fence_before_publish = assert_final_authorization(
            frozen=state.frozen, observed=observed
        )
        # 记录被放行的那份 digest：`after_pointers` 会比对真正落库的那一份，
        # 于是「fence 放行了 A，落库的是 B」这种偷换是可检出的。
        state.approved_result_sha256 = artifact_sha256
        state.journal.record(ApplyStage.fence_verified_before_publish, artifact_sha256)

    async def _fence_before_write(
        self, state: _ApplyState, *, current_revision: int
    ) -> None:
        """DB commit 前的第二道重验（AC 10.10）：在 wp 锁内、任何写之前。

        两道都要跑，不是冗余：第一道到第二道之间发生了 `publish_representation`
        （文件 IO，可能是几十 MB 的 xlsx，耗时可观），撤权完全可能落在这段时间里。
        """
        state.journal.assert_write_precondition()
        if int(current_revision) < 0:
            raise ResultArtifactDigestError(f"current revision 非法: {current_revision}")
        observed = await self.observe_live_authorization(
            state.frozen, canonical_operation_id=state.canonical_operation_id
        )
        state.fence_before_write = assert_final_authorization(
            frozen=state.frozen, observed=observed
        )
        state.journal.record(ApplyStage.fence_verified_before_write, str(current_revision))

    async def _write_application_result(
        self, state: _ApplyState, facts: CommitTransactionFacts
    ) -> None:
        """与 business projection/version/representation/pointer/outbox **同事务**。

        写四样东西：

        1. application 的 result（revision / representation / artifact digest /
           merged·incoming projection digest / logical result）+ append-only event；
        2. operation 的 `applying → applied|refresh_required` + append-only event；
        3. room 的 server last-applied **与 canonical fence**（`RoomService.
           advance_server_last_applied` 一次完成，AC 10.11 要求二者原子决定）；
        4. client-confirmed 基线的裁决（只在 merged==incoming 时推进）。

        第 3 条为什么还要调 Task 21：Task 15 的 `_advance_room` 只推 `last_applied_
        version_id`，不动 `latest_durable_application_id/latest_durable_sequence`。
        少了它，Task 27 的 resolve（先比 canonical application identity）会读到
        「server 已推进、canonical fence 还指着上一个 application」的中间态。
        """
        assert_published_digest_was_approved(
            approved_sha256=state.approved_result_sha256,
            published_sha256=facts.artifact_sha256,
        )
        assert state.merged_digest is not None and state.incoming_digest is not None

        app = await self._lock_application(state.frozen.application_id)
        app.result_revision = int(facts.revision)
        app.result_representation_id = facts.representation_id
        app.result_artifact_sha256 = facts.artifact_sha256
        app.merged_projection_sha256 = state.merged_digest
        app.incoming_projection_sha256 = state.incoming_digest
        app.durable_at = app.durable_at or _now()
        await self._walk_application(
            app, (ApplicationState.applying,), actor_id=state.actor_id
        )
        terminal = (
            ApplicationState.refresh_required
            if facts.requires_client_refresh
            else ApplicationState.applied
        )
        app.logical_result_code = (
            OoToHtmlResult.refresh_required.value
            if facts.requires_client_refresh
            else OoToHtmlResult.applied.value
        )
        await self._advance_application(
            app,
            to_state=terminal,
            actor_id=state.actor_id,
            event_type=ApplicationEventType.terminal,
        )
        app.finished_at = _now()

        await self._walk_operation(
            state.canonical_operation_id,
            (
                (OperationState.applying, "apply"),
                (
                    (
                        OperationState.refresh_required
                        if facts.requires_client_refresh
                        else OperationState.applied
                    ),
                    "apply",
                ),
            ),
            state=state,
        )

        advance = await self._rooms.advance_server_last_applied(
            room_id=state.frozen.room_id,
            content_version_id=facts.content_version_id,
            application_id=state.frozen.application_id,
        )
        assert_canonical_fence_points_at(
            advanced_application_id=advance.latest_durable_application_id,
            expected_application_id=state.frozen.application_id,
        )
        state.result_facts = facts
        state.journal.record(ApplyStage.application_result_written, str(facts.revision))

    # ─────────────────────────────────────────────────────────────────
    # 6.9 双基线裁决（Property 62）
    # ─────────────────────────────────────────────────────────────────

    async def _settle_baseline(
        self, state: _ApplyState, *, receipt: ContentCommitReceipt
    ) -> None:
        """merged==incoming 才推进 client-confirmed；否则 refresh-required + supersede。

        AC 2.9 / 4.11 / Property 62 的三段：

        1. server last-applied **无条件**推进（已在 `after_pointers` 内完成）；
        2. client-confirmed **仅在**等值时推进；
        3. 不等值 ⇒ room 落 `refresh_required` 并 supersede/reopen，**禁止下一次
           forcesave**（那道门在 `RoomService.assert_can_initiate_request`，它检查
           `refresh_required_at`，所以本方法只要确保那一列被写上）。
        """
        assert state.merge is not None and state.incoming_projection is not None
        assert state.merged_digest is not None and state.incoming_digest is not None
        merged_side, incoming_side = settlement_digest_pair(
            merge=state.merge,
            incoming=state.incoming_projection,
            merged_digest=state.merged_digest,
            incoming_digest=state.incoming_digest,
        )
        # 🔴 bundle identity 用 Task 21 的 `frozen_bundle_identity()` 现读，**不**自己
        # 拼一个 `FrozenBundleIdentity` —— 它含 `slots_digest`，自己拼就是第二套算法，
        # 漂移那天两边都「全绿」。这里另外核对它与 application 冻结值一致。
        bundle_identity = await self._rooms.frozen_bundle_identity(
            state.frozen.definition_bundle_id
        )
        if bundle_identity.definition_bundle_sha256.strip() != (
            state.frozen.definition_bundle_sha256.strip()
        ):
            raise ResultBundleIdentityError(
                "client-confirmed 基线要写入的 bundle digest 与 application 冻结值不一致"
            )
        settlement = await self._rooms.settle_client_baseline(
            room_id=state.frozen.room_id,
            merged_projection_sha256=merged_side,
            incoming_projection_sha256=incoming_side,
            applied_content_version_id=receipt.content_version_id,
            applied_representation_id=receipt.representation_id,
            bundle=bundle_identity,
        )
        state.client_baseline_advanced = settlement.client_baseline_advanced
        state.room_refresh_required = settlement.refresh_required
        state.journal.record(
            ApplyStage.baseline_settled,
            "advanced" if settlement.client_baseline_advanced else settlement.reason,
        )
        if settlement.refresh_required:
            # AC 4.11：不等值时必须 supersede/reopen 后才接受下一次 request。
            await self._rooms.supersede_room(
                room_id=state.frozen.room_id, reason=SUPERSEDE_REASON_MERGED_DIFFERS
            )
            state.room_superseded = True
            state.journal.record(
                ApplyStage.generation_superseded, SUPERSEDE_REASON_MERGED_DIFFERS
            )
        await self._session.commit()

    # ─────────────────────────────────────────────────────────────────
    # 6.10 durable 后失败：保留 incoming、同一 operation error、指针不动
    # ─────────────────────────────────────────────────────────────────

    async def _record_post_durable_failure(
        self, state: _ApplyState, *, exc: BaseException, result: OoToHtmlResult
    ) -> OoToHtmlOutcome:
        """Property 19 / AC 5.8：ack=0、保留 incoming、同一 operation 落可重试 error。

        `result` 分两种，不合并：

        * :attr:`OoToHtmlResult.error` —— extract/merge/rematerialize 失败，**可** retry；
        * :attr:`OoToHtmlResult.authorization_stale` —— 最终 fence 失败，**不可** retry，
          只能走 supersede/recovery（AC 10.10 末句）。

        合并成一个终态的后果很具体：撤权用户的 application 会进入普通 retry 队列，
        而 retry 不重新拿授权（它按设计复用 frozen identity）⇒ 撤权被绕过。
        """
        await self._session.rollback()
        error_code = getattr(exc, "error_code", None) or type(exc).__name__
        app = await self._lock_application(state.frozen.application_id)
        target_app = (
            ApplicationState.authorization_stale
            if result is OoToHtmlResult.authorization_stale
            else ApplicationState.error
        )
        target_op = (
            OperationState.authorization_stale
            if result is OoToHtmlResult.authorization_stale
            else OperationState.error
        )
        await self._advance_application(
            app, to_state=target_app, actor_id=state.actor_id, error_code=error_code
        )
        app.logical_result_code = result.value
        await self._advance_operation(
            state.canonical_operation_id,
            to_state=target_op,
            stage="post_durable",
            state=state,
            error_code=error_code,
        )
        state.journal.record(ApplyStage.post_durable_error_recorded, error_code)
        if (
            result is OoToHtmlResult.authorization_stale
            and state.frozen.frozen_request_kind is RequestKind.close_capture
        ):
            await self._terminate_stale_close_capture(state, error_code=error_code)
        await self._session.commit()

        # incoming 必须仍在原处、仍是 durable incoming（可 retry 的前提）。
        await self._assert_incoming_untouched(state)
        state.journal.record(ApplyStage.responded, f"{result.value}:{error_code}")
        return self._outcome(
            state,
            result=result,
            error_code=error_code,
            error_stage="post_durable",
            error_detail=_error_detail(exc),
            next_forcesave_allowed=False,
        )

    async def _terminate_stale_close_capture(
        self, state: _ApplyState, *, error_code: str
    ) -> None:
        """leader 在 **promotion 之后**授权失效：supersede generation（AC 10.10 末句）。

        为什么这件事落在本模块而不是 Task 24 的 reconciler：
        `WorkpaperSyncRepository.reconcile_close_intents` 一见到本 generation 有
        `state=promoted` 的 intent 就**提前返回**（源码注释原文：「已 promotion：授权失效
        只能由最终 fence 走 recovery，绝不再选 successor」）。reconciler 显式把这条路交给
        了最终 fence，而在本方法出现之前 fence 只写 application/operation 终态：room 停在
        `close_barrier`、close 永远等不到内容 —— AC 10.10 的「并 supersede/recovery」与
        Property 63 的「不能永久 blocked」都不成立。

        ⚠️ **promoted intent 的行终态在 V151 下无法表达，且刻意不表达**：

        * `CLOSE_INTENT_EDGES[promoted]` 登记了 `authorization_stale / error /
          recovery_required / superseded` 四条出边，但 V151 的
          `ck_wpoci_promoted_pair CHECK ((state='promoted') = (promoted_request_id IS NOT
          NULL))` 要求离开 `promoted` 必须同时把 `promoted_request_id` 置空 ——
          那是本 fence 反查 promotion epoch 所依赖的审计链（见
          :meth:`_frozen_close_leader_eligibility_epoch`），置空等于毁证。
          **登记表与 CHECK 互相矛盾，属 Task 9/24 的欠账**，本模块不靠毁证绕过它。
        * 更关键：`state=promoted` 正是 reconciler 短路的钥匙。把它推成终态反而会让
          `already_promoted` 失效，于是下一次 reconcile 会走「current_leader 已不合格」
          分支、推进 eligibility epoch 并**另选 successor** —— 那正是 AC 10.10 明令禁止
          的「接任再造第二个 capture」。留在 `promoted` 是唯一能同时满足两条的形态。

        「intent 是否还在 `promoted`」**不需要**在这里断言：本 fence 反查 promotion epoch
        走的是 `promoted_request_id`，而 `ck_wpoci_promoted_pair` 保证带着该列的行必然
        `state='promoted'`。再写一条运行期检查就是一条由 DB CHECK 保证为真的死分支
        （短路它永远判 GREEN）。判据落在守卫侧：`_pg` 的
        `test_no_successor_can_be_promoted_afterwards` 直接断言那一行仍是 `promoted`。

        因此本方法只做一件在 V151 下合法且必需的事（在调用方的同一事务里，不 commit）：
        supersede generation —— room 不再接受新 request，UI 能显示「需重开」而不是
        无限等待。
        """
        room = await self._repo.lock_room(state.frozen.room_id)
        if room.superseded_at is not None:
            state.room_superseded = True
            return
        await self._rooms.supersede_room(
            room_id=state.frozen.room_id,
            reason=SUPERSEDE_REASON_CLOSE_CAPTURE_STALE,
        )
        state.room_superseded = True
        state.journal.record(
            ApplyStage.generation_superseded,
            f"{SUPERSEDE_REASON_CLOSE_CAPTURE_STALE}:{error_code}",
        )

    # ─────────────────────────────────────────────────────────────────
    # 6.11 P14：applied 后前端要加载的最低 revision
    # ─────────────────────────────────────────────────────────────────

    async def reload_floor_revision(
        self,
        *,
        operation_id: uuid.UUID,
        declared_project_id: uuid.UUID,
        declared_wp_id: uuid.UUID,
        declared_entry_id: str,
        authorize: Any = None,
    ) -> int:
        """前端 `reloadHtml` 允许加载的**最低** revision（Property 14）。

        取值来源固定为 `application.result_revision` —— 不是 `working_paper.
        content_revision`（并发的别的 wp 提交会把它抬高，于是「不低于」变成恒真）
        也不是 receipt（前端重连后没有 receipt）。

        pre-bind shell（`application_id=NULL`）问这个值一律抛
        :class:`PreBindResultRevisionError`：AC 4.1 明确 accepted 时还没有 application，
        「伪造一个 result revision」会让前端在内容尚未应用时就去 reload。
        """
        canonical = await self._requests.read_operation(
            operation_id=operation_id,
            declared_project_id=declared_project_id,
            declared_wp_id=declared_wp_id,
            declared_entry_id=declared_entry_id,
            action="reload_floor",
            authorize=authorize,
            require_application=False,
        )
        shape = classify_operation_shape(
            application_id=canonical.canonical_operation.application_id,
            duplicate_of_operation_id=(
                canonical.canonical_operation.duplicate_of_operation_id
            ),
            state=canonical.canonical_operation.state,
        )
        if shape is OperationShape.pre_correlation or (
            canonical.canonical_application_id is None
        ):
            raise PreBindResultRevisionError(
                f"operation {operation_id} 的 canonical 形态是 {shape.value} —— "
                "accepted 时尚无 application，不得伪造 result revision（AC 4.1 / P14）"
            )
        revision = (
            await self._session.execute(
                sa.select(WorkpaperContentApplication.result_revision).where(
                    WorkpaperContentApplication.id == canonical.canonical_application_id
                )
            )
        ).scalar_one()
        if revision is None:
            raise PreBindResultRevisionError(
                f"application {canonical.canonical_application_id} 尚未 applied "
                "（result_revision 为空）—— 前端不得据此 reload"
            )
        return int(revision)

    # ─────────────────────────────────────────────────────────────────
    # 6.12 内部
    # ─────────────────────────────────────────────────────────────────

    async def _lock_application(
        self, application_id: uuid.UUID
    ) -> WorkpaperContentApplication:
        return (
            await self._session.execute(
                sa.select(WorkpaperContentApplication)
                .where(WorkpaperContentApplication.id == application_id)
                .with_for_update()
            )
        ).scalar_one()

    async def _walk_application(
        self,
        app: WorkpaperContentApplication,
        pipeline: tuple[ApplicationState, ...],
        *,
        actor_id: uuid.UUID | None,
    ) -> None:
        """按 pipeline 推进 application state，**从当前状态可达的第一站进入**。

        🔴 这不是「容错」，而是 AC 8.9 的 retry 语义：`error → extracting` 是登记过的
        恢复边，而 `error → validating` **不是**。直写整条 pipeline 的写法在首次执行时
        正常、在 retry 时必然撞 `StateTransitionError` —— 于是「durable incoming 可无
        forcesave 重试」这条承诺在真库上根本不成立（本任务实测踩到）。

        判据来自 `APPLICATION_EDGES` 这一份登记表，不在这里另写一套「哪些可以跳过」。
        """
        for target in pipeline:
            current = ApplicationState(app.state)
            if current is target:
                continue
            if target not in APPLICATION_EDGES.get(current, frozenset()):
                # 从当前状态到不了这一站 ⇒ 它属于本次已经越过的阶段，跳过。
                continue
            await self._advance_application(app, to_state=target, actor_id=actor_id)

    async def _walk_operation(
        self,
        operation_id: uuid.UUID,
        pipeline: tuple[tuple[OperationState, str], ...],
        *,
        state: _ApplyState,
    ) -> None:
        """operation 侧的同一套 pipeline 语义（判据来自 `OPERATION_EDGES`）。"""
        for target, stage in pipeline:
            current = OperationState(
                (
                    await self._session.execute(
                        sa.select(WorkpaperSyncOperation.state).where(
                            WorkpaperSyncOperation.id == operation_id
                        )
                    )
                ).scalar_one()
            )
            if current is target:
                continue
            if target not in OPERATION_EDGES.get(current, frozenset()):
                continue
            await self._advance_operation(
                operation_id, to_state=target, stage=stage, state=state
            )

    async def _advance_application(
        self,
        app: WorkpaperContentApplication,
        *,
        to_state: ApplicationState,
        actor_id: uuid.UUID | None,
        error_code: str | None = None,
        event_type: ApplicationEventType = ApplicationEventType.state_changed,
    ) -> None:
        """先写 append-only event，再更新 current state 投影（AC 5.10 的顺序）。

        `from_state == to_state` 时直接返回：retry 会重走 `extracting → merging`，
        而 `APPLICATION_EDGES` 里没有自环边 —— 那不是「非法转换」，只是「已经在那儿」。
        """
        current = ApplicationState(app.state)
        if current is to_state:
            return
        await self._repo.append_application_event(
            application_id=app.id,
            event_type=event_type,
            origin_request_sequence=int(app.origin_request_sequence),
            effective_request_sequence=int(app.effective_request_sequence),
            from_state=current,
            to_state=to_state,
            actor_type=ActorType.callback,
            actor_id=actor_id,
            error_code=error_code,
        )
        app.state = to_state.value
        await self._session.flush()

    async def _advance_operation(
        self,
        operation_id: uuid.UUID,
        *,
        to_state: OperationState,
        stage: str,
        state: _ApplyState,
        error_code: str | None = None,
    ) -> None:
        """同一条 operation timeline 上追加一次 attempt（Property 38：retry 不新建）。

        入参是 **id 而不是 ORM 行**：本流程跨了多个事务边界（conflict 分支自己 commit、
        Task 15 的 commit 有自己的边界），而 `expire_on_commit=True` 的 session 在
        commit 之后访问旧 ORM 属性会触发隐式 IO，在 async 下直接 `MissingGreenlet`。
        每次按 id 重取一行是廉价且无歧义的。
        """
        op = (
            await self._session.execute(
                sa.select(WorkpaperSyncOperation)
                .where(WorkpaperSyncOperation.id == operation_id)
                .with_for_update()
            )
        ).scalar_one()
        current = OperationState(op.state)
        if current is to_state:
            return
        await self._repo.append_operation_event(
            operation_id=op.id,
            from_state=current,
            to_state=to_state,
            stage=f"{stage}#{state.attempt}",
            actor_type=ActorType.callback,
            actor_id=state.actor_id,
            error_code=error_code,
            client_edit_epoch=int(state.frozen.client_edit_epoch),
            origin_request_sequence=int(state.frozen.origin_request_sequence),
            effective_request_sequence=int(state.frozen.effective_request_sequence),
        )
        op.state = to_state.value
        await self._session.flush()

    async def _assert_incoming_untouched(self, state: _ApplyState) -> None:
        """重读 incoming artifact 行，逐列核对它**没有**被晋升或改写。

        判据落在数据库行上而不是「我没写那行代码」：AC 8.10 的承诺是
        「incoming 本身永不成为 published representation、current pointer 或 resolver
        输出」，它必须在**每一次** apply 之后可被证伪。
        """
        row = (
            await self._session.execute(
                sa.select(WorkpaperArtifact).where(
                    WorkpaperArtifact.id == state.substrate.artifact_id
                )
            )
        ).scalar_one()
        assert_incoming_row_unchanged(
            artifact_id=row.id,
            observed_kind=str(row.kind),
            observed_state=str(row.state),
            observed_published_at=row.published_at,
            observed_relative_path=str(row.relative_path or ""),
            observed_sha256=str(row.sha256 or ""),
            expected_relative_path=state.substrate.relative_path,
            expected_sha256=state.substrate.sha256,
        )

    async def _current_revision(self, wp_id: uuid.UUID) -> int:
        row = (
            await self._session.execute(
                sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
                {"wp": wp_id},
            )
        ).scalar_one()
        return int(row)

    async def _current_version_id(self, wp_id: uuid.UUID) -> uuid.UUID | None:
        return (
            await self._session.execute(
                sa.text(
                    "SELECT current_content_version_id FROM working_paper WHERE id = :wp"
                ),
                {"wp": wp_id},
            )
        ).scalar_one_or_none()

    def _outcome(
        self,
        state: _ApplyState,
        *,
        result: OoToHtmlResult,
        receipt: ContentCommitReceipt | None = None,
        conflict_set_digest: str | None = None,
        error_code: str | None = None,
        error_stage: str | None = None,
        error_detail: str | None = None,
        next_forcesave_allowed: bool = False,
    ) -> OoToHtmlOutcome:
        merge = state.merge
        return OoToHtmlOutcome(
            result=result,
            application_id=state.frozen.application_id,
            canonical_operation_id=state.canonical_operation_id,
            requested_operation_id=state.requested_operation_id,
            followed_duplicate=state.followed_duplicate,
            attempt=state.attempt,
            substrate=state.substrate,
            merge=merge,
            conflict_count=(0 if merge is None else int(merge.conflict_count)),
            conflict_set_digest=conflict_set_digest,
            conflict_rows_written=state.conflict_rows_written,
            conflict_rows_superseded=state.conflict_rows_superseded,
            resolutions_applied=len(state.resolutions),
            content_version_id=(None if receipt is None else receipt.content_version_id),
            result_revision=(None if receipt is None else int(receipt.revision)),
            result_representation_id=(
                None if receipt is None else receipt.representation_id
            ),
            result_artifact_sha256=(None if receipt is None else receipt.artifact_sha256),
            merged_projection_sha256=(None if receipt is None else state.merged_digest),
            incoming_projection_sha256=state.incoming_digest,
            server_last_applied_advanced=state.result_facts is not None,
            client_baseline_advanced=state.client_baseline_advanced,
            room_refresh_required=state.room_refresh_required,
            room_superseded=state.room_superseded,
            next_forcesave_allowed=next_forcesave_allowed,
            fence_compared_before_publish=state.fence_before_publish,
            fence_compared_before_write=state.fence_before_write,
            # durable 之后一律 0：Task 4 实测 OO 对非零 error 不重投 ⇒ 非零 = 静默丢件。
            callback_response_error=0,
            error_code=error_code,
            error_stage=error_stage,
            error_detail=error_detail,
            stages=state.journal.order,
        )


def _error_detail(exc: BaseException, *, frames: int = 4, limit: int = 400) -> str:
    """失败原文 + 最后几帧（Requirement 5.12 的可定位诊断）。

    只记 `type: message` 时，`TypeError` 这类接线错误无从定位到行 —— 而它恰恰是本域
    最常见的失败形态（adapter 签名、列名、单参调用 async）。
    """
    import traceback

    tb = traceback.extract_tb(exc.__traceback__)[-frames:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}" for f in reversed(tb))
    return f"{type(exc).__name__}: {exc} @ {where}"[:limit]


_ = FrozenBundleIdentity  # 显式保留：`_settle_baseline` 的返回类型来自 Task 21，不 re-export
