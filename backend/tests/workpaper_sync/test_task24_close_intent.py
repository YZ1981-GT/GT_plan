# -*- coding: utf-8 -*-
"""Task 24 离线守卫：Command Service 出站分类、destroy 闸与 close-leader 纯仲裁。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 24
Requirements: 4.1, 4.4, 4.7, 4.10, 5.5, 10.10
Properties: **P12 / P13 / P15 / P43 / P64**

═══ 为什么这些判据必须离线、且必须用合成输入 ═══

Task 24 的行为面（exactly-one close-capture、leader/successor/no-successor）在真库上
由 `test_task24_close_intent_pg.py` discharge。但真库 happy path **走不到**下列分支：

* :func:`~.close_intent.assert_leader_matches_prediction` 的三条比对 —— 正确的
  reconciler 永不与预测分叉，所以「分叉时会不会抛、抛哪一个类型」只能喂构造输入；
* :func:`~.command_service.classify_editor_destroy` 的七个 verdict —— 真库里
  request 不会同时呈现七种状态；
* Command Service 的 error 1/2/3/5/6 —— OO 9.4 实测只在特定条件下返回，
  而契约要求全部七个返回码都有确定处置（AC 4.9「未知状态 fail visible」）。

「守卫不得断言真实数据仍有缺陷，要用合成输入证明分支覆盖」这条规矩正是为此。

═══ `parametrize` 一律带 `ids=` ═══

不带 `ids=` 时 nodeid 里是参数**位置**（`[case0]`），一旦增删用例，定向变异的
`want=` 就会指到别的用例上并被判 WRONG-TEST。凡被变异引用的 nodeid 都是接口。
"""
from __future__ import annotations

import ast
import json
import re
import sys
import uuid
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))

from app.models.workpaper_sync_models import (  # noqa: E402
    WorkpaperForcesaveRequest,
    WorkpaperSyncOperation,
)
from app.services.workpaper_sync import close_intent as ci  # noqa: E402
from app.services.workpaper_sync import command_service as cs  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    CloseIntentState,
    OperationState,
    ParticipantState,
    RequestKind,
    RequestState,
    classify_operation_shape,
)
from app.services.workpaper_sync.oo_contract import (  # noqa: E402
    CallbackContractError,
    load_callback_contract,
)
from app.services.workpaper_sync.request_application import (  # noqa: E402
    AcceptedRequest,
    ApplicationPrecreatedError,
)

_CLOSE_INTENT_SRC = _BACKEND / "app" / "services" / "workpaper_sync" / "close_intent.py"
_COMMAND_SRC = _BACKEND / "app" / "services" / "workpaper_sync" / "command_service.py"
_V151 = (
    _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"
)

_SECRET = "task24-test-secret"


# ═══════════════════════════════════════════════════════════════════════════
# 合成工具
# ═══════════════════════════════════════════════════════════════════════════
#
# id 刻意用固定字面量而不是 `uuid4()`：leader 仲裁的 tiebreak 就是 id 的大小，
# 随机 id 会让「最高 id 胜」这条断言时红时绿（而那种偶发红会被当成环境问题）。

_ID_LOW = uuid.UUID("11111111-1111-4111-8111-111111111111")
_ID_MID = uuid.UUID("88888888-8888-4888-8888-888888888888")
_ID_HIGH = uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")


def _participant(
    pid: uuid.UUID,
    *,
    state: ParticipantState = ParticipantState.closing,
    revoked: bool = False,
    expired: bool = False,
) -> ci.ParticipantFacts:
    return ci.ParticipantFacts(
        participant_id=pid, state=state, revoked=revoked, expired=expired
    )


def _intent(
    *,
    intent_id: uuid.UUID,
    participant_id: uuid.UUID,
    sequence: int,
    state: CloseIntentState = CloseIntentState.created,
) -> ci.CloseIntentFacts:
    return ci.CloseIntentFacts(
        intent_id=intent_id,
        participant_id=participant_id,
        intent_sequence=sequence,
        state=state,
    )


def _credential(
    *,
    room_id: uuid.UUID | None = None,
    generation: int = 1,
    participant_id: uuid.UUID | None = None,
    application_id: uuid.UUID | None = None,
    application_count: int = 0,
    state: OperationState = OperationState.accepted,
) -> AcceptedRequest:
    """合成一个 :class:`AcceptedRequest`（不入库；只用于出站前的形态判据）。"""
    room = room_id if room_id is not None else _ID_MID
    request = WorkpaperForcesaveRequest(
        id=uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001"),
        room_id=room,
        generation=generation,
        kind=RequestKind.forcesave.value,
        initiated_by_participant_id=participant_id,
        request_sequence=7,
        frozen_request_fingerprint="f" * 64,
    )
    operation = WorkpaperSyncOperation(
        id=uuid.UUID("bbbbbbbb-0000-4000-8000-000000000001"),
        application_id=application_id,
        duplicate_of_operation_id=None,
        state=state.value,
    )
    return AcceptedRequest(
        request=request,
        operation=operation,
        operation_shape=classify_operation_shape(
            application_id=application_id,
            duplicate_of_operation_id=None,
            state=state,
        ),
        application_count=application_count,
        cache_hit=False,
        request_sequence=7,
        frozen_request_fingerprint="f" * 64,
    )


class _RecordingTransport:
    """可编程 stand-in transport。

    真实 OO 9.4 的端到端验收是 Task 44/70；本任务用它把七个返回码、非 200、
    坏 JSON 与「出站前就该被拒」四类形态全部变成确定性判据。
    `calls` 让「本该在网络之前拒掉的请求，是不是真的没发出去」可断言 ——
    只断言抛了异常无法区分「拒在出站前」与「发出去了才失败」。
    """

    def __init__(self, *, status: int = 200, body: Any = None, text: str | None = None):
        self.status = status
        self.body = body if body is not None else {"error": 0}
        self.text = text
        self.calls: list[cs.CommandRequest] = []

    async def post(self, request: cs.CommandRequest) -> cs.CommandResponse:
        self.calls.append(request)
        payload = self.text if self.text is not None else json.dumps(self.body)
        return cs.CommandResponse(status_code=int(self.status), text=payload)


