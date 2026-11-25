"""同步 operation 结算后复核的**纯判据**部分（无 IO、无 DB、无 CLI）。

spec `frozen-contract-read-path-and-legacy-operation-settlement` 任务 9 / R3.4。

R3.4 原文：
    该 operation 终态 / 冲突行 resolved-or-superseded 状态 / 版本链指针 /
    审计轨迹逐项可查，写成可重跑的只读探针。

本模块只放「给定读回来的事实，判据怎么算」——值对象、计数滚动、八条形态判据。
**碰 IO 的部分全部在** `check_sync_operation_settlement.py`（CLI 层）。这样切的原因不是风格：

* 判据可以在**离线**用例里逐条驱动（含否定侧），不需要临时 schema 也能证明它们真的会红；
* 「探针是只读的」这条判据可以**静态**断言（AST 扫两个模块里的
  `insert/update/delete/commit` 调用），不必靠人读；
* 本仓 `check_file_size.py` 的门限是 800 行，判据与 IO 分开后两侧都留得下余量。

═══ 「状态变了但内容没落地」到底指什么 ═══

任务原文举的例子是「终态为 applied 时必须有新 representation 且 revision 前进」。
这里把它拆成**方向分型 + 两种终态各自成立**的一组判据（V1~V8），因为现算发现
「已落地」在平台上不是一个方向的事：

| 方向 | 落地证据 | 现算 |
| --- | --- | --- |
| `oo_to_html` | content application → 新 representation + 新 content version | 106/106 三条判据成立 |
| `html_to_oo` | **只有** room（该方向从不产生 content application，Property 64） | 784/784 `application_id IS NULL` |

⇒ 若不按方向分型，`html_to_oo` 的 784 条 `applied` 会被判成「状态变了但内容没落地」，
即把正确实现判成缺陷。这类「假红」与假绿同样有害：它会让探针输出失去可读性。

判据里的「终态」一律**从状态机现读**（`models.is_terminal("operation", …)`）；
「作废终态」取任务 8 的 `conflict_abandon.ABANDON_TERMINAL_STATE`。只有
「哪些终态算已落地」是本地常量 `LANDED_TERMINAL_STATES` —— 它表达的是**业务语义**
（内容写进库了）而非状态机性质，`duplicate` 也是终态但不落地内容，必须排除。
"""

from __future__ import annotations

from typing import Mapping, Sequence

from scripts.check.sync_settlement_facts import (  # noqa: F401 - re-export
    ConflictRollup,
    OperationReport,
    TimelineEvent,
    VersionChain,
    Verdict,
    summarize_conflicts,
)

__all__ = [
    "REPORT_SCHEMA",
    "NONDETERMINISTIC_KEYS",
    "LANDED_TERMINAL_STATES",
    "ALL_VERDICTS",
    "KNOWN_LEGACY_GAPS",
    "VERDICT_OPERATION_TERMINAL_EVENT",
    "VERDICT_EVENT_SEQUENCE",
    "VERDICT_CONFLICT_TRIPLET",
    "VERDICT_CONFLICT_RESOLUTION_PAIR",
    "VERDICT_APPLIED_HAS_APPLICATION",
    "VERDICT_APPLIED_HAS_RESULT",
    "VERDICT_SUPERSEDED_HAS_NO_RESULT",
    "VERDICT_APPLIED_HAS_NO_OPEN_CONFLICT",
    "ConflictRollup",
    "VersionChain",
    "TimelineEvent",
    "Verdict",
    "OperationReport",
    "summarize_conflicts",
    "is_landed_terminal",
    "is_abandon_terminal",
    "is_terminal_operation_state",
    "build_verdicts",
    "verdict_operation_terminal_has_matching_event",
    "verdict_event_sequence_is_contiguous",
    "verdict_abandon_triplet_is_all_or_nothing",
    "verdict_resolution_pair_is_all_or_nothing",
    "verdict_applied_has_application",
    "verdict_applied_has_new_representation",
    "verdict_superseded_created_no_representation",
    "verdict_applied_has_no_open_conflict",
]

#: 报告 schema 版本。对拍时先比它 —— 结构变了就不能按字段比。
REPORT_SCHEMA = "sync-operation-settlement-review/v1"

#: `--compare` 与「可重跑」判据里被显式忽略的键。
#: 只放**生成时刻**这一类，不放任何业务字段 —— 否则「忽略」会掩盖真差异。
NONDETERMINISTIC_KEYS: tuple[str, ...] = ("generated_at",)

