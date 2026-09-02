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
# 🔴 Task 12（workpaper-html-onlyoffice-bidirectional-writeback-closure）：
# storage/version 分叉收敛到统一 canonical resolver。改造前 `Path(wp.file_path)`
# + `.exists()` 对空 `file_path` 判 True ⇒ `file_path.parent` 是当前目录、
# `stem` 是空串，`shutil.copy2('.', ...)` 会以 IsADirectoryError 炸在快照步骤上；
# 且完全没有路径边界（Requirement 9.6 / Property 42）。
from app.services.workpaper_sync.canonical_paths import legacy_storage_root
from app.services.wp_export.wp_file_resolver import resolve_wp_file

logger = logging.getLogger(__name__)

#: 🔴 Task 12：项目存储根改为从 `canonical_paths.legacy_storage_root()` 取（单一真源）。
#: 改造前是 `Path(__file__).resolve().parent.parent.parent / "storage" / "projects"` ——
#: 与 WOPI 云端双写、`wp_download_service` 各拼一份，文件一搬家就静默指向错目录。
STORAGE_ROOT = legacy_storage_root()
MAX_VERSIONS = 10


class WpStorageService:
    """底稿存储优化"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_version(self, wp_id: UUID) -> dict:
        """把当前底稿文件复制成一份 `.versions` 快照（保留最近 MAX_VERSIONS 份）。

        🔴 Task 19（workpaper-html-onlyoffice-bidirectional-writeback-closure /
        Requirement 2.1、2.2、Property 61）：本方法**不再拥有版本计数器**。

        改造前它自己 `wp.file_version = (wp.file_version or 1) + 1`。那是一次
        「内容一个字节都没变」的版本推进 —— 它只是把**当前**文件复制到 `.versions/`。
        后果有两层：

        1. **伪版本**。备份动作把业务版本号往前推，于是「版本 7」可能与「版本 6」内容
           完全一致，`content_revision` 与 `file_version` 谁也解释不了差异；
        2. **四方争抢同一个计数器**。WOPI PutFile、离线上传、structure 保存与本方法都
           在 `+= 1` 同一列，谁先谁后不确定，快照名与版本号的对应关系随之不确定。

        改造后：快照名跟随**真正在动的那个**计数器（`content_revision`，由
        `ContentMutationService` 的 CAS 唯一推进），本方法只读不写。它因此也不再是
        content writer —— 它不改任何业务内容，只落一份备份。

        返回值把 `new_version` 换成 `content_revision`（快照对应的业务版本）与
        `snapshot_of_revision`；调用方要的是「这份备份是哪个版本的」，而不是一个由备份
        动作自己发明的号。
        """
        wp = (await self.db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )).scalar_one_or_none()
        if not wp:
            return {"error": "底稿不存在"}

        resolution = resolve_wp_file(
            wp.file_path, wp_code=None, allow_template_fallback=False
        )
        if resolution.path is None:
            # 分档保留（`empty` / `missing` / `path_rejected` 语义不同，调用方要能区分）
            logger.warning(
                "save_version: 底稿文件不可达 wp=%s verdict=%s reason=%s",
                wp_id, resolution.verdict, resolution.reason,
            )
            return {"error": resolution.reason, "verdict": resolution.verdict}
        file_path = resolution.path

        # 版本目录
        version_dir = file_path.parent / ".versions" / file_path.stem
        version_dir.mkdir(parents=True, exist_ok=True)

        # 复制当前文件为版本快照。名字里的 revision 取**当前** business content
        # revision：这份备份就是那个版本的内容。用一个由本方法自增的号会让
        # `{stem}_v1.xlsx` 在计数器不动时被反复覆盖 —— 备份看着在、实际只剩最后一份。
        content_revision = int(wp.content_revision or 0)
        version_name = (
            f"v{content_revision}_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}{file_path.suffix}"
        )
        version_path = version_dir / version_name
        shutil.copy2(str(file_path), str(version_path))

        # 清理超出限制的旧版本
        versions = sorted(version_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in versions[MAX_VERSIONS:]:
            old.unlink(missing_ok=True)

        return {
            "wp_id": str(wp_id),
            # 备份动作不产生新版本，所以没有 `new_version` 可回。回传的是「这份快照对应
            # 哪个业务版本」—— 调用方（wp_storage router / WOPI 后处理）需要的正是它。
            "content_revision": content_revision,
            "snapshot_of_revision": content_revision,
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

        resolution = resolve_wp_file(
            wp.file_path, wp_code=None, allow_template_fallback=False
        )
        if resolution.path is None:
            return []
        file_path = resolution.path
        version_dir = file_path.parent / ".versions" / file_path.stem
        # 🔴 用 `is_dir()` 而不是 `exists()`：下一行就 `iterdir()`，若同名是**文件**
        #    （历史脏数据完全可能），`exists()` 放行后 `iterdir()` 抛 NotADirectoryError。
        #    `exists()` 判可达也是本 spec 反复消灭的形态（`Path('')` 判 True）。
        if not version_dir.is_dir():
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
        # 同上：紧接着 `tar.add(dir)` 与 `rglob`，必须是目录才行。
        if not project_dir.is_dir():
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
