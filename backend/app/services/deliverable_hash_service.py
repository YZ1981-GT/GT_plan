"""交付物版本哈希链 — 防篡改完整性校验"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase13_models import WordExportTask, WordExportTaskVersion
from app.services.audit_log_helper import append_audit_log

logger = logging.getLogger(__name__)


@dataclass
class IntegrityResult:
    valid: bool
    tampered_versions: list[int]
    checked_count: int
    message: str | None = None


def compute_file_sha256(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


class DeliverableHashService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def bind_version_hash(
        self,
        version: WordExportTaskVersion,
        task: WordExportTask,
        user_id: UUID,
    ) -> None:
        """版本创建时写入 file_hash + 审计日志链条目"""
        if not version.file_path:
            return
        path = Path(version.file_path)
        if not path.exists():
            return

        file_hash = compute_file_sha256(path)
        entry_id = await append_audit_log(
            self.db,
            {
                "user_id": user_id,
                "project_id": task.project_id,
                "action": "deliverable_version_hash",
                "resource_type": "word_export_task_version",
                "resource_id": str(version.id),
                "details": {
                    "file_hash": file_hash,
                    "version_no": version.version_no,
                    "task_id": str(task.id),
                    "doc_type": task.doc_type,
                },
            },
        )
        version.file_hash = file_hash
        version.hash_chain_entry_id = entry_id
        await self.db.flush()

    async def verify_task_integrity(self, task_id: UUID) -> IntegrityResult:
        """校验各版本文件哈希与链上记录是否一致"""
        result = await self.db.execute(
            sa.select(WordExportTaskVersion)
            .where(WordExportTaskVersion.word_export_task_id == task_id)
            .order_by(WordExportTaskVersion.version_no.asc())
        )
        versions = list(result.scalars().all())
        tampered: list[int] = []
        checked = 0

        for ver in versions:
            if not ver.file_hash or not ver.file_path:
                continue
            path = Path(ver.file_path)
            if not path.exists():
                tampered.append(ver.version_no)
                checked += 1
                continue
            current = compute_file_sha256(path)
            checked += 1
            if current != ver.file_hash:
                tampered.append(ver.version_no)

        if tampered:
            return IntegrityResult(
                valid=False,
                tampered_versions=tampered,
                checked_count=checked,
                message=f"检测到 {len(tampered)} 个版本文件哈希不一致，可能已被篡改",
            )
        return IntegrityResult(
            valid=True,
            tampered_versions=[],
            checked_count=checked,
        )
