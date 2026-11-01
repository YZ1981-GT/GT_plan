"""底稿提交复核的唯一业务编排。服务只 flush，事务由 router 持有。"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import AIConfirmationStatus, AIContent
from app.models.core import Project
from app.models.procedure_models import ProcedureInstance
from app.models.workpaper_models import (
    ReviewCommentStatus,
    ReviewRecord,
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpQcResult,
    WpReviewStatus,
)
from app.services.working_paper_service import WorkingPaperService


class ReviewSubmissionUnavailable(RuntimeError):
    """提交门禁基础设施不可用；必须失败关闭，不能降级放行。"""


async def assert_review_level_actor(
    db: AsyncSession, *, project_id: UUID, wp_id: UUID,
    new_review_status: str, actor,
) -> None:
    """按项目复核配置校验当前层角色和指定复核人。admin 可应急处理。"""
    row = (await db.execute(
        sa.select(WorkingPaper, Project).join(Project, Project.id == WorkingPaper.project_id).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == sa.false(),
            Project.is_deleted == sa.false(),
        )
    )).first()
    if row is None:
        raise LookupError("底稿不存在")
    wp, project = row
    actual_role = getattr(getattr(actor, "role", None), "value", getattr(actor, "role", ""))
    if actual_role == "admin":
        return

    import re
    match = re.search(r"level(\d+)", new_review_status)
    if match is None:
        current = getattr(getattr(wp, "review_status", None), "value", "")
        match = re.search(r"level(\d+)", current)
    if match is None:
        raise PermissionError("无法确定当前复核层级")
    level = int(match.group(1))
    config = project.review_config if isinstance(project.review_config, dict) else {}
    roles = config.get("level_roles") if isinstance(config.get("level_roles"), dict) else {}
    expected = str(roles.get(f"L{level}") or ("manager" if level == 1 else "partner"))
    if actual_role != expected:
        role_label = {
            "manager": "经理", "partner": "合伙人", "qc": "质控",
            "eqcr": "EQCR", "auditor": "审计员",
        }.get(expected, expected)
        raise PermissionError(f"当前为 L{level} 复核，仅允许项目{role_label}角色处理")

    designated = None
    if level == 1 and wp.reviewer is not None:
        designated = wp.reviewer
    elif expected == "manager":
        designated = project.manager_id
    elif expected == "partner":
        designated = project.partner_id
    if designated is not None and actor.id != designated:
        raise PermissionError(f"当前账号不是 L{level} 指定复核人")


@dataclass(frozen=True)
class ReviewSubmissionResult:
    can_submit: bool
    status: str
    blocking_reasons: tuple[str, ...] = ()
    hit_rules: tuple[dict, ...] = ()
    trace_id: str | None = None
    wp_status: str | None = None
    review_status: str | None = None

    def as_dict(self) -> dict:
        result = {
            "status": self.status,
            "can_submit": self.can_submit,
            "blocking_reasons": list(self.blocking_reasons),
        }
        if self.hit_rules:
            result["hit_rules"] = list(self.hit_rules)
        if self.trace_id:
            result["trace_id"] = self.trace_id
        if self.wp_status is not None:
            result["wp_status"] = self.wp_status
        if self.review_status is not None:
            result["review_status"] = self.review_status
        return result


class WorkpaperReviewSubmissionService:
    """单笔和批量入口共用的提交复核服务。"""

    async def submit(
        self, db: AsyncSession, *, project_id: UUID, wp_id: UUID, actor_id: UUID,
    ) -> ReviewSubmissionResult:
        wp = (await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == sa.false(),
            ).with_for_update()
        )).scalar_one_or_none()
        if wp is None:
            raise LookupError("底稿不存在")

        allowed_file_states = {
            WpFileStatus.draft, WpFileStatus.edit_complete, WpFileStatus.revision_required,
        }
        if wp.status not in allowed_file_states:
            current = wp.status.value if wp.status else "unknown"
            raise ValueError(f"当前编制状态 {current} 不允许提交复核")
        current_review = wp.review_status or WpReviewStatus.not_submitted
        if current_review != WpReviewStatus.not_submitted and "rejected" not in current_review.value:
            raise ValueError(f"当前复核状态 {current_review.value} 不允许重复提交")

        gate_result = await self._evaluate_gate(db, project_id, wp, actor_id)
        if gate_result is not None:
            return gate_result
        await self._assert_sod(db, project_id, wp_id, actor_id)
        blockers = await self._blocking_reasons(db, project_id, wp)
        if blockers:
            return ReviewSubmissionResult(False, "blocked", tuple(blockers))

        # “提交复核”本身就是显式完成编制；退回修订在此归一后直接重提。
        wp.status = WpFileStatus.edit_complete
        wp.review_status = WpReviewStatus.not_submitted
        transition = await WorkingPaperService().update_review_status(
            db=db, wp_id=wp_id, new_review_status="pending_level1", project_id=project_id,
        )
        await self._complete_program(db, project_id, wp.wp_index_id)
        await db.flush()
        return ReviewSubmissionResult(
            True, "submitted", (), (), None,
            transition.get("status"), transition.get("review_status"),
        )

    async def _evaluate_gate(
        self, db: AsyncSession, project_id: UUID, wp: WorkingPaper, actor_id: UUID,
    ) -> ReviewSubmissionResult | None:
        try:
            from app.services.gate_engine import gate_engine

            result = await gate_engine.evaluate(
                db=db,
                gate_type="submit_review",
                project_id=project_id,
                wp_id=wp.id,
                actor_id=actor_id,
                context={"wp_status": WpFileStatus.edit_complete, "year": getattr(wp, "year", None)},
            )
        except Exception as exc:
            raise ReviewSubmissionUnavailable("统一提交门禁暂时不可用，请稍后重试") from exc
        if result.decision != "block":
            return None
        hits = tuple(
            {
                "rule_code": hit.rule_code,
                "error_code": hit.error_code,
                "severity": hit.severity,
                "message": hit.message,
                "location": hit.location,
                "suggested_action": hit.suggested_action,
            }
            for hit in result.hit_rules
        )
        reasons = tuple(
            f"[{hit.rule_code}] {hit.message}"
            for hit in result.hit_rules if hit.severity == "blocking"
        )
        return ReviewSubmissionResult(
            False, "blocked", reasons, hits, str(result.trace_id) if result.trace_id else None,
        )

    async def _assert_sod(
        self, db: AsyncSession, project_id: UUID, wp_id: UUID, actor_id: UUID,
    ) -> None:
        try:
            from app.services.sod_guard_service import sod_guard_service

            result = await sod_guard_service.check(
                db=db, project_id=project_id, wp_id=wp_id,
                actor_id=actor_id, target_role="reviewer",
            )
        except Exception as exc:
            raise ReviewSubmissionUnavailable("职责分离校验暂时不可用，请稍后重试") from exc
        if not result.allowed:
            raise PermissionError(result.conflict_type or "职责分离校验未通过")

    async def _blocking_reasons(
        self, db: AsyncSession, project_id: UUID, wp: WorkingPaper,
    ) -> list[str]:
        reasons: list[str] = []
        if not wp.reviewer:
            reasons.append("复核人未分配")

        qc = (await db.execute(
            sa.select(WpQcResult).where(WpQcResult.working_paper_id == wp.id)
            .order_by(WpQcResult.check_timestamp.desc()).limit(1)
        )).scalar_one_or_none()
        if qc is None:
            reasons.append("未执行质量自检")
        elif qc.blocking_count > 0:
            reasons.append(f"存在 {qc.blocking_count} 个阻断级 QC 问题")

        from app.models.phase10_models import CellAnnotation
        unresolved = (await db.execute(
            sa.select(sa.func.count()).select_from(CellAnnotation).where(
                CellAnnotation.project_id == project_id,
                CellAnnotation.object_type == "workpaper",
                CellAnnotation.object_id == wp.id,
                CellAnnotation.status != "resolved",
                CellAnnotation.is_deleted == sa.false(),
            )
        )).scalar() or 0
        if unresolved:
            reasons.append(f"{unresolved} 条未解决复核意见")

        ai_pending = (await db.execute(
            sa.select(sa.func.count()).select_from(AIContent).where(
                AIContent.project_id == project_id,
                AIContent.workpaper_id == wp.id,
                AIContent.confirmation_status == AIConfirmationStatus.pending,
                AIContent.is_deleted == sa.false(),
            )
        )).scalar() or 0
        if ai_pending:
            reasons.append(f"{ai_pending} 项未确认的 AI 生成内容")

        open_reviews = (await db.execute(
            sa.select(sa.func.count()).select_from(ReviewRecord).where(
                ReviewRecord.working_paper_id == wp.id,
                ReviewRecord.status == ReviewCommentStatus.open,
                ReviewRecord.is_deleted == sa.false(),
            )
        )).scalar() or 0
        if open_reviews:
            reasons.append(f"{open_reviews} 条复核意见未回复（状态仍为 open）")
        return reasons

    @staticmethod
    async def _complete_program(db: AsyncSession, project_id: UUID, wp_index_id: UUID) -> None:
        wp_code = (await db.execute(
            sa.select(WpIndex.wp_code).where(WpIndex.id == wp_index_id)
        )).scalar_one_or_none()
        if not wp_code:
            return
        await db.execute(
            sa.update(ProcedureInstance).where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.wp_code == wp_code,
                ProcedureInstance.is_deleted == sa.false(),
            ).values(execution_status="completed")
        )
