"""统一底稿保存后处理编排器

所有 4 条写入路径（wp_html_save / wp_editor_router / onlyoffice_callback / custom_query.snapshot_writer）
在完成数据写入后统一调用 `orchestrator.after_save(...)` 执行后处理：
  1. 乐观锁校验（expected_version != wp.file_version → raise OptimisticLockError）
  2. file_version += 1
  3. prefill_stale = True
  4. updated_at = now
  5. 审计日志
  6. event_bus.publish(WORKPAPER_SAVED)
  7. flush（不 commit，由 router 统一 commit）

Validates: Requirements 1.1, 1.2, 2.1
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class OptimisticLockError(Exception):
    """乐观锁冲突：expected_version != current file_version"""

    def __init__(self, expected: int, actual: int):
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Optimistic lock conflict: expected version {expected}, "
            f"but current is {actual}"
        )


class WorkpaperSaveOrchestrator:
    """统一后处理编排器 — 只 flush 不 commit。"""

    async def after_save(
        self,
        db: AsyncSession,
        wp: Any,
        user: Any,
        *,
        trigger: str,
        extra: dict[str, Any] | None = None,
        expected_version: int | None = None,
    ) -> int:
        """执行保存后统一后处理，返回新 file_version。

        Args:
            db: 数据库会话（调用方负责 commit）
            wp: WorkingPaper ORM 实例（需有 id, file_version, prefill_stale, updated_at, project_id）
            user: 当前用户（需有 id 属性）
            trigger: 触发来源标识 ("html_save" | "univer_save" | "onlyoffice_callback" | "custom_query_writeback")
            extra: 附加信息（content_hash, sheets, cells 等）
            expected_version: 乐观锁校验版本号，None 表示不校验

        Returns:
            新的 file_version

        Raises:
            OptimisticLockError: expected_version 与当前 file_version 不一致
        """
        extra = extra or {}

        # Step 1: 乐观锁校验
        if expected_version is not None and expected_version != wp.file_version:
            raise OptimisticLockError(
                expected=expected_version, actual=wp.file_version
            )

        # Step 2: file_version 递增
        old_version = wp.file_version
        wp.file_version += 1

        # Step 3: prefill_stale 标记
        wp.prefill_stale = True

        # Step 4: updated_at
        now = datetime.now(timezone.utc)
        wp.updated_at = now

        # Step 5: 审计日志
        try:
            from app.models.core import Log

            log = Log(
                user_id=getattr(user, "id", None),
                action_type=f"workpaper_{trigger}",
                object_type="working_paper",
                object_id=wp.id,
                new_value={
                    "old_version": old_version,
                    "new_version": wp.file_version,
                    "trigger": trigger,
                    **{k: v for k, v in extra.items() if _is_json_serializable(v)},
                },
            )
            db.add(log)
        except Exception as exc:
            logger.warning(
                "after_save audit log failed wp=%s trigger=%s: %s",
                wp.id, trigger, exc,
            )

        # Step 6: event_bus.publish(WORKPAPER_SAVED)
        try:
            from app.models.audit_platform_schemas import EventPayload, EventType
            from app.services.event_bus import event_bus

            payload = EventPayload(
                event_type=EventType.WORKPAPER_SAVED,
                project_id=wp.project_id,
                year=extra.get("year"),
                extra={
                    "wp_id": str(wp.id),
                    "file_version": wp.file_version,
                    "trigger": trigger,
                    **{k: str(v) if isinstance(v, UUID) else v
                       for k, v in extra.items()
                       if k != "year" and _is_json_serializable(v)},
                },
            )
            await event_bus.publish(payload)
        except Exception as exc:
            logger.warning(
                "after_save event publish failed wp=%s trigger=%s: %s",
                wp.id, trigger, exc,
            )

        # Step 7: flush（不 commit）
        await db.flush()

        logger.info(
            "WorkpaperSaveOrchestrator.after_save: wp=%s trigger=%s v%d→v%d",
            wp.id, trigger, old_version, wp.file_version,
        )
        return wp.file_version


def _is_json_serializable(value: Any) -> bool:
    """简单判断值是否可 JSON 序列化（用于 extra 字段过滤）"""
    if value is None:
        return True
    if isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, (list, dict)):
        return True
    if isinstance(value, UUID):
        return True
    return False


# 模块级单例
orchestrator = WorkpaperSaveOrchestrator()