def _client(transport: _RecordingTransport) -> cs.CommandServiceClient:
    return cs.CommandServiceClient(
        onlyoffice_url="http://oo.internal:8080",
        jwt_secret=_SECRET,
        transport=transport,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 一、纯仲裁：最高 (intent_sequence, id)，`created_at` 不可表达
# ═══════════════════════════════════════════════════════════════════════════


def test_arbitration_input_type_carries_no_timestamp_field() -> None:
    """:class:`~.close_intent.CloseIntentFacts` 不得有任何时间字段。

    这是「`created_at` 只作审计、禁止参与仲裁」在类型层的落法。断言字段名清单
    而不是「没写 created_at」：`reconciled_at` / `finished_at` / 任何 `*_at`
    进来都同样打开了按时间排序的门。
    """
    names = {f.name for f in dataclass_fields(ci.CloseIntentFacts)}
    assert names == {"intent_id", "participant_id", "intent_sequence", "state"}, names
    timeish = sorted(n for n in names if n.endswith("_at") or "time" in n)
    assert timeish == [], f"仲裁输入类型出现时间字段 {timeish} —— created_at 禁止参与仲裁"


def test_leader_is_highest_sequence_even_when_it_is_neither_first_nor_last_inserted() -> None:
    """判别性输入：最高 `(intent_sequence, id)` 者**既不是第一条也不是最后一条**。

    🔴 这条是本任务最关键的离线判据。若三条 intent 的「插入顺序 / sequence / id 大小」
    三者同序，那么 `max by (seq,id)`、`min by id`、`第一条`、`最后一条` 会给出同一个
    答案 —— 于是 comparator 怎么改都测不出来（Task 23 的第一版竞态就是这个形态：
    断言全过，而 fold 分支一次都没执行）。

    这里刻意让三者错位：
        插入序 A(seq=2,id=HIGH) → B(seq=5,id=LOW) → C(seq=3,id=MID)
    最高 sequence 是 B（第 2 个插入，既非首也非尾），而 B 的 id 是**最小**的 ——
    所以「按 id 排序」「按插入序取首/取尾」三种错法都会选错。
    """
    pa, pb, pc = _ID_LOW, _ID_MID, _ID_HIGH
    a = _intent(intent_id=_ID_HIGH, participant_id=pa, sequence=2)
    b = _intent(intent_id=_ID_LOW, participant_id=pb, sequence=5)
    c = _intent(intent_id=_ID_MID, participant_id=pc, sequence=3)
    rows = [a, b, c]
    parts = {pa: _participant(pa), pb: _participant(pb), pc: _participant(pc)}

    leader = ci.select_close_leader(rows)
    assert leader is not None and leader.intent_id == b.intent_id, leader
    assert leader is not rows[0] and leader is not rows[-1], "判别性丧失：leader 是首/尾"
    assert leader.intent_id != max(r.intent_id for r in rows), "判别性丧失：leader 恰是最大 id"

    prediction = ci.predict_close_leader(rows, parts, current_leader_intent_id=None)
    assert prediction.leader_intent_id == b.intent_id
    assert prediction.no_successor is False
    assert prediction.expected_stale_intent_ids == ()


def test_leader_is_invariant_under_input_order_permutations() -> None:
    """六种排列下 leader 不变（插入顺序扰动不得换 leader）。"""
    pa, pb, pc = _ID_LOW, _ID_MID, _ID_HIGH
    rows = [
        _intent(intent_id=_ID_HIGH, participant_id=pa, sequence=2),
        _intent(intent_id=_ID_LOW, participant_id=pb, sequence=5),
        _intent(intent_id=_ID_MID, participant_id=pc, sequence=3),
    ]
    parts = {pa: _participant(pa), pb: _participant(pb), pc: _participant(pc)}
    import itertools

    seen = {
        ci.predict_close_leader(
            list(perm), parts, current_leader_intent_id=None
        ).leader_intent_id
        for perm in itertools.permutations(rows)
    }
    assert seen == {_ID_LOW}, seen


def test_equal_sequence_falls_back_to_highest_id() -> None:
    """sequence 相等时由 id tiebreak 决定 —— 且必须取**最高** id。

    单独一条的理由：真库里 `intent_sequence` 由 `max+1` 生成，永不相等，所以
    tiebreak 分支在真实数据上**不可达**。丢掉 `str(i.id)` 这一项的变异不会被任何
    真库场景抓到 —— 只有这条合成断言能。
    """
    pa, pb = _ID_LOW, _ID_MID
    rows = [
        _intent(intent_id=_ID_LOW, participant_id=pa, sequence=9),
        _intent(intent_id=_ID_HIGH, participant_id=pb, sequence=9),
    ]
    leader = ci.select_close_leader(rows)
    assert leader is not None and leader.intent_id == _ID_HIGH, leader
    assert ci.close_leader_sort_key(rows[1]) > ci.close_leader_sort_key(rows[0])


def test_sort_key_string_order_matches_postgres_uuid_byte_order() -> None:
    """`str(uuid)` 字典序必须与 PG `uuid` 字节序同序。

    双记账的前提：Python 侧预测用 `str(id)`，SQL 侧 `ORDER BY id DESC` 用字节序。
    两者若不同序，tiebreak 会偶发分叉 —— 表现为随机的仲裁告警（CI 重试的来源）。
    这里对同一批 UUID 用「16 字节序」与「canonical 字符串序」各排一次并比对。
    """
    samples = [
        uuid.UUID("00000000-0000-4000-8000-000000000000"),
        uuid.UUID("0f000000-0000-4000-8000-000000000000"),
        uuid.UUID("10000000-0000-4000-8000-000000000000"),
        uuid.UUID("a0000000-0000-4000-8000-000000000000"),
        uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"),
        _ID_LOW,
        _ID_MID,
    ]
    by_bytes = sorted(samples, key=lambda u: u.bytes)
    by_text = sorted(samples, key=str)
    assert by_bytes == by_text, (by_bytes, by_text)


@pytest.mark.parametrize(
    ("label", "participant", "intent_state", "expected"),
    [
        ("closing_live", _participant(_ID_LOW), CloseIntentState.created, True),
        (
            "revoked",
            _participant(_ID_LOW, revoked=True),
            CloseIntentState.created,
            False,
        ),
        (
            "expired",
            _participant(_ID_LOW, expired=True),
            CloseIntentState.created,
            False,
        ),
        (
            "still_active",
            _participant(_ID_LOW, state=ParticipantState.active),
            CloseIntentState.created,
            False,
        ),
        (
            "left",
            _participant(_ID_LOW, state=ParticipantState.left),
            CloseIntentState.created,
            False,
        ),
        (
            "terminal_intent",
            _participant(_ID_LOW),
            CloseIntentState.authorization_stale,
            False,
        ),
        (
            "promoted_intent",
            _participant(_ID_LOW),
            CloseIntentState.promoted,
            False,
        ),
    ],
    ids=[
        "closing_live",
        "revoked",
        "expired",
        "still_active",
        "left",
        "terminal_intent",
        "promoted_intent",
    ],
)
def test_eligibility_has_one_independent_branch_per_disqualifier(
    label: str,
    participant: ci.ParticipantFacts,
    intent_state: CloseIntentState,
    expected: bool,
) -> None:
    """失格的每一种方式各一条用例。

    合成一条 `all([...])` 时，删掉任一子判据都会被其余遮蔽 ⇒ 定向变异判 GREEN。
    """
    intent = _intent(
        intent_id=_ID_MID, participant_id=_ID_LOW, sequence=1, state=intent_state
    )
    assert ci.intent_is_eligible(intent, {_ID_LOW: participant}) is expected, label


def test_missing_participant_is_not_eligible() -> None:
    """intent 指向的 participant 不在本 room 快照里 ⇒ 不合格（而不是 KeyError）。"""
    intent = _intent(intent_id=_ID_MID, participant_id=_ID_HIGH, sequence=1)
    assert ci.intent_is_eligible(intent, {}) is False


def test_promoted_short_circuit_precedes_staleness_check() -> None:
    """已 promoted ⇒ 幂等短路，**不再**选 successor（AC 10.10）。

    构造上让「若继续走失格分支就会选出另一个 successor」：promoted 的那条
    participant 已被撤销，且另有一条合格 intent。正确行为是返回 promoted 那条、
    零 stale、no_successor=False。
    """
    pa, pb = _ID_LOW, _ID_MID
    promoted = _intent(
        intent_id=_ID_HIGH,
        participant_id=pa,
        sequence=9,
        state=CloseIntentState.promoted,
    )
    other = _intent(intent_id=_ID_LOW, participant_id=pb, sequence=3)
    parts = {pa: _participant(pa, revoked=True), pb: _participant(pb)}
    pred = ci.predict_close_leader(
        [promoted, other], parts, current_leader_intent_id=_ID_HIGH
    )
    assert pred.promoted_short_circuit is True
    assert pred.leader_intent_id == _ID_HIGH
    assert pred.expected_stale_intent_ids == ()
    assert pred.no_successor is False


def test_stale_leader_yields_successor_by_the_same_comparator() -> None:
    """leader 失格 ⇒ 记 stale，并从仍合法 intents 里按**同一** comparator 选 successor。"""
    pa, pb, pc = _ID_LOW, _ID_MID, _ID_HIGH
    leader = _intent(intent_id=_ID_HIGH, participant_id=pb, sequence=9)
    lower = _intent(intent_id=_ID_MID, participant_id=pa, sequence=4)
    lowest = _intent(intent_id=_ID_LOW, participant_id=pc, sequence=6)
    parts = {
        pa: _participant(pa),
        pb: _participant(pb, revoked=True),
        pc: _participant(pc),
    }
    pred = ci.predict_close_leader(
        [leader, lowest, lower], parts, current_leader_intent_id=_ID_HIGH
    )
    assert pred.expected_stale_intent_ids == (_ID_HIGH,)
    # successor 必须是剩余里 sequence 最高的那条（6 > 4），不是 id 最大的那条
    assert pred.leader_intent_id == _ID_LOW
    assert pred.no_successor is False


def test_no_successor_is_distinct_from_no_intents_at_all() -> None:
    """「一条 intent 都没有」≠「有 intent 但全部失格」。

    两者都返回 `leader=None`，但只有后者才该 supersede generation 并落
    `recovery_required`。合成一个 `leader is None` 判据会把「还没人关闭」的 room
    也 supersede 掉。
    """
    empty = ci.predict_close_leader([], {}, current_leader_intent_id=None)
    assert empty.empty is True and empty.no_successor is False

    pa = _ID_LOW
    all_stale = ci.predict_close_leader(
        [_intent(intent_id=_ID_MID, participant_id=pa, sequence=1)],
        {pa: _participant(pa, revoked=True)},
        current_leader_intent_id=None,
    )
    assert all_stale.empty is False and all_stale.no_successor is True
    assert all_stale.leader_intent_id is None


# ═══════════════════════════════════════════════════════════════════════════
# 二、双记账比对：三条分歧各自分型
# ═══════════════════════════════════════════════════════════════════════════


def _prediction(
    *,
    leader: uuid.UUID | None = _ID_HIGH,
    no_successor: bool = False,
    stale: tuple[uuid.UUID, ...] = (),
) -> ci.LeaderPrediction:
    return ci.LeaderPrediction(
        leader_intent_id=leader,
        eligible_intent_ids=(_ID_HIGH, _ID_LOW),
        expected_stale_intent_ids=stale,
        no_successor=no_successor,
        promoted_short_circuit=False,
        empty=False,
    )


def test_matching_report_passes() -> None:
    """一致时不抛 —— 反向自检：否则下面三条「不一致必抛」可能只是恒抛。"""
    ci.assert_leader_matches_prediction(
        prediction=_prediction(stale=(_ID_LOW,)),
        reported_leader_intent_id=_ID_HIGH,
        reported_no_successor=False,
        reported_stale_intent_ids=[_ID_LOW],
    )


def test_leader_mismatch_raises_arbitration_error() -> None:
    with pytest.raises(ci.CloseLeaderArbitrationError):
        ci.assert_leader_matches_prediction(
            prediction=_prediction(),
            reported_leader_intent_id=_ID_LOW,
            reported_no_successor=False,
            reported_stale_intent_ids=[],
        )


def test_no_successor_mismatch_raises_accounting_error() -> None:
    """有 successor 却报 no_successor（或反之）⇒ **accounting** 而非 arbitration。"""
    with pytest.raises(ci.CloseSuccessorAccountingError):
        ci.assert_leader_matches_prediction(
            prediction=_prediction(leader=None, no_successor=True),
            reported_leader_intent_id=None,
            reported_no_successor=False,
            reported_stale_intent_ids=[],
        )


def test_missing_authorization_stale_raises_accounting_error() -> None:
    """leader 选对了但漏写 `authorization_stale` 审计 ⇒ 必须独立可见。

    🔴 这条与上面两条**共同**证明三项比对互不遮蔽：若三者共用一个异常类型，
    「漏写 stale」的定向变异会被「leader 选错」那条断言吃掉而判 GREEN
    （本 spec 已在 Task 22 M04/M10、Task 23 M25 上付过三次代价）。
    """
    with pytest.raises(ci.CloseSuccessorAccountingError):
        ci.assert_leader_matches_prediction(
            prediction=_prediction(stale=(_ID_LOW,)),
            reported_leader_intent_id=_ID_HIGH,
            reported_no_successor=False,
            reported_stale_intent_ids=[],
        )


def test_close_intent_refusals_are_pairwise_disjoint() -> None:
    names = ci.assert_refusals_are_disjoint()
    assert len(names) == 5, names
    assert not issubclass(ci.CloseLeaderArbitrationError, ci.CloseSuccessorAccountingError)
    assert not issubclass(ci.CloseSuccessorAccountingError, ci.CloseLeaderArbitrationError)
    assert not issubclass(ci.CloseCaptureNotUniqueError, ci.CloseIntentPermanentlyBlockedError)
    assert not issubclass(ci.CloseIntentPermanentlyBlockedError, ci.CloseCaptureNotUniqueError)


def test_command_service_refusals_are_pairwise_disjoint() -> None:
    names = cs.assert_refusals_are_disjoint()
    assert len(names) == 6, names
    assert not issubclass(cs.CommandServiceProtocolError, cs.UnknownCommandReturnCodeError)
    assert not issubclass(cs.UnknownCommandReturnCodeError, cs.CommandServiceProtocolError)
    assert not issubclass(cs.CommandServiceCredentialError, cs.CommandServiceTargetMismatchError)
    assert not issubclass(cs.CommandServiceTargetMismatchError, cs.CommandServiceCredentialError)


# ═══════════════════════════════════════════════════════════════════════════
# 三、契约投影：返回码真值表与超时单一真源
# ═══════════════════════════════════════════════════════════════════════════


def test_every_contract_return_code_has_a_closed_outcome() -> None:
    """七个返回码全部有机器可读处置，且 accepted ⇔ 期待 callback。"""
    policy = cs.load_command_service_policy(force=True)
    assert policy.known_codes == (0, 1, 2, 3, 4, 5, 6), policy.known_codes
    for code, rule in policy.codes.items():
        assert isinstance(rule.outcome, cs.CommandOutcome)
        assert rule.callback_expected is (rule.outcome is cs.CommandOutcome.accepted), code
    assert policy.codes[0].outcome is cs.CommandOutcome.accepted
    assert policy.codes[4].outcome is cs.CommandOutcome.no_changes
    assert policy.codes[3].retryable is True, "error 3 契约明写「可重试；保持 OO 模式」"
    assert policy.codes[4].retryable is False


def test_only_retryable_free_no_callback_codes_are_terminal_without_callback() -> None:
    """`terminal_without_callback` ≠ `not callback_expected`。

    error 3 也没有 callback，但可重试 ⇒ request 不得就地终结（契约「保持 OO 模式」）。
    把两者当同义词会让可重试错误被读成「已终结，放心走」，内容随之丢失。
    """
    policy = cs.load_command_service_policy()
    assert policy.codes[3].terminal_without_callback is False
    assert policy.codes[4].terminal_without_callback is True
    assert policy.codes[0].terminal_without_callback is False


def test_timers_come_from_oo_contract_not_a_second_parse() -> None:
    policy = cs.load_command_service_policy()
    cs.assert_timer_single_source(policy)
    assert policy.timers is not None
    assert policy.timers == load_callback_contract().timers


def test_command_service_module_does_not_reparse_timers() -> None:
    """源码判据：本模块不得自己解析 `timers` 小节。

    行为判据（:func:`~.command_service.assert_timer_single_source`）只能证明
    「这次两边等值」；抄一份解析且抄对了，行为判据仍然是绿的。两条一起才是
    「单一真源」。
    """
    tree = ast.parse(_COMMAND_SRC.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in (
            "timers",
            "delivery_ttl",
            "forcesave_callback_wait_timeout_seconds",
            "in_flight_grace_seconds",
            "command_service_http_timeout_seconds",
        ):
            offenders.append(str(node.value))
    assert offenders == [], (
        f"command_service.py 出现 timers 小节的字面量键 {sorted(set(offenders))} —— "
        "超时只能取自 oo_contract 的 Timers，不得在本模块另解析一份"
    )


def test_open_capture_states_are_locked_to_the_sql_index() -> None:
    """`OPEN_CAPTURE_STATES` 与 V151 partial unique 的 WHERE 子句双向锁死。

    真源本来有三处（SQL / 仓储常量 / 本模块）。本模块那份已经改成 import 仓储的
    常量（不再是第三份），这里把剩下两处对齐 —— 在此之前**没有任何守卫**比较过
    SQL 的 `state IN (...)` 与 Python 的元组，两边可以各自漂移。
    """
    sql = _V151.read_text(encoding="utf-8")
    m = re.search(
        r"uq_wpfr_open_close_capture.*?WHERE\s+kind\s*=\s*'close_capture'\s+AND\s+state\s+IN\s*\(([^)]*)\)",
        sql,
        re.S,
    )
    assert m is not None, "V151 里找不到 uq_wpfr_open_close_capture 的 WHERE 子句"
    sql_states = {s.strip().strip("'") for s in m.group(1).split(",") if s.strip()}
    python_states = {s.value for s in ci.OPEN_CAPTURE_STATES}
    assert sql_states == python_states, (sql_states, python_states)
    # 反向自检：这些状态必须真的都是「非终态」（有出边），否则「open」名不副实
    from app.services.workpaper_sync.models import is_terminal

    assert all(not is_terminal("request", RequestState(s)) for s in python_states)


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("jwt_not_required", lambda d: d["command_service"]["jwt"].update({"required": False})),
        (
            "http_status_declared_meaningful",
            lambda d: d["command_service"]["http_semantics"].update(
                {"http_status_always_200_even_on_error": False}
            ),
        ),
        (
            "unknown_platform_outcome",
            lambda d: d["command_service"]["return_codes"][0].update(
                {"platform_outcome": "probably_fine"}
            ),
        ),
        (
            "accepted_without_callback",
            lambda d: d["command_service"]["return_codes"][0].update(
                {"callback_expected": False}
            ),
        ),
        (
            "ambiguous_claim_shape",
            lambda d: d["command_service"]["jwt"].update({"platform_rule": "随便哪种都行"}),
        ),
        (
            "missing_retryable",
            lambda d: d["command_service"]["return_codes"][5].pop("retryable"),
        ),
    ],
    ids=[
        "jwt_not_required",
        "http_status_declared_meaningful",
        "unknown_platform_outcome",
        "accepted_without_callback",
        "ambiguous_claim_shape",
        "missing_retryable",
    ],
)
def test_contract_defects_fail_closed(
    tmp_path: Path, label: str, mutate: Any
) -> None:
    """契约本身出问题时 fail closed，绝不回退到默认值。"""
    raw = json.loads(
        (_BACKEND / "data" / "onlyoffice_callback_state_contract.json").read_text(
            encoding="utf-8"
        )
    )
    mutate(raw)
    target = tmp_path / "contract.json"
    target.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CallbackContractError):
        cs.load_command_service_policy(target, force=True)


