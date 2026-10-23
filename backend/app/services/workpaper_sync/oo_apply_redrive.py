"""OO→HTML apply 中断后的重驱候选（spec writeback-followup-issue-closure R3.2）。

回调里的 apply 是同步跑完才回文档服务器的；进程在 apply 中途退出（开发服务器热重载、
容器重启、OOM）时，incoming 已 durable、application 停在 `queued` … `applying` 某一站。
文档服务器若已收到回执就不会再投，这一条从此没人推进：前端等到窗口超时，用户只能退出重进。

候选判据（全部来自已有事实，不引入新状态）：

* application 停在「进行中」的一站（:data:`REDRIVE_STATES`）；application 只在 incoming durable
  之后建行（唯一建行点同时写 `durable_at`），无需再判。`error` / `conflict` 不在内 —— 前者已有
  可见失败等用户重试，后者等用户裁决；
* 最近一次 application 事件早于 :data:`STALE_AFTER_SECONDS`（建行同一事务就写 `created` 事件，
  正在跑的 apply 每一站都会写事件，冷建注册最慢也在分钟内，5 分钟没有任何推进 ⇒ 没有活着的
  apply 在管它）；按建行时间先后，一次一条；
* 有绑定它的 primary operation（重驱沿用同一个 operation timeline，不新建）。

重驱本身走与回调同一个入口（`wp_sync_router._apply_durable_incoming`），见
`app.workers.oo_apply_redrive_worker`。
"""

from __future__ import annotations

import uuid
from typing import Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.workpaper_sync.models import ApplicationState
from app.services.workpaper_sync.oo_to_html import APPLY_ADMISSIBLE_APPLICATION_STATES

__all__ = ["REDRIVE_STATES", "STALE_AFTER_SECONDS", "find_stuck_application"]

#: apply 中途的各站（`queued` 是回调归组后、apply 开始前的那一站）= 协调器仍准入 apply 的状态，
#: 去掉两种「等用户」的：`error`（等用户重试）与 `conflict`（等用户裁决）。从准入集合推出、不另写
#: 名单（同 `oo_to_html` 的单一登记表原则：状态机加一站，这里自动跟上）。
REDRIVE_STATES: Final[frozenset[ApplicationState]] = APPLY_ADMISSIBLE_APPLICATION_STATES - {
    ApplicationState.error,
    ApplicationState.conflict,
}

#: 多久没有任何推进才算中断（秒）。
STALE_AFTER_SECONDS: Final[int] = 300

_FIND_SQL = sa.text(
    """
    SELECT a.id AS application_id, o.id AS operation_id
    FROM working_paper_content_application a
    JOIN working_paper_sync_operation o ON o.application_id = a.id
    WHERE a.state = ANY(:states)
      AND (SELECT max(e.occurred_at) FROM working_paper_content_application_event e
           WHERE e.application_id = a.id) < now() - make_interval(secs => :stale)
    ORDER BY a.created_at
    LIMIT 1
    """
)


async def find_stuck_application(
    session: AsyncSession, *, stale_after_seconds: int = STALE_AFTER_SECONDS
) -> tuple[uuid.UUID, uuid.UUID] | None:
    """最早一条中断的 apply：``(application_id, operation_id)``；没有则 ``None``。"""
    row = (
        await session.execute(
            _FIND_SQL,
            {"states": sorted(s.value for s in REDRIVE_STATES), "stale": float(stale_after_seconds)},
        )
    ).first()
    if row is None:
        return None
    return uuid.UUID(str(row.application_id)), uuid.UUID(str(row.operation_id))
