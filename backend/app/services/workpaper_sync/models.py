# -*- coding: utf-8 -*-
"""同步域 domain enum、允许状态边、identity 计算与纯不变式校验（无 ORM、无 IO）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 10
Requirements: 2.1, 2.4, 2.5, 2.9, 4.3, 5.4, 5.5, 5.10, 8.5, 10.5, 10.9, 10.10, 10.11, 13.5, 14.10
Properties: P4 / P5 / P18 / P36 / P43 / P59 / P63 / P64 / P68

═══ 为什么状态边与 identity 必须是纯函数 ═══

`repository.py` 的每一次写入都先过这里的 :func:`assert_transition` /
:func:`classify_operation_shape` / :func:`compute_application_key`。纯函数让
「允许状态边」和「幂等 identity」可以用 hypothesis 在**全输入空间**上验证，而不必
每次都连库；数据库侧的 CHECK/trigger 则是同一批规则的第二道锁（design §Data Model
明文要求「数据库约束与 repository 双向校验」）。

两侧任何一侧单独存在都不够：
* 只有 DB 约束 ⇒ 应用层会把非法写入送到数据库才失败，错误码/阶段无法 fail-visible；
* 只有 Python 校验 ⇒ 多 worker 并发下绕过 ORM 的写入（psql/脚本/未来 router）无人拦。

═══ Property 64 的核心：application_key 不含什么 ═══

:func:`compute_application_key` 的入参**刻意不含** callback status、request id、
request sequence、callback 到达时的 room last-applied 指针。它只吃 frozen request
已冻结的值 + durable incoming 的 sha256。任何试图把 status 或 sequence 塞进 key 的
改动都会让 :func:`compute_application_key` 的签名变化，守卫直接打红。
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Final, Iterable, Mapping

# ═══════════════════════════════════════════════════════════════════════════
# 0. digest / opaque id 单一真源（镜像 V151 的 wpsync_is_digest / _is_opaque_*）
# ═══════════════════════════════════════════════════════════════════════════

_HEX64: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
_ALL_ZERO: Final[str] = "0" * 64
_DIGITS_ONLY: Final[re.Pattern[str]] = re.compile(r"^[0-9]+$")


def is_digest(value: object) -> bool:
    """是否为合法内容身份 digest：非空 + 64 位**小写** hex + 非全零。

    与 V151 的 `wpsync_is_digest()` 逐条对齐：空串、纯空白、全零 hash、大写 hex、
    长度不足/超出一律拒绝。全零单独排除是因为「忘了算 hash 就填 0」是最常见的
    伪身份写法，而它在 `char(64)` 与正则层面都是合法 hex。
    """
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v or v == _ALL_ZERO:
        return False
    return bool(_HEX64.match(v))


def is_opaque_resource_id(value: object) -> bool:
    """scope index 的 resource_id 是否 opaque：纯数字（numeric revision）一律拒绝。

    Requirement 10.6 / 8.7：per-wp numeric `revision` 只作显示与乐观锁，
    绝不能当 scope/resource/route key —— 两个不同 wp 的 revision 1 会在
    authorization 索引里碰撞成同一行。
    """
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v:
        return False
    return not bool(_DIGITS_ONLY.match(v))


def is_uuid_text(value: object) -> bool:
    """是否为 UUID 文本（content version 的 resource_id 只接受 immutable UUID）。"""
    if not isinstance(value, str):
        return False
    try:
        uuid.UUID(value.strip())
    except (ValueError, AttributeError, TypeError):
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# 1. 封闭枚举
# ═══════════════════════════════════════════════════════════════════════════


class ArtifactKind(str, Enum):
    canonical = "canonical"
    upgrade_candidate = "upgrade_candidate"
    incoming = "incoming"
    projection = "projection"
    definition = "definition"
    template = "template"
    evidence = "evidence"
    trace_bundle = "trace_bundle"


class ArtifactState(str, Enum):
    staged = "staged"
    durable = "durable"
    candidate = "candidate"
    published = "published"
    orphan = "orphan"
    quarantined = "quarantined"
    deleted = "deleted"


class DefinitionKind(str, Enum):
    template = "template"
    instrumentation = "instrumentation"
    contract = "contract"
    authority_model = "authority_model"


class DefinitionState(str, Enum):
    candidate = "candidate"
    approved = "approved"
    retired = "retired"


class AuthorityModel(str, Enum):
    projection_contract = "projection_contract"
    custom_authoritative_ooxml = "custom_authoritative_ooxml"
    opaque_single_onlyoffice = "opaque_single_onlyoffice"


class BundleSlot(str, Enum):
    template = "template"
    instrumentation = "instrumentation"
    contract = "contract"


class CandidateState(str, Enum):
    staged = "staged"
    awaiting_contract = "awaiting_contract"
    ready = "ready"
    finalized = "finalized"
    rejected = "rejected"
    orphaned = "orphaned"


class PendingMutationState(str, Enum):
    pending = "pending"
    committing = "committing"
    committed = "committed"
    expired = "expired"
    invalidated = "invalidated"


class ScopeResourceKind(str, Enum):
    room = "room"
    participant = "participant"
    client_confirmation = "client_confirmation"
    forcesave_request = "forcesave_request"
    close_intent = "close_intent"
    callback_delivery = "callback_delivery"
    content_application = "content_application"
    sync_operation = "sync_operation"
    recovery_case = "recovery_case"
    sync_conflict = "sync_conflict"
    content_version = "content_version"
    content_representation = "content_representation"
    upgrade_candidate = "upgrade_candidate"
    pending_mutation = "pending_mutation"
    sync_test_run = "sync_test_run"
    evidence_scenario = "evidence_scenario"


class RoomState(str, Enum):
    opening = "opening"
    active = "active"
    close_barrier = "close_barrier"
    closing = "closing"
    refresh_required = "refresh_required"
    superseded = "superseded"
    closed = "closed"
    recovery_required = "recovery_required"


class ParticipantState(str, Enum):
    active = "active"
    closing = "closing"
    left = "left"
    revoked = "revoked"
    expired = "expired"


class ParticipantMode(str, Enum):
    edit = "edit"
    view = "view"


class ContributorSource(str, Enum):
    """`working_paper_sync_operation_contributor.source` 的封闭域（同 V151 CHECK）。

    三个值对应 Task 4 实证的三种**不同**来源，绝不可互换：

    * ``request_initiator`` —— 平台自己冻结的 forcesave 发起人。OO 侧**没有**发起人字段
      （`commands.jsonl` 实证 Command Service 请求体只有 `c`/`key`/`userdata`），
      所以这一条只能来自平台的 frozen request，不可能来自 callback payload。
    * ``oo_users`` —— callback payload 里的 OO 侧用户信息。契约
      `contributor_snapshot_source` 固定为 `history.changes[].user`；**不是** `users`
      字段（`users_field_semantics = last_editor_only_not_contributors`）。
    * ``active_writer_snapshot`` —— OO 没给出 history 时的服务端兜底快照。
    """

    request_initiator = "request_initiator"
    oo_users = "oo_users"
    active_writer_snapshot = "active_writer_snapshot"


class ContributorConfidence(str, Enum):
    """contributor 归属置信度的封闭域（同 V151 CHECK）。

    `exact` 只属于平台自己冻结的 initiator。OO 派生的 contributor 永远达不到 `exact`：
    Task 4 实测 `history.changes` **包含已被 drop 的用户**，故它是审计快照而非授权依据
    （契约 `contributor_snapshot_caveat`）。把它标 `exact` 就等于把审计快照当授权凭据用。
    """

    exact = "exact"
    aggregate = "aggregate"
    unknown = "unknown"


class RequestKind(str, Enum):
    forcesave = "forcesave"
    close_capture = "close_capture"
    recovery_claim = "recovery_claim"


class RequestState(str, Enum):
    frozen = "frozen"
    pending = "pending"
    accepted = "accepted"
    correlated = "correlated"
    terminal = "terminal"
    rejected = "rejected"
    unmatched = "unmatched"
    superseded = "superseded"
    authorization_stale = "authorization_stale"


class CloseIntentState(str, Enum):
    created = "created"
    ordinary_forcesaving = "ordinary_forcesaving"
    waiting_barrier = "waiting_barrier"
    leader_ready = "leader_ready"
    promoted = "promoted"
    retryable_blocked = "retryable_blocked"
    authorization_stale = "authorization_stale"
    successor_selected = "successor_selected"
    recovery_required = "recovery_required"
    superseded = "superseded"
    error = "error"


class RecoveryReason(str, Enum):
    missing_request = "missing_request"
    ambiguous_close = "ambiguous_close"
    crash_close = "crash_close"
    stale_candidate = "stale_candidate"


class RecoveryCaseState(str, Enum):
    unclaimed = "unclaimed"
    claiming = "claiming"
    application_created = "application_created"
    download_only = "download_only"
    quarantined = "quarantined"
    expired = "expired"


class ApplicationState(str, Enum):
    queued = "queued"
    validating = "validating"
    extracting = "extracting"
    merging = "merging"
    conflict = "conflict"
    rematerializing = "rematerializing"
    applying = "applying"
    applied = "applied"
    refresh_required = "refresh_required"
    error = "error"
    superseded = "superseded"
    authorization_stale = "authorization_stale"


class ApplicationEventType(str, Enum):
    created = "created"
    sequence_folded = "sequence_folded"
    state_changed = "state_changed"
    superseded = "superseded"
    terminal = "terminal"


class OperationDirection(str, Enum):
    html_to_oo = "html_to_oo"
    oo_to_html = "oo_to_html"
    conflict_resolution = "conflict_resolution"
    rollback = "rollback"


class OperationState(str, Enum):
    created = "created"
    command_pending = "command_pending"
    accepted = "accepted"
    waiting_application = "waiting_application"
    application_bound = "application_bound"
    duplicate = "duplicate"
    extracting = "extracting"
    merging = "merging"
    conflict = "conflict"
    rematerializing = "rematerializing"
    applying = "applying"
    applied = "applied"
    refresh_required = "refresh_required"
    error = "error"
    rejected = "rejected"
    superseded = "superseded"
    authorization_stale = "authorization_stale"


class DeliveryState(str, Enum):
    received = "received"
    downloading = "downloading"
    durable = "durable"
    acknowledged = "acknowledged"
    rejected = "rejected"
    error = "error"
    unmatched = "unmatched"


class CorrelationResult(str, Enum):
    request = "request"
    existing_application = "existing_application"
    close_capture = "close_capture"
    unmatched = "unmatched"
    ambiguous = "ambiguous"


class ActorType(str, Enum):
    user = "user"
    system = "system"
    callback = "callback"
    reconciler = "reconciler"


class OperationShape(str, Enum):
    """operation 与 application/duplicate 指针的三态（互斥且穷尽）。"""

    pre_correlation = "pre_correlation"
    primary = "primary"
    duplicate = "duplicate"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 允许状态边
# ═══════════════════════════════════════════════════════════════════════════

#: operation 执行投影的允许边。duplicate 是 terminal，出边为空。
OPERATION_EDGES: Final[Mapping[OperationState, frozenset[OperationState]]] = {
    # `created → application_bound / duplicate` 是合法直达边：recovery claim 在**同一
    # 事务**内创建 shell 并立即 create-or-hit application（design §recovery claim），
    # 中间不经过 command_pending/accepted（recovery 不调用 Command Service）。
    OperationState.created: frozenset({
        OperationState.command_pending, OperationState.accepted,
        OperationState.waiting_application, OperationState.application_bound,
        OperationState.duplicate,
        OperationState.extracting, OperationState.merging,
        OperationState.rejected, OperationState.error,
        OperationState.applied, OperationState.superseded,
        OperationState.authorization_stale,
    }),
    OperationState.command_pending: frozenset({
        OperationState.accepted, OperationState.waiting_application,
        OperationState.application_bound, OperationState.duplicate,
        OperationState.rejected,
        OperationState.error, OperationState.authorization_stale,
        OperationState.superseded,
    }),
    OperationState.accepted: frozenset({
        OperationState.waiting_application, OperationState.application_bound,
        OperationState.duplicate, OperationState.error,
        OperationState.rejected, OperationState.superseded,
        OperationState.authorization_stale,
    }),
    OperationState.waiting_application: frozenset({
        OperationState.application_bound, OperationState.duplicate,
        OperationState.error, OperationState.superseded,
        OperationState.authorization_stale,
    }),
    OperationState.application_bound: frozenset({
        OperationState.extracting, OperationState.merging,
        OperationState.conflict, OperationState.rematerializing,
        OperationState.applying, OperationState.applied,
        OperationState.refresh_required, OperationState.error,
        OperationState.superseded, OperationState.authorization_stale,
    }),
    OperationState.extracting: frozenset({
        OperationState.merging, OperationState.error,
        OperationState.superseded, OperationState.authorization_stale,
    }),
    OperationState.merging: frozenset({
        OperationState.conflict, OperationState.rematerializing,
        OperationState.error, OperationState.superseded,
        OperationState.authorization_stale,
    }),
    OperationState.conflict: frozenset({
        OperationState.merging, OperationState.rematerializing,
        OperationState.error, OperationState.superseded,
        OperationState.authorization_stale,
    }),
    OperationState.rematerializing: frozenset({
        OperationState.applying, OperationState.refresh_required,
        OperationState.error, OperationState.superseded,
        OperationState.authorization_stale,
    }),
    OperationState.applying: frozenset({
        OperationState.applied, OperationState.refresh_required,
        OperationState.error, OperationState.superseded,
        OperationState.authorization_stale,
    }),
    # ── terminal ──
    OperationState.duplicate: frozenset(),
    OperationState.applied: frozenset(),
    OperationState.refresh_required: frozenset(),
    OperationState.rejected: frozenset(),
    OperationState.superseded: frozenset(),
    OperationState.authorization_stale: frozenset(),
    # error 可从保存点重试（Requirement 8.9：不再调用 OO forcesave）
    OperationState.error: frozenset({
        OperationState.extracting, OperationState.merging,
        OperationState.rematerializing, OperationState.applying,
        OperationState.superseded, OperationState.authorization_stale,
    }),
}

APPLICATION_EDGES: Final[Mapping[ApplicationState, frozenset[ApplicationState]]] = {
    ApplicationState.queued: frozenset({
        ApplicationState.validating, ApplicationState.error,
        ApplicationState.superseded, ApplicationState.authorization_stale,
    }),
    ApplicationState.validating: frozenset({
        ApplicationState.extracting, ApplicationState.error,
        ApplicationState.superseded, ApplicationState.authorization_stale,
    }),
    ApplicationState.extracting: frozenset({
        ApplicationState.merging, ApplicationState.error,
        ApplicationState.superseded, ApplicationState.authorization_stale,
    }),
    ApplicationState.merging: frozenset({
        ApplicationState.conflict, ApplicationState.rematerializing,
        ApplicationState.error, ApplicationState.superseded,
        ApplicationState.authorization_stale,
    }),
    ApplicationState.conflict: frozenset({
        ApplicationState.merging, ApplicationState.rematerializing,
        ApplicationState.error, ApplicationState.superseded,
        ApplicationState.authorization_stale,
    }),
    ApplicationState.rematerializing: frozenset({
        ApplicationState.applying, ApplicationState.refresh_required,
        ApplicationState.error, ApplicationState.superseded,
        ApplicationState.authorization_stale,
    }),
    ApplicationState.applying: frozenset({
        ApplicationState.applied, ApplicationState.refresh_required,
        ApplicationState.error, ApplicationState.superseded,
        ApplicationState.authorization_stale,
    }),
    ApplicationState.error: frozenset({
        ApplicationState.extracting, ApplicationState.merging,
        ApplicationState.rematerializing, ApplicationState.applying,
        ApplicationState.superseded, ApplicationState.authorization_stale,
    }),
    ApplicationState.applied: frozenset(),
    ApplicationState.refresh_required: frozenset(),
    ApplicationState.superseded: frozenset(),
    ApplicationState.authorization_stale: frozenset(),
}

REQUEST_EDGES: Final[Mapping[RequestState, frozenset[RequestState]]] = {
    RequestState.frozen: frozenset({
        RequestState.pending, RequestState.accepted, RequestState.correlated,
        RequestState.rejected, RequestState.terminal, RequestState.unmatched,
        RequestState.superseded, RequestState.authorization_stale,
    }),
    RequestState.pending: frozenset({
        RequestState.accepted, RequestState.rejected,
        RequestState.superseded, RequestState.authorization_stale,
    }),
    RequestState.accepted: frozenset({
        RequestState.correlated, RequestState.unmatched, RequestState.terminal,
        RequestState.superseded, RequestState.authorization_stale,
    }),
    RequestState.correlated: frozenset({
        RequestState.terminal, RequestState.superseded,
        RequestState.authorization_stale,
    }),
    RequestState.unmatched: frozenset({
        RequestState.terminal, RequestState.superseded,
        RequestState.authorization_stale,
    }),
    RequestState.terminal: frozenset(),
    RequestState.rejected: frozenset(),
    RequestState.superseded: frozenset(),
    RequestState.authorization_stale: frozenset(),
}

ROOM_EDGES: Final[Mapping[RoomState, frozenset[RoomState]]] = {
    RoomState.opening: frozenset({
        RoomState.active, RoomState.refresh_required, RoomState.superseded,
        RoomState.closed, RoomState.recovery_required,
    }),
    RoomState.active: frozenset({
        RoomState.close_barrier, RoomState.refresh_required,
        RoomState.superseded, RoomState.closed, RoomState.recovery_required,
    }),
    RoomState.close_barrier: frozenset({
        RoomState.closing, RoomState.superseded, RoomState.closed,
        RoomState.recovery_required, RoomState.refresh_required,
    }),
    RoomState.closing: frozenset({
        RoomState.closed, RoomState.superseded, RoomState.recovery_required,
    }),
    RoomState.refresh_required: frozenset({
        RoomState.superseded, RoomState.closed, RoomState.recovery_required,
    }),
    RoomState.superseded: frozenset(),
    RoomState.closed: frozenset(),
    RoomState.recovery_required: frozenset({RoomState.superseded}),
}

PARTICIPANT_EDGES: Final[Mapping[ParticipantState, frozenset[ParticipantState]]] = {
    ParticipantState.active: frozenset({
        ParticipantState.closing, ParticipantState.left,
        ParticipantState.revoked, ParticipantState.expired,
    }),
    # closing 仍可被撤销/过期（Requirement 10.4 的 leader authorization_stale 路径）
    ParticipantState.closing: frozenset({
        ParticipantState.left, ParticipantState.revoked, ParticipantState.expired,
    }),
    ParticipantState.left: frozenset(),
    ParticipantState.revoked: frozenset(),
    ParticipantState.expired: frozenset(),
}

CLOSE_INTENT_EDGES: Final[Mapping[CloseIntentState, frozenset[CloseIntentState]]] = {
    CloseIntentState.created: frozenset({
        CloseIntentState.ordinary_forcesaving, CloseIntentState.waiting_barrier,
        CloseIntentState.leader_ready, CloseIntentState.authorization_stale,
        CloseIntentState.recovery_required, CloseIntentState.superseded,
        CloseIntentState.error, CloseIntentState.retryable_blocked,
    }),
    CloseIntentState.ordinary_forcesaving: frozenset({
        CloseIntentState.waiting_barrier, CloseIntentState.leader_ready,
        CloseIntentState.authorization_stale, CloseIntentState.recovery_required,
        CloseIntentState.superseded, CloseIntentState.error,
    }),
    # waiting_barrier → promoted：barrier predecessors 全部安全终结后，reconciler 直接 CAS
    # 提升等待中的 leader（design §close intent：leader 等 predecessor terminal 后才 promote）。
    CloseIntentState.waiting_barrier: frozenset({
        CloseIntentState.leader_ready, CloseIntentState.promoted,
        CloseIntentState.retryable_blocked,
        CloseIntentState.authorization_stale, CloseIntentState.recovery_required,
        CloseIntentState.superseded, CloseIntentState.error,
    }),
    # leader_ready → waiting_barrier 是合法回退：reconciler 复查时若 active 未归零或
    # barrier predecessor 又出现未终结的普通 forcesave，leader 必须退回等待，不得抢跑。
    CloseIntentState.leader_ready: frozenset({
        CloseIntentState.promoted, CloseIntentState.waiting_barrier,
        CloseIntentState.authorization_stale,
        CloseIntentState.recovery_required, CloseIntentState.superseded,
        CloseIntentState.error, CloseIntentState.retryable_blocked,
    }),
    CloseIntentState.retryable_blocked: frozenset({
        CloseIntentState.leader_ready, CloseIntentState.authorization_stale,
        CloseIntentState.recovery_required, CloseIntentState.superseded,
        CloseIntentState.error,
    }),
    # leader 在 promotion 前失去资格 ⇒ 审计为 authorization_stale，并选 successor
    CloseIntentState.authorization_stale: frozenset({
        CloseIntentState.superseded, CloseIntentState.recovery_required,
    }),
    CloseIntentState.successor_selected: frozenset({
        CloseIntentState.promoted, CloseIntentState.waiting_barrier,
        CloseIntentState.leader_ready, CloseIntentState.authorization_stale,
        CloseIntentState.recovery_required, CloseIntentState.superseded,
    }),
    # promoted 之后授权失效只能由最终 fence 走 recovery，不得再选 successor
    CloseIntentState.promoted: frozenset({
        CloseIntentState.authorization_stale, CloseIntentState.recovery_required,
        CloseIntentState.superseded, CloseIntentState.error,
    }),
    CloseIntentState.recovery_required: frozenset({CloseIntentState.superseded}),
    CloseIntentState.superseded: frozenset(),
    CloseIntentState.error: frozenset({CloseIntentState.superseded}),
}

RECOVERY_CASE_EDGES: Final[Mapping[RecoveryCaseState, frozenset[RecoveryCaseState]]] = {
    RecoveryCaseState.unclaimed: frozenset({
        RecoveryCaseState.claiming, RecoveryCaseState.download_only,
        RecoveryCaseState.quarantined, RecoveryCaseState.expired,
    }),
    RecoveryCaseState.claiming: frozenset({
        RecoveryCaseState.application_created, RecoveryCaseState.unclaimed,
        RecoveryCaseState.download_only, RecoveryCaseState.quarantined,
        RecoveryCaseState.expired,
    }),
    RecoveryCaseState.application_created: frozenset(),
    RecoveryCaseState.download_only: frozenset(),
    RecoveryCaseState.quarantined: frozenset({RecoveryCaseState.expired}),
    RecoveryCaseState.expired: frozenset(),
}

DELIVERY_EDGES: Final[Mapping[DeliveryState, frozenset[DeliveryState]]] = {
    DeliveryState.received: frozenset({
        DeliveryState.downloading, DeliveryState.rejected, DeliveryState.error,
    }),
    DeliveryState.downloading: frozenset({
        DeliveryState.durable, DeliveryState.rejected, DeliveryState.error,
    }),
    DeliveryState.durable: frozenset({
        DeliveryState.acknowledged, DeliveryState.unmatched, DeliveryState.error,
    }),
    DeliveryState.unmatched: frozenset({DeliveryState.acknowledged, DeliveryState.error}),
    DeliveryState.acknowledged: frozenset({DeliveryState.error}),
    DeliveryState.rejected: frozenset(),
    DeliveryState.error: frozenset(),
}

CANDIDATE_EDGES: Final[Mapping[CandidateState, frozenset[CandidateState]]] = {
    CandidateState.staged: frozenset({
        CandidateState.awaiting_contract, CandidateState.ready,
        CandidateState.rejected, CandidateState.orphaned,
    }),
    CandidateState.awaiting_contract: frozenset({
        CandidateState.ready, CandidateState.rejected, CandidateState.orphaned,
    }),
    CandidateState.ready: frozenset({
        CandidateState.finalized, CandidateState.rejected, CandidateState.orphaned,
    }),
    CandidateState.finalized: frozenset(),
    CandidateState.rejected: frozenset({CandidateState.orphaned}),
    CandidateState.orphaned: frozenset(),
}

PENDING_MUTATION_EDGES: Final[Mapping[PendingMutationState, frozenset[PendingMutationState]]] = {
    PendingMutationState.pending: frozenset({
        PendingMutationState.committing, PendingMutationState.expired,
        PendingMutationState.invalidated,
    }),
    # 事务前失败可回到 pending 重试（design §pending mutation）
    PendingMutationState.committing: frozenset({
        PendingMutationState.committed, PendingMutationState.pending,
        PendingMutationState.expired, PendingMutationState.invalidated,
    }),
    PendingMutationState.committed: frozenset(),
    PendingMutationState.expired: frozenset(),
    PendingMutationState.invalidated: frozenset(),
}

#: incoming artifact 的两支：durable 与 quarantined 不可互转（Requirement 5.6）。
INCOMING_ARTIFACT_EDGES: Final[Mapping[ArtifactState, frozenset[ArtifactState]]] = {
    ArtifactState.staged: frozenset({ArtifactState.durable, ArtifactState.quarantined}),
    ArtifactState.durable: frozenset({ArtifactState.orphan, ArtifactState.deleted}),
    ArtifactState.quarantined: frozenset({ArtifactState.orphan, ArtifactState.deleted}),
    ArtifactState.orphan: frozenset({ArtifactState.deleted}),
    ArtifactState.deleted: frozenset(),
}

#: 全部状态机的登记表：`assert_transition` 只接受这里登记的机器。
STATE_MACHINES: Final[Mapping[str, Mapping[Enum, frozenset]]] = {
    "operation": OPERATION_EDGES,
    "application": APPLICATION_EDGES,
    "request": REQUEST_EDGES,
    "room": ROOM_EDGES,
    "participant": PARTICIPANT_EDGES,
    "close_intent": CLOSE_INTENT_EDGES,
    "recovery_case": RECOVERY_CASE_EDGES,
    "delivery": DELIVERY_EDGES,
    "candidate": CANDIDATE_EDGES,
    "pending_mutation": PENDING_MUTATION_EDGES,
    "incoming_artifact": INCOMING_ARTIFACT_EDGES,
}

#: 各机器的 terminal 状态（出边为空）。
TERMINAL_STATES: Final[Mapping[str, frozenset]] = {
    name: frozenset(s for s, outs in edges.items() if not outs)
    for name, edges in STATE_MACHINES.items()
}


# ═══════════════════════════════════════════════════════════════════════════
# 3. 异常（fail-visible；禁 except Exception 降级）
# ═══════════════════════════════════════════════════════════════════════════


class SyncDomainError(RuntimeError):
    """同步域基类。所有子类都带明确 `error_code`，禁止被宽泛 except 吞掉。"""

    error_code = "sync_domain_error"


class StateTransitionError(SyncDomainError):
    error_code = "illegal_state_transition"


class IdentityError(SyncDomainError):
    """identity 输入非法（空 digest / 全零 hash / 缺 bundle 或 authority model）。"""

    error_code = "invalid_identity"


class RevisionConflictError(SyncDomainError):
    """business revision 乐观锁失败。"""

    error_code = "revision_conflict"


class IdempotencyConflictError(SyncDomainError):
    """同 Idempotency-Key 但 initiator/kind/payload 不等值 ⇒ HTTP 409。

    🔴 `http_status=409` 且**不携带旧标识**：Requirement 4.1 明确「任一不等 SHALL
    返回 409 且不得返回旧标识」，泄露旧 request/operation id 等于把别人的资源 id
    交给冲突方。
    """

    error_code = "idempotency_conflict"
    http_status = 409


class ScopeIntegrityError(SyncDomainError):
    """scope index 违规：跨 scope 绑定、id 复用、物理删除、清空 tombstone、孤儿 child。"""

    error_code = "scope_integrity_violation"


class DuplicateLinkError(SyncDomainError):
    """duplicate 指针违规：self / 链 / 环 / 目标未绑定 application / 跨 scope。"""

    error_code = "invalid_duplicate_link"


class QuarantinedIncomingError(SyncDomainError):
    """quarantined incoming 不得创建 application、不得进入 engine（Requirement 5.6）。

    🔴 与 :class:`IncomingNotDurableError` **必须**是两个类型：quarantine 是**永久**的
    安全策略终态（只允许 download-only/expire/retention，永不解除），而「尚未 durable」
    是**暂态**（下载/校验还没走完，稍后可能变 durable）。若共用一个异常类型，把
    quarantine 专属分支短路掉之后，暂态分支会抛出同一类型把它遮蔽 —— 变异检验实测判
    GREEN，即「隔离永不解除」这条判据根本没被守卫锁住。
    """

    error_code = "quarantined_incoming_rejected"


class IncomingNotDurableError(SyncDomainError):
    """incoming 尚未 durable（或 kind 不是 incoming）—— 暂态，不是隔离终态。"""

    error_code = "incoming_not_durable"


class BundleIntegrityError(SyncDomainError):
    """bundle typed slots / child kind/state/digest / approved contract child 违规。

    `slot` 装的是**首个非法 slot**（按 :class:`BundleSlot` 声明序）。它不是给日志看的
    装饰：AC 6.10 / Task 65 正文要求「指出首个非法 slot」，而调用方（provisioner、
    repository、opaque gate）都只有一个 `except BundleIntegrityError` —— 没有这个字段时
    「是哪一个 slot 先坏的」只能靠解析中文消息，那不是可依赖的接口。
    """

    error_code = "invalid_definition_bundle"

    def __init__(self, message: str, *, slot: "BundleSlot | None" = None) -> None:
        super().__init__(message)
        self.slot = slot

    @property
    def first_illegal_slot(self) -> str | None:
        """首个非法 slot 的名字（无从判定时 None）。"""
        return None if self.slot is None else self.slot.value


# 🔴 五类非法空值各自一个异常类型 —— 与 `endpoint_guard` 的 404/403 家族同一理由：
#    共用一个类型时，把靠前的分支短路掉之后靠后的分支会抛出**同样的**类型顶上来，
#    只断言类型的守卫判 GREEN，那条判据于是从未被锁住。本 spec 已三次实测到该形态。
#    全部继承 :class:`BundleIntegrityError`，所以既有 `except BundleIntegrityError`
#    的调用方一行都不用改。


class BundleSlotOmissionError(BundleIntegrityError):
    """① slot 整个缺席 —— 缺席不表示「可选」，那是 typed null marker 的职责。"""

    error_code = "bundle_slot_omission"


class BundleSlotNullFieldError(BundleIntegrityError):
    """② slot 字段是 SQL NULL / JSON NULL。"""

    error_code = "bundle_slot_null_field"


class BundleSlotEmptyFieldError(BundleIntegrityError):
    """③ slot 字段是空串或纯空白。"""

    error_code = "bundle_slot_empty_field"


class BundleSlotAllZeroDigestError(BundleIntegrityError):
    """④ 全零 hash —— 在 `char(64)` 与 hex 正则层面都合法，是典型的「忘了算 hash」伪身份。"""

    error_code = "bundle_slot_all_zero_digest"


class BundleSlotMalformedDigestError(BundleIntegrityError):
    """digest 形态非法（非 64 位小写 hex）—— 与全零分开，因为成因与修法都不同。"""

    error_code = "bundle_slot_malformed_digest"


class SupersedeError(SyncDomainError):
    """supersede 违规：self-supersede，或同 canonical application 因自身更高 sequence 被 supersede。"""

    error_code = "invalid_supersede"


class DeliveryOwnershipError(SyncDomainError):
    """delivery 归属违规：双 owner，或 durable fact 存在却零 owner。"""

    error_code = "invalid_delivery_ownership"


# ═══════════════════════════════════════════════════════════════════════════
# 4. 状态边校验
# ═══════════════════════════════════════════════════════════════════════════


def assert_transition(machine: str, from_state: Enum | str | None, to_state: Enum | str) -> None:
    """校验一条状态转换属于登记的允许边，否则抛 :class:`StateTransitionError`。

    `from_state=None` 表示新建（初始状态），只校验目标是登记状态。
    """
    edges = STATE_MACHINES.get(machine)
    if edges is None:
        raise StateTransitionError(f"未登记的状态机: {machine!r}")
    key_type = type(next(iter(edges)))

    def _coerce(v: Enum | str) -> Enum:
        if isinstance(v, key_type):
            return v
        try:
            return key_type(v)
        except ValueError as exc:
            raise StateTransitionError(f"{machine}: 未登记状态 {v!r}") from exc

    target = _coerce(to_state)
    if target not in edges:
        raise StateTransitionError(f"{machine}: 未登记状态 {to_state!r}")
    if from_state is None:
        return
    source = _coerce(from_state)
    if source not in edges:
        raise StateTransitionError(f"{machine}: 未登记状态 {from_state!r}")
    if target not in edges[source]:
        raise StateTransitionError(
            f"{machine}: 非法状态边 {source.value} → {target.value}"
            f"（允许 {sorted(s.value for s in edges[source])}）"
        )


def is_terminal(machine: str, state: Enum | str) -> bool:
    """该状态是否 terminal（出边为空）。"""
    edges = STATE_MACHINES[machine]
    key_type = type(next(iter(edges)))
    s = state if isinstance(state, key_type) else key_type(state)
    return not edges[s]


# ═══════════════════════════════════════════════════════════════════════════
# 5. operation 三态 / delivery 归属 / sequence fold
# ═══════════════════════════════════════════════════════════════════════════


def classify_operation_shape(
    *,
    application_id: uuid.UUID | None,
    duplicate_of_operation_id: uuid.UUID | None,
    state: OperationState | str,
) -> OperationShape:
    """把 operation 归入 pre_correlation / primary / duplicate 三态，非法组合抛异常。

    三态互斥且穷尽（design §working_paper_sync_operation）：

    ==================  ==============  =========================  ==============
    形态                application_id  duplicate_of_operation_id  state
    ==================  ==============  =========================  ==============
    pre_correlation     NULL            NULL                       ≠ duplicate
    primary             非空            NULL                       ≠ duplicate
    duplicate           NULL            非空                       = duplicate
    ==================  ==============  =========================  ==============
    """
    st = state if isinstance(state, OperationState) else OperationState(state)
    if application_id is not None and duplicate_of_operation_id is not None:
        raise DuplicateLinkError(
            "operation 同时绑定 application 与 duplicate 指针 —— primary/duplicate 必须互斥"
        )
    if duplicate_of_operation_id is not None:
        if st is not OperationState.duplicate:
            raise DuplicateLinkError(
                f"duplicate 必为 terminal state='duplicate'，实得 {st.value}"
            )
        return OperationShape.duplicate
    if st is OperationState.duplicate:
        raise DuplicateLinkError("state='duplicate' 但缺 duplicate_of_operation_id（stranded shell）")
    if application_id is not None:
        return OperationShape.primary
    return OperationShape.pre_correlation


@dataclass(frozen=True)
class OperationScope:
    """duplicate 链校验所需的 scope + frozen bundle 身份。"""

    operation_id: uuid.UUID
    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    room_id: uuid.UUID | None
    definition_bundle_id: uuid.UUID
    authority_model_definition_sha256: str
    application_id: uuid.UUID | None
    duplicate_of_operation_id: uuid.UUID | None
    state: OperationState


def assert_direct_primary(
    *, loser: OperationScope, target: OperationScope, application_id: uuid.UUID
) -> None:
    """校验 duplicate 只能直指「同 scope + 同 frozen bundle 且已绑定该 application」的 primary。

    覆盖 Property 18 / 64 的五条禁令：self-reference、指向另一个 duplicate（链/环）、
    指向未绑定 application 的 shell（stranded）、跨 scope、跨 bundle。
    """
    if loser.operation_id == target.operation_id:
        raise DuplicateLinkError("duplicate 不得 self-reference")
    # 🔴 「目标本身不能是 duplicate」的两个判据合并在同一条 if 里（与 V151 的
    # `wpsync_check_operation_duplicate_link` 对称）：指针与 state 是同一件事的两面，
    # 任一面被短路都必须打红，所以守卫要用**只触发其中一面**的输入分别覆盖。
    if (
        target.duplicate_of_operation_id is not None
        or target.state is OperationState.duplicate
    ):
        raise DuplicateLinkError(
            "duplicate 只能直指 primary："
            f"target(duplicate_of={target.duplicate_of_operation_id!r}, "
            f"state={target.state.value}) 本身就是 duplicate —— 禁止链与环"
        )
    # 刻意**不**单独写 `target.application_id is None`：那条永远被下面的不等值比较
    # 覆盖（application_id 非空时 `None != application_id` 恒真），单独写就是不可达
    # 分支（变异检验实测短路它判 GREEN）。stranded duplicate 由本条一并拒绝。
    if target.application_id != application_id:
        raise DuplicateLinkError(
            f"duplicate 目标的 application={target.application_id!r} 与本次 canonical "
            f"application={application_id!r} 不一致（None 即 stranded shell）"
        )
    if (
        loser.project_id != target.project_id
        or loser.wp_id != target.wp_id
        or loser.entry_id != target.entry_id
        or loser.room_id != target.room_id
    ):
        raise DuplicateLinkError("duplicate 目标跨 scope（project/wp/entry/room 不一致）")
    if (
        loser.definition_bundle_id != target.definition_bundle_id
        or loser.authority_model_definition_sha256 != target.authority_model_definition_sha256
    ):
        raise DuplicateLinkError("duplicate 目标的 frozen bundle / authority model 不一致")


def fold_effective_sequence(existing: int, incoming: int) -> int:
    """`effective_request_sequence = GREATEST(existing, incoming)`。

    单调提升语义的唯一真源：同一 canonical application 命中更高 sequence 的 request
    时只 fold，绝不回退，也绝不因此把自己 supersede（见 :func:`assert_supersede`）。
    """
    if existing < 1 or incoming < 1:
        raise IdentityError(f"request sequence 必须 >= 1，实得 existing={existing} incoming={incoming}")
    return max(existing, incoming)


def assert_supersede(
    *,
    old_application_id: uuid.UUID,
    new_application_id: uuid.UUID,
    old_effective_sequence: int,
    new_effective_sequence: int,
) -> None:
    """只有「较新且 canonical application 不同」的 durable snapshot 才可 supersede 旧 application。

    禁 self-supersede（Requirement 5.5 / Property 18 / Property 36）：同一 canonical
    application 因 same-key duplicate 抬高 effective sequence 时，绝不能把自己判 stale。
    """
    if old_application_id == new_application_id:
        raise SupersedeError(
            "self-supersede：同一 canonical application 的更高 sequence 只 fold，不得 supersede 自己"
        )
    if new_effective_sequence <= old_effective_sequence:
        raise SupersedeError(
            f"supersede 要求更高 effective sequence，实得 new={new_effective_sequence} "
            f"<= old={old_effective_sequence}"
        )


def assert_delivery_ownership(
    *,
    state: DeliveryState | str,
    durable_at_is_set: bool,
    application_id: uuid.UUID | None,
    callback_recovery_case_id: uuid.UUID | None,
    forcesave_request_id: uuid.UUID | None = None,
) -> None:
    """delivery 归属只按 immutable `durable_at` 判定（Requirement 5.4）。

    * 任何阶段禁双 owner；
    * `durable_at IS NULL` 的 pre-durable `received/downloading/rejected/error`
      可零 application/recovery owner（可保留已精确绑定的 request/operation shell）；
    * `durable_at IS NOT NULL` ⇒ application 与 recovery 恰属其一（XOR）；
    * **request 与 application 不做 XOR** —— 成功 request-first correlation 后二者同时存在
      是正常态，把它们做 XOR 是 Task 10 明令禁止的错误建模。
    """
    st = state if isinstance(state, DeliveryState) else DeliveryState(state)
    if application_id is not None and callback_recovery_case_id is not None:
        raise DeliveryOwnershipError("delivery 双 owner（application 与 recovery case 同时非空）")
    if durable_at_is_set:
        if (application_id is None) == (callback_recovery_case_id is None):
            raise DeliveryOwnershipError(
                "durable fact 存在 ⇒ application / recovery 必须恰属其一；"
                f"实得 application={application_id!r} recovery={callback_recovery_case_id!r}"
            )
    else:
        if st in (DeliveryState.durable, DeliveryState.acknowledged, DeliveryState.unmatched):
            raise DeliveryOwnershipError(
                f"state={st.value} 必须有 durable_at（禁止把泛化 terminal 当 durable）"
            )
    # request 与 application 可同时存在：此处刻意**不**校验二者互斥。
    _ = forcesave_request_id


# ═══════════════════════════════════════════════════════════════════════════
# 6. identity 计算
# ═══════════════════════════════════════════════════════════════════════════


def _require_digest(name: str, value: str) -> str:
    if not is_digest(value):
        raise IdentityError(
            f"{name} 必须是非空 64 位小写 hex 且非全零 digest，实得 {value!r}"
        )
    return value.strip()


def _sha256_join(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def compute_application_key(
    *,
    wp_id: uuid.UUID,
    room_id: uuid.UUID,
    generation: int,
    frozen_client_base_version_id: uuid.UUID,
    frozen_client_base_representation_id: uuid.UUID,
    incoming_sha256: str,
    definition_bundle_sha256: str,
    authority_model_definition_sha256: str,
    adapter_build_digest: str,
) -> str:
    """application key = frozen request 值 + durable incoming（design §content_application）。

    ``sha256(wp_id | room_id | generation | frozen_client_base_version_id |
    frozen_client_base_representation_id | incoming_sha256 |
    definition_bundle_sha256 | authority_model_definition_sha256 |
    adapter_build_digest)``

    🔴 Property 64：入参**不含** callback status、request id、request sequence、
    callback 到达时的 room last-applied 指针。故：
    * 同 frozen identity 的 status 6 / status 2 / 网络重试得到同一 key；
    * base / representation / bundle / authority model 任一不同即得不同 key，
      「相同 incoming + 不同 frozen identity」永不折叠。
    """
    if generation < 1:
        raise IdentityError(f"generation 必须 >= 1，实得 {generation}")
    return _sha256_join([
        str(wp_id),
        str(room_id),
        str(generation),
        str(frozen_client_base_version_id),
        str(frozen_client_base_representation_id),
        _require_digest("incoming_sha256", incoming_sha256),
        _require_digest("definition_bundle_sha256", definition_bundle_sha256),
        _require_digest(
            "authority_model_definition_sha256", authority_model_definition_sha256
        ),
        _require_digest("adapter_build_digest", adapter_build_digest),
    ])


def compute_frozen_request_fingerprint(
    *,
    client_confirmation_id: uuid.UUID,
    client_base_version_id: uuid.UUID,
    client_base_representation_id: uuid.UUID,
    client_base_projection_sha256: str,
    definition_bundle_sha256: str,
    authority_model_definition_sha256: str,
    adapter_build_digest: str,
    contributor_snapshot_digest: str,
    client_edit_epoch: int,
    write_fence_epoch: int,
    initiator_permission_epoch: int,
) -> str:
    """canonical frozen request fingerprint：cache hit 必须逐项等值才可返回旧 request。

    覆盖 Requirement 4.1 的「initiator、kind、confirmation、base/representation、
    bundle、fence 与 contributor digest 全部相同的重放才可返回原 request/operation」。
    initiator 与 kind 已在复合唯一键 `(room,generation,initiator,kind,key)` 里，
    故 fingerprint 只需覆盖 payload 侧。
    """
    if write_fence_epoch < 1:
        raise IdentityError(f"write_fence_epoch 必须 >= 1，实得 {write_fence_epoch}")
    if client_edit_epoch < 0 or initiator_permission_epoch < 0:
        raise IdentityError("client_edit_epoch / initiator_permission_epoch 不得为负")
    return _sha256_join([
        "forcesave-request-fingerprint:v1",
        str(client_confirmation_id),
        str(client_base_version_id),
        str(client_base_representation_id),
        _require_digest("client_base_projection_sha256", client_base_projection_sha256),
        _require_digest("definition_bundle_sha256", definition_bundle_sha256),
        _require_digest(
            "authority_model_definition_sha256", authority_model_definition_sha256
        ),
        _require_digest("adapter_build_digest", adapter_build_digest),
        _require_digest("contributor_snapshot_digest", contributor_snapshot_digest),
        str(client_edit_epoch),
        str(write_fence_epoch),
        str(initiator_permission_epoch),
    ])


def compute_delivery_key(
    *,
    room_id: uuid.UUID,
    generation: int,
    callback_status: int,
    discriminator: str,
) -> str:
    """delivery key **含** status 与 OO/userdata discriminator（Requirement 5.4）。

    与 application key 的关键区别：同 frozen identity 的 status 6 / status 2 /
    网络重试各自是**独立 delivery**（各留证据），但只对应**一个** application。
    """
    if generation < 1:
        raise IdentityError(f"generation 必须 >= 1，实得 {generation}")
    if not discriminator or not discriminator.strip():
        raise IdentityError("delivery discriminator 不得为空（否则重试会撞同一 delivery row）")
    return _sha256_join([
        "callback-delivery-key:v1",
        str(room_id),
        str(generation),
        str(callback_status),
        discriminator.strip(),
    ])


def compute_eligibility_digest(
    *, room_id: uuid.UUID, generation: int, eligibility_epoch: int,
    eligible_intent_ids: list[uuid.UUID],
) -> str:
    """close leader 候选资格快照 digest：同 snapshot 重放不得换 leader（Property 63）。"""
    if eligibility_epoch < 0:
        raise IdentityError(f"eligibility_epoch 不得为负，实得 {eligibility_epoch}")
    return _sha256_join([
        "close-leader-eligibility:v1",
        str(room_id),
        str(generation),
        str(eligibility_epoch),
        ",".join(sorted(str(i) for i in eligible_intent_ids)),
    ])


def compute_bundle_slots_digest(
    *,
    authority_model: "AuthorityModel | str",
    authority_model_definition_sha256: str,
    slots: Mapping["BundleSlot", "BundleSlotSpec"],
) -> str:
    """approved bundle 的 **typed-slot inventory** digest（Requirement 2.5 / 3.7 / 4.1）。

    room、descriptor confirmation、每个 forcesave/close request 都要冻结「同一 bundle 的
    typed-slot 清单」。它不能等于 `definition_bundle_sha256`：后者是 canonical payload
    的 digest，而 confirm-descriptor / forcesave 需要逐项比对的是
    `(authority model, 三个 slot 的 type/ref/digest)` 这份**清单本身** —— 换一个 slot
    ref 但 payload 里别的字段一起变时，只比 payload digest 无法指出「是哪一个 slot 漂了」。

    🔴 slot 顺序按 :class:`BundleSlot` 的**声明序**固定，不按 dict 插入序：dict 序会让
    同一 bundle 在不同代码路径（repository 构造 / descriptor 构造）算出不同 digest，
    表现为「明明是同一个 bundle 却报 identity 漂移」，而两边都没错。
    """
    model = authority_model.value if isinstance(authority_model, AuthorityModel) else str(
        authority_model
    )
    if model not in {item.value for item in AuthorityModel}:
        raise IdentityError(
            f"authority_model={model!r} 不在封闭域 "
            f"{sorted(item.value for item in AuthorityModel)} 内"
        )
    parts = [
        "bundle-slots-inventory:v1",
        model,
        _require_digest(
            "authority_model_definition_sha256", authority_model_definition_sha256
        ),
    ]
    for slot in BundleSlot:
        spec = slots.get(slot)
        if spec is None:
            raise IdentityError(
                f"bundle typed-slot 清单缺 {slot.value} —— slot omission 必须 fail closed，"
                "不得以缺席表示「可选」（那正是 typed null marker 存在的原因）"
            )
        parts.extend([
            slot.value,
            spec.slot_type,
            spec.slot_ref,
            _require_digest(f"{slot.value}.slot_digest", spec.slot_digest),
        ])
    return _sha256_join(parts)


def compute_contributor_snapshot_digest(
    *,
    room_id: uuid.UUID,
    generation: int,
    contributor_user_ids: Iterable[uuid.UUID | str],
) -> str:
    """contributor set 的审计快照 digest（Requirement 4.1 的 frozen fingerprint 成分）。

    契约 `multi_user_semantics.contributor_snapshot_source` = `history.changes[].user`，
    `contributor_snapshot_caveat` 明确它**包含已被 drop 的用户**，所以这是审计快照而
    非授权依据 —— 本函数只负责让它可比对、可复现，授权判定由 write fence + participant
    lease 承担（Property 63）。

    排序 + 去重是刻意的：OO 的 `history.changes` 顺序随编辑时序变化，若按到达序入 digest，
    同一批贡献者会算出不同 digest，导致合法重放被误判 409。
    """
    normalized = sorted({str(item).strip().lower() for item in contributor_user_ids if str(item).strip()})
    return _sha256_join([
        "contributor-snapshot:v1",
        str(room_id),
        str(generation),
        ",".join(normalized),
    ])


# ═══════════════════════════════════════════════════════════════════════════
# 7. bundle typed slots 校验（repository 侧，与 DB CHECK/trigger 双向）
# ═══════════════════════════════════════════════════════════════════════════

_MARKER_TYPE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(template|instrumentation|contract):none:v[0-9]+$"
)
_DEFINITION_REF_RE: Final[re.Pattern[str]] = re.compile(
    r"^definition:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


@dataclass(frozen=True)
class BundleSlotSpec:
    """一个 typed canonical slot：type / ref / digest 三者必须同时非空且互相一致。"""

    slot: BundleSlot
    slot_type: str
    slot_ref: str
    slot_digest: str

    @property
    def is_definition(self) -> bool:
        return self.slot_type == "definition"


#: 消息模板写成模块常量而不是内联多行 f-string：`raise` 必须保持**单行**。
#: 变异检验把一整行替换成别的语句时，跨行的 `raise X(` 会变成 SyntaxError ⇒ pytest 报
#: ERROR 而 `-rf` 只列 FAILED ⇒ 四态判定把 GREEN 误读成 RED（Task 61 实测）。
_SLOT_NULL_MSG = "{n} slot {f} 是 SQL/JSON NULL —— NULL 不表示「可选」，可选只能用版本化 typed null marker 表达"
_SLOT_EMPTY_MSG = "{n} slot {f} 是空串/纯空白 —— 空串是一个合法但无身份的值，等于伪造 identity"
_SLOT_ZERO_MSG = "{n} slot digest 是全零 hash —— char(64) 与 hex 正则都放行，属「忘了算 hash 就填 0」的伪身份"
_SLOT_BADHEX_MSG = "{n} slot digest 不是 64 位小写 hex: {v!r}"
_BUNDLE_OMISSION_MSG = "bundle typed slots 缺失: {missing}（三 slot 必须全出现；首个非法 slot: {first}）"


def _assert_slot_field_present(spec: BundleSlotSpec, field: str, value: object) -> None:
    """NULL 与空串**分成两条**：两者成因不同（前者是列没写/JSON 少键，后者是写了个空值），
    合成一条时短路任一半都会被另一半遮蔽。"""
    if value is None:
        raise BundleSlotNullFieldError(
            _SLOT_NULL_MSG.format(n=spec.slot.value, f=field), slot=spec.slot
        )
    if not str(value).strip():
        raise BundleSlotEmptyFieldError(
            _SLOT_EMPTY_MSG.format(n=spec.slot.value, f=field), slot=spec.slot
        )


def _assert_slot_digest_shape(spec: BundleSlotSpec) -> None:
    """digest 四态各自一个类型：NULL / 空串 / 全零 / 非 64 位小写 hex。

    🔴 全零必须**先于** `is_digest` 判断：`is_digest` 对全零也返回 False，合在一起时
    「全零」这条判据就没有任何单点可锁 —— 把它删掉，非法 hex 那条会顶上来抛同类型。
    """
    digest = spec.slot_digest
    _assert_slot_field_present(spec, "digest", digest)
    if str(digest).strip() == "0" * 64:
        raise BundleSlotAllZeroDigestError(
            _SLOT_ZERO_MSG.format(n=spec.slot.value), slot=spec.slot
        )
    if not is_digest(digest):
        raise BundleSlotMalformedDigestError(
            _SLOT_BADHEX_MSG.format(n=spec.slot.value, v=digest), slot=spec.slot
        )


def validate_bundle_slot(spec: BundleSlotSpec) -> None:
    """校验单个 typed slot 的形态：slot omission / NULL / 空串 / 全零 hash / 非法 marker 全拒。

    与 V151 的 `wpsync_assert_bundle_slot()` + `ck_wpsdb_*` 系列 CHECK 双向对齐。

    五类非法空值**各抛各自的子类**（见 :class:`BundleSlotOmissionError` 一族），并在
    `slot` 上带出首个非法 slot；调用方仍可用 `except BundleIntegrityError` 一网打尽。
    """
    name = spec.slot.value
    _assert_slot_field_present(spec, "type", spec.slot_type)
    _assert_slot_field_present(spec, "ref", spec.slot_ref)
    _assert_slot_digest_shape(spec)
    if spec.is_definition:
        if not _DEFINITION_REF_RE.match(spec.slot_ref):
            raise BundleIntegrityError(
                f"{name} slot type=definition 但 ref 不是 `definition:<uuid>`: {spec.slot_ref!r}",
                slot=spec.slot,
            )
        return
    if not _MARKER_TYPE_RE.match(spec.slot_type):
        raise BundleIntegrityError(
            f"{name} slot type 既非 'definition' 也非版本化 typed null marker: {spec.slot_type!r}",
            slot=spec.slot,
        )
    if not spec.slot_type.startswith(f"{name}:none:v"):
        raise BundleIntegrityError(
            f"{name} slot 用了别的 slot 的 marker: {spec.slot_type!r}", slot=spec.slot
        )
    if spec.slot_ref != f"marker:{spec.slot_type}":
        raise BundleIntegrityError(
            f"{name} slot type 与 ref 不一致：type={spec.slot_type!r} ref={spec.slot_ref!r}",
            slot=spec.slot,
        )


def validate_bundle_slots(
    *,
    authority_model: AuthorityModel | str,
    authority_model_definition_sha256: str,
    slots: Mapping[BundleSlot, BundleSlotSpec],
) -> None:
    """校验四个 slot 全出现 + `projection_contract` 三 child 必须均为 approved definition。

    Requirement 2.3 / 3.3：`projection_contract` 标准入口不得用 typed null marker
    冒充 per-entry contract；`custom_authoritative_ooxml / opaque_single_onlyoffice`
    按 authority model 规则使用明确 marker。
    """
    am = authority_model if isinstance(authority_model, AuthorityModel) else AuthorityModel(
        authority_model
    )
    if not is_digest(authority_model_definition_sha256):
        # bundle 级问题一律抛 BundleIntegrityError（而不是 IdentityError）：
        # 调用方按 bundle fail-closed 分支处理，异常类型混用会让 error_code 漂移。
        raise BundleIntegrityError(
            "bundle 的 authority model digest 必须非空非全零"
            f"，实得 {authority_model_definition_sha256!r}"
        )
    # 🔴 缺席按 `BundleSlot` **声明序**取首个 —— 不按 dict 插入序：插入序会让同一份坏
    #    bundle 在不同代码路径报出不同的「首个非法 slot」，运维照着修会修错那一个。
    missing = [s for s in BundleSlot if s not in slots]
    if missing:
        raise BundleSlotOmissionError(
            _BUNDLE_OMISSION_MSG.format(
                missing=[s.value for s in missing], first=missing[0].value
            ),
            slot=missing[0],
        )
    for slot in BundleSlot:
        spec = slots[slot]
        if spec.slot is not slot:
            raise BundleIntegrityError(
                f"slot 键 {slot.value} 与 spec.slot {spec.slot.value} 不符", slot=slot
            )
        validate_bundle_slot(spec)
    if am is AuthorityModel.projection_contract:
        non_definition = [s for s in BundleSlot if not slots[s].is_definition]
        if non_definition:
            raise BundleIntegrityError(
                "projection_contract bundle 的 template/instrumentation/contract 必须全部是 "
                f"approved definition child，实得 marker: "
                f"{[s.value for s in non_definition]}（首个非法 slot: {non_definition[0].value}）",
                slot=non_definition[0],
            )


def validate_definition_child(
    *,
    slot: BundleSlot,
    child_kind: DefinitionKind | str,
    child_state: DefinitionState | str,
    child_sha256: str,
    slot_digest: str,
) -> None:
    """definition child 的 kind / state / digest 必须与 slot 声明一致且已 approved。"""
    kind = child_kind if isinstance(child_kind, DefinitionKind) else DefinitionKind(child_kind)
    state = child_state if isinstance(child_state, DefinitionState) else DefinitionState(child_state)
    if kind.value != slot.value:
        raise BundleIntegrityError(
            f"{slot.value} slot 引用的 definition kind={kind.value} 不符"
        )
    if state is not DefinitionState.approved:
        raise BundleIntegrityError(
            f"{slot.value} slot 的 definition child state={state.value}，只有 approved 可用于 bundle"
        )
    if not is_digest(child_sha256) or child_sha256.strip() != slot_digest.strip():
        raise BundleIntegrityError(
            f"{slot.value} slot digest 与 definition child sha256 不一致"
        )


__all__ = [
    # digest / id
    "is_digest", "is_opaque_resource_id", "is_uuid_text",
    # enums
    "ArtifactKind", "ArtifactState", "DefinitionKind", "DefinitionState",
    "AuthorityModel", "BundleSlot", "CandidateState", "PendingMutationState",
    "ScopeResourceKind", "RoomState", "ParticipantState", "ParticipantMode",
    "ContributorSource", "ContributorConfidence",
    "RequestKind", "RequestState", "CloseIntentState", "RecoveryReason",
    "RecoveryCaseState", "ApplicationState", "ApplicationEventType",
    "OperationDirection", "OperationState", "DeliveryState", "CorrelationResult",
    "ActorType", "OperationShape",
    # state machines
    "STATE_MACHINES", "TERMINAL_STATES", "OPERATION_EDGES", "APPLICATION_EDGES",
    "REQUEST_EDGES", "ROOM_EDGES", "PARTICIPANT_EDGES", "CLOSE_INTENT_EDGES",
    "RECOVERY_CASE_EDGES", "DELIVERY_EDGES", "CANDIDATE_EDGES",
    "PENDING_MUTATION_EDGES", "INCOMING_ARTIFACT_EDGES",
    "assert_transition", "is_terminal",
    # shapes / ownership / fold
    "OperationScope", "classify_operation_shape", "assert_direct_primary",
    "fold_effective_sequence", "assert_supersede", "assert_delivery_ownership",
    # identity
    "compute_application_key", "compute_frozen_request_fingerprint",
    "compute_delivery_key", "compute_eligibility_digest",
    "compute_bundle_slots_digest", "compute_contributor_snapshot_digest",
    # bundle
    "BundleSlotSpec", "validate_bundle_slot", "validate_bundle_slots",
    "validate_definition_child",
    # errors
    "SyncDomainError", "StateTransitionError", "IdentityError",
    "RevisionConflictError", "IdempotencyConflictError", "ScopeIntegrityError",
    "DuplicateLinkError", "QuarantinedIncomingError", "IncomingNotDurableError",
    "BundleIntegrityError", "SupersedeError", "DeliveryOwnershipError",
    # bundle slot 五类非法空值：各自一个类型（Task 65）
    "BundleSlotOmissionError", "BundleSlotNullFieldError",
    "BundleSlotEmptyFieldError", "BundleSlotAllZeroDigestError",
    "BundleSlotMalformedDigestError",
]