# ═══════════════════════════════════════════════════════════════════════════
# 四、出站：HTTP 200 只代表 accepted，且落库先于出站
# ═══════════════════════════════════════════════════════════════════════════


def test_dispatch_result_exposes_no_success_or_saved_flag() -> None:
    """:class:`~.command_service.CommandDispatch` 不得有「成功/已保存」字段。

    AC 4.1 末句禁止把 HTTP 200 当保存完成。只要回执上有一个布尔叫 success/saved，
    调用点就会拿它当完成信号 —— 所以判据落在**字段名清单**上。
    """
    names = {f.name for f in dataclass_fields(cs.CommandDispatch)}
    banned = sorted(
        n
        for n in names
        if any(k in n for k in ("saved", "success", "applied", "durable", "complete"))
    )
    assert banned == [], f"回执出现完成语义字段 {banned}"
    props = {
        n
        for n in dir(cs.CommandDispatch)
        if isinstance(getattr(cs.CommandDispatch, n, None), property)
    }
    assert "accepted" in props and "awaits_callback" in props
    assert not (props & {"saved", "success", "applied", "is_complete"})


@pytest.mark.asyncio
async def test_error_zero_marks_accepted_only() -> None:
    transport = _RecordingTransport(body={"error": 0})
    dispatch = await _client(transport).forcesave(
        _credential(participant_id=_ID_LOW),
        target=cs.CommandTarget(room_id=_ID_MID, generation=1, doc_key="dk-1"),
    )
    assert dispatch.outcome is cs.CommandOutcome.accepted
    assert dispatch.accepted is True and dispatch.awaits_callback is True
    assert dispatch.http_status == 200
    assert dispatch.terminal_without_callback is False


