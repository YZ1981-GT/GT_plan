"""Adapter three-way merge、结构 remap 与 crash recovery（Task 15）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 14.1–14.7

* different-field 自动合并，保留 unmanaged；
* same-field → typed conflict，**禁止**整文件 LWW；
* 结构漂移 → RemapCandidate，阻断自动 projection；
* carrier 丢失/重复不按 label 猜；
* ProjectOperation crash 可重放；current pointer 只在 CAS 成功后变。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.services.custom_template_ingestion.adapters import FieldConflict
from app.services.custom_template_ingestion.lifecycles import (
    Clock,
    ProjectOperationRecord,
    ProjectOperationState,
    SystemClock,
)

__all__ = [
    "RemapCandidate",
    "MergeOutcome",
    "three_way_merge_fields",
    "detect_structural_remap",
    "replay_crashed_operation",
]


@dataclass(frozen=True, slots=True)
class RemapCandidate:
    kind: str  # row|column|sheet|cross_sheet_formula|name|locator
    from_locator: str
    to_locator: str | None
    reason: str
    blocks_auto_projection: bool = True


@dataclass(frozen=True, slots=True)
class MergeOutcome:
    auto_merged: Mapping[str, Any]
    conflicts: tuple[FieldConflict, ...]
    unmanaged_preserved: Mapping[str, Any]
    remaps: tuple[RemapCandidate, ...]
    blocked: bool


def three_way_merge_fields(
    *,
    base: Mapping[str, Any],
    ours: Mapping[str, Any],
    theirs: Mapping[str, Any],
    unmanaged: Mapping[str, Any] | None = None,
) -> MergeOutcome:
    """字段级三方合并；同字段冲突不 LWW。"""
    keys = set(base) | set(ours) | set(theirs)
    merged: dict[str, Any] = {}
    conflicts: list[FieldConflict] = []
    for key in sorted(keys):
        b, o, t = base.get(key), ours.get(key), theirs.get(key)
        if o == t:
            if o is not None:
                merged[key] = o
            elif b is not None:
                merged[key] = b
            continue
        if o == b and t != b:
            merged[key] = t
            continue
        if t == b and o != b:
            merged[key] = o
            continue
        # same-field divergent
        conflicts.append(
            FieldConflict(
                field_id=key,
                base_value=b,
                current_value=o,
                incoming_value=t,
            )
        )
    return MergeOutcome(
        auto_merged=merged,
        conflicts=tuple(conflicts),
        unmanaged_preserved=dict(unmanaged or {}),
        remaps=(),
        blocked=bool(conflicts),
    )


def detect_structural_remap(
    *,
    before_locators: Mapping[str, str],
    after_locators: Mapping[str, str],
) -> tuple[RemapCandidate, ...]:
    """行列/sheet locator drift → RemapCandidate，阻断自动 projection。"""
    remaps: list[RemapCandidate] = []
    before_ids = set(before_locators)
    after_ids = set(after_locators)
    for lost in sorted(before_ids - after_ids):
        remaps.append(
            RemapCandidate(
                kind="locator",
                from_locator=before_locators[lost],
                to_locator=None,
                reason="carrier_lost",
                blocks_auto_projection=True,
            )
        )
    for gained in sorted(after_ids - before_ids):
        # 不得按 label 猜测映射到 lost
        remaps.append(
            RemapCandidate(
                kind="locator",
                from_locator="",
                to_locator=after_locators[gained],
                reason="carrier_new_unmapped",
                blocks_auto_projection=True,
            )
        )
    for shared in sorted(before_ids & after_ids):
        if before_locators[shared] != after_locators[shared]:
            remaps.append(
                RemapCandidate(
                    kind="locator",
                    from_locator=before_locators[shared],
                    to_locator=after_locators[shared],
                    reason="locator_drift",
                    blocks_auto_projection=True,
                )
            )
    return tuple(remaps)


def replay_crashed_operation(
    op: ProjectOperationRecord,
    *,
    clock: Clock | None = None,
    apply: Any = None,
) -> ProjectOperationRecord:
    """崩溃恢复：PENDING/APPLYING 可重放；COMMITTED 幂等返回。"""
    clk = clock or SystemClock()
    if op.state == ProjectOperationState.COMMITTED:
        return op
    if op.state not in (
        ProjectOperationState.PENDING,
        ProjectOperationState.APPLYING,
        ProjectOperationState.FAILED,
    ):
        raise ValueError(f"不可重放状态: {op.state}")
    op.state = ProjectOperationState.APPLYING
    op.updated_at = clk.now()
    if apply is not None:
        apply(op)
    op.state = ProjectOperationState.COMMITTED
    op.updated_at = clk.now()
    return op
