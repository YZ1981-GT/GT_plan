"""同步 operation 结算后复核的**值对象**（R3.4 的四段事实）。

spec `frozen-contract-read-path-and-legacy-operation-settlement` 任务 9 / R3.4。

这里只有数据结构与一个计数滚动函数（`summarize_conflicts`），没有 IO、没有判据、
没有 CLI —— 它们分别在 `check_sync_operation_settlement.py`（IO + CLI）与
`sync_settlement_review.py`（八条形态判据 V1~V8）。

把值对象单独放一个模块的理由与本仓 `check_file_size.py` 无关，是**复用面**：
真库守卫（`test_sync_operation_settlement_pg.py`）要直接构造这些对象来断言
「残缺形态会不会被判红」，而它不该 import 一个带 SQL 的模块。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

__all__ = [
    "ConflictRollup",
    "VersionChain",
    "TimelineEvent",
    "Verdict",
    "OperationReport",
    "summarize_conflicts",
]


# ═══════════════════════════════════════════════════════════════════════════
# 值对象（纯数据，便于离线断言与 --compare 逐字段比对）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ConflictRollup:
    """② 冲突行的 resolved-or-superseded 状态（R3.4 的四类计数 + 三列齐备率）。"""

    total: int
    resolved: int
    abandoned: int
    superseded: int
    unsettled: int
    #: 三列齐备的作废行数（`abandoned_at` / `abandon_reason` / `abandoned_by` 全非空）。
    triplet_complete: int
    #: `resolved_at` / `resolved_by` 成对的行数。
    resolution_pair_complete: int
    #: `resolved_at` 非空但 `resolved_value` 为空的 id（裁决轨迹残缺）。
    resolved_without_value: tuple[str, ...]

    @property
    def settled(self) -> int:
        """已收口条数。**「resolved-or-superseded」的唯一口径**，别处不再各算一次。"""
        return self.resolved + self.abandoned + self.superseded

    @property
    def is_fully_settled(self) -> bool:
        return self.unsettled == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "resolved": self.resolved,
            "abandoned": self.abandoned,
            "superseded": self.superseded,
            "unsettled": self.unsettled,
            "triplet_complete": self.triplet_complete,
            "resolution_pair_complete": self.resolution_pair_complete,
            "resolved_without_value": list(self.resolved_without_value),
            "settled": self.settled,
            "is_fully_settled": self.is_fully_settled,
        }


@dataclass(frozen=True)
class VersionChain:
    """③ 版本链指针。

    🔴 `application.current_revision` 是 `working_paper.content_revision`（另一个计数器）
    在 correlation 时的快照，**不是**冻结基线版本的 revision；判断「revision 前进了没有」
    的**唯一**正确基线是 `base_content_version_revision`
    （拿 `current_revision` 当基线会给出假红，见 V6 docstring）。
    """

    application_id: str | None
    application_state: str | None
    definition_bundle_id: str | None
    base_version_id: str | None
    base_representation_id: str | None
    #: 见类 docstring：这是 `working_paper.content_revision` 的快照，**不是**判断基线的口径。
    current_revision: int | None
    #: 冻结基线 content version 的 revision（`base_version_id → revision`）。
    base_content_version_revision: int | None
    result_representation_id: str | None
    result_revision: int | None
    merged_projection_sha256: str | None
    #: entry 级 current pointer（可能整行不存在 —— 历史 wp 的回填债）。
    entry_state_present: bool
    entry_current_representation_id: str | None
    entry_representation_generation: int | None
    #: `result_representation_id` 的实际 generation（现读 representation 表）。
    result_representation_generation: int | None
    result_content_version_revision: int | None
    #: operation 的 `room_id`（HTML→OO 方向它必非空，OO→HTML 方向可为空）。
    room_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "application_id": self.application_id,
            "application_state": self.application_state,
            "definition_bundle_id": self.definition_bundle_id,
            "base_version_id": self.base_version_id,
            "base_representation_id": self.base_representation_id,
            "current_revision": self.current_revision,
            "base_content_version_revision": self.base_content_version_revision,
            "result_representation_id": self.result_representation_id,
            "result_revision": self.result_revision,
            "merged_projection_sha256": self.merged_projection_sha256,
            "entry_state_present": self.entry_state_present,
            "entry_current_representation_id": self.entry_current_representation_id,
            "entry_representation_generation": self.entry_representation_generation,
            "result_representation_generation": self.result_representation_generation,
            "result_content_version_revision": self.result_content_version_revision,
            "room_id": self.room_id,
        }


@dataclass(frozen=True)
class TimelineEvent:
    """④ 审计轨迹的一条 operation event（append-only）。"""

    sequence_no: int
    from_state: str | None
    to_state: str
    stage: str | None
    actor_type: str
    actor_id: str | None
    error_code: str | None
    occurred_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence_no": self.sequence_no,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "stage": self.stage,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "error_code": self.error_code,
            "occurred_at": self.occurred_at,
        }


@dataclass(frozen=True)
class Verdict:
    """一条形态判据的结论（`ok=False` 时 `detail` 必须点名具体行 / 具体计数）。"""

    rule_id: str
    ok: bool
    detail: str
    #: 已知历史缺口的 id（无缺口时为空串）。非空 ⇒ 该条判据**仍判红**，
    #: 只是报告里可分辨「这是已登记的旧债」还是「新出现的形态」。
    known_gap: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "ok": self.ok,
            "detail": self.detail,
            "known_gap": self.known_gap,
        }


@dataclass
class OperationReport:
    """一条 operation 的逐项复核结论（四段事实 + 八条判据）。"""

    operation_id: str
    entry_id: str
    wp_id: str
    project_id: str
    direction: str
    state: str
    is_terminal: bool
    accepted_at: str | None
    finished_at: str | None
    error_code: str | None
    error_stage: str | None
    conflicts: ConflictRollup
    version_chain: VersionChain
    timeline: tuple[TimelineEvent, ...]
    verdicts: tuple[Verdict, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return all(v.ok for v in self.verdicts)

    @property
    def known_gaps(self) -> tuple[str, ...]:
        return tuple(sorted({v.known_gap for v in self.verdicts if v.known_gap}))

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "entry_id": self.entry_id,
            "wp_id": self.wp_id,
            "project_id": self.project_id,
            "direction": self.direction,
            "state": self.state,
            "is_terminal": self.is_terminal,
            "accepted_at": self.accepted_at,
            "finished_at": self.finished_at,
            "error_code": self.error_code,
            "error_stage": self.error_stage,
            "conflicts": self.conflicts.as_dict(),
            "version_chain": self.version_chain.as_dict(),
            "timeline": [e.as_dict() for e in self.timeline],
            "verdicts": [v.as_dict() for v in self.verdicts],
            "known_gaps": list(self.known_gaps),
            "ok": self.ok,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 计数滚动
# ═══════════════════════════════════════════════════════════════════════════


def summarize_conflicts(rows: Iterable[Mapping[str, Any]]) -> ConflictRollup:
    """把冲突行的三列事实滚成 R3.4 需要的分类计数。

    🔴 「resolved-or-superseded」在这里**一次**定义清楚，别处只准读这个结果：
    一行只要有 `resolved_at` / `abandoned_at` / `superseded_at` 任一非空即已收口；
    三者全空才算「仍未处理」。用两个独立标志位各算一次是第二真源。

    三列（`abandoned_*`）与两列（`resolved_at`/`resolved_by`）都**同生共死**：
    全空或全非空。三列全空是合法态（未作废），所以 `triplet_complete` 只统计
    「有作废痕迹且三列齐备」的行数。
    """
    total = resolved = abandoned = superseded = unsettled = 0
    triplet = pair = 0
    missing_value: list[str] = []
    for row in rows:
        total += 1
        has_resolved_at = row.get("resolved_at") is not None
        has_resolved_by = row.get("resolved_by") is not None
        has_abandoned_at = row.get("abandoned_at") is not None
        has_abandon_reason = bool(str(row.get("abandon_reason") or "").strip())
        has_abandoned_by = row.get("abandoned_by") is not None
        has_superseded_at = row.get("superseded_at") is not None

        if has_resolved_at:
            resolved += 1
            if row.get("resolved_value") is None:
                missing_value.append(str(row.get("id")))
        if has_abandoned_at:
            abandoned += 1
        if has_superseded_at:
            superseded += 1
        if not (has_resolved_at or has_abandoned_at or has_superseded_at):
            unsettled += 1

        # 三列同生共死（V276 的 `ck_wpsc_abandon_triplet` 在 DB 上强制，这里复核读回值）。
        if has_abandoned_at or has_abandon_reason or has_abandoned_by:
            if has_abandoned_at and has_abandon_reason and has_abandoned_by:
                triplet += 1
        # `ck_wpsc_resolution_pair` 同理。
        if has_resolved_at and has_resolved_by:
            pair += 1

    return ConflictRollup(
        total=total,
        resolved=resolved,
        abandoned=abandoned,
        superseded=superseded,
        unsettled=unsettled,
        triplet_complete=triplet,
        resolution_pair_complete=pair,
        resolved_without_value=tuple(sorted(missing_value)),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 状态分型（从状态机现读，不写字面量）
# ═══════════════════════════════════════════════════════════════════════════
