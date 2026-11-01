"""角色作业台 Facade — P1 实现

按角色聚合已有 service，每个数据源 try/except 独立降级。
所有 item 必须包含 route 或 missing_reason。

Requirements: 1.1, 2.1, 4.1
"""
from __future__ import annotations

import asyncio
import logging
import sqlalchemy as sa
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ─── 角色 → Section 注册 ─────────────────────────────────────────────────────

ROLE_SECTION_REGISTRY: dict[str, list[str]] = {
    "auditor": ["todo", "review_return", "due_soon", "material_gap", "ai_pending", "adj_my_drafts"],
    "manager": ["completion_rate", "review_aging", "budget_consumption", "personnel_load", "risk_overview", "adj_pending_review", "adj_material_items"],
    "partner": ["signoff_blockers", "ai_unconfirmed", "risk_overview", "key_adjustments", "adj_material_items", "adj_exceptions"],
    "qc": ["qc_rule_hits", "issue_rectification", "quality_trend", "cycle_matrix", "adj_exceptions"],
    "eqcr": ["eqcr_dimensions", "eqcr_checklist", "eqcr_annotations", "adj_snapshot_drift", "adj_material_items"],
}

SECTION_TITLES: dict[str, str] = {
    "todo": "今日待办",
    "review_return": "被退回复核",
    "due_soon": "即将截止",
    "material_gap": "资料缺口",
    "ai_pending": "AI 建议待确认",
    "completion_rate": "底稿完成率",
    "review_aging": "复核 Aging",
    "budget_consumption": "工时预算消耗率",
    "personnel_load": "人员负荷",
    "risk_overview": "风险总览",
    "signoff_blockers": "签发阻断项",
    "ai_unconfirmed": "AI 未确认内容",
    "key_adjustments": "关键调整",
    "qc_rule_hits": "QC 规则命中",
    "issue_rectification": "问题整改",
    "quality_trend": "质量趋势",
    "cycle_matrix": "循环质量矩阵",
    "eqcr_dimensions": "EQCR 复核维度",
    "eqcr_checklist": "EQCR Checklist",
    "eqcr_annotations": "EQCR 批注",
    # 调整分录跨角色 section
    "adj_my_drafts": "我的草稿分录",
    "adj_pending_review": "待我复核的调整",
    "adj_material_items": "重大调整事项",
    "adj_exceptions": "调整例外与下游失败",
    "adj_snapshot_drift": "EQCR 快照漂移",
}


# ─── Helper ───────────────────────────────────────────────────────────────────


