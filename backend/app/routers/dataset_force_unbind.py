"""F50 / Sprint 8.27: admin 双人授权的 force-unbind 接口（合规风险 6 缓解）。

一旦 AuditReport 转 final 并绑定 dataset，该 dataset 永远不能 rollback。
如果用户事后发现 dataset 数据实际有误（极低频），需要解开绑定重导：

本接口解决方案：
1. 必须 admin 角色
2. 必须另一名 admin 作"第二审批人"（双人授权）
3. 必须填写 reason（将进入 ActivationRecord 审计轨迹）
4. 解绑时同步：
   - 绑定到该 dataset 的 final/eqcr_approved AuditReport 退回 review 状态
     （撤销签字合规性，让用户重新复核+签字）
   - 清空 bound_dataset_id / dataset_bound_at
   - 写 ActivationRecord (action=force_unbind)
   - 记录 audit_logger（高危操作）

路由：POST /api/datasets/{dataset_id}/force-unbind
请求：{ "second_approver_id": "<uuid>", "reason": "数据错误需重导" }
响应：{ "unlocked_reports": [...], "dataset_id": "...", "unbind_record_id": "..." }
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_models import UnadjustedMisstatement
from app.models.core import User
from app.models.dataset_models import ActivationRecord, ActivationType, LedgerDataset
from app.models.report_models import AuditReport, DisclosureNote, ReportStatus
from app.models.workpaper_models import WorkingPaper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/datasets", tags=["数据集版本-合规操作"])


class ForceUnbindRequest(BaseModel):
    """双人授权 force-unbind 请求体。"""

    second_approver_id: UUID = Field(
        ...,
        description="第二审批人（必须是另一名 admin，不能与操作人相同）",
    )
    reason: str = Field(
        ...,
        min_length=5,
        description="解绑理由（必填，进入 ActivationRecord 审计轨迹）",
    )


class UnlockedReport(BaseModel):
    id: UUID
    previous_status: str
    new_status: str
    year: int


class ForceUnbindResponse(BaseModel):
    dataset_id: UUID
    unlocked_reports: list[UnlockedReport]
    unlocked_workpapers: int
    unlocked_disclosure_notes: int
    unlocked_misstatements: int
    unbind_record_id: UUID
    reason: str


@router.post("/{dataset_id}/force-unbind", response_model=ForceUnbindResponse)
async def force_unbind_dataset(
    dataset_id: UUID,
    payload: ForceUnbindRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ForceUnbindResponse:
    """F50 合规例外 — 强制解除下游对象的 dataset 绑定。

    使用场景：已签字定稿的审计报告，事后发现底层账套数据实际有误，
    需要 rollback 并重新签字。

    ⚠️ 高危操作：
    - 所有绑定该 dataset 的 final / eqcr_approved 报表会被退回 review 状态
      （撤销签字合规性）
    - 底稿 / 附注 / 错报的 bound_dataset_id 会被清空
    - 操作完成后用户需要重新走完 EQCR 复核 + 签字流程

    安全约束：
    - 操作人必须是 admin
    - 必须提供第二审批人（另一名 admin，不能与操作人相同）
    - 必须填写 reason（≥5 字符）
    """
    # 1. 权限校验：操作人必须是 admin
    operator_role = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    if operator_role != "admin":
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "ADMIN_ONLY",
                "message": "force-unbind 是合规高危操作，仅 admin 可执行",
            },
        )

    # 2. 第二审批人必须存在 + 必须是 admin + 不能是操作人
    if payload.second_approver_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "SECOND_APPROVER_SAME_AS_OPERATOR",
                "message": "第二审批人不能与操作人相同（双人授权原则）",
            },
        )

    second = (
        await db.execute(
            sa.select(User).where(
                User.id == payload.second_approver_id,
                User.is_deleted == sa.false(),
                User.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if second is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "SECOND_APPROVER_NOT_FOUND",
                "message": "第二审批人不存在或已停用",
            },
        )
    second_role = (
        second.role.value if hasattr(second.role, "value") else str(second.role)
    )
    if second_role != "admin":
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "SECOND_APPROVER_NOT_ADMIN",
                "message": "第二审批人必须是 admin 角色",
            },
        )

    # 3. 确认数据集存在
    dataset = (
        await db.execute(
            sa.select(LedgerDataset).where(LedgerDataset.id == dataset_id)
        )
    ).scalar_one_or_none()
    if dataset is None:
        raise HTTPException(status_code=404, detail="数据集不存在")

    # 4. 找到所有绑定该 dataset 的下游对象
    bound_reports_rows = (
        await db.execute(
            sa.select(AuditReport)
            .where(
                AuditReport.bound_dataset_id == dataset_id,
                AuditReport.is_deleted == sa.false(),
            )
        )
    ).scalars().all()

    bound_wps = (
        await db.execute(
            sa.select(WorkingPaper)
            .where(
                WorkingPaper.bound_dataset_id == dataset_id,
                WorkingPaper.is_deleted == sa.false(),
            )
        )
    ).scalars().all()

    bound_notes = (
        await db.execute(
            sa.select(DisclosureNote)
            .where(
                DisclosureNote.bound_dataset_id == dataset_id,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
    ).scalars().all()

    bound_misstatements = (
        await db.execute(
            sa.select(UnadjustedMisstatement)
            .where(
                UnadjustedMisstatement.bound_dataset_id == dataset_id,
                UnadjustedMisstatement.is_deleted == sa.false(),
            )
        )
    ).scalars().all()

    # 5. 逐一解绑 + 撤销报表签字
    unlocked_reports: list[UnlockedReport] = []
    for report in bound_reports_rows:
        prev_status = (
            report.status.value
            if hasattr(report.status, "value")
            else str(report.status)
        )
        # final / eqcr_approved → review（撤销签字）
        if report.status in (ReportStatus.final, ReportStatus.eqcr_approved):
            report.status = ReportStatus.review
            unlocked_reports.append(
                UnlockedReport(
                    id=report.id,
                    previous_status=prev_status,
                    new_status=ReportStatus.review.value,
                    year=report.year,
                )
            )
        report.bound_dataset_id = None
        report.dataset_bound_at = None

    for wp in bound_wps:
        wp.bound_dataset_id = None
        wp.dataset_bound_at = None

    for note in bound_notes:
        note.bound_dataset_id = None
        note.dataset_bound_at = None

    for mis in bound_misstatements:
        mis.bound_dataset_id = None
        mis.dataset_bound_at = None

    # 6. 写 ActivationRecord 审计轨迹
    client_ip = None
    if request and request.client:
        client_ip = request.client.host
    audit_details = {
        "second_approver_id": str(payload.second_approver_id),
        "second_approver_username": second.username,
        "unlocked_reports": [
            {
                "id": str(r.id),
                "previous_status": r.previous_status,
                "new_status": r.new_status,
                "year": r.year,
            }
            for r in unlocked_reports
        ],
        "unlocked_workpapers": len(bound_wps),
        "unlocked_disclosure_notes": len(bound_notes),
        "unlocked_misstatements": len(bound_misstatements),
    }

    record = ActivationRecord(
        id=uuid.uuid4(),
        project_id=dataset.project_id,
        year=dataset.year,
        dataset_id=dataset_id,
        action=ActivationType.force_unbind,
        previous_dataset_id=dataset.previous_dataset_id,
        performed_by=current_user.id,
        reason=payload.reason,
        ip_address=client_ip,
        # 把双人授权元信息放进 after_row_counts（JSONB 字段）
        # 避免为该合规例外新增专用列
        after_row_counts=audit_details,
    )
    db.add(record)

    # 7. 高危操作审计日志（哈希链）
    try:
        from app.services.audit_logger_enhanced import audit_logger

        await audit_logger.log_action(
            user_id=current_user.id,
            action="dataset.force_unbind",
            object_type="ledger_dataset",
            object_id=dataset_id,
            project_id=dataset.project_id,
            details={
                "second_approver_id": str(payload.second_approver_id),
                "reason": payload.reason,
                "impact_counts": {
                    "reports_unlocked": len(unlocked_reports),
                    "workpapers_unbound": len(bound_wps),
                    "notes_unbound": len(bound_notes),
                    "misstatements_unbound": len(bound_misstatements),
                },
            },
            ip_address=client_ip,
        )
    except Exception as log_err:  # 审计日志失败不能阻断主流程
        logger.warning(
            "force-unbind audit log failed: dataset=%s err=%s",
            dataset_id, log_err,
        )

    await db.flush()
    await db.commit()

    logger.warning(
        "FORCE_UNBIND: dataset=%s operator=%s second_approver=%s "
        "reports_unlocked=%d wps=%d notes=%d misstatements=%d reason=%r",
        dataset_id,
        current_user.id,
        payload.second_approver_id,
        len(unlocked_reports),
        len(bound_wps),
        len(bound_notes),
        len(bound_misstatements),
        payload.reason,
    )

    return ForceUnbindResponse(
        dataset_id=dataset_id,
        unlocked_reports=unlocked_reports,
        unlocked_workpapers=len(bound_wps),
        unlocked_disclosure_notes=len(bound_notes),
        unlocked_misstatements=len(bound_misstatements),
        unbind_record_id=record.id,
        reason=payload.reason,
    )