#: 「内容已落地」的 operation 终态。
#:
#: `oo_to_html._apply_settled` 按 `requires_client_refresh` 在 `applied` /
#: `refresh_required` 之间选 —— 两者都是「内容已写进库」的终态。
#: `duplicate` 也是终态，但语义是「同 key 折叠到别人身上」，不落地内容，**必须排除**。
LANDED_TERMINAL_STATES: frozenset[str] = frozenset({"applied", "refresh_required"})

#: 每段判据的稳定 id。守卫按 id 断言（不按中文文案），文案改动不动判据。
VERDICT_OPERATION_TERMINAL_EVENT = "V1_operation_terminal_has_matching_event"
VERDICT_EVENT_SEQUENCE = "V2_event_sequence_is_contiguous_from_one"
VERDICT_CONFLICT_TRIPLET = "V3_abandon_triplet_is_all_or_nothing"
VERDICT_CONFLICT_RESOLUTION_PAIR = "V4_resolution_pair_is_all_or_nothing"
VERDICT_APPLIED_HAS_APPLICATION = "V5_oo_to_html_applied_has_application"
VERDICT_APPLIED_HAS_RESULT = "V6_applied_has_new_representation_and_newer_revision"
VERDICT_SUPERSEDED_HAS_NO_RESULT = "V7_superseded_created_no_representation"
VERDICT_APPLIED_HAS_NO_OPEN_CONFLICT = "V8_applied_conflicts_are_all_settled"

#: 全部形态判据（守卫断言「每条判据都在报告里出现过」—— 防登记了却从不执行的死判据）。
ALL_VERDICTS: tuple[str, ...] = (
    VERDICT_OPERATION_TERMINAL_EVENT,
    VERDICT_EVENT_SEQUENCE,
    VERDICT_CONFLICT_TRIPLET,
    VERDICT_CONFLICT_RESOLUTION_PAIR,
    VERDICT_APPLIED_HAS_APPLICATION,
    VERDICT_APPLIED_HAS_RESULT,
    VERDICT_SUPERSEDED_HAS_NO_RESULT,
    VERDICT_APPLIED_HAS_NO_OPEN_CONFLICT,
)

#: 已知的**历史数据缺口**：缺口 id → 一句中文说明。
#:
#: 🔴 这不是「允许违规」的白名单，而是**棘轮**：`test_sync_operation_settlement_probe`
#: 断言「现算出的缺口集合 ⊆ 本集合」**且**「本集合里没有已自愈的条目」。新增缺口即红；
#: 修好了必须同步删行（否则棘轮失效，与本仓其它棘轮的纪律一致）。
#:
#: 两条都早于本 spec，且与任务 8 的作废路径无关：
#:
#: * ``legacy_oo_applied_unsettled_conflicts`` —— 2026-11-16 现算：1 条 `applied` 的
#:   `oo_to_html` operation 上 108 条冲突里 54 条三列全空。它走「带 resolutions 的
#:   apply」路径，`record_conflicts` 只覆盖三值元数据、**不清** `resolved_*`（裁决轨迹），
#:   旧一轮观测靠 `superseded_at` 收口。不影响「内容已落地」（V5/V6 在它上面成立）。
#: * ``legacy_oo_applied_without_entry_state`` —— 2026-09 那批 applied 的 52 条
#:   application 所在 wp 至今没有 `working_paper_sync_entry_state` 行（entry_state 是
#:   后加的 current pointer，历史 wp 从未回填）。内容确实落地了，缺的是 pointer 回填。
KNOWN_LEGACY_GAPS: Mapping[str, str] = {
    "legacy_oo_applied_unsettled_conflicts": (
        "已 applied 的 operation 上仍挂着未裁决也未作废的冲突行 —— "
        "属同一冲突集旧一轮观测，设计上由 superseded_at 收口"
    ),
    "legacy_oo_applied_without_entry_state": (
        "历史 oo_to_html applied 的 wp 没有 working_paper_sync_entry_state 行 —— "
        "内容已落地（result_representation_id / revision 齐备），缺的是 current pointer 回填"
    ),
}


#: 值对象与计数滚动在 `sync_settlement_facts`（真库守卫要直接构造它们）。
def _operation_is_terminal(state: str) -> bool:
    """`is_terminal("operation", …)` —— 现读状态机，不写死终态集合。"""
    from app.services.workpaper_sync.models import OperationState, is_terminal

    return is_terminal("operation", OperationState(state))