def _build_item(
    item_id: str,
    label: str,
    *,
    route: str | None = None,
    missing_reason: str | None = None,
    priority: str = "normal",
    due_date: str | None = None,
    source: str | None = None,
    metric: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造标准 item，保证 route/missing_reason 二选一不变量。"""
    item: dict[str, Any] = {
        "id": item_id,
        "label": label,
        "priority": priority,
    }
    if route:
        item["route"] = route
    elif missing_reason:
        item["missing_reason"] = missing_reason
    else:
        # 兜底：缺少路由信息
        item["missing_reason"] = "route_not_available"
    if due_date:
        item["due_date"] = due_date
    if source:
        item["source"] = source
    if metric:
        item["metric"] = metric
    return item


# ─── Facade ───────────────────────────────────────────────────────────────────


class RoleWorkbenchFacade:
    """角色作业台聚合 Facade

    聚合 my_todo_service、dashboard_aggregator_service、review_conversation_service、
    workhour_service、risk_summary_service、stale_degraded_logger，
    按角色返回不同 section 组合。
    """

    def __init__(self, db: AsyncSession, project_id: UUID, user_id: UUID):
        self.db = db
        self.project_id = project_id
        self.user_id = user_id

    async def get_workbench(self, role: str) -> dict[str, Any]:
        """按角色返回作业台 DTO。"""
        if role not in ROLE_SECTION_REGISTRY:
            raise ValueError(f"Unknown role: {role}")

        section_ids = ROLE_SECTION_REGISTRY[role]
        sections = await asyncio.gather(
            *[self._build_section(sid) for sid in section_ids]
        )

        return {
            "role": role,
            "project_id": str(self.project_id),
            "sections": list(sections),
        }

    async def _build_section(self, section_id: str) -> dict[str, Any]:
        """构建单个 section，数据源失败时降级为空。"""
        try:
            items = await self._fetch_section_items(section_id)
        except Exception as e:
            logger.warning(f"[RoleWorkbench] section '{section_id}' fetch failed: {e}")
            items = [_build_item(
                f"{section_id}-error",
                f"数据加载失败",
                missing_reason=f"data_source_error: {type(e).__name__}",
            )]

        return {
            "id": section_id,
            "title": SECTION_TITLES.get(section_id, section_id),
            "items": items,
        }

    async def _fetch_section_items(self, section_id: str) -> list[dict[str, Any]]:
        """根据 section_id 调用对应 service 获取数据。"""
        dispatch: dict[str, Any] = {
            "todo": self._fetch_todo,
            "review_return": self._fetch_review_return,
            "due_soon": self._fetch_due_soon,
            "material_gap": self._fetch_material_gap,
            "ai_pending": self._fetch_ai_pending,
            "completion_rate": self._fetch_completion_rate,
            "review_aging": self._fetch_review_aging,
            "budget_consumption": self._fetch_budget_consumption,
            "personnel_load": self._fetch_personnel_load,
            "risk_overview": self._fetch_risk_overview,
            "signoff_blockers": self._fetch_signoff_blockers,
            "ai_unconfirmed": self._fetch_ai_unconfirmed,
            "key_adjustments": self._fetch_key_adjustments,
            "qc_rule_hits": self._fetch_qc_rule_hits,
            "issue_rectification": self._fetch_issue_rectification,
            "quality_trend": self._fetch_quality_trend,
            "cycle_matrix": self._fetch_cycle_matrix,
            "eqcr_dimensions": self._fetch_eqcr_dimensions,
            "eqcr_checklist": self._fetch_eqcr_checklist,
            "eqcr_annotations": self._fetch_eqcr_annotations,
            # 调整分录跨角色 section
            "adj_my_drafts": self._fetch_adj_my_drafts,
            "adj_pending_review": self._fetch_adj_pending_review,
            "adj_material_items": self._fetch_adj_material_items,
            "adj_exceptions": self._fetch_adj_exceptions,
            "adj_snapshot_drift": self._fetch_adj_snapshot_drift,
        }
        handler = dispatch.get(section_id)
        if handler is None:
            return []
        return await handler()

    # ─── Auditor Sections ─────────────────────────────────────────────────

    async def _fetch_todo(self) -> list[dict[str, Any]]:
        """聚合 my_todo_service 的待办列表。"""
        from app.services.my_todo_service import get_my_todo

        result = await get_my_todo(self.db, self.project_id, self.user_id)
        items = []
        for todo in result.items[:10]:  # 限制 10 条
            route = f"/projects/{self.project_id}/workpapers/{todo.wp_id}/edit"
            items.append(_build_item(
                f"todo-{todo.wp_id}",
                f"{todo.wp_code} {todo.wp_name}",
                route=route,
                priority=todo.urgency,
                source="my_todo_service",
            ))
        return items

    async def _fetch_review_return(self) -> list[dict[str, Any]]:
        """被退回的复核意见。"""
        from app.models.workpaper_models import (
            ReviewCommentStatus,
            ReviewRecord,
            WorkingPaper,
            WpIndex,
        )
        import sqlalchemy as sa

        stmt = (
            sa.select(ReviewRecord, WpIndex.wp_code, WpIndex.wp_name)
            .join(WorkingPaper, ReviewRecord.working_paper_id == WorkingPaper.id)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WpIndex.project_id == self.project_id,
                ReviewRecord.status == ReviewCommentStatus.open,
                ReviewRecord.is_deleted == sa.false(),
                WorkingPaper.assigned_to == self.user_id,
            )
            .order_by(ReviewRecord.created_at.desc())
            .limit(10)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        items = []
        for rec, wp_code, wp_name in rows:
            route = f"/projects/{self.project_id}/workpapers/{rec.working_paper_id}/edit"
            items.append(_build_item(
                f"rr-{rec.id}",
                f"{wp_code} 复核意见待处理",
                route=route,
                priority="high",
                source="review_conversation_service",
            ))
        return items

    async def _fetch_due_soon(self) -> list[dict[str, Any]]:
        """即将截止的问题单。"""
        from app.models.phase15_models import IssueTicket
        from datetime import timedelta
        import sqlalchemy as sa

        now = datetime.now(timezone.utc)
        t_48h = now + timedelta(hours=48)

        stmt = (
            sa.select(IssueTicket)
            .where(
                IssueTicket.project_id == self.project_id,
                IssueTicket.status.in_(["open", "in_fix"]),
                IssueTicket.due_at.isnot(None),
                IssueTicket.due_at <= t_48h,
                IssueTicket.due_at > now,
            )
            .order_by(IssueTicket.due_at.asc())
            .limit(10)
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        items = []
        for ticket in rows:
            route = f"/projects/{self.project_id}/issues"
            items.append(_build_item(
                f"due-{ticket.id}",
                f"{ticket.title} 即将截止",
                route=route,
                priority="high",
                due_date=ticket.due_at.isoformat() if ticket.due_at else None,
                source="issue_ticket",
            ))
        return items

    async def _fetch_material_gap(self) -> list[dict[str, Any]]:
        """资料缺口：PBC 未回收项。"""
        try:
            import sqlalchemy as sa
            from app.models.collaboration_models import PBCItem

            stmt = (
                sa.select(PBCItem)
                .where(
                    PBCItem.project_id == self.project_id,
                    PBCItem.status.in_(["pending", "requested"]),
                    PBCItem.is_deleted == sa.false(),
                )
                .limit(10)
            )
            result = await self.db.execute(stmt)
            rows = result.scalars().all()

            items = []
            for pbc in rows:
                items.append(_build_item(
                    f"mg-{pbc.id}",
                    f"{pbc.item_name or '资料'} 未回收",
                    missing_reason="material_not_received",
                    priority="medium",
                    source="pbc_service",
                ))
            return items
        except Exception:
            # PBC 模型可能不存在
            return [_build_item("mg-na", "资料缺口数据暂不可用", missing_reason="pbc_service_unavailable")]

    async def _fetch_ai_pending(self) -> list[dict[str, Any]]:
        """AI 生成内容未确认。"""
        try:
            import sqlalchemy as sa
            from app.models.workpaper_models import WorkingPaper, WpIndex

            stmt = (
                sa.select(WorkingPaper, WpIndex.wp_code)
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .where(
                    WpIndex.project_id == self.project_id,
                    WorkingPaper.assigned_to == self.user_id,
                    WorkingPaper.prefill_stale == True,  # noqa: E712
                    WorkingPaper.is_deleted == sa.false(),
                )
                .limit(10)
            )
            result = await self.db.execute(stmt)
            rows = result.all()

            items = []
            for wp, wp_code in rows:
                route = f"/projects/{self.project_id}/workpapers/{wp.id}/edit"
                items.append(_build_item(
                    f"ai-{wp.id}",
                    f"{wp_code} AI 内容待确认",
                    route=route,
                    priority="medium",
                    source="ai_content_gate",
                ))
            return items
        except Exception:
            return []

    # ─── Manager Sections ─────────────────────────────────────────────────

    async def _fetch_completion_rate(self) -> list[dict[str, Any]]:
        """底稿完成率。"""
        import sqlalchemy as sa
        from app.models.workpaper_models import WpIndex

        stmt = sa.select(
            sa.func.count().label("total"),
            sa.func.count().filter(
                WpIndex.status.in_(["reviewed", "signed_off"])
            ).label("completed"),
        ).where(
            WpIndex.project_id == self.project_id,
            WpIndex.status != "cancelled",
            WpIndex.is_deleted == sa.false(),
        )
        result = await self.db.execute(stmt)
        row = result.one()
        total = row.total or 0
        completed = row.completed or 0
        rate = round(completed / total * 100, 1) if total > 0 else 0.0

        priority = "high" if rate < 50 else ("medium" if rate < 80 else "normal")
        route = f"/projects/{self.project_id}/workpapers"

        return [_build_item(
            "cr-1",
            f"底稿完成率 {rate}%",
            route=route,
            priority=priority,
            source="wp_index",
            metric={"numerator": completed, "denominator": total, "value": rate / 100, "unit": "percent"},
        )]

    async def _fetch_review_aging(self) -> list[dict[str, Any]]:
        """复核 Aging：未关闭的复核意见。"""
        import sqlalchemy as sa
        from app.models.workpaper_models import (
            ReviewCommentStatus,
            ReviewRecord,
            WorkingPaper,
            WpIndex,
        )

        now = datetime.now(timezone.utc)

        stmt = (
            sa.select(ReviewRecord, WpIndex.wp_code)
            .join(WorkingPaper, ReviewRecord.working_paper_id == WorkingPaper.id)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WpIndex.project_id == self.project_id,
                ReviewRecord.status == ReviewCommentStatus.open,
                ReviewRecord.is_deleted == sa.false(),
            )
            .order_by(ReviewRecord.created_at.asc())
            .limit(10)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        items = []
        for rec, wp_code in rows:
            aging_hours = 0
            if rec.created_at:
                created = rec.created_at if rec.created_at.tzinfo else rec.created_at.replace(tzinfo=timezone.utc)
                aging_hours = int((now - created).total_seconds() / 3600)
            aging_days = aging_hours // 24

            priority = "high" if aging_hours > 72 else ("medium" if aging_hours > 48 else "normal")
            route = f"/projects/{self.project_id}/review-conversations"

            items.append(_build_item(
                f"ra-{rec.id}",
                f"{wp_code} 复核超期 {aging_days} 天",
                route=route,
                priority=priority,
                source="review_conversation_service",
            ))
        return items

    async def _fetch_budget_consumption(self) -> list[dict[str, Any]]:
        """工时预算消耗率。"""
        try:
            from app.services.workhour_service import WorkHourService

            svc = WorkHourService(self.db)
            summary = await svc.project_summary(self.project_id)
            total_hours = sum(s["total_hours"] for s in summary) if summary else 0

            # budget_hours 字段可能不存在
            import sqlalchemy as sa
            from app.models.core import Project

            proj = await self.db.get(Project, self.project_id)
            budget_hours = getattr(proj, "budget_hours", None) if proj else None

            if budget_hours and budget_hours > 0:
                rate = round(total_hours / float(budget_hours) * 100, 1)
                priority = "high" if rate > 90 else ("medium" if rate > 70 else "normal")
                return [_build_item(
                    "bc-1",
                    f"工时预算消耗 {rate}%",
                    route=f"/projects/{self.project_id}/workhours",
                    priority=priority,
                    source="workhour_service",
                    metric={"consumed": total_hours, "budget": float(budget_hours), "value": rate / 100, "unit": "percent"},
                )]
            else:
                return [_build_item(
                    "bc-1",
                    "预算数据暂缺",
                    missing_reason="budget_hours_field_missing",
                    priority="normal",
                    source="workhour_service",
                )]
        except Exception as e:
            logger.warning(f"[RoleWorkbench] budget fetch failed: {e}")
            return [_build_item("bc-1", "工时数据暂不可用", missing_reason=f"workhour_service_error")]

    async def _fetch_personnel_load(self) -> list[dict[str, Any]]:
        """人员负荷。"""
        try:
            from app.services.workhour_service import WorkHourService

            svc = WorkHourService(self.db)
            summary = await svc.project_summary(self.project_id)

            items = []
            for s in summary[:5]:
                # 简单估算负荷：总工时 / 标准工时(160h/月)
                total = s["total_hours"]
                priority = "high" if total > 160 else "normal"
                items.append(_build_item(
                    f"pl-{s['staff_name']}",
                    f"{s['staff_name']} 累计 {total}h",
                    route=f"/projects/{self.project_id}/workhours",
                    priority=priority,
                    source="workhour_service",
                ))
            return items if items else [_build_item("pl-na", "暂无工时数据", missing_reason="no_workhour_data")]
        except Exception:
            return [_build_item("pl-na", "人员负荷数据暂不可用", missing_reason="workhour_service_error")]

    async def _fetch_risk_overview(self) -> list[dict[str, Any]]:
        """风险总览。"""
        try:
            from app.services.risk_summary_service import RiskSummaryService

            svc = RiskSummaryService(self.db)
            risk = await svc.aggregate(self.project_id)

            blockers = risk["summary"]["total_blockers"]
            warnings = risk["summary"]["total_warnings"]
            priority = "high" if blockers > 0 else ("medium" if warnings > 3 else "normal")

            items = [_build_item(
                "ro-1",
                f"阻断项 {blockers} / 警告 {warnings}",
                route=f"/projects/{self.project_id}/risks",
                priority=priority,
                source="risk_summary_service",
            )]

            # 高严重度问题单
            for finding in risk.get("high_findings", [])[:3]:
                items.append(_build_item(
                    f"ro-f-{finding['id']}",
                    finding.get("title", "高严重度问题"),
                    route=f"/projects/{self.project_id}/issues",
                    priority="high",
                    source="risk_summary_service",
                ))
            return items
        except Exception as e:
            logger.warning(f"[RoleWorkbench] risk fetch failed: {e}")
            return [_build_item("ro-na", "风险数据暂不可用", missing_reason="risk_service_error")]

    # ─── Partner Sections ─────────────────────────────────────────────────

    async def _fetch_signoff_blockers(self) -> list[dict[str, Any]]:
        """签发阻断项：stale + conflict + 重大复核未关闭 + AI 未确认。"""
        items = []

        # 1. Stale 降级记录
        try:
            from app.services.stale_degraded_logger import get_degraded_records
            records = get_degraded_records()
            if records:
                items.append(_build_item(
                    "sb-stale",
                    f"stale 降级记录 {len(records)} 项",
                    route=f"/projects/{self.project_id}/consistency",
                    priority="critical",
                    source="stale_degraded_logger",
                ))
        except Exception:
            pass

        # 2. 重大复核未关闭
        try:
            from app.services.risk_summary_service import RiskSummaryService
            svc = RiskSummaryService(self.db)
            risk = await svc.aggregate(self.project_id)
            unresolved = risk.get("unresolved_comments", [])
            if unresolved:
                items.append(_build_item(
                    "sb-review",
                    f"未解决复核意见 {len(unresolved)} 条",
                    route=f"/projects/{self.project_id}/review-conversations",
                    priority="critical",
                    source="risk_summary_service",
                ))
        except Exception:
            pass

        # 3. 持续经营风险
        try:
            from app.services.risk_summary_service import RiskSummaryService
            svc = RiskSummaryService(self.db)
            risk = await svc.aggregate(self.project_id)
            if risk.get("going_concern_flag"):
                items.append(_build_item(
                    "sb-gc",
                    "持续经营风险标记",
                    route=f"/projects/{self.project_id}/subsequent-events",
                    priority="critical",
                    source="risk_summary_service",
                ))
        except Exception:
            pass

        if not items:
            items.append(_build_item(
                "sb-clear",
                "无签发阻断项",
                route=f"/projects/{self.project_id}/dashboard",
                priority="normal",
                source="signoff_check",
            ))

        return items

    async def _fetch_ai_unconfirmed(self) -> list[dict[str, Any]]:
        """AI 未确认内容。"""
        try:
            import sqlalchemy as sa
            from app.models.workpaper_models import WorkingPaper, WpIndex

            stmt = (
                sa.select(sa.func.count())
                .select_from(WorkingPaper)
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .where(
                    WpIndex.project_id == self.project_id,
                    WorkingPaper.prefill_stale == True,  # noqa: E712
                    WorkingPaper.is_deleted == sa.false(),
                )
            )
            result = await self.db.execute(stmt)
            count = result.scalar() or 0

            if count > 0:
                return [_build_item(
                    "au-1",
                    f"AI 未确认底稿 {count} 份",
                    route=f"/projects/{self.project_id}/workpapers",
                    priority="high",
                    source="ai_content_gate",
                )]
            return [_build_item(
                "au-clear",
                "AI 内容已全部确认",
                route=f"/projects/{self.project_id}/workpapers",
                priority="normal",
                source="ai_content_gate",
            )]
        except Exception:
            return [_build_item("au-na", "AI 状态暂不可用", missing_reason="ai_gate_unavailable")]

    async def _fetch_key_adjustments(self) -> list[dict[str, Any]]:
        """关键调整分录（被拒 AJE）。"""
        try:
            from app.services.risk_summary_service import RiskSummaryService
            svc = RiskSummaryService(self.db)
            risk = await svc.aggregate(self.project_id)
            rejected = risk.get("unconverted_rejected_aje", [])

            items = []
            for aje in rejected[:5]:
                items.append(_build_item(
                    f"ka-{aje['id']}",
                    f"被拒 AJE: {aje.get('adjustment_no', '')} {aje.get('description', '')[:30]}",
                    route=f"/projects/{self.project_id}/adjustments",
                    priority="high",
                    source="risk_summary_service",
                ))
            if not items:
                items.append(_build_item(
                    "ka-clear",
                    "无被拒关键调整",
                    route=f"/projects/{self.project_id}/adjustments",
                    priority="normal",
                    source="risk_summary_service",
                ))
            return items
        except Exception:
            return [_build_item("ka-na", "调整数据暂不可用", missing_reason="adjustment_service_error")]

    # ─── QC Sections (P2-1) ───────────────────────────────────────────────

    async def _fetch_qc_rule_hits(self) -> list[dict[str, Any]]:
        """QC 规则命中。"""
        try:
            from app.services.qc_dashboard_service import QCDashboardService
            svc = QCDashboardService(self.db)
            overview = await svc.get_overview(self.project_id)
            blocking = overview.get("qc_blocking", 0)
            pass_rate = overview.get("qc_pass_rate", 0)
            priority = "high" if blocking > 0 else "normal"

            return [_build_item(
                "qc-hits-1",
                f"QC 阻断 {blocking} 项，通过率 {pass_rate}%",
                route=f"/projects/{self.project_id}/qc",
                priority=priority,
                source="qc_dashboard_service",
                metric={"blocking": blocking, "pass_rate": pass_rate, "unit": "percent"},
            )]
        except Exception as e:
            logger.warning(f"[RoleWorkbench] qc_rule_hits failed: {e}")
            return [_build_item("qc-hits-na", "QC 数据暂不可用", missing_reason="qc_service_error")]

    async def _fetch_issue_rectification(self) -> list[dict[str, Any]]:
        """问题整改。"""
        try:
            from app.services.qc_dashboard_service import QCDashboardService, ReviewIssueTracker
            tracker = ReviewIssueTracker(self.db)
            open_issues = await tracker.get_open_issues(self.project_id)
            total_open = open_issues.get("total_open", 0)
            priority = "high" if total_open > 5 else ("medium" if total_open > 0 else "normal")

            return [_build_item(
                "qc-rect-1",
                f"未解决问题 {total_open} 条",
                route=f"/projects/{self.project_id}/review-conversations",
                priority=priority,
                source="review_issue_tracker",
            )]
        except Exception as e:
            logger.warning(f"[RoleWorkbench] issue_rectification failed: {e}")
            return [_build_item("qc-rect-na", "问题整改数据暂不可用", missing_reason="tracker_error")]

    async def _fetch_quality_trend(self) -> list[dict[str, Any]]:
        """质量趋势。"""
        try:
            from app.services.qc_dashboard_service import QCDashboardService
            svc = QCDashboardService(self.db)
            overview = await svc.get_overview(self.project_id)
            pass_rate = overview.get("qc_pass_rate", 0)

            if pass_rate >= 90:
                label = "良好"
                priority = "normal"
            elif pass_rate >= 70:
                label = "需关注"
                priority = "medium"
            else:
                label = "需整改"
                priority = "high"

            return [_build_item(
                "qc-trend-1",
                f"质量趋势: {label} ({pass_rate}%)",
                route=f"/projects/{self.project_id}/qc",
                priority=priority,
                source="qc_dashboard_service",
            )]
        except Exception as e:
            logger.warning(f"[RoleWorkbench] quality_trend failed: {e}")
            return [_build_item("qc-trend-na", "质量趋势暂不可用", missing_reason="qc_service_error")]

    async def _fetch_cycle_matrix(self) -> list[dict[str, Any]]:
        """循环质量矩阵。"""
        try:
            from app.services.qc_dashboard_service import QCDashboardService
            svc = QCDashboardService(self.db)
            overview = await svc.get_overview(self.project_id)
            matrix = overview.get("cycle_matrix", {})

            items = []
            for cycle, stats in list(matrix.items())[:5]:
                total = sum(stats.values())
                items.append(_build_item(
                    f"qc-cycle-{cycle}",
                    f"循环 {cycle}: {total} 底稿",
                    route=f"/projects/{self.project_id}/qc",
                    priority="normal",
                    source="qc_dashboard_service",
                ))
            if not items:
                items.append(_build_item(
                    "qc-cycle-na",
                    "暂无循环质量数据",
                    missing_reason="no_cycle_data",
                ))
            return items
        except Exception as e:
            logger.warning(f"[RoleWorkbench] cycle_matrix failed: {e}")
            return [_build_item("qc-cycle-na", "循环矩阵暂不可用", missing_reason="qc_service_error")]

    # ─── EQCR Sections (P2-2) ────────────────────────────────────────────

    async def _fetch_eqcr_dimensions(self) -> list[dict[str, Any]]:
        """EQCR 复核维度。"""
        try:
            from app.services.eqcr_review_workbench import EqcrReviewWorkbenchService
            svc = EqcrReviewWorkbenchService(self.db)
            dimensions = svc._default_dimensions()

            items = []
            for dim in dimensions:
                status = dim.get("status", "not_reviewed")
                priority = "high" if status == "not_reviewed" else "normal"
                items.append(_build_item(
                    f"eqcr-dim-{dim['id']}",
                    f"{dim['title']}: {status}",
                    route=f"/projects/{self.project_id}{dim['route_suffix']}",
                    priority=priority,
                    source="eqcr_review_workbench",
                ))
            return items
        except Exception as e:
            logger.warning(f"[RoleWorkbench] eqcr_dimensions failed: {e}")
            return [_build_item("eqcr-dim-na", "EQCR 维度暂不可用", missing_reason="eqcr_service_error")]

    async def _fetch_eqcr_checklist(self) -> list[dict[str, Any]]:
        """EQCR Checklist。"""
        try:
            from app.services.eqcr_review_workbench import EqcrReviewWorkbenchService
            svc = EqcrReviewWorkbenchService(self.db)
            checklist = svc.get_checklist_status(self.project_id)
            total = checklist.get("total_required", 0)
            done = checklist.get("completed_required", 0)
            can_sign = checklist.get("all_required_done", False)

            priority = "normal" if can_sign else "high"
            label = f"Checklist {done}/{total}" + (" ✓ 可签出" if can_sign else " 待完成")

            return [_build_item(
                "eqcr-cl-1",
                label,
                route=f"/projects/{self.project_id}/eqcr/checklist",
                priority=priority,
                source="eqcr_review_workbench",
            )]
        except Exception as e:
            logger.warning(f"[RoleWorkbench] eqcr_checklist failed: {e}")
            return [_build_item("eqcr-cl-na", "Checklist 暂不可用", missing_reason="eqcr_service_error")]

    async def _fetch_eqcr_annotations(self) -> list[dict[str, Any]]:
        """EQCR 批注。"""
        return [_build_item(
            "eqcr-ann-1",
            "EQCR 独立复核批注",
            route=f"/projects/{self.project_id}/eqcr/annotations",
            priority="normal",
            source="eqcr_review_workbench",
        )]

    # ─── 调整分录跨角色 Sections ──────────────────────────────────────────

    async def _fetch_adj_my_drafts(self) -> list[dict[str, Any]]:
        """审计助理：我编制的草稿和被驳回分录。"""
        try:
            from app.models.audit_platform_models import Adjustment, ReviewStatus
            rows = (await self.db.execute(
                sa.select(
                    Adjustment.entry_group_id,
                    Adjustment.adjustment_no,
                    Adjustment.review_status,
                ).where(
                    Adjustment.project_id == self.project_id,
                    Adjustment.created_by == self.user_id,
                    Adjustment.is_deleted == sa.false(),
                    Adjustment.review_status.in_([ReviewStatus.draft, ReviewStatus.rejected]),
                ).group_by(
                    Adjustment.entry_group_id,
                    Adjustment.adjustment_no,
                    Adjustment.review_status,
                ).order_by(Adjustment.adjustment_no)
                .limit(20)
            )).all()
            if not rows:
                return [_build_item("adj-draft-0", "暂无草稿或被驳回的分录", missing_reason="no_data")]
            return [
                _build_item(
                    f"adj-draft-{str(gid)[:8]}",
                    f"{no} · {'草稿' if str(getattr(status, 'value', status)) == 'draft' else '被驳回'}",
                    route=f"/projects/{self.project_id}/adjustments?focus={gid}",
                    priority="medium" if str(getattr(status, "value", status)) == "rejected" else "normal",
                )
                for gid, no, status in rows
            ]
        except Exception as exc:
            logger.warning("[RoleWorkbench] adj_my_drafts failed: %s", exc)
            return [_build_item("adj-draft-err", "草稿数据加载失败", missing_reason="data_source_error")]

    async def _fetch_adj_pending_review(self) -> list[dict[str, Any]]:
        """经理：分配给我的待复核调整分录任务。"""
        try:
            from app.services import adjustment_review_task_service as tasks
            my_tasks = await tasks.list_tasks(
                self.db, project_id=self.project_id, actor_id=self.user_id, status="pending",
            )
            if not my_tasks:
                return [_build_item("adj-review-0", "暂无分配给我的待复核分录", missing_reason="no_data")]
            return [
                _build_item(
                    f"adj-review-{str(t.id)[:8]}",
                    f"待复核 · {'合伙人' if t.required_level == 'partner' else '经理'}",
                    route=f"/projects/{self.project_id}/adjustments?focus={t.entry_group_id}",
                    priority="high" if t.required_level == "partner" else "medium",
                )
                for t in my_tasks[:20]
            ]
        except Exception as exc:
            logger.warning("[RoleWorkbench] adj_pending_review failed: %s", exc)
            return [_build_item("adj-review-err", "复核任务加载失败", missing_reason="data_source_error")]

    async def _fetch_adj_material_items(self) -> list[dict[str, Any]]:
        """经理/合伙人/EQCR：达到执行重要性或命中性质风险的分录。"""
        try:
            from app.models.audit_platform_models import Adjustment, AdjustmentType, ReviewStatus
            from app.services.adjustment_risk_projection import project_adjustment_risks

            group_ids = list((await self.db.execute(
                sa.select(sa.distinct(Adjustment.entry_group_id)).where(
                    Adjustment.project_id == self.project_id,
                    Adjustment.is_deleted == sa.false(),
                    Adjustment.review_status.in_([ReviewStatus.approved, ReviewStatus.pending_review]),
                ).limit(200)
            )).scalars().all())
            if not group_ids:
                return [_build_item("adj-mat-0", "暂无重大调整", missing_reason="no_data")]
            from app.services.project_audit_year import fetch_project_audit_year
            year = await fetch_project_audit_year(self.db, self.project_id) or 2025
            risks = await project_adjustment_risks(self.db, project_id=self.project_id, year=year, group_ids=group_ids)
            material = [
                (gid, risk) for gid, risk in risks.items()
                if risk.get("required_level") == "partner" or risk.get("reaches_performance")
            ]
            if not material:
                return [_build_item("adj-mat-0", "暂无达到执行重要性的调整分录", missing_reason="no_data")]
            return [
                _build_item(
                    f"adj-mat-{gid[:8]}",
                    f"执行重要性 {risk.get('performance_ratio', '?')}%"
                    + (f" · {'、'.join(f.get('label', '') for f in risk.get('risk_flags', []))}" if risk.get("risk_flags") else ""),
                    route=f"/projects/{self.project_id}/adjustments?focus={gid}",
                    priority="high",
                )
                for gid, risk in material[:20]
            ]
        except Exception as exc:
            logger.warning("[RoleWorkbench] adj_material_items failed: %s", exc)
            return [_build_item("adj-mat-err", "重大调整数据加载失败", missing_reason="data_source_error")]

    async def _fetch_adj_exceptions(self) -> list[dict[str, Any]]:
        """合伙人/QC：调整例外（未完成处理 + 下游失败）。"""
        try:
            from app.services.wp_adjustment_helpers import count_unresolved_adjustment_groups
            from app.services.project_audit_year import fetch_project_audit_year
            year = await fetch_project_audit_year(self.db, self.project_id) or 2025
            unresolved = await count_unresolved_adjustment_groups(self.db, self.project_id, year)
            if unresolved == 0:
                return [_build_item("adj-exc-0", "全部分录均已完成内部复核", missing_reason="no_data")]
            return [_build_item(
                "adj-exc-unresolved",
                f"{unresolved} 笔分录尚未完成内部复核",
                route=f"/projects/{self.project_id}/adjustments?review_status=draft",
                priority="high" if unresolved > 5 else "medium",
            )]
        except Exception as exc:
            logger.warning("[RoleWorkbench] adj_exceptions failed: %s", exc)
            return [_build_item("adj-exc-err", "例外数据加载失败", missing_reason="data_source_error")]

    async def _fetch_adj_snapshot_drift(self) -> list[dict[str, Any]]:
        """EQCR：快照漂移检测——当前快照的调整数量是否与实时一致。"""
        try:
            from app.services.eqcr_snapshot_service import get_current_snapshot
            from app.services.project_audit_year import fetch_project_audit_year
            year = await fetch_project_audit_year(self.db, self.project_id) or 2025
            snapshot = await get_current_snapshot(self.db, self.project_id, year)
            if snapshot is None:
                return [_build_item("adj-snap-none", "尚未创建 EQCR 快照", missing_reason="no_snapshot",
                                    route=f"/projects/{self.project_id}/eqcr")]
            snapshot_adj = snapshot.get("snapshot_data", {}).get("adjustments", [])
            from app.models.audit_platform_models import Adjustment
            live_count = int((await self.db.execute(sa.select(
                sa.func.count(sa.distinct(Adjustment.entry_group_id)),
            ).where(
                Adjustment.project_id == self.project_id,
                Adjustment.year == year,
                Adjustment.is_deleted == sa.false(),
            ))).scalar() or 0)
            snap_count = len(snapshot_adj)
            if live_count == snap_count:
                return [_build_item("adj-snap-ok", f"快照与实时一致（{snap_count} 笔）",
                                    route=f"/projects/{self.project_id}/eqcr", priority="normal")]
            return [_build_item(
                "adj-snap-drift",
                f"快照 {snap_count} 笔 vs 实时 {live_count} 笔，请刷新快照",
                route=f"/projects/{self.project_id}/eqcr",
                priority="high",
            )]
        except Exception as exc:
            logger.warning("[RoleWorkbench] adj_snapshot_drift failed: %s", exc)
            return [_build_item("adj-snap-err", "快照漂移检测失败", missing_reason="snapshot_service_error")]
