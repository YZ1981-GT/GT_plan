"""合并附注结构锁服务——激活/释放/检查。

spec: consol-note-mapping-reuse-and-reference-push Phase 6 Task 21~23

Service 只 flush 不 commit（router 层 commit）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_note_mapping_template_models import (
    ConsolNoteStructureLock,
    ConsolNoteStructureLockEntity,
)

logger = logging.getLogger(__name__)


class StructureLockError(Exception):
    """结构锁操作错误。"""

    def __init__(self, status: int, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 激活锁
# ═══════════════════════════════════════════════════════════════════════════════


async def activate_lock(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
    section_id: str,
    locked_version_id: UUID,
    locked_by: UUID,
) -> dict[str, Any]:
    """激活结构锁。从合并树 data_leaves 展开写入关联表。

    校验：
    1. 版本存在
    2. 同章节无活跃锁（否则 409）
    """
    from app.models.consol_note_mapping_models import ConsolNoteDetailTemplateVersion

    # 校验版本存在
    version = (await db.execute(
        sa.select(ConsolNoteDetailTemplateVersion).where(
            ConsolNoteDetailTemplateVersion.id == locked_version_id,
        )
    )).scalar_one_or_none()
    if version is None:
        raise StructureLockError(404, "VERSION_NOT_FOUND", "模板版本不存在")

    # 校验无活跃锁
    existing = (await db.execute(
        sa.select(ConsolNoteStructureLock).where(
            ConsolNoteStructureLock.consol_project_id == consol_project_id,
            ConsolNoteStructureLock.section_id == section_id,
            ConsolNoteStructureLock.is_active == sa.true(),
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise StructureLockError(
            409, "ALREADY_LOCKED",
            f"章节 {section_id} 已被锁定",
            {"lock_id": str(existing.id)},
        )

    now = datetime.now(timezone.utc)
    lock = ConsolNoteStructureLock(
        consol_project_id=consol_project_id,
        section_id=section_id,
        locked_version_id=locked_version_id,
        lock_scope="rows_only",
        locked_by=locked_by,
        locked_at=now,
    )
    db.add(lock)
    await db.flush()

    # 展开合并树叶子企业写入关联表
    entity_count = 0
    try:
        from app.services.consol_tree_service import build_tree
        from app.services.consol_calc_basis import data_leaves

        tree = await build_tree(db, consol_project_id)
        if tree is not None:
            for leaf in data_leaves(tree):
                if leaf.project_id is None:
                    continue
                db.add(ConsolNoteStructureLockEntity(
                    lock_id=lock.id,
                    entity_project_id=leaf.project_id,
                    entity_node_key=leaf.node_key,
                ))
                entity_count += 1
    except Exception:
        logger.warning("展开合并树叶子企业失败（锁已创建但关联为空）", exc_info=True)

    await db.flush()
    return {
        "action": "locked",
        "lock_id": str(lock.id),
        "consol_project_id": str(consol_project_id),
        "section_id": section_id,
        "entity_count": entity_count,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 检查锁
# ═══════════════════════════════════════════════════════════════════════════════


async def check_structure_lock(
    db: AsyncSession,
    *,
    entity_project_id: UUID,
    section_id: str,
) -> dict[str, Any] | None:
    """检查子企业某章节是否被结构锁。

    直接查 consol_note_structure_lock_entity JOIN consol_note_structure_lock，
    不需要 build_tree。

    Returns:
        None = 未锁定
        dict = 锁定信息
    """
    result = (await db.execute(
        sa.select(
            ConsolNoteStructureLock.id,
            ConsolNoteStructureLock.consol_project_id,
            ConsolNoteStructureLock.section_id,
            ConsolNoteStructureLock.lock_scope,
            ConsolNoteStructureLock.locked_by,
            ConsolNoteStructureLock.locked_at,
        )
        .join(
            ConsolNoteStructureLockEntity,
            ConsolNoteStructureLockEntity.lock_id == ConsolNoteStructureLock.id,
        )
        .where(
            ConsolNoteStructureLockEntity.entity_project_id == entity_project_id,
            ConsolNoteStructureLock.section_id == section_id,
            ConsolNoteStructureLock.is_active == sa.true(),
        )
        .limit(1)
    )).one_or_none()

    if result is None:
        return None

    return {
        "locked": True,
        "lock_id": str(result.id),
        "consol_project_id": str(result.consol_project_id),
        "section_id": result.section_id,
        "lock_scope": result.lock_scope,
        "locked_by": str(result.locked_by) if result.locked_by else None,
        "locked_at": result.locked_at.isoformat() if result.locked_at else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 释放锁
# ═══════════════════════════════════════════════════════════════════════════════


async def release_lock(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
    section_id: str,
    released_by: UUID,
) -> dict[str, Any]:
    """解除结构锁。需 review 级权限（路由层校验）。"""
    lock = (await db.execute(
        sa.select(ConsolNoteStructureLock).where(
            ConsolNoteStructureLock.consol_project_id == consol_project_id,
            ConsolNoteStructureLock.section_id == section_id,
            ConsolNoteStructureLock.is_active == sa.true(),
        )
    )).scalar_one_or_none()

    if lock is None:
        raise StructureLockError(404, "LOCK_NOT_FOUND", "该章节未被锁定")

    lock.is_active = False
    # 关联的 entity 行由 FK CASCADE DELETE 处理（PG）；
    # SQLite 下手动删（兼容测试环境）
    await db.execute(
        sa.delete(ConsolNoteStructureLockEntity).where(
            ConsolNoteStructureLockEntity.lock_id == lock.id,
        )
    )
    await db.flush()
    return {
        "action": "released",
        "lock_id": str(lock.id),
        "consol_project_id": str(consol_project_id),
        "section_id": section_id,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 列出锁状态
# ═══════════════════════════════════════════════════════════════════════════════


async def get_locks(
    db: AsyncSession,
    *,
    consol_project_id: UUID,
) -> list[dict[str, Any]]:
    """查询某合并项目的所有活跃结构锁。"""
    locks = (await db.execute(
        sa.select(ConsolNoteStructureLock).where(
            ConsolNoteStructureLock.consol_project_id == consol_project_id,
            ConsolNoteStructureLock.is_active == sa.true(),
        ).order_by(ConsolNoteStructureLock.section_id)
    )).scalars().all()

    result: list[dict[str, Any]] = []
    for lock in locks:
        entities = (await db.execute(
            sa.select(ConsolNoteStructureLockEntity).where(
                ConsolNoteStructureLockEntity.lock_id == lock.id,
            )
        )).scalars().all()
        result.append({
            "lock_id": str(lock.id),
            "section_id": lock.section_id,
            "lock_scope": lock.lock_scope,
            "locked_by": str(lock.locked_by) if lock.locked_by else None,
            "locked_at": lock.locked_at.isoformat() if lock.locked_at else None,
            "entity_count": len(entities),
            "entities": [
                {"entity_project_id": str(e.entity_project_id), "entity_node_key": e.entity_node_key}
                for e in entities
            ],
        })
    return result
