"""启动阶段的两个迁移任务：执行待执行迁移，再做只读的完整性核验（核验不过即阻断启动）。

从 ``startup_registry.py`` 原样抽出（2026-11-04，该文件超行数门）。``startup_registry`` 以原名
``_task_run_migrations`` / ``_task_migration_mark_complete`` 引用，``STARTUP_TASKS`` 的顺序与关键性不变。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.startup_registry import StartupContext


async def run_migrations(ctx: StartupContext) -> None:
    """Run pending migrations; the following critical task verifies the final state."""
    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner

    log = logging.getLogger("audit_platform")
    runner = MigrationRunner(database_url=settings.DATABASE_URL)
    try:
        result = await runner.run_pending()
        ctx.extras["migration_run_result"] = result
        if result.executed:
            log.info("[启动] 数据库迁移完成，执行了版本: %s", result.executed)
        if result.failed:
            for f in result.failed:
                log.error(
                    "[启动] 迁移 %s 失败 (%s): %s",
                    f.filename, f.error_type, f.error_message[:200],
                )
            log.error(
                "[启动] 共 %d 个迁移失败，已写入 schema_migration_failures 表 / health=degraded",
                len(result.failed),
            )
    except Exception as mig_err:
        ctx.extras["migration_run_error"] = type(mig_err).__name__
        log.warning(
            "[启动] 数据库迁移调度失败（等待只读完整性核验阻断启动）: %s", mig_err
        )
    finally:
        await runner.close()


async def migration_mark_complete(ctx: StartupContext) -> None:
    """Only mark complete after a strict, read-only disk/DB comparison."""
    from app.core.config import settings
    from app.core.migration_runner import MigrationRunner
    from app.core.runtime_state import migration_state

    runner = MigrationRunner(database_url=settings.DATABASE_URL)
    try:
        readiness = await runner.inspect_readiness()
        ctx.extras["migration_readiness"] = readiness
        if not readiness.is_complete:
            pending = list(readiness.pending_versions)
            failed = [f.version for f in readiness.failures]
            raise RuntimeError(
                "数据库迁移未就绪："
                f"pending_versions={pending}, failed_versions={failed}"
            )
        migration_state.mark_complete()
    except Exception:
        migration_state.mark_incomplete()
        raise
    finally:
        await runner.close()
