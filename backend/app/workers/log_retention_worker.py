"""日志保留期清理 worker（V274，spec operation-log-and-last-login）

每日清理超期日志：
  - sys_login_log：默认保留 180 天（LOGIN_LOG_RETENTION_DAYS）
  - logs（操作审计）：默认保留 365 天（OPERATION_LOG_RETENTION_DAYS；
    ⚠️ workhours / wp_batch_router 按 action_type 查编辑时间段，保留期
    必须 ≥ 365，删短会断工时审计）

模式复用 export_cleanup_worker：30s 心跳、86400s 业务间隔、启动即跑一次、
leader lock 保证多副本只有一处执行清理。
"""

from __future__ import annotations

import asyncio
import logging

import sqlalchemy as sa

from app.core.config import settings
from app.workers.worker_helpers import write_heartbeat

logger = logging.getLogger("audit_platform.log_retention_worker")

HEARTBEAT_INTERVAL_SECONDS = 30
CLEANUP_INTERVAL_SECONDS = 86400  # 每日一次
#: 每轮每表最多删多少行（防止一次性大事务）
BATCH_SIZE = 5000


async def _cleanup_table(table, ts_column, retention_days: int) -> int:
    """删除单表超期行（限批，cutoff 在应用层计算 —— SQLite / PG 双方言通用）。

    🔴 不在 SQL 里拼 ``INTERVAL '...' DAYS``：那是 PG 专用语法，SQLite 测试环境直接报错。
    """
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))
    deleted_total = 0
    while True:
        rows = await db_execute(
            sa.select(table.id).where(ts_column < cutoff).limit(BATCH_SIZE)
        )
        ids = [row[0] for row in rows]
        if not ids:
            break
        await db_execute(sa.delete(table).where(table.id.in_(ids)), commit=True)
        deleted_total += len(ids)
        if len(ids) < BATCH_SIZE:
            break
    return deleted_total


async def db_execute(stmt, commit: bool = False):
    """独立短会话执行语句；commit=True 时提交。SELECT 返回行，写语句返回 []。"""
    from sqlalchemy import text as sa_text

    from app.core.database import async_session

    async with async_session() as session:
        result = await session.execute(stmt)
        if commit:
            await session.commit()
        # DELETE/UPDATE 的 CursorResult 无 returns_rows；用 statement 判别更稳
        is_select = isinstance(stmt, sa.Select) or (isinstance(stmt, sa.TextClause) and stmt.text.lower().startswith("select"))
        return result.fetchall() if is_select else []


async def run(stop_event: asyncio.Event) -> None:
    """清理主循环：启动即跑一次，之后每 24h 一次。"""
    login_days = int(getattr(settings, "LOGIN_LOG_RETENTION_DAYS", 180))
    biz_days = int(getattr(settings, "OPERATION_LOG_RETENTION_DAYS", 365))

    await _do_cleanup(login_days, biz_days)

    loop_count = 0
    while not stop_event.is_set():
        await write_heartbeat("log_retention_worker")
        loop_count += 1
        if loop_count * HEARTBEAT_INTERVAL_SECONDS >= CLEANUP_INTERVAL_SECONDS:
            await _do_cleanup(login_days, biz_days)
            loop_count = 0
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass


async def _do_cleanup(login_days: int, biz_days: int) -> None:
    from app.models.core import Log, SysLoginLog

    try:
        deleted_login = await _cleanup_table(SysLoginLog, SysLoginLog.ts, login_days)
        deleted_biz = await _cleanup_table(Log, Log.created_at, biz_days)
        if deleted_login or deleted_biz:
            logger.info(
                "[log_retention] 清理完成：sys_login_log=%d（保留 %d 天）、logs=%d（保留 %d 天）",
                deleted_login, login_days, deleted_biz, biz_days,
            )
    except Exception:
        # 清理失败不影响服务（下轮重试）；日志留痕即可
        logger.exception("[log_retention] 日志清理失败")