def is_terminal_operation_state(state: str) -> bool:
    """公开版 `_operation_is_terminal`：给报告层填 `is_terminal` 用。

    未知状态（枚举里没有的字面量）返回 `False` 而不是抛 —— 报告仍要能渲染出这一行，
    否则一条脏状态会把整份复核打断。判据侧不依赖它（V1 用它判「是否适用」，
    脏状态会被当成非终态 ⇒ V1 跳过，而 V2/V3/V4 仍照跑）。
    """
    try:
        return _operation_is_terminal(state)
    except (ValueError, ImportError):
        return False


def is_landed_terminal(state: str) -> bool:
    """「内容已写进库」的终态 = 终态 ∧ 属于 `LANDED_TERMINAL_STATES`。

    🔴 必须**两条都成立**：只取 `LANDED_TERMINAL_STATES` 会漏掉「状态机改了而本常量没跟」
    （那时应当判据失效而不是静默放行）；只取 `is_terminal` 会把 `duplicate` / `rejected`
    也算成落地。
    """
    try:
        terminal = _operation_is_terminal(state)
    except (ValueError, ImportError):  # pragma: no cover - 未知状态 / 模块缺失
        return False
    return terminal and state in LANDED_TERMINAL_STATES


def is_abandon_terminal(state: str) -> bool:
    """作废终态 —— **从任务 8 的常量现读**，不写字面量。"""
    from app.services.workpaper_sync.conflict_abandon import ABANDON_TERMINAL_STATE

    return state == ABANDON_TERMINAL_STATE.value


# ═══════════════════════════════════════════════════════════════════════════
# 八条形态判据
# ═══════════════════════════════════════════════════════════════════════════


def verdict_operation_terminal_has_matching_event(
    *, state: str, timeline: Sequence[TimelineEvent], is_terminal_state: bool
) -> Verdict:
    """V1 —— 终态必须有落进该终态的 event（`current state` 只是 timeline 投影）。

    🔴 这不是新发明的不变量：`working_paper_sync_operation_event` 的建表注释原文就是
    「current state 只是 timeline 投影」。裸 `UPDATE … SET state` 会让两者分叉，
    而那正是 R3.4「状态变了但内容没落地」最直接的形态之一。
    """
    if not is_terminal_state:
        return Verdict(
            rule_id=VERDICT_OPERATION_TERMINAL_EVENT,
            ok=True,
            detail=f"state={state} 非终态，不适用；timeline 共 {len(timeline)} 条",
        )
    hits = [e for e in timeline if e.to_state == state]
    if not hits:
        return Verdict(
            rule_id=VERDICT_OPERATION_TERMINAL_EVENT,
            ok=False,
            detail=(
                f"终态 {state} 在 timeline 上没有任何 to_state={state} 的 event "
                f"（现有 to_state 集合：{sorted({e.to_state for e in timeline})}）—— "
                "current state 与 append-only timeline 分叉，疑似裸 SQL 改了 state"
            ),
        )
    last = hits[-1]
    return Verdict(
        rule_id=VERDICT_OPERATION_TERMINAL_EVENT,
        ok=True,
        detail=(
            f"终态 {state} 由第 {last.sequence_no} 条 event 落定"
            f"（from={last.from_state!r} stage={last.stage!r} actor_type={last.actor_type}）"
        ),
    )


def verdict_event_sequence_is_contiguous(timeline: Sequence[TimelineEvent]) -> Verdict:
    """V2 —— `sequence_no` 必须从 1 起严格连续（历史轨迹不得断号/重号）。"""
    numbers = [e.sequence_no for e in timeline]
    if not numbers:
        return Verdict(
            rule_id=VERDICT_EVENT_SEQUENCE,
            ok=False,
            detail="operation 一条 event 都没有 —— 任何状态变化都应留下 append-only event",
        )
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        return Verdict(
            rule_id=VERDICT_EVENT_SEQUENCE,
            ok=False,
            detail=f"sequence_no 不是 1..{len(numbers)} 的连续序列：{numbers}",
        )
    return Verdict(
        rule_id=VERDICT_EVENT_SEQUENCE,
        ok=True,
        detail=f"sequence_no = 1..{len(numbers)} 连续",
    )


