"""粗裁与已生成底稿、程序行任务的联动（spec procedure-trim-generation-delegation-chain 需求 3）。

粗裁方案 preview / apply 共用三件事：

1. **覆盖范围**：一条粗裁条目「管」哪些已生成底稿 —— 与生成时的保留范围同一判定（最近一级有程序行的
   编码决定）：``H3`` 管 ``H3``、``H3-1``~``H3-6``、``H3A``；``A1`` 不管自带程序行的 ``A1-11``；区间行
   ``D2-6至D2-13`` 管 ``D2-6``~``D2-13`` 及其子表。
2. **级联任务**：范围内的程序行任务按底稿归属（``wp_index_id``）匹配。原先按 ``audit_cycle_snapshot``
   匹配，物化时循环兜底成 ``A`` 的任务（重药安徽 I2 / I3）裁剪后没被取消。
3. **回收站**：按应用后的裁剪状态，范围内被裁的已生成底稿移入回收站；恢复执行的从回收站恢复（只恢复
   因裁剪移入的），因级联取消的任务重开为待委派（细裁取消的不动）。

只读部分（覆盖范围、联动计划、预览）不写库；``apply_linkage`` 只 flush。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureInstance, ProcedureRowTaskHistory
from app.models.workpaper_models import WpIndex
from app.services.procedure_scope_retention import TrimmedScope, normalize_code
from app.services.workpaper_recycle_service import (
    KIND_TRIM,
    RecycleTarget,
    last_recycle_kind,
    move_to_recycle_bin,
    plan_recycle,
    restore_from_recycle_bin,
)

#: 粗裁级联取消任务的历史事件类型（恢复执行时据此只重开级联取消的任务）
CASCADE_EVENT = "scheme_scope_cascade"
WORKFLOW_CANCELLED = "cancelled"
SUBSTANTIVE_UNCONFIRMED = "substantive_recycle_unconfirmed"


@dataclass(frozen=True)
class IndexRow:
    id: UUID
    wp_code: str
    wp_name: str
    is_deleted: bool
    recycle_kind: str | None


@dataclass
class ScopeCoverage:
    """项目当前的程序行（含状态）与全部底稿索引（含已删除）。"""

    instances: list[tuple[UUID, str, str]]
    scope: TrimmedScope
    indexes: list[IndexRow]
    _by_id: dict[UUID, IndexRow] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._by_id = {row.id: row for row in self.indexes}

    def code_of(self, wp_index_id: UUID) -> str | None:
        row = self._by_id.get(wp_index_id)
        return row.wp_code if row else None

    def covered(self, entry_code: str) -> list[IndexRow]:
        """由该程序行（最近一级）决定的底稿。决定者与状态无关，只看哪一级有程序行。

        跟随下级程序行的科目母码（``D2`` 审定表）算作它每一条下级行都管（``TrimmedScope.deciders``）：
        只恢复其中一条下级行时，母码也要从回收站恢复。
        """
        code = normalize_code(entry_code)
        return [row for row in self.indexes if code in self.scope.deciders(row.wp_code)]

    def simulate(self, overrides: dict[UUID, str]) -> TrimmedScope:
        """把部分程序行换成目标状态后的裁剪结果（preview / apply 写库前判定用）。"""
        return TrimmedScope.from_rows((code, overrides.get(iid, status)) for iid, code, status in self.instances)


async def load_scope_coverage(db: AsyncSession, project_id: UUID) -> ScopeCoverage:
    rows = (await db.execute(
        sa.select(
            ProcedureInstance.id,
            sa.func.coalesce(ProcedureInstance.wp_code, ProcedureInstance.procedure_code),
            ProcedureInstance.status,
        ).where(ProcedureInstance.project_id == project_id, ProcedureInstance.is_deleted == sa.false())
    )).all()
    instances = [(r[0], r[1] or "", r[2] or "") for r in rows]
    indexes = [
        IndexRow(r[0], r[1], r[2] or "", bool(r[3]), last_recycle_kind(r[4]))
        for r in (await db.execute(
            sa.select(WpIndex.id, WpIndex.wp_code, WpIndex.wp_name, WpIndex.is_deleted, WpIndex.cross_ref_codes)
            .where(WpIndex.project_id == project_id)
        )).all()
    ]
    return ScopeCoverage(instances, TrimmedScope.from_rows((c, s) for _, c, s in instances), indexes)


@dataclass
class ScopeLinkage:
    """一次粗裁应用对已生成底稿与任务的联动计划。"""

    recycle_trim_codes: dict[str, list[str]] = field(default_factory=dict)  # 底稿编码 → 导致移入的条目编码
    restore_codes: list[str] = field(default_factory=list)
    reopen_task_ids: set[UUID] = field(default_factory=set)
    targets: list[RecycleTarget] = field(default_factory=list)

    @property
    def substantive(self) -> list[RecycleTarget]:
        return [t for t in self.targets if t.substantive]

    def preview(self) -> dict:
        return {
            "to_recycle": sorted(self.recycle_trim_codes),
            "substantive": [t.to_dict() for t in self.substantive],
            "to_restore": sorted(self.restore_codes),
            "to_reopen_tasks": len(self.reopen_task_ids),
        }


async def _cascade_cancelled(db: AsyncSession, task_ids: list[UUID]) -> set[UUID]:
    """最近一条历史是「粗裁级联取消」的任务（细裁取消、别的原因取消的不算）。"""
    if not task_ids:
        return set()
    latest: dict[UUID, str] = {}
    rows = await db.execute(
        sa.select(ProcedureRowTaskHistory.task_id, ProcedureRowTaskHistory.event_type)
        .where(ProcedureRowTaskHistory.task_id.in_(task_ids))
        .order_by(ProcedureRowTaskHistory.created_at)
    )
    for task_id, event_type in rows.all():
        latest[task_id] = event_type
    return {tid for tid, ev in latest.items() if ev == CASCADE_EVENT}


async def plan_scope_linkage(
    db: AsyncSession, project_id: UUID, scope_plans: list[dict], coverage: ScopeCoverage | None
) -> ScopeLinkage:
    """按「应用后」的裁剪状态算出要移入 / 恢复的底稿、要重开的任务（只读）。"""
    linkage = ScopeLinkage()
    if not scope_plans or coverage is None:
        return linkage
    overrides = {inst.id: sp["target_status"] for sp in scope_plans for inst in sp["instances"]}
    after = coverage.simulate(overrides)
    reopen_candidates: list[UUID] = []
    for sp in scope_plans:
        entry_code = normalize_code(sp["entry"]["wp_index_code"])
        for row in coverage.covered(entry_code):
            trimmed = after.is_trimmed(row.wp_code)
            if trimmed and not row.is_deleted:
                linkage.recycle_trim_codes.setdefault(row.wp_code, []).append(entry_code)
            elif not trimmed and row.is_deleted and row.recycle_kind == KIND_TRIM:
                linkage.restore_codes.append(row.wp_code)
        if sp["target_status"] == "execute":
            for t in sp["cascade_tasks"]:
                code = coverage.code_of(t.wp_index_id)
                if t.workflow_status == WORKFLOW_CANCELLED and code and not after.is_trimmed(code):
                    reopen_candidates.append(t.id)
    linkage.restore_codes = sorted(set(linkage.restore_codes))
    linkage.reopen_task_ids = await _cascade_cancelled(db, sorted(set(reopen_candidates)))
    linkage.targets = await plan_recycle(db, project_id, linkage.recycle_trim_codes)
    return linkage


def ensure_confirmed(linkage: ScopeLinkage, confirmed: bool) -> None:
    """有实质内容的底稿要移入回收站、而用户没确认 ⇒ 409（写库前拦，预览凭证不消费，确认后可重试）。"""
    items = linkage.substantive
    if items and not confirmed:
        raise HTTPException(status_code=409, detail={
            "error": SUBSTANTIVE_UNCONFIRMED,
            "message": f"{len(items)} 张底稿已有编制内容，裁剪后将移入回收站，请确认后再保存",
            "codes": [t.wp_code for t in items],
            "substantive": [t.to_dict() for t in items],
        })


async def apply_linkage(
    db: AsyncSession,
    project_id: UUID,
    linkage: ScopeLinkage,
    *,
    actor_user_id: UUID | None,
    request_id: str | None,
    reasons: dict[str, str],
) -> dict:
    """裁剪状态写入之后执行：移入回收站 + 从回收站恢复。``reasons``：条目编码 → 裁剪理由。"""
    reasons = {normalize_code(k): v for k, v in reasons.items()}
    by_reason: dict[str, list[str]] = {}
    for wp_code, entry_codes in linkage.recycle_trim_codes.items():
        reason = "；".join(dict.fromkeys(reasons.get(c) or f"程序裁剪：{c} 标为不执行" for c in entry_codes))
        by_reason.setdefault(reason, []).append(wp_code)
    recycled: list[str] = []
    for reason, codes in by_reason.items():
        recycled += await move_to_recycle_bin(
            db, project_id, codes, kind=KIND_TRIM, reason=reason, actor_user_id=actor_user_id,
            trim_codes={c: linkage.recycle_trim_codes[c] for c in codes}, request_id=request_id,
        )
    restored = await restore_from_recycle_bin(
        db, project_id, linkage.restore_codes, kind=KIND_TRIM, reason="程序裁剪恢复执行",
        actor_user_id=actor_user_id, request_id=request_id,
    ) if linkage.restore_codes else []
    return {"recycled_codes": sorted(recycled), "restored_codes": sorted(restored)}
