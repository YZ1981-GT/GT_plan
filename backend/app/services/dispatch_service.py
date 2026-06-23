"""分发记录业务服务 — D0-1 跨底稿分发持久化

Feature: cross-workpaper-dispatch-persistence

设计要点：
- batch_create: INSERT ON CONFLICT DO NOTHING + 二次查询确定 skipped
- service 只 flush 不 commit（router 层 commit）
- revoke: 权限校验 + 删除
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dispatch_models import DispatchRecord


# ─── 目标白名单 ─────────────────────────────────────────────────────────────

VALID_TARGETS = {"D0-4", "D0-5", "D0-6", "D0-7"}


# ─── 数据结构 ────────────────────────────────────────────────────────────────


@dataclass
class DispatchEntry:
    """单条分发请求数据"""

    confirm_index: str
    target: str
    entity_name: str | None = None
    account_type: str | None = None
    amount: Decimal | None = None
    reason: str | None = None


@dataclass
class BatchResult:
    """批量创建结果"""

    dispatched: list[DispatchRecord] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)


# ─── 异常 ────────────────────────────────────────────────────────────────────


class DispatchNotFoundError(Exception):
    """分发记录不存在"""

    pass


class DispatchPermissionError(Exception):
    """撤回权限不足"""

    pass


# ─── 服务类 ──────────────────────────────────────────────────────────────────


class DispatchService:
    """分发记录持久化服务"""

    @staticmethod
    async def batch_create(
        db: AsyncSession,
        project_id: uuid.UUID,
        entries: list[DispatchEntry],
        user_id: uuid.UUID,
    ) -> BatchResult:
        """批量创建分发记录（去重：ON CONFLICT DO NOTHING）

        实现策略：
        1. 批量 INSERT ... ON CONFLICT DO NOTHING，得到实际插入的行（RETURNING id）
        2. 二次查询入参集合中已存在的记录，用差集确定 skipped
        """
        result = BatchResult()

        if not entries:
            return result

        # 构建插入值
        now = datetime.now(timezone.utc)
        insert_values = []
        for entry in entries:
            insert_values.append(
                {
                    "id": uuid.uuid4(),
                    "project_id": project_id,
                    "confirm_index": entry.confirm_index,
                    "target": entry.target,
                    "entity_name": entry.entity_name,
                    "account_type": entry.account_type,
                    "amount": entry.amount,
                    "reason": entry.reason,
                    "dispatched_by": user_id,
                    "dispatched_at": now,
                }
            )

        # INSERT ON CONFLICT DO NOTHING + RETURNING
        stmt = (
            sa.dialects.postgresql.insert(DispatchRecord)
            .values(insert_values)
            .on_conflict_do_nothing(constraint="uq_dispatch_dedup")
            .returning(DispatchRecord.id)
        )
        inserted_result = await db.execute(stmt)
        inserted_ids = {row[0] for row in inserted_result.fetchall()}

        # 查询本次实际插入的完整记录
        if inserted_ids:
            inserted_records = (
                await db.execute(
                    sa.select(DispatchRecord).where(
                        DispatchRecord.id.in_(inserted_ids)
                    )
                )
            ).scalars().all()
            result.dispatched = list(inserted_records)

        # 确定 skipped：入参中存在于 DB 但未被本次插入的（已有重复）
        input_keys = {(e.confirm_index, e.target) for e in entries}
        dispatched_keys = {
            (r.confirm_index, r.target) for r in result.dispatched
        }
        skipped_keys = input_keys - dispatched_keys

        if skipped_keys:
            for key in skipped_keys:
                result.skipped.append(
                    {
                        "confirm_index": key[0],
                        "target": key[1],
                        "reason": "duplicate",
                    }
                )

        await db.flush()
        return result

    @staticmethod
    async def list_records(
        db: AsyncSession,
        project_id: uuid.UUID,
        *,
        target: str | None = None,
        confirm_index: str | None = None,
    ) -> list[DispatchRecord]:
        """查询分发记录（可选过滤）"""
        stmt = sa.select(DispatchRecord).where(
            DispatchRecord.project_id == project_id
        )

        if target is not None:
            stmt = stmt.where(DispatchRecord.target == target)
        if confirm_index is not None:
            stmt = stmt.where(DispatchRecord.confirm_index == confirm_index)

        stmt = stmt.order_by(DispatchRecord.dispatched_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def revoke(
        db: AsyncSession,
        record_id: uuid.UUID,
        user_id: uuid.UUID,
        is_manager: bool = False,
    ) -> DispatchRecord:
        """撤回分发记录

        权限校验：dispatched_by 本人 OR manager/partner 角色
        """
        record = (
            await db.execute(
                sa.select(DispatchRecord).where(DispatchRecord.id == record_id)
            )
        ).scalar_one_or_none()

        if record is None:
            raise DispatchNotFoundError(f"Record {record_id} not found")

        # 权限检查
        if record.dispatched_by != user_id and not is_manager:
            raise DispatchPermissionError(
                "Only the dispatcher or a manager/partner can revoke"
            )

        await db.delete(record)
        await db.flush()
        return record
