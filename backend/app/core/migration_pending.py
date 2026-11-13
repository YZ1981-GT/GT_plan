"""请求期「数据库结构落后于程序」的判定（spec voucher-workflow-linkage-lineage-closure R2，ADR-VWL-03）。

开发服务器热重载不跑迁移（``GT_BOOTSTRAP_DONE``），共享库可能比磁盘上的迁移旧：2026-11-03 共享库 V234、磁盘 V251，
客户入账、项目列表等一查新表新列就 500「服务器内部错误」，看不出是迁移没执行。

``generic_exception_handler`` 遇到「表 / 列不存在」（PG 42P01 / 42703）时调 :func:`pending_migration_info`：
磁盘上确有未执行的迁移才回 503 ``MIGRATION_PENDING``（写明两边版本与个数）；没有待执行迁移时照旧 500，
真实的代码缺陷（写错表名列名）不会被说成迁移问题；判定本身读库失败也按 500。
判定结果缓存 60 秒（迁移执行后最长 60 秒恢复正常判断），并发请求只查一次。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: undefined_table / undefined_column
MISSING_SCHEMA_SQLSTATES = frozenset({"42P01", "42703"})
CACHE_TTL_SECONDS = 60.0
_MAX_CHAIN = 6


@dataclass(frozen=True)
class PendingMigrations:
    db_max: str | None
    disk_max: str
    pending_count: int

    def message(self) -> str:
        db_part = f"库里最高 V{self.db_max}" if self.db_max else "库里还没有登记任何迁移"
        return (f"数据库结构未升级：程序需要 V{self.disk_max}，{db_part}，还有 {self.pending_count} 个迁移未执行。"
                "请联系管理员重启后端（启动时会自动执行迁移）")

    def detail(self) -> dict:
        return {
            "error_code": "MIGRATION_PENDING",
            "message": self.message(),
            "db_version": self.db_max,
            "code_version": self.disk_max,
            "pending_count": self.pending_count,
        }


def is_missing_schema_error(exc: BaseException | None) -> bool:
    """沿异常链（自身 → ``orig`` → ``__cause__`` → ``__context__``）找 PG 的「表 / 列不存在」。"""
    seen: set[int] = set()
    todo = [exc]
    while todo and len(seen) < _MAX_CHAIN * 4:
        cur = todo.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        code = getattr(cur, "sqlstate", None) or getattr(cur, "pgcode", None)
        if isinstance(code, str) and code in MISSING_SCHEMA_SQLSTATES:
            return True
        todo.extend(x for x in (getattr(cur, "orig", None), cur.__cause__, cur.__context__) if isinstance(x, BaseException))
    return False


_cache: tuple[float, PendingMigrations | None] | None = None
_locks: dict[int, asyncio.Lock] = {}


def _lock() -> asyncio.Lock:
    """按事件循环各一把锁（测试会换事件循环；一把锁绑定到旧循环后在新循环里会报错）。"""
    loop_id = id(asyncio.get_running_loop())
    lock = _locks.get(loop_id)
    if lock is None:
        _locks.clear()
        lock = _locks[loop_id] = asyncio.Lock()
    return lock


async def _inspect() -> PendingMigrations | None:
    from app.core.database import engine
    from app.core.migration_runner import MigrationRunner

    runner = MigrationRunner(engine=engine)
    try:
        readiness = await runner.inspect_readiness()
    finally:
        await runner.close()
    if not readiness.pending_versions:
        return None
    applied = sorted(readiness.applied_versions, key=int)
    return PendingMigrations(
        db_max=applied[-1] if applied else None,
        disk_max=max(readiness.disk_versions, key=int),
        pending_count=len(readiness.pending_versions),
    )


async def pending_migration_info(*, clock=time.monotonic) -> PendingMigrations | None:
    """有未执行的迁移返回概况，否则 None；读库失败也返回 None（调用方按 500 处理）。结果缓存 60 秒。"""
    global _cache
    if _cache is not None and clock() - _cache[0] < CACHE_TTL_SECONDS:
        return _cache[1]
    async with _lock():
        if _cache is not None and clock() - _cache[0] < CACHE_TTL_SECONDS:
            return _cache[1]
        try:
            info = await _inspect()
        except Exception as exc:  # noqa: BLE001 —— 判定失败不能再抛：按 500 处理
            logger.warning("迁移待执行判定失败，按 500 处理 error_type=%s error=%s", type(exc).__name__, exc)
            info = None
        _cache = (clock(), info)
        return info


def reset_cache_for_test() -> None:
    global _cache
    _cache = None
