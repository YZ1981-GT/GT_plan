# -*- coding: utf-8 -*-
"""同步域指标目录：声明式定义 + 强制归因维度 + 禁止把特定终态压成普通 error。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 29
Requirements: 13.7, 13.9, 13.10, 5.10
Properties: P68（指标与 timeline 用同一套归因字段）

═══ 为什么指标要有「目录」而不是散落的 `counter.inc()` ═══

Requirement 13.7 列了十几类必须覆盖的指标，13.9 又要求每条告警规则绑定阈值/窗口/
去重键。若指标名散落在各服务里：

* 告警规则引用的指标名可能根本没人 emit（规则永不触发，看板全绿）；
* 同一件事在两处用了两个名字（`forcesave_ok` / `forcesave_accepted`），率值失真；
* 归因维度各写各的，`room` 在一处叫 `room_id`、另一处叫 `room` ⇒ 无法按 room 聚合。

所以本模块是**唯一的指标词汇表**：:data:`METRIC_CATALOG`。`alerting.py` 的规则必须
引用目录里的名字（两侧双向锁死），emit 侧必须通过 :class:`SyncMetrics` 才能记数。

═══ 归因等级：三类，不是「都得有 room」═══

Task 29 的原话是「同一指标必须能按 room/generation/requested+canonical operation/
application 与 participant 归因」。但 outbox 堆积、orphan backlog、retention 删除
**在语义上就没有 room** —— 硬塞一个 `room=unknown` 标签比不塞更坏（它会让「按 room
聚合」这件事看起来能做，实际全落在 unknown 桶）。因此归因按 :class:`AttributionClass`
分三级，且每个指标的等级是**数据**，由守卫与 requirements 双向核对：

* :attr:`AttributionClass.operation_scoped` —— 必须带全部六个核心维度；
* :attr:`AttributionClass.room_scoped` —— 必须带 room/generation/participant；
* :attr:`AttributionClass.platform_scoped` —— 明确没有 room 语义，只带 entry/wp 级别。

「把一个本该 operation_scoped 的指标降级成 platform_scoped」是最省事的作弊路径，
所以降级也必须让守卫红（等级来自目录，改等级即改判据）。

═══ 三类终态不得压成普通 error ═══

Task 29 明文禁止「把 same-app fold、跨 participant 冲突或无 successor 恢复态压成普通
error」。这三件事都是**正确行为**或**需要专门 runbook 的状态**，压进 `error_total`
会造成两种真实伤害：

1. 告警噪音把真错误埋掉（同 key 重试在正常协同下每分钟都会发生）；
2. 值班按 error runbook 处理「无 successor 的 recovery_required」，而那条路径要的是
   重新授权 + 新 generation，不是重试。

:meth:`SyncMetrics.record_error` 因此对 :data:`FORBIDDEN_GENERIC_ERROR_OUTCOMES` 里的
终态直接抛 :class:`MetricAttributionError`，并在异常里指出该用哪个专用指标。

═══ 为什么 `record_outcome` 强制显式结果 ═══

Task 22 的 `handle_callback` 与 Task 26 的 `apply_durable_incoming` **在 incoming
durable 之后刻意不抛异常** —— 失败落在 `outcome.result` / `response_error` 里。于是
「没抛异常就 +1 成功」这种写法会把失败记成成功，而且四层静态检查全绿（Task 27/28 都
为此补过 landed-check）。:meth:`SyncMetrics.record_outcome` 的 `result` 与 `landed`
是**无默认值的必填参数**，调用方必须从 outcome 里显式读出来；守卫对签名有 AST 判据。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final, Mapping

from app.services.workpaper_sync.models import SyncDomainError


class MetricsError(SyncDomainError):
    """指标目录/调用协议违规的基类。**不 fail open** —— 记错比不记更危险。"""

    error_code = "sync_metrics_invalid"


class UnknownMetricError(MetricsError):
    """emit 了目录里没有的指标名。"""

    error_code = "sync_metric_unknown"


class MetricAttributionError(MetricsError):
    """归因维度缺失/多余，或把专用终态压成普通 error。"""

    error_code = "sync_metric_attribution_invalid"


class MetricKind(str, Enum):
    counter = "counter"
    histogram = "histogram"
    gauge = "gauge"


class AttributionClass(str, Enum):
    operation_scoped = "operation_scoped"
    room_scoped = "room_scoped"
    #: room/generation 级的**聚合文档事件**：没有 participant 语义。
    #:
    #: 这一级不是为了省事：AC 5.1 / 10.9 明文「callback 是 room/generation 级服务事件，
    #: 不得把可选 `participant_id` 当作聚合 artifact 的唯一作者或唯一授权依据」。若把
    #: callback 侧指标划成 `room_scoped`（强制 participant），emit 处就只能填 route
    #: participant —— 那正是「route 当作者」这条被禁的归因。
    route_scoped = "route_scoped"
    platform_scoped = "platform_scoped"


class AttributionDim(str, Enum):
    """标签名词汇表。**只有这些名字**可以做维度。"""

    project = "project_id"
    wp = "wp_id"
    entry = "entry_id"
    room = "room_id"
    generation = "generation"
    participant = "participant_id"
    requested_operation = "requested_operation_id"
    canonical_operation = "canonical_operation_id"
    application = "application_id"


#: operation 级指标必须带的六个核心维度（Task 29 的「同一指标必须能按 … 归因」）。
#:
#: `requested_operation` 与 `canonical_operation` **都要**：duplicate 跟随 primary 之后，
#: 只留 canonical 会让「谁发起的重放」彻底不可查（AC 5.10 要求两者都能查）。
OPERATION_ATTRIBUTION: Final[frozenset[AttributionDim]] = frozenset(
    {
        AttributionDim.room,
        AttributionDim.generation,
        AttributionDim.requested_operation,
        AttributionDim.canonical_operation,
        AttributionDim.application,
        AttributionDim.participant,
    }
)

#: room 级指标（还没有 operation/application 时就要能记，例如 fingerprint 409）。
#: 有明确发起人，所以 participant 必填。
ROOM_ATTRIBUTION: Final[frozenset[AttributionDim]] = frozenset(
    {AttributionDim.room, AttributionDim.generation, AttributionDim.participant}
)

#: route 级指标（聚合 callback 事件）：**刻意不含 participant**。
ROUTE_ATTRIBUTION: Final[frozenset[AttributionDim]] = frozenset(
    {AttributionDim.room, AttributionDim.generation}
)

#: 平台级指标的最小归因（无 room 语义）。
PLATFORM_ATTRIBUTION: Final[frozenset[AttributionDim]] = frozenset(
    {AttributionDim.project, AttributionDim.wp}
)

CLASS_REQUIRED_DIMS: Final[Mapping[AttributionClass, frozenset[AttributionDim]]] = {
    AttributionClass.operation_scoped: OPERATION_ATTRIBUTION,
    AttributionClass.room_scoped: ROOM_ATTRIBUTION,
    AttributionClass.route_scoped: ROUTE_ATTRIBUTION,
    AttributionClass.platform_scoped: PLATFORM_ATTRIBUTION,
}

#: 🔴 **禁止**带 participant 维度的归因等级 —— AC 10.9 的机器判据。
#:
#: 把 callback 侧指标带上 participant 就等于宣称「这份聚合 artifact 是这个人写的」。
#: `SyncMetrics._validate_labels` 因此不只检查「缺没缺」，还检查「有没有多」。
FORBIDDEN_DIMS: Final[Mapping[AttributionClass, frozenset[AttributionDim]]] = {
    AttributionClass.route_scoped: frozenset({AttributionDim.participant}),
}


@dataclass(frozen=True)
class MetricDefinition:
    """一个指标的声明。`requirement` 让「为什么需要它」不靠记忆。"""

    name: str
    kind: MetricKind
    attribution: AttributionClass
    requirement: str
    why: str
    #: 该指标是否**必须**有一条告警规则（`alerting.py` 侧双向核对）。
    alert_required: bool = False
    #: counter/gauge 的封闭结果域；空 = 不带 result 标签。
    result_domain: tuple[str, ...] = field(default_factory=tuple)

    @property
    def required_dims(self) -> frozenset[AttributionDim]:
        return CLASS_REQUIRED_DIMS[self.attribution]


_M = MetricDefinition
_C = MetricKind.counter
_H = MetricKind.histogram
_G = MetricKind.gauge
_OP = AttributionClass.operation_scoped
_ROOM = AttributionClass.room_scoped
_ROUTE = AttributionClass.route_scoped
_PLAT = AttributionClass.platform_scoped

#: 🔴 指标唯一真源。名字前缀统一 `workpaper_sync_`，便于看板一把捞。
METRIC_CATALOG: Final[tuple[MetricDefinition, ...]] = (
    # ── forcesave / durable / correlation ───────────────────────────────
    _M(
        "workpaper_sync_forcesave_accepted_total", _C, _ROOM, "13.7",
        "Command Service 接受（**不等于**保存完成，AC 4.12 的第一格）",
        result_domain=("accepted", "rejected", "fence_denied", "refresh_required"),
    ),
    _M(
        "workpaper_sync_incoming_durable_total", _C, _ROUTE, "13.7",
        "incoming artifact 已耐久（AC 4.12 的第二格）。route 级：callback 没有作者",
        result_domain=("durable", "quarantined", "pre_durable_failed"),
    ),
    _M(
        "workpaper_sync_application_bind_total", _C, _OP, "5.10",
        "pre-correlation shell → primary 的唯一 `application_bound`",
        result_domain=("primary_bound", "direct_duplicate"),
    ),
    _M(
        "workpaper_sync_application_correlation_total", _C, _OP, "5.10",
        "correlation 结果分型（request / existing_application / close_capture / "
        "unmatched / ambiguous）",
        result_domain=(
            "request", "existing_application", "close_capture", "unmatched", "ambiguous",
        ),
    ),
    _M(
        "workpaper_sync_forcesave_fingerprint_conflict_total", _C, _ROOM, "13.7",
        "同 Idempotency-Key 跨 participant/kind/payload ⇒ 409。**不是** error：它是"
        "协议要求的拒绝，且必须能按 participant 归因才能查出谁在串键",
        alert_required=True,
        result_domain=("cross_participant", "cross_kind", "payload_mismatch"),
    ),
    _M(
        "workpaper_sync_application_sequence_fold_total", _C, _OP, "5.10",
        "同 canonical application 的更高 sequence 只 fold（origin 不变、不 self-stale）；"
        "压成 error 会把正常协同重试变成告警噪音",
        result_domain=("folded", "rejected_lower_sequence"),
    ),
    _M(
        "workpaper_sync_incoming_sequence_total", _C, _OP, "13.7",
        "durable request 推进 room durable fence 的次数（含 supersede 旧 application）",
        result_domain=("advanced", "superseded_older", "no_advance"),
    ),
    _M(
        "workpaper_sync_delivery_dedupe_total", _C, _OP, "13.7",
        "status 6/2 与网络重试命中同一 frozen identity 的去重次数",
        result_domain=("delivery_key_hit", "application_key_hit"),
    ),
    # ── 阶段耗时与失败 ─────────────────────────────────────────────────
    _M(
        "workpaper_sync_extract_seconds", _H, _OP, "13.7", "extract 阶段耗时",
    ),
    _M(
        "workpaper_sync_merge_seconds", _H, _OP, "13.7", "三方 merge 阶段耗时",
    ),
    _M(
        "workpaper_sync_apply_seconds", _H, _OP, "13.7",
        "durable → applied/conflict 终态耗时（AC 14.12 的 p95 门）",
    ),
    _M(
        "workpaper_sync_rematerialize_failed_total", _C, _OP, "13.9",
        "canonical rematerialize 失败（反读不等值/未管理区域变化）",
        alert_required=True,
        result_domain=("roundtrip_mismatch", "unmanaged_region_changed", "publish_failed"),
    ),
    _M(
        "workpaper_sync_refresh_required_total", _C, _OP, "13.9",
        "merged≠incoming ⇒ room 进 refresh_required，积压说明客户端一直没重开",
        alert_required=True,
        result_domain=("entered", "resolved_by_reopen", "resolved_by_supersede"),
    ),
    _M(
        "workpaper_sync_post_durable_failure_total", _C, _OP, "13.9",
        "**已 durable 之后**的处理失败。单列是因为它与 pre-durable 拒绝的 runbook 完全"
        "不同：文件还在，只能重新授权后 retry，绝不能让 OO 重发",
        alert_required=True,
        result_domain=("extract", "merge", "rematerialize", "authorization_fence", "commit"),
    ),
    # ── recovery ───────────────────────────────────────────────────────
    _M(
        "workpaper_sync_recovery_case_total", _C, _ROUTE, "13.7",
        "durable 但无法唯一归组 ⇒ recovery case（claim 前三实体恒 0）。route 级：建 case 时"
        "**恰恰**是因为归组不出发起人，此时填 participant 就是编造",
        alert_required=True,
        result_domain=("missing_request", "ambiguous_close", "crash_close", "stale_candidate"),
    ),
    _M(
        "workpaper_sync_recovery_claim_total", _C, _ROOM, "13.7",
        "authorization-first claim 的结果分型",
        result_domain=("application_created", "application_hit", "rejected"),
    ),
    _M(
        "workpaper_sync_recovery_download_only_total", _C, _ROUTE, "13.7",
        "download-only 终结：必须证明 request/application/operation 三实体为 0。route 级："
        "case 从未被 claim，`claimed_by_participant_id` 恒 NULL —— 强制 participant 只会"
        "逼调用方拿授权用户冒充 participant",
        result_domain=("terminated", "rejected"),
    ),
    _M(
        "workpaper_sync_unmatched_status2_total", _C, _ROUTE, "13.9",
        "status=2 无 userdata 且无唯一 close-capture/frozen identity 可归组",
        alert_required=True,
        result_domain=("no_request", "candidate_conflict"),
    ),
    # ── close barrier ──────────────────────────────────────────────────
    _M(
        "workpaper_sync_close_capture_total", _C, _ROOM, "13.7",
        "close-capture 提升次数。exactly-one 的观测面：同 generation >1 即违规",
        alert_required=True,
        result_domain=("promoted", "cache_hit"),
    ),
    _M(
        "workpaper_sync_close_leader_authorization_stale_total", _C, _ROOM, "13.7",
        "leader promotion 前失去资格 ⇒ 记 `authorization_stale` 并选 successor。"
        "**有 successor** 的分支是正常运行态，不是 error",
        result_domain=("successor_selected", "leader_promoted_then_stale"),
    ),
    _M(
        "workpaper_sync_close_leader_recovery_required_total", _C, _ROOM, "13.9",
        "**无**合法 successor ⇒ generation supersede + `recovery_required` 显式终态。"
        "runbook 是「让重新授权的用户从新 generation 恢复」，与重试类 error 无关",
        alert_required=True,
        result_domain=("no_successor",),
    ),
    # ── permission / fence ─────────────────────────────────────────────
    _M(
        "workpaper_sync_permission_fence_invalidated_total", _C, _ROOM, "13.9",
        "participant 撤销/过期或 write fence 提升导致 outstanding request 作废",
        alert_required=True,
        result_domain=("revoked", "expired", "fence_advanced", "generation_rotated"),
    ),
    # ── definition / candidate ─────────────────────────────────────────
    _M(
        "workpaper_sync_bundle_candidate_finalize_total", _C, _PLAT, "13.9",
        "representation upgrade candidate → immutable representation 的 finalize。"
        "`rejected` 说明 approved contract/bundle 还没成形，此时 pointer 必须留在旧 "
        "representation（AC 6.18），积压需要人介入",
        alert_required=True,
        result_domain=("finalized", "awaiting_contract", "rejected"),
    ),
    _M(
        "workpaper_sync_candidate_exposure_total", _C, _PLAT, "13.9",
        "candidate 被 resolver/room/current pointer/evidence 误读（应恒为 0）",
        alert_required=True,
        result_domain=("resolver", "room", "current_pointer", "evidence"),
    ),
    _M(
        "workpaper_sync_definition_drift_total", _C, _PLAT, "13.9",
        "template/instrumentation/contract/bundle digest 漂移 ⇒ fail closed",
        alert_required=True,
        result_domain=("template", "instrumentation", "contract", "bundle", "authority_model"),
    ),
    # ── 平台级后台 ─────────────────────────────────────────────────────
    _M(
        "workpaper_sync_outbox_backlog", _G, _PLAT, "13.9",
        "outbox pending/failed 深度（Property 54 的运维面）",
        alert_required=True,
    ),
    _M(
        "workpaper_sync_orphan_backlog", _G, _PLAT, "13.9",
        "orphan/retention 待处理量；不确定即保留会让它单调涨",
        alert_required=True,
    ),
    _M(
        "workpaper_sync_retention_deleted_total", _C, _PLAT, "13.7",
        "retention 逐对象删除结果（dry-run 与 apply 分开记）",
        result_domain=("deleted", "retained", "legal_hold", "uncertain"),
    ),
    _M(
        "workpaper_sync_windows_file_in_use_total", _C, _PLAT, "13.9",
        "`os.replace` 被占用（Windows 部署的特有失败）",
        alert_required=True,
        result_domain=("staging", "publish", "delete"),
    ),
    _M(
        "workpaper_sync_oo_service_unavailable_total", _C, _ROOM, "13.9",
        "Command Service / DocServer 不可达",
        alert_required=True,
        result_domain=("connect_error", "timeout", "http_5xx", "invalid_response"),
    ),
    _M(
        "workpaper_sync_callback_missing_total", _C, _ROOM, "13.9",
        "forcesave accepted 之后 callback 未在窗口内到达",
        alert_required=True,
        result_domain=("timeout",),
    ),
    # ── 兜底 error（**受限**）─────────────────────────────────────────
    _M(
        "workpaper_sync_error_total", _C, _OP, "13.7",
        "未分型的失败。:data:`FORBIDDEN_GENERIC_ERROR_OUTCOMES` 里的终态**禁止**走这里",
        result_domain=("pre_durable", "validation", "unknown"),
    ),
)

METRICS_BY_NAME: Final[Mapping[str, MetricDefinition]] = {m.name: m for m in METRIC_CATALOG}

#: 🔴 禁止压成 `workpaper_sync_error_total` 的终态 → 应当使用的专用指标。
#:
#: 这三条正是 Task 29 明文点名的；另外两条（refresh_required / post-durable 失败）也在
#: 这里，因为它们同样有独立 runbook，而且历史上最容易被顺手记成 error。
FORBIDDEN_GENERIC_ERROR_OUTCOMES: Final[Mapping[str, str]] = {
    "same_application_sequence_fold": "workpaper_sync_application_sequence_fold_total",
    "cross_participant_idempotency_conflict": (
        "workpaper_sync_forcesave_fingerprint_conflict_total"
    ),
    "close_leader_no_successor_recovery_required": (
        "workpaper_sync_close_leader_recovery_required_total"
    ),
    "refresh_required": "workpaper_sync_refresh_required_total",
    "post_durable_failure": "workpaper_sync_post_durable_failure_total",
}


@dataclass(frozen=True)
class MetricSample:
    """一次记数。`result` 与 `landed` 都不可省。"""

    metric: str
    result: str | None
    landed: bool
    value: float
    labels: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "result": self.result,
            "landed": self.landed,
            "value": self.value,
            "labels": dict(self.labels),
        }


#: 进程内保留的最近样本数。
#:
#: **有界**是必须的：生产单例若用无界 list，一个长跑进程会把每次 forcesave 的样本一直
#: 攒着（6000 会话 × 每秒 20 applications 的容量门下几小时就是几百万条）。告警评估只需要
#: 最近一个窗口，超过的样本对判据没有价值。
SAMPLE_BUFFER_SIZE: Final[int] = 20000


class SyncMetrics:
    """指标记录器。

    刻意**不**直连 Prometheus client：本 spec 的判据是「指标存在、维度齐、终态不被压
    平」，而不是「用了哪个 exporter」。`samples` 是进程内可断言的记录面，生产可以再
    接 exporter；接不上时也不会静默丢掉判据（Task 16 的 outbox 同思路）。
    """

    def __init__(
        self,
        *,
        catalog: Mapping[str, MetricDefinition] | None = None,
        buffer_size: int = SAMPLE_BUFFER_SIZE,
    ) -> None:
        self._catalog = dict(catalog or METRICS_BY_NAME)
        self._samples: deque[MetricSample] = deque(maxlen=int(buffer_size))

    @property
    def samples(self) -> tuple[MetricSample, ...]:
        return tuple(self._samples)

    # ------------------------------------------------------------------
    # 归因校验
    # ------------------------------------------------------------------

    def _definition(self, metric: str) -> MetricDefinition:
        definition = self._catalog.get(metric)
        if definition is None:
            raise UnknownMetricError(
                f"指标 {metric!r} 不在目录里 —— 新指标必须先登记 METRIC_CATALOG"
                "（否则告警规则会引用一个永不 emit 的名字）"
            )
        return definition

    def _validate_labels(
        self, definition: MetricDefinition, labels: Mapping[str, Any]
    ) -> dict[str, Any]:
        known = {dim.value for dim in AttributionDim}
        unknown = sorted(set(labels) - known)
        if unknown:
            raise MetricAttributionError(
                f"{definition.name}: 未登记的维度 {unknown} —— 维度名只能取 "
                f"AttributionDim（否则同一件事在两处用两个标签名，无法聚合）"
            )
        missing = sorted(
            dim.value for dim in definition.required_dims if labels.get(dim.value) is None
        )
        if missing:
            raise MetricAttributionError(
                f"{definition.name}（{definition.attribution.value}）缺归因维度 {missing} "
                "—— Requirement 13.7 要求同一指标可按 room/generation/requested+canonical "
                "operation/application 与 participant 归因"
            )
        forbidden = FORBIDDEN_DIMS.get(definition.attribution, frozenset())
        present_forbidden = sorted(
            dim.value for dim in forbidden if labels.get(dim.value) is not None
        )
        if present_forbidden:
            raise MetricAttributionError(
                f"{definition.name}（{definition.attribution.value}）不得带维度 "
                f"{present_forbidden} —— 聚合 callback 事件是 room/generation 级服务事件，"
                "把 route participant 当作者是 AC 5.1/10.9 明文禁止的归因"
            )
        return {key: value for key, value in labels.items() if value is not None}

    def _validate_result(self, definition: MetricDefinition, result: str | None) -> None:
        if not definition.result_domain:
            if result is not None:
                raise MetricAttributionError(
                    f"{definition.name} 未声明 result_domain，却传了 result={result!r}"
                )
            return
        if result is None:
            raise MetricAttributionError(
                f"{definition.name} 声明了 result_domain={list(definition.result_domain)}，"
                "result 不得为空 —— 「没抛异常就算成功」正是 Task 22/26 刻意不抛之后最容易"
                "犯的错"
            )
        if result not in definition.result_domain:
            raise MetricAttributionError(
                f"{definition.name}: result={result!r} 不在封闭域 "
                f"{list(definition.result_domain)}"
            )

    # ------------------------------------------------------------------
    # 记数
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        metric: str,
        *,
        result: str | None,
        landed: bool,
        value: float = 1.0,
        **labels: Any,
    ) -> MetricSample:
        """记一次带显式结果的观测。

        `result` 与 `landed` **没有默认值**：调用方必须从 outcome 里读出来。
        `landed` 表示「incoming 是否已耐久」——它决定失败该记 pre-durable 还是
        post-durable，两者 runbook 不同（AC 5.7 vs 5.8）。
        """
        definition = self._definition(metric)
        self._validate_result(definition, result)
        checked = self._validate_labels(definition, labels)
        sample = MetricSample(
            metric=metric, result=result, landed=bool(landed), value=float(value),
            labels=checked,
        )
        self._samples.append(sample)
        return sample

    def observe(self, metric: str, *, seconds: float, **labels: Any) -> MetricSample:
        """直方图观测。耗时永远是「已发生的事实」，故 `landed=True`。"""
        definition = self._definition(metric)
        if definition.kind is not MetricKind.histogram:
            raise MetricAttributionError(
                f"{metric} 的 kind 是 {definition.kind.value}，observe() 只接受 histogram"
            )
        return self.record_outcome(metric, result=None, landed=True, value=seconds, **labels)

    def set_gauge(self, metric: str, *, value: float, **labels: Any) -> MetricSample:
        definition = self._definition(metric)
        if definition.kind is not MetricKind.gauge:
            raise MetricAttributionError(
                f"{metric} 的 kind 是 {definition.kind.value}，set_gauge() 只接受 gauge"
            )
        return self.record_outcome(metric, result=None, landed=True, value=value, **labels)

    def record_error(
        self,
        *,
        outcome: str,
        landed: bool,
        result: str,
        **labels: Any,
    ) -> MetricSample:
        """兜底 error 记数。命中 :data:`FORBIDDEN_GENERIC_ERROR_OUTCOMES` 即拒绝。

        `outcome` 是**语义终态名**（不是 error_code）：它让「这件事到底是什么」可判定。
        """
        dedicated = FORBIDDEN_GENERIC_ERROR_OUTCOMES.get(outcome)
        if dedicated is not None:
            raise MetricAttributionError(
                f"终态 {outcome!r} 不得压成 workpaper_sync_error_total —— 它有专用指标 "
                f"{dedicated}；压平会让值班按错误 runbook 处理一个正常/需专门恢复的状态"
                "（Task 29 明文禁止）"
            )
        return self.record_outcome(
            "workpaper_sync_error_total", result=result, landed=landed, **labels
        )

    # ------------------------------------------------------------------
    # 断言面（供守卫与运维视图）
    # ------------------------------------------------------------------

    def by_metric(self, metric: str) -> tuple[MetricSample, ...]:
        return tuple(s for s in self.samples if s.metric == metric)

    def total(self, metric: str, **labels: Any) -> float:
        wanted = {k: v for k, v in labels.items() if v is not None}
        return sum(
            s.value
            for s in self.samples
            if s.metric == metric
            and all(str(s.labels.get(k)) == str(v) for k, v in wanted.items())
        )


def validate_catalog(
    catalog: tuple[MetricDefinition, ...] = METRIC_CATALOG,
) -> tuple[str, ...]:
    """目录自检，返回问题列表（空 = 合规）。守卫直接断言它为空。"""
    problems: list[str] = []
    seen: dict[str, int] = {}
    for definition in catalog:
        seen[definition.name] = seen.get(definition.name, 0) + 1
        if not definition.name.startswith("workpaper_sync_"):
            problems.append(f"{definition.name}: 名字必须以 workpaper_sync_ 开头")
        if definition.kind is MetricKind.counter and not definition.name.endswith("_total"):
            problems.append(f"{definition.name}: counter 必须以 _total 结尾")
        if definition.kind is MetricKind.histogram and not definition.name.endswith("_seconds"):
            problems.append(f"{definition.name}: histogram 必须以 _seconds 结尾")
        if definition.kind is not MetricKind.counter and definition.result_domain:
            problems.append(
                f"{definition.name}: 只有 counter 允许 result_domain"
            )
        if len(definition.why) < 8:
            problems.append(f"{definition.name}: why 过短")
        if not definition.requirement:
            problems.append(f"{definition.name}: 缺 requirement")
    for name, count in sorted(seen.items()):
        if count > 1:
            problems.append(f"{name}: 目录里重复 {count} 次")
    for outcome, metric in FORBIDDEN_GENERIC_ERROR_OUTCOMES.items():
        if metric not in seen:
            problems.append(
                f"FORBIDDEN_GENERIC_ERROR_OUTCOMES[{outcome}] 指向不存在的指标 {metric}"
            )
    return tuple(problems)


#: 生产单例。生产调用一律走它，测试各自构造独立实例（避免样本互相串）。
sync_metrics = SyncMetrics()


__all__ = [
    "SAMPLE_BUFFER_SIZE",
    "AttributionClass",
    "AttributionDim",
    "CLASS_REQUIRED_DIMS",
    "FORBIDDEN_GENERIC_ERROR_OUTCOMES",
    "METRICS_BY_NAME",
    "METRIC_CATALOG",
    "MetricAttributionError",
    "MetricDefinition",
    "MetricKind",
    "MetricSample",
    "MetricsError",
    "FORBIDDEN_DIMS",
    "OPERATION_ATTRIBUTION",
    "PLATFORM_ATTRIBUTION",
    "ROOM_ATTRIBUTION",
    "ROUTE_ATTRIBUTION",
    "SyncMetrics",
    "UnknownMetricError",
    "sync_metrics",
    "validate_catalog",
]
