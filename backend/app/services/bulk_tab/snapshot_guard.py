"""SnapshotGuard — 批量导入前快照 + 失败回滚（复用 version-trail）。

职责：
  - snapshot(db, wp_ids, ...): 对每个待写底稿调用 VersionTrailService.create_snapshot
    创建 pre-import 快照，记录 snapshot_id。
  - rollback(db, snapshots, ...): 将底稿恢复到各自的 snapshot_id 状态。
  - rollback_single(db, snapshot, ...): 回滚单个底稿。

原子性策略：
  - per-sheet（默认）：失败 sheet 仅回滚自身，其余保留。
  - all-or-nothing：任一 sheet 失败 → 全部回滚。

核心铁律：
  - service 只 flush 不 commit（调用者控制事务）
  - 复用 VersionTrailService，不新建快照表
  - 降级快照（>2MB）不可回滚时记 warning 继续

Requirements: 2.4, 6.2
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.version_trail_service import VersionTrailService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class AtomicityMode(str, Enum):
    """原子性策略。"""

    PER_SHEET = "per-sheet"
    ALL_OR_NOTHING = "all-or-nothing"


@dataclass
class SnapshotRecord:
    """单个底稿的快照记录。"""

    wp_id: UUID
    snapshot_id: UUID


# ---------------------------------------------------------------------------
# SnapshotGuard
# ---------------------------------------------------------------------------


class SnapshotGuard:
    """批量导入快照守卫 — 复用 VersionTrailService。"""

    @staticmethod
    async def snapshot(
        db: AsyncSession,
        wp_ids: Sequence[UUID],
        *,
        project_id: UUID,
        user_id: UUID,
        description: str | None = None,
    ) -> list[SnapshotRecord]:
        """为每个 wp_id 创建 pre-import 快照。

        - 调用 VersionTrailService.create_snapshot（snapshot_type='auto_import'）
        - fire-and-forget 语义：单个底稿快照失败仅 log warning，不阻断整包
        - 返回成功创建的 SnapshotRecord 列表（失败的不包含）

        Args:
            db: 数据库会话（service 只 flush 不 commit）
            wp_ids: 待写入的底稿 ID 列表
            project_id: 项目 ID
            user_id: 操作者用户 ID
            description: 快照描述（默认 "批量导入前自动快照"）

        Returns:
            成功创建的快照记录列表
        """
        desc = description or "批量导入前自动快照"
        records: list[SnapshotRecord] = []

        for wp_id in wp_ids:
            try:
                meta = await VersionTrailService.create_snapshot(
                    db=db,
                    project_id=project_id,
                    workpaper_id=wp_id,
                    user_id=user_id,
                    snapshot_type="auto_import",
                    description=desc,
                )
                records.append(SnapshotRecord(wp_id=wp_id, snapshot_id=meta.id))
            except Exception:
                logger.warning(
                    "SnapshotGuard: 快照创建失败 wp_id=%s, 继续处理其余",
                    wp_id,
                    exc_info=True,
                )

        return records

    @staticmethod
    async def rollback(
        db: AsyncSession,
        snapshots: Sequence[SnapshotRecord],
        *,
        project_id: UUID,
        user_id: UUID,
    ) -> None:
        """将所有底稿恢复到各自的 snapshot_id 状态。

        逐个调用 VersionTrailService.rollback_to_snapshot；
        单个回滚失败仅 log error，不阻断其余回滚。

        Args:
            db: 数据库会话
            snapshots: 快照记录列表
            project_id: 项目 ID
            user_id: 操作者用户 ID
        """
        for record in snapshots:
            await SnapshotGuard.rollback_single(
                db, record, project_id=project_id, user_id=user_id
            )

    @staticmethod
    async def rollback_single(
        db: AsyncSession,
        snapshot: SnapshotRecord,
        *,
        project_id: UUID,
        user_id: UUID,
    ) -> None:
        """回滚单个底稿到指定快照。

        Args:
            db: 数据库会话
            snapshot: 快照记录
            project_id: 项目 ID
            user_id: 操作者用户 ID
        """
        try:
            await VersionTrailService.rollback_to_snapshot(
                db=db,
                project_id=project_id,
                workpaper_id=snapshot.wp_id,
                snapshot_id=snapshot.snapshot_id,
                user_id=user_id,
            )
        except Exception:
            logger.error(
                "SnapshotGuard: 回滚失败 wp_id=%s, snapshot_id=%s",
                snapshot.wp_id,
                snapshot.snapshot_id,
                exc_info=True,
            )
