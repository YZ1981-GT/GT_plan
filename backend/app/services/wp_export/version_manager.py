"""WpVersionManager - 版本归档管理器

现有 WpUploadService.upload_file 已做 file_version+1、WORKPAPER_SAVED 事件、
云同步、version_line。本模块补充"归档旧文件 + wp_version_archive 记录 + 保留10版"
这一真实空白。

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


# ─── Pure Helper Functions (testable without DB) ──────────────────────────────


def archive_path_for(project_id: UUID | str, wp_id: UUID | str, version_no: int) -> str:
    """计算归档路径（纯函数，无副作用）

    Returns:
        格式: storage/projects/{project_id}/archive/{wp_id}/v{version_no}/
    """
    return f"storage/projects/{project_id}/archive/{wp_id}/v{version_no}/"


def mark_excess_versions(
    archives: list[dict[str, Any]], keep: int = 10
) -> list[dict[str, Any]]:
    """标记超出保留数的版本 file_retained=false（纯函数）

    Args:
        archives: 版本归档记录列表，每条须含 version_no 和 file_retained 字段
        keep: 保留最近多少个版本文件，默认 10

    Returns:
        标记后的列表（修改 file_retained 字段）。
        最近 keep 个版本保持 file_retained=True，其余置 False。
    """
    # 按 version_no 降序排列（最新在前）
    sorted_archives = sorted(archives, key=lambda a: a["version_no"], reverse=True)

    for idx, archive in enumerate(sorted_archives):
        if idx < keep:
            archive["file_retained"] = True
        else:
            archive["file_retained"] = False

    return sorted_archives


# ─── WpVersionManager Class ──────────────────────────────────────────────────


class WpVersionManager:
    """版本管理器 - 归档旧版本 + 保留10版

    现有 WpUploadService.upload_file 已做 file_version+1，
    本类补充归档能力。service 只 flush 不 commit。
    """

    async def create_version(
        self,
        db: Any,
        wp_id: UUID,
        file_content: bytes,
        source: str = "import",
        user_id: UUID | None = None,
    ) -> dict:
        """创建新版本归档记录

        1. 读取当前 working_paper 的 file_version 和 project_id
        2. 计算 content_hash
        3. 创建 WpVersionArchive 记录（version_no = 当前 file_version + 1）
        4. 归档旧文件（非阻塞）
        5. 清理超过 10 版的文件
        6. flush 不 commit

        Returns:
            dict with new_version, archive_path, content_hash, wp_id, project_id
        """
        from app.models.wp_export_models import WpVersionArchive

        # 1. 读取当前 working_paper
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.models.workpaper_models import WorkingPaper

        db_session: AsyncSession = db

        # 查询 working_paper 获取当前版本和项目信息（ORM，非 raw SQL）
        wp_result = await db_session.execute(
            select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )
        wp_row = wp_result.scalars().first()

        if wp_row is None:
            raise ValueError(f"WorkingPaper not found: {wp_id}")

        current_version = wp_row.file_version or 0
        project_id = wp_row.project_id
        file_path = wp_row.file_path
        new_version = current_version + 1

        # 2. 计算 content_hash
        content_hash = hashlib.sha256(file_content).hexdigest()

        # 3. 计算归档路径
        arch_path = archive_path_for(project_id, wp_id, new_version)

        # 4. 创建 WpVersionArchive 记录
        import uuid as uuid_mod

        archive_record = WpVersionArchive(
            id=uuid_mod.uuid4(),
            working_paper_id=wp_id,
            project_id=UUID(str(project_id)) if not isinstance(project_id, UUID) else project_id,
            version_no=new_version,
            source=source,
            content_hash=content_hash,
            file_size_bytes=len(file_content),
            archive_path=arch_path,
            file_retained=True,
            created_by=user_id,
        )
        db_session.add(archive_record)

        # 5. 归档旧文件（非阻塞，失败仅记日志）
        if file_path:
            try:
                await self.archive_old_version(
                    project_id=project_id,
                    wp_id=wp_id,
                    version=current_version,
                    file_path=file_path,
                )
            except Exception as e:
                logger.warning(
                    "归档旧版本失败 wp_id=%s version=%d: %s",
                    wp_id, current_version, e,
                )

        # 6. 清理超出 10 版的文件
        try:
            await self.cleanup_excess_versions(db_session, wp_id, keep=10)
        except Exception as e:
            logger.warning(
                "清理超限版本失败 wp_id=%s: %s", wp_id, e,
            )

        # flush 不 commit
        await db_session.flush()

        # 7. 发布 WORKPAPER_SAVED 事件触发下游级联更新（试算表重算、stale 标记）
        try:
            import asyncio

            from app.services.event_bus import event_bus

            event_payload = {
                "event_type": "WORKPAPER_SAVED",
                "project_id": str(project_id),
                "extra": {
                    "wp_id": str(wp_id),
                    "file_version": new_version,
                    "trigger": "import",
                    "content_hash": content_hash,
                    "source": source,
                },
            }
            asyncio.create_task(event_bus.publish(event_payload))
        except Exception as e:
            logger.warning("发布 WORKPAPER_SAVED 事件失败 wp_id=%s: %s", wp_id, e)

        return {
            "wp_id": wp_id,
            "project_id": project_id,
            "new_version": new_version,
            "archive_path": arch_path,
            "content_hash": content_hash,
            "source": source,
        }

    async def archive_old_version(
        self,
        project_id: UUID | str,
        wp_id: UUID | str,
        version: int,
        file_path: str | Path,
    ) -> None:
        """将旧版本文件移至归档路径

        目标: storage/projects/{pid}/archive/{wp_id}/v{n}/
        归档失败记录日志不阻塞。
        """
        if not file_path:
            return

        source_path = Path(file_path)
        if not source_path.exists():
            logger.info(
                "旧版本文件不存在，跳过归档 wp_id=%s version=%d path=%s",
                wp_id, version, file_path,
            )
            return

        arch_dir = Path(archive_path_for(project_id, wp_id, version))
        arch_dir.mkdir(parents=True, exist_ok=True)

        dest_path = arch_dir / source_path.name
        shutil.copy2(str(source_path), str(dest_path))
        logger.info(
            "旧版本已归档 wp_id=%s version=%d -> %s",
            wp_id, version, dest_path,
        )

    async def cleanup_excess_versions(
        self, db: Any, wp_id: UUID, keep: int = 10
    ) -> int:
        """清理超出保留数的文件（仅标记 file_retained=false，不删元数据）

        Returns:
            被标记为不保留的记录数
        """
        from sqlalchemy import select, update
        from sqlalchemy.ext.asyncio import AsyncSession

        from app.models.wp_export_models import WpVersionArchive

        db_session: AsyncSession = db

        # 查询该底稿所有版本归档记录
        result = await db_session.execute(
            select(WpVersionArchive)
            .where(WpVersionArchive.working_paper_id == wp_id)
            .order_by(WpVersionArchive.version_no.desc())
        )
        all_archives = result.scalars().all()

        if len(all_archives) <= keep:
            return 0

        # 标记超出部分
        excess_count = 0
        for idx, archive in enumerate(all_archives):
            if idx >= keep and archive.file_retained:
                archive.file_retained = False
                excess_count += 1

        if excess_count > 0:
            await db_session.flush()

        return excess_count
