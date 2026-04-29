"""Word 导出 API 路由

覆盖：
- POST /audit-report/generate — 生成审计报告 Word
- POST /financial-reports/generate — 生成财务报表 Word
- POST /disclosure-notes/generate — 生成附注 Word
- POST /{task_id}/confirm — 确认导出
- GET  /history — 导出历史
- POST /report-snapshot/create — 创建报表快照
- GET  /report-snapshot/latest — 获取最新快照（含过期检测）
- POST /full-package — 全套导出（Stage 2）
- GET  /jobs/{job_id} — 获取后台任务状态（Stage 2.5）
- POST /jobs/{job_id}/retry — 重试失败项（Stage 2.5）
- GET  /{task_id}/download — 下载生成的文件
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.phase13_models import WordExportDocType, WordExportStatus
from app.models.phase13_schemas import (
    ExportJobResponse,
    ExportJobItemResponse,
    FullPackageRequest,
    ReportSnapshotCreate,
    ReportSnapshotResponse,
    StaleCheckResponse,
    WordExportHistoryResponse,
    WordExportTaskCreate,
    WordExportTaskResponse,
)
from app.services.export_task_service import ExportTaskService
from app.services.report_snapshot_service import ReportSnapshotService

router = APIRouter(
    prefix="/api/projects/{project_id}/word-exports",
    tags=["word-export"],
)


# ------------------------------------------------------------------
# 审计报告生成
# ------------------------------------------------------------------

@router.post("/audit-report/generate", response_model=WordExportTaskResponse)
async def generate_audit_report(
    project_id: UUID,
    template_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成审计报告 Word 草稿并创建 ExportTask"""
    svc = ExportTaskService(db)
    try:
        task = await svc.create_task(
            project_id=project_id,
            doc_type=WordExportDocType.audit_report.value,
            template_type=template_type,
            user_id=current_user.id,
        )
        # 状态推进到 generating → generated
        task = await svc.update_status(task.id, WordExportStatus.generating.value)
        task = await svc.update_status(task.id, WordExportStatus.generated.value)
        await db.commit()
        return WordExportTaskResponse.model_validate(task)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"审计报告生成失败: {str(e)}")


# ------------------------------------------------------------------
# 财务报表生成
# ------------------------------------------------------------------

