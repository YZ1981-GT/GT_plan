"""EQCR（独立复核合伙人）工作台服务

Refinement Round 5 任务 3 — 实现需求 1 所列 EQCR 工作台后端接口：

* ``list_my_projects(user_id)``         返回"本人作为 EQCR 的项目"列表（排序按签字日升序）
* ``get_project_overview(user_id, project_id)`` 返回项目 EQCR 总览数据

设计要点（与 R5 design.md 对齐）：

- 项目过滤靠 ``ProjectAssignment.role='eqcr'``（R1 已在枚举预留；R5 任务 2 已
  在 ``assignment_service.ROLE_MAP`` 注册）；用户 → 人员映射走
  ``StaffMember.user_id``。系统角色（user.role）不做强过滤，避免与"两层角色"
  模型冲突（UserRole=系统级，ProjectAssignment.role=项目级）。
- 签字日来源优先级：
    1. ``AuditReport.report_date``（最权威）
    2. ``ProjectTimeline`` 中 ``milestone_type=REPORT`` 的 ``planned_date``
    3. ``Project.audit_period_end``（兜底）
    4. ``None``（在排序时视为最晚）
- 进度与判断事项计数复用 5 个 ``EqcrOpinion.domain`` 约定枚举：
  ``materiality / estimate / related_party / going_concern / opinion_type``。
  组成部分审计师（需求 11 扩展的 ``component_auditor``）不计入工作台 5 个
  基础判断域 —— 那是合并审计的 opt-in Tab。
- 进度归类：
    * ``not_started``  无 opinion 记录
    * ``disagree``     任一 opinion.verdict='disagree'
    * ``approved``     5 个 domain 全部已录且全部为 agree，且 AuditReport.status
                       已切到 ``eqcr_approved`` / ``final``（否则降为 ``in_progress``）
    * ``in_progress``  其余情形

本服务不直接修改数据，仅做只读聚合；错误情况（如项目不存在 / 用户无权限）
由上层路由层决定返回 404 / 403。
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
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


class EqcrService:
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
    # 5 判断域聚合方法（原 monkey-patch，现为正式类方法）
    # ------------------------------------------------------------------

    async def get_materiality(self, project_id: uuid.UUID) -> dict[str, Any]:
        """需求 2.2：重要性 Tab 数据 + 本域意见历史。"""
        from app.models.audit_platform_models import Materiality

        q = (
            select(Materiality)
            .where(
                Materiality.project_id == project_id,
                Materiality.is_deleted == False,  # noqa: E712
            )
            .order_by(Materiality.year.desc(), Materiality.created_at.desc())
        )
        rows = list((await self.db.execute(q)).scalars().all())

        current_year: dict[str, Any] | None = None
        history_years: list[dict[str, Any]] = []
        for idx, row in enumerate(rows):
            payload = {
                "year": row.year,
                "benchmark_type": row.benchmark_type,
                "benchmark_amount": _decimal_str(row.benchmark_amount),
                "overall_percentage": _decimal_str(row.overall_percentage),
                "overall_materiality": _decimal_str(row.overall_materiality),
                "performance_ratio": _decimal_str(row.performance_ratio),
                "performance_materiality": _decimal_str(row.performance_materiality),
                "trivial_ratio": _decimal_str(row.trivial_ratio),
                "trivial_threshold": _decimal_str(row.trivial_threshold),
                "is_override": bool(row.is_override),
                "override_reason": row.override_reason,
            }
            if idx == 0:
                current_year = payload
            else:
                history_years.append(payload)

        opinions = await _load_domain_opinions(self.db, project_id, "materiality")
        current_opinion, history_opinions = _split_current_history(opinions)

        return {
            "project_id": str(project_id),
            "domain": "materiality",
            "data": {
                "current": current_year,
                "prior_years": history_years,
            },
            "current_opinion": current_opinion,
            "history_opinions": history_opinions,
        }

    async def get_estimates(self, project_id: uuid.UUID) -> dict[str, Any]:
        """需求 2.3：会计估计 Tab 数据。"""
        from app.models.workpaper_models import WorkingPaper, WpIndex

        name_filter = None
        for kw in _ESTIMATE_KEYWORDS:
            cond = WpIndex.wp_name.like(f"%{kw}%")
            name_filter = cond if name_filter is None else (name_filter | cond)

        has_category = hasattr(WpIndex, "category")
        if has_category:
            category_cond = getattr(WpIndex, "category") == "estimate"
            name_filter = category_cond if name_filter is None else (name_filter | category_cond)

        q = (
            select(WpIndex, WorkingPaper)
            .outerjoin(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WpIndex.project_id == project_id,
                WpIndex.is_deleted == False,  # noqa: E712
                name_filter,
            )
            .order_by(WpIndex.wp_code.asc())
        )
        rows = (await self.db.execute(q)).all()

        items: list[dict[str, Any]] = []
        seen_wp_index_ids: set[uuid.UUID] = set()
        for idx_row, wp_row in rows:
            if idx_row.id in seen_wp_index_ids:
                continue
            seen_wp_index_ids.add(idx_row.id)
            items.append(
                {
                    "wp_index_id": str(idx_row.id),
                    "wp_code": idx_row.wp_code,
                    "wp_name": idx_row.wp_name,
                    "audit_cycle": idx_row.audit_cycle,
                    "index_status": idx_row.status.value if idx_row.status else None,
                    "file_status": wp_row.status.value if wp_row and wp_row.status else None,
                    "review_status": wp_row.review_status.value
                    if wp_row and wp_row.review_status
                    else None,
                    "working_paper_id": str(wp_row.id) if wp_row else None,
                }
            )

        opinions = await _load_domain_opinions(self.db, project_id, "estimate")
        current_opinion, history_opinions = _split_current_history(opinions)

        return {
            "project_id": str(project_id),
            "domain": "estimate",
            "data": {
                "items": items,
                "match_strategy": "wp_name_keyword",
                "keywords": list(_ESTIMATE_KEYWORDS),
            },
            "current_opinion": current_opinion,
            "history_opinions": history_opinions,
        }

    async def get_related_parties(self, project_id: uuid.UUID) -> dict[str, Any]:
        """需求 2.4：关联方 Tab 数据（注册表 + 交易明细）。"""
        from app.models.related_party_models import (
            RelatedPartyRegistry,
            RelatedPartyTransaction,
        )

        reg_q = (
            select(RelatedPartyRegistry)
            .where(
                RelatedPartyRegistry.project_id == project_id,
                RelatedPartyRegistry.is_deleted == False,  # noqa: E712
            )
            .order_by(RelatedPartyRegistry.created_at.asc())
        )
        registries = list((await self.db.execute(reg_q)).scalars().all())

        txn_q = (
            select(RelatedPartyTransaction)
            .where(
                RelatedPartyTransaction.project_id == project_id,
                RelatedPartyTransaction.is_deleted == False,  # noqa: E712
            )
            .order_by(RelatedPartyTransaction.created_at.asc())
        )
        transactions = list((await self.db.execute(txn_q)).scalars().all())

        registries_payload = [
            {
                "id": str(r.id),
                "name": r.name,
                "relation_type": r.relation_type,
                "is_controlled_by_same_party": bool(r.is_controlled_by_same_party),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in registries
        ]
        transactions_payload = [
            {
                "id": str(t.id),
                "related_party_id": str(t.related_party_id),
                "amount": _decimal_str(t.amount),
                "transaction_type": t.transaction_type,
                "is_arms_length": t.is_arms_length,
                "evidence_refs": t.evidence_refs,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in transactions
        ]

        opinions = await _load_domain_opinions(self.db, project_id, "related_party")
        current_opinion, history_opinions = _split_current_history(opinions)

        return {
            "project_id": str(project_id),
            "domain": "related_party",
            "data": {
                "registries": registries_payload,
                "transactions": transactions_payload,
                "summary": {
                    "registry_count": len(registries_payload),
                    "transaction_count": len(transactions_payload),
                },
            },
            "current_opinion": current_opinion,
            "history_opinions": history_opinions,
        }

    async def get_going_concern(self, project_id: uuid.UUID) -> dict[str, Any]:
        """需求 2.5：持续经营 Tab 数据（复用 GoingConcernEvaluation）。"""
        from app.models.collaboration_models import (
            GoingConcernEvaluation,
            GoingConcernIndicator,
        )

        eval_q = (
            select(GoingConcernEvaluation)
            .where(
                GoingConcernEvaluation.project_id == project_id,
                GoingConcernEvaluation.is_deleted == False,  # noqa: E712
            )
            .order_by(GoingConcernEvaluation.evaluation_date.desc())
        )
        evaluations = list((await self.db.execute(eval_q)).scalars().all())

        current_eval: dict[str, Any] | None = None
        prior_evals: list[dict[str, Any]] = []
        latest_indicators: list[dict[str, Any]] = []

        for idx, ev in enumerate(evaluations):
            payload = {
                "id": str(ev.id),
                "evaluation_date": ev.evaluation_date.isoformat()
                if ev.evaluation_date
                else None,
                "conclusion": ev.conclusion.value if ev.conclusion else None,
                "key_indicators": ev.key_indicators,
                "management_plan": ev.management_plan,
                "auditor_conclusion": ev.auditor_conclusion,
            }
            if idx == 0:
                current_eval = payload

                ind_q = (
                    select(GoingConcernIndicator)
                    .where(
                        GoingConcernIndicator.evaluation_id == ev.id,
                        GoingConcernIndicator.is_deleted == False,  # noqa: E712
                    )
                    .order_by(GoingConcernIndicator.created_at.asc())
                )
                indicators = list((await self.db.execute(ind_q)).scalars().all())
                latest_indicators = [
                    {
                        "id": str(ind.id),
                        "indicator_type": ind.indicator_type,
                        "indicator_value": ind.indicator_value,
                        "threshold": ind.threshold,
                        "is_triggered": bool(ind.is_triggered),
                        "severity": ind.severity.value if ind.severity else None,
                        "notes": ind.notes,
                    }
                    for ind in indicators
                ]
            else:
                prior_evals.append(payload)

        opinions = await _load_domain_opinions(self.db, project_id, "going_concern")
        current_opinion, history_opinions = _split_current_history(opinions)

        return {
            "project_id": str(project_id),
            "domain": "going_concern",
            "data": {
                "current_evaluation": current_eval,
                "prior_evaluations": prior_evals,
                "indicators": latest_indicators,
            },
            "current_opinion": current_opinion,
            "history_opinions": history_opinions,
        }

    async def get_opinion_type(self, project_id: uuid.UUID) -> dict[str, Any]:
        """需求 2.6：审计意见类型 Tab 数据。"""
        ar_q = (
            select(AuditReport)
            .where(
                AuditReport.project_id == project_id,
                AuditReport.is_deleted == False,  # noqa: E712
            )
            .order_by(AuditReport.year.desc())
        )
        reports = list((await self.db.execute(ar_q)).scalars().all())

        current_report: dict[str, Any] | None = None
        prior_reports: list[dict[str, Any]] = []
        for idx, ar in enumerate(reports):
            payload = {
                "id": str(ar.id),
                "year": ar.year,
                "opinion_type": ar.opinion_type.value if ar.opinion_type else None,
                "company_type": ar.company_type.value if ar.company_type else None,
                "status": ar.status.value if ar.status else None,
                "report_date": ar.report_date.isoformat() if ar.report_date else None,
                "signing_partner": ar.signing_partner,
                "paragraphs": ar.paragraphs,
            }
            if idx == 0:
                current_report = payload
            else:
                prior_reports.append(payload)

        opinions = await _load_domain_opinions(self.db, project_id, "opinion_type")
        current_opinion, history_opinions = _split_current_history(opinions)

        return {
            "project_id": str(project_id),
            "domain": "opinion_type",
            "data": {
                "current_report": current_report,
                "prior_reports": prior_reports,
            },
            "current_opinion": current_opinion,
            "history_opinions": history_opinions,
        }

    # ------------------------------------------------------------------
    # 意见 CRUD（POST / PATCH）
    # ------------------------------------------------------------------

    async def create_opinion(
        self,
        *,
        project_id: uuid.UUID,
        domain: str,
        verdict: str,
        comment: str | None,
        extra_payload: dict | None,
        user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """新建一条 EQCR 意见。调用方负责 ``db.commit()``。"""
        if domain not in _ALLOWED_DOMAINS:
            raise ValueError(f"非法 domain: {domain}；允许值 {sorted(_ALLOWED_DOMAINS)}")
        if verdict not in _ALLOWED_VERDICTS:
            raise ValueError(
                f"非法 verdict: {verdict}；允许值 {sorted(_ALLOWED_VERDICTS)}"
            )

        op = EqcrOpinion(
            project_id=project_id,
            domain=domain,
            verdict=verdict,
            comment=comment,
            extra_payload=extra_payload,
            created_by=user_id,
        )
        self.db.add(op)
        await self.db.flush()
        await self.db.refresh(op)
        return _serialize_opinion(op)

    async def update_opinion(
        self,
        *,
        opinion_id: uuid.UUID,
        user_id: uuid.UUID,
        verdict: str | None = None,
        comment: str | None = None,
        extra_payload: dict | None = None,
    ) -> dict[str, Any] | None:
        """更新一条 EQCR 意见。返回 None 表示不存在。"""
        q = select(EqcrOpinion).where(
            EqcrOpinion.id == opinion_id,
            EqcrOpinion.is_deleted == False,  # noqa: E712
        )
        op = (await self.db.execute(q)).scalar_one_or_none()
        if op is None:
            return None

        if verdict is not None:
            if verdict not in _ALLOWED_VERDICTS:
                raise ValueError(
                    f"非法 verdict: {verdict}；允许值 {sorted(_ALLOWED_VERDICTS)}"
                )
            op.verdict = verdict
        if comment is not None:
            op.comment = comment
        if extra_payload is not None:
            op.extra_payload = extra_payload

        await self.db.flush()
        await self.db.refresh(op)
        return _serialize_opinion(op)

    # ------------------------------------------------------------------
    # 公开接口 2：项目 EQCR 总览
    # ------------------------------------------------------------------

    async def get_project_overview(
        self, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """返回项目 EQCR 总览（用于 EqcrProjectView 详情页壳）。

        ``None`` 表示项目不存在。调用方可据此返回 404。

        Shape::

            {
                "project": {id, name, client_name, signing_date,
                            report_scope, status, audit_period_start, audit_period_end},
                "my_role_confirmed": bool,         # 我是否是该项目 EQCR
                "report_status": str | None,       # audit_report.status
                "opinion_summary": {               # 5 个基础 domain 快照
                    "by_domain": {"materiality": "agree"|..., ...},
                    "total": int,                  # 包含所有 domain（含 component_auditor）
                },
                "note_count": int,                 # 仅"本人"视角：我建的笔记数
                "shadow_comp_count": int,          # 项目下的影子计算总数
                "disagreement_count": int,         # 未解决的 EQCR 异议数
            }
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

        # 未解决的异议：使用 LEFT JOIN 单查询
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