@pytest.mark.parametrize(
    ("error", "outcome", "accepted", "retryable"),
    [
        (1, cs.CommandOutcome.doc_not_online, False, False),
        (2, cs.CommandOutcome.configuration_error, False, False),
        (3, cs.CommandOutcome.server_error, False, True),
        (4, cs.CommandOutcome.no_changes, False, False),
        (5, cs.CommandOutcome.implementation_defect, False, False),
        (6, cs.CommandOutcome.configuration_error, False, False),
    ],
    ids=["error1", "error2", "error3", "error4", "error5", "error6"],
)
@pytest.mark.asyncio
async def test_http_200_with_nonzero_error_is_never_accepted(
    error: int, outcome: cs.CommandOutcome, accepted: bool, retryable: bool
) -> None:
    """HTTP 200 + body error≠0 ⇒ 一律不是 accepted（契约 http_semantics）。"""
    transport = _RecordingTransport(status=200, body={"error": error})
    dispatch = await _client(transport).forcesave(
        _credential(participant_id=_ID_LOW),
        target=cs.CommandTarget(room_id=_ID_MID, generation=1, doc_key="dk-1"),
    )
    assert dispatch.http_status == 200
    assert dispatch.outcome is outcome
    assert dispatch.accepted is accepted
    assert dispatch.retryable is retryable
    assert dispatch.awaits_callback is False