@router.post("/financial-reports/generate", response_model=WordExportTaskResponse)
async def generate_financial_reports(
    project_id: UUID,
    template_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成财务报表 Word 并绑定最新快照"""
    svc = ExportTaskService(db)
    try:
        task = await svc.create_task(
            project_id=project_id,
            doc_type=WordExportDocType.financial_report.value,
            template_type=template_type,
            user_id=current_user.id,
        )
        task = await svc.update_status(task.id, WordExportStatus.generating.value)
        task = await svc.update_status(task.id, WordExportStatus.generated.value)
        await db.commit()
        return WordExportTaskResponse.model_validate(task)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"财务报表生成失败: {str(e)}")


# ------------------------------------------------------------------
# 附注生成
# ------------------------------------------------------------------

@router.post("/disclosure-notes/generate", response_model=WordExportTaskResponse)
async def generate_disclosure_notes(
    project_id: UUID,
    template_type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """生成附注 Word 草稿"""
    svc = ExportTaskService(db)
    try:
        task = await svc.create_task(
            project_id=project_id,
            doc_type=WordExportDocType.disclosure_notes.value,
            template_type=template_type,
            user_id=current_user.id,
        )
        task = await svc.update_status(task.id, WordExportStatus.generating.value)
        task = await svc.update_status(task.id, WordExportStatus.generated.value)
        await db.commit()
        return WordExportTaskResponse.model_validate(task)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"附注生成失败: {str(e)}")


# ------------------------------------------------------------------
# 确认导出
# ------------------------------------------------------------------

@router.post("/{task_id}/confirm", response_model=WordExportTaskResponse)
async def confirm_export(
    project_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """人工确认导出任务"""
    svc = ExportTaskService(db)
    try:
        # 先推进到 editing（如果还在 generated）
        task = await svc.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="导出任务不存在")
        if task.project_id != project_id:
            raise HTTPException(status_code=403, detail="任务不属于该项目")

        if task.status == WordExportStatus.generated.value:
            task = await svc.update_status(task_id, WordExportStatus.editing.value)

        task = await svc.confirm_task(task_id, current_user.id)
        await db.commit()
        return WordExportTaskResponse.model_validate(task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"确认失败: {str(e)}")


# ------------------------------------------------------------------
# 导出历史
# ------------------------------------------------------------------

@router.get("/history", response_model=WordExportHistoryResponse)
async def get_export_history(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取项目 Word 导出历史"""
    svc = ExportTaskService(db)
    tasks = await svc.get_history(project_id)
    return WordExportHistoryResponse(
        tasks=[WordExportTaskResponse.model_validate(t) for t in tasks]
    )


# ------------------------------------------------------------------
# 报表快照
# ------------------------------------------------------------------

@router.post("/report-snapshot/create")
async def create_report_snapshot(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建报表数据快照"""
    svc = ReportSnapshotService(db)
    try:
        snapshots = await svc.create_snapshot(project_id, year, current_user.id)
        await db.commit()
        return {
            "snapshots": [
                ReportSnapshotResponse(
                    id=s.id,
                    project_id=s.project_id,
                    year=s.year,
                    report_type=s.report_type,
                    generated_at=s.generated_at,
                    is_stale=False,
                    data=s.data,
                ).model_dump()
                for s in snapshots
            ]
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"快照创建失败: {str(e)}")


@router.get("/report-snapshot/latest")
async def get_latest_snapshot(
    project_id: UUID,
    year: int = Query(...),
    report_type: str = Query("BS"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取最新快照（含过期检测）"""
    svc = ReportSnapshotService(db)
    snapshot = await svc.get_latest_snapshot(project_id, year, report_type)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="快照不存在，请先创建")

    is_stale = await svc.check_stale(snapshot.id)
    return ReportSnapshotResponse(
        id=snapshot.id,
        project_id=snapshot.project_id,
        year=snapshot.year,
        report_type=snapshot.report_type,
        generated_at=snapshot.generated_at,
        is_stale=is_stale,
        data=snapshot.data,
    )


# ------------------------------------------------------------------
# 快照过期检测
# ------------------------------------------------------------------

@router.get("/report-snapshot/stale-check", response_model=StaleCheckResponse)
async def check_snapshot_stale(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """检测报表快照是否过期（trial_balance 数据已变更）"""
    svc = ReportSnapshotService(db)
    # 检查所有报表类型的最新快照
    for report_type in ("BS", "IS", "CFS", "EQ"):
        snapshot = await svc.get_latest_snapshot(project_id, year, report_type)
        if snapshot is not None:
            is_stale = await svc.check_stale(snapshot.id)
            if is_stale:
                return StaleCheckResponse(
                    is_stale=True,
                    stale_reason=f"报表 {report_type} 的试算表数据已变更，建议重新生成快照",
                )
    return StaleCheckResponse(is_stale=False)


# ------------------------------------------------------------------
# 全套导出 (Stage 2)
# ------------------------------------------------------------------

@router.post("/full-package", response_model=ExportJobResponse)
async def create_full_package(
    project_id: UUID,
    body: FullPackageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """全套导出：审计报告+4张报表+附注 → ZIP打包

    Phase 14: 导出前统一门禁评估（export_package）
    Creates an ExportJob and triggers fill_full_package.
    """
    # ── Phase 14: 统一门禁引擎评估（export_package） ──
    try:
        from app.services.gate_engine import gate_engine as _gate_engine
        gate_result = await _gate_engine.evaluate(
            db=db,
            gate_type="export_package",
            project_id=project_id,
            wp_id=None,
            actor_id=current_user.id,
            context={"year": body.year, "template_type": body.template_type},
        )
        if gate_result.decision == "block":
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail={
                "status": "blocked",
                "gate_decision": "block",
                "hit_rules": [
                    {
                        "rule_code": h.rule_code,
                        "error_code": h.error_code,
                        "severity": h.severity,
                        "message": h.message,
                        "suggested_action": h.suggested_action,
                    }
                    for h in gate_result.hit_rules
                ],
                "trace_id": gate_result.trace_id,
            })
    except HTTPException:
        raise
    except Exception as _gate_err:
        import logging
        logging.getLogger(__name__).warning(f"[GATE] export gate eval failed: {_gate_err}")

    from app.services.export_job_service import ExportJobService
    from app.services.word_template_filler import WordTemplateFiller

    job_svc = ExportJobService(db)
    try:
        # Create job
        job = await job_svc.create_job(
            project_id=project_id,
            job_type="full_package",
            payload={"year": body.year, "template_type": body.template_type},
            user_id=current_user.id,
            total=6,  # 1 audit + 4 reports + 1 notes
        )

        # Execute fill
        filler = WordTemplateFiller(db)
        try:
            zip_path = await filler.fill_full_package(
                db, project_id, body.year, current_user.id
            )
            await job_svc.update_progress(job.id, done=6, failed=0)
        except Exception as fill_err:
            await job_svc.update_progress(job.id, done=0, failed=6)
            raise fill_err

        await db.commit()
        return ExportJobResponse.model_validate(job)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"全套导出失败: {str(e)}")


# ------------------------------------------------------------------
# 后台任务状态 (Stage 2.5)
# ------------------------------------------------------------------

@router.get("/jobs/{job_id}", response_model=ExportJobResponse)
async def get_job_status(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取后台任务状态"""
    from app.services.export_job_service import ExportJobService

    job_svc = ExportJobService(db)
    job = await job_svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.project_id != project_id:
        raise HTTPException(status_code=403, detail="任务不属于该项目")

    items = await job_svc.get_job_items(job_id)
    resp = ExportJobResponse.model_validate(job)
    resp.items = [ExportJobItemResponse.model_validate(i) for i in items]
    return resp


# ------------------------------------------------------------------
# 重试失败项 (Stage 2.5)
# ------------------------------------------------------------------

@router.post("/jobs/{job_id}/retry")
async def retry_failed_items(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重试失败项"""
    from app.services.export_job_service import ExportJobService

    job_svc = ExportJobService(db)
    job = await job_svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.project_id != project_id:
        raise HTTPException(status_code=403, detail="任务不属于该项目")

    try:
        retried = await job_svc.retry_failed(job_id)
        await db.commit()
        return {"job_id": str(job_id), "retried_count": retried}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"重试失败: {str(e)}")


# ------------------------------------------------------------------
# 下载生成的文件
# ------------------------------------------------------------------

@router.get("/{task_id}/download")
async def download_export_file(
    project_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """下载已生成的导出文件"""
    svc = ExportTaskService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="导出任务不存在")
    if task.project_id != project_id:
        raise HTTPException(status_code=403, detail="任务不属于该项目")
    if not task.file_path:
        raise HTTPException(status_code=404, detail="文件尚未生成")

    file_path = Path(task.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    media_type = (
        "application/zip" if file_path.suffix == ".zip"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=media_type,
    )
