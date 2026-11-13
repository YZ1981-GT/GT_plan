"""底稿末级复核/归档后的内容冻结单一判据。"""

from __future__ import annotations

import inspect
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper, WpFileStatus


class WorkpaperContentFrozenError(HTTPException):
    """末级复核通过或归档后的底稿拒绝业务内容写入。"""

    def __init__(self, message: str) -> None:
        super().__init__(status_code=423, detail=message)


# 终态内容冻结状态 → 中文标签。本模块是基础层，持有平台「冻结底稿」状态的**单一定义**：
# 复核通过 / 已归档 + 两个逐级中间态旧值（legacy WpFileStatus）。上层既有冻结判据
# （formula_push.engine.FROZEN_WP_STATUSES、bulk_tab.workflow_gate、workhour_approval、
# wp_prerequisite_status、wp_mapping）枚举的正是同一组 4 值；收窄成 {review_passed, archived}
# 会让被 formula_push 视为冻结的旧值底稿仍可经内容写端点改写。跨模块一致性由
# test_workpaper_terminal_freeze_guard 对 FROZEN_WP_STATUSES 键集的断言守卫。
_FROZEN_STATUS_LABELS: dict[WpFileStatus, str] = {
    WpFileStatus.review_passed: "复核通过",
    WpFileStatus.archived: "已归档",
    WpFileStatus.review_level1_passed: "一级复核通过",
    WpFileStatus.review_level2_passed: "二级复核通过",
}
TERMINAL_CONTENT_STATUSES = frozenset(_FROZEN_STATUS_LABELS)


def frozen_message(status: WpFileStatus) -> str:
    label = _FROZEN_STATUS_LABELS.get(status, "复核通过")
    return f"底稿{label}，内容已冻结。如需修改，请先按流程创建新修订。"


def _dialect_name(db: AsyncSession) -> str:
    """尽力读取会话方言；替身会话无 bind 时返回空字符串。"""
    try:
        bind = db.get_bind()
        if inspect.isawaitable(bind):
            close = getattr(bind, "close", None)
            if callable(close):
                close()
            return ""
        return str(getattr(getattr(bind, "dialect", None), "name", ""))
    except Exception:
        return ""


async def _advisory_lock(db: AsyncSession, key: str) -> None:
    """PG 下与内容 revision 共用 advisory 命名空间；测试/SQLite 不造假锁。"""
    if _dialect_name(db) != "postgresql":
        return
    from app.services.workpaper_sync.repository import (
        WORKPAPER_SYNC_ADVISORY_NAMESPACE,
    )

    await db.execute(
        sa.text("SELECT pg_advisory_xact_lock(:ns, hashtext(:key))"),
        {"ns": WORKPAPER_SYNC_ADVISORY_NAMESPACE, "key": key},
    )


async def acquire_project_bulk_content_lock(db: AsyncSession, project_id: UUID) -> None:
    """批量写先串行化同项目，随后各底稿仍按 advisory→row 的统一顺序取锁。"""
    await _advisory_lock(db, f"workpaper_bulk:{project_id}")


async def load_workpaper_status(
    db: AsyncSession,
    wp_id: UUID,
    *,
    for_update: bool = False,
) -> WpFileStatus | None:
    """读取底稿状态；内容写入口用 ``for_update`` 与状态流转共用行锁。

    status / is_deleted 都经 ``to_jsonb(working_paper)->>…`` 读取，与 ``repository.lock_workpaper``
    同一安全读法：部分 V151 隔离测试桩刻意只建 id/project_id/revision 等列，缺键 ``->>`` 返回
    NULL（按非终态、未删除处理），不会因 ``SELECT status`` 触发 UndefinedColumn 打红真库外的隔离世界。
    生产 schema/ORM 的 status 列存在性另有迁移完整性守卫。
    """
    if _dialect_name(db) == "sqlite":
        # SQLite 没有 to_jsonb；普通单元测试的 ORM schema 含 status/is_deleted，保留 ORM 路径。
        stmt = sa.select(WorkingPaper.status).where(
            WorkingPaper.id == wp_id,
            WorkingPaper.is_deleted == sa.false(),
        )
        if for_update:
            stmt = stmt.with_for_update()
        return (await db.execute(stmt)).scalar_one_or_none()

    # PostgreSQL（及无 bind 的 mock）使用安全的整行 JSON 读取。V151 隔离 PG schema 可能少 status
    # 或 is_deleted 列，直接 SELECT 这些列会触发 UndefinedColumn；to_jsonb 缺键返回 NULL。
    sql = (
        "SELECT to_jsonb(working_paper)->>'status' AS status, "
        "to_jsonb(working_paper)->>'is_deleted' AS is_deleted "
        "FROM working_paper WHERE id = :wp"
    )
    if for_update:
        await _advisory_lock(db, f"workpaper_sync:{wp_id}")
        sql += " FOR UPDATE"
    row = (await db.execute(sa.text(sql), {"wp": str(wp_id)})).first()
    if row is None:
        return None
    if str(row[1] or "").lower() in ("true", "t"):
        return None  # 已删除：内容冻结判据放行（与原 is_deleted 过滤同义，删除由他处处理）
    raw = row[0]
    if not raw:
        return None
    try:
        return WpFileStatus(str(raw))
    except ValueError:
        return None


async def assert_workpaper_content_writable(
    db: AsyncSession,
    wp_id: UUID,
    *,
    for_update: bool = True,
) -> WpFileStatus | None:
    """终态底稿拒绝业务内容写入，返回非终态状态供调用方复用。"""
    status = await load_workpaper_status(db, wp_id, for_update=for_update)
    if status in TERMINAL_CONTENT_STATUSES:
        raise WorkpaperContentFrozenError(frozen_message(status))
    return status


def raise_if_status_text_frozen(status_text: str) -> None:
    """按状态文本（``to_jsonb(working_paper)->>'status'`` 的结果）判终态并抛 423。

    供 ``repository.lock_workpaper`` 在同一行锁内复用：它已在锁定行里读出 status 文本，
    无需二次查询。缺列桩 / 空文本 → 非终态放行。
    """
    if status_text in {s.value for s in TERMINAL_CONTENT_STATUSES}:
        raise WorkpaperContentFrozenError(frozen_message(WpFileStatus(status_text)))


__all__ = [
    "TERMINAL_CONTENT_STATUSES",
    "WorkpaperContentFrozenError",
    "acquire_project_bulk_content_lock",
    "assert_workpaper_content_writable",
    "frozen_message",
    "load_workpaper_status",
    "raise_if_status_text_frozen",
]
