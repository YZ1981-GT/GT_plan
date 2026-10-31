"""公式执行预算（spec formula-hub-integrity-closure 需求 12.3，ADR-FHIC-19）。

:func:`run_with_deadline` 给一次求值一个时限，五个执行端点共用：``/api/formula/execute``、``/api/formula/debug``、
``/api/report-config/execute-formula`` 每请求 :func:`execute_seconds`（``FORMULA_EXECUTE_TIMEOUT``）；
``/api/formula/batch-execute``、``/api/report-config/execute-formulas-batch`` 整批 :func:`batch_seconds`
（``FORMULA_BATCH_TIMEOUT``）。

1. 求值全程在保存点里（``db.begin_nested()``）；PG 上一条语句先读 ``current_setting('statement_timeout')``、再在本事务内
   ``set_config('statement_timeout', ms, true)``，``ms = FORMULA_EXECUTE_TIMEOUT × 1000 − 500`` —— 单条语句由数据库先以
   query_canceled（SQLSTATE 57014）结束，属普通数据库错误、保存点可回滚；SQLite 跳过。
2. ``asyncio.wait_for(factory(), seconds)`` 只作 Python 侧兜底。
3. 结局：
   - 成功 ⇒ 恢复 ``statement_timeout`` 原值、释放保存点，返回结果；求值里吞掉过其他数据库错误、PG 事务停在失败态
     （恢复语句执行不了）⇒ 回到保存点后照常返回结果（结果里已如实报错，会话回到可用状态）；
   - 整体超时（``TimeoutError``）或语句被取消 ⇒ 回滚保存点（同时撤销该 GUC）后抛 :class:`FormulaTimeout`（504
     ``FORMULA_TIMEOUT``，不返回部分结果）。「语句被取消」只按驱动异常的 SQLSTATE 判（:func:`statement_canceled`，不依赖
     异常类名），**被内层 ``except`` 吞掉的也算**：预载层等处 fail-soft 的取数会把取消记成取数缺口后继续求值，方言级
     ``handle_error`` 观察器按本次求值的 ContextVar 记下每条被取消的语句，求值结束后照样按超时处理；
   - 保存点回滚本身失败，或连接已被作废（取消落在语句执行中时 SQLAlchemy 作废该连接，保存点回滚成了空操作）⇒
     ``await db.invalidate()`` 后抛 504：该连接不再复用，会话下次使用时换新连接；
   - 其他异常 ⇒ 回滚保存点后原样上抛。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any, TypeVar

from fastapi import HTTPException, status
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

TIMEOUT_ERROR_CODE = "FORMULA_TIMEOUT"
BATCH_TOO_LARGE_ERROR_CODE = "FORMULA_BATCH_TOO_LARGE"
QUERY_CANCELED_SQLSTATE = "57014"
#: 单条语句时限比 FORMULA_EXECUTE_TIMEOUT 少的毫秒数：数据库先结束语句，Python 侧兜底后到
STATEMENT_SLACK_MS = 500
CAUSE_DEADLINE = "整体超时"
CAUSE_STATEMENT = "数据库语句超时"

#: 本次求值范围内被数据库取消的语句（观察器写入；``None`` = 不在预算范围内）
_canceled_in_scope: ContextVar[list[BaseException] | None] = ContextVar("formula_budget_canceled", default=None)


class FormulaTimeout(HTTPException):
    """504 ``FORMULA_TIMEOUT``：整体超时或数据库语句被取消；不返回部分结果。"""

    def __init__(self, seconds: float, cause: str) -> None:
        super().__init__(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail={
            "error_code": TIMEOUT_ERROR_CODE, "cause": cause, "timeout_seconds": seconds,
            "message": f"公式执行超时（{cause}，时限 {seconds:g} 秒），未返回部分结果"})


def execute_seconds() -> float:
    """单条（execute / debug / report-config 单条）每请求的时限。"""
    return float(settings.FORMULA_EXECUTE_TIMEOUT)


def batch_seconds() -> float:
    """两个 batch 端点整批的时限。"""
    return float(settings.FORMULA_BATCH_TIMEOUT)


def statement_timeout_ms() -> int:
    """PG 单条语句时限（毫秒）；至少 1（0 在 PG 里表示不限时）。"""
    return max(int(settings.FORMULA_EXECUTE_TIMEOUT * 1000) - STATEMENT_SLACK_MS, 1)


def require_batch_size(count: int, limit: int) -> None:
    """批量条数超上限 ⇒ 422 ``FORMULA_BATCH_TOO_LARGE``（整批拒绝，不截断、不求值）。"""
    if count > limit:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "error_code": BATCH_TOO_LARGE_ERROR_CODE, "max_items": limit, "received": count,
            "message": f"单次最多 {limit} 条公式，收到 {count} 条"})


def statement_canceled(exc: BaseException | None) -> bool:
    """数据库以 query_canceled（SQLSTATE 57014）结束了语句：看驱动异常的 ``sqlstate`` / ``pgcode``，不依赖类名。"""
    orig = getattr(exc, "orig", exc)
    return QUERY_CANCELED_SQLSTATE in (getattr(orig, "sqlstate", None), getattr(orig, "pgcode", None))


def _on_db_error(context: Any) -> None:
    """方言级 ``handle_error``：本次求值范围内被取消的语句记下来（内层 ``except`` 吞掉了也照样算超时）。"""
    seen = _canceled_in_scope.get()
    if seen is not None and statement_canceled(context.original_exception):
        seen.append(context.original_exception)


def _watch(db: AsyncSession) -> None:
    """在会话所用引擎上挂观察器（幂等；``handle_error`` 只能挂在引擎 / 方言上）。"""
    bind = db.get_bind()
    engine = getattr(bind, "engine", bind)
    if not event.contains(engine, "handle_error", _on_db_error):
        event.listen(engine, "handle_error", _on_db_error)


async def _limit_statements(db: AsyncSession) -> str | None:
    """PG：本事务内设单条语句时限，返回原值供成功后恢复；其他方言（SQLite 单测）跳过，返回 ``None``。"""
    if db.get_bind().dialect.name != "postgresql":
        return None
    # 读原值与设新值一条语句：MATERIALIZED CTE 先求出原值，外层投影再 set_config（求值顺序由计划保证）
    return (await db.execute(text(
        "WITH original AS MATERIALIZED (SELECT current_setting('statement_timeout') AS value) "
        "SELECT original.value, set_config('statement_timeout', :ms, true) FROM original"),
        {"ms": str(statement_timeout_ms())})).one()[0]


async def _discard(db: AsyncSession, nested: AsyncSessionTransaction) -> None:
    """回滚保存点（PG 上同时撤销本保存点之后设的 statement_timeout）；回滚失败或连接已作废 ⇒ 作废会话。"""
    try:
        await nested.rollback()
        if not (await db.connection()).invalidated:
            return
        reason = "连接已作废（取消落在语句执行中）"
    except Exception as exc:  # noqa: BLE001 —— 原因记日志，会话随即作废
        reason = f"{type(exc).__name__}: {exc}"
    logger.warning("公式执行预算：保存点回滚失败（%s），作废会话，该连接不再复用", reason)
    try:
        await db.invalidate()
    except Exception:  # noqa: BLE001 —— 作废失败不掩盖本次超时 / 原异常
        logger.exception("公式执行预算：作废会话失败")


async def run_with_deadline(db: AsyncSession, factory: Callable[[], Awaitable[T]], *, seconds: float) -> T:
    """在保存点 + 单条语句时限 + 整体时限内跑 ``factory()``（结局见模块 docstring）。"""
    _watch(db)
    nested = await db.begin_nested()
    canceled: list[BaseException] = []
    token = _canceled_in_scope.set(canceled)
    try:
        original = await _limit_statements(db)
        result = await asyncio.wait_for(factory(), seconds)
    except TimeoutError as exc:
        await _discard(db, nested)
        raise FormulaTimeout(seconds, CAUSE_DEADLINE) from exc
    except Exception as exc:
        await _discard(db, nested)
        if statement_canceled(exc) or canceled:
            raise FormulaTimeout(seconds, CAUSE_STATEMENT) from exc
        raise
    finally:
        _canceled_in_scope.reset(token)
    if canceled:  # 被取消的语句让内层吞掉了：结果不完整，不返回
        await _discard(db, nested)
        raise FormulaTimeout(seconds, CAUSE_STATEMENT) from canceled[0]
    try:
        if original is not None:
            await db.execute(text("SELECT set_config('statement_timeout', :value, true)"), {"value": original})
    except Exception:  # noqa: BLE001
        # 求值里有被吞掉的其他数据库错误（结果里已如实报错），PG 事务停在失败态、恢复语句执行不了：回到保存点
        # （同时撤销 GUC）后照常返回结果 —— 不能先 RELEASE：释放失败后保存点不再回滚，会话会一直停在失败态
        logger.warning("公式执行预算：求值期间有被吞掉的数据库错误，回到保存点", exc_info=True)
        await _discard(db, nested)
        return result
    await nested.commit()
    return result
