"""底稿快照服务

Sprint 8 Task 8.2: 自动创建 + 对比 + 锁定。
触发时机：预填充完成 / 提交复核 / 签字时。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class WpSnapshotService:
    """底稿快照服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_snapshot(
        self,
        wp_id: UUID,
        trigger_event: str,
        user_id: UUID,
        bound_dataset_id: Optional[UUID] = None,
    ) -> dict:
        """创建底稿快照

        Args:
            wp_id: 底稿 ID
            trigger_event: 触发事件 (prefill/review/sign)
            user_id: 操作人
            bound_dataset_id: 绑定的数据集 ID（签字时锁定）

        Returns:
            快照信息
        """
        # 获取底稿当前公式单元格值
        wp = (await self.db.execute(sa.text(
            "SELECT parsed_data, quality_score FROM working_paper WHERE id = :wid"
        ), {"wid": str(wp_id)})).first()

        if not wp:
            return {"error": "底稿不存在"}

        # 提取公式单元格的当前值作为快照数据
        parsed = wp.parsed_data or {}
        snapshot_data = {
            "formula_values": parsed.get("formula_values", {}),
            "audited_amounts": parsed.get("audited_amounts", {}),
            "quality_score": wp.quality_score,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }

        snapshot_id = uuid4()
        is_locked = trigger_event == "sign"

        await self.db.execute(sa.text("""
            INSERT INTO workpaper_snapshots (id, wp_id, trigger_event, snapshot_data,
                                            created_by, created_at, is_locked, bound_dataset_id)
            VALUES (:id, :wid, :evt, :data, :uid, :ts, :locked, :dsid)
        """), {
            "id": str(snapshot_id),
            "wid": str(wp_id),
            "evt": trigger_event,
            "data": sa.type_coerce(snapshot_data, sa.JSON),
            "uid": str(user_id),
            "ts": datetime.now(timezone.utc),
            "locked": is_locked,
            "dsid": str(bound_dataset_id) if bound_dataset_id else None,
        })
        await self.db.flush()

        logger.info("Snapshot created: wp=%s event=%s locked=%s", wp_id, trigger_event, is_locked)
        return {
            "snapshot_id": str(snapshot_id),
            "trigger_event": trigger_event,
            "is_locked": is_locked,
        }

    async def list_snapshots(self, wp_id: UUID) -> list[dict]:
        """获取底稿快照列表"""
        rows = (await self.db.execute(sa.text("""
            SELECT id, trigger_event, created_at, created_by, is_locked
            FROM workpaper_snapshots
            WHERE wp_id = :wid
            ORDER BY created_at DESC
        """), {"wid": str(wp_id)})).fetchall()

        return [
            {
                "id": r.id,
                "trigger_event": r.trigger_event,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "created_by": r.created_by,
                "is_locked": r.is_locked,
            }
            for r in rows
        ]

    async def compare_snapshots(
        self, snapshot_id_a: UUID, snapshot_id_b: UUID
    ) -> dict:
        """对比两个快照，返回差异

        Returns:
            {changes: [{field, old_value, new_value}], summary}
        """
        rows = (await self.db.execute(sa.text("""
            SELECT id, snapshot_data FROM workpaper_snapshots
            WHERE id IN (:a, :b)
        """), {"a": str(snapshot_id_a), "b": str(snapshot_id_b)})).fetchall()

        if len(rows) < 2:
            return {"error": "快照不存在", "changes": []}

        data_map = {r.id: r.snapshot_data for r in rows}
        data_a = data_map.get(str(snapshot_id_a), {})
        data_b = data_map.get(str(snapshot_id_b), {})

        changes = []
        # 对比公式值
        vals_a = data_a.get("formula_values", {})
        vals_b = data_b.get("formula_values", {})
        all_keys = set(list(vals_a.keys()) + list(vals_b.keys()))

        for key in sorted(all_keys):
            old_val = vals_a.get(key)
            new_val = vals_b.get(key)
            if old_val != new_val:
                changes.append({
                    "field": key,
                    "old_value": old_val,
                    "new_value": new_val,
                })

        # 对比审定数
        amts_a = data_a.get("audited_amounts", {})
        amts_b = data_b.get("audited_amounts", {})
        for key in set(list(amts_a.keys()) + list(amts_b.keys())):
            old_val = amts_a.get(key)
            new_val = amts_b.get(key)
            if old_val != new_val:
                changes.append({
                    "field": f"audited:{key}",
                    "old_value": old_val,
                    "new_value": new_val,
                })

        return {
            "changes": changes,
            "total_changes": len(changes),
            "summary": f"共 {len(changes)} 处变更",
        }

    async def lock_snapshot(self, snapshot_id: UUID) -> bool:
        """锁定快照（签字后不可删除）"""
        result = await self.db.execute(sa.text(
            "UPDATE workpaper_snapshots SET is_locked = true WHERE id = :sid"
        ), {"sid": str(snapshot_id)})
        await self.db.flush()
        return result.rowcount > 0
