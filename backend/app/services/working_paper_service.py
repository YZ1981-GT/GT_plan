"""底稿管理服务 — 列表/详情/离线下载上传/状态管理/分配

MVP实现：
- list_workpapers: 按循环/状态/编制人筛选
- get_workpaper: 详情含索引+文件+QC状态
- download_for_offline: stub预填充 + 返回文件信息
- upload_offline_edit: 冲突检测 + 版本递增
- update_status / assign_workpaper

Validates: Requirements 6.1, 7.1-7.5
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import (
    WpFileStatus,
    WpIndex,
    WpStatus,
    WorkingPaper,
    WpQcResult,
)

logger = logging.getLogger(__name__)


class WorkingPaperService:
    """底稿管理服务

    Validates: Requirements 6.1, 7.1-7.5
    """

    # ------------------------------------------------------------------
    # 10.1  list_workpapers / get_workpaper
    # ------------------------------------------------------------------

    async def list_workpapers(
        self,
        db: AsyncSession,
        project_id: UUID,
        audit_cycle: str | None = None,
        status: str | None = None,
        assigned_to: UUID | None = None,
    ) -> list[dict]:
        """获取项目底稿列表（支持按循环、状态、编制人筛选）。

        Validates: Requirements 6.1
        """
        query = (
            sa.select(WorkingPaper, WpIndex)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == sa.false(),
                WpIndex.is_deleted == sa.false(),
            )
        )

        if audit_cycle:
            query = query.where(WpIndex.audit_cycle == audit_cycle)
        if status:
            query = query.where(WpIndex.status == status)
        if assigned_to:
            query = query.where(WorkingPaper.assigned_to == assigned_to)

        query = query.order_by(WpIndex.wp_code)
        result = await db.execute(query)
        rows = result.all()

        items = []
        for wp, idx in rows:
            items.append({
                "id": str(wp.id),
                "project_id": str(wp.project_id),
                "wp_index_id": str(wp.wp_index_id),
                "wp_code": idx.wp_code,
                "wp_name": idx.wp_name,
                "audit_cycle": idx.audit_cycle,
                "index_status": idx.status.value if idx.status else None,
                "file_status": wp.status.value if wp.status else None,
                "assigned_to": str(wp.assigned_to) if wp.assigned_to else None,
                "reviewer": str(wp.reviewer) if wp.reviewer else None,
                "file_version": wp.file_version,
                "file_path": wp.file_path,
                "source_type": wp.source_type.value if wp.source_type else None,
                "created_at": wp.created_at.isoformat() if wp.created_at else None,
                "updated_at": wp.updated_at.isoformat() if wp.updated_at else None,
            })
        return items

    async def get_workpaper(
        self,
        db: AsyncSession,
        wp_id: UUID,
    ) -> dict | None:
        """获取底稿详情（含索引信息、文件信息、最新QC状态）。"""
        result = await db.execute(
            sa.select(WorkingPaper, WpIndex)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(WorkingPaper.id == wp_id)
        )
        row = result.one_or_none()
        if row is None:
            return None

        wp, idx = row

        # Get latest QC result
        qc_result = await db.execute(
            sa.select(WpQcResult)
            .where(WpQcResult.working_paper_id == wp_id)
            .order_by(WpQcResult.check_timestamp.desc())
            .limit(1)
        )
        qc = qc_result.scalar_one_or_none()

        return {
            "id": str(wp.id),
            "project_id": str(wp.project_id),
            "wp_index_id": str(wp.wp_index_id),
            "wp_code": idx.wp_code,
            "wp_name": idx.wp_name,
            "audit_cycle": idx.audit_cycle,
            "index_status": idx.status.value if idx.status else None,
            "file_status": wp.status.value if wp.status else None,
            "assigned_to": str(wp.assigned_to) if wp.assigned_to else None,
            "reviewer": str(wp.reviewer) if wp.reviewer else None,
            "file_version": wp.file_version,
            "file_path": wp.file_path,
            "source_type": wp.source_type.value if wp.source_type else None,
            "last_parsed_at": wp.last_parsed_at.isoformat() if wp.last_parsed_at else None,
            "qc_passed": qc.passed if qc else None,
            "qc_blocking_count": qc.blocking_count if qc else 0,
            "created_at": wp.created_at.isoformat() if wp.created_at else None,
            "updated_at": wp.updated_at.isoformat() if wp.updated_at else None,
        }

    # ------------------------------------------------------------------
    # 10.2  download_for_offline
    # ------------------------------------------------------------------

    async def download_for_offline(
        self,
        db: AsyncSession,
        wp_id: UUID,
    ) -> dict:
        """下载底稿（离线编辑）：执行预填充 → 返回文件信息。

        Validates: Requirements 7.1
        """
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )
        wp = result.scalar_one_or_none()
        if wp is None:
            raise ValueError("底稿不存在")

        # MVP stub: prefill is a no-op
        return {
            "wp_id": str(wp.id),
            "file_path": wp.file_path,
            "file_version": wp.file_version,
            "message": "MVP stub — 预填充暂未实现，返回文件信息",
        }

    # ------------------------------------------------------------------
    # 10.3  upload_offline_edit
    # ------------------------------------------------------------------

    async def upload_offline_edit(
        self,
        db: AsyncSession,
        wp_id: UUID,
        recorded_version: int,
    ) -> dict:
        """上传离线编辑的底稿：冲突检测 → 版本递增。

        Validates: Requirements 7.2, 7.3, 7.4, 7.5
        """
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )
        wp = result.scalar_one_or_none()
        if wp is None:
            raise ValueError("底稿不存在")

        # Conflict detection
        if recorded_version < wp.file_version:
            return {
                "success": False,
                "has_conflict": True,
                "uploaded_version": recorded_version,
                "server_version": wp.file_version,
                "message": f"版本冲突: 上传版本 {recorded_version} < 服务器版本 {wp.file_version}",
            }

        # No conflict — increment version (stub: no actual file replacement)
        wp.file_version += 1
        wp.updated_at = datetime.now(timezone.utc)
        await db.flush()

        return {
            "success": True,
            "has_conflict": False,
            "new_version": wp.file_version,
            "message": "上传成功",
        }

    # ------------------------------------------------------------------
    # 10.4  update_status / assign_workpaper
    # ------------------------------------------------------------------

    async def update_status(
        self,
        db: AsyncSession,
        wp_id: UUID,
        new_status: str,
    ) -> dict:
        """更新底稿状态。

        Validates: Requirements 6.1
        """
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )
        wp = result.scalar_one_or_none()
        if wp is None:
            raise ValueError("底稿不存在")

        try:
            wp.status = WpFileStatus(new_status)
        except ValueError:
            raise ValueError(f"无效状态: {new_status}")

        wp.updated_at = datetime.now(timezone.utc)
        await db.flush()

        # Also update wp_index status
        idx_result = await db.execute(
            sa.select(WpIndex).where(WpIndex.id == wp.wp_index_id)
        )
        idx = idx_result.scalar_one_or_none()
        if idx:
            # Map file status to index status
            status_map = {
                WpFileStatus.draft: WpStatus.in_progress,
                WpFileStatus.edit_complete: WpStatus.draft_complete,
                WpFileStatus.review_level1_passed: WpStatus.review_passed,
                WpFileStatus.review_level2_passed: WpStatus.review_passed,
                WpFileStatus.archived: WpStatus.archived,
            }
            mapped = status_map.get(wp.status)
            if mapped:
                idx.status = mapped
                await db.flush()

        return {
            "wp_id": str(wp.id),
            "status": wp.status.value,
            "message": "状态已更新",
        }

    async def assign_workpaper(
        self,
        db: AsyncSession,
        wp_id: UUID,
        assigned_to: UUID | None = None,
        reviewer: UUID | None = None,
    ) -> dict:
        """分配编制人和复核人。

        Validates: Requirements 6.1
        """
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )
        wp = result.scalar_one_or_none()
        if wp is None:
            raise ValueError("底稿不存在")

        if assigned_to is not None:
            wp.assigned_to = assigned_to
        if reviewer is not None:
            wp.reviewer = reviewer
        wp.updated_at = datetime.now(timezone.utc)
        await db.flush()

        # Also update wp_index
        idx_result = await db.execute(
            sa.select(WpIndex).where(WpIndex.id == wp.wp_index_id)
        )
        idx = idx_result.scalar_one_or_none()
        if idx:
            if assigned_to is not None:
                idx.assigned_to = assigned_to
            if reviewer is not None:
                idx.reviewer = reviewer
            await db.flush()

        return {
            "wp_id": str(wp.id),
            "assigned_to": str(wp.assigned_to) if wp.assigned_to else None,
            "reviewer": str(wp.reviewer) if wp.reviewer else None,
            "message": "分配成功",
        }
