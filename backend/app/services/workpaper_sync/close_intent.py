# -*- coding: utf-8 -*-
"""Task 24（下半）：clean close 的 exactly-one close-capture 仲裁与生命周期。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 24
Requirements: 4.1, 4.4, 4.7, 4.10, 5.5, 10.10
Properties: **P12 / P13 / P15 / P43 / P64**

═══ 这一层补的到底是什么 ═══

Task 10 的 :meth:`~.repository.WorkpaperSyncRepository.reconcile_close_intents` 已经在
room lock 内实现了 leader / successor / no-successor 三条路径。Task 21 给了 room 侧的
八条资格门。Task 23 给了「先落库再出站」的唯一入口。**但三者之间没有生产代码**：

1. **授权**：:meth:`~.repository.WorkpaperSyncRepository.create_close_intent` 只校验
   confirmation 属于同 room/participant，**不校验** mode=edit、lease 未过期、未撤销、
   write fence、bundle identity。AC 4.10 要求 close intent 必须由「已完成 descriptor
   confirmation 的 authenticated active edit participant」创建 —— 这一层在此加上，
   且在**任何写之前**（`system/route identity 不可替代用户授权`，AC 10.10）。
2. **barrier predecessor**：`working_paper_oo_close_intent.ordinary_forcesave_request_id`
   这一列此前**没有任何生产代码写过**（只在 schema 契约测试里被裸 INSERT 填过）。
   AC 4.10「非 leader closing participant 只执行普通 forcesave」正是靠它成为 barrier
   predecessor —— 不写它，barrier 就只能靠「room/generation 里还有没有 open forcesave」
   这种间接判据，而 intent 与它的 predecessor 之间的对应关系无从审计。
3. **出站**：leader 被 CAS 提升成 `close_capture` request 之后，得真的把命令发给 OO。

═══ leader 仲裁：`created_at` 在这一层**不可表达** ═══

AC 4.10 / 契约 `clean_close.server_protocol` 都写死「按最高 `(intent_sequence,id)`」，
且 Task 24 正文补了一句：「`created_at` 只作审计、禁止参与仲裁，时间戳/插入顺序扰动
不得换 leader」。

把它写成注释是没用的。本模块的做法是让 `created_at` **进不来**：
:class:`CloseIntentFacts`（仲裁的唯一输入类型）根本没有时间字段，于是
:func:`select_close_leader` 想按时间排序也无从下手。这比「记得别用 created_at」强一个
量级 —— 后者靠自觉，前者靠类型。

🔴 与之配套的是**双记账**：:class:`CloseIntentService` 在同一个 room lock 内先用本模块的
纯函数算出 :class:`LeaderPrediction`，再调仓储的 reconciler，然后
:func:`assert_leader_matches_prediction` 逐项比对。仓储侧 comparator 若被改成
`created_at`（或 min、或丢掉 id tiebreak），两侧结论在「最高 sequence 的 intent 既不是
最早插入、也不是最晚 `created_at`」这类输入上会分叉，于是服务边界当场抛
:class:`CloseLeaderArbitrationError`。

这不是「再写一遍逻辑」的重复：纯函数只接收快照、不落库、不选 leader（选 leader 是
reconciler 在锁内的职责），它的唯一作用是**证伪**。Task 23 的
`_assert_convergence` 是同一个模式（仓储已保证，入口再验一次，因为入口处失败可诊断）。

═══ at-most-one ≠ exactly-one ═══

V151 的 `uq_wpfr_open_close_capture` 只是 generation 内 open-state partial unique：
它能证明**不会有两条**，永远证明不了**最终会有一条**。所以本模块另外承担两条断言：

* :meth:`CloseIntentService._assert_at_most_one_open_capture` —— 每次 reconcile 后真查
  库（不是信 outcome），把 partial unique 的保证在服务层也变成可诊断失败；
* :meth:`CloseIntentService._assert_no_live_intent_remains` —— no-successor 路径跑完，
  **不允许**还有 intent 停在 live 状态。AC 4.10 明令「不得永久 `retryable_blocked`」，
  而 partial unique 对「一条都没有」毫无意见 —— 只有这条断言能把「永久阻塞」抓住。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final, Iterable, Mapping, Sequence

import sqlalchemy as sa

from app.models.workpaper_sync_models import (
    WorkpaperContentApplication,
    WorkpaperForcesaveRequest,
    WorkpaperOoCloseIntent,
    WorkpaperOoParticipant,
    WorkpaperOoRoom,
    WorkpaperSyncOperation,
)

from .command_service import CommandServiceClient, CommandTarget, DispatchRecord
from .models import (
    ActorType,
    CloseIntentState,
    ParticipantState,
    RequestKind,
    RequestState,
    RoomState,
    SyncDomainError,
    assert_transition,
    classify_operation_shape,
)
from .repository import (
    _OPEN_CAPTURE_STATES,
    CloseReconcileOutcome,
    WorkpaperSyncRepository,
)
from .request_application import AcceptedRequest, RequestApplicationService
from .rooms import FrozenBundleIdentity, RoomScope, RoomService

__all__ = [
    "CLOSE_INTENT_LIVE_STATES",
    "CloseCaptureNotUniqueError",
    "CloseIntentAuthorizationError",
    "CloseIntentDomainError",
    "CloseIntentFacts",
    "CloseIntentOpened",
    "CloseIntentPermanentlyBlockedError",
    "CloseIntentService",
    "CloseLeaderArbitrationError",
    "CloseReconcileServiceOutcome",
    "CloseSuccessorAccountingError",
    "LeaderPrediction",
    "OPEN_CAPTURE_STATES",
    "ParticipantFacts",
    "assert_at_most_one_open_capture",
    "assert_frozen_identity_complete",
    "assert_leader_matches_prediction",
    "assert_no_live_intent_remains",
    "assert_refusals_are_disjoint",
    "close_leader_sort_key",
    "eligible_close_intents",
    "intent_is_eligible",
    "predict_close_leader",
    "select_close_leader",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 拒绝类型（逐条分型，互不为子类）
# ═══════════════════════════════════════════════════════════════════════════


class CloseIntentDomainError(SyncDomainError):
    """Task 24 close-intent 域基类。"""

    error_code = "close_intent_error"


class CloseIntentAuthorizationError(CloseIntentDomainError):
    """close intent 的冻结身份不完整（participant/permission epoch/bundle/fence 任一为空）。

    与 Task 21 的 :class:`~.rooms.RoomPolicyError` 家族**分型**：那些是「资格不合格」
    （撤销/过期/只读/fence 变化），本条是「资格合格但冻结值缺失」——
    AC 10.10 的「initiator 缺失 SHALL 阻止提交」说的正是后者，而它在前者的判据里
    一条都不对应（一个有效 participant 完全可能 permission_epoch 为 NULL）。
    """

    error_code = "close_intent_authorization_incomplete"


class CloseLeaderArbitrationError(CloseIntentDomainError):
    """仓储 reconciler 选出的 leader 与本模块纯函数的预测不一致。

    这是双记账的告警口。触发它只有两种可能：仓储 comparator 变了
    （被改成 `created_at` / min / 丢 id tiebreak），或本模块的 eligibility 谓词
    与仓储的 `eligible()` 漂移了。两者都必须**立刻**可见，绝不能继续提升 leader。
    """

    error_code = "close_leader_arbitration_mismatch"


class CloseSuccessorAccountingError(CloseIntentDomainError):
    """`authorization_stale` / `no_successor` 的记账与预测不符。

    🔴 与 :class:`CloseLeaderArbitrationError` **必须分型且互不为子类**：
    「leader 选错」与「leader 没选错但漏写 authorization_stale 审计」是两条独立
    要求（AC 4.10 分别写明）。合成一类时，「漏写 stale」的定向变异会被
    「leader 选错」那条断言遮蔽 —— 本 spec 已在 Task 22 M04/M10、Task 23 M25
    上为这个形态付过三次代价。
    """

    error_code = "close_successor_accounting_mismatch"


class CloseCaptureNotUniqueError(CloseIntentDomainError):
    """同 generation 出现 >1 条 open close-capture。任何 >1 都失败（AC 4.10）。"""

    error_code = "close_capture_not_unique"


class CloseIntentPermanentlyBlockedError(CloseIntentDomainError):
    """no-successor 终结后仍有 intent 停在 live 状态 —— 永久阻塞。

    单独分型：它与 :class:`CloseCaptureNotUniqueError` 是 exactly-one 的**两个反面**
    （多了一条 / 一条都不会有且卡死）。共用类型时「零 capture 但不阻塞」这半条
    就没有独立判据。
    """

    error_code = "close_intent_permanently_blocked"


_REFUSALS: Final[tuple[type[CloseIntentDomainError], ...]] = (
    CloseIntentAuthorizationError,
    CloseLeaderArbitrationError,
    CloseSuccessorAccountingError,
    CloseCaptureNotUniqueError,
    CloseIntentPermanentlyBlockedError,
)


def assert_refusals_are_disjoint() -> tuple[str, ...]:
    """逐对断言拒绝类型互不为子类且 error_code 不重复（守卫的分母）。"""
    codes: dict[str, str] = {}
    for t in _REFUSALS:
        code = str(getattr(t, "error_code", ""))
        if not code:
            raise CloseIntentDomainError(f"{t.__name__} 未声明 error_code")
        if code in codes:
            raise CloseIntentDomainError(
                f"{t.__name__} 与 {codes[code]} 共用 error_code={code!r}"
            )
        codes[code] = t.__name__
    for a in _REFUSALS:
        for b in _REFUSALS:
            if a is not b and issubclass(a, b):
                raise CloseIntentDomainError(
                    f"{a.__name__} 是 {b.__name__} 的子类 —— 捕获后者会顺手吃掉前者"
                )
    return tuple(sorted(t.__name__ for t in _REFUSALS))


# ═══════════════════════════════════════════════════════════════════════════
# 2. 纯仲裁层：`created_at` 在这里不可表达
# ═══════════════════════════════════════════════════════════════════════════

#: intent 仍「在世」（尚未终结、仍可成为 leader/successor）的状态集合。
#:
#: 与仓储 `eligible()` 的状态清单同义。终态（`promoted` / `authorization_stale` /
#: `recovery_required` / `superseded` / `error`）都不在内。
CLOSE_INTENT_LIVE_STATES: Final[frozenset[CloseIntentState]] = frozenset(
    {
        CloseIntentState.created,
        CloseIntentState.ordinary_forcesaving,
        CloseIntentState.waiting_barrier,
        CloseIntentState.leader_ready,
        CloseIntentState.retryable_blocked,
        CloseIntentState.successor_selected,
    }
)

#: close-capture 的「open」状态集合 —— 直接复用仓储的那一份，**不另抄**。
#:
#: 真源其实有三处：V151 的 `uq_wpfr_open_close_capture` WHERE 子句、仓储的
#: `_OPEN_CAPTURE_STATES`、以及本模块。第三处在此被消掉（import 而非复制），
#: 剩下两处由 `test_task24_*::test_open_capture_states_are_locked_to_the_sql_index`
#: 双向锁死 —— 那条守卫直读 V151 的 SQL 并与这个常量比对。
OPEN_CAPTURE_STATES: Final[frozenset[RequestState]] = frozenset(
    RequestState(s) for s in _OPEN_CAPTURE_STATES
)


@dataclass(frozen=True)
class ParticipantFacts:
    """仲裁需要的 participant 事实（只读投影）。"""

    participant_id: uuid.UUID
    state: ParticipantState
    revoked: bool
    expired: bool


@dataclass(frozen=True)
class CloseIntentFacts:
    """仲裁的唯一输入类型。

    🔴 **刻意没有 `created_at`**（也没有 `reconciled_at` / `finished_at`）。
    AC 4.10 / Task 24 正文：`created_at` 只作审计、禁止参与仲裁。把它从输入类型里
    删掉，「不小心按时间排序」就从「需要 review 发现」变成「写不出来」。
    """

    intent_id: uuid.UUID
    participant_id: uuid.UUID
    intent_sequence: int
    state: CloseIntentState


def intent_is_eligible(
    intent: CloseIntentFacts, participants: Mapping[uuid.UUID, ParticipantFacts]
) -> bool:
    """该 intent 是否仍有资格成为 leader/successor。

    四条判据各自独立可变异（合成一条时删掉任一条都会被其余遮蔽）：

    1. participant 必须存在于本 room 的快照里；
    2. participant 必须**正处于** `closing` —— 已 `left`/`active`/`expired` 都不算
       （`active` 也不算：intent 创建时就该把它转成 `closing`，仍 `active` 说明状态机破了）；
    3. 未被撤销；
    4. lease 未过期。

    第 2~4 条对应 AC 4.10「若 leader 在 promotion 前失去资格」的三种失格方式。
    """
    p = participants.get(intent.participant_id)
    if p is None:
        return False
    if p.state is not ParticipantState.closing:
        return False
    if p.revoked:
        return False
    if p.expired:
        return False
    return intent.state in CLOSE_INTENT_LIVE_STATES


def eligible_close_intents(
    intents: Iterable[CloseIntentFacts],
    participants: Mapping[uuid.UUID, ParticipantFacts],
) -> tuple[CloseIntentFacts, ...]:
    """按 :func:`intent_is_eligible` 过滤，保持调用方给的顺序。"""
    return tuple(i for i in intents if intent_is_eligible(i, participants))


def close_leader_sort_key(intent: CloseIntentFacts) -> tuple[int, str]:
    """仲裁排序键：`(intent_sequence, id)`，**取最大**。

    `str(uuid)` 的字典序与 PostgreSQL `uuid` 列的字节序等价：canonical 形式是
    16 字节的小写十六进制、连字符在固定位置，故连字符永不参与比较，而
    `0-9 < a-f` 在 ASCII 与十六进制数值上同序。这一点让「Python 侧预测」与
    「SQL 侧 `ORDER BY intent_sequence DESC, id DESC`」必然一致 ——
    否则双记账会在 id tiebreak 上偶发分叉，表现为随机的仲裁告警。
    """
    return (int(intent.intent_sequence), str(intent.intent_id))


def select_close_leader(
    intents: Sequence[CloseIntentFacts],
) -> CloseIntentFacts | None:
    """最高 `(intent_sequence, id)` 者胜；空集返回 ``None``。

    确定性由排序键本身保证，因此「同 eligibility snapshot 重试不得换 leader」
    不需要任何额外的「digest 相同就沿用旧 leader」分支 —— 那种分支在行为上不可达
    （eligible 集合不变 ⇒ 键集不变 ⇒ max 不变），属于「additive 注入即死代码」。
    """
    if not intents:
        return None
    return max(intents, key=close_leader_sort_key)


@dataclass(frozen=True)
class LeaderPrediction:
    """对 reconciler 结论的独立预测（双记账的一边）。"""

    leader_intent_id: uuid.UUID | None
    eligible_intent_ids: tuple[uuid.UUID, ...]
    expected_stale_intent_ids: tuple[uuid.UUID, ...]
    no_successor: bool
    promoted_short_circuit: bool
    empty: bool

    @property
    def has_successor(self) -> bool:
        return self.leader_intent_id is not None


def predict_close_leader(
    intents: Sequence[CloseIntentFacts],
    participants: Mapping[uuid.UUID, ParticipantFacts],
    *,
    current_leader_intent_id: uuid.UUID | None,
) -> LeaderPrediction:
    """复刻 AC 4.10 的仲裁顺序，作为对仓储 reconciler 的独立预测。

    分支顺序**必须**与 reconciler 一致，否则双记账会在合法场景上假红：

    0. 该 generation 一条 intent 都没有 ⇒ 什么也不做（既非 no-successor，也无 leader）；
    1. 已有 `promoted` intent ⇒ 幂等短路。AC 10.10：promotion 后授权失效只能走
       recovery，**不得**再选 successor，所以这一步在失格判定**之前**；
    2. 当前 leader 已失格 ⇒ 它将被记为 `authorization_stale`；
    3. 剩余 eligible 为空 ⇒ no-successor（零 capture + 显式 recovery 终态）；
    4. 否则按最高 `(intent_sequence, id)` 选 leader/successor。
    """
    rows = list(intents)
    if not rows:
        return LeaderPrediction(
            leader_intent_id=None,
            eligible_intent_ids=(),
            expected_stale_intent_ids=(),
            no_successor=False,
            promoted_short_circuit=False,
            empty=True,
        )
    promoted = next((i for i in rows if i.state is CloseIntentState.promoted), None)
    if promoted is not None:
        return LeaderPrediction(
            leader_intent_id=promoted.intent_id,
            eligible_intent_ids=(),
            expected_stale_intent_ids=(),
            no_successor=False,
            promoted_short_circuit=True,
            empty=False,
        )
    stale: list[uuid.UUID] = []
    if current_leader_intent_id is not None:
        current = next(
            (i for i in rows if i.intent_id == current_leader_intent_id), None
        )
        if current is not None and not intent_is_eligible(current, participants):
            stale.append(current.intent_id)
    eligible = eligible_close_intents(rows, participants)
    leader = select_close_leader(eligible)
    return LeaderPrediction(
        leader_intent_id=(None if leader is None else leader.intent_id),
        eligible_intent_ids=tuple(i.intent_id for i in eligible),
        expected_stale_intent_ids=tuple(stale),
        no_successor=not eligible,
        promoted_short_circuit=False,
        empty=False,
    )


def assert_leader_matches_prediction(
    *,
    prediction: LeaderPrediction,
    reported_leader_intent_id: uuid.UUID | None,
    reported_no_successor: bool,
    reported_stale_intent_ids: Sequence[uuid.UUID],
) -> None:
    """双记账比对。三项各自分型，互不遮蔽。

    抽成模块级纯函数（而不是 :class:`CloseIntentService` 的私有方法）是为了
    **可用合成输入证明分支覆盖**：真实 happy path 上三条分支一条都不会走，
    只在库里放一份「reconciler 与预测分叉」的状态是做不到的（正确的 reconciler
    不会分叉）。守卫因此直接喂构造好的不一致输入 —— 这正是「守卫不得断言真实数据
    仍有缺陷，要用合成输入证明分支覆盖」那条规矩。
    """
    if reported_leader_intent_id != prediction.leader_intent_id:
        raise CloseLeaderArbitrationError(
            f"reconciler 选出的 leader={reported_leader_intent_id} 与按最高 "
            f"(intent_sequence, id) 的预测 {prediction.leader_intent_id} 不一致"
            f"（eligible={list(prediction.eligible_intent_ids)}）—— "
            "`created_at` 与插入顺序禁止参与仲裁（AC 4.10）"
        )
    if bool(reported_no_successor) != bool(prediction.no_successor):
        raise CloseSuccessorAccountingError(
            f"reconciler 报告 no_successor={reported_no_successor}，预测为 "
            f"{prediction.no_successor} —— 有 successor 却走 supersede（或反之）"
        )
    if sorted(str(i) for i in reported_stale_intent_ids) != sorted(
        str(i) for i in prediction.expected_stale_intent_ids
    ):
        raise CloseSuccessorAccountingError(
            f"authorization_stale 记账不符：reconciler "
            f"{[str(i) for i in reported_stale_intent_ids]} vs 预测 "
            f"{[str(i) for i in prediction.expected_stale_intent_ids]} —— "
            "leader 在 promotion 前失格必须 append-only 记 `authorization_stale`"
        )


def assert_frozen_identity_complete(
    *,
    participant_id: uuid.UUID | None,
    permission_epoch: int | None,
    confirmation_id: uuid.UUID | None,
    write_fence_epoch: int | None,
    definition_bundle_id: uuid.UUID | None,
) -> None:
    """冻结身份五项非空（AC 4.10 / 10.10：null initiator 必须在出站前被拒）。

    五项**逐一**检查而不是 `all([...])`：合并成一条时，删掉任意一项都会被其余遮蔽，
    定向变异必然判 GREEN。

    入参是**纯值**而不是 ORM 行：一个有效 participant 完全可能 `permission_epoch`
    为 NULL，而真库里造这种行要么被约束挡住、要么污染其他判据；纯值签名让五条分支
    各自用合成输入证明。
    """
    if participant_id is None:
        raise CloseIntentAuthorizationError(
            "close intent 的 initiating participant 为空 —— "
            "system/route identity 不可替代用户授权"
        )
    if permission_epoch is None:
        raise CloseIntentAuthorizationError(
            f"participant {participant_id} 的 permission_epoch 为空 —— "
            "冻结身份必须含非空 permission epoch"
        )
    if confirmation_id is None:
        raise CloseIntentAuthorizationError(
            "close intent 必须引用已完成的 descriptor confirmation"
        )
    if write_fence_epoch is None:
        raise CloseIntentAuthorizationError(
            "room 的 write_fence_epoch 为空 —— 冻结身份必须含非空 fence"
        )
    if definition_bundle_id is None:
        raise CloseIntentAuthorizationError(
            "room 没有 client-confirmed definition bundle —— "
            "冻结身份必须含非空 approved bundle"
        )


def assert_at_most_one_open_capture(
    count: int, *, room_id: uuid.UUID, generation: int
) -> None:
    """generation 内 open close-capture 不得 >1（AC 4.10：任何 >1 均失败）。

    `uq_wpfr_open_close_capture` 已在库层保证这一点，本函数是服务入口处的可诊断复核。

    🔴 抽成模块级纯函数而不是留在服务方法里：正确实现下 `count` 永远是 0 或 1，
    所以「>1 时会不会抛」在任何真库场景里都触发不到 —— 内嵌形态的这条判据是
    **不可证伪**的（把它改成 `if False:` 不会有任何测试变红）。抽出来喂合成
    `count=2` 才让它有判据。
    """
    if count > 1:
        raise CloseCaptureNotUniqueError(
            f"room {room_id} generation {generation} 出现 {count} 条 open "
            "close-capture —— exactly-one 被破坏（任何 >1 均失败）"
        )


def assert_no_live_intent_remains(
    live_intents: int, *, room_id: uuid.UUID, generation: int
) -> None:
    """no-successor 终结后不得还有 live intent（AC 4.10「不得永久 blocked」）。

    这是 exactly-one 的另一半：partial unique 对「一条 capture 都没有」毫无意见，
    所以「零 capture 且卡死」只能靠本条抓 —— 它正是 Task 24 正文里
    「无 successor 仍 blocked 的定向变异必须打红」对应的生产判据。

    与 :func:`assert_at_most_one_open_capture` 同理抽成纯函数：正确实现下
    `live_intents` 恒为 0。
    """
    if live_intents:
        raise CloseIntentPermanentlyBlockedError(
            f"room {room_id} generation {generation} 已判定无 successor，"
            f"但仍有 {live_intents} 条 intent 停在 live 状态 —— 必须全部落 "
            "`recovery_required`/`authorization_stale` 显式终态，"
            "不得永久 retryable_blocked"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 服务结果
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CloseReconcileServiceOutcome:
    """一次服务层 reconcile 的结果（仓储结论 + 本层核验 + 可能的出站）。"""

    repository: CloseReconcileOutcome
    prediction: LeaderPrediction
    open_capture_count: int
    live_intent_count: int
    capture_dispatch: DispatchRecord | None

    @property
    def leader_intent_id(self) -> uuid.UUID | None:
        return self.repository.leader_intent_id

    @property
    def capture_created(self) -> bool:
        return bool(self.repository.capture_created)

    @property
    def no_successor(self) -> bool:
        return bool(self.repository.no_successor)


@dataclass(frozen=True)
class CloseIntentOpened:
    """一次 close intent 创建的结果。"""

    intent_id: uuid.UUID
    intent_sequence: int
    participant_id: uuid.UUID
    remaining_active_editors: int
    predecessor: DispatchRecord | None
    reconcile: CloseReconcileServiceOutcome

    @property
    def has_predecessor(self) -> bool:
        return self.predecessor is not None


# ═══════════════════════════════════════════════════════════════════════════
# 4. 服务
# ═══════════════════════════════════════════════════════════════════════════


class CloseIntentService:
    """clean close 的编排层。**不 commit**；事务边界由 coordinator 持有。

    `client` 没有默认值：忘记接线时会在**构造**处 `TypeError`，而不是在运行时
    静默跳过出站（「没配就不发」是 fail-open 的经典形态）。
    """

    def __init__(
        self,
        repo: WorkpaperSyncRepository,
        client: CommandServiceClient,
        *,
        rooms: RoomService | None = None,
        requests: RequestApplicationService | None = None,
    ) -> None:
        self._repo = repo
        self._session = repo.session
        self._rooms = rooms if rooms is not None else RoomService(repo)
        self._requests = (
            requests
            if requests is not None
            else RequestApplicationService(repo, self._rooms)
        )
        self._client = client

    # ─────────────────────────────────────────────────────────────────
    # 4.1 创建 close intent
    # ─────────────────────────────────────────────────────────────────

    async def open_close_intent(
        self,
        scope: RoomScope,
        *,
        room_id: uuid.UUID,
        participant_id: uuid.UUID,
        idempotency_key: str,
        client_edit_epoch: int,
        adapter_build_digest: str,
        contributor_snapshot_digest: str,
        contributor_user_ids: Iterable[uuid.UUID | str] = (),
        expected_write_fence_epoch: int | None = None,
        expected_bundle: FrozenBundleIdentity | None = None,
        created_by: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> CloseIntentOpened:
        """销毁编辑器**之前**创建 close intent（AC 4.10 的入口）。

        顺序固定：

        1. **授权先行** —— Task 21 的八条资格门 + 本层的「冻结值非空」检查。
           在任何写之前，且在任何 Command Service 调用之前（AC 4.7 / Property 15）；
        2. room lock 内建 intent 并把 participant `active→closing`、推进 barrier
           （委派仓储；`closing` 自此不再计入 active）；
        3. 若仍有其他 active editor ⇒ 为本 participant 建普通 forcesave predecessor
           （经 Task 23 的唯一入口）、写 `ordinary_forcesave_request_id`、出站，然后 leave；
        4. `reconcile_close_intents()` —— active 首次归零时它会冻结 barrier 并选 leader。

        第 3 步的「若仍有其他 active editor」判定发生在第 2 步**之后**：本 participant
        已是 `closing`，所以「最后一个关闭的人」看到的 active 数是 0，不会给自己建
        predecessor —— 它的 close-capture 就是它的保存。
        """
        room, participant, confirmation = await self._rooms.assert_can_initiate_request(
            room_id=room_id,
            participant_id=participant_id,
            # 🔴 用 `forcesave` 过门而不是 `close_capture`：Task 21 的门对
            # `close_capture` 一律拒绝（客户端不得直接发起 close-capture，
            # 契约 clean_close.forbidden[0]）。close intent 要的是「该用户此刻
            # 有资格发起写请求」这同一组判据，而 close-capture 只能由 reconciler
            # 在锁内 CAS 产生。
            kind=RequestKind.forcesave,
            expected_write_fence_epoch=expected_write_fence_epoch,
            expected_bundle=expected_bundle,
        )
        assert_frozen_identity_complete(
            participant_id=participant.id,
            permission_epoch=participant.permission_epoch,
            confirmation_id=confirmation.id,
            write_fence_epoch=room.write_fence_epoch,
            definition_bundle_id=room.client_confirmed_definition_bundle_id,
        )

        intent = await self._repo.create_close_intent(
            project_id=scope.project_id,
            wp_id=scope.wp_id,
            entry_id=scope.entry_id,
            room_id=room_id,
            participant_id=participant_id,
            client_confirmation_id=confirmation.id,
            actor_id=actor_id,
        )

        remaining_active = await self._count_active_editors(room_id)
        predecessor: DispatchRecord | None = None
        if remaining_active > 0:
            predecessor = await self._create_and_dispatch_predecessor(
                scope,
                room=room,
                intent=intent,
                participant_id=participant_id,
                idempotency_key=idempotency_key,
                client_edit_epoch=client_edit_epoch,
                contributor_user_ids=contributor_user_ids,
                expected_write_fence_epoch=expected_write_fence_epoch,
                expected_bundle=expected_bundle,
                created_by=created_by,
                actor_id=actor_id,
            )

        reconcile = await self.reconcile(
            scope,
            room_id=room_id,
            adapter_build_digest=adapter_build_digest,
            contributor_snapshot_digest=contributor_snapshot_digest,
        )
        return CloseIntentOpened(
            intent_id=intent.id,
            intent_sequence=int(intent.intent_sequence),
            participant_id=participant_id,
            remaining_active_editors=remaining_active,
            predecessor=predecessor,
            reconcile=reconcile,
        )

    async def _count_active_editors(self, room_id: uuid.UUID) -> int:
        """仍在 `active` 的 participant 数。`closing` **不计入**（AC 4.10）。"""
        return int(
            (
                await self._session.execute(
                    sa.select(sa.func.count())
                    .select_from(WorkpaperOoParticipant)
                    .where(
                        WorkpaperOoParticipant.room_id == room_id,
                        WorkpaperOoParticipant.state == ParticipantState.active.value,
                    )
                )
            ).scalar_one()
        )

    async def _create_and_dispatch_predecessor(
        self,
        scope: RoomScope,
        *,
        room: WorkpaperOoRoom,
        intent: WorkpaperOoCloseIntent,
        participant_id: uuid.UUID,
        idempotency_key: str,
        client_edit_epoch: int,
        contributor_user_ids: Iterable[uuid.UUID | str],
        expected_write_fence_epoch: int | None,
        expected_bundle: FrozenBundleIdentity | None,
        created_by: uuid.UUID | None,
        actor_id: uuid.UUID | None,
    ) -> DispatchRecord:
        """非 leader / 先关闭的 participant 的 barrier predecessor（AC 4.10）。

        request 一律经 Task 23 的 :meth:`~.request_application.RequestApplicationService.freeze_and_persist_request`
        创建 —— 本模块**不直接**调 `create_forcesave_request_with_shell`
        （`test_task24_*::test_service_never_bypasses_the_task23_entry_point` 是这条的
        源码判据）。走那个入口才能拿到「authorization-first → freeze → 同事务落库」
        的顺序保证，以及同 Idempotency-Key 重放时对当前授权与 frozen fingerprint
        的重新校验。
        """
        accepted = await self._requests.freeze_and_persist_request(
            scope,
            room_id=room.id,
            participant_id=participant_id,
            idempotency_key=idempotency_key,
            client_edit_epoch=client_edit_epoch,
            kind=RequestKind.forcesave,
            contributor_user_ids=contributor_user_ids,
            expected_write_fence_epoch=expected_write_fence_epoch,
            expected_bundle=expected_bundle,
            created_by=created_by,
        )
        intent.ordinary_forcesave_request_id = accepted.request.id
        prior = CloseIntentState(intent.state)
        if prior is not CloseIntentState.ordinary_forcesaving:
            assert_transition(
                "close_intent", prior, CloseIntentState.ordinary_forcesaving
            )
            intent.state = CloseIntentState.ordinary_forcesaving.value
            await self._session.flush()
            await self._repo.append_close_intent_event(
                intent_id=intent.id,
                from_state=prior,
                to_state=CloseIntentState.ordinary_forcesaving,
                eligibility_epoch=int(intent.eligibility_epoch),
                actor_type=ActorType.user,
                actor_id=actor_id,
                authorization_result="predecessor",
            )
        else:  # pragma: no cover - 仅在同 intent 被重复接线时可达
            await self._session.flush()
        dispatch = await self._client.forcesave(
            accepted,
            target=CommandTarget(
                room_id=room.id, generation=int(room.generation), doc_key=room.doc_key
            ),
        )
        return DispatchRecord(accepted=accepted, dispatch=dispatch)

    # ─────────────────────────────────────────────────────────────────
    # 4.2 可重入 reconcile
    # ─────────────────────────────────────────────────────────────────

    async def reconcile(
        self,
        scope: RoomScope,
        *,
        room_id: uuid.UUID,
        adapter_build_digest: str,
        contributor_snapshot_digest: str,
    ) -> CloseReconcileServiceOutcome:
        """可重入 reconcile（AC 4.10）。快照与仲裁在**同一个 room lock** 内。

        `lock_room` 先于快照读取，是双记账成立的前提：若快照在锁外读，另一个事务
        可以在「预测」与「仲裁」之间改掉 participant 状态，于是分叉是并发造成的、
        而不是 comparator 错了 —— 那会让告警变成随机噪声（CI 重试的经典来源）。
        """
        room = await self._repo.lock_room(room_id)
        generation = int(room.generation)
        intents, participants = await self._snapshot(room_id, generation)
        prediction = predict_close_leader(
            intents,
            participants,
            current_leader_intent_id=room.close_leader_intent_id,
        )

        outcome = await self._repo.reconcile_close_intents(
            project_id=scope.project_id,
            wp_id=scope.wp_id,
            entry_id=scope.entry_id,
            room_id=room_id,
            adapter_build_digest=adapter_build_digest,
            contributor_snapshot_digest=contributor_snapshot_digest,
        )
        assert_leader_matches_prediction(
            prediction=prediction,
            reported_leader_intent_id=outcome.leader_intent_id,
            reported_no_successor=outcome.no_successor,
            reported_stale_intent_ids=outcome.authorization_stale_intent_ids,
        )

        open_captures = await self._assert_at_most_one_open_capture(room_id, generation)
        live = await self._count_live_intents(room_id, generation)
        if outcome.no_successor:
            assert_no_live_intent_remains(
                live, room_id=room_id, generation=generation
            )

        dispatch: DispatchRecord | None = None
        if outcome.capture_created and outcome.promoted_request_id is not None:
            credential = await self._credential_for(
                outcome.promoted_request_id, cache_hit=not outcome.capture_created
            )
            command = await self._client.forcesave(
                credential,
                target=CommandTarget(
                    room_id=room.id,
                    generation=generation,
                    doc_key=room.doc_key,
                ),
            )
            dispatch = DispatchRecord(accepted=credential, dispatch=command)

        return CloseReconcileServiceOutcome(
            repository=outcome,
            prediction=prediction,
            open_capture_count=open_captures,
            live_intent_count=live,
            capture_dispatch=dispatch,
        )

    async def _snapshot(
        self, room_id: uuid.UUID, generation: int
    ) -> tuple[tuple[CloseIntentFacts, ...], Mapping[uuid.UUID, ParticipantFacts]]:
        """把 ORM 行投影成仲裁事实。

        `expired` 在这里就地判定成布尔而不是把 `expires_at` 传下去：让纯仲裁层
        彻底不接触任何时间值 —— 时间一旦进得去，「用 created_at 排序」就又变成
        一行代码的事（AC 4.10 明令禁止）。
        """
        now = _now()
        rows = (
            (
                await self._session.execute(
                    sa.select(WorkpaperOoCloseIntent)
                    .where(
                        WorkpaperOoCloseIntent.room_id == room_id,
                        WorkpaperOoCloseIntent.generation == generation,
                    )
                    .order_by(
                        WorkpaperOoCloseIntent.intent_sequence.desc(),
                        WorkpaperOoCloseIntent.id.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        parts = (
            (
                await self._session.execute(
                    sa.select(WorkpaperOoParticipant).where(
                        WorkpaperOoParticipant.room_id == room_id
                    )
                )
            )
            .scalars()
            .all()
        )
        participants = {
            p.id: ParticipantFacts(
                participant_id=p.id,
                state=ParticipantState(p.state),
                revoked=p.revoked_at is not None,
                expired=(p.expires_at is not None and p.expires_at <= now),
            )
            for p in parts
        }
        intents = tuple(
            CloseIntentFacts(
                intent_id=r.id,
                participant_id=r.participant_id,
                intent_sequence=int(r.intent_sequence),
                state=CloseIntentState(r.state),
            )
            for r in rows
        )
        return intents, participants

    async def _assert_at_most_one_open_capture(
        self, room_id: uuid.UUID, generation: int
    ) -> int:
        """真查库核对 open close-capture 条数（不信 outcome），再交纯函数裁决。"""
        count = int(
            (
                await self._session.execute(
                    sa.select(sa.func.count())
                    .select_from(WorkpaperForcesaveRequest)
                    .where(
                        WorkpaperForcesaveRequest.room_id == room_id,
                        WorkpaperForcesaveRequest.generation == generation,
                        WorkpaperForcesaveRequest.kind
                        == RequestKind.close_capture.value,
                        WorkpaperForcesaveRequest.state.in_(
                            sorted(s.value for s in OPEN_CAPTURE_STATES)
                        ),
                    )
                )
            ).scalar_one()
        )
        assert_at_most_one_open_capture(
            count, room_id=room_id, generation=generation
        )
        return count

    async def _count_live_intents(self, room_id: uuid.UUID, generation: int) -> int:
        return int(
            (
                await self._session.execute(
                    sa.select(sa.func.count())
                    .select_from(WorkpaperOoCloseIntent)
                    .where(
                        WorkpaperOoCloseIntent.room_id == room_id,
                        WorkpaperOoCloseIntent.generation == generation,
                        WorkpaperOoCloseIntent.state.in_(
                            sorted(s.value for s in CLOSE_INTENT_LIVE_STATES)
                        ),
                    )
                )
            ).scalar_one()
        )

    # ─────────────────────────────────────────────────────────────────
    # 4.3 promoted close-capture 的出站凭据
    # ─────────────────────────────────────────────────────────────────

    async def _credential_for(
        self, request_id: uuid.UUID, *, cache_hit: bool
    ) -> AcceptedRequest:
        """为 reconciler 已落库的 close-capture request 重建出站凭据。

        重建而不是让 reconciler 返回凭据：凭据的语义是「我**查过库**，shell 仍是
        pre-correlation 且零 application」（见 :class:`AcceptedRequest` 的 docstring）。
        由本层在出站前现查，才与「出站那一刻的库状态」对应上；
        让锁内的 reconciler 提前造一个凭据，等于把自证的时刻挪早。
        """
        request = (
            await self._session.execute(
                sa.select(WorkpaperForcesaveRequest).where(
                    WorkpaperForcesaveRequest.id == request_id
                )
            )
        ).scalar_one()
        operation = (
            await self._session.execute(
                sa.select(WorkpaperSyncOperation).where(
                    WorkpaperSyncOperation.forcesave_request_id == request_id
                )
            )
        ).scalar_one()
        app_count = int(
            (
                await self._session.execute(
                    sa.select(sa.func.count())
                    .select_from(WorkpaperContentApplication)
                    .where(WorkpaperContentApplication.origin_request_id == request_id)
                )
            ).scalar_one()
        )
        credential = AcceptedRequest(
            request=request,
            operation=operation,
            operation_shape=classify_operation_shape(
                application_id=operation.application_id,
                duplicate_of_operation_id=operation.duplicate_of_operation_id,
                state=operation.state,
            ),
            application_count=app_count,
            cache_hit=bool(cache_hit),
            request_sequence=int(request.request_sequence),
            frozen_request_fingerprint=str(request.frozen_request_fingerprint),
        )
        credential.assert_dispatchable()
        return credential


_ = RoomState  # 显式保留：room 终态枚举供调用方比对 supersede 结果，不做 re-export 门面