def verdict_abandon_triplet_is_all_or_nothing(rollup: ConflictRollup) -> Verdict:
    """V3 —— 作废三列同生共死（`ck_wpsc_abandon_triplet` 的读侧复核）。

    分母是**全部**冲突行：只写一两列的残缺行在 DB 层已被约束拒绝，但读侧仍要复核，
    因为「约束没生效」正是任务 8 R9.3 实测抓到的形态（`pg_constraint` 只按 conname
    查会因同库另有同名约束而静默跳过建约束）。
    """
    if rollup.abandoned == 0:
        return Verdict(
            rule_id=VERDICT_CONFLICT_TRIPLET,
            ok=True,
            detail=f"{rollup.total} 条冲突行都没有作废（三列全空是合法态）",
        )
    if rollup.triplet_complete != rollup.abandoned:
        return Verdict(
            rule_id=VERDICT_CONFLICT_TRIPLET,
            ok=False,
            detail=(
                f"{rollup.abandoned} 条行有 abandoned_at，但只有 "
                f"{rollup.triplet_complete} 条三列齐备 "
                f"（缺 {rollup.abandoned - rollup.triplet_complete} 条）—— "
                "「谁在什么时候因为什么作废了」残缺，ck_wpsc_abandon_triplet 未生效或数据被旁路写入"
            ),
        )
    return Verdict(
        rule_id=VERDICT_CONFLICT_TRIPLET,
        ok=True,
        detail=f"{rollup.abandoned}/{rollup.total} 条已作废行三列齐备",
    )


def verdict_resolution_pair_is_all_or_nothing(rollup: ConflictRollup) -> Verdict:
    """V4 —— `resolved_at` / `resolved_by` 成对（`ck_wpsc_resolution_pair` 的读侧复核）。

    额外断言 `resolved_value` 非空：AC 8.6 要求「裁决轨迹 = 选择结果 + 落地值 + actor +
    时间」四要素，`resolved_by`/`resolved_at` 成对但 `resolved_value` 为空的行，
    事后无法证明「裁决落到哪个值」。
    """
    if rollup.resolved == 0:
        return Verdict(
            rule_id=VERDICT_CONFLICT_RESOLUTION_PAIR,
            ok=True,
            detail=f"{rollup.total} 条冲突行都没有裁决记录",
        )
    problems: list[str] = []
    if rollup.resolution_pair_complete != rollup.resolved:
        problems.append(
            f"{rollup.resolved} 条有 resolved_at 但只有 {rollup.resolution_pair_complete} 条成对"
        )
    if rollup.resolved_without_value:
        problems.append(
            f"{len(rollup.resolved_without_value)} 条有 resolved_at 却没有 resolved_value"
            f"（{list(rollup.resolved_without_value[:3])}）"
        )
    if problems:
        return Verdict(
            rule_id=VERDICT_CONFLICT_RESOLUTION_PAIR,
            ok=False,
            detail="裁决轨迹残缺：" + "；".join(problems),
        )
    return Verdict(
        rule_id=VERDICT_CONFLICT_RESOLUTION_PAIR,
        ok=True,
        detail=f"{rollup.resolved}/{rollup.total} 条裁决行三要素（by/at/value）齐备",
    )


def verdict_applied_has_application(
    *, state: str, direction: str, chain: VersionChain
) -> Verdict:
    """V5 —— `oo_to_html` 的「已落地」终态必须有 application（唯一的落地载体）。

    🔴 **方向分型是必须的**，不是放宽：`html_to_oo` 方向**永远**没有 content
    application（`materialize_coordinator._open_operation` 的 docstring 原文：
    「HTML→OO 方向没有 incoming artifact，永远不产生 content application（Property 64）」）。
    现算：784 条 `applied` 的 `html_to_oo` operation 全部 `application_id IS NULL` ——
    若这里不做方向分型，会有 784 条假阳。它的落地证据是 `room_id`（现算 784/784 非空）。
    """
    if not is_landed_terminal(state):
        return Verdict(
            rule_id=VERDICT_APPLIED_HAS_APPLICATION,
            ok=True,
            detail=f"state={state} 不是「已落地」终态，不适用",
        )
    if direction == "html_to_oo":
        if chain.room_id is None:
            return Verdict(
                rule_id=VERDICT_APPLIED_HAS_APPLICATION,
                ok=False,
                detail=(
                    "html_to_oo 已落地的 operation 没有 room_id —— 该方向不产生 "
                    "content application，room 是它唯一的落地证据"
                ),
            )
        return Verdict(
            rule_id=VERDICT_APPLIED_HAS_APPLICATION,
            ok=True,
            detail=(
                "html_to_oo 方向不产生 content application（Property 64）；"
                f"room={chain.room_id}"
            ),
        )
    if chain.application_id is None:
        return Verdict(
            rule_id=VERDICT_APPLIED_HAS_APPLICATION,
            ok=False,
            detail=(
                f"direction={direction} 的 {state} operation 没有 application_id —— "
                "该方向的落地必须经过 content application，缺它即「状态变了但内容没落地」"
            ),
        )
    return Verdict(
        rule_id=VERDICT_APPLIED_HAS_APPLICATION,
        ok=True,
        detail=f"application={chain.application_id}（state={chain.application_state}）",
    )


