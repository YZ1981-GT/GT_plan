"""合伙人视角 API — 多项目风控总览 / 签字前检查 / 团队效能"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.core import User
from app.services.partner_service import (
    PartnerOverviewService,
    SignReadinessService,
    TeamEfficiencyService,
)

router = APIRouter(tags=["partner-dashboard"])


@router.get("/api/partner/overview")
async def get_partner_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """合伙人全局总览 — 我负责的所有项目+风险预警+待签字"""
    svc = PartnerOverviewService(db)
    return await svc.get_my_projects_overview(current_user.id)


@router.get("/api/projects/{project_id}/sign-readiness")
async def check_sign_readiness(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """签字前 8 项检查"""
    svc = SignReadinessService(db)
    return await svc.check_sign_readiness(project_id)


@router.post("/api/projects/{project_id}/partner/workpaper-readiness")
async def check_workpaper_readiness(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("review")),
):
    """Phase 12 P1-7: 签字前底稿专项检查（5项）+ Phase 14 门禁引擎"""
    # Phase 14: 统一门禁引擎评估（sign_off）
    gate_result_data = None
    try:
        from app.services.gate_engine import gate_engine as _gate_engine
        gate_result = await _gate_engine.evaluate(
            db=db,
            gate_type="sign_off",
            project_id=project_id,
            wp_id=None,
            actor_id=current_user.id,
            context={},
        )
        gate_result_data = {
            "gate_decision": gate_result.decision,
            "gate_hit_rules": [
                {
                    "rule_code": h.rule_code,
                    "error_code": h.error_code,
                    "severity": h.severity,
                    "message": h.message,
                    "suggested_action": h.suggested_action,
                }
                for h in gate_result.hit_rules
            ],
            "gate_trace_id": gate_result.trace_id,
        }
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning(f"[GATE] sign_off gate eval failed: {_e}")

    svc = SignReadinessService(db)
    readiness = await svc.check_workpaper_readiness(project_id)

    # 合并门禁结果
    if gate_result_data:
        readiness["gate_engine"] = gate_result_data

    return readiness


@router.get("/api/partner/team-efficiency")
async def get_team_efficiency(
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """团队效能分析"""
    svc = TeamEfficiencyService(db)
    return await svc.get_team_efficiency(current_user.id, days)
