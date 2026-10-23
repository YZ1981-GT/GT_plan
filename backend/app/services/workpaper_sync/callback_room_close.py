"""status 2 回 0 之后关闭 room（spec writeback-followup-issue-closure P1 / D1）。

文档服务器收到对 status 2（最终保存）的 ``error 0`` 后认定这一代 doc key 已保存；之后再用
同一个 key 打开，编辑器报「版本已更改」并按原配置重载 —— 载入的是 room 物化时的旧字节，
而 store 早已是新内容。所以这一代必须终结，下次进入由 materialize 的「终结代际换代」路径
发新 generation / 新 doc key。

由 OO 回调路由在 apply **之后**调用（apply 结算的是这一代 room 的 client 基线 / refresh 状态）。
"""
from __future__ import annotations

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import WorkpaperCallbackDelivery
from app.services.workpaper_sync.repository import WorkpaperSyncRepository
from app.services.workpaper_sync.rooms import RoomService

logger = logging.getLogger(__name__)

__all__ = ["DOCSERVER_FINAL_SAVE_STATUS", "close_room_if_docserver_saved"]

#: 文档服务器「最终保存」的回调 status。status 4（关闭且无修改）不在内：文档服务器没有保存
#: 那个 key，复用不会触发版本过期，换代反而让下次打开多一次转换（偏离契约
#: ``callback_statuses[].room_transition`` 的理由同此）。
DOCSERVER_FINAL_SAVE_STATUS = 2


async def close_room_if_docserver_saved(
    db: AsyncSession, *, room_id: uuid.UUID, delivery_id: uuid.UUID | None
) -> bool:
    """本次回调是已 durable 的 status 2 ⇒ 关闭 room 并 commit；返回是否走了关闭。

    * 判据取 delivery 行（``callback_status`` + ``durable_at``），与路由 landed 指标同口径：
      重发的回调命中既有 durable delivery 时同样成立，关闭本身幂等；
    * apply 失败也关：key 已被文档服务器作废，失败留在 operation 上走既有重试入口；
      关闭之后的 apply 由 ``content_mutation._advance_room`` / ``settle_client_baseline``
      对终态 room 跳过 refresh 与基线（D2）。

    🔴 不得抛：incoming 已 durable，回调必须回 0。先 rollback 是为了从 apply 可能留下的失败
    事务里脱身（``get_db`` 不 commit，未提交的写本来就会在请求结束时丢弃）。
    """
    if delivery_id is None:
        return False
    try:
        await db.rollback()
        row = (
            await db.execute(
                sa.select(
                    WorkpaperCallbackDelivery.callback_status,
                    WorkpaperCallbackDelivery.durable_at,
                ).where(WorkpaperCallbackDelivery.id == delivery_id)
            )
        ).one_or_none()
        if (
            row is None
            or int(row.callback_status) != DOCSERVER_FINAL_SAVE_STATUS
            or row.durable_at is None
        ):
            return False
        await RoomService(WorkpaperSyncRepository(db)).close_after_docserver_saved(
            room_id=room_id
        )
        await db.commit()
        return True
    except Exception:  # noqa: BLE001 — durable 之后回调必须回 0
        await db.rollback()
        logger.exception(
            "status 2 之后关闭 room 失败 room=%s delivery=%s —— 下次进入可能复用已保存的 key",
            room_id,
            delivery_id,
        )
        return False
