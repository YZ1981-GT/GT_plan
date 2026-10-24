"""真库用例的共享引擎收尾：``asyncio.run(run_and_dispose(coro))``。

``app.core.database`` 的 ``engine`` / ``async_engine`` / ``async_session`` 共用一个连接池，池里的连接绑在建连时的
事件循环上。``asyncio.run`` 退出就关掉这个循环；不释放连接池的话，同一进程里下一个 ``asyncio.run`` 的真库用例
从池里拿到旧循环的连接，ping 时报 ``Event loop is closed`` / ``'NoneType' object has no attribute 'send'``，
红在下一个文件上。守卫：``test_pg_tests_dispose_shared_engine.py``。
"""
from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")


async def run_and_dispose(awaitable: Awaitable[T]) -> T:
    """等 ``awaitable`` 跑完（成功或抛错）后释放共享引擎的连接池。"""
    try:
        return await awaitable
    finally:
        try:
            from app.core.database import engine
        except ImportError:  # 环境里连 app.core.database 都导入不了（调用方会自行 skip）⇒ 没有连接池可释放
            engine = None
        if engine is not None:
            await engine.dispose()
