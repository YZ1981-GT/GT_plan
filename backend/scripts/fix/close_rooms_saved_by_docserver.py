# -*- coding: utf-8 -*-
"""关闭「文档服务器已最终保存、却仍按 live 状态挂着」的在线编辑房间（存量修复）。

spec: writeback-followup-issue-closure · R1 / D1

═══ 为什么需要 ═══

修复前平台从不关闭 room：status 2（最终保存）回 ``error 0`` 之后，文档服务器已认定这一代
doc key 保存过，而 room 仍是 ``active``。下次进入复用同一个 key ⇒ 编辑器报「版本已更改」并
载入 room 物化时的旧字节（真栈：重药安徽 D2-2 g12）。新代码在回调里关闭 room；本工具补
存量：最后一次回调就是这条 durable 的 status 2（之后再无任何连接 / 保存回调）的 room。

判据只认「最后一次回调」：之后若有人重连，文档服务器会先发 status 1 —— 那种 room 可能有
live 会话，不碰。关闭走 ``RoomService.close_after_docserver_saved``（与回调同一条路径），
锁住 room 后在同一事务里复核判据。关闭只会让下次进入换代（同内容版本、同 artifact、新
doc key），不删除任何行。

用法::

    $env:PYTHONIOENCODING='utf-8'
    .\\.venv\\Scripts\\python.exe backend/scripts/fix/close_rooms_saved_by_docserver.py           # 只列出
    .\\.venv\\Scripts\\python.exe backend/scripts/fix/close_rooms_saved_by_docserver.py --apply   # 执行
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

#: 还没终结、却可能挂着已保存 key 的 room 状态（与 ``ROOM_EDGES`` 里能到 closed 的起点一致）。
_CLOSABLE = ("opening", "active", "close_barrier", "closing", "refresh_required")

_CANDIDATES_SQL = sa.text(
    """
    WITH last_delivery AS (
        SELECT DISTINCT ON (d.room_id) d.room_id, d.id AS delivery_id, d.callback_status,
               d.durable_at, d.response_error
        FROM working_paper_callback_delivery d
        ORDER BY d.room_id, d.received_at DESC, d.id DESC
    )
    SELECT r.id AS room_id, r.wp_id, r.entry_id, r.generation, r.state, ld.delivery_id,
           ld.durable_at, p.name AS project,
           (es.representation_generation = r.generation) AS at_pointer
    FROM working_paper_oo_room r
    JOIN last_delivery ld ON ld.room_id = r.id
    JOIN working_paper w ON w.id = r.wp_id
    JOIN projects p ON p.id = w.project_id
    LEFT JOIN working_paper_sync_entry_state es
           ON es.wp_id = r.wp_id AND es.entry_id = r.entry_id
    WHERE r.state = ANY(:closable)
      AND ld.callback_status = 2 AND ld.durable_at IS NOT NULL AND ld.response_error = 0
    ORDER BY p.name, r.entry_id, r.generation
    """
)

_LATEST_DELIVERY_SQL = sa.text(
    "SELECT id FROM working_paper_callback_delivery WHERE room_id = :r "
    "ORDER BY received_at DESC, id DESC LIMIT 1"
)


def _engine() -> Any:
    from app.core.config import settings

    return create_async_engine(str(settings.DATABASE_URL), poolclass=NullPool)


async def _close_one(Session: Any, row: Any) -> str:
    """锁 room → 复核「最后一次回调仍是这条 status 2」→ 关闭。返回结果码。"""
    from app.services.workpaper_sync.repository import WorkpaperSyncRepository
    from app.services.workpaper_sync.rooms import RoomService

    async with Session() as s:
        repo = WorkpaperSyncRepository(s)
        room = await repo.lock_room(row.room_id)
        latest = (await s.execute(_LATEST_DELIVERY_SQL, {"r": row.room_id})).scalar_one_or_none()
        if latest != row.delivery_id:
            await s.rollback()
            return "skipped_new_callback"
        if str(room.state) not in _CLOSABLE:
            await s.rollback()
            return f"skipped_state_{room.state}"
        closed = await RoomService(repo).close_after_docserver_saved(room_id=row.room_id)
        await s.commit()
        return f"closed:{closed.state}"


async def _main(apply: bool) -> int:
    engine = _engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as s:
            rows = (await s.execute(_CANDIDATES_SQL, {"closable": list(_CLOSABLE)})).all()
        print(f"候选 room：{len(rows)} 间（其中当前代际 {sum(1 for r in rows if r.at_pointer)} 间）")
        results: dict[str, int] = {}
        for row in rows:
            mark = "当前代际" if row.at_pointer else "历史代际"
            line = (
                f"  {row.project} | wp={row.wp_id} | {row.entry_id} | g{row.generation} "
                f"| {row.state} | 已保存于 {row.durable_at:%Y-%m-%d %H:%M:%S} UTC | {mark}"
            )
            if apply:
                outcome = await _close_one(Session, row)
                results[outcome.split(":")[0]] = results.get(outcome.split(":")[0], 0) + 1
                line += f" ⇒ {outcome}"
            print(line)
        if apply:
            print("结果：" + "，".join(f"{k} {v}" for k, v in sorted(results.items())))
        else:
            print("只读模式：未改任何数据；确认后加 --apply 执行。")
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--apply", action="store_true", help="执行关闭（默认只列出）")
    args = parser.parse_args()
    return asyncio.run(_main(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())
