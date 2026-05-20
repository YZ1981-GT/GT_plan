"""合伙人仪表盘聚合服务

Requirements: 2.2, 3.1, 3.2, 4.1, 4.2, 7.2, 9.2, 9.3, 9.5

并发聚合 cycle_progress / vr_summary / open_reviews / timeline / trimming，
任一子查询失败降级为 null + errors 记录。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log_models import AuditLogEntry
from app.models.core import Project
from app.models.procedure_models import ProcedureInstance
from app.models.workpaper_models import (
    ReviewCommentStatus,
    ReviewRecord,
    WorkingPaper,
    WpIndex,
)
from app.services.consistency_gate import ConsistencyGate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LAYER_PRIORITY: dict[str, int] = {"L5": 5, "L4": 4, "L3": 3, "L2": 2, "L1": 1}

CYCLES: list[str] = ["D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N"]

CYCLE_NAMES: dict[str, str] = {
    "D": "销售收入",
    "E": "货币资金",
    "F": "采购存货",
    "G": "投资",
    "H": "固定资产",
    "I": "无形资产",
    "J": "薪酬",
    "K": "管理",
    "L": "筹资",
    "M": "权益",
    "N": "税费",
}


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def calc_progress_rate(total: int, completed: int, trimmed: int) -> float:
    """计算循环完成率，保证结果 ∈ [0.0, 100.0]

    denominator = total - trimmed
    if denominator <= 0: return 100.0 (全部裁剪视为完成)
    rate = (completed / denominator) * 100.0
    return clamp(rate, 0.0, 100.0)
    """
    denominator = total - trimmed
    if denominator <= 0:
        return 100.0
    rate = (completed / denominator) * 100.0
    return max(0.0, min(100.0, rate))


def _negate_str(s: str) -> str:
    """Create a string that sorts in reverse order of the original.

    For ISO 8601 datetime strings, this produces correct reverse ordering.
    """
    # Negate each character's ordinal to reverse sort order
    return "".join(chr(0xFFFF - ord(c)) for c in s)


def sort_reviews(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按层级优先级降序，同层级内按创建时间降序排序。

    sorted by (-LAYER_PRIORITY[layer], -created_at)
    Higher priority first, then more recent first within same layer.
    """
    return sorted(
        items,
        key=lambda x: (
            -LAYER_PRIORITY.get(x.get("review_layer", ""), 0),
            _negate_str(x.get("created_at", "")),
        ),
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DashboardAggregatorService:
    """合伙人仪表盘聚合服务

    并发调用多个子查询，任一失败降级为 null + errors 记录。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_summary(
        self, *, project_id: str | UUID, user_id: str | UUID
    ) -> dict[str, Any]:
        """并发聚合所有子查询，任一失败降级为 null + errors 记录。"""
        pid = UUID(str(project_id)) if not isinstance(project_id, UUID) else project_id

        # Fetch project basic info
        project = await self._get_project(pid)
        if project is None:
            return {"error": "project_not_found"}

        errors: dict[str, str] = {}

        # Concurrent sub-queries
        results = await asyncio.gather(
            self._safe_call("cycle_progress", self._aggregate_cycle_progress(pid)),
            self._safe_call("vr_summary", self._aggregate_vr_summary(pid, project)),
            self._safe_call("open_reviews", self._aggregate_open_reviews(pid)),
            self._safe_call("timeline", self._aggregate_timeline(pid, project)),
            self._safe_call("trimming_overview", self._aggregate_trimming(pid)),
            return_exceptions=False,
        )

        response: dict[str, Any] = {
            "project_name": project.name,
            "audit_year": (
                project.audit_period_end.year
                if project.audit_period_end
                else datetime.now().year
            ),
            "last_updated": datetime.now().isoformat(),
        }

        field_names = [
            "cycle_progress",
            "vr_summary",
            "open_reviews",
            "timeline",
            "trimming_overview",
        ]
        for name, result in zip(field_names, results):
            if isinstance(result, dict) and result.get("__error__"):
                errors[name] = result["__error__"]
                response[name] = None
            else:
                response[name] = result

        if errors:
            response["errors"] = errors
        else:
            response["errors"] = None

        return response

    async def _safe_call(self, name: str, coro) -> Any:
        """Wrap a coroutine to catch exceptions and return error marker."""
        try:
            return await coro
        except Exception as e:
            logger.warning(f"Dashboard sub-query '{name}' failed: {e}")
            return {"__error__": str(e)}

    async def _get_project(self, project_id: UUID) -> Project | None:
        """Fetch project by ID."""
        stmt = select(Project).where(
            Project.id == project_id,
            Project.is_deleted == False,  # noqa: E712
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Sub-query: Cycle Progress
    # ------------------------------------------------------------------

    async def _aggregate_cycle_progress(self, project_id: UUID) -> list[dict[str, Any]]:
        """遍历 D~N 11 循环，从 procedure_instances 聚合 total/completed/trimmed。"""
        items: list[dict[str, Any]] = []

        for cycle in CYCLES:
            # Query procedure_instances for this cycle
            stmt = select(
                func.count().label("total"),
                func.count()
                .filter(
                    ProcedureInstance.execution_status == "completed"
                )
                .label("completed"),
                func.count()
                .filter(
                    ProcedureInstance.status == "not_applicable"
                )
                .label("trimmed"),
            ).where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.audit_cycle == cycle,
                ProcedureInstance.is_deleted == False,  # noqa: E712
            )

            result = await self.db.execute(stmt)
            row = result.one()
            total = row.total or 0
            completed = row.completed or 0
            trimmed = row.trimmed or 0

            items.append(
                {
                    "cycle": cycle,
                    "cycle_name": CYCLE_NAMES.get(cycle, cycle),
                    "total_procedures": total,
                    "completed_procedures": completed,
                    "trimmed_procedures": trimmed,
                    "progress_rate": calc_progress_rate(total, completed, trimmed),
                }
            )

        return items

    # ------------------------------------------------------------------
    # Sub-query: VR Summary
    # ------------------------------------------------------------------

    async def _aggregate_vr_summary(
        self, project_id: UUID, project: Project
    ) -> dict[str, Any]:
        """调用 ConsistencyGate.run_all_checks，按循环分组统计 blocking 未通过数。"""
        year = (
            project.audit_period_end.year
            if project.audit_period_end
            else datetime.now().year
        )

        gate = ConsistencyGate(self.db)
        result = await gate.run_all_checks(project_id, year)

        # Group blocking failures by cycle
        total_rules = len(result.checks)
        blocking_failed = sum(
            1 for c in result.checks if not c.passed and c.severity == "blocking"
        )

        # Infer cycle from check_name (e.g., "d4_revenue_xxx" → "D")
        by_cycle: list[dict[str, Any]] = []
        cycle_failures: dict[str, list[dict[str, Any]]] = {}

        for check in result.checks:
            if not check.passed and check.severity == "blocking":
                cycle_code = self._infer_cycle_from_check(check.check_name)
                if cycle_code not in cycle_failures:
                    cycle_failures[cycle_code] = []
                cycle_failures[cycle_code].append(
                    {
                        "rule_id": check.check_name,
                        "rule_name": check.check_name,
                        "details": check.details or None,
                    }
                )

        for cycle_code, failed_rules in cycle_failures.items():
            by_cycle.append(
                {
                    "cycle": cycle_code,
                    "blocking_failed": len(failed_rules),
                    "failed_rules": failed_rules,
                }
            )

        return {
            "total_rules": total_rules,
            "blocking_failed": blocking_failed,
            "all_passed": blocking_failed == 0,
            "by_cycle": by_cycle,
        }

    def _infer_cycle_from_check(self, check_name: str) -> str:
        """Infer audit cycle code from check name.

        Examples:
            "d4_revenue_reconciliation" → "D"
            "f5_f2_triangle" → "F"
            "h_cycle_triangle" → "H"
            "tb_balance" → "GENERAL"
        """
        name_lower = check_name.lower()
        for cycle in CYCLES:
            if name_lower.startswith(cycle.lower()):
                return cycle
        # Check for patterns like "x_cycle_"
        for cycle in CYCLES:
            if f"{cycle.lower()}_cycle" in name_lower or f"_{cycle.lower()}" in name_lower:
                return cycle
        return "GENERAL"

    # ------------------------------------------------------------------
    # Sub-query: Open Reviews
    # ------------------------------------------------------------------

    async def _aggregate_open_reviews(self, project_id: UUID) -> dict[str, Any]:
        """查询 review_records WHERE status='open'，按 LAYER_PRIORITY 排序。"""
        # Join ReviewRecord with WorkingPaper to filter by project_id
        stmt = (
            select(ReviewRecord)
            .join(
                WorkingPaper,
                ReviewRecord.working_paper_id == WorkingPaper.id,
            )
            .join(
                WpIndex,
                WorkingPaper.wp_index_id == WpIndex.id,
            )
            .where(
                WpIndex.project_id == project_id,
                ReviewRecord.status == ReviewCommentStatus.open,
                ReviewRecord.is_deleted == False,  # noqa: E712
            )
        )

        result = await self.db.execute(stmt)
        records = result.scalars().all()

        items: list[dict[str, Any]] = []
        by_layer: dict[str, int] = {}

        for rec in records:
            layer = rec.review_layer or "unknown"
            by_layer[layer] = by_layer.get(layer, 0) + 1

            # Truncate summary to 80 characters
            summary = (rec.comment_text or "")[:80]

            items.append(
                {
                    "id": str(rec.id),
                    "review_layer": layer,
                    "summary": summary,
                    "created_at": rec.created_at.isoformat() if rec.created_at else "",
                    "wp_code": "",  # Will be populated below
                    "sheet_name": rec.target_sheet,
                    "cell_ref": rec.target_cell or rec.cell_reference,
                }
            )

        # Populate wp_code by querying WpIndex for each record
        # (Optimization: batch query)
        if records:
            wp_ids = [rec.working_paper_id for rec in records]
            wp_code_stmt = (
                select(WorkingPaper.id, WpIndex.wp_code)
                .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
                .where(WorkingPaper.id.in_(wp_ids))
            )
            wp_result = await self.db.execute(wp_code_stmt)
            wp_code_map = {str(row[0]): row[1] for row in wp_result.all()}

            for i, rec in enumerate(records):
                items[i]["wp_code"] = wp_code_map.get(str(rec.working_paper_id), "")

        # Sort by priority
        sorted_items = sort_reviews(items)

        return {
            "total": len(sorted_items),
            "by_layer": by_layer,
            "items": sorted_items,
        }

    # ------------------------------------------------------------------
    # Sub-query: Timeline
    # ------------------------------------------------------------------

    async def _aggregate_timeline(
        self, project_id: UUID, project: Project
    ) -> dict[str, Any]:
        """从 project 表 + audit_log_entries 推断当前阶段。

        四阶段：planning → execution → review → reporting
        """
        stages = [
            {"name": "planning", "status": "pending", "entered_at": None, "completed_at": None, "summary": None},
            {"name": "execution", "status": "pending", "entered_at": None, "completed_at": None, "summary": None},
            {"name": "review", "status": "pending", "entered_at": None, "completed_at": None, "summary": None},
            {"name": "reporting", "status": "pending", "entered_at": None, "completed_at": None, "summary": None},
        ]

        # Infer current stage from project status and audit log
        current_stage = await self._infer_current_stage(project_id, project)

        stage_order = ["planning", "execution", "review", "reporting"]
        current_idx = stage_order.index(current_stage) if current_stage in stage_order else 0

        for i, stage in enumerate(stages):
            if i < current_idx:
                stage["status"] = "completed"
            elif i == current_idx:
                stage["status"] = "current"
            else:
                stage["status"] = "pending"

        # Try to get timestamps from audit log
        stage_timestamps = await self._get_stage_timestamps(project_id)
        for stage in stages:
            name = stage["name"]
            if name in stage_timestamps:
                stage["entered_at"] = stage_timestamps[name].get("entered_at")
                stage["completed_at"] = stage_timestamps[name].get("completed_at")

        return {
            "current_stage": current_stage,
            "stages": stages,
        }

    async def _infer_current_stage(self, project_id: UUID, project: Project) -> str:
        """Infer current project stage from project status and data state."""
        status_str = project.status.value if hasattr(project.status, "value") else str(project.status)

        # Map project status to stage
        status_stage_map = {
            "created": "planning",
            "planning": "planning",
            "in_progress": "execution",
            "execution": "execution",
            "review": "review",
            "under_review": "review",
            "reporting": "reporting",
            "completed": "reporting",
            "archived": "reporting",
        }

        return status_stage_map.get(status_str, "planning")

    async def _get_stage_timestamps(self, project_id: UUID) -> dict[str, dict[str, str | None]]:
        """Get stage transition timestamps from audit log entries."""
        timestamps: dict[str, dict[str, str | None]] = {}

        # Query audit log for project status changes
        stmt = (
            select(AuditLogEntry)
            .where(
                AuditLogEntry.object_type == "project",
                AuditLogEntry.object_id == project_id,
                AuditLogEntry.action_type.in_(["status_change", "create", "update"]),
            )
            .order_by(AuditLogEntry.ts.asc())
        )

        result = await self.db.execute(stmt)
        entries = result.scalars().all()

        for entry in entries:
            payload = entry.payload or {}
            new_status = payload.get("new_status") or payload.get("status")
            if new_status:
                stage = self._status_to_stage(new_status)
                if stage and stage not in timestamps:
                    timestamps[stage] = {
                        "entered_at": entry.ts.isoformat() if entry.ts else None,
                        "completed_at": None,
                    }

        return timestamps

    def _status_to_stage(self, status: str) -> str | None:
        """Map a status string to a stage name."""
        mapping = {
            "created": "planning",
            "planning": "planning",
            "in_progress": "execution",
            "execution": "execution",
            "review": "review",
            "under_review": "review",
            "reporting": "reporting",
            "completed": "reporting",
        }
        return mapping.get(status)

    # ------------------------------------------------------------------
    # Sub-query: Trimming Overview
    # ------------------------------------------------------------------

    async def _aggregate_trimming(self, project_id: UUID) -> dict[str, Any]:
        """从 procedure_instances 聚合裁剪统计。

        trimming 未实施时返回 available=false。
        """
        # Check if any procedures have been trimmed (not_applicable status)
        stmt = select(
            func.count().label("total"),
            func.count()
            .filter(ProcedureInstance.status == "not_applicable")
            .label("trimmed"),
        ).where(
            ProcedureInstance.project_id == project_id,
            ProcedureInstance.is_deleted == False,  # noqa: E712
        )

        result = await self.db.execute(stmt)
        row = result.one()
        total = row.total or 0
        trimmed = row.trimmed or 0

        # If no procedures exist at all, trimming is not available
        if total == 0:
            return {"available": False, "total_procedures": 0, "trimmed_count": 0, "trim_rate": 0.0, "by_cycle": []}

        # If no trimming has been done, mark as not available
        if trimmed == 0:
            return {"available": False, "total_procedures": total, "trimmed_count": 0, "trim_rate": 0.0, "by_cycle": []}

        # Trimming is available — aggregate by cycle
        by_cycle: list[dict[str, Any]] = []
        for cycle in CYCLES:
            cycle_stmt = select(
                func.count().label("cycle_total"),
                func.count()
                .filter(ProcedureInstance.status == "not_applicable")
                .label("cycle_trimmed"),
            ).where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.audit_cycle == cycle,
                ProcedureInstance.is_deleted == False,  # noqa: E712
            )

            cycle_result = await self.db.execute(cycle_stmt)
            cycle_row = cycle_result.one()
            cycle_total = cycle_row.cycle_total or 0
            cycle_trimmed = cycle_row.cycle_trimmed or 0

            if cycle_total > 0:
                rate = (cycle_trimmed / cycle_total) * 100.0
                by_cycle.append(
                    {
                        "cycle": cycle,
                        "total": cycle_total,
                        "trimmed": cycle_trimmed,
                        "rate": round(rate, 1),
                        "warning": rate > 50.0,
                    }
                )

        trim_rate = (trimmed / total) * 100.0 if total > 0 else 0.0

        return {
            "available": True,
            "total_procedures": total,
            "trimmed_count": trimmed,
            "trim_rate": round(trim_rate, 1),
            "by_cycle": by_cycle,
        }
