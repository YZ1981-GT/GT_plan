"""监管对接服务

功能：
- submit_cicpa_report: 提交中注协审计报告备案（stub）
- submit_archival_standard: 提交电子底稿归档标准（stub）
- check_filing_status: 查询备案状态
- handle_filing_response: 处理备案响应
- retry_filing: 重试失败的备案
- 备案状态跟踪: submitted/pending/approved/rejected 状态机
- 备案日志记录
- 错误处理与重试机制

Validates: Requirements 8.1-8.7
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.extension_models import RegulatoryFiling

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 状态机：合法的状态转换
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[str, list[str]] = {
    "submitted": ["pending", "approved", "rejected"],
    "pending": ["approved", "rejected"],
    "approved": [],  # 终态
    "rejected": ["submitted"],  # 可重试
}

MAX_RETRY_ATTEMPTS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RegulatoryService:
    """监管对接服务"""

    # ── 提交备案 ──────────────────────────────────────────────────

    async def submit_cicpa_report(
        self,
        db: AsyncSession,
        project_id: UUID,
        submission_data: dict | None = None,
    ) -> dict:
        """提交中注协审计报告备案（stub — 格式转换占位）"""
        await self._validate_project(db, project_id)
        formatted_data = self._format_cicpa_data(submission_data or {})

        filing = RegulatoryFiling(
            project_id=project_id,
            filing_type="cicpa_report",
            filing_status="submitted",
            submission_data=formatted_data,
            submitted_at=_now(),
        )
        db.add(filing)
        await db.flush()

        logger.info("CICPA报告备案已提交: filing_id=%s, project_id=%s", filing.id, project_id)
        return self._to_dict(filing)

    async def submit_archival_standard(
        self,
        db: AsyncSession,
        project_id: UUID,
        submission_data: dict | None = None,
    ) -> dict:
        """提交电子底稿归档标准（stub）"""
        await self._validate_project(db, project_id)
        formatted_data = self._format_archival_data(submission_data or {})

        filing = RegulatoryFiling(
            project_id=project_id,
            filing_type="archival_standard",
            filing_status="submitted",
            submission_data=formatted_data,
            submitted_at=_now(),
        )
        db.add(filing)
        await db.flush()

        logger.info("电子底稿归档标准已提交: filing_id=%s, project_id=%s", filing.id, project_id)
        return self._to_dict(filing)

    # ── 状态查询 ──────────────────────────────────────────────────

    async def check_filing_status(self, db: AsyncSession, filing_id: UUID) -> dict:
        """查询备案状态"""
        filing = await self._get_or_raise(db, filing_id)
        return {
            "id": str(filing.id),
            "filing_type": filing.filing_type,
            "filing_status": filing.filing_status,
            "submitted_at": filing.submitted_at.isoformat() if filing.submitted_at else None,
            "responded_at": filing.responded_at.isoformat() if filing.responded_at else None,
            "error_message": filing.error_message,
        }

    # ── 处理响应 ──────────────────────────────────────────────────

    async def handle_filing_response(
        self,
        db: AsyncSession,
        filing_id: UUID,
        new_status: str,
        response_data: dict | None = None,
        error_message: str | None = None,
    ) -> dict:
        """处理备案响应（状态机转换）"""
        filing = await self._get_or_raise(db, filing_id)

        current = filing.filing_status
        if new_status not in VALID_TRANSITIONS.get(current, []):
            raise ValueError(
                f"非法状态转换: {current} → {new_status}，"
                f"允许的转换: {VALID_TRANSITIONS.get(current, [])}"
            )

        filing.filing_status = new_status
        # 保留已有的 retry_count 等元数据
        existing_meta = filing.response_data or {}
        merged = {**existing_meta, **(response_data or {})}
        filing.response_data = merged
        filing.responded_at = _now()

        if error_message:
            filing.error_message = error_message

        await db.flush()
        logger.info("备案状态更新: filing_id=%s, %s → %s", filing_id, current, new_status)
        return self._to_dict(filing)

    # ── 重试 ──────────────────────────────────────────────────────

    async def retry_filing(self, db: AsyncSession, filing_id: UUID) -> dict:
        """重试失败的备案"""
        filing = await self._get_or_raise(db, filing_id)

        if filing.filing_status != "rejected":
            raise ValueError(f"只能重试被拒绝的备案，当前状态: {filing.filing_status}")

        retry_count = (filing.response_data or {}).get("retry_count", 0)
        if retry_count >= MAX_RETRY_ATTEMPTS:
            raise ValueError(f"已达最大重试次数 ({MAX_RETRY_ATTEMPTS})，请联系管理员")

        filing.filing_status = "submitted"
        filing.submitted_at = _now()
        filing.error_message = None
        filing.responded_at = None
        filing.response_data = {
            **(filing.response_data or {}),
            "retry_count": retry_count + 1,
            "last_retry_at": _now().isoformat(),
        }

        await db.flush()
        logger.info("备案重试: filing_id=%s, retry_count=%d", filing_id, retry_count + 1)
        return self._to_dict(filing)

    # ── 列表查询 ──────────────────────────────────────────────────

    async def list_filings(
        self,
        db: AsyncSession,
        project_id: UUID | None = None,
        filing_type: str | None = None,
        filing_status: str | None = None,
    ) -> list[dict]:
        """列出备案记录"""
        stmt = (
            sa.select(RegulatoryFiling)
            .where(RegulatoryFiling.is_deleted == sa.false())
            .order_by(RegulatoryFiling.created_at.desc())
        )
        if project_id:
            stmt = stmt.where(RegulatoryFiling.project_id == project_id)
        if filing_type:
            stmt = stmt.where(RegulatoryFiling.filing_type == filing_type)
        if filing_status:
            stmt = stmt.where(RegulatoryFiling.filing_status == filing_status)

        result = await db.execute(stmt)
        return [self._to_dict(f) for f in result.scalars().all()]

    # ── 格式转换 stub ─────────────────────────────────────────────

    def _format_cicpa_data(self, data: dict) -> dict:
        """中注协数据格式转换（stub）"""
        return {"format": "cicpa_v1", "converted_at": _now().isoformat(), **data}

    def _format_archival_data(self, data: dict) -> dict:
        """电子底稿归档标准格式转换（stub）"""
        return {"format": "archival_v1", "converted_at": _now().isoformat(), **data}

    # ── 内部方法 ──────────────────────────────────────────────────

    async def _validate_project(self, db: AsyncSession, project_id: UUID) -> None:
        from app.models.core import Project
        result = await db.execute(
            sa.select(Project).where(Project.id == project_id, Project.is_deleted == sa.false())
        )
        if not result.scalar_one_or_none():
            raise ValueError("项目不存在")

    async def _get_or_raise(self, db: AsyncSession, filing_id: UUID) -> RegulatoryFiling:
        result = await db.execute(
            sa.select(RegulatoryFiling).where(
                RegulatoryFiling.id == filing_id, RegulatoryFiling.is_deleted == sa.false()
            )
        )
        filing = result.scalar_one_or_none()
        if not filing:
            raise ValueError("备案记录不存在")
        return filing

    def _to_dict(self, filing: RegulatoryFiling) -> dict:
        return {
            "id": str(filing.id),
            "project_id": str(filing.project_id),
            "filing_type": filing.filing_type,
            "filing_status": filing.filing_status,
            "submission_data": filing.submission_data,
            "response_data": filing.response_data,
            "submitted_at": filing.submitted_at.isoformat() if filing.submitted_at else None,
            "responded_at": filing.responded_at.isoformat() if filing.responded_at else None,
            "error_message": filing.error_message,
            "created_at": filing.created_at.isoformat() if filing.created_at else None,
        }
