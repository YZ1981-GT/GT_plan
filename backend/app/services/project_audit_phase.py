"""项目当前审计阶段与预审截止日（spec voucher-identity-writeback-and-audit-phase 任务 8，需求 6.1 / 6.2 / 6.5，ADR-VK-09）。

阶段是项目的事实，不再由抽凭引擎的宿主各写一个字面量：抽凭、挂凭、挂凭回拉生成的行缺省按
``projects.current_audit_phase`` 标阶段（V212，缺省 final）。只接受 preliminary / final 两个值。

改动只走 ``PUT /api/projects/{id}/audit-phase``（routers/project_audit_phase.py）：项目经理、合伙人
（含签字合伙人）与 admin 可改 —— 与程序行委派人同一判定（procedure_authorization.ensure_project_delegator，
按项目委派角色），改动写 app_audit_log（动作 project.audit_phase.change）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project

logger = logging.getLogger(__name__)

AuditPhase = Literal["preliminary", "final"]
AUDIT_PHASES: tuple[str, ...] = ("preliminary", "final")
DEFAULT_AUDIT_PHASE = "final"
AUDIT_LOG_ACTION = "project.audit_phase.change"


@dataclass(frozen=True)
class ProjectAuditPhase:
    phase: str
    interim_cutoff_date: date | None
    audit_period_start: date | None
    audit_period_end: date | None

    def to_dict(self) -> dict:
        return {
            "current_audit_phase": self.phase,
            "interim_cutoff_date": self.interim_cutoff_date.isoformat() if self.interim_cutoff_date else None,
            "audit_period_start": self.audit_period_start.isoformat() if self.audit_period_start else None,
            "audit_period_end": self.audit_period_end.isoformat() if self.audit_period_end else None,
        }


async def load_project_audit_phase(db: AsyncSession, project_id: UUID) -> ProjectAuditPhase:
    """阶段 + 预审截止日 + 审计期间。向导只填了审计年度、没填期间的项目，期间按该年度 1 月 1 日至 12 月 31 日。"""
    row = (await db.execute(
        sa.select(Project.current_audit_phase, Project.interim_cutoff_date,
                  Project.audit_period_start, Project.audit_period_end, Project.audit_year)
        .where(Project.id == project_id, Project.is_deleted == False)  # noqa: E712
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    phase = row.current_audit_phase if row.current_audit_phase in AUDIT_PHASES else DEFAULT_AUDIT_PHASE
    start, end = row.audit_period_start, row.audit_period_end
    if row.audit_year:
        start = start or date(row.audit_year, 1, 1)
        end = end or date(row.audit_year, 12, 31)
    return ProjectAuditPhase(phase, row.interim_cutoff_date, start, end)


async def project_phase(db: AsyncSession, project_id: UUID) -> str:
    """项目当前阶段：抽凭、挂凭、挂凭回拉在请求没给阶段时用它。"""
    return (await load_project_audit_phase(db, project_id)).phase


def validate_interim_cutoff(cutoff: date | None, start: date | None, end: date | None) -> None:
    """预审截止日须落在审计期间内，且早于期末（截止日之后要留出年审剩余期间）。"""
    if cutoff is None:
        return
    if start is not None and cutoff < start:
        raise HTTPException(status_code=422, detail={
            "error_code": "INTERIM_CUTOFF_OUT_OF_PERIOD",
            "message": f"预审截止日 {cutoff.isoformat()} 早于审计期间开始日 {start.isoformat()}",
        })
    if end is not None and cutoff >= end:
        raise HTTPException(status_code=422, detail={
            "error_code": "INTERIM_CUTOFF_OUT_OF_PERIOD",
            "message": f"预审截止日须早于审计期间结束日 {end.isoformat()}（截止日之后是年审的剩余期间）",
        })


async def _write_audit_log(db: AsyncSession, *, actor_id: UUID, project_id: UUID, old: dict, new: dict) -> None:
    """写 app_audit_log（与 project_wizard 改上级代码同一做法）：放进 SAVEPOINT，写失败只回滚这一步。

    app_audit_log 是 PG 表（gen_random_uuid / jsonb），SQLite 测试库没有它，失败记 warning 不阻断。
    """
    try:
        async with db.begin_nested():
            await db.execute(
                sa.text(
                    "INSERT INTO app_audit_log (id, user_id, action, resource_type, resource_id, details, created_at) "
                    "VALUES (gen_random_uuid(), :user_id, :action, 'project', :resource_id, "
                    "CAST(:details AS jsonb), :now)"
                ),
                {
                    "user_id": str(actor_id),
                    "action": AUDIT_LOG_ACTION,
                    "resource_id": str(project_id),
                    "details": json.dumps({"old": old, "new": new}, ensure_ascii=False),
                    "now": datetime.now(timezone.utc),
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("审计阶段变更审计日志写入失败（不阻断）：project=%s err=%s", project_id, exc)


async def update_project_audit_phase(
    db: AsyncSession,
    project_id: UUID,
    *,
    phase: str,
    interim_cutoff_date: date | None,
    actor_id: UUID,
) -> bool:
    """改阶段与预审截止日（调用方已判权限）；只 flush，由路由 commit。返回是否有改动。"""
    if phase not in AUDIT_PHASES:
        raise HTTPException(status_code=422, detail=f"审计阶段只能是 {' / '.join(AUDIT_PHASES)}")
    state = await load_project_audit_phase(db, project_id)
    validate_interim_cutoff(interim_cutoff_date, state.audit_period_start, state.audit_period_end)
    project = await db.get(Project, project_id)
    old = {"current_audit_phase": project.current_audit_phase,
           "interim_cutoff_date": project.interim_cutoff_date.isoformat() if project.interim_cutoff_date else None}
    new = {"current_audit_phase": phase,
           "interim_cutoff_date": interim_cutoff_date.isoformat() if interim_cutoff_date else None}
    if old == new:
        return False
    project.current_audit_phase = phase
    project.interim_cutoff_date = interim_cutoff_date
    await db.flush()
    await _write_audit_log(db, actor_id=actor_id, project_id=project_id, old=old, new=new)
    return True
