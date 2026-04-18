"""私人库存储服务 — Phase 10 Task 3.1

用户私人文件存储，容量管理（1GB上限），归档联动，存储统计。
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage"))


class PrivateStorageService:
    """私人库管理"""

    MAX_SIZE_BYTES = 1 * 1024 * 1024 * 1024  # 1GB
    WARN_THRESHOLD = 0.9

    def _user_dir(self, user_id: UUID) -> Path:
        return STORAGE_ROOT / "users" / str(user_id) / "private"

    async def check_quota(self, user_id: UUID) -> dict[str, Any]:
        """检查容量"""
        path = self._user_dir(user_id)
        if not path.exists():
            return {"used": 0, "limit": self.MAX_SIZE_BYTES, "usage_pct": 0.0, "warning": False}
        used = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        pct = used / self.MAX_SIZE_BYTES if self.MAX_SIZE_BYTES > 0 else 0
        return {
            "used": used,
            "limit": self.MAX_SIZE_BYTES,
            "usage_pct": round(pct, 4),
            "warning": pct >= self.WARN_THRESHOLD,
        }

    async def list_files(self, user_id: UUID) -> list[dict[str, Any]]:
        """列出私人库文件"""
        path = self._user_dir(user_id)
        if not path.exists():
            return []
        files = []
        for f in sorted(path.rglob("*")):
            if f.is_file():
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "path": str(f.relative_to(path)),
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
        return files

    async def upload_file(self, user_id: UUID, filename: str, content: bytes) -> dict[str, Any]:
        """上传文件到私人库"""
        quota = await self.check_quota(user_id)
        if quota["used"] + len(content) > self.MAX_SIZE_BYTES:
            raise ValueError(f"容量不足：已用 {quota['used']/(1024*1024):.1f}MB，上限 {self.MAX_SIZE_BYTES/(1024*1024):.0f}MB")

        path = self._user_dir(user_id)
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / filename
        file_path.write_bytes(content)
        logger.info("private_storage upload: user=%s, file=%s, size=%d", user_id, filename, len(content))
        return {"name": filename, "size": len(content), "path": str(file_path.relative_to(path))}

    async def delete_file(self, user_id: UUID, filename: str) -> bool:
        """删除私人库文件"""
        file_path = self._user_dir(user_id) / filename
        if file_path.exists():
            file_path.unlink()
            return True
        return False


class ProjectArchiveService:
    """归档联动服务（Phase 10）

    归档流程：锁定底稿 → 生成清单 → 推送云端 → 可选清理本地
    """

    async def archive_project(
        self, db: Any, project_id: UUID,
        push_to_cloud: bool = True,
        cleanup_local: bool = False,
    ) -> dict[str, Any]:
        """项目归档：锁定底稿+生成清单+推送云端"""
        import sqlalchemy as sa
        from app.models.workpaper_models import WorkingPaper, WpIndex

        # 1. 锁定所有底稿为 archived
        result = await db.execute(
            sa.select(WorkingPaper, WpIndex)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(WorkingPaper.project_id == project_id, WorkingPaper.is_deleted == sa.false())
        )
        rows = result.all()
        archive_list = []
        for wp, idx in rows:
            wp.status = "archived"
            archive_list.append({
                "wp_code": idx.wp_code,
                "wp_name": idx.wp_name,
                "status": "archived",
                "file_version": wp.file_version,
                "assigned_to": str(wp.assigned_to) if wp.assigned_to else None,
                "reviewer": str(wp.reviewer) if wp.reviewer else None,
            })
        await db.flush()

        # 2. 获取项目信息用于云端目录命名
        from app.models.core import Project
        proj_result = await db.execute(
            sa.select(Project).where(Project.id == project_id)
        )
        project = proj_result.scalar_one_or_none()
        project_name = project.client_name if project else "unknown"
        year = 2025  # 从 wizard_state 取
        if project and project.wizard_state:
            bi = project.wizard_state.get("steps", {}).get("basic_info", {}).get("data", {})
            year = bi.get("audit_year", 2025)

        # 3. 推送云端
        cloud_result = None
        if push_to_cloud:
            from app.services.cloud_storage_service import CloudStorageService
            cloud_svc = CloudStorageService()
            try:
                cloud_result = await cloud_svc.upload_project_archive(project_id, project_name, year)
                logger.info("cloud_push: project=%s result=%s", project_id, cloud_result.get("status"))
            except Exception as e:
                logger.error("cloud_push failed: %s", e)
                cloud_result = {"status": "failed", "error": str(e)}

        # 4. 可选清理本地
        cleanup_result = None
        if cleanup_local and cloud_result and cloud_result.get("status") == "success":
            from app.services.cloud_storage_service import CloudStorageService
            cloud_svc = CloudStorageService()
            cleanup_result = await cloud_svc.cleanup_local_after_archive(project_id)

        logger.info("archive_project: project=%s, workpapers=%d", project_id, len(archive_list))
        return {
            "project_id": str(project_id),
            "archived_count": len(archive_list),
            "archive_list": archive_list,
            "cloud_push": cloud_result,
            "local_cleanup": cleanup_result,
        }


class StorageStatsService:
    """存储统计"""

    async def get_stats(self) -> dict[str, Any]:
        """按项目/用户/年度统计存储占用"""
        total = 0
        by_project: list[dict] = []
        by_user: list[dict] = []

        # 项目存储
        projects_dir = STORAGE_ROOT / "projects"
        if projects_dir.exists():
            for p in projects_dir.iterdir():
                if p.is_dir():
                    size = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
                    total += size
                    by_project.append({"project_id": p.name, "size": size})

        # 用户私人库
        users_dir = STORAGE_ROOT / "users"
        if users_dir.exists():
            for u in users_dir.iterdir():
                if u.is_dir():
                    size = sum(f.stat().st_size for f in u.rglob("*") if f.is_file())
                    total += size
                    by_user.append({"user_id": u.name, "size": size})

        return {
            "total_size": total,
            "by_project": sorted(by_project, key=lambda x: x["size"], reverse=True),
            "by_user": sorted(by_user, key=lambda x: x["size"], reverse=True),
        }