@pytest.mark.asyncio
async def test_non_200_is_a_transport_failure_not_a_return_code() -> None:
    """非 200 ⇒ 请求没到 OO（网关/代理），不得按返回码语义处理。"""
    transport = _RecordingTransport(status=502, body={"error": 0})
    with pytest.raises(cs.CommandServiceTransportError):
        await _client(transport).forcesave(
            _credential(participant_id=_ID_LOW),
            target=cs.CommandTarget(room_id=_ID_MID, generation=1, doc_key="dk-1"),
        )


@pytest.mark.parametrize(
    ("label", "text", "expected"),
    [
        ("not_json", "<html>502 Bad Gateway</html>", cs.CommandServiceProtocolError),
        ("json_array", "[0]", cs.CommandServiceProtocolError),
        ("missing_error_key", '{"ok": true}', cs.CommandServiceProtocolError),
        ("error_is_string", '{"error": "0"}', cs.UnknownCommandReturnCodeError),
        ("error_is_bool", '{"error": true}', cs.UnknownCommandReturnCodeError),
        ("error_unlisted", '{"error": 99}', cs.UnknownCommandReturnCodeError),
    ],
    ids=[
        "not_json",
        "json_array",
        "missing_error_key",
        "error_is_string",
        "error_is_bool",
        "error_unlisted",
    ],
)
@pytest.mark.asyncio
async def test_unreadable_or_unknown_return_code_fails_visible(
    label: str, text: str, expected: type[Exception]
) -> None:
    """读不出 error / 读出但未登记 ⇒ 各自分型，均 fail visible，不得默认成功。"""
    transport = _RecordingTransport(status=200, text=text)
    with pytest.raises(expected):
        await _client(transport).forcesave(
            _credential(participant_id=_ID_LOW),
            target=cs.CommandTarget(room_id=_ID_MID, generation=1, doc_key="dk-1"),
        )


@pytest.mark.asyncio
async def test_non_credential_argument_is_refused_before_any_network_call() -> None:
    """不是 :class:`AcceptedRequest` ⇒ 拒在出站之前（AC 4.1 的顺序）。

    断言 `transport.calls == []`：只断言抛异常无法区分「拒在出站前」与
    「发出去了才失败」，而 AC 4.1 管的正是前者。
    """
    transport = _RecordingTransport()
    with pytest.raises(cs.CommandServiceCredentialError):
        await _client(transport).forcesave(
            object(),  # type: ignore[arg-type]
            target=cs.CommandTarget(room_id=_ID_MID, generation=1, doc_key="dk-1"),
        )
    assert transport.calls == []


@pytest.mark.asyncio
async def test_precreated_application_is_refused_before_any_network_call() -> None:
    """凭据自证失败（库里已有 application）⇒ 出站前拒（Property 12 / P64）。"""
    transport = _RecordingTransport()
    with pytest.raises(ApplicationPrecreatedError):
        await _client(transport).forcesave(
            _credential(participant_id=_ID_LOW, application_count=1),
            target=cs.CommandTarget(room_id=_ID_MID, generation=1, doc_key="dk-1"),
        )
    assert transport.calls == []


