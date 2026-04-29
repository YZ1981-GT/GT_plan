"""Phase 14: SoD 职责分离守卫服务

对齐 v2 WP-ENT-04 + 4.5.14 角色冲突与回避规则
编制/复核/签字/放行互斥矩阵 + 服务端强校验
"""
import uuid
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase14_enums import (
    SoDRole, TraceEventType, TraceObjectType, ReasonCode
)
from app.services.trace_event_service import trace_event_service, generate_trace_id

logger = logging.getLogger(__name__)

# SoD 互斥矩阵（对齐 v2 4.5.14）
# key: (已有角色, 目标角色) → 冲突描述
CONFLICT_MATRIX: dict[tuple[str, str], str] = {
    (SoDRole.preparer, SoDRole.partner_approver): "同人编制+终审同一底稿",
    (SoDRole.partner_approver, SoDRole.preparer): "同人编制+终审同一底稿",
    (SoDRole.preparer, SoDRole.reviewer): "经理复核本人编制底稿",
    (SoDRole.reviewer, SoDRole.preparer): "经理复核本人编制底稿",
    (SoDRole.qc_reviewer, SoDRole.preparer): "质控人员参与被抽查底稿修改",
    (SoDRole.preparer, SoDRole.qc_reviewer): "质控人员参与被抽查底稿修改",
}

# policy_code 映射
POLICY_CODES: dict[tuple[str, str], str] = {
    (SoDRole.preparer, SoDRole.partner_approver): "SOD_PREPARER_APPROVER_CONFLICT",
    (SoDRole.partner_approver, SoDRole.preparer): "SOD_PREPARER_APPROVER_CONFLICT",
    (SoDRole.preparer, SoDRole.reviewer): "SOD_PREPARER_REVIEWER_CONFLICT",
    (SoDRole.reviewer, SoDRole.preparer): "SOD_PREPARER_REVIEWER_CONFLICT",
    (SoDRole.qc_reviewer, SoDRole.preparer): "SOD_QC_PREPARER_CONFLICT",
    (SoDRole.preparer, SoDRole.qc_reviewer): "SOD_QC_PREPARER_CONFLICT",
}


@dataclass
class SoDCheckResult:
    allowed: bool
    conflict_type: Optional[str] = None
    policy_code: Optional[str] = None
    trace_id: str = ""


class SoDGuardService:
    """SoD 职责分离守卫"""

    async def check(
        self,
        db: AsyncSession,
        project_id: uuid.UUID,
        wp_id: uuid.UUID,
        actor_id: uuid.UUID,
        target_role: str,
    ) -> SoDCheckResult:
        """校验角色冲突

        1. 查询 actor_id 在该底稿上的已有角色
        2. 与 target_role 做互斥矩阵比对
        3. 冲突时写 trace_events
        """
        trace_id = generate_trace_id()

        # 延迟导入避免循环依赖
        from app.models.workpaper_models import WorkingPaper

        # 查询底稿的角色分配
        stmt = select(WorkingPaper).where(WorkingPaper.id == wp_id)
        result = await db.execute(stmt)
        wp = result.scalar_one_or_none()

        if not wp:
            return SoDCheckResult(allowed=True, trace_id=trace_id)

        # 收集 actor_id 在此底稿上的已有角色
        existing_roles: list[str] = []
        if hasattr(wp, 'preparer_id') and wp.preparer_id == actor_id:
            existing_roles.append(SoDRole.preparer)
        if hasattr(wp, 'reviewer_id') and wp.reviewer_id == actor_id:
            existing_roles.append(SoDRole.reviewer)
        if hasattr(wp, 'partner_reviewed_by') and wp.partner_reviewed_by == actor_id:
            existing_roles.append(SoDRole.partner_approver)

        # 检查互斥矩阵
        for existing_role in existing_roles:
            conflict_key = (existing_role, target_role)
            if conflict_key in CONFLICT_MATRIX:
                conflict_type = CONFLICT_MATRIX[conflict_key]
                policy_code = POLICY_CODES.get(conflict_key, "SOD_CONFLICT_DETECTED")

                # 写 trace_events
                await trace_event_service.write(
                    db=db,
                    project_id=project_id,
                    event_type=TraceEventType.sod_checked,
                    object_type=TraceObjectType.workpaper,
                    object_id=wp_id,
                    actor_id=actor_id,
                    action=f"sod_check:{existing_role}->{target_role}",
                    decision="block",
                    reason_code=ReasonCode.SOD_CONFLICT,
                    trace_id=trace_id,
                )

                logger.warning(
                    f"[SOD_CONFLICT] actor={actor_id} wp={wp_id} "
                    f"existing={existing_role} target={target_role} "
                    f"conflict={conflict_type} trace={trace_id}"
                )

                return SoDCheckResult(
                    allowed=False,
                    conflict_type=conflict_type,
                    policy_code=policy_code,
                    trace_id=trace_id,
                )

        # 无冲突
        await trace_event_service.write(
            db=db,
            project_id=project_id,
            event_type=TraceEventType.sod_checked,
            object_type=TraceObjectType.workpaper,
            object_id=wp_id,
            actor_id=actor_id,
            action=f"sod_check:none->{target_role}",
            decision="allow",
            trace_id=trace_id,
        )

        return SoDCheckResult(allowed=True, trace_id=trace_id)


# 全局单例
sod_guard_service = SoDGuardService()
