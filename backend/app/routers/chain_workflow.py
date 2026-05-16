"""全链路工作流路由 — 执行/进度/历史/重试

Requirements: 1.1, 2.1-2.7, 9.1-9.4, 15.1-15.3

端点:
  POST /api/projects/{pid}/workflow/execute-full-chain  — 执行全链路
  GET  /api/projects/{pid}/workflow/progress/{eid}      — SSE 进度流
  GET  /api/projects/{pid}/workflow/executions          — 执行历史
  POST /api/projects/{pid}/workflow/retry/{eid}         — 重试失败步骤
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.services.chain_orchestrator import (
    ChainConflictError,
    ChainStep,
    chain_orchestrator,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/projects/{project_id}/workflow",
    tags=["chain-workflow"],
)

# ---------------------------------------------------------------------------
# SSE subscriber registry (per execution_id)
# ---------------------------------------------------------------------------

_subscribers: dict[str, list[asyncio.Queue]] = {}


def _get_subscribers(execution_id: str) -> list[asyncio.Queue]:
    """Get or create subscriber list for an execution."""
    if execution_id not in _subscribers:
        _subscribers[execution_id] = []
    return _subscribers[execution_id]


def _cleanup_subscribers(execution_id: str) -> None:
    """Remove subscriber list after execution completes."""
    _subscribers.pop(execution_id, None)


async def _broadcast(execution_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Broadcast an SSE event to all subscribers of an execution."""
    queues = _subscribers.get(execution_id, [])
    message = {"event": event_type, "data": data}
    for q in queues:
        try:
            q.put_nowait(message)
        except asyncio.QueueFull:
            pass  # Drop if subscriber is too slow


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------


class ExecuteChainRequest(BaseModel):
    year: int = Field(..., description="年度")
    steps: list[str] | None = Field(None, description="指定步骤（空=全部）")
    force: bool = Field(False, description="强制执行（跳过前置条件）")


class ExecutionResponse(BaseModel):
    execution_id: str
    status: str
    steps: dict
    total_duration_ms: int | None = None
    started_at: str | None = None
    completed_at: str | None = None


class ExportPackageRequest(BaseModel):
    """组合导出包请求参数"""
    year: int = Field(..., description="年度")
    include_audit_report: bool = Field(False, description="是否包含审计报告")
    include_workpapers: bool = Field(False, description="是否包含审定表")
    force_export: bool = Field(False, description="强制导出（跳过一致性检查）")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/execute-full-chain")
