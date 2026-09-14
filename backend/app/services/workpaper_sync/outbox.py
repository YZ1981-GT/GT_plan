# -*- coding: utf-8 -*-
"""底稿同步域的耐久事件 outbox facade。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Task 16
Requirements 2.12 / 13.1 / 13.2 / 13.3 / 13.4；Property 52 / 53 / 54。

design.md §outbox 的硬约束是"**不新建第二套事件表**"，所以这里没有任何新表：
``import_event_outbox`` / ``event_outbox_dlq`` / ``import_event_consumptions``
三张现成表、``ImportEventOutboxService`` 的 publish/replay/DLQ 升级逻辑、以及
``outbox_replay_worker`` 的补偿循环全部原样复用，旧 service 继续作为导入域的兼容
门面存在。本 facade 只补现有 service 缺的三件事：

1. **提交边界安全的 API**（Requirement 13.1 / Property 52）
   ``enqueue()`` 只 ``flush`` 不 ``commit``，并且**不返回**绑定在 pre-commit session
   上的 ORM 行，而返回不可变的 :class:`PendingPublication`。发布必须由调用方在自己
   ``commit()`` 之后调 ``publish_pending()``。旧路径在事务内直接
   ``event_bus.publish(...)``：事务一旦回滚，事件已经发出去了，下游按不存在的内容
   版本去刷新 —— 这正是 Property 52 要打掉的幽灵事件。

2. **handler 幂等闸门**（Requirement 13.3）
   ``claim_consumption()`` 以 ``(event_id, handler_name@vN)`` 命中
   ``import_event_consumptions`` 的唯一索引，第二次投递返回 ``False``。重放用的是同
   一个 outbox 行 id，所以 ``event_id`` 跨重放稳定。

   这道闸门不是"给后续任务备用的 API"，而是**接在派发口上**的：
   ``ImportEventOutboxService._deliver()`` 对 :data:`GATED_FANOUT_EVENT_TYPES` 里的事件
   先 :meth:`begin_fanout` 再 ``publish_immediate``，抢不到就整条跳过。这样
   "publish → 行被标 failed → worker 重放"这类重复投递不会把订阅
   ``WORKPAPER_SAVED`` 的一整片 handler（一致性比对 / prefill stale / stale_engine /
   ACNR 失效 / 循环联动 / SSE）再跑一遍。派发失败时 :meth:`abort_fanout` 归还派发权，
   所以"失败可重放"与"成功不重复"两件事互不干扰。

3. **失败即耐久**（Requirement 13.4 / Property 54）
   发布失败只把行标 ``failed`` 并累加 ``attempt_count``，由既有 worker 继续重放、
   耗尽 ``max_attempts`` 后进 DLQ。调用方因此**不需要也不应该**再把发布异常降级成
   ``logger.warning`` —— 耐久行的存在本身就是"没有静默丢失"的判据。

关于 revision：本模块任何代码路径都不读写 ``file_version`` /
``content_revision`` / ``parsed_data._version``。Requirement 2.12 要求"handler 重试
不得再次递增 content revision"，而重放走的就是这里的 publish 路径，因此
**重放天然不可能推进版本**。版本推进留在 ``after_save`` 的同事务段落里，由 Task 18
随 ``ContentMutationService`` 一并迁走。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import EventType
from app.models.dataset_models import ImportEventConsumption, ImportEventOutbox, OutboxStatus
from app.services.import_event_outbox_service import ImportEventOutboxService

logger = logging.getLogger(__name__)


#: publish 时注入 payload 的耐久行标识键。Requirement 13.3 的 handler 幂等就以它为
#: ``event_id``；由 :meth:`ImportEventOutboxService.publish_one` 写入，此处只声明常量
#: 供 consumer 与守卫共用，避免两侧各写一份字面量。
EVENT_ID_PAYLOAD_KEY = "__event_id"

#: 挂在 ``Session.info`` 上的待发布清单键。用 session 作用域而不是模块级单例：
#: 一个进程内并发多个请求各有自己的 session，模块级列表会互相串。
PENDING_SESSION_KEY = "workpaper_sync.durable_outbox.pending"

#: ``handler_name@vN``：handler 语义变化时把版本号 +1，历史 consumption 行不会挡住
#: 新语义重跑一次（Requirement 13.3 的 "handler version" 半边）。
HANDLER_VERSION_SEPARATOR = "@v"

#: 整条 fan-out（in-process handler 链 + SSE）作为**一个** consumer 登记幂等。
#:
#: Requirement 13.3 要的是"重复投递不得重复刷新、重复 after-save、重复生成 artifact"。
#: 底稿保存的副作用不是一个函数，而是订阅 ``WORKPAPER_SAVED`` 的一整片 handler
#: （一致性比对 / prefill stale / stale_engine / ACNR 失效 / 循环联动 / SSE …）。把闸门
#: 放在**派发口**而不是逐个 handler 里，一处就把整片副作用变成 at-most-once，且不需要
#: 改动任何下游 handler（它们分属别的 spec）。
FANOUT_HANDLER_NAME = "workpaper_sync.durable_outbox.fanout"
FANOUT_HANDLER_VERSION = 1

#: 只有底稿同步域的两个耐久事件类型走 fan-out 闸门。
#:
#: 刻意**不**覆盖导入域（``LEDGER_*`` / ``DATA_IMPORTED``）：那边 outbox 的重放语义由
#: ledger-import spec 拥有，其 handler 各自已有 ``import_event_consumptions`` 记账，
#: 在派发口再加一道会改掉它们的既有行为。Task 16 只对自己拥有的两个事件类型负责。
GATED_FANOUT_EVENT_TYPES: frozenset[EventType] = frozenset(
    {EventType.WORKPAPER_SAVED, EventType.WORKPAPER_CONTENT_UPDATED}
)


class DurableOutboxError(RuntimeError):
    """入队参数不足以形成一条可发布的耐久事件时抛出（fail closed）。"""


@dataclass(frozen=True)
class PendingPublication:
    """一条已入队、尚未发布的耐久事件句柄。

    刻意不持有 ORM 行：ORM 行绑定在入队时的 session/事务上，而 Requirement 13.1 要求
    发布发生在那个事务 **commit 之后**。只带 id 与路由字段，发布时按 id 重新读行。
    """

    outbox_id: UUID
    event_type: EventType
    project_id: UUID
    year: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "outbox_id": str(self.outbox_id),
            "event_type": self.event_type.value,
            "project_id": str(self.project_id),
            "year": self.year,
        }


@dataclass
class PublishReport:
    """一次 post-commit 发布的结果。

    ``rolled_back`` 是 Property 52 的直接判据：调用方事务回滚后耐久行根本不存在，
    因此 publish 阶段既发不出事件、也不会把不存在的行当成失败重试。
    """

    attempted: int = 0
    published: int = 0
    failed: int = 0
    already_published: int = 0
    rolled_back: int = 0
    last_error: str | None = None
    published_event_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "published": self.published,
            "failed": self.failed,
            "already_published": self.already_published,
            "rolled_back": self.rolled_back,
            "last_error": self.last_error,
            "published_event_ids": list(self.published_event_ids),
        }


def _pending_bucket(db: AsyncSession, *, create: bool) -> list[PendingPublication] | None:
    """返回挂在 session 上的待发布清单，拿不到真实 ``Session.info`` 时返回 ``None``。

    ``AsyncSession.info`` 代理到底层 ``Session.info``（一个普通 dict）。这里显式检查
    类型：单元测试里的 ``AsyncMock`` 会让 ``db.info`` 变成另一个 mock，``setdefault``
    照样"成功"却什么都没记住 —— 那是最典型的 fail-open。返回 ``None`` 让调用方能把
    这种情况记成 ERROR，而不是假装记住了。
    """
    info = getattr(db, "info", None)
    if not isinstance(info, dict):
        return None
    bucket = info.get(PENDING_SESSION_KEY)
    if not isinstance(bucket, list):
        if not create:
            return None
        bucket = []
        info[PENDING_SESSION_KEY] = bucket
    return bucket


class DurableEventOutboxService:
    """通用耐久事件 outbox facade（Task 16）。

    与 :class:`ImportEventOutboxService` 的分工：后者是导入域的既有门面，仍然提供
    ``replay_pending`` / ``_move_to_dlq`` / ``summary`` / ``dlq_depth``；本类不复制这
    些逻辑，而是委托它们，只额外承担提交边界、待发布清单与 consumption 幂等。
    """

    # ------------------------------------------------------------------
    # 入队：与业务写入同事务，只 flush 不 commit
    # ------------------------------------------------------------------
    @staticmethod
    async def enqueue(
        db: AsyncSession,
        *,
        event_type: EventType,
        project_id: UUID | None,
        year: int | None = None,
        payload: dict[str, Any] | None = None,
        remember: bool = True,
    ) -> PendingPublication:
        """在调用方事务内写一条 pending 耐久事件，返回待发布句柄。

        ``project_id`` 必填：``import_event_outbox.project_id`` 是 NOT NULL 外键，而
        ``EventPayload.project_id`` 也是必填 UUID。旧路径把缺 project_id 的构造异常吞
        成 warning，结果是"保存成功但下游联动永久静默"。这里 fail closed。
        """
        if project_id is None:
            raise DurableOutboxError(
                f"durable event {event_type.value} requires project_id; "
                "import_event_outbox.project_id is NOT NULL"
            )

        row = ImportEventOutbox(
            event_type=event_type.value,
            project_id=project_id,
            year=year,
            payload=dict(payload or {}),
            status=OutboxStatus.pending,
        )
        db.add(row)
        # flush 而不是 commit：耐久性由调用方那一次 commit 提供，Requirement 13.1。
        await db.flush()

        publication = PendingPublication(
            outbox_id=row.id,
            event_type=event_type,
            project_id=project_id,
            year=year,
        )
        if remember and not DurableEventOutboxService.remember(db, publication):
            logger.error(
                "durable outbox: session 不支持 info 字典，%s 的待发布句柄未登记，"
                "只能等 outbox_replay_worker 补偿 outbox_id=%s",
                event_type.value,
                row.id,
            )
        return publication

    # ------------------------------------------------------------------
    # 待发布清单（session 作用域）
    # ------------------------------------------------------------------
    @staticmethod
    def remember(db: AsyncSession, publication: PendingPublication) -> bool:
        bucket = _pending_bucket(db, create=True)
        if bucket is None:
            return False
        bucket.append(publication)
        return True

    @staticmethod
    def remembered(db: AsyncSession) -> tuple[PendingPublication, ...]:
        bucket = _pending_bucket(db, create=False)
        return tuple(bucket or ())

    @staticmethod
    def forget_all(db: AsyncSession) -> None:
        bucket = _pending_bucket(db, create=False)
        if bucket is not None:
            bucket.clear()

    # ------------------------------------------------------------------
    # 发布：必须在调用方 commit 之后
    # ------------------------------------------------------------------
    @staticmethod
    async def publish_pending(
        db: AsyncSession,
        publications: list[PendingPublication] | tuple[PendingPublication, ...] | None = None,
        *,
        commit: bool = True,
    ) -> PublishReport:
        """发布 ``publications``（默认取本 session 记住的全部），并持久化发布状态。

        必须在调用方 ``commit()`` 之后调用：

        * 调用方回滚了 → 耐久行不存在 → ``rolled_back`` 计数，**不发事件**（Property 52）；
        * 行还在但发布失败 → 行落 ``failed`` + ``attempt_count`` 并 commit，既有 worker
          继续重放，耗尽后进 DLQ（Property 54）。因此本方法**不向上抛**发布异常：
          "没有静默丢失"由耐久行保证，而不是由请求 500 保证。

        本方法幂等：处理过的句柄从 session 清单里摘掉，且已 ``published`` 的行只计
        ``already_published`` 不重发（Property 52 的"恰有一个事件"）。
        """
        targets = (
            list(publications)
            if publications is not None
            else list(DurableEventOutboxService.remembered(db))
        )
        report = PublishReport(attempted=len(targets))
        if not targets:
            return report

        touched = False
        for publication in targets:
            try:
                row = await ImportEventOutboxService.get(db, publication.outbox_id)
                if row is None:
                    # 入队事务回滚（或行已被清理）：没有可发布的耐久事实。
                    report.rolled_back += 1
                    continue
                if row.status == OutboxStatus.published:
                    report.already_published += 1
                    continue
                ok = await ImportEventOutboxService.publish_one(db, publication.outbox_id)
                touched = True
                if ok:
                    report.published += 1
                    report.published_event_ids.append(str(publication.outbox_id))
                else:
                    report.failed += 1
                    refreshed = await ImportEventOutboxService.get(db, publication.outbox_id)
                    report.last_error = getattr(refreshed, "last_error", None)
            except Exception as exc:  # pragma: no cover - 连库都不可用时的兜底
                # 连状态都写不下去：耐久行仍是 pending（调用方已提交），worker 会接手。
                report.failed += 1
                report.last_error = str(exc)[:1000]
                logger.error(
                    "durable outbox: publish 阶段异常 outbox_id=%s event=%s，"
                    "耐久行保持可重放：%s",
                    publication.outbox_id,
                    publication.event_type.value,
                    exc,
                    exc_info=True,
                )

        if commit and touched:
            try:
                await db.commit()
            except Exception as exc:  # pragma: no cover
                report.last_error = str(exc)[:1000]
                logger.error(
                    "durable outbox: 发布状态提交失败，事件已发出但状态可能仍是 "
                    "pending/failed，worker 重放会命中幂等闸门：%s",
                    exc,
                    exc_info=True,
                )

        DurableEventOutboxService.forget_all(db)
        if report.failed:
            logger.warning(
                "durable outbox: %s/%s 条事件发布失败并已落 failed 待重放 last_error=%s",
                report.failed,
                report.attempted,
                report.last_error,
            )
        return report

    # ------------------------------------------------------------------
    # consumer 幂等（Requirement 13.3）
    # ------------------------------------------------------------------
    @staticmethod
    def handler_key(handler_name: str, handler_version: int) -> str:
        return f"{handler_name}{HANDLER_VERSION_SEPARATOR}{int(handler_version)}"

    @staticmethod
    async def claim_consumption(
        db: AsyncSession,
        *,
        event_id: str | UUID,
        handler_name: str,
        handler_version: int = 1,
        project_id: UUID | None = None,
        year: int | None = None,
    ) -> bool:
        """抢占 ``(event_id, handler@vN)`` 消费权；已被抢占过返回 ``False``。

        用 savepoint 包住插入：唯一索引冲突抛的 ``IntegrityError`` 会污染整个事务，
        套 ``begin_nested()`` 后只回滚这一个 savepoint，调用方事务里其它写入不受影响。
        """
        key = DurableEventOutboxService.handler_key(handler_name, handler_version)
        row = ImportEventConsumption(
            event_id=str(event_id)[:64],
            handler_name=key[:200],
            project_id=project_id,
            year=year,
        )
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
        except IntegrityError:
            logger.debug(
                "durable outbox: 重复投递已被幂等闸门拦下 event_id=%s handler=%s",
                event_id,
                key,
            )
            return False
        return True

    @staticmethod
    async def release_consumption(
        db: AsyncSession,
        *,
        event_id: str | UUID,
        handler_name: str,
        handler_version: int = 1,
    ) -> bool:
        """撤销 ``(event_id, handler@vN)`` 的消费记录；删掉行返回 ``True``。

        存在的理由是 Property 54：抢到消费权之后**副作用本身失败**时，如果消费行留在
        库里，后续重放会命中闸门而跳过 —— 事件被永久静默丢失，正是 Requirement 13.4
        禁止的形态。所以失败路径必须把消费权还回去。

        同样套 ``begin_nested()``：调用方通常是在一个已经被异常污染过的分支里调它。
        """
        key = DurableEventOutboxService.handler_key(handler_name, handler_version)
        async with db.begin_nested():
            result = await db.execute(
                sa.delete(ImportEventConsumption).where(
                    ImportEventConsumption.event_id == str(event_id)[:64],
                    ImportEventConsumption.handler_name == key[:200],
                )
            )
        return bool(result.rowcount)

    # ------------------------------------------------------------------
    # fan-out 闸门（Requirement 13.3：重复投递不重复副作用）
    # ------------------------------------------------------------------
    @staticmethod
    def is_fanout_gated(event_type: EventType | str) -> bool:
        """该事件类型的 in-process 派发是否受 at-most-once 闸门管辖。"""
        if isinstance(event_type, EventType):
            return event_type in GATED_FANOUT_EVENT_TYPES
        return any(item.value == event_type for item in GATED_FANOUT_EVENT_TYPES)

    @staticmethod
    async def begin_fanout(
        db: AsyncSession,
        *,
        event_id: str | UUID,
        project_id: UUID | None = None,
        year: int | None = None,
    ) -> bool:
        """抢占这条耐久事件的派发权；此前已派发过返回 ``False``（本次跳过）。"""
        return await DurableEventOutboxService.claim_consumption(
            db,
            event_id=event_id,
            handler_name=FANOUT_HANDLER_NAME,
            handler_version=FANOUT_HANDLER_VERSION,
            project_id=project_id,
            year=year,
        )

    @staticmethod
    async def abort_fanout(db: AsyncSession, *, event_id: str | UUID) -> bool:
        """派发失败后归还派发权，让 worker 重放能重新抢到（Property 54）。"""
        return await DurableEventOutboxService.release_consumption(
            db,
            event_id=event_id,
            handler_name=FANOUT_HANDLER_NAME,
            handler_version=FANOUT_HANDLER_VERSION,
        )

    # ------------------------------------------------------------------
    # 复用既有重放 / DLQ 能力（不复制实现）
    # ------------------------------------------------------------------
    @staticmethod
    async def replay_pending(db: AsyncSession, **kwargs: Any) -> dict[str, Any]:
        """委托既有 ``ImportEventOutboxService.replay_pending``（含 DLQ 升级）。"""
        return await ImportEventOutboxService.replay_pending(db, **kwargs)

    @staticmethod
    async def summary(db: AsyncSession, **kwargs: Any) -> dict[str, Any]:
        return await ImportEventOutboxService.summary(db, **kwargs)

    @staticmethod
    async def dlq_depth(db: AsyncSession) -> int:
        return await ImportEventOutboxService.dlq_depth(db)


durable_event_outbox = DurableEventOutboxService()
