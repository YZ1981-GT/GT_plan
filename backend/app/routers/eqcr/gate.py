"""EQCR 审批门禁 + 意见解锁"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.eqcr_service import EqcrService

from .schemas import EqcrApproveRequest, EqcrUnlockOpinionRequest

router = APIRouter()


@router.post("/projects/{project_id}/approve")
async def eqcr_approve(
    project_id: UUID,
    payload: EqcrApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 审批入口（需求 5）。"""
    from app.models.eqcr_models import EqcrDisagreementResolution, EqcrOpinion
    from app.models.extension_models import SignatureRecord
    from app.models.phase14_enums import GateDecisionResult, GateType
    from app.models.report_models import AuditReport, ReportStatus
    from app.services.gate_engine import gate_engine

    if payload.verdict not in ("approve", "disagree"):
        raise HTTPException(
            status_code=400,
            detail="verdict 必须为 'approve' 或 'disagree'",
        )

    svc = EqcrService(db)
    is_eqcr = await svc._is_user_eqcr_on(current_user.id, project_id)
    if not is_eqcr:
        raise HTTPException(
            status_code=403,
            detail="当前用户不是该项目的 EQCR，无权审批",
        )

    ar_q = (
        select(AuditReport)
        .where(
            AuditReport.project_id == project_id,
            AuditReport.is_deleted == False,  # noqa: E712
        )
        .order_by(AuditReport.year.desc())
        .limit(1)
    )
    audit_report = (await db.execute(ar_q)).scalar_one_or_none()
    if audit_report is None:
        raise HTTPException(status_code=404, detail="该项目无审计报告")

    current_status = (
        audit_report.status.value
        if hasattr(audit_report.status, "value")
        else str(audit_report.status)
    )
    if current_status != ReportStatus.review.value:
        raise HTTPException(
            status_code=400,
            detail=f"审计报告当前状态为 '{current_status}'，只有 'review' 状态才能进行 EQCR 审批",
        )

    if payload.verdict == "approve":
        gate_result = await gate_engine.evaluate(
            db=db,
            gate_type=GateType.eqcr_approval,
            project_id=project_id,
            wp_id=None,
            actor_id=current_user.id,
            context={
                "action": "eqcr_approve",
                "comment": payload.comment,
            },
        )

        if gate_result.decision == GateDecisionResult.block:
            blocking_rules = [
                {
                    "rule_code": h.rule_code,
                    "error_code": h.error_code,
                    "message": h.message,
                    "suggested_action": h.suggested_action,
                }
                for h in gate_result.hit_rules
                if h.severity == "blocking"
            ]
            raise HTTPException(
                status_code=422,
                detail={
                    "error_code": "EQCR_GATE_BLOCKED",
                    "message": "EQCR 审批门禁未通过",
                    "blocking_rules": blocking_rules,
                    "trace_id": gate_result.trace_id,
                },
            )

        audit_report.status = ReportStatus.eqcr_approved
        audit_report.updated_by = current_user.id

        sig = SignatureRecord(
            object_type="audit_report",
            object_id=audit_report.id,
            signer_id=current_user.id,
            signature_level="eqcr",
            required_order=4,
            required_role="eqcr",
            signature_data={
                "verdict": "approve",
                "comment": payload.comment,
                "shadow_comp_refs": [str(r) for r in payload.shadow_comp_refs]
                if payload.shadow_comp_refs
                else None,
                "attached_opinion_ids": [str(r) for r in payload.attached_opinion_ids]
                if payload.attached_opinion_ids
                else None,
            },
            signature_timestamp=datetime.now(timezone.utc),
        )
        db.add(sig)
        await db.commit()

        return {
            "status": "approved",
            "report_status": ReportStatus.eqcr_approved.value,
            "gate_decision": gate_result.decision,
            "trace_id": gate_result.trace_id,
            "signature_id": str(sig.id),
        }

    else:
        disagree_opinion = (
            await db.execute(
                select(EqcrOpinion)
                .where(
                    EqcrOpinion.project_id == project_id,
                    EqcrOpinion.verdict == "disagree",
                    EqcrOpinion.is_deleted == False,  # noqa: E712
                )
                .order_by(EqcrOpinion.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if disagree_opinion is None:
            disagree_opinion = EqcrOpinion(
                project_id=project_id,
                domain="opinion_type",
                verdict="disagree",
                comment=payload.comment,
                created_by=current_user.id,
            )
            db.add(disagree_opinion)
            await db.flush()

        resolution = EqcrDisagreementResolution(
            project_id=project_id,
            eqcr_opinion_id=disagree_opinion.id,
            participants=[str(current_user.id)],
            resolution=None,
            resolution_verdict=None,
            resolved_at=None,
        )
        db.add(resolution)
        await db.commit()
        await db.refresh(resolution)

        return {
            "status": "disagreed",
            "report_status": current_status,
            "disagreement_resolution_id": str(resolution.id),
            "opinion_id": str(disagree_opinion.id),
            "message": "EQCR 异议已记录，请启动合议流程",
        }


@router.post("/projects/{project_id}/unlock-opinion")
async def eqcr_unlock_opinion(
    project_id: UUID,
    payload: EqcrUnlockOpinionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """EQCR 显式回退审计报告到 review 态（需求 6.4）。"""
    from app.models.report_models import AuditReport, ReportStatus
    from app.services.audit_logger_enhanced import audit_logger

    svc = EqcrService(db)
    is_eqcr = await svc._is_user_eqcr_on(current_user.id, project_id)
    if not is_eqcr:
        raise HTTPException(
            status_code=403,
            detail="当前用户不是该项目的 EQCR，无权解锁",
        )

    ar_q = (
        select(AuditReport)
        .where(
            AuditReport.project_id == project_id,
            AuditReport.is_deleted == False,  # noqa: E712
        )
        .order_by(AuditReport.year.desc())
        .limit(1)
    )
    audit_report = (await db.execute(ar_q)).scalar_one_or_none()
    if audit_report is None:
        raise HTTPException(status_code=404, detail="该项目无审计报告")

    current_status = (
        audit_report.status.value
        if hasattr(audit_report.status, "value")
        else str(audit_report.status)
    )
    if current_status != ReportStatus.eqcr_approved.value:
        raise HTTPException(
            status_code=400,
            detail=f"审计报告当前状态为 '{current_status}'，只有 'eqcr_approved' 状态才能回退",
        )

    audit_report.status = ReportStatus.review
    audit_report.updated_by = current_user.id

    await audit_logger.log_action(
        user_id=current_user.id,
        action="eqcr_unlock_opinion",
        object_type="audit_report",
        object_id=audit_report.id,
        project_id=project_id,
        details={
            "reason": payload.reason,
            "previous_status": ReportStatus.eqcr_approved.value,
            "new_status": ReportStatus.review.value,
        },
    )

    await db.commit()

    return {
        "status": "unlocked",
        "report_status": ReportStatus.review.value,
        "reason": payload.reason,
        "message": "审计报告已回退到 review 状态，意见类型和段落已解锁",
    }
