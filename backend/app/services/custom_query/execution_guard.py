"""查询执行的时间预算与取消传播（R6.4 / R6.5）。

**存在理由（真实 PG 实测）**：库级 ``statement_timeout = 0``（无限制），且全仓
grep ``statement_timeout`` 命中 **0** 处 —— 任何一条失控查询都能一直占着连接，
而 ``tb_ledger`` 实测约 697 万行、白名单又允许 JOIN，一次误操作即可拖垮连接池。
配合 ``except Exception → 200`` 的 fail-open，用户看到的还只是「空结果」。

本模块只做两件事：给语句设时间预算，以及在客户端断开时把取消传下去。

_Requirements: 6.4, 6.5
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: 交互式查询的时间预算（毫秒）。超出即认为用户等不起，应改为加筛选或导出。
QUERY_TIMEOUT_MS = 30_000
#: 导出的时间预算（毫秒）。导出是后台性质，允许更久但仍必须有上限。
EXPORT_TIMEOUT_MS = 120_000

#: PG 语句被取消时的 SQLSTATE（query_canceled）
_QUERY_CANCELED_SQLSTATE = "57014"


@asynccontextmanager
async def statement_timeout(
    db: AsyncSession, timeout_ms: int = QUERY_TIMEOUT_MS
) -> AsyncIterator[None]:
    """在当前事务内设置语句超时。

    用 ``SET LOCAL`` 而非 ``SET``：作用域限于当前事务，不会污染连接池里被复用的
    连接（``SET`` 会一直留在该连接上，影响后续任意请求）。``SET LOCAL`` 需要处于
    显式事务中，故不在事务内时先开一个。

    非 PG 后端（如测试用 SQLite）不识别该语句，此时降级为无超时并记 debug ——
    但**不吞** PG 上的失败，那属于必须暴露的配置问题。
    """
    started_tx = False
    try:
        if not db.in_transaction():
            await db.begin()
            started_tx = True
    except Exception as exc:  # noqa: BLE001 — 事务状态探测失败不阻断查询
        logger.debug("statement_timeout 事务探测失败，跳过超时设置: %s", exc)
        yield
        return

    try:
        await db.execute(
            text(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
        )
    except Exception as exc:  # noqa: BLE001
        # 方言不支持（SQLite 等）→ 无超时执行；PG 上若出现应在日志里看到
        logger.debug("statement_timeout 设置失败（方言可能不支持）: %s", exc)

    try:
        yield
    finally:
        if started_tx:
            # 本上下文只读，不提交；由调用方决定事务归属
            pass


def is_query_canceled(exc: BaseException) -> bool:
    """判断异常是否为语句超时 / 被取消。"""
    if isinstance(exc, asyncio.TimeoutError):
        return True
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None) or getattr(
        getattr(exc, "orig", None), "pgcode", None
    )
    if sqlstate == _QUERY_CANCELED_SQLSTATE:
        return True
    if isinstance(exc, DBAPIError):
        return _QUERY_CANCELED_SQLSTATE in str(exc)
    return False


def query_timeout_error(timeout_ms: int) -> HTTPException:
    """构造可识别的超时错误（408）。

    必须是明确的错误码而不是空结果 —— 「查不到」与「查太久被掐掉」对审计师意味着
    完全不同的下一步动作。
    """
    return HTTPException(
        status_code=408,
        detail={
            "error_code": "QUERY_TIMEOUT",
            "message": (
                f"查询超过 {timeout_ms // 1000} 秒时间预算已中止；"
                "请补充筛选条件缩小范围，或改用导出"
            ),
            "timeout_ms": timeout_ms,
        },
    )


@asynccontextmanager
async def cancellable_query(
    db: AsyncSession, timeout_ms: int = QUERY_TIMEOUT_MS
) -> AsyncIterator[None]:
    """统一的「超时 + 取消」包装。

    - 语句超时 → 408 ``QUERY_TIMEOUT``；
    - 客户端断开（FastAPI 取消 task）→ 显式 rollback 后重新抛出 ``CancelledError``，
      让连接尽快回池而不是留着一条还在跑的语句。
    """
    async with statement_timeout(db, timeout_ms):
        try:
            yield
        except asyncio.CancelledError:
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001 — 回滚失败不掩盖取消本身
                pass
            raise
        except Exception as exc:
            if is_query_canceled(exc):
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                raise query_timeout_error(timeout_ms) from exc
            raise