@pytest.mark.asyncio
async def test_bound_shell_is_refused_before_any_network_call() -> None:
    """shell 已绑定 application（不是 pre-correlation）⇒ 出站前拒。"""
    transport = _RecordingTransport()
    with pytest.raises(ApplicationPrecreatedError):
        await _client(transport).forcesave(
            _credential(
                participant_id=_ID_LOW,
                application_id=uuid.UUID("cccccccc-0000-4000-8000-000000000001"),
            ),
            target=cs.CommandTarget(room_id=_ID_MID, generation=1, doc_key="dk-1"),
        )
    assert transport.calls == []


@pytest.mark.parametrize(
    ("label", "room", "generation"),
    [
        ("other_room", _ID_HIGH, 1),
        ("other_generation", _ID_MID, 2),
    ],
    ids=["other_room", "other_generation"],
)
@pytest.mark.asyncio
async def test_target_must_belong_to_the_frozen_request_generation(
    label: str, room: uuid.UUID, generation: int
) -> None:
    """doc_key 与凭据里的 request 必须同 room 代际，否则拒在出站之前。"""
    transport = _RecordingTransport()
    with pytest.raises(cs.CommandServiceTargetMismatchError):
        await _client(transport).forcesave(
            _credential(room_id=_ID_MID, generation=1, participant_id=_ID_LOW),
            target=cs.CommandTarget(room_id=room, generation=generation, doc_key="dk"),
        )
    assert transport.calls == []


@pytest.mark.asyncio
async def test_null_initiator_is_refused_before_the_command_service_call() -> None:
    """null initiator ⇒ 出站前拒（AC 10.10：system/route identity 不可替代用户授权）。"""
    transport = _RecordingTransport()
    with pytest.raises(cs.CommandServiceCredentialError):
        await _client(transport).forcesave(
            _credential(participant_id=None),
            target=cs.CommandTarget(room_id=_ID_MID, generation=1, doc_key="dk-1"),
        )
    assert transport.calls == []


@pytest.mark.asyncio
async def test_outbound_request_carries_doc_key_request_id_and_signed_short_ttl_jwt() -> None:
    """出站请求形态：`c=forcesave` + doc_key + userdata(request id) + 短 TTL 签名。"""
    from jose import jwt as jose_jwt

    transport = _RecordingTransport(body={"error": 0})
    client = _client(transport)
    credential = _credential(participant_id=_ID_LOW)
    await client.forcesave(
        credential,
        target=cs.CommandTarget(room_id=_ID_MID, generation=1, doc_key="dk-42"),
    )
    assert len(transport.calls) == 1
    sent = transport.calls[0]
    assert sent.body["c"] == "forcesave"
    assert sent.body["key"] == "dk-42"
    assert str(credential.request.id) in sent.body["userdata"]
    assert sent.url.endswith("/coauthoring/CommandService.ashx")
    timers = load_callback_contract().timers
    assert sent.timeout_seconds == float(timers.command_service_http_timeout_seconds)

    header = sent.headers[client.policy.jwt_header]
    assert header.startswith(client.policy.jwt_scheme + " ")
    claims = jose_jwt.decode(
        header.split(" ", 1)[1], _SECRET, algorithms=["HS256"], options={"verify_aud": False}
    )
    # 契约 platform_rule 点名 payload_wrapped ⇒ body 必须整体进 `payload`
    assert claims["payload"]["key"] == "dk-42"
    assert claims["exp"] - claims["iat"] == timers.command_service_http_timeout_seconds


def test_missing_jwt_secret_fails_closed_instead_of_signing_nothing() -> None:
    """无 secret ⇒ 拒绝，绝不像旧实现那样返回空 token（鉴权降级成可选）。"""
    with pytest.raises(cs.CommandServiceConfigError):
        cs.sign_command_token(
            secret="", body={"c": "forcesave"}, ttl_seconds=10, claim_shape="payload_wrapped"
        )


def test_non_positive_ttl_is_refused() -> None:
    with pytest.raises(cs.CommandServiceConfigError):
        cs.sign_command_token(
            secret=_SECRET, body={}, ttl_seconds=0, claim_shape="payload_wrapped"
        )


def test_empty_onlyoffice_url_is_refused_instead_of_defaulting() -> None:
    policy = cs.load_command_service_policy()
    with pytest.raises(cs.CommandServiceConfigError):
        policy.endpoint("   ")


def test_empty_doc_key_is_unrepresentable() -> None:
    with pytest.raises(cs.CommandServiceTargetMismatchError):
        cs.CommandTarget(room_id=_ID_MID, generation=1, doc_key="")


# ═══════════════════════════════════════════════════════════════════════════
# 五、destroy 闸 / 超时保持 OO（Property 13 / AC 4.4）
# ═══════════════════════════════════════════════════════════════════════════


def _facts(
    *,
    state: RequestState = RequestState.accepted,
    outcome: cs.CommandOutcome | None = cs.CommandOutcome.accepted,
    waited: float = 1.0,
) -> cs.DestroyRequestFacts:
    return cs.DestroyRequestFacts(
        request_id=_ID_LOW, state=state, outcome=outcome, waited_seconds=waited
    )


@pytest.mark.parametrize(
    ("label", "req", "incoming_durable", "recovery_open", "verdict", "keep_oo", "reload_ok"),
    [
        (
            "terminal_allows_destroy",
            _facts(state=RequestState.terminal),
            False,
            False,
            cs.DestroyVerdict.allowed_request_terminal,
            False,
            True,
        ),
        (
            "no_changes_allows_leave",
            _facts(state=RequestState.accepted, outcome=cs.CommandOutcome.no_changes),
            False,
            False,
            cs.DestroyVerdict.allowed_no_changes,
            False,
            True,
        ),
        (
            "open_request_keeps_oo",
            _facts(state=RequestState.accepted, waited=1.0),
            False,
            False,
            cs.DestroyVerdict.refused_request_open,
            True,
            False,
        ),
        (
            "timeout_keeps_oo",
            _facts(state=RequestState.accepted, waited=999.0),
            False,
            False,
            cs.DestroyVerdict.refused_timeout_keep_oo,
            True,
            False,
        ),
        (
            "retryable_keeps_oo",
            _facts(state=RequestState.accepted, outcome=cs.CommandOutcome.server_error),
            False,
            False,
            cs.DestroyVerdict.refused_retryable_error,
            True,
            False,
        ),
        (
            "crash_with_durable_incoming_allows_recovery",
            None,
            True,
            True,
            cs.DestroyVerdict.allowed_recovery_case,
            False,
            False,
        ),
        (
            "crash_without_durable_incoming_refused",
            None,
            False,
            False,
            cs.DestroyVerdict.refused_no_request_no_incoming,
            True,
            False,
        ),
        (
            "crash_durable_but_no_case_refused",
            None,
            True,
            False,
            cs.DestroyVerdict.refused_no_request_no_incoming,
            True,
            False,
        ),
    ],
    ids=[
        "terminal_allows_destroy",
        "no_changes_allows_leave",
        "open_request_keeps_oo",
        "timeout_keeps_oo",
        "retryable_keeps_oo",
        "crash_with_durable_incoming_allows_recovery",
        "crash_without_durable_incoming_refused",
        "crash_durable_but_no_case_refused",
    ],
)
def test_editor_destroy_gate_branches(
    label: str,
    req: cs.DestroyRequestFacts | None,
    incoming_durable: bool,
    recovery_open: bool,
    verdict: cs.DestroyVerdict,
    keep_oo: bool,
    reload_ok: bool,
) -> None:
    """七个 verdict 各一条用例，且逐条断言两个前端布尔。"""
    decision = cs.classify_editor_destroy(
        request=req,
        incoming_durable=incoming_durable,
        recovery_case_open=recovery_open,
        timers=load_callback_contract().timers,
    )
    assert decision.verdict is verdict, (label, decision)
    assert decision.keep_onlyoffice is keep_oo, label
    assert decision.reload_html_allowed is reload_ok, label
    assert decision.allowed is verdict.value.startswith("allowed_"), label