# ---------------------------------------------------------------------------
# 5 判断域聚合 + 意见 CRUD 辅助（Round 5 任务 5）
# ---------------------------------------------------------------------------

from decimal import Decimal  # noqa: E402

# 会计估计关键词（用于 WorkingPaper.name/wp_index.wp_name 兜底匹配）
_ESTIMATE_KEYWORDS: tuple[str, ...] = (
    "估计",
    "减值",
    "跌价",
    "折旧",
    "摊销",
)

_ALLOWED_DOMAINS: frozenset[str] = frozenset(
    list(EQCR_CORE_DOMAINS) + ["component_auditor"]
)
_ALLOWED_VERDICTS: frozenset[str] = frozenset(
    ["agree", "disagree", "need_more_evidence"]
)


def _decimal_str(value: Decimal | None) -> str | None:
    """将 Decimal 序列化为字符串（JSON 兼容，保留精度）。"""
    if value is None:
        return None
    return str(value)


def _serialize_opinion(op: "EqcrOpinion") -> dict[str, Any]:
    """把 ``EqcrOpinion`` ORM 对象转换为 JSON 可序列化字典。"""
    return {
        "id": str(op.id),
        "project_id": str(op.project_id),
        "domain": op.domain,
        "verdict": op.verdict,
        "comment": op.comment,
        "extra_payload": op.extra_payload,
        "created_by": str(op.created_by) if op.created_by else None,
        "created_at": op.created_at.isoformat() if op.created_at else None,
        "updated_at": op.updated_at.isoformat() if op.updated_at else None,
    }


def _split_current_history(
    opinions: list["EqcrOpinion"],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """按 ``created_at`` 升序，最后一条为 ``current_opinion``，其余为 ``history``（旧→新前）。"""
    if not opinions:
        return None, []
    sorted_ops = sorted(opinions, key=lambda o: o.created_at or datetime.min)
    current = _serialize_opinion(sorted_ops[-1])
    history = [_serialize_opinion(o) for o in sorted_ops[:-1]]
    return current, history


# 暴露 EqcrService 的域方法时需要引用以下模型，放到函数内延迟导入以避免
# 本模块 import 时的循环依赖（Materiality 等位于 audit_platform_models）。


async def _load_domain_opinions(
    db: AsyncSession, project_id: uuid.UUID, domain: str
) -> list[EqcrOpinion]:
    """载入某个 domain 下该项目的所有 active opinion，按创建时间升序。"""
    q = (
        select(EqcrOpinion)
        .where(
            EqcrOpinion.project_id == project_id,
            EqcrOpinion.domain == domain,
            EqcrOpinion.is_deleted == False,  # noqa: E712
        )
        .order_by(EqcrOpinion.created_at.asc())
    )
    return list((await db.execute(q)).scalars().all())

