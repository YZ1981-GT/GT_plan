"""报表附注数据锁定与版本快照服务

审计报告签字完成后自动锁定报表和附注数据，生成 JSON 快照。
支持管理员解锁（需填写原因+审计日志）和版本历史链。

Requirements: 53.1-53.7
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class NoteDataLockService:
    """报表附注数据锁定与版本快照服务"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def lock_on_sign_off(
        self,
        project_id: UUID,
        year: int,
    ) -> dict[str, Any]:
        """审计报告签字完成后自动锁定报表和附注。

        同时生成数据快照。
        """
        now = datetime.now(timezone.utc)

        # 生成快照
        snapshot = await self.create_snapshot(project_id, year)

        # 标记锁定
        await self._db.execute(
            text("""
                UPDATE projects
                SET wizard_state = jsonb_set(
                    COALESCE(wizard_state, '{}'),
                    '{data_locked}',
                    :lock_info
                )
                WHERE id = :pid
            """),
            {
                "pid": str(project_id),
                "lock_info": json.dumps({
                    "locked": True,
                    "locked_at": now.isoformat(),
                    "snapshot_id": snapshot["snapshot_id"],
                    "year": year,
                }),
            },
        )

        logger.info(
            "[DataLock] Locked project %s year %d after sign-off (snapshot=%s)",
            project_id, year, snapshot["snapshot_id"],
        )

        return {
            "project_id": str(project_id),
            "year": year,
            "locked": True,
            "locked_at": now.isoformat(),
            "snapshot_id": snapshot["snapshot_id"],
            "data_hash": snapshot["data_hash"],
        }

    async def create_snapshot(
        self,
        project_id: UUID,
        year: int,
    ) -> dict[str, Any]:
        """创建报表和附注数据的 JSON 快照。"""
        snapshot_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # 收集报表数据
        report_result = await self._db.execute(
            text("""
                SELECT report_type, row_code, row_name,
                       current_period_amount, prior_period_amount
                FROM financial_report
                WHERE project_id = :pid AND year = :year
                ORDER BY report_type, row_code
            """),
            {"pid": str(project_id), "year": year},
        )
        reports = [dict(r._mapping) for r in report_result.fetchall()]

        # 收集附注数据
        note_result = await self._db.execute(
            text("""
                SELECT section_code, title, content, table_data
                FROM disclosure_notes
                WHERE project_id = :pid AND year = :year
                ORDER BY sort_order
            """),
            {"pid": str(project_id), "year": year},
        )
        notes = [dict(r._mapping) for r in note_result.fetchall()]

        # 构建快照
        snapshot_data = {
            "project_id": str(project_id),
            "year": year,
            "created_at": now.isoformat(),
            "reports": reports,
            "notes": notes,
        }

        # 计算哈希
        data_json = json.dumps(snapshot_data, default=str, sort_keys=True)
        data_hash = hashlib.sha256(data_json.encode()).hexdigest()

        # 存储快照
        await self._db.execute(
            text("""
                INSERT INTO data_snapshots
                    (id, project_id, year, snapshot_data, data_hash, created_at)
                VALUES
                    (:id, :pid, :year, :data, :hash, :now)
            """),
            {
                "id": snapshot_id,
                "pid": str(project_id),
                "year": year,
                "data": data_json,
                "hash": data_hash,
                "now": now,
            },
        )

        logger.info(
            "[DataLock] Snapshot created: %s (reports=%d, notes=%d, hash=%s...)",
            snapshot_id, len(reports), len(notes), data_hash[:12],
        )

        return {
            "snapshot_id": snapshot_id,
            "data_hash": data_hash,
            "report_count": len(reports),
            "note_count": len(notes),
            "created_at": now.isoformat(),
        }

    async def unlock(
        self,
        project_id: UUID,
        year: int,
        user_id: UUID,
        reason: str,
    ) -> dict[str, Any]:
        """管理员解锁（需填写原因，记录审计日志）。"""
        now = datetime.now(timezone.utc)

        # 清除锁定标记
        await self._db.execute(
            text("""
                UPDATE projects
                SET wizard_state = jsonb_set(
                    COALESCE(wizard_state, '{}'),
                    '{data_locked}',
                    :lock_info
                )
                WHERE id = :pid
            """),
            {
                "pid": str(project_id),
                "lock_info": json.dumps({
                    "locked": False,
                    "unlocked_at": now.isoformat(),
                    "unlocked_by": str(user_id),
                    "unlock_reason": reason,
                    "year": year,
                }),
            },
        )

        # 记录审计日志
        await self._db.execute(
            text("""
                INSERT INTO audit_log_entries
                    (id, user_id, action, object_type, object_id, details, created_at)
                VALUES
                    (:id, :uid, :action, :obj_type, :obj_id, :details, :now)
            """),
            {
                "id": str(uuid4()),
                "uid": str(user_id),
                "action": "data_unlock",
                "obj_type": "project",
                "obj_id": str(project_id),
                "details": json.dumps({
                    "year": year,
                    "reason": reason,
                    "unlocked_at": now.isoformat(),
                }),
                "now": now,
            },
        )

        logger.info(
            "[DataLock] Unlocked project %s year %d by user %s (reason: %s)",
            project_id, year, user_id, reason,
        )

        return {
            "project_id": str(project_id),
            "year": year,
            "locked": False,
            "unlocked_at": now.isoformat(),
            "unlocked_by": str(user_id),
            "reason": reason,
        }

    async def get_snapshot_chain(
        self,
        project_id: UUID,
        year: int,
    ) -> list[dict[str, Any]]:
        """获取版本快照历史链。"""
        result = await self._db.execute(
            text("""
                SELECT id, data_hash, created_at
                FROM data_snapshots
                WHERE project_id = :pid AND year = :year
                ORDER BY created_at DESC
            """),
            {"pid": str(project_id), "year": year},
        )

        return [
            {
                "snapshot_id": str(r[0]),
                "data_hash": r[1],
                "created_at": str(r[2]),
            }
            for r in result.fetchall()
        ]

    async def is_locked(self, project_id: UUID, year: int) -> bool:
        """检查项目数据是否已锁定。"""
        result = await self._db.execute(
            text("SELECT wizard_state FROM projects WHERE id = :pid"),
            {"pid": str(project_id)},
        )
        row = result.first()
        if not row or not row[0]:
            return False

        ws = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        lock_info = ws.get("data_locked", {})
        return lock_info.get("locked", False) and lock_info.get("year") == year