def test_timeout_never_permits_reload_html() -> None:
    """Property 13：超时后 mode 仍是 OO 且 reloadHtml 不被允许。

    单独一条（不并入上面的矩阵）：Property 13 是被 Task 24 正文点名的验收项，
    定向变异需要一个稳定的 nodeid 指向它。
    """
    timers = load_callback_contract().timers
    decision = cs.classify_editor_destroy(
        request=_facts(
            state=RequestState.accepted,
            waited=float(timers.forcesave_callback_wait_timeout_seconds),
        ),
        incoming_durable=False,
        recovery_case_open=False,
        timers=timers,
    )
    assert decision.verdict is cs.DestroyVerdict.refused_timeout_keep_oo
    assert decision.keep_onlyoffice is True
    assert decision.reload_html_allowed is False
    assert decision.allowed is False


def test_retryable_error_is_checked_before_fsm_terminality() -> None:
    """可重试错误必须先判 —— 否则 `rejected`（FSM terminal）会被读成「放心走」。"""
    decision = cs.classify_editor_destroy(
        request=_facts(
            state=RequestState.rejected, outcome=cs.CommandOutcome.server_error
        ),
        incoming_durable=False,
        recovery_case_open=False,
        timers=load_callback_contract().timers,
    )
    assert decision.verdict is cs.DestroyVerdict.refused_retryable_error
    assert decision.keep_onlyoffice is True


# ═══════════════════════════════════════════════════════════════════════════
# 六、结构判据：接线顺序无法用行为证明
# ═══════════════════════════════════════════════════════════════════════════

_FORBIDDEN_DIRECT_REPO_CALLS = frozenset({"create_forcesave_request_with_shell"})


def test_service_never_bypasses_the_task23_entry_point() -> None:
    """`close_intent.py` 不得直接建 request —— 必须经 Task 23 的唯一入口。

    直接调 `create_forcesave_request_with_shell` 与经
    :meth:`~.request_application.RequestApplicationService.freeze_and_persist_request`
    在 happy path 上**没有任何行为差异**（都会落一条 request + shell），只有源码判据
    会红。差别在于后者保证「authorization-first → freeze → 同事务落库」，以及同
    Idempotency-Key 重放时重新校验当前授权与 frozen fingerprint。
    """
    tree = ast.parse(_CLOSE_INTENT_SRC.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_DIRECT_REPO_CALLS:
            hits.append(node.attr)
    assert hits == [], (
        f"close_intent.py 直接调用了 {sorted(set(hits))} —— request 只能经 "
        "RequestApplicationService.freeze_and_persist_request 创建"
    )
    src = _CLOSE_INTENT_SRC.read_text(encoding="utf-8")
    assert "freeze_and_persist_request" in src, (
        "反向自检：本模块必须**真的**用到 Task 23 的入口，否则上面那条禁令是空的"
    )


def test_close_intent_service_requires_a_wired_command_client() -> None:
    """`client` 无默认值 —— 忘记接线时构造即失败，而不是运行时静默跳过出站。"""
    import inspect

    sig = inspect.signature(ci.CloseIntentService.__init__)
    client = sig.parameters["client"]
    assert client.default is inspect.Parameter.empty, (
        "client 有默认值 ⇒ 「没配就不发」的 fail-open 形态"
    )
    assert client.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


def test_command_client_never_touches_the_database() -> None:
    """出站客户端不得 import 任何 ORM/session 符号。

    它一旦能写库，「先落库再出站」就退化成同一个对象里两行代码的顺序 ——
    而顺序在代码里没有类型。
    """
    tree = ast.parse(_COMMAND_SRC.read_text(encoding="utf-8"))
    banned = {"sqlalchemy", "sa", "AsyncSession", "WorkpaperSyncRepository", "repository"}
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module.split(".")[0])
            found.update(a.name for a in node.names)
    assert not (found & banned), sorted(found & banned)


