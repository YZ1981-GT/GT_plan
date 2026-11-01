"""附件存储位置的唯一安全解析器。

任何领域授权完成后的本地附件读取、转换、OCR、归档和删除，都必须先经本模块把
``(project_id, storage_type, storage_key)`` 解析为项目附件根内的 canonical path。
知道服务器路径、附件 ID 或 blob hash 都不构成读取权限。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

from app.core.config import settings

PAPERLESS_PREFIX = "paperless://"
ACTIVE_CONTENT_EXTENSIONS = frozenset({".svg", ".html", ".htm", ".xhtml"})


@dataclass(frozen=True)
class StoredAttachmentRef:
    """提交后物理清理所需的最小、带项目作用域的存储引用。"""

    project_id: UUID
    storage_type: str | None
    storage_key: str | None


@dataclass(frozen=True)
class AttachmentReadPlan:
    kind: Literal["local", "remote", "rejected"]
    canonical_path: Path | None = None
    remote_locator: str | None = None
    reason: str | None = None

    @property
    def rejected(self) -> bool:
        return self.kind == "rejected"


def attachment_root(root: str | Path | None = None) -> Path:
    """返回配置的附件根；相对路径按当前后端进程 cwd 解释，与写入路径一致。"""
    configured = Path(root if root is not None else settings.ATTACHMENT_LOCAL_STORAGE_ROOT)
    return configured.resolve(strict=False)


def project_attachment_root(project_id: UUID | str, root: str | Path | None = None) -> Path:
    return (attachment_root(root) / str(project_id)).resolve(strict=False)


def _within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _candidate_paths(raw: str, project_root: Path, global_root: Path) -> list[Path]:
    value = Path(raw)
    if value.is_absolute():
        return [value]
    # 兼容三种历史表示：从 cwd 起的完整相对路径、从附件根起、从项目根起。
    return [Path.cwd() / value, global_root / value, project_root / value]

def plan_project_attachment(
    project_id: UUID | str,
    storage_type: str | None,
    storage_key: str | None,
    *,
    root: str | Path | None = None,
    require_file: bool = True,
) -> AttachmentReadPlan:
    """解析项目附件存储位置；越界、跨项目、软链接逃逸和未知 scheme 均拒绝。"""
    key = (storage_key or "").strip()
    kind = (storage_type or "").strip().lower()
    if not key:
        return AttachmentReadPlan("rejected", reason="empty")
    if key.startswith(PAPERLESS_PREFIX) or kind == "paperless":
        if not key.startswith(PAPERLESS_PREFIX):
            return AttachmentReadPlan("rejected", reason="invalid_remote_locator")
        return AttachmentReadPlan("remote", remote_locator=key)
    if "://" in key:
        return AttachmentReadPlan("rejected", reason="unsupported_scheme")

    global_root = attachment_root(root)
    scoped_root = project_attachment_root(project_id, global_root)
    seen: set[str] = set()
    for raw_candidate in _candidate_paths(key, scoped_root, global_root):
        try:
            # strict=False 仍会解析已存在的 symlink/junction；不存在的尾段保持可判边界。
            candidate = raw_candidate.resolve(strict=False)
        except (OSError, RuntimeError):
            continue
        marker = os.path.normcase(str(candidate))
        if marker in seen:
            continue
        seen.add(marker)
        if not _within(candidate, scoped_root):
            continue
        if require_file and not candidate.is_file():
            continue
        return AttachmentReadPlan("local", canonical_path=candidate)
    return AttachmentReadPlan("rejected", reason="outside_project_root_or_missing")


def resolve_project_attachment_file(
    project_id: UUID | str,
    storage_type: str | None,
    storage_key: str | None,
    *,
    root: str | Path | None = None,
) -> Path | None:
    plan = plan_project_attachment(project_id, storage_type, storage_key, root=root)
    return plan.canonical_path if plan.kind == "local" else None


def inline_preview_allowed(file_name: str | None) -> bool:
    """活动内容不以内联同源资源返回；只允许走下载。"""
    return Path(file_name or "").suffix.lower() not in ACTIVE_CONTENT_EXTENSIONS
