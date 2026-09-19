"""统一底稿保存后处理编排器 —— **零版本写**的可重放副作用 handler

所有 4 条写入路径（wp_html_save / wp_editor_router / onlyoffice_callback / custom_query.snapshot_writer）
在完成数据写入后统一调用 `orchestrator.after_save(...)` 执行后处理：
  1. prefill_stale = True
  2. updated_at = now
  3. 审计日志（同事务，失败即让保存失败）
  4. 把 WORKPAPER_SAVED 写进耐久 outbox（同事务，**不发布**）
  5. flush（不 commit，由 router 统一 commit）

提交后由调用方调 `DurableEventOutboxService.publish_pending(db)` 真正发事件。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Task 16 + Task 18
Requirements 2.1 / 2.12 / 13.1 / 13.3 / 13.4；Property 4 / 52 / 54。

═══ Task 16：两处 best-effort 降级被拆掉 ═══

* **审计日志**原来 `except Exception → logger.warning`。它和内容写在同一个事务里，
  本身就是耐久的；真失败时正确做法是让整笔保存失败，而不是留下一条没有审计痕迹的
  内容变更（Requirement 13.4「不得 best-effort warning 后永久丢失」）。
* **事件发布**原来在事务内直接 `event_bus.publish(...)`，且失败降级成 warning。两个
  问题：事务回滚后事件已经发出去（幽灵事件，Property 52）；Redis 抖一下事件就永久
  丢失，下游 cross_ref / stale / SSE 静默不触发（Property 54）。现在改为同事务写一条
  `import_event_outbox` pending 行，提交后再发布，失败自动落 failed 由
  `outbox_replay_worker` 重放、耗尽后进 DLQ。

═══ Task 18：`file_version += 1` 与 `expected_version` 一并删除 ═══

Requirement 2.12 的原文是「`after_save()` 等副作用 SHALL 由提交后可重放 handler 执行；
handler 重试不得再次递增 content revision」。Task 16 只做到了「被重放的那一半不碰
version」，**提交前那一半仍然递增 `file_version`**，因为当时还没有替代所有者。

Task 18 给了替代所有者，于是这里删掉两样东西：

1. `wp.file_version += 1` —— 一个**共享副作用 handler** 不该是任何版本的所有者。业务
   内容版本域是 `working_paper.content_revision`，唯一推进者是
   `ContentMutationService`（Task 15/18）的单次业务事务；真正需要「文件生命周期版本」
   的三条路径（univer 保存 / OO callback / custom_query 回写）已把
   `file_version += 1` 收回**各自写文件处** —— 那里才是文件生命周期的所有者
   （design §`working_paper` 增量列：「`file_version` 保留给既有文件生命周期，不再被新
   同步协议当内容乐观锁」）。
2. `expected_version` / `OptimisticLockError` —— 它比较的是**内存里的**
   `wp.file_version`。同一个 Python 对象自己跟自己比，跨进程并发一个也拦不住；两次
   调用之间没有任何数据库谓词，所以它从来不是乐观锁，只是个看起来像锁的断言。真正的
   乐观锁是 `WorkpaperSyncRepository.bump_content_revision()` 的
   `UPDATE ... WHERE content_revision = :expected`（单条 SQL 的 CAS，命中 0 行即冲突），
   由 `ContentMutationService` 在业务事务内执行。

`content_revision` 参数是**只读**的：调用方把本次业务提交预定的 revision 传进来，
handler 只把它写进审计日志与耐久 payload，供下游按正确版本刷新。handler 自己**不**
读写 `working_paper.content_revision`，因此重复投递不可能递增 revision。

Validates: Requirements 2.1, 2.12, 13.1, 13.3, 13.4
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: 被重放的副作用 handler 名与版本，写进 `import_event_consumptions.handler_name`
#: 供 Requirement 13.3 的 `(event_id, handler@vN)` 幂等闸门使用。语义变化时 +1。
#:
#: 🔴 Task 18 把「递增 file_version」从本 handler 移出去了 —— 那是**语义变化**，所以
#: 版本从 1 升到 2：v1 时代投递过的事件按 v1 语义（含版本递增）已消费完毕，不应被 v2
#: 的幂等键复用（Requirement 13.3 的 handler version 半边就是为此存在）。
SIDE_EFFECT_HANDLER_NAME = "workpaper_save_orchestrator.after_save"
SIDE_EFFECT_HANDLER_VERSION = 2

#: 本 handler 允许写入的 `working_paper` 字段。**版本字段一个都不在里面**
#: （Requirement 2.1：`prefill_stale` / `updated_at` 明确不是业务内容也不是版本）。
#: 守卫按这个集合逐字段核对实际写入，见
#: `tests/test_workpaper_save_orchestrator.py::test_after_save_writes_no_version_field`。
SIDE_EFFECT_WRITABLE_FIELDS: frozenset[str] = frozenset({"prefill_stale", "updated_at"})


class WorkpaperSaveOrchestrator:
    """统一后处理编排器 — 只 flush 不 commit，且不持有任何版本域。"""

    async def after_save(
        self,
        db: AsyncSession,
        wp: Any,
        user: Any,
        *,
        trigger: str,
        extra: dict[str, Any] | None = None,
        content_revision: int | None = None,
    ) -> int | None:
        """执行保存后统一后处理，返回本次记录的 business content revision。

        Args:
            db: 数据库会话（调用方负责 commit，并在 commit 后调 publish_pending）
            wp: WorkingPaper ORM 实例（需有 id, prefill_stale, updated_at, project_id）
            user: 当前用户（需有 id 属性）
            trigger: 触发来源标识 ("html_save" | "univer_save" | "onlyoffice_callback" | "custom_query_writeback")
            extra: 附加信息（content_hash, sheets, cells 等）
            content_revision: 本次业务提交预定推进到的 `content_revision`。**只读** ——
                handler 只把它写进审计日志与耐久 payload，绝不读写数据库里的版本列。
                尚未迁入 `ContentMutationService` 的路径传 None（Task 19/20 补齐）。

        Returns:
            传入的 `content_revision`（原样回传，便于调用方断言两边一致）

        Raises:
            DurableOutboxError: wp.project_id 缺失，无法形成可发布的耐久事件
        """
        extra = extra or {}

        # Step 1: prefill_stale 标记（Requirement 2.1：不是业务内容，也不是版本）
        wp.prefill_stale = True

        # Step 2: updated_at（通用审计时间，不参与 merge、不当同步版本）
        now = datetime.now(timezone.utc)
        wp.updated_at = now

        # Step 3: 审计日志（同事务；不再降级成 warning）
        from app.models.core import Log

        log = Log(
            user_id=getattr(user, "id", None),
            action_type=f"workpaper_{trigger}",
            object_type="working_paper",
            object_id=wp.id,
            new_value={
                # 🔴 记的是**业务内容版本**，不是文件版本。旧实现记 old/new file_version，
                # 于是「审计日志里的版本」与「下游按哪个版本刷新」是两个不同的计数器。
                "content_revision": content_revision,
                "trigger": trigger,
                **{k: v for k, v in extra.items() if _is_json_serializable(v)},
            },
        )
        db.add(log)

        # Step 4: 耐久 outbox 入队（同事务，不发布 —— Requirement 13.1 / Property 52）
        from app.models.audit_platform_schemas import EventType
        from app.services.workpaper_sync.outbox import DurableEventOutboxService

        await DurableEventOutboxService.enqueue(
            db,
            event_type=EventType.WORKPAPER_SAVED,
            project_id=wp.project_id,
            year=extra.get("year"),
            payload={
                "wp_id": str(wp.id),
                "content_revision": content_revision,
                "trigger": trigger,
                **{
                    k: str(v) if isinstance(v, UUID) else v
                    for k, v in extra.items()
                    if k != "year" and _is_json_serializable(v)
                },
            },
        )

        # Step 5: flush（不 commit）
        await db.flush()

        logger.info(
            "WorkpaperSaveOrchestrator.after_save: wp=%s trigger=%s content_revision=%s",
            wp.id, trigger, content_revision,
        )
        return content_revision


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
