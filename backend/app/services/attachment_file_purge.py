"""回收站彻底删除附件后删本地物理文件（spec attachment-archive-and-a-class-evidence 需求 9，ADR-AE-12）。

改造前彻底删除只删附件行、文件留在磁盘 ⇒ 孤儿文件越积越多（归档完整性检查「孤儿文件」类别的主要来源）。

删除条件（缺一不删）：
- 是本地文件（``paperless://`` 由 Paperless 管理，不删）且读得到；
- 解析后在附件存储根 ``ATTACHMENT_LOCAL_STORAGE_ROOT`` 内（与上传落盘的 ``ensure_within_root`` 同口径）；
- 没有其他附件行（含已删除的）或治理版本行引用同一文件 —— 版本行、复制出的附件可能共用一个文件。

必须在删除附件行的事务 **提交之后** 调用：提交失败则文件保留；删文件失败只记日志并计数，不回滚已提交的删除。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import logging
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.services.attachment_storage_resolver import StoredAttachmentRef

logger = logging.getLogger(__name__)


async def unlink_unreferenced_files(
    db: AsyncSession,
    refs: Iterable["StoredAttachmentRef"],
) -> dict[str, int]:
    """删除已提交业务行留下的本地字节；每个引用必须携带原项目作用域。"""
    from app.services.archive_inventory import normalized_path, referenced_local_paths
    from app.services.attachment_storage_resolver import (
        StoredAttachmentRef,
        plan_project_attachment,
    )

    stats = {"deleted": 0, "kept_referenced": 0, "skipped_outside_root": 0, "failed": 0}
    unique = {
        (str(ref.project_id), ref.storage_type or "", ref.storage_key or ""): ref
        for ref in refs
        if isinstance(ref, StoredAttachmentRef) and ref.storage_key
    }
    for ref in unique.values():
        plan = plan_project_attachment(ref.project_id, ref.storage_type, ref.storage_key)
        if plan.kind == "remote":
            continue
        if plan.kind != "local" or plan.canonical_path is None:
            stats["skipped_outside_root"] += 1
            continue
        resolved = plan.canonical_path
        try:
            referenced = await referenced_local_paths(db, project_id=ref.project_id)
        except Exception:  # noqa: BLE001 — 查不出引用就不删（宁可留孤儿，不误删共用文件）
            logger.warning("附件文件引用查询失败，保留文件", exc_info=True)
            stats["failed"] += 1
            continue
        if normalized_path(resolved) in referenced:
            stats["kept_referenced"] += 1
            continue
        try:
            resolved.unlink()
            stats["deleted"] += 1
        except OSError:
            logger.warning("附件文件删除失败", exc_info=True)
            stats["failed"] += 1
    return stats


def cleanup_message(stats: dict[str, int]) -> str:
    """回执附言：只在有文件删不掉时提示。"""
    return f"（{stats['failed']} 个附件文件未能从磁盘删除，已记录日志）" if stats.get("failed") else ""
