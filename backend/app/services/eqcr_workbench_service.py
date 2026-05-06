"""EQCR 工作台服务 — 项目列表与总览聚合

从 eqcr_service.py 拆分而来，包含：
- list_my_projects
- get_project_overview
- 相关私有辅助方法
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any, Iterable

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collaboration_models import MilestoneType, ProjectTimeline
from app.models.core import Project
from app.models.eqcr_models import (
    EqcrDisagreementResolution,
    EqcrOpinion,
    EqcrReviewNote,
    EqcrShadowComputation,
)
from app.models.report_models import AuditReport, ReportStatus
from app.models.staff_models import ProjectAssignment, StaffMember

_logger = logging.getLogger(__name__)


# EQCR 工作台基础 5 个判断域（与 requirements.md 需求 2 对齐）
EQCR_CORE_DOMAINS: tuple[str, ...] = (
    "materiality",
    "estimate",
    "related_party",
    "going_concern",
    "opinion_type",
)

# 进度枚举（前后端约定，存字符串）
PROGRESS_NOT_STARTED = "not_started"
PROGRESS_IN_PROGRESS = "in_progress"
PROGRESS_APPROVED = "approved"
PROGRESS_DISAGREE = "disagree"


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _today() -> date:
    """抽出便于测试 mock。"""
    return date.today()


def _days_between(target: date | None, origin: date | None = None) -> int | None:
    if target is None:
        return None
    origin = origin or _today()
    return (target - origin).days


def _classify_progress(opinion_rows: Iterable[EqcrOpinion], report_status: str | None) -> str:
    """根据 opinion 集合 + 报告状态归类 EQCR 进度。"""
    rows = list(opinion_rows)
    if not rows:
        return PROGRESS_NOT_STARTED

    if any(op.verdict == "disagree" for op in rows):
        return PROGRESS_DISAGREE

    reviewed_domains = {op.domain for op in rows if op.domain in EQCR_CORE_DOMAINS}
    all_agree = all(
        op.verdict == "agree"
        for op in rows
        if op.domain in EQCR_CORE_DOMAINS
    )
    if (
        reviewed_domains == set(EQCR_CORE_DOMAINS)
        and all_agree
        and report_status in (ReportStatus.eqcr_approved.value, ReportStatus.final.value)
    ):
        return PROGRESS_APPROVED

    return PROGRESS_IN_PROGRESS


# ---------------------------------------------------------------------------
# 主服务
# ---------------------------------------------------------------------------


class EqcrWorkbenchService:
    """EQCR 工作台查询服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 基础查询
    # ------------------------------------------------------------------

    async def _resolve_staff_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """由 ``User.id`` 解析出对应 ``StaffMember.id`` 集合（一人一般一条）。"""
        q = select(StaffMember.id).where(
            StaffMember.user_id == user_id,
            StaffMember.is_deleted == False,  # noqa: E712
        )
        rows = (await self.db.execute(q)).scalars().all()
        return list(rows)

    async def _is_user_eqcr_on(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> bool:
        """判断当前用户在项目中是否是 EQCR。"""
        q = (
            select(func.count(ProjectAssignment.id))
            .select_from(ProjectAssignment)
            .join(StaffMember, ProjectAssignment.staff_id == StaffMember.id)
            .where(
                ProjectAssignment.project_id == project_id,
                ProjectAssignment.role == "eqcr",
                ProjectAssignment.is_deleted == False,  # noqa: E712
                StaffMember.user_id == user_id,
                StaffMember.is_deleted == False,  # noqa: E712
            )
        )
        count = (await self.db.execute(q)).scalar() or 0
        return count > 0

    async def _resolve_signing_date(self, project: Project) -> date | None:
        """按优先级解析签字日。"""
        # 1) AuditReport.report_date
        ar_q = (
            select(AuditReport.report_date)
            .where(
                AuditReport.project_id == project.id,
                AuditReport.is_deleted == False,  # noqa: E712
            )
            .order_by(AuditReport.year.desc())
            .limit(1)
        )
        ar_date = (await self.db.execute(ar_q)).scalar()
        if ar_date:
            return ar_date

        # 2) ProjectTimeline milestone_type=REPORT planned_date
        tl_q = (
            select(ProjectTimeline.planned_date)
            .where(
                ProjectTimeline.project_id == project.id,
                ProjectTimeline.milestone_type == MilestoneType.REPORT,
                ProjectTimeline.is_deleted == False,  # noqa: E712
            )
            .order_by(ProjectTimeline.planned_date.asc())
            .limit(1)
        )
        tl_date = (await self.db.execute(tl_q)).scalar()
        if tl_date:
            return tl_date

        # 3) 兜底 audit_period_end
        return project.audit_period_end

    async def _get_report_status(self, project_id: uuid.UUID) -> str | None:
        """取 ``AuditReport.status``（最新年度），无报告则 ``None``。"""
        q = (
            select(AuditReport.status)
            .where(
                AuditReport.project_id == project_id,
                AuditReport.is_deleted == False,  # noqa: E712
            )
            .order_by(AuditReport.year.desc())
            .limit(1)
        )
        status = (await self.db.execute(q)).scalar()
        if status is None:
            return None
        # status 可能是 enum，也可能是字符串（SQLite 测试环境下）
        return status.value if hasattr(status, "value") else str(status)

    async def _get_core_opinions(
        self, project_id: uuid.UUID
    ) -> list[EqcrOpinion]:
        """取项目所有 active 的 EQCR 意见（所有 domain）。"""
        q = (
            select(EqcrOpinion)
            .where(
                EqcrOpinion.project_id == project_id,
                EqcrOpinion.is_deleted == False,  # noqa: E712
            )
            .order_by(EqcrOpinion.created_at.asc())
        )
        return list((await self.db.execute(q)).scalars().all())

    # ------------------------------------------------------------------
    # 公开接口 1：列出本人 EQCR 项目
    # ------------------------------------------------------------------

    async def list_my_projects(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """返回本人作为 EQCR 的项目列表（排序按签字日升序，无签字日的排后面）。

        优化：批量查询 AuditReport 和 EqcrOpinion，避免 N+1。
        """
        staff_ids = await self._resolve_staff_ids(user_id)
        if not staff_ids:
            return []

        proj_q = (
            select(Project)
            .join(
                ProjectAssignment,
                ProjectAssignment.project_id == Project.id,
            )
            .where(
                ProjectAssignment.staff_id.in_(staff_ids),
                ProjectAssignment.role == "eqcr",
                ProjectAssignment.is_deleted == False,  # noqa: E712
                Project.is_deleted == False,  # noqa: E712
            )
            .distinct()
        )
        projects = list((await self.db.execute(proj_q)).scalars().all())
        if not projects:
            return []

        project_ids = [p.id for p in projects]

        # Batch fetch: AuditReport (signing_date + status) for all projects
        ar_q = (
            select(AuditReport)
            .where(
                AuditReport.project_id.in_(project_ids),
                AuditReport.is_deleted == False,  # noqa: E712
            )
            .order_by(AuditReport.year.desc())
        )
        all_reports = list((await self.db.execute(ar_q)).scalars().all())
        # Group by project_id, keep only latest per project
        report_by_project: dict[uuid.UUID, AuditReport] = {}
        for ar in all_reports:
            if ar.project_id not in report_by_project:
                report_by_project[ar.project_id] = ar

        # Batch fetch: EqcrOpinion for all projects
        op_q = (
            select(EqcrOpinion)
            .where(
                EqcrOpinion.project_id.in_(project_ids),
                EqcrOpinion.is_deleted == False,  # noqa: E712
            )
            .order_by(EqcrOpinion.created_at.asc())
        )
        all_opinions = list((await self.db.execute(op_q)).scalars().all())
        # Group by project_id
        opinions_by_project: dict[uuid.UUID, list[EqcrOpinion]] = {}
        for op in all_opinions:
            opinions_by_project.setdefault(op.project_id, []).append(op)

        # Batch fetch: ProjectTimeline REPORT milestones
        tl_q = (
            select(ProjectTimeline)
            .where(
                ProjectTimeline.project_id.in_(project_ids),
                ProjectTimeline.milestone_type == MilestoneType.REPORT,
                ProjectTimeline.is_deleted == False,  # noqa: E712
            )
            .order_by(ProjectTimeline.planned_date.asc())
        )
        all_timelines = list((await self.db.execute(tl_q)).scalars().all())
        timeline_by_project: dict[uuid.UUID, date] = {}
        for tl in all_timelines:
            if tl.project_id not in timeline_by_project and tl.planned_date:
                timeline_by_project[tl.project_id] = tl.planned_date

        cards: list[dict[str, Any]] = []
        for proj in projects:
            # Resolve signing date from batch data
            ar = report_by_project.get(proj.id)
            signing_date: date | None = None
            if ar and ar.report_date:
                signing_date = ar.report_date
            elif proj.id in timeline_by_project:
                signing_date = timeline_by_project[proj.id]
            else:
                signing_date = proj.audit_period_end

            # Report status from batch data
            report_status: str | None = None
            if ar:
                report_status = ar.status.value if hasattr(ar.status, "value") else str(ar.status)

            opinions = opinions_by_project.get(proj.id, [])
            reviewed_domains = {
                op.domain for op in opinions if op.domain in EQCR_CORE_DOMAINS
            }
            cards.append(
                {
                    "project_id": str(proj.id),
                    "project_name": proj.name,
                    "client_name": proj.client_name,
                    "signing_date": signing_date.isoformat() if signing_date else None,
                    "days_to_signing": _days_between(signing_date),
                    "my_progress": _classify_progress(opinions, report_status),
                    "judgment_counts": {
                        "unreviewed": len(EQCR_CORE_DOMAINS) - len(reviewed_domains),
                        "reviewed": len(reviewed_domains),
                    },
                    "report_status": report_status,
                }
            )

        # 按签字日升序，None 排最后
        cards.sort(
            key=lambda c: (
                c["signing_date"] is None,
                c["signing_date"] or "9999-12-31",
                c["project_name"] or "",
            )
        )
        return cards

    # ------------------------------------------------------------------
    # 公开接口 2：项目 EQCR 总览
    # ------------------------------------------------------------------

    async def get_project_overview(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """返回项目 EQCR 总览（用于 EqcrProjectView 详情页壳）。

        ``None`` 表示项目不存在。调用方可据此返回 404。
        """
        proj = (
            await self.db.execute(
                select(Project).where(
                    Project.id == project_id,
                    Project.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if proj is None:
            return None

        signing_date = await self._resolve_signing_date(proj)
        report_status = await self._get_report_status(project_id)
        my_role = await self._is_user_eqcr_on(user_id, project_id)
        all_opinions = await self._get_core_opinions(project_id)

        # 5 个核心 domain 快照（每个 domain 取最新一条 verdict）
        by_domain: dict[str, str | None] = {d: None for d in EQCR_CORE_DOMAINS}
        for op in all_opinions:
            if op.domain in EQCR_CORE_DOMAINS:
                by_domain[op.domain] = op.verdict

        # 本人建的笔记数
        note_q = (
            select(func.count(EqcrReviewNote.id))
            .where(
                EqcrReviewNote.project_id == project_id,
                EqcrReviewNote.created_by == user_id,
                EqcrReviewNote.is_deleted == False,  # noqa: E712
            )
        )
        note_count = (await self.db.execute(note_q)).scalar() or 0

        # 影子计算：无软删除字段，直接 count
        shadow_q = (
            select(func.count(EqcrShadowComputation.id))
            .where(EqcrShadowComputation.project_id == project_id)
        )
        shadow_count = (await self.db.execute(shadow_q)).scalar() or 0

        # 未解决的异议
        disagree_count_q = (
            select(func.count(EqcrOpinion.id))
            .outerjoin(
                EqcrDisagreementResolution,
                and_(
                    EqcrDisagreementResolution.eqcr_opinion_id == EqcrOpinion.id,
                    EqcrDisagreementResolution.resolved_at.isnot(None),
                )
            )
            .where(
                EqcrOpinion.project_id == project_id,
                EqcrOpinion.verdict == "disagree",
                EqcrOpinion.is_deleted == False,  # noqa: E712
                EqcrDisagreementResolution.id.is_(None),  # no resolution
            )
        )
        disagreement_count = (await self.db.execute(disagree_count_q)).scalar() or 0

        return {
            "project": {
                "id": str(proj.id),
                "name": proj.name,
                "client_name": proj.client_name,
                "signing_date": signing_date.isoformat() if signing_date else None,
                "report_scope": proj.report_scope,
                "status": proj.status.value if hasattr(proj.status, "value") else str(proj.status),
                "audit_period_start": (
                    proj.audit_period_start.isoformat()
                    if proj.audit_period_start
                    else None
                ),
                "audit_period_end": (
                    proj.audit_period_end.isoformat()
                    if proj.audit_period_end
                    else None
                ),
            },
            "my_role_confirmed": my_role,
            "report_status": report_status,
            "opinion_summary": {
                "by_domain": by_domain,
                "total": len(all_opinions),
            },
            "note_count": int(note_count),
            "shadow_comp_count": int(shadow_count),
            "disagreement_count": int(disagreement_count),
        }
