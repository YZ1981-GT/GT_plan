"""程序适用性裁剪引擎 — ProcedureTrimEngine

Sprint 1 Task 1.1: 实现 trim/revert/get_summary/get_history 方法。
数据存储在 parsed_data.trimming_metadata[sheet_key][row_id]，
状态更新在 parsed_data.procedure_status[sheet_key][row_id].status。

Requirements: 2.4, 3.3, 3.5, 4.1, 7.1, 7.2
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.services.audit_logger_enhanced import audit_logger

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Schemas
# ---------------------------------------------------------------------------


class TrimReasonCode(str, Enum):
    NO_RELATED_BUSINESS = "no_related_business"
    LOW_RISK_ASSESSMENT = "low_risk_assessment"
    CONTROL_TEST_EFFECTIVE = "control_test_effective"
    OTHER = "other"


class ProcedureTrimRequest(BaseModel):
    action: str = Field(..., pattern="^(trim|revert)$")
    sheet_key: str
    row_ids: list[str]
    reason_code: Optional[TrimReasonCode] = None
    reason_text: Optional[str] = None


class ProcedureTrimResponse(BaseModel):
    ok: bool
    action: str
    succeeded: list[str]
    skipped: list[str]
    failed: list[str]
    message: Optional[str] = None


class CycleTrimStat(BaseModel):
    cycle: str
    total: int
    trimmed: int
    rate: float
    warning: bool


class ReasonTrimStat(BaseModel):
    reason_code: str
    count: int


class TrimSummaryResponse(BaseModel):
    total_procedures: int
    trimmed_count: int
    trim_rate: float
    by_cycle: list[CycleTrimStat]
    by_reason: list[ReasonTrimStat]
    warnings: list[str]


class TrimHistoryEntry(BaseModel):
    id: str
    action: str
    row_ids: list[str]
    reason_code: Optional[str] = None
    reason_text: Optional[str] = None
    user_id: str
    user_name: Optional[str] = None
    created_at: str
    sheet_key: Optional[str] = None
    batch_id: Optional[str] = None


# ---------------------------------------------------------------------------
# TrimResult (internal)
# ---------------------------------------------------------------------------


class TrimResult:
    """Internal result object for trim/revert operations."""

    def __init__(
        self,
        ok: bool,
        action: str,
        succeeded: list[str],
        skipped: list[str],
        failed: list[str],
        message: str | None = None,
    ):
        self.ok = ok
        self.action = action
        self.succeeded = succeeded
        self.skipped = skipped
        self.failed = failed
        self.message = message

    def to_response(self) -> ProcedureTrimResponse:
        return ProcedureTrimResponse(
            ok=self.ok,
            action=self.action,
            succeeded=self.succeeded,
            skipped=self.skipped,
            failed=self.failed,
            message=self.message,
        )


# ---------------------------------------------------------------------------
# TrimSummary (internal)
# ---------------------------------------------------------------------------


class TrimSummary:
    """Internal summary object."""

    def __init__(
        self,
        total_procedures: int,
        trimmed_count: int,
        trim_rate: float,
        by_cycle: list[CycleTrimStat],
        by_reason: list[ReasonTrimStat],
        warnings: list[str],
    ):
        self.total_procedures = total_procedures
        self.trimmed_count = trimmed_count
        self.trim_rate = trim_rate
        self.by_cycle = by_cycle
        self.by_reason = by_reason
        self.warnings = warnings

    def to_response(self) -> TrimSummaryResponse:
        return TrimSummaryResponse(
            total_procedures=self.total_procedures,
            trimmed_count=self.trimmed_count,
            trim_rate=self.trim_rate,
            by_cycle=self.by_cycle,
            by_reason=self.by_reason,
            warnings=self.warnings,
        )


# ---------------------------------------------------------------------------
# ProcedureTrimEngine
# ---------------------------------------------------------------------------


class ProcedureTrimEngine:
    """程序适用性裁剪引擎。

    所有操作直接修改 WorkingPaper.parsed_data JSONB 字段：
    - procedure_status[sheet_key][row_id].status
    - trimming_metadata[sheet_key][row_id]
    """

    ACTION_TRIMMED = "workpaper.procedure_trimmed"
    ACTION_TRIM_REVERTED = "workpaper.procedure_trim_reverted"

    async def trim(
        self,
        *,
        db: AsyncSession,
        wp_id: uuid.UUID,
        sheet_key: str,
        row_ids: list[str],
        reason_code: TrimReasonCode,
        reason_text: str | None,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> TrimResult:
        """将指定程序行标记为 not_applicable。

        幂等：已为 not_applicable 的行跳过。
        不存在的 row_id 放入 failed 列表。
        """
        from app.models.workpaper_models import WorkingPaper

        result = await db.execute(
            select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )
        wp = result.scalar_one_or_none()
        if not wp:
            return TrimResult(
                ok=False, action="trim",
                succeeded=[], skipped=[], failed=row_ids,
                message="workpaper not found",
            )

        parsed: dict = dict(wp.parsed_data or {})
        procedure_status: dict = dict(parsed.get("procedure_status") or {})
        sheet_data: dict = dict(procedure_status.get(sheet_key) or {})
        trimming_metadata: dict = dict(parsed.get("trimming_metadata") or {})
        sheet_trim: dict = dict(trimming_metadata.get(sheet_key) or {})

        succeeded: list[str] = []
        skipped: list[str] = []
        failed: list[str] = []

        now_iso = datetime.now(timezone.utc).isoformat()
        batch_id = str(uuid.uuid4()) if len(row_ids) > 1 else None

        for row_id in row_ids:
            row_data = dict(sheet_data.get(row_id) or {})
            # Check if row exists in procedure_status
            if not row_data and row_id not in sheet_data:
                # Row doesn't exist — mark as failed
                failed.append(row_id)
                continue

            current_status = row_data.get("status", "pending")
            if current_status == "not_applicable":
                # Already N/A — idempotent skip
                skipped.append(row_id)
                continue

            # Update status
            row_data["status"] = "not_applicable"
            sheet_data[row_id] = row_data

            # Write trimming metadata
            sheet_trim[row_id] = {
                "reason_code": reason_code.value,
                "reason_text": reason_text,
                "trimmed_by": str(user_id),
                "trimmed_at": now_iso,
                "batch_id": batch_id,
            }
            succeeded.append(row_id)

        # Persist changes
        procedure_status[sheet_key] = sheet_data
        parsed["procedure_status"] = procedure_status
        trimming_metadata[sheet_key] = sheet_trim
        parsed["trimming_metadata"] = trimming_metadata
        wp.parsed_data = parsed
        flag_modified(wp, "parsed_data")

        # Audit log
        await self._log_trim_action(
            user_id=user_id,
            wp_id=wp_id,
            project_id=project_id,
            action_type="trim",
            sheet_key=sheet_key,
            row_ids=succeeded,
            reason_code=reason_code.value,
            reason_text=reason_text,
            batch_id=batch_id,
        )

        await db.flush()

        return TrimResult(
            ok=True,
            action="trim",
            succeeded=succeeded,
            skipped=skipped,
            failed=failed,
            message=None,
        )

    async def revert(
        self,
        *,
        db: AsyncSession,
        wp_id: uuid.UUID,
        sheet_key: str,
        row_ids: list[str],
        user_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> TrimResult:
        """将指定程序行从 not_applicable 恢复为 pending。

        幂等：非 not_applicable 的行跳过。
        不删除历史 trim 审计日志（仅追加 revert 条目）。
        """
        from app.models.workpaper_models import WorkingPaper

        result = await db.execute(
            select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )
        wp = result.scalar_one_or_none()
        if not wp:
            return TrimResult(
                ok=False, action="revert",
                succeeded=[], skipped=[], failed=row_ids,
                message="workpaper not found",
            )

        parsed: dict = dict(wp.parsed_data or {})
        procedure_status: dict = dict(parsed.get("procedure_status") or {})
        sheet_data: dict = dict(procedure_status.get(sheet_key) or {})
        trimming_metadata: dict = dict(parsed.get("trimming_metadata") or {})
        sheet_trim: dict = dict(trimming_metadata.get(sheet_key) or {})

        succeeded: list[str] = []
        skipped: list[str] = []
        failed: list[str] = []

        for row_id in row_ids:
            row_data = dict(sheet_data.get(row_id) or {})
            if not row_data and row_id not in sheet_data:
                failed.append(row_id)
                continue

            current_status = row_data.get("status", "pending")
            if current_status != "not_applicable":
                # Not N/A — idempotent skip
                skipped.append(row_id)
                continue

            # Restore status to pending
            row_data["status"] = "pending"
            sheet_data[row_id] = row_data

            # Clear trimming metadata for this row
            if row_id in sheet_trim:
                del sheet_trim[row_id]

            succeeded.append(row_id)

        # Persist changes
        procedure_status[sheet_key] = sheet_data
        parsed["procedure_status"] = procedure_status
        trimming_metadata[sheet_key] = sheet_trim
        parsed["trimming_metadata"] = trimming_metadata
        wp.parsed_data = parsed
        flag_modified(wp, "parsed_data")

        # Audit log (append-only — does NOT delete prior trim logs)
        await self._log_trim_action(
            user_id=user_id,
            wp_id=wp_id,
            project_id=project_id,
            action_type="revert",
            sheet_key=sheet_key,
            row_ids=succeeded,
            reason_code=None,
            reason_text=None,
            batch_id=None,
        )

        await db.flush()

        return TrimResult(
            ok=True,
            action="revert",
            succeeded=succeeded,
            skipped=skipped,
            failed=failed,
            message=None,
        )

    async def get_summary(
        self,
        *,
        db: AsyncSession,
        wp_id: uuid.UUID,
    ) -> TrimSummary:
        """获取裁剪汇总统计。

        按循环（sheet_key）分组 + 按理由分组 + 裁剪率 > 50% 警告。
        """
        from app.models.workpaper_models import WorkingPaper

        result = await db.execute(
            select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )
        wp = result.scalar_one_or_none()
        if not wp:
            return TrimSummary(
                total_procedures=0,
                trimmed_count=0,
                trim_rate=0.0,
                by_cycle=[],
                by_reason=[],
                warnings=[],
            )

        parsed: dict = wp.parsed_data or {}
        procedure_status: dict = parsed.get("procedure_status") or {}
        trimming_metadata: dict = parsed.get("trimming_metadata") or {}

        total_procedures = 0
        trimmed_count = 0
        cycle_stats: dict[str, dict] = {}
        reason_counts: dict[str, int] = {}

        for sheet_key, rows in procedure_status.items():
            if not isinstance(rows, dict):
                continue
            cycle_total = 0
            cycle_trimmed = 0
            for row_id, row_data in rows.items():
                if not isinstance(row_data, dict):
                    continue
                cycle_total += 1
                total_procedures += 1
                if row_data.get("status") == "not_applicable":
                    cycle_trimmed += 1
                    trimmed_count += 1

            cycle_stats[sheet_key] = {
                "total": cycle_total,
                "trimmed": cycle_trimmed,
            }

        # Count by reason from trimming_metadata
        for sheet_key, rows in trimming_metadata.items():
            if not isinstance(rows, dict):
                continue
            for row_id, meta in rows.items():
                if not isinstance(meta, dict):
                    continue
                rc = meta.get("reason_code", "unknown")
                reason_counts[rc] = reason_counts.get(rc, 0) + 1

        # Build cycle stats with warnings
        by_cycle: list[CycleTrimStat] = []
        warnings: list[str] = []
        for cycle, stats in cycle_stats.items():
            rate = (stats["trimmed"] / stats["total"] * 100) if stats["total"] > 0 else 0.0
            is_warning = rate > 50
            by_cycle.append(CycleTrimStat(
                cycle=cycle,
                total=stats["total"],
                trimmed=stats["trimmed"],
                rate=round(rate, 2),
                warning=is_warning,
            ))
            if is_warning:
                warnings.append(f"循环 {cycle} 裁剪率 {rate:.1f}% 超过 50%")

        # Build reason stats
        by_reason: list[ReasonTrimStat] = [
            ReasonTrimStat(reason_code=rc, count=cnt)
            for rc, cnt in sorted(reason_counts.items(), key=lambda x: -x[1])
        ]

        trim_rate = (trimmed_count / total_procedures * 100) if total_procedures > 0 else 0.0

        return TrimSummary(
            total_procedures=total_procedures,
            trimmed_count=trimmed_count,
            trim_rate=round(trim_rate, 2),
            by_cycle=by_cycle,
            by_reason=by_reason,
            warnings=warnings,
        )

    async def get_history(
        self,
        *,
        db: AsyncSession,
        wp_id: uuid.UUID,
        filters: dict | None = None,
    ) -> list[TrimHistoryEntry]:
        """从审计日志读取裁剪操作历史。

        支持按操作人/理由/时间范围筛选。
        返回按 created_at 降序排列。
        """
        from sqlalchemy import text

        # Build filter conditions
        conditions = [
            "object_id = :wp_id",
            "action_type IN (:action_trim, :action_revert)",
        ]
        params: dict = {
            "wp_id": str(wp_id),
            "action_trim": self.ACTION_TRIMMED,
            "action_revert": self.ACTION_TRIM_REVERTED,
        }

        if filters:
            if filters.get("user_id"):
                conditions.append("user_id = :filter_user_id")
                params["filter_user_id"] = str(filters["user_id"])
            if filters.get("reason_code"):
                conditions.append("payload->>'reason_code' = :filter_reason")
                params["filter_reason"] = filters["reason_code"]
            if filters.get("start_time"):
                conditions.append("created_at >= :start_time")
                params["start_time"] = filters["start_time"]
            if filters.get("end_time"):
                conditions.append("created_at <= :end_time")
                params["end_time"] = filters["end_time"]

        where_clause = " AND ".join(conditions)
        query = text(f"""
            SELECT id, action_type, user_id, payload, created_at
            FROM audit_log_entries
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT 200
        """)

        try:
            result = await db.execute(query, params)
            rows = result.fetchall()
        except Exception as e:
            logger.warning("Failed to query audit_log_entries: %s", e)
            return []

        entries: list[TrimHistoryEntry] = []
        for row in rows:
            payload = row[3] if isinstance(row[3], dict) else {}
            action_type = row[1]
            # Map action_type to trim/revert
            action = "trim" if "trimmed" in (action_type or "") else "revert"
            entries.append(TrimHistoryEntry(
                id=str(row[0]),
                action=action,
                row_ids=payload.get("row_ids", []),
                reason_code=payload.get("reason_code"),
                reason_text=payload.get("reason_text"),
                user_id=str(row[2]) if row[2] else "",
                user_name=None,
                created_at=row[4].isoformat() if row[4] else "",
                sheet_key=payload.get("sheet_key"),
                batch_id=payload.get("batch_id"),
            ))

        return entries

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    async def _log_trim_action(
        self,
        *,
        user_id: uuid.UUID,
        wp_id: uuid.UUID,
        project_id: uuid.UUID,
        action_type: str,
        sheet_key: str,
        row_ids: list[str],
        reason_code: str | None,
        reason_text: str | None,
        batch_id: str | None,
    ) -> None:
        """Write audit log entry via WpAuditTrailService."""
        if not row_ids:
            return

        action = self.ACTION_TRIMMED if action_type == "trim" else self.ACTION_TRIM_REVERTED

        await audit_logger.log_action(
            user_id=user_id,
            action=action,
            object_type="workpaper",
            object_id=wp_id,
            project_id=project_id,
            details={
                "action_type": action_type,
                "sheet_key": sheet_key,
                "row_ids": row_ids,
                "reason_code": reason_code,
                "reason_text": reason_text,
                "batch_id": batch_id,
                "user_id": str(user_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


# Module-level singleton
procedure_trim_engine = ProcedureTrimEngine()
