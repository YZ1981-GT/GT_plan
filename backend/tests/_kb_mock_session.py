"""知识检索 mock 会话辅助（spec knowledge-base-retrieval-and-authz-closure）。

检索内核把每条读 ``knowledge_index`` 的语句包进 ``begin_nested()``（SAVEPOINT），并用
``get_bind().dialect.name`` 判断是否探测 pgvector 列。``AsyncMock()`` 默认把这两个方法做成
协程 —— ``async with`` 一个协程会直接 TypeError，``get_bind()`` 返回未 await 的协程。

本辅助只补这两处**形状**，不改变 mock 的取数语义：
  * ``begin_nested()`` → 异步上下文管理器，``__aexit__`` 返回 False（**不吞**块内异常，
    否则失败路径测试就空转了）
  * ``get_bind()`` → 同步返回 dialect 为 ``sqlite`` 的 bind（pgvector 分支确定性关闭，
    走内存向量计算 —— 与未装 pgvector 的真库一致）
真库语义（SAVEPOINT 隔离、aborted 事务）由 ``*_pg.py`` 测试覆盖，mock 测不出。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


def attach_retrieval_session_shape(session, *, dialect: str = "sqlite"):
    savepoint = MagicMock()
    savepoint.__aenter__ = AsyncMock(return_value=None)
    savepoint.__aexit__ = AsyncMock(return_value=False)
    session.begin_nested = MagicMock(return_value=savepoint)

    bind = MagicMock()
    bind.dialect.name = dialect
    bind.engine = bind
    session.get_bind = MagicMock(return_value=bind)
    return session


def make_retrieval_session(**attrs):
    """新建带检索形状的 AsyncMock 会话；``attrs`` 覆盖 execute/commit 等。"""
    session = AsyncMock()
    for key, value in attrs.items():
        setattr(session, key, value)
    return attach_retrieval_session_shape(session)