async def execute_full_chain(
    project_id: UUID,
    body: ExecuteChainRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行全链路生成

    Requirements: 1.1-1.9
    """
    # Parse steps
    chain_steps: list[ChainStep] | None = None
    if body.steps:
        try:
            chain_steps = [ChainStep(s) for s in body.steps]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid step: {e}")

    # Create progress callback that broadcasts to SSE subscribers
    execution_id_holder: list[str] = []

    async def progress_cb(event_type: str, payload: dict[str, Any]) -> None:
        if execution_id_holder:
            await _broadcast(execution_id_holder[0], event_type, payload)

    try:
        execution = await chain_orchestrator.execute_full_chain(
            db=db,
            project_id=project_id,
            year=body.year,
            steps=chain_steps,
            force=body.force,
            trigger_type="manual",
            triggered_by=current_user.id,
            progress_cb=progress_cb,
        )
        execution_id_holder.append(execution.id)

        await db.commit()

        # Cleanup subscribers after completion
        _cleanup_subscribers(execution.id)

        return {
            "execution_id": execution.id,
            "status": execution.status,
            "steps": execution.steps,
            "total_duration_ms": execution.total_duration_ms,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        }

    except ChainConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.exception("Chain execution failed for project %s", project_id)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Chain execution failed: {str(e)}")


@router.get("/progress/{execution_id}")
async def get_progress_stream(
    project_id: UUID,
    execution_id: str,
    current_user: User = Depends(get_current_user),
):
    """SSE 进度流 — 实时推送步骤状态

    Requirements: 2.1-2.7
    支持多客户端同时订阅同一 execution_id。
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    subscribers = _get_subscribers(execution_id)
    subscribers.append(queue)

    async def event_generator():
        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = message.get("event", "message")
                    data = json.dumps(message.get("data", {}), ensure_ascii=False, default=str)
                    yield f"event: {event_type}\ndata: {data}\n\n"

                    # Terminal event — close stream
                    if event_type == "chain_completed":
                        break
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f": keepalive\n\n"
        finally:
            # Remove this subscriber
            if queue in subscribers:
                subscribers.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/executions")
async def get_executions(
    project_id: UUID,
    status: str | None = Query(None, description="按状态筛选"),
    start_time: str | None = Query(None, description="开始时间 ISO 格式"),
    end_time: str | None = Query(None, description="结束时间 ISO 格式"),
    limit: int = Query(100, ge=1, le=100, description="最多返回条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """执行历史列表

    Requirements: 9.1-9.4
    """
    start_dt = datetime.fromisoformat(start_time) if start_time else None
    end_dt = datetime.fromisoformat(end_time) if end_time else None

    executions = await chain_orchestrator.get_execution_history(
        db=db,
        project_id=project_id,
        limit=limit,
        status=status,
        start_time=start_dt,
        end_time=end_dt,
    )

    return {
        "items": [
            {
                "execution_id": e.id,
                "status": e.status,
                "steps": e.steps,
                "trigger_type": e.trigger_type,
                "triggered_by": e.triggered_by,
                "started_at": e.started_at.isoformat() if e.started_at else None,
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "total_duration_ms": e.total_duration_ms,
            }
            for e in executions
        ],
        "total": len(executions),
    }


@router.post("/export-package")
async def export_package(
    project_id: UUID,
    body: "ExportPackageRequest",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """组合导出包（ZIP）

    ZIP 包含：财务报表 xlsx + 附注 docx + manifest.json
    打包前执行 ConsistencyGate 校验。

    Requirements: 5.1-5.8
    """
    from app.services.export_package_service import ConsistencyCheckError, ExportPackageService

    service = ExportPackageService(db)
    try:
        output = await service.export_package(
            project_id=project_id,
            year=body.year,
            include_audit_report=body.include_audit_report,
            include_workpapers=body.include_workpapers,
            force_export=body.force_export,
        )
    except ConsistencyCheckError as e:
        raise HTTPException(status_code=400, detail={"message": str(e), "checks": e.checks})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Export package failed for project %s", project_id)
        raise HTTPException(status_code=500, detail=f"Export package failed: {str(e)}")

    # Build ZIP filename per 致同 naming convention
    from app.services.export_package_service import get_company_short_name, sanitize_filename
    from app.models.core import Project

    result = await db.execute(sa_select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    company_short = get_company_short_name(project) if project else "未知公司"
    zip_filename = sanitize_filename(f"{company_short}_{body.year}年度审计终稿.zip")

    return StreamingResponse(
        output,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_filename}"',
            "Content-Type": "application/zip",
        },
    )


@router.get("/consistency-check")
async def consistency_check(
    project_id: UUID,
    year: int = Query(..., description="年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """一致性检查 — 5 项检查

    Requirements: 6.1-6.6
    返回每项检查结果 { check_name, passed, details, severity }
    """
    from app.services.consistency_gate import ConsistencyGate

    gate = ConsistencyGate(db)
    result = await gate.run_all_checks(project_id, year)

    checks_payload = [
        {
            "check_name": c.check_name,
            "passed": c.passed,
            "details": c.details,
            "severity": c.severity,
        }
        for c in result.checks
    ]
    all_passed = all(c["passed"] for c in checks_payload) if checks_payload else True

    return {
        "overall": result.overall,
        "all_passed": all_passed,           # F4 (v3 §2): 顶层方便前端徽章
        "consistent": all_passed,           # alias，兼容多种前端写法
        "passed_count": sum(1 for c in checks_payload if c["passed"]),
        "total_count": len(checks_payload),
        "checks": checks_payload,
    }


@router.get("/compare/{execution_id}")
async def compare_execution(
    project_id: UUID,
    execution_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """版本对比 — 返回执行前后每行变化

    Requirements: 14.1-14.5
    Returns per-row changes: { row_code, row_name, before, after, diff, diff_percent }
    """
    from app.models.chain_execution import ChainExecution

    stmt = sa_select(ChainExecution).where(ChainExecution.id == execution_id)
    result = await db.execute(stmt)
    execution = result.scalar_one_or_none()

    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")

    snapshot_before = execution.snapshot_before or {}
    changes = []

    # Load current report data for comparison
    from app.models.report_models import FinancialReport, FinancialReportType

    rpt_stmt = sa_select(FinancialReport).where(
        FinancialReport.project_id == project_id,
        FinancialReport.year == execution.year,
        FinancialReport.is_deleted == False,
    )
    rpt_result = await db.execute(rpt_stmt)
    current_rows = rpt_result.scalars().all()

    # Build before map from snapshot
    before_map: dict[str, float] = {}
    if "report_rows" in snapshot_before:
        for row_data in snapshot_before["report_rows"]:
            code = row_data.get("row_code", "")
            before_map[code] = float(row_data.get("amount", 0))

    # Compare
    for row in current_rows:
        row_code = row.row_code or ""
        row_name = row.row_name or ""
        after_val = float(row.current_period_amount or 0)
        before_val = before_map.get(row_code, 0.0)

        diff = after_val - before_val
        diff_percent = 0.0
        if before_val != 0:
            diff_percent = round((diff / abs(before_val)) * 100, 2)

        if abs(diff) > 0.001:  # Only include rows with actual changes
            changes.append({
                "row_code": row_code,
                "row_name": row_name,
                "before": before_val,
                "after": after_val,
                "diff": round(diff, 2),
                "diff_percent": diff_percent,
            })

    return {
        "execution_id": execution_id,
        "year": execution.year,
        "changes": changes,
        "total_changes": len(changes),
    }


@router.get("/data-health")
async def get_data_health(
    project_id: UUID,
    year: int = Query(..., description="年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """全局数据一致性实时监控 — 数据健康度

    Requirements: 29.1-29.5
    Returns: { score: 0-100, checks: [...] }
    """
    from app.services.data_health_monitor import DataHealthMonitor

    monitor = DataHealthMonitor(db)
    result = await monitor.calculate_health_score(project_id, year)

    return {
        "score": result.score,
        "checks": [
            {
                "check_name": c.check_name,
                "passed": c.passed,
                "status": c.status,
                "details": c.details,
                "suggestion": c.suggestion,
            }
            for c in result.checks
        ],
    }


@router.post("/notes/sync-from-report")
async def sync_notes_from_report(
    project_id: UUID,
    year: int = Query(..., description="年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """同步报表数据到附注

    Requirements: 30.1-30.5
    """
    from app.services.report_note_sync_service import ReportNoteSyncService

    service = ReportNoteSyncService(db)
    result = await service.sync_report_to_notes(project_id, year)
    await db.commit()

    return result


@router.post("/notes/trim-and-sort")
async def trim_and_sort_notes(
    project_id: UUID,
    year: int = Query(..., description="年度"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """附注智能裁剪与排序

    Requirements: 37.1-37.6
    """
    from app.services.note_trim_sort_service import NoteTrimSortService

    service = NoteTrimSortService(db)
    result = await service.trim_and_sort(project_id, year)
    await db.commit()

    return result


@router.post("/retry/{execution_id}")
async def retry_execution(
    project_id: UUID,
    execution_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重试失败步骤

    Requirements: 15.1-15.3
    """
    try:
        execution = await chain_orchestrator.retry_execution(
            db=db,
            project_id=project_id,
            execution_id=execution_id,
        )
        await db.commit()

        return {
            "execution_id": execution.id,
            "status": execution.status,
            "steps": execution.steps,
            "total_duration_ms": execution.total_duration_ms,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        }

    except ChainConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Retry failed for execution %s", execution_id)
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Retry failed: {str(e)}")


# ---------------------------------------------------------------------------
# 批量项目操作（Task 10.4）
# Requirements: 10.1-10.5
# ---------------------------------------------------------------------------

# 独立路由（不带 project_id 前缀）
batch_router = APIRouter(
    prefix="/api/workflow",
    tags=["chain-workflow"],
)


class BatchExecuteRequest(BaseModel):
    """批量执行请求"""
    project_ids: list[str] = Field(..., description="项目 ID 列表")
    year: int = Field(..., description="年度")
    steps: list[str] | None = Field(None, description="指定步骤（空=全部）")


@batch_router.post("/batch-execute")
async def batch_execute(
    body: BatchExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量项目执行全链路

    每个项目独立执行，互不影响。最多同时处理 10 个项目（超过排队）。
    返回批量执行汇总（成功/失败/跳过数）。

    Requirements: 10.1-10.5
    """
    MAX_CONCURRENT = 10
    project_ids = body.project_ids
    year = body.year
    steps = body.steps

    results: list[dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    skipped_count = 0

    # 分批处理（最多 10 个并发）
    for i in range(0, len(project_ids), MAX_CONCURRENT):
        batch = project_ids[i:i + MAX_CONCURRENT]

        for pid_str in batch:
            try:
                pid = UUID(pid_str)
                parsed_steps = (
                    [ChainStep(s) for s in steps] if steps else None
                )

                execution = await chain_orchestrator.execute_full_chain(
                    db=db,
                    project_id=pid,
                    year=year,
                    steps=parsed_steps,
                    force=True,
                    trigger_type="batch",
                )
                await db.commit()

                results.append({
                    "project_id": pid_str,
                    "status": "success",
                    "execution_id": execution.id,
                })
                success_count += 1

            except ChainConflictError:
                results.append({
                    "project_id": pid_str,
                    "status": "skipped",
                    "reason": "Already executing",
                })
                skipped_count += 1
                await db.rollback()

            except Exception as e:
                logger.warning("[BatchExecute] Failed for project %s: %s", pid_str, e)
                results.append({
                    "project_id": pid_str,
                    "status": "failed",
                    "error": str(e),
                })
                failed_count += 1
                await db.rollback()

    return {
        "total": len(project_ids),
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "results": results,
    }
