"""底稿存储优化服务

Phase 9 Task 9.9: 文件版本管理 + 归档压缩 + 存储清理
"""

from __future__ import annotations

import logging
import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper

logger = logging.getLogger(__name__)

STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent / "storage" / "projects"
MAX_VERSIONS = 10


class WpStorageService:
    """底稿存储优化"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_version(self, wp_id: UUID) -> dict:
        """保存底稿版本（每次 WOPI PutFile 后调用）

        保留最近 MAX_VERSIONS 个版本，超出的自动清理。
        """
        wp = (await self.db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )).scalar_one_or_none()
        if not wp:
            return {"error": "底稿不存在"}

        file_path = Path(wp.file_path)
        if not file_path.exists():
            return {"error": "文件不存在"}

        # 版本目录
        version_dir = file_path.parent / ".versions" / file_path.stem
        version_dir.mkdir(parents=True, exist_ok=True)

        # 复制当前文件为版本快照
        version_name = f"v{wp.file_version}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}{file_path.suffix}"
        version_path = version_dir / version_name
        shutil.copy2(str(file_path), str(version_path))

        # 清理超出限制的旧版本
        versions = sorted(version_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in versions[MAX_VERSIONS:]:
            old.unlink(missing_ok=True)

        # 递增版本号
        wp.file_version = (wp.file_version or 1) + 1
        await self.db.flush()

        return {
            "wp_id": str(wp_id),
            "new_version": wp.file_version,
            "version_file": str(version_path),
            "total_versions": min(len(versions) + 1, MAX_VERSIONS),
        }

    async def list_versions(self, wp_id: UUID) -> list[dict]:
        """列出底稿的历史版本"""
        wp = (await self.db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )).scalar_one_or_none()
        if not wp:
            return []

        file_path = Path(wp.file_path)
        version_dir = file_path.parent / ".versions" / file_path.stem
        if not version_dir.exists():
            return []

        versions = sorted(version_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        return [
            {
                "filename": v.name,
                "size": v.stat().st_size,
                "modified": datetime.fromtimestamp(v.stat().st_mtime).isoformat(),
            }
            for v in versions
        ]

    async def archive_project(self, project_id: UUID) -> dict:
        """归档项目底稿 — 压缩为 .tar.gz 移到冷存储"""
        project_dir = STORAGE_ROOT / str(project_id)
        if not project_dir.exists():
            return {"error": "项目目录不存在"}

        archive_dir = STORAGE_ROOT.parent / "archives"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{project_id}.tar.gz"

        try:
            with tarfile.open(str(archive_path), "w:gz") as tar:
                tar.add(str(project_dir), arcname=str(project_id))

            archive_size = archive_path.stat().st_size
            original_size = sum(f.stat().st_size for f in project_dir.rglob("*") if f.is_file())

            logger.info(f"项目归档完成: {project_id}, {original_size} → {archive_size} bytes")
            return {
                "project_id": str(project_id),
                "archive_path": str(archive_path),
                "original_size": original_size,
                "archive_size": archive_size,
                "compression_ratio": round(archive_size / original_size * 100, 1) if original_size > 0 else 0,
            }
        except Exception as e:
            logger.error(f"归档失败: {e}")
            return {"error": str(e)}
