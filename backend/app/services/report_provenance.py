"""S5 报表来源信封运行上下文与项目年度串行门。"""
from __future__ import annotations

import asyncio
import weakref
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import UUID

import sqlalchemy as sa

from app.models.report_models import ReportGenerationRun


@dataclass(frozen=True)
class ReportGenerationContext:
    run_id: UUID
    project_id: UUID
    year: int
    trigger: str
    triggered_by: UUID | None
    started_at: datetime
    calc_version: str

    @property
    def fence(self) -> UUID:
        return self.run_id


_ACTIVE: ContextVar[ReportGenerationContext | None] = ContextVar("report_generation_context", default=None)
_LOCKS: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def current_context() -> ReportGenerationContext | None:
    return _ACTIVE.get()


def _lock(project_id: UUID, year: int) -> asyncio.Lock:
    key = (id(asyncio.get_running_loop()), str(project_id), int(year))
    result = _LOCKS.get(key)
    if result is None:
        result = asyncio.Lock()
        _LOCKS[key] = result
    return result


async def _advisory_lock(db: Any, project_id: UUID, year: int) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    await db.execute(sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {
        "key": f"report_generation:{project_id}:{year}",
    })


@asynccontextmanager
async def generation_context(
    db: Any, *, project_id: UUID, year: int, trigger: str,
    triggered_by: UUID | None, calc_version: str,
) -> AsyncIterator[ReportGenerationContext]:
    """创建与本事务同生共死的 run，并在当前协程暴露其 fence。"""
    async with _lock(project_id, year):
        await _advisory_lock(db, project_id, year)
        now = datetime.now(timezone.utc)
        run = ReportGenerationRun(
            project_id=project_id, year=year, trigger=trigger, triggered_by=triggered_by,
            started_at=now, status="running", calc_version=calc_version,
        )
        db.add(run)
        await db.flush()
        ctx = ReportGenerationContext(run.id, project_id, year, trigger, triggered_by, now, calc_version)
        token = _ACTIVE.set(ctx)
        try:
            yield ctx
        finally:
            _ACTIVE.reset(token)


async def finish_generation(db: Any, ctx: ReportGenerationContext, summary: Any) -> None:
    """把逐行汇总回写到当前 run；调用方随后统一 commit。"""
    run = await db.get(ReportGenerationRun, ctx.run_id)
    if run is None:
        raise RuntimeError("报表来源运行记录不存在")
    run.changed_rows = len(getattr(summary, "changed_rows", ()))
    run.recomputed_rows = len(getattr(summary, "recomputed_rows", ()))
    run.failed_rows = len(getattr(summary, "failed_rows", ()))
    errors = [str(row.get("error") or "") for row in getattr(summary, "failed_rows", ())]
    run.error_summary = "；".join(error for error in errors if error)[:4000] or None
    run.status = "partial" if run.failed_rows else "succeeded"
    run.finished_at = datetime.now(timezone.utc)
    await db.flush()


def install_report_generation_provenance(report_engine_cls: type) -> None:
    """为三条既有报表写路径安装同一 run context，不复制计算实现。"""
    from functools import wraps

    from app.services.report_freshness import CALC_VERSION
    from app.services.report_row_compute import GenerateSummary

    original_full = report_engine_cls.generate_all_reports
    original_stale = report_engine_cls.recalculate_stale_rows
    original_affected = report_engine_cls.regenerate_affected

    async def run_with_context(
        engine: Any, operation: Any, *, trigger: str, project_id: UUID, year: int,
        triggered_by: UUID | None, kwargs: dict[str, Any],
    ) -> Any:
        summary = kwargs.get("summary_out")
        if summary is None:
            summary = GenerateSummary()
            kwargs["summary_out"] = summary
        active = current_context()
        if active is not None:
            if active.project_id != project_id or active.year != year:
                raise RuntimeError("报表来源运行上下文与当前项目年度不一致")
            return await operation(engine, project_id, year, **kwargs)
        async with generation_context(
            engine.db, project_id=project_id, year=year, trigger=trigger,
            triggered_by=triggered_by, calc_version=f"report:{CALC_VERSION}",
        ) as context:
            result = await operation(engine, project_id, year, **kwargs)
            await finish_generation(engine.db, context, summary)
            return result

    @wraps(original_full)
    async def full(
        self: Any, project_id: UUID, year: int, *args: Any,
        triggered_by: UUID | None = None, **kwargs: Any,
    ) -> dict[str, Any]:
        if args:
            kwargs["applicable_standard"] = args[0]
            if len(args) > 1:
                kwargs["mode"] = args[1]
            if len(args) > 2:
                kwargs["debug"] = args[2]
        return await run_with_context(
            self, original_full, trigger="full", project_id=project_id,
            year=year, triggered_by=triggered_by, kwargs=kwargs,
        )

    @wraps(original_stale)
    async def stale(
        self: Any, project_id: UUID, year: int, *args: Any,
        triggered_by: UUID | None = None, **kwargs: Any,
    ) -> dict[str, Any]:
        if args:
            kwargs["applicable_standard"] = args[0]
            if len(args) > 1:
                kwargs["mode"] = args[1]
        return await run_with_context(
            self, original_stale, trigger="stale", project_id=project_id,
            year=year, triggered_by=triggered_by, kwargs=kwargs,
        )

    @wraps(original_affected)
    async def affected(
        self: Any, project_id: UUID, year: int, *args: Any,
        triggered_by: UUID | None = None, **kwargs: Any,
    ) -> int:
        if args:
            kwargs["changed_accounts"] = args[0]
            if len(args) > 1:
                kwargs["applicable_standard"] = args[1]
        return await run_with_context(
            self, original_affected, trigger="affected", project_id=project_id,
            year=year, triggered_by=triggered_by, kwargs=kwargs,
        )

    report_engine_cls.generate_all_reports = full
    report_engine_cls.recalculate_stale_rows = stale
    report_engine_cls.regenerate_affected = affected