def test_close_intent_module_imports_the_accepted_request_credential() -> None:
    """反向自检：本模块必须**用到** `AcceptedRequest`。

    没有这条，「出站只接受凭据」这一整组判据可能只是因为本模块根本没有出站路径
    （additive 注入即死代码的形态）。
    """
    src = _CLOSE_INTENT_SRC.read_text(encoding="utf-8")
    assert "AcceptedRequest" in src
    assert "assert_dispatchable" in src
    assert "ordinary_forcesave_request_id" in src, (
        "barrier predecessor 必须真的写 ordinary_forcesave_request_id —— "
        "该列此前没有任何生产代码写过"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 七、exactly-one 的两个反面 + 冻结身份完整性（正确实现下恒不触发的分支）
# ═══════════════════════════════════════════════════════════════════════════
#
# 这三组判据在真库上**一条都走不到**：正确实现下 open capture 数恒为 0/1、
# no-successor 后 live intent 恒为 0、冻结身份五项恒非空。所以它们必须是纯函数 +
# 合成输入 —— 内嵌在服务方法里时把它们改成 `if False:` 不会有任何测试变红
# （不可证伪的判据 = 假绿入口）。


@pytest.mark.parametrize(
    ("count", "raises"),
    [(0, False), (1, False), (2, True), (5, True)],
    ids=["zero", "one", "two", "five"],
)
def test_more_than_one_open_capture_is_refused(count: int, raises: bool) -> None:
    """任何 >1 都失败；0 与 1 都合法（0 是 no-successor 路径的正确结果）。"""
    call = lambda: ci.assert_at_most_one_open_capture(  # noqa: E731
        count, room_id=_ID_MID, generation=7
    )
    if raises:
        with pytest.raises(ci.CloseCaptureNotUniqueError):
            call()
    else:
        call()


@pytest.mark.parametrize(
    ("live", "raises"),
    [(0, False), (1, True), (3, True)],
    ids=["none_live", "one_live", "three_live"],
)
def test_live_intent_after_no_successor_is_refused(live: int, raises: bool) -> None:
    """no-successor 终结后还有 live intent ⇒ 永久阻塞，必须拒。"""
    call = lambda: ci.assert_no_live_intent_remains(  # noqa: E731
        live, room_id=_ID_MID, generation=7
    )
    if raises:
        with pytest.raises(ci.CloseIntentPermanentlyBlockedError):
            call()
    else:
        call()


_COMPLETE_IDENTITY: dict[str, Any] = {
    "participant_id": _ID_LOW,
    "permission_epoch": 5,
    "confirmation_id": _ID_MID,
    "write_fence_epoch": 2,
    "definition_bundle_id": _ID_HIGH,
}


def test_complete_frozen_identity_passes() -> None:
    """反向自检：五项齐全时不抛，否则下面五条「缺一即拒」可能只是恒抛。"""
    ci.assert_frozen_identity_complete(**_COMPLETE_IDENTITY)


@pytest.mark.parametrize(
    "missing",
    [
        "participant_id",
        "permission_epoch",
        "confirmation_id",
        "write_fence_epoch",
        "definition_bundle_id",
    ],
    ids=[
        "participant_id",
        "permission_epoch",
        "confirmation_id",
        "write_fence_epoch",
        "definition_bundle_id",
    ],
)
def test_each_frozen_identity_field_is_independently_required(missing: str) -> None:
    """五项各一条用例（AC 10.10：initiator 缺失 SHALL 阻止提交）。

    `permission_epoch=0` 是合法值而 `None` 不是 —— 所以判据必须是 `is None`
    而不是真值判断。用例里把它置 `None` 才能证明这一点。
    """
    payload = dict(_COMPLETE_IDENTITY)
    payload[missing] = None
    with pytest.raises(ci.CloseIntentAuthorizationError):
        ci.assert_frozen_identity_complete(**payload)


def test_zero_permission_epoch_and_zero_fence_are_valid() -> None:
    """0 不等于缺失：`permission_epoch=0` / `write_fence_epoch=0` 必须放过。

    没有这条，把 `is None` 写成 `not x` 的实现会被上面五条全部放过 ——
    而那会把「刚建 room、fence 还是 0」的正常 close 一律拒掉。
    """
    ci.assert_frozen_identity_complete(
        **{**_COMPLETE_IDENTITY, "permission_epoch": 0, "write_fence_epoch": 0}
    )


# ═══════════════════════════════════════════════════════════════════════════
# 变异接口登记（mutation interface registry）
# ═══════════════════════════════════════════════════════════════════════════
#
# `backend/scripts/diagnose/mutate_task24_close_intent_guards.py` 的 `want=` 直接引用
# 下列 nodeid。**被变异引用的 parametrized nodeid 就是接口**：改 `ids=` 里的字符串、
# 增删用例顺序都会让 `want` 指空并被判 WRONG-TEST，所以它们必须像公开签名一样登记。
#
# 这份清单同时让变异脚本的 `--list` 能定位到目标 —— `_mutation_kit` 只能在守卫文件
# 的**文本**里查 needle，而 parametrize 生成的 id 不出现在源码里（`ids=` 里只有裸字符串
# `"revoked"`，不是完整 nodeid）。
#
# _MUTATION_INTERFACE:
#   test_eligibility_has_one_independent_branch_per_disqualifier[revoked]
#   test_eligibility_has_one_independent_branch_per_disqualifier[expired]
#   test_eligibility_has_one_independent_branch_per_disqualifier[still_active]
#   test_eligibility_has_one_independent_branch_per_disqualifier[left]
#   test_eligibility_has_one_independent_branch_per_disqualifier[terminal_intent]
#   test_eligibility_has_one_independent_branch_per_disqualifier[promoted_intent]
#   test_more_than_one_open_capture_is_refused[two]
#   test_more_than_one_open_capture_is_refused[five]
#   test_live_intent_after_no_successor_is_refused[one_live]
#   test_live_intent_after_no_successor_is_refused[three_live]
#   test_target_must_belong_to_the_frozen_request_generation[other_room]
#   test_target_must_belong_to_the_frozen_request_generation[other_generation]
#   test_unreadable_or_unknown_return_code_fails_visible[missing_error_key]
#   test_unreadable_or_unknown_return_code_fails_visible[error_is_bool]
#   test_editor_destroy_gate_branches[retryable_keeps_oo]
#   test_editor_destroy_gate_branches[timeout_keeps_oo]
#   test_editor_destroy_gate_branches[crash_durable_but_no_case_refused]


def test_mutation_interface_nodeids_still_exist() -> None:
    """登记的 nodeid 必须真的能被 pytest 收集到。

    没有这条，登记块就只是注释：改掉某个 `ids=` 字符串后，变异脚本的 `--list` 仍能在
    注释里查到 needle（假绿），而 `--run` 到那条时会判 WRONG-TEST —— 而 WRONG-TEST
    很容易被读成「污染残留」而不是「接口被改了」。

    这里直接用 pytest 的收集结果核对，而不是正则解析 `ids=`：后者会漏掉
    `ids=[...]` 由列表推导生成的情况。
    """
    import subprocess

    src = Path(__file__).read_text(encoding="utf-8")
    marker = "# _MUTATION_INTERFACE:"
    assert marker in src, "登记块不见了"
    declared = [
        line.strip().lstrip("#").strip()
        for line in src.split(marker, 1)[1].splitlines()
        if line.strip().startswith("#") and "[" in line
    ]
    assert len(declared) >= 17, declared

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(Path(__file__)), "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
    )
    collected = proc.stdout
    missing = [d for d in declared if d not in collected]
    assert missing == [], (
        f"登记的 nodeid 已不存在（`ids=` 被改或用例被删）：{missing} —— "
        "变异脚本的 want 会指空并被判 WRONG-TEST"
    )
