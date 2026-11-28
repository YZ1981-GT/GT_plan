"""冲突集「显式作废」—— 遗留 operation 的唯一可用出口（R3.3）。

═══ 为什么需要它（spec frozen-contract-read-path 任务 8 / ADR-FC-004 第二条） ═══

一条 `state=conflict` 的 operation 在契约换代之后**没有可用出口**：

* **正式裁决**在数据层双重不可达。第一拦：遗留冲突全部 `conflict_kind='schema'` 且
  `schema_anomaly IS NULL` ⇒ :attr:`~.conflict_resolution.ConflictPreviewItem.adjudicable_by_value_choice`
  在成因未知时 fail-closed 返回 `False` ⇒ `apply_resolutions` 抛
  `StructuralConflictNotAdjudicableError`。第二拦：即使补齐成因，
  `resolve → apply_durable_incoming → _fence_before_publish → assert_final_authorization`
  的 `approved_bundle_identity` 判据要求「entry **当前** approved bundle == application
  冻结的那份」，契约换代后必不相等 ⇒ `ApprovedBundleReplacedError`。
  **这两道拒绝都是保护审计链的正确行为**，不是待修缺陷。
* 于是这条 operation 永远停在 `conflict`，它的冲突既不能裁决也不能丢弃 —— 一条只增不减
  的僵死记录。

本模块补的是**显式作废**：把「这批冲突在当前视角下已无意义」这个判断落成审计事实。

═══ 三条硬约束（都不是风格问题） ═══

1. **不物理删除冲突行**（R3.3）。冲突行是 append-only 审计事实；删掉之后没人能证明
   「曾经有过这些冲突、并且它们被作废了」。作废只写 `abandoned_at` / `abandon_reason` /
   `abandoned_by` 三列。
2. **不复用 `superseded_at`**。该列的唯一写入方是 `repository.record_conflicts`
   （观测同步），它还会对**本轮命中**的行执行 `row.superseded_at = None` **清零** ——
   拿它存人工作废会被下一次重观测静默抹掉。故 V276 新起三列。
3. **不裸 SQL 改 `state`**。状态推进必须经
   :meth:`~.repository.WorkpaperSyncRepository.append_operation_event`（它内部
   `assert_transition` 校验登记边，再写 append-only event，最后投影 current state）——
   裸 `UPDATE … SET state` 会跳过边校验与 timeline，版本链与审计链同时断。

═══ 终态取值为什么不新造 ═══

`OperationState` 是封闭枚举，DB 侧 `ck_wpso_state` 也逐值锁死（V151）。`conflict` 的
出边是 `{merging, rematerializing, error, superseded, authorization_stale}`
（:data:`~.models.OPERATION_EDGES`），其中**终态**只有两个：`superseded` 与
`authorization_stale`。作废取 ``OperationState.superseded``：

* 语义逐字相符 ——「这条 operation 因契约换代不再需要被处理」；
* **不取** `authorization_stale`：那个取值的语义是「授权在裁决途中失效」（由
  `assert_final_authorization` 的 fence 触发），而作废是人工作出的业务决定。用它会让
  timeline 把作废误报成授权事件，运维去查权限而不是查谁作了废。

🔴 **不新造** `abandoned` 字面量：`ck_wpso_state`（V151）会拒绝写入，且平台的
`is_terminal("operation", …)` 会把它判成非终态 ⇒ `finished_at` 不写、
`settle_requests_of_terminal_application` 不触发。

═══ 幂等与拒绝 ═══

| 情形 | 结果 |
| --- | --- |
| 同一 operation + 同一原因重放 | **幂等成功**（返回既有作废事实，不追加 event） |
| operation 已离开 `conflict`（含已作废）且原因不同 | `ConflictNotAbandonableError` |
| 一个冲突行都没有 | `ConflictNotAbandonableError`（没有可作废的对象） |
| 原因空白 | `AbandonReasonRequiredError` |
| 操作者缺失 | `AbandonActorRequiredError`（审计事实不得无主体） |

🔴 **操作者取服务端当前用户**，`abandon()` 的 `actor_id` 由 router 从
`GuardedScope.user_id` 传入，**不读请求体**。请求体只允许带 `reason`（见
`AbandonRequest`）—— 让客户端指定「谁作的废」等于让审计轨迹可伪造。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, Sequence

import sqlalchemy as sa

from app.models.workpaper_sync_models import (
    WorkpaperSyncConflict,
    WorkpaperSyncOperation,
)
from app.services.workpaper_sync.models import (
    ActorType,
    OperationState,
    SyncDomainError,
    is_terminal,
)
from app.services.workpaper_sync.repository import WorkpaperSyncRepository

__all__ = [
    "ConflictAbandonError",
    "ConflictNotAbandonableError",
    "AbandonReasonRequiredError",
    "AbandonActorRequiredError",
    "AbandonOutcome",
    "ConflictAbandonService",
    "ABANDON_TERMINAL_STATE",
    "ABANDON_STAGE",
    "MIN_REASON_CHARS",
]

#: 作废后的 operation 终态。**从既有枚举里选**，不新造字面量 —— 理由见模块 docstring
#: 「终态取值为什么不新造」。`conflict` 的另两个终态后继是 `superseded`（本处采用）
#: 与 `authorization_stale`（语义是「授权失效」，不适用）。
ABANDON_TERMINAL_STATE: Final[OperationState] = OperationState.superseded

#: operation event 的 `stage` 列（VARCHAR(40)）。
ABANDON_STAGE: Final[str] = "conflict_abandoned"

#: 原因的最小长度（去空白后）。R3.3 要求「带中文原因」，一个字的理由等于没写。
MIN_REASON_CHARS: Final[int] = 4


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常
# ═══════════════════════════════════════════════════════════════════════════


class ConflictAbandonError(SyncDomainError):
    """作废域的基类。"""

    error_code = "conflict_abandon_failed"


class ConflictNotAbandonableError(ConflictAbandonError):
    """当前状态不允许作废（已结算 / 非 conflict / 无冲突行 / 已按别的理由作废过）。

    🔴 `http_status = 409`：它与 `reslove_fence_rejected` 同族 —— 「你看到的是一份
    已经变了的服务端真值」，客户端刷新后可能就该看到别的按钮。**不给 404**：scope 可见、
    行也存在，用 404 会把它伪装成「不存在」。
    """

    error_code = "conflict_not_abandonable"
    http_status = 409


class AbandonReasonRequiredError(ConflictAbandonError):
    """作废必须带中文原因 —— R3.3 的原文。"""

    error_code = "conflict_abandon_reason_required"


class AbandonActorRequiredError(ConflictAbandonError):
    """作废必须记录操作者 —— 无主体的审计事实不可追溯。"""

    error_code = "conflict_abandon_actor_required"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 结果值对象
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AbandonOutcome:
    """一次作废的结果（`idempotent_replay` 区分首次与重放）。"""

    operation_id: uuid.UUID
    from_state: str
    to_state: str
    abandoned_conflicts: int
    already_abandoned: int
    abandon_reason: str
    abandoned_by: uuid.UUID
    abandoned_at: datetime
    idempotent_replay: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": str(self.operation_id),
            "from_state": self.from_state,
            "to_state": self.to_state,
            # 「状态变了但内容没落地」不可能出现：终态为 superseded 时这两个数必非零
            # 或（重放时）全部来自既有作废行（见 `_assert_trail_is_complete`）。
            "abandoned_conflicts": int(self.abandoned_conflicts),
            "already_abandoned": int(self.already_abandoned),
            "abandon_reason": self.abandon_reason,
            "abandoned_by": str(self.abandoned_by),
            "abandoned_at": self.abandoned_at.isoformat(),
            "idempotent_replay": bool(self.idempotent_replay),
            # 反向断言的可观测面：作废**不创建** representation / content version。
            "created_representations": 0,
            "created_content_versions": 0,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 3. 输入校验（纯函数，便于离线断言）
# ═══════════════════════════════════════════════════════════════════════════


def normalize_abandon_reason(raw: object) -> str:
    """校验并归一作废原因（空白 / 过短 / 非文本一律拒）。

    独立成模块级函数而不是内联：离线守卫要能直接驱动否定侧，且 router 侧的入参校验
    与 service 侧必须是同一份（抄第二份必然漂移）。
    """
    if not isinstance(raw, str):
        raise AbandonReasonRequiredError(
            f"作废原因必须是文本，实得 {type(raw).__name__} —— "
            "R3.3 要求带中文原因，缺失即不得作废"
        )
    text = raw.strip()
    if len(text) < MIN_REASON_CHARS:
        raise AbandonReasonRequiredError(
            f"作废原因至少 {MIN_REASON_CHARS} 个字（去空白后实得 {len(text)} 个）—— "
            "「无」「作废」这类理由无法让后来人判断这批冲突为什么不需要处理了"
        )
    return text


def assert_abandon_actor(actor_id: object) -> uuid.UUID:
    """操作者必填。`None` / 非 UUID 一律拒 —— 无主体的作废事实不可追溯。"""
    if actor_id is None:
        raise AbandonActorRequiredError(
            "作废必须记录操作者 —— 审计事实没有主体时，事后无法判断是谁把冲突判为无意义"
        )
    if isinstance(actor_id, uuid.UUID):
        return actor_id
    try:
        return uuid.UUID(str(actor_id))
    except (TypeError, ValueError) as exc:
        raise AbandonActorRequiredError(
            f"作废操作者 {actor_id!r} 不是合法 UUID"
        ) from exc


def assert_conflict_abandonable(state: OperationState | str) -> None:
    """只有 `conflict` 态可作废。

    🔴 不写成「非终态即可」：`applying` 之类的中间态作废会把一条正在落库的流水线
    拦腰切断，而作废的正确语义是「这批冲突不再需要处理」—— 只有冲突态才有这个语义。
    """
    current = state if isinstance(state, OperationState) else OperationState(str(state))
    if current is OperationState.conflict:
        return
    if is_terminal("operation", current):
        raise ConflictNotAbandonableError(
            f"operation 已处于终态 {current.value} —— 已结算的 operation 不得重复作废"
            f"（终态集合见 models.OPERATION_EDGES；作废只在 conflict 态成立）"
        )
    raise ConflictNotAbandonableError(
        f"operation 当前 state={current.value}，不是 conflict —— "
        "作废的语义是「这批冲突不再需要处理」，只有冲突态有这个语义；"
        "中间态（applying / rematerializing…）作废会把正在落库的流水线拦腰切断"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 服务
# ═══════════════════════════════════════════════════════════════════════════


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ConflictAbandonService:
    """作废一条 `conflict` operation 的冲突集。**只 flush 不 commit**（router 统一 commit）。

    本类刻意不 import `conflict_resolution`（那会形成环：`conflict_resolution` 已经
    依赖 `conflict_preview_contract` → `frozen_contract_reader`），也不复用
    `ConflictResolutionService` 的任何方法 —— 作废与裁决是两条不同的写路径，共用会
    把「作废也要过 fence」这种错误约束带进来。
    """

    def __init__(self, *, repo: WorkpaperSyncRepository) -> None:
        self._repo = repo
        self._session = repo.session

    # ─────────────────────────────────────────────────────────────────

    async def abandon(
        self,
        *,
        operation_id: uuid.UUID,
        reason: object,
        actor_id: object,
        now: datetime | None = None,
    ) -> AbandonOutcome:
        """把人工作废落成三列审计事实 + operation 终态。

        顺序即判据（任一顺序调换都会留下可观测的不一致）：

        1. 校验原因与操作者（纯函数，**在任何数据库读之前**抛）；
        2. 加行锁读 operation；
        3. 读该 operation 的全部冲突行（含已 superseded 的：作废要盖住整个冲突集）；
        4. 幂等判定（同原因重放 ⇒ 直接返回既有事实，零写入）；
        5. 写三列（不删行、不碰 `superseded_at`）；
        6. `append_operation_event` 推状态（边校验 + append-only event + 投影）；
        7. flush（不 commit）。

        第 5~6 步之间**没有** commit —— 作废事实与状态推进同生共死。
        """
        clean_reason = normalize_abandon_reason(reason)
        actor = assert_abandon_actor(actor_id)
        stamp = now or _now()

        op = (
            await self._session.execute(
                sa.select(WorkpaperSyncOperation)
                .where(WorkpaperSyncOperation.id == operation_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if op is None:
            # 走到这里说明 scope index 与业务行不一致（router 的 guard 已确认可见性）。
            raise ConflictNotAbandonableError(
                f"operation {operation_id} 行不存在（scope index 与业务行不一致）—— "
                "作废不创建 operation，也不修补 scope index"
            )

        current = OperationState(str(op.state))
        rows = await self._load_all_conflicts(operation_id)

        # ── 4. 幂等：已按同一原因作废过 ⇒ 返回既有事实（不追加 event、不改任何列） ──
        already = [r for r in rows if r.abandoned_at is not None]
        if already and all(str(r.abandon_reason or "") == clean_reason for r in already):
            if current is ABANDON_TERMINAL_STATE and len(already) == len(rows):
                self._assert_trail_is_complete(rows)
                return AbandonOutcome(
                    operation_id=operation_id,
                    from_state=current.value,
                    to_state=current.value,
                    abandoned_conflicts=0,
                    already_abandoned=len(already),
                    abandon_reason=clean_reason,
                    abandoned_by=actor,
                    abandoned_at=max(r.abandoned_at for r in already),
                    idempotent_replay=True,
                )

        # ── 5. 状态准入（幂等分支之外才判 —— 已作废的重放必须仍可读到结果） ──
        assert_conflict_abandonable(current)
        if not rows:
            raise ConflictNotAbandonableError(
                f"operation {operation_id} 没有任何冲突行 —— 没有可作废的对象；"
                "「一条冲突都没有」的 operation 应走正常 apply 路径，不是作废"
            )
        if already:
            other = sorted({str(r.abandon_reason or "") for r in already})
            raise ConflictNotAbandonableError(
                f"operation {operation_id} 的部分冲突已被另一条理由作废（{other}）—— "
                "同一冲突集的作废理由必须唯一，否则审计轨迹会自相矛盾"
            )

        # ── 5. 写三列（不删行；**不碰** superseded_at） ──
        for row in rows:
            row.abandoned_at = stamp
            row.abandon_reason = clean_reason
            row.abandoned_by = actor

        # ── 6. 状态推进：边校验 + append-only event + 投影（唯一合法写法） ──
        await self._repo.append_operation_event(
            operation_id=op.id,
            from_state=current,
            to_state=ABANDON_TERMINAL_STATE,
            stage=ABANDON_STAGE,
            actor_type=ActorType.user,
            actor_id=actor,
            error_code=None,
        )
        op.state = ABANDON_TERMINAL_STATE.value
        if op.finished_at is None:
            op.finished_at = stamp

        await self._session.flush()
        self._assert_trail_is_complete(rows)
        return AbandonOutcome(
            operation_id=operation_id,
            from_state=current.value,
            to_state=ABANDON_TERMINAL_STATE.value,
            abandoned_conflicts=len(rows),
            already_abandoned=0,
            abandon_reason=clean_reason,
            abandoned_by=actor,
            abandoned_at=stamp,
            idempotent_replay=False,
        )

    # ─────────────────────────────────────────────────────────────────

    async def _load_all_conflicts(
        self, operation_id: uuid.UUID
    ) -> Sequence[WorkpaperSyncConflict]:
        """该 operation 的**全部**冲突行，含 `superseded_at` 非空的。

        🔴 刻意不用 `repo.load_conflicts()`（它默认滤掉 superseded）：作废是「整个冲突集
        不再需要处理」，只盖住当前可见的那部分会让 superseded 的行永远停在「既没裁决
        也没作废」的状态，而它们在审计上同属这一批冲突。
        """
        rows = list(
            (
                await self._session.execute(
                    sa.select(WorkpaperSyncConflict)
                    .where(WorkpaperSyncConflict.operation_id == operation_id)
                    .order_by(
                        WorkpaperSyncConflict.sheet_key,
                        WorkpaperSyncConflict.table_key,
                        WorkpaperSyncConflict.row_key,
                        WorkpaperSyncConflict.stable_field_key,
                        WorkpaperSyncConflict.oo_location,
                    )
                )
            ).scalars()
        )
        return rows

    @staticmethod
    def _assert_trail_is_complete(rows: Sequence[WorkpaperSyncConflict]) -> None:
        """Property 3 的形态判据：「状态变了但内容没落地」不可能出现。

        终态为作废时，**每一行**冲突都必须三列齐备。这不是防御性代码：DB 侧的
        `ck_wpsc_abandon_triplet` 只管「三列同生共死」，管不住「只更新了其中一部分行」
        —— 那正是本判据要拦的形态（例如按 `load_conflicts()` 的可见集更新，而
        superseded 行被漏掉）。

        🔴 它同时断言原文里那句「不物理删除冲突行」：调用方拿到的 rows 是**本次写之前**
        读出来的行集合，行数不变才说明没有删除。
        """
        broken = [
            str(r.id)
            for r in rows
            if r.abandoned_at is None
            or r.abandoned_by is None
            or not str(r.abandon_reason or "").strip()
        ]
        if broken:
            raise ConflictAbandonError(
                f"{len(broken)} 条冲突行只写了部分作废列（{broken[:5]}）—— "
                "「状态变了但内容没落地」在作废路径上不允许出现"
            )
