"""底稿下载与导入服务 — Phase 10 Task 1.1-1.2

提供底稿批量打包下载（含预填充）和离线编辑回传（含版本冲突检测）。
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper, WpIndex

logger = logging.getLogger(__name__)

STORAGE_ROOT = Path("storage")


class WpDownloadService:
    """底稿下载服务"""

    async def download_single(
        self, db: AsyncSession, project_id: UUID, wp_id: UUID,
    ) -> dict[str, Any]:
        """单个底稿下载，返回文件路径和元数据"""
        result = await db.execute(
            sa.select(WorkingPaper, WpIndex)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(WorkingPaper.id == wp_id,
                   WorkingPaper.project_id == project_id,
                   WorkingPaper.is_deleted == sa.false())
        )
        row = result.first()
        if not row:
            raise ValueError("底稿不存在")
        wp, idx = row
        file_path = Path(wp.file_path)
        if not file_path.exists():
            raise ValueError(f"底稿文件不存在: {wp.file_path}")
        return {
            "file_path": str(file_path),
            "file_name": f"{idx.wp_code}_{idx.wp_name}.xlsx",
            "file_version": wp.file_version,
            "wp_id": str(wp.id),
        }

    async def download_pack(
        self,
        db: AsyncSession,
        project_id: UUID,
        wp_ids: list[UUID],
        include_prefill: bool = True,
    ) -> io.BytesIO:
        """批量打包下载为 ZIP

        目录结构: {audit_cycle}/{wp_code}_{wp_name}.xlsx
        """
        result = await db.execute(
            sa.select(WorkingPaper, WpIndex)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.id.in_(wp_ids),
                WorkingPaper.is_deleted == sa.false(),
            )
        )
        rows = result.all()
        if not rows:
            raise ValueError("未找到可下载的底稿")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for wp, idx in rows:
                file_path = Path(wp.file_path)
                if not file_path.exists():
                    logger.warning("底稿文件缺失: %s", wp.file_path)
                    continue
                cycle = idx.audit_cycle or "其他"
                arc_name = f"{cycle}/{idx.wp_code}_{idx.wp_name}.xlsx"
                zf.write(file_path, arc_name)

        buf.seek(0)
        logger.info(
            "download_pack: project=%s, count=%d, size=%d bytes",
            project_id, len(rows), buf.getbuffer().nbytes,
        )
        return buf


class WpUploadService:
    """底稿导入服务（离线编辑回传）"""

    async def check_version_conflict(
        self, db: AsyncSession, wp_id: UUID, uploaded_version: int,
    ) -> dict[str, Any]:
        """检查版本冲突"""
        result = await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )
        wp = result.scalar_one_or_none()
        if not wp:
            raise ValueError("底稿不存在")

        has_conflict = uploaded_version < wp.file_version
        return {
            "has_conflict": has_conflict,
            "uploaded_version": uploaded_version,
            "server_version": wp.file_version,
            "wp_id": str(wp.id),
        }

    async def upload_file(
        self,
        db: AsyncSession,
        project_id: UUID,
        wp_id: UUID,
        file_content: bytes,
        uploaded_version: int,
        force_overwrite: bool = False,
    ) -> dict[str, Any]:
        """上传底稿文件

        Args:
            force_overwrite: True 时强制覆盖（忽略版本冲突）
        """
        result = await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.project_id == project_id,
            )
        )
        wp = result.scalar_one_or_none()
        if not wp:
            raise ValueError("底稿不存在")

        # 版本冲突检测
        if not force_overwrite and uploaded_version < wp.file_version:
            return {
                "status": "conflict",
                "uploaded_version": uploaded_version,
                "server_version": wp.file_version,
                "message": f"版本冲突: 上传版本 {uploaded_version} < 服务器版本 {wp.file_version}",
            }

        # 写入文件
        file_path = Path(wp.file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(file_content)

        # 更新数据库
        wp.file_version += 1
        wp.updated_at = datetime.utcnow()
        wp.prefill_stale = True  # 标记需要重新解析
        await db.flush()

        # 双写云端（非阻塞，失败只记日志）
        try:
            from app.services.cloud_storage_service import CloudStorageService, CLOUD_SYNC_ON_UPLOAD
            if CLOUD_SYNC_ON_UPLOAD:
                cloud_svc = CloudStorageService()
                # 获取项目信息
                import sqlalchemy as sa
                from app.models.core import Project
                proj_r = await db.execute(sa.select(Project).where(Project.id == project_id))
                proj = proj_r.scalar_one_or_none()
                if proj:
                    pname = proj.client_name or "unknown"
                    ws = proj.wizard_state or {}
                    yr = ws.get("steps", {}).get("basic_info", {}).get("data", {}).get("audit_year", 2025)
                    rel_path = str(file_path.relative_to(Path("storage") / "projects" / str(project_id)))
                    await cloud_svc.sync_single_file(project_id, pname, yr, file_path, rel_path)
        except Exception as e:
            logger.warning("cloud sync on upload failed (non-blocking): %s", e)

        # 触发 ParseService 解析关键单元格 → 回写 parsed_data
        try:
            from app.services.prefill_service import ParseService
            from app.services.task_center import create_task, update_task, TaskType, TaskStatus
            parse_task_id = create_task(TaskType.parse_workpaper, project_id=str(project_id), object_id=str(wp_id))
            update_task(parse_task_id, TaskStatus.processing)
            parse_svc = ParseService()
            parse_result = await parse_svc.parse_workpaper(db=db, project_id=project_id, wp_id=wp_id)
            update_task(parse_task_id, TaskStatus.success, result=parse_result)
            logger.info("parse after upload: wp=%s result=%s", wp_id, parse_result.get("status"))
        except Exception as e:
            try:
                update_task(parse_task_id, TaskStatus.failed, error=str(e))
            except Exception:
                pass
            logger.warning("parse after upload failed (non-blocking): %s", e)

        # 发布 WORKPAPER_SAVED 事件 → 级联更新试算表和报表
        try:
            from app.models.audit_platform_schemas import EventType, EventPayload
            from app.services.event_bus import event_bus
            payload = EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                project_id=project_id,
                extra={"wp_id": str(wp_id), "file_version": wp.file_version, "trigger": "upload"},
            )
            await event_bus.publish(payload)
            logger.info("event WORKPAPER_SAVED published: wp=%s", wp_id)
        except Exception as e:
            logger.warning("event publish failed (non-blocking): %s", e)

        logger.info(
            "upload_file: wp=%s, new_version=%d, size=%d bytes",
            wp_id, wp.file_version, len(file_content),
        )
        return {
            "status": "success",
            "wp_id": str(wp.id),
            "new_version": wp.file_version,
            "file_size": len(file_content),
        }
