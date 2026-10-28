"""回收站彻底删除附件后删本地物理文件（spec attachment-archive-and-a-class-evidence 需求 9，ADR-AE-12）。

改造前彻底删除只删附件行、文件留在磁盘 ⇒ 孤儿文件越积越多（归档完整性检查「孤儿文件」类别的主要来源）。

删除条件（缺一不删）：
- 是本地文件（``paperless://`` 由 Paperless 管理，不删）且读得到；
- 解析后在附件存储根 ``ATTACHMENT_LOCAL_STORAGE_ROOT`` 内（与上传落盘的 ``ensure_within_root`` 同口径）；
- 没有其他附件行（含已删除的）或治理版本行引用同一文件 —— 版本行、复制出的附件可能共用一个文件。

必须在删除附件行的事务 **提交之后** 调用：提交失败则文件保留；删文件失败只记日志并计数，不回滚已提交的删除。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def unlink_unreferenced_files(db: AsyncSession, raw_paths: Iterable[str | None]) -> dict[str, int]:
    from app.core.config import settings
    from app.services.archive_inventory import normalized_path, referenced_local_paths
    from app.services.attachment_upload_policy import resolve_local_attachment_file

    root = Path(settings.ATTACHMENT_LOCAL_STORAGE_ROOT).resolve()
    stats = {"deleted": 0, "kept_referenced": 0, "skipped_outside_root": 0, "failed": 0}
    for raw in dict.fromkeys(p for p in raw_paths if p):
        path = resolve_local_attachment_file(raw)
        if path is None:
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            stats["skipped_outside_root"] += 1
            continue
        try:
            referenced = await referenced_local_paths(db, name_hint=path.name)
        except Exception:  # noqa: BLE001 — 查不出引用就不删（宁可留孤儿，不误删共用文件）
            logger.warning("附件文件引用查询失败，保留文件 path=%s", resolved, exc_info=True)
            stats["failed"] += 1
            continue
        if normalized_path(resolved) in referenced:
            stats["kept_referenced"] += 1
            continue
        try:
            resolved.unlink()
            stats["deleted"] += 1
        except OSError:
            logger.warning("附件文件删除失败 path=%s", resolved, exc_info=True)
            stats["failed"] += 1
    return stats


def cleanup_message(stats: dict[str, int]) -> str:
    """回执附言：只在有文件删不掉时提示。"""
    return f"（{stats['failed']} 个附件文件未能从磁盘删除，已记录日志）" if stats.get("failed") else ""