def verdict_applied_has_new_representation(
    *, state: str, direction: str, chain: VersionChain
) -> Verdict:
    """V6 —— 「已落地」终态必须有**新** representation 且 content revision 前进。

    这是任务原文那句「终态为 applied 时必须有新 representation 且 revision 前进」的落地。
    三件事逐项断言（任一不成立都点名）：

    1. `result_representation_id` 非空，且该 representation 行真实存在（generation 读得回来）；
    2. 它**不等于** `base_representation_id`（不是原地复用）；
    3. 它所属 content version 的 `revision` **大于**冻结基线版本
       `base_version_id → revision` 的 revision。

    🔴 **基线选错会假红，这一点是实测出来的**：`application.current_revision` 看着像
    「冻结时的 revision」，实际是 `working_paper.content_revision`（另一个计数器）在
    correlation 时的快照 —— 现算 106 条里有 4 条 `result_revision`(5/7/9/11) 小于它(11)，
    但它们的 `base_version.revision` 是 4/6/8/10，逐条严格前进。拿 `current_revision`
    当基线会给这 4 条假红，也就是把正确实现判成缺陷。

    现算依据（2026-11-16，共享库）：106 条 `applied`/`refresh_required` 的 application
    在这三条上**逐条成立**（`result_representation_id <> base_representation_id`
    106/106、`result_cv.revision > base_cv.revision` 106/106）。
    """
    if not is_landed_terminal(state):
        return Verdict(
            rule_id=VERDICT_APPLIED_HAS_RESULT,
            ok=True,
            detail=f"state={state} 不是「已落地」终态，不适用",
        )
    if direction == "html_to_oo":
        return Verdict(
            rule_id=VERDICT_APPLIED_HAS_RESULT,
            ok=True,
            detail="html_to_oo 方向不发布 representation（materialize 只开 room），不适用",
        )
    problems: list[str] = []
    if chain.result_representation_id is None:
        problems.append("result_representation_id 为空")
    elif chain.result_representation_generation is None:
        problems.append(f"result representation {chain.result_representation_id} 行不存在")
    if (
        chain.result_representation_id is not None
        and chain.result_representation_id == chain.base_representation_id
    ):
        problems.append("result representation 与 base representation 是同一个（没有新代际）")
    if chain.result_content_version_revision is None:
        problems.append("result representation 所属 content version 读不回来")
    elif chain.base_content_version_revision is None:
        problems.append("base_version 行读不回来，无法证明 revision 前进")
    elif chain.result_content_version_revision <= chain.base_content_version_revision:
        problems.append(
            f"content revision 没有前进（result={chain.result_content_version_revision} "
            f"<= base={chain.base_content_version_revision}）"
        )
    if problems:
        return Verdict(
            rule_id=VERDICT_APPLIED_HAS_RESULT,
            ok=False,
            detail="「状态变了但内容没落地」：" + "；".join(problems),
        )
    return Verdict(
        rule_id=VERDICT_APPLIED_HAS_RESULT,
        ok=True,
        detail=(
            f"新 representation={chain.result_representation_id} "
            f"(generation={chain.result_representation_generation})，"
            f"revision {chain.base_content_version_revision} → "
            f"{chain.result_content_version_revision}"
        ),
    )


