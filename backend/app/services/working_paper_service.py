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
    WpReviewStatus,
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
                "status": wp.status.value if wp.status else (idx.status.value if idx.status else None),
                "review_status": wp.review_status.value if wp.review_status else "not_submitted",
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
        project_id: UUID | None = None,
    ) -> dict | None:
        """获取底稿详情（含索引信息、文件信息、最新QC状态）。"""
        query = (
            sa.select(WorkingPaper, WpIndex)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.id == wp_id,
                WorkingPaper.is_deleted == sa.false(),
                WpIndex.is_deleted == sa.false(),
            )
        )
        if project_id is not None:
            query = query.where(WorkingPaper.project_id == project_id)
        result = await db.execute(query)
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
            "status": wp.status.value if wp.status else (idx.status.value if idx.status else None),
            "review_status": wp.review_status.value if wp.review_status else "not_submitted",
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
        project_id: UUID | None = None,
    ) -> dict:
        """下载底稿（离线编辑）：执行预填充 → 返回文件信息。

        Validates: Requirements 7.1
        """
        query = sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.is_deleted == sa.false(),
        )
        if project_id is not None:
            query = query.where(WorkingPaper.project_id == project_id)
        result = await db.execute(query)
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
        project_id: UUID | None = None,
    ) -> dict:
        """上传离线编辑的底稿：冲突检测 → 版本递增。

        Validates: Requirements 7.2, 7.3, 7.4, 7.5
        """
        query = sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.is_deleted == sa.false(),
        )
        if project_id is not None:
            query = query.where(WorkingPaper.project_id == project_id)
        result = await db.execute(query)
        wp = result.scalar_one_or_none()
        if wp is None:
            raise ValueError("底稿不存在")

        # 归档后只读，禁止上传
        if wp.status == WpFileStatus.archived:
            return {
                "success": False,
                "has_conflict": False,
                "message": "底稿已归档，不允许修改。如需修改请先解除归档。",
            }

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
        project_id: UUID | None = None,
    ) -> dict:
        """更新底稿编制生命周期状态（与复核状态分开管理）。

        编制状态流转：
          draft → edit_complete → under_review → review_passed → archived
          under_review → revision_required → edit_complete（退回修改）
        """
        VALID_TRANSITIONS: dict[str, list[str]] = {
            "draft": ["edit_complete"],
            "edit_complete": ["draft", "under_review"],
            "under_review": ["revision_required", "review_passed"],
            "revision_required": ["edit_complete"],
            "review_passed": ["archived"],
            "archived": [],
            # 兼容旧值
            "review_level1_passed": ["review_level2_passed", "edit_complete", "archived"],
            "review_level2_passed": ["review_level1_passed", "archived"],
        }

        query = sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.is_deleted == sa.false(),
        )
        if project_id is not None:
            query = query.where(WorkingPaper.project_id == project_id)
        result = await db.execute(query)
        wp = result.scalar_one_or_none()
        if wp is None:
            raise ValueError("底稿不存在")

        try:
            new_enum = WpFileStatus(new_status)
        except ValueError:
            raise ValueError(f"无效状态: {new_status}")

        current = wp.status.value if wp.status else "draft"
        allowed = VALID_TRANSITIONS.get(current, [])
        if new_status not in allowed:
            raise ValueError(
                f"状态转换不允许: {current} → {new_status}（允许: {', '.join(allowed) or '无'}）"
            )

        wp.status = new_enum
        wp.updated_at = datetime.now(timezone.utc)
        await db.flush()

        # 同步更新 wp_index 状态
        idx_result = await db.execute(
            sa.select(WpIndex).where(WpIndex.id == wp.wp_index_id)
        )
        idx = idx_result.scalar_one_or_none()
        if idx:
            status_map = {
                WpFileStatus.draft: WpStatus.in_progress,
                WpFileStatus.edit_complete: WpStatus.draft_complete,
                WpFileStatus.under_review: WpStatus.draft_complete,
                WpFileStatus.revision_required: WpStatus.in_progress,
                WpFileStatus.review_passed: WpStatus.review_passed,
                WpFileStatus.archived: WpStatus.archived,
                WpFileStatus.review_level1_passed: WpStatus.review_passed,
                WpFileStatus.review_level2_passed: WpStatus.review_passed,
            }
            mapped = status_map.get(wp.status)
            if mapped:
                idx.status = mapped
                await db.flush()

        return {
            "wp_id": str(wp.id),
            "status": wp.status.value,
            "review_status": wp.review_status.value if wp.review_status else "not_submitted",
            "message": "状态已更新",
        }

    async def update_review_status(
        self,
        db: AsyncSession,
        wp_id: UUID,
        new_review_status: str,
        project_id: UUID | None = None,
    ) -> dict:
        """更新底稿复核任务状态（独立于编制状态）。

        复核状态流转：
          not_submitted → pending_level1 → level1_in_progress → level1_passed/level1_rejected
          level1_passed → pending_level2 → level2_in_progress → level2_passed/level2_rejected
          level1_rejected/level2_rejected → not_submitted（退回后重新提交）
        """
        REVIEW_TRANSITIONS: dict[str, list[str]] = {
            "not_submitted": ["pending_level1"],
            "pending_level1": ["level1_in_progress", "not_submitted"],
            "level1_in_progress": ["level1_passed", "level1_rejected"],
            "level1_passed": ["pending_level2"],
            "level1_rejected": ["not_submitted"],
            "pending_level2": ["level2_in_progress", "level1_passed"],
            "level2_in_progress": ["level2_passed", "level2_rejected"],
            "level2_passed": [],
            "level2_rejected": ["not_submitted", "pending_level1"],
        }

        query = sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.is_deleted == sa.false(),
        )
        if project_id is not None:
            query = query.where(WorkingPaper.project_id == project_id)
        result = await db.execute(query)
        wp = result.scalar_one_or_none()
        if wp is None:
            raise ValueError("底稿不存在")

        try:
            new_enum = WpReviewStatus(new_review_status)
        except ValueError:
            raise ValueError(f"无效复核状态: {new_review_status}")

        current = wp.review_status.value if wp.review_status else "not_submitted"
        allowed = REVIEW_TRANSITIONS.get(current, [])
        if new_review_status not in allowed:
            raise ValueError(
                f"复核状态转换不允许: {current} → {new_review_status}（允许: {', '.join(allowed) or '无'}）"
            )

        wp.review_status = new_enum
        wp.updated_at = datetime.now(timezone.utc)

        # 复核状态变化联动编制状态
        if new_review_status == "pending_level1":
            wp.status = WpFileStatus.under_review
        elif new_review_status in ("level1_rejected", "level2_rejected"):
            wp.status = WpFileStatus.revision_required
        elif new_review_status == "level2_passed":
            wp.status = WpFileStatus.review_passed

        await db.flush()

        return {
            "wp_id": str(wp.id),
            "status": wp.status.value,
            "review_status": wp.review_status.value,
            "message": "复核状态已更新",
        }

    async def assign_workpaper(
        self,
        db: AsyncSession,
        wp_id: UUID,
        assigned_to: UUID | None = None,
        reviewer: UUID | None = None,
        project_id: UUID | None = None,
    ) -> dict:
        """分配编制人和复核人。

        Validates: Requirements 6.1
        """
        query = sa.select(WorkingPaper).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.is_deleted == sa.false(),
        )
        if project_id is not None:
            query = query.where(WorkingPaper.project_id == project_id)
        result = await db.execute(query)
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
