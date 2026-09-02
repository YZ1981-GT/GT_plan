# -*- coding: utf-8 -*-
"""append-only timeline 查询：四条独立 event 流的统一投影 + 一致性 oracle。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 29
Requirements: 5.10, 13.5, 13.6, 13.8, 13.10
Properties: **P68**（operation/recovery timeline 完整单调）

═══ 四条流，刻意不合表 ═══

V151 里有四张 append-only event 表，各自有独立 parent 与独立 `sequence_no`：

| 表 | parent | 为什么不能合成一张 |
|---|---|---|
| `working_paper_sync_operation_event` | operation | 用户轮询面；shell 阶段 `application_id` 为 NULL |
| `working_paper_content_application_event` | application | `sequence_folded` 只属于 application |
| `working_paper_callback_recovery_case_event` | recovery case | **claim 前根本没有 operation** |
| `working_paper_oo_close_intent_event` | close intent | eligibility epoch / leader 更替 |

AC 13.5 的后半句是「recovery case 在 claim 前不得借 operation timeline 伪造 operation」。
合成一张表最省事，但那样 recovery case 的 event 就必须挂一个 `operation_id` —— 于是
「claim 前零 operation」这条不变式在**存储层**就无法表达。本模块因此只在**读侧**做
归并投影，四张表各自保持独立 parent。

:meth:`SyncTimelineService.recovery_case_timeline` 的返回结构里没有 operation 字段，
:attr:`RecoveryTimeline.operation_id` 只在 claim 之后由 case 行自己给出；claim 前它是
`None` 且 `operation_events` 为空元组 —— 这是 P68「claim 前 timeline 不得关联
operation/application」的直接投影。

═══ current state 只是 timeline 的投影 ═══

AC 13.5 / P68：「先写 append-only transition event，再更新 current state projection」。
写侧由 Task 10 的 `repository.append_*_event` 保证；**读侧**需要一个能发现「有人直接改
了 current state」或「中间 event 被删」的判据，这就是
:meth:`SyncTimelineService.check_projection` ：

1. 最后一条 event 的 `to_state` 必须等于当前行的 `state`；
2. `sequence_no` 必须从 1 起严格连续（删中间一条即断号）；
3. 相邻 event 的 `from_state` 必须等于前一条的 `to_state`（伪造一条即断链）；
4. `occurred_at` 必须单调不减（服务端时钟，AC 13.10）。

四条各自返回独立的 :class:`ProjectionDefect` 码 —— 共用一个码会让靠后的检查在靠前的
检查失效时被遮蔽，那条变异就永久 GREEN（本 spec 已三次踩到）。

═══ 时间只认服务端 ═══

AC 13.10：「operation timeline 的关键时间 SHALL 来自后端数据库/服务端时钟；浏览器
trace 只能作为客户端证据」。因此：

* 排序键恒为 `(sequence_no, occurred_at)`，且 `occurred_at` 直接取自 DB 列；
* 投影结果里的客户端证据只能出现在 `client_` 前缀键下（由 `RedactionPolicy`
  的 allowlist 规则放行），并且 :meth:`SyncTimelineService.merged_timeline` **不**用它排序；
* :func:`assert_server_clock_only` 拒绝任何以 `client_` 开头的排序键。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Final, Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import (
    WorkpaperCallbackDelivery,
    WorkpaperCallbackRecoveryCase,
    WorkpaperCallbackRecoveryCaseEvent,
    WorkpaperContentApplication,
    WorkpaperContentApplicationEvent,
    WorkpaperOoCloseIntent,
    WorkpaperOoCloseIntentEvent,
    WorkpaperSyncOperation,
    WorkpaperSyncOperationEvent,
)
from app.services.workpaper_sync.models import SyncDomainError
from app.services.workpaper_sync.redaction import RedactionPolicy, load_redaction_policy

#: 允许的排序键。**只有服务端列**。
SERVER_ORDER_KEYS: Final[tuple[str, ...]] = ("sequence_no", "occurred_at")

#: 单次查询的硬上限（防止一次 timeline 查询把整个 room 的历史拉进内存）。
MAX_TIMELINE_ROWS: Final[int] = 2000


class TimelineError(SyncDomainError):
    error_code = "sync_timeline_invalid"


class TimelineUsageError(TimelineError):
    """查询协议违规（缺 scope、非法排序键、超上限）。"""

    error_code = "sync_timeline_usage_invalid"


class TimelineProjectionError(TimelineError):
    """current state 与 append-only timeline 分叉（P68 的打红点）。"""

    error_code = "sync_timeline_projection_diverged"


class TimelineStream(str, Enum):
    """四条独立流。值同时用作投影结果里的 `stream` 字段。"""

    operation = "operation"
    application = "application"
    recovery_case = "recovery_case"
    close_intent = "close_intent"


class ProjectionDefect(str, Enum):
    """一致性缺陷分型。逐条独立，禁止合并。"""

    state_diverged = "state_diverged"
    sequence_gap = "sequence_gap"
    transition_chain_broken = "transition_chain_broken"
    clock_regressed = "clock_regressed"
    empty_timeline = "empty_timeline"


@dataclass(frozen=True)
class TimelineEvent:
    """一条脱敏后的 timeline 事件。"""

    stream: TimelineStream
    parent_id: uuid.UUID
    sequence_no: int
    occurred_at: datetime
    from_state: str | None
    to_state: str | None
    payload: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "stream": self.stream.value,
            "parent_id": str(self.parent_id),
            "sequence_no": self.sequence_no,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "from_state": self.from_state,
            "to_state": self.to_state,
            **dict(self.payload),
        }


@dataclass(frozen=True)
class ProjectionCheck:
    """:meth:`SyncTimelineService.check_projection` 的结果。"""

    stream: TimelineStream
    parent_id: uuid.UUID
    current_state: str | None
    last_event_state: str | None
    event_count: int
    defects: tuple[ProjectionDefect, ...] = ()

    @property
    def consistent(self) -> bool:
        return not self.defects

    def as_dict(self) -> dict[str, Any]:
        return {
            "stream": self.stream.value,
            "parent_id": str(self.parent_id),
            "current_state": self.current_state,
            "last_event_state": self.last_event_state,
            "event_count": self.event_count,
            "defects": [d.value for d in self.defects],
            "consistent": self.consistent,
        }


@dataclass(frozen=True)
class OperationTimeline:
    """一个 operation 的完整 timeline（含 canonical 跟随信息）。"""

    requested_operation_id: uuid.UUID
    canonical_operation_id: uuid.UUID
    followed_duplicate: bool
    #: shell 阶段恒为 `None` —— 这是**正确**形态，投影不得写成 0/""（AC 5.5）。
    application_id: uuid.UUID | None
    operation_events: tuple[TimelineEvent, ...] = ()
    application_events: tuple[TimelineEvent, ...] = ()
    checks: tuple[ProjectionCheck, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_operation_id": str(self.requested_operation_id),
            "canonical_operation_id": str(self.canonical_operation_id),
            "followed_duplicate": self.followed_duplicate,
            "application_id": (
                None if self.application_id is None else str(self.application_id)
            ),
            "operation_events": [e.as_dict() for e in self.operation_events],
            "application_events": [e.as_dict() for e in self.application_events],
            "checks": [c.as_dict() for c in self.checks],
            "server_clock_source": "database",
        }


@dataclass(frozen=True)
class RecoveryTimeline:
    """一个 recovery case 的 timeline。

    🔴 结构上没有 `operation_events`：claim 之前不存在 operation，而一个「顺手挂上
    operation 事件」的投影会让 P68 的「claim 前不得关联 operation/application」在读侧
    重新被违反。claim 之后的 operation timeline 用 :attr:`claimed_operation_id` 单独查。
    """

    case_id: uuid.UUID
    state: str
    reason: str
    claimed_operation_id: uuid.UUID | None
    claimed_application_id: uuid.UUID | None
    recovery_request_id: uuid.UUID | None
    events: tuple[TimelineEvent, ...] = ()
    checks: tuple[ProjectionCheck, ...] = ()

    @property
    def has_three_entities(self) -> bool:
        """claim 成功后三实体齐备；download-only / unclaimed 必须为 False。"""
        return (
            self.claimed_operation_id is not None
            and self.claimed_application_id is not None
            and self.recovery_request_id is not None
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": str(self.case_id),
            "state": self.state,
            "reason": self.reason,
            "claimed_operation_id": (
                None if self.claimed_operation_id is None else str(self.claimed_operation_id)
            ),
            "claimed_application_id": (
                None
                if self.claimed_application_id is None
                else str(self.claimed_application_id)
            ),
            "recovery_request_id": (
                None if self.recovery_request_id is None else str(self.recovery_request_id)
            ),
            "has_three_entities": self.has_three_entities,
            "events": [e.as_dict() for e in self.events],
            "checks": [c.as_dict() for c in self.checks],
            "server_clock_source": "database",
        }


@dataclass(frozen=True)
class TimelineQuery:
    """查询条件。**至少一个**定位维度必填 —— 无条件全表扫不是查询。

    这些维度直接对应 AC 13.6 的「按 wp/room/participant/operation/recovery case/
    application/correlation id 查询」，外加 AC 5.10 的 request 与 sequence。
    """

    wp_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    request_id: uuid.UUID | None = None
    participant_id: uuid.UUID | None = None
    operation_id: uuid.UUID | None = None
    recovery_case_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None
    min_sequence_no: int | None = None
    streams: tuple[TimelineStream, ...] = field(
        default_factory=lambda: tuple(TimelineStream)
    )
    limit: int = 200

    #: 供守卫核对「AC 13.6 的维度是否一个都没少」。
    #:
    #: 🔴 必须是 `ClassVar`：`Final[...]` 在 dataclass 里**会**变成一个带默认值的实例
    #: 字段（PEP 591 只影响类型检查，不影响 `@dataclass` 的字段收集）。实测
    #: `dataclasses.fields(TimelineQuery)` 里确实多出 `LOCATORS` —— 于是每个查询对象
    #: 都带一份可被调用方覆盖的「维度清单」，`validate()` 就能被 `TimelineQuery(
    #: LOCATORS=())` 绕过。
    LOCATORS: ClassVar[tuple[str, ...]] = (
        "wp_id",
        "room_id",
        "request_id",
        "participant_id",
        "operation_id",
        "recovery_case_id",
        "application_id",
        "correlation_id",
    )

    def locators(self) -> dict[str, uuid.UUID]:
        found: dict[str, uuid.UUID] = {}
        for name in self.LOCATORS:
            value = getattr(self, name)
            if value is not None:
                found[name] = value
        return found

    def validate(self) -> None:
        if not self.locators():
            raise TimelineUsageError(
                f"timeline 查询至少需要一个定位维度 {list(self.LOCATORS)} —— "
                "无条件查询会把整库 event 拉出来，且绕开 authorization-before-resource"
            )
        if self.limit <= 0 or self.limit > MAX_TIMELINE_ROWS:
            raise TimelineUsageError(
                f"limit 必须在 1..{MAX_TIMELINE_ROWS}，实得 {self.limit}"
            )
        if not self.streams:
            raise TimelineUsageError("streams 不得为空")
        if self.min_sequence_no is not None and self.min_sequence_no < 1:
            raise TimelineUsageError("min_sequence_no 从 1 起（sequence_no 不存在 0）")


def assert_server_clock_only(order_keys: Sequence[str]) -> None:
    """排序键必须全部来自服务端列（AC 13.10）。

    单独成函数而不是内联 `if`：它同时被 :meth:`SyncTimelineService.merged_timeline`
    与守卫调用，于是「换成按 client 时间排序」这件事只有一个可变异落点。
    """
    illegal = [key for key in order_keys if key not in SERVER_ORDER_KEYS]
    if illegal:
        raise TimelineUsageError(
            f"排序键 {illegal} 不是服务端时钟列（只允许 {list(SERVER_ORDER_KEYS)}）—— "
            "浏览器 trace 只能作为客户端证据，不得伪造服务端 callback 顺序"
        )


class SyncTimelineService:
    """append-only timeline 的唯一读侧入口。

    **不做授权**：授权在 Task 28 的 `SyncEndpointGuard`（AC 10.6 的固定阶段链要求
    「只查 scope index → visibility → action → 业务 resource」）。本服务是「业务
    resource」那一步，因此它**必须**被 guard 包着调用；`declared_*` 参数用于把 guard
    已确认的 scope 与实际行再比一次（横向 id 的第二道门）。
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        policy: RedactionPolicy | None = None,
    ) -> None:
        self._session = session
        self._policy = policy or load_redaction_policy()

    @property
    def policy(self) -> RedactionPolicy:
        return self._policy

    # ------------------------------------------------------------------
    # 投影
    # ------------------------------------------------------------------

    def _project_row(self, stream: TimelineStream, row: Any, parent_id: uuid.UUID) -> TimelineEvent:
        raw: dict[str, Any] = {
            column.name: getattr(row, column.name, None)
            for column in row.__table__.columns
        }
        # `id` 是 bigint 代理键，不进投影：`(stream, parent_id, sequence_no)` 才是业务身份。
        raw.pop("id", None)
        projected, report = self._policy.redact(raw)
        self._policy.assert_no_leak(projected)
        payload = dict(projected)
        payload["redaction_policy_version"] = self._policy.policy_version
        if not report.leaked_nothing:
            payload["redaction_report"] = report.as_dict()
        occurred = getattr(row, "occurred_at", None)
        return TimelineEvent(
            stream=stream,
            parent_id=parent_id,
            sequence_no=int(getattr(row, "sequence_no")),
            occurred_at=occurred,
            from_state=_opt_str(getattr(row, "from_state", None)),
            to_state=_opt_str(getattr(row, "to_state", None)),
            payload=payload,
        )

    # ------------------------------------------------------------------
    # 一致性 oracle（Property 68）
    # ------------------------------------------------------------------

    def check_projection(
        self,
        *,
        stream: TimelineStream,
        parent_id: uuid.UUID,
        current_state: str | None,
        events: Sequence[TimelineEvent],
        require_events: bool = True,
    ) -> ProjectionCheck:
        """四条独立判据，各自一个缺陷码。"""
        defects: list[ProjectionDefect] = []
        ordered = sorted(events, key=lambda e: e.sequence_no)

        if not ordered:
            if require_events:
                defects.append(ProjectionDefect.empty_timeline)
            return ProjectionCheck(
                stream=stream, parent_id=parent_id, current_state=current_state,
                last_event_state=None, event_count=0, defects=tuple(defects),
            )

        # ① 号段：对**全部**事件连续。删中间一条即断号，与状态无关。
        expected = [index + 1 for index in range(len(ordered))]
        if [e.sequence_no for e in ordered] != expected:
            defects.append(ProjectionDefect.sequence_gap)

        # application 流的 `sequence_folded` 事件不带状态（`to_state` 为 NULL）：它是序号
        # 折叠审计，不是状态转换。链式与投影两条判据都只看**带状态**的事件，否则一次
        # 合法 fold 会同时误报 transition_chain_broken 与 state_diverged。
        stateful = [e for e in ordered if e.to_state is not None]

        # ② 转换链：相邻带状态事件的 from/to 必须接得上。伪造一条即断链。
        for previous, following in zip(stateful, stateful[1:]):
            if following.from_state is not None and following.from_state != previous.to_state:
                defects.append(ProjectionDefect.transition_chain_broken)
                break

        # ③ 服务端时钟单调（AC 13.10）：对全部事件成立，含无状态的 fold。
        for previous, following in zip(ordered, ordered[1:]):
            if (
                previous.occurred_at is not None
                and following.occurred_at is not None
                and following.occurred_at < previous.occurred_at
            ):
                defects.append(ProjectionDefect.clock_regressed)
                break

        # ④ current state 只是投影：必须等于最后一条带状态事件的 to_state。
        last_state = stateful[-1].to_state if stateful else None
        if current_state is not None and last_state is not None and last_state != current_state:
            defects.append(ProjectionDefect.state_diverged)

        return ProjectionCheck(
            stream=stream, parent_id=parent_id, current_state=current_state,
            last_event_state=last_state, event_count=len(ordered), defects=tuple(defects),
        )

    def assert_projection(self, check: ProjectionCheck) -> None:
        if not check.consistent:
            raise TimelineProjectionError(
                f"{check.stream.value} {check.parent_id} 的 current state 与 append-only "
                f"timeline 分叉: {[d.value for d in check.defects]} "
                f"(current={check.current_state!r} last_event={check.last_event_state!r})"
            )

    # ------------------------------------------------------------------
    # operation timeline
    # ------------------------------------------------------------------

    async def operation_timeline(
        self,
        *,
        operation_id: uuid.UUID,
        declared_project_id: uuid.UUID,
        declared_wp_id: uuid.UUID,
        declared_entry_id: str,
        canonical_operation_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> OperationTimeline:
        """requested → canonical 的 timeline。

        `canonical_operation_id` 由调用方（Task 23 的 `read_operation`）给出：canonical
        化本身带 direct-primary invariant 校验，本服务**不**重做那套判定，只投影。
        传 `None` 表示 requested 就是 canonical。
        """
        requested = await self._load_operation(operation_id)
        _assert_scope(
            requested, declared_project_id, declared_wp_id, declared_entry_id,
            label="operation",
        )
        canonical = requested
        if canonical_operation_id is not None and canonical_operation_id != requested.id:
            canonical = await self._load_operation(canonical_operation_id)
            _assert_scope(
                canonical, declared_project_id, declared_wp_id, declared_entry_id,
                label="canonical operation",
            )

        op_rows = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperSyncOperationEvent)
                    .where(WorkpaperSyncOperationEvent.operation_id == canonical.id)
                    .order_by(WorkpaperSyncOperationEvent.sequence_no)
                    .limit(min(limit, MAX_TIMELINE_ROWS))
                )
            ).scalars()
        )
        op_events = tuple(
            self._project_row(TimelineStream.operation, row, canonical.id) for row in op_rows
        )
        checks = [
            self.check_projection(
                stream=TimelineStream.operation,
                parent_id=canonical.id,
                current_state=_opt_str(canonical.state),
                events=op_events,
            )
        ]

        app_events: tuple[TimelineEvent, ...] = ()
        if canonical.application_id is not None:
            app_rows = list(
                (
                    await self._session.execute(
                        sa.select(WorkpaperContentApplicationEvent)
                        .where(
                            WorkpaperContentApplicationEvent.application_id
                            == canonical.application_id
                        )
                        .order_by(WorkpaperContentApplicationEvent.sequence_no)
                        .limit(min(limit, MAX_TIMELINE_ROWS))
                    )
                ).scalars()
            )
            app_events = tuple(
                self._project_row(
                    TimelineStream.application, row, canonical.application_id
                )
                for row in app_rows
            )
            application = (
                await self._session.execute(
                    sa.select(WorkpaperContentApplication).where(
                        WorkpaperContentApplication.id == canonical.application_id
                    )
                )
            ).scalar_one_or_none()
            checks.append(
                self.check_projection(
                    stream=TimelineStream.application,
                    parent_id=canonical.application_id,
                    current_state=(
                        None if application is None else _opt_str(application.state)
                    ),
                    events=app_events,
                )
            )
        return OperationTimeline(
            requested_operation_id=requested.id,
            canonical_operation_id=canonical.id,
            followed_duplicate=canonical.id != requested.id,
            application_id=canonical.application_id,
            operation_events=op_events,
            application_events=app_events,
            checks=tuple(checks),
        )

    # ------------------------------------------------------------------
    # recovery case timeline
    # ------------------------------------------------------------------

    async def recovery_case_timeline(
        self,
        *,
        case_id: uuid.UUID,
        declared_project_id: uuid.UUID,
        declared_wp_id: uuid.UUID,
        declared_entry_id: str,
        limit: int = 200,
    ) -> RecoveryTimeline:
        """recovery case 的**独立** timeline。claim 前三实体恒空。"""
        case = (
            await self._session.execute(
                sa.select(WorkpaperCallbackRecoveryCase).where(
                    WorkpaperCallbackRecoveryCase.id == case_id
                )
            )
        ).scalar_one_or_none()
        if case is None:
            raise TimelineUsageError(f"recovery case 不存在: {case_id}")
        _assert_scope(
            case, declared_project_id, declared_wp_id, declared_entry_id,
            label="recovery case",
        )
        rows = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperCallbackRecoveryCaseEvent)
                    .where(WorkpaperCallbackRecoveryCaseEvent.case_id == case_id)
                    .order_by(WorkpaperCallbackRecoveryCaseEvent.sequence_no)
                    .limit(min(limit, MAX_TIMELINE_ROWS))
                )
            ).scalars()
        )
        events = tuple(
            self._project_row(TimelineStream.recovery_case, row, case_id) for row in rows
        )
        check = self.check_projection(
            stream=TimelineStream.recovery_case,
            parent_id=case_id,
            current_state=_opt_str(case.state),
            events=events,
        )
        return RecoveryTimeline(
            case_id=case_id,
            state=str(case.state),
            reason=str(case.reason),
            claimed_operation_id=case.operation_id,
            claimed_application_id=case.application_id,
            recovery_request_id=case.recovery_request_id,
            events=events,
            checks=(check,),
        )

    # ------------------------------------------------------------------
    # 归并查询（AC 13.6）
    # ------------------------------------------------------------------

    async def merged_timeline(self, query: TimelineQuery) -> tuple[TimelineEvent, ...]:
        """按任一定位维度归并四条流，按服务端 `(sequence_no, occurred_at)` 排序。"""
        query.validate()
        assert_server_clock_only(SERVER_ORDER_KEYS)
        collected: list[TimelineEvent] = []

        if TimelineStream.operation in query.streams:
            collected.extend(await self._operation_events_for(query))
        if TimelineStream.application in query.streams:
            collected.extend(await self._application_events_for(query))
        if TimelineStream.recovery_case in query.streams:
            collected.extend(await self._recovery_events_for(query))
        if TimelineStream.close_intent in query.streams:
            collected.extend(await self._close_intent_events_for(query))

        if query.min_sequence_no is not None:
            collected = [e for e in collected if e.sequence_no >= query.min_sequence_no]
        collected.sort(key=lambda e: (e.sequence_no, e.occurred_at or _EPOCH, e.stream.value))
        return tuple(collected[: query.limit])

    async def _operation_ids_for(self, query: TimelineQuery) -> list[uuid.UUID]:
        stmt = sa.select(WorkpaperSyncOperation.id)
        conditions = []
        if query.operation_id is not None:
            conditions.append(WorkpaperSyncOperation.id == query.operation_id)
        if query.wp_id is not None:
            conditions.append(WorkpaperSyncOperation.wp_id == query.wp_id)
        if query.room_id is not None:
            conditions.append(WorkpaperSyncOperation.room_id == query.room_id)
        if query.request_id is not None:
            conditions.append(
                WorkpaperSyncOperation.forcesave_request_id == query.request_id
            )
        if query.participant_id is not None:
            conditions.append(
                WorkpaperSyncOperation.initiated_by_participant_id == query.participant_id
            )
        if query.application_id is not None:
            conditions.append(WorkpaperSyncOperation.application_id == query.application_id)
        if not conditions:
            return []
        rows = (await self._session.execute(stmt.where(sa.and_(*conditions)))).scalars()
        return list(rows)

    async def _operation_events_for(self, query: TimelineQuery) -> list[TimelineEvent]:
        if query.correlation_id is not None:
            rows = list(
                (
                    await self._session.execute(
                        sa.select(WorkpaperSyncOperationEvent)
                        .where(
                            WorkpaperSyncOperationEvent.correlation_id == query.correlation_id
                        )
                        .order_by(WorkpaperSyncOperationEvent.sequence_no)
                        .limit(min(query.limit, MAX_TIMELINE_ROWS))
                    )
                ).scalars()
            )
            return [
                self._project_row(TimelineStream.operation, row, row.operation_id)
                for row in rows
            ]
        operation_ids = await self._operation_ids_for(query)
        if not operation_ids:
            return []
        rows = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperSyncOperationEvent)
                    .where(WorkpaperSyncOperationEvent.operation_id.in_(operation_ids))
                    .order_by(WorkpaperSyncOperationEvent.sequence_no)
                    .limit(min(query.limit, MAX_TIMELINE_ROWS))
                )
            ).scalars()
        )
        return [
            self._project_row(TimelineStream.operation, row, row.operation_id) for row in rows
        ]

    async def _application_events_for(self, query: TimelineQuery) -> list[TimelineEvent]:
        conditions = []
        if query.application_id is not None:
            conditions.append(WorkpaperContentApplication.id == query.application_id)
        if query.wp_id is not None:
            conditions.append(WorkpaperContentApplication.wp_id == query.wp_id)
        if query.room_id is not None:
            conditions.append(WorkpaperContentApplication.room_id == query.room_id)
        if query.request_id is not None:
            conditions.append(
                WorkpaperContentApplication.origin_request_id == query.request_id
            )
        if not conditions:
            return []
        application_ids = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperContentApplication.id).where(sa.and_(*conditions))
                )
            ).scalars()
        )
        if not application_ids:
            return []
        rows = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperContentApplicationEvent)
                    .where(
                        WorkpaperContentApplicationEvent.application_id.in_(application_ids)
                    )
                    .order_by(WorkpaperContentApplicationEvent.sequence_no)
                    .limit(min(query.limit, MAX_TIMELINE_ROWS))
                )
            ).scalars()
        )
        return [
            self._project_row(TimelineStream.application, row, row.application_id)
            for row in rows
        ]

    async def _recovery_events_for(self, query: TimelineQuery) -> list[TimelineEvent]:
        conditions = []
        if query.recovery_case_id is not None:
            conditions.append(WorkpaperCallbackRecoveryCase.id == query.recovery_case_id)
        if query.wp_id is not None:
            conditions.append(WorkpaperCallbackRecoveryCase.wp_id == query.wp_id)
        if query.room_id is not None:
            conditions.append(WorkpaperCallbackRecoveryCase.room_id == query.room_id)
        if query.application_id is not None:
            conditions.append(
                WorkpaperCallbackRecoveryCase.application_id == query.application_id
            )
        if not conditions:
            return []
        case_ids = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperCallbackRecoveryCase.id).where(sa.and_(*conditions))
                )
            ).scalars()
        )
        if not case_ids:
            return []
        rows = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperCallbackRecoveryCaseEvent)
                    .where(WorkpaperCallbackRecoveryCaseEvent.case_id.in_(case_ids))
                    .order_by(WorkpaperCallbackRecoveryCaseEvent.sequence_no)
                    .limit(min(query.limit, MAX_TIMELINE_ROWS))
                )
            ).scalars()
        )
        return [
            self._project_row(TimelineStream.recovery_case, row, row.case_id) for row in rows
        ]

    async def _close_intent_events_for(self, query: TimelineQuery) -> list[TimelineEvent]:
        conditions = []
        if query.room_id is not None:
            conditions.append(WorkpaperOoCloseIntent.room_id == query.room_id)
        if query.participant_id is not None:
            conditions.append(WorkpaperOoCloseIntent.participant_id == query.participant_id)
        if query.request_id is not None:
            conditions.append(
                WorkpaperOoCloseIntent.promoted_request_id == query.request_id
            )
        if not conditions:
            return []
        intent_ids = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperOoCloseIntent.id).where(sa.and_(*conditions))
                )
            ).scalars()
        )
        if not intent_ids:
            return []
        rows = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperOoCloseIntentEvent)
                    .where(WorkpaperOoCloseIntentEvent.intent_id.in_(intent_ids))
                    .order_by(WorkpaperOoCloseIntentEvent.sequence_no)
                    .limit(min(query.limit, MAX_TIMELINE_ROWS))
                )
            ).scalars()
        )
        return [
            self._project_row(TimelineStream.close_intent, row, row.intent_id) for row in rows
        ]

    # ------------------------------------------------------------------
    # 归属核对（Requirement 5.4 的 delivery owner 约束在读侧的投影）
    # ------------------------------------------------------------------

    async def delivery_owner_summary(self, *, room_id: uuid.UUID) -> dict[str, int]:
        """按 `durable_at` 分桶统计 delivery 的归属形态。

        运维视图需要它回答「有没有 durable incoming 成了无主死路」。判据用
        `durable_at IS NULL` 而**不是** state 名单：AC 5.4 明文「归属约束只以 immutable
        `durable_at`/durable fact 判定，不得把泛化 `terminal` 当 durable」。
        """
        rows = list(
            (
                await self._session.execute(
                    sa.select(
                        WorkpaperCallbackDelivery.durable_at,
                        WorkpaperCallbackDelivery.application_id,
                        WorkpaperCallbackDelivery.callback_recovery_case_id,
                    ).where(WorkpaperCallbackDelivery.room_id == room_id)
                )
            ).all()
        )
        summary = {
            "pre_durable_unowned": 0,
            "durable_correlated": 0,
            "durable_recovery": 0,
            "durable_ownerless": 0,
            "dual_owner": 0,
        }
        for durable_at, application_id, recovery_case_id in rows:
            if application_id is not None and recovery_case_id is not None:
                summary["dual_owner"] += 1
                continue
            if durable_at is None:
                summary["pre_durable_unowned"] += 1
                continue
            if application_id is not None:
                summary["durable_correlated"] += 1
            elif recovery_case_id is not None:
                summary["durable_recovery"] += 1
            else:
                summary["durable_ownerless"] += 1
        return summary

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    async def _load_operation(self, operation_id: uuid.UUID) -> WorkpaperSyncOperation:
        row = (
            await self._session.execute(
                sa.select(WorkpaperSyncOperation).where(
                    WorkpaperSyncOperation.id == operation_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise TimelineUsageError(f"operation 不存在: {operation_id}")
        return row


#: 排序兜底值。**必须带 tzinfo**：`occurred_at` 是 timestamptz（aware），naive 与 aware
#: 混在同一个排序键元组里会抛 `TypeError: can't compare offset-naive and offset-aware`，
#: 于是「某条事件的 occurred_at 为 NULL」这种数据异常会表现为 500 而不是可读的判定。
_EPOCH: Final[datetime] = datetime.min.replace(tzinfo=timezone.utc)


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _assert_scope(
    row: Any,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    *,
    label: str,
) -> None:
    """行的归属必须与 guard 已确认的显式 scope 完全一致。

    这是横向 id 的**第二道**门：guard 查的是 scope index，这里比的是业务行本身。
    两者不一致意味着 scope index 与业务行不同步（AC 10.6 要求它们同事务创建/退役）。
    """
    if row.project_id != project_id or row.wp_id != wp_id or str(row.entry_id) != entry_id:
        raise TimelineUsageError(
            f"{label} 的归属与声明 scope 不符 —— scope index 与业务行不同步，"
            "或调用方越过 guard 直接传了别的 scope"
        )


__all__ = [
    "MAX_TIMELINE_ROWS",
    "SERVER_ORDER_KEYS",
    "OperationTimeline",
    "ProjectionCheck",
    "ProjectionDefect",
    "RecoveryTimeline",
    "SyncTimelineService",
    "TimelineError",
    "TimelineEvent",
    "TimelineProjectionError",
    "TimelineQuery",
    "TimelineStream",
    "TimelineUsageError",
    "assert_server_clock_only",
]
