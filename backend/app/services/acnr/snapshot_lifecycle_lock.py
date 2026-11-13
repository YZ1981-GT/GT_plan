"""ACNR 快照文件与项目版本锁的共同生命周期锁。

``projects.acnr_registry_version`` 是快照的持久引用。GC 的安全不变量是：只删除**没有任何项目
锁定**的旧快照。仅按「查引用 → 关会话 → 删除文件」实现会有 TOCTOU：归档事务可能在两步之间
验过快照并写入锁，而 GC 仍按旧引用集合把该快照删除。

本模块给两条路径同一把 PostgreSQL transaction advisory lock：

- ``project_registry_lock.lock_project_registry``：在验快照、写项目锁之前取得，持有到归档事务结束；
- ``catalog_snapshot_gc.run_db_aware_gc``：在同一事务内完成取锁、查引用、判候选和删文件。

使用 ``pg_try_advisory_xact_lock`` 而不是无界等待：GC 抢不到就 fail-closed 不删；用户归档抢不到则
返回 ``ACNR_REGISTRY_LOCK_FAILED``，提示稍后重试。事务结束由 PostgreSQL 自动释放，不留跨请求锁。
SQLite 仅用于本地契约测试，没有多进程共享库，返回 ``not_required``；其他未知 / 非 PostgreSQL
方言按 ``unverifiable`` fail-closed，不能假设它们天然具备等价锁语义。
"""
from __future__ import annotations

import logging
from typing import Any, Literal

import sqlalchemy as sa

logger = logging.getLogger(__name__)

# 两个有符号 int32，组成 PostgreSQL 的双键 advisory lock。
# 十六进制分别是 ASCII "ACNR" / "SNAP"，值固定且不依赖 Python hash 随机种子。
LOCK_NAMESPACE = 0x41434E52
LOCK_RESOURCE = 0x534E4150

LifecycleLockStatus = Literal["acquired", "busy", "not_required", "unverifiable"]


def _dialect_name(db: Any) -> str | None:
    """兼容 AsyncSession（get_bind）与 AsyncConnection（自身有 dialect）。"""
    try:
        get_bind = getattr(db, "get_bind", None)
        bind = get_bind() if callable(get_bind) else db
        dialect = getattr(bind, "dialect", None)
        name = getattr(dialect, "name", None)
        return str(name) if isinstance(name, str) else None
    except Exception:  # noqa: BLE001 — 判不出方言必须 fail-closed，不让探针异常变删除动作
        return None


async def try_acquire_snapshot_lifecycle_lock(db: Any) -> LifecycleLockStatus:
    """尝试取得当前事务的快照生命周期锁，不等待。

    返回值由调用方按动作解释：``busy`` / ``unverifiable`` 对 GC 都是零删除；归档则转稳定 409。
    数据库语句异常不外抛：异常后的 PostgreSQL 事务可能已 aborted，调用方不能继续读写；归档调用方
    会立即抛业务异常并由路由回滚，GC 调用方只生成不可验证报告后退出。
    """
    dialect = _dialect_name(db)
    if dialect is None:
        logger.warning("ACNR 快照生命周期锁：无法判定数据库方言")
        return "unverifiable"
    if dialect == "sqlite":
        return "not_required"
    if dialect != "postgresql":
        logger.warning("ACNR 快照生命周期锁：未登记的数据库方言 %s，按不可验证处理", dialect)
        return "unverifiable"

    async def _execute_lock():
        result = await db.execute(
            sa.text("SELECT pg_try_advisory_xact_lock(:namespace, :resource)"),
            {"namespace": LOCK_NAMESPACE, "resource": LOCK_RESOURCE},
        )
        return bool(result.scalar_one())

    try:
        # PostgreSQL 语句异常会把当前事务置为 aborted。用 SAVEPOINT 隔离这条探针：成功释放保存点后
        # transaction-level advisory lock 继续由外层事务持有；失败回滚保存点，归档编排仍能写入
        # failed job 并把 RegistryLockError 以稳定 409 返回。
        begin_nested = getattr(db, "begin_nested", None)
        if callable(begin_nested):
            async with begin_nested():
                acquired = await _execute_lock()
        else:  # 测试替身；真实 AsyncSession / AsyncConnection 都有 begin_nested
            acquired = await _execute_lock()
    except Exception as exc:  # noqa: BLE001 — 见 docstring，安全默认值是不执行文件删除
        logger.warning("ACNR 快照生命周期锁：取得失败（%s）", exc)
        return "unverifiable"
    return "acquired" if acquired else "busy"


__all__ = [
    "LOCK_NAMESPACE",
    "LOCK_RESOURCE",
    "LifecycleLockStatus",
    "try_acquire_snapshot_lifecycle_lock",
]