def verdict_superseded_created_no_representation(
    *, state: str, rollup: ConflictRollup, chain: VersionChain
) -> Verdict:
    """V7 —— 作废终态**不得**造出新内容，且必须留下三列审计事实。

    这是任务原文第二个方向的互斥断言：「superseded 但三列不全」与
    「superseded 却新建了 representation」都不允许。

    🔴 判据的分母是**该 operation 的冲突行**（作废的对象），不是 application ——
    作废路径压根不碰 application（`ConflictAbandonService` 只在冲突行与 operation 上写）。
    """
    if not is_abandon_terminal(state):
        return Verdict(
            rule_id=VERDICT_SUPERSEDED_HAS_NO_RESULT,
            ok=True,
            detail=f"state={state} 不是作废终态，不适用",
        )
    problems: list[str] = []
    if rollup.total == 0:
        problems.append("作废终态下一条冲突行都没有 —— 没有可作废的对象，作废事实不可复核")
    elif rollup.abandoned != rollup.total:
        problems.append(
            f"只有 {rollup.abandoned}/{rollup.total} 条冲突行被作废"
            "（剩余行既没裁决也没作废）"
        )
    elif rollup.triplet_complete != rollup.total:
        problems.append(f"三列齐备的只有 {rollup.triplet_complete}/{rollup.total} 条")
    if chain.result_representation_id is not None:
        problems.append(
            f"作废路径却产生了 result representation {chain.result_representation_id} —— "
            "作废不得发布内容"
        )
    if problems:
        return Verdict(
            rule_id=VERDICT_SUPERSEDED_HAS_NO_RESULT,
            ok=False,
            detail="；".join(problems),
        )
    return Verdict(
        rule_id=VERDICT_SUPERSEDED_HAS_NO_RESULT,
        ok=True,
        detail=f"{rollup.total}/{rollup.total} 条冲突行已作废、三列齐备、未发布 representation",
    )


def verdict_applied_has_no_open_conflict(
    *, state: str, direction: str, rollup: ConflictRollup
) -> Verdict:
    """V8 —— 「已落地」终态下不该还有既未裁决也未作废的冲突行。

    🔴 这条判据**当前对一条历史数据不成立**（现算：1 条 `applied` 的 `oo_to_html`
    operation 上挂着 108 条冲突，其中 54 条三列全空）。它登记为已知缺口
    ``legacy_oo_applied_unsettled_conflicts``（详见 `KNOWN_LEGACY_GAPS`）。

    ⇒ 判据保留且**照实判红**（不因「已登记」而降级为绿），由守卫按棘轮核对集合。
    """
    if not is_landed_terminal(state):
        return Verdict(
            rule_id=VERDICT_APPLIED_HAS_NO_OPEN_CONFLICT,
            ok=True,
            detail=(
                f"state={state} 不是「已落地」终态 —— 冲突未收口在这种状态下**是正常形态**"
                "（冲突态本来就有未处理行），不适用"
            ),
        )
    if direction == "html_to_oo":
        return Verdict(
            rule_id=VERDICT_APPLIED_HAS_NO_OPEN_CONFLICT,
            ok=True,
            detail=f"direction={direction} 不产生冲突集（无 incoming），不适用",
        )
    if rollup.unsettled == 0:
        return Verdict(
            rule_id=VERDICT_APPLIED_HAS_NO_OPEN_CONFLICT,
            ok=True,
            detail=f"{rollup.total} 条冲突行全部已收口（resolved/abandoned/superseded）",
        )
    return Verdict(
        rule_id=VERDICT_APPLIED_HAS_NO_OPEN_CONFLICT,
        ok=False,
        detail=(
            f"{rollup.unsettled}/{rollup.total} 条冲突行既未裁决也未作废，"
            "但 operation 已是 applied"
        ),
        known_gap="legacy_oo_applied_unsettled_conflicts",
    )


def build_verdicts(
    *,
    state: str,
    direction: str,
    rollup: ConflictRollup,
    chain: VersionChain,
    timeline: Sequence[TimelineEvent],
) -> tuple[Verdict, ...]:
    """把八条判据对一条 operation 全跑一遍（顺序固定 = `ALL_VERDICTS`，便于对拍）。"""
    try:
        is_terminal_state = _operation_is_terminal(state)
    except (ValueError, ImportError):  # pragma: no cover
        is_terminal_state = False
    return (
        verdict_operation_terminal_has_matching_event(
            state=state, timeline=timeline, is_terminal_state=is_terminal_state
        ),
        verdict_event_sequence_is_contiguous(timeline),
        verdict_abandon_triplet_is_all_or_nothing(rollup),
        verdict_resolution_pair_is_all_or_nothing(rollup),
        verdict_applied_has_application(state=state, direction=direction, chain=chain),
        verdict_applied_has_new_representation(
            state=state, direction=direction, chain=chain
        ),
        verdict_superseded_created_no_representation(
            state=state, rollup=rollup, chain=chain
        ),
        verdict_applied_has_no_open_conflict(
            state=state, direction=direction, rollup=rollup
        ),
    )
