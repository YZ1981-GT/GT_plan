# -*- coding: utf-8 -*-
"""同一 lease 在同代 room 里重开编辑器：旧 client-confirmation 让位给 room 已认可的新基线。

spec: d2-skeleton-slot-reuse-and-writeback-speed · R4（重开在线编辑必须打开最新版）

═══ 缺陷（重药安徽 D2 真栈，2026-10-23）═══

OO→HTML 应用成功且 merged == incoming 时，``RoomService.settle_client_baseline`` 把 room
的 client-confirmed 快照推进到已应用版本；随会话的提交不换代（``_next_generation_probe``
的 ``plan.room_id`` 分支），entry pointer 指向同代的新 representation。participant 的
confirmation 行却是 immutable 的，永远停在打开时那一版。

之后用户重开在线编辑 —— 关标签页、刷新、``leave`` 因在途请求 409、网络断开后再点 ——
``_join_or_reuse_participant`` 复用同一条 lease（``uq_wpoop_active_lease``），而
confirm-descriptor 回传的是 pointer 上的新基线 ⇒ 撞「同一编辑会话不得用不同基线二次确认」，
lease 到期（4 小时）前在线编辑打不开。正常路径只在 ``leave`` 成功时才不撞，任何非正常
退出都会把用户锁住。

═══ 判据（只放行一种形态，其余保持原 409）═══

新 descriptor 的 (representation, content version, projection) **逐项等于** room 当前的
client-confirmed 快照，且新内容版本的 revision **严格大于** 旧确认的 ⇒ 旧确认作废
（``invalidated_at``；``uq_wpocc_active`` 是 ``WHERE invalidated_at IS NULL`` 的 partial
unique），新确认照常插入。

* room 快照只会由「本代确认」或「merged == incoming 的应用」写入，所以等于快照 = room 已
  认定编辑器里的文档就是这一版（同 doc_key 的 OO 缓存也正是它）；
* 旧基线的 descriptor（陈旧标签页重放）、room 未认可的基线、同版本换 representation、
  版本倒退 —— 全部仍是 409。
* 在途请求不受影响：request 冻结的 base 取自 room 快照（``build_request_freeze``），
  不读 confirmation 行。
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import (
    WorkpaperContentVersion,
    WorkpaperOoClientConfirmation,
    WorkpaperOoRoom,
)

__all__ = ["is_rebase_onto_room_baseline"]


async def is_rebase_onto_room_baseline(
    session: AsyncSession,
    *,
    room: WorkpaperOoRoom,
    existing: WorkpaperOoClientConfirmation,
    representation_id: uuid.UUID,
    content_version_id: uuid.UUID,
    projection_sha256: str,
) -> bool:
    """新 descriptor 是否把同一 lease 的确认前移到 room 已认可的快照上（见模块 docstring）。"""
    if (
        room.client_confirmed_representation_id != representation_id
        or room.client_confirmed_base_version_id != content_version_id
        or str(room.client_confirmed_projection_sha256 or "").strip()
        != str(projection_sha256 or "").strip()
    ):
        return False
    # 严格前移：同一内容版本换 representation（revision 相等）与版本倒退一并拒绝。
    rows = (
        await session.execute(
            sa.select(WorkpaperContentVersion.id, WorkpaperContentVersion.revision).where(
                WorkpaperContentVersion.id.in_(
                    (existing.content_version_id, content_version_id)
                )
            )
        )
    ).all()
    revisions = {row[0]: int(row[1]) for row in rows}
    old = revisions.get(existing.content_version_id)
    new = revisions.get(content_version_id)
    return old is not None and new is not None and new > old
