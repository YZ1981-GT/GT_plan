"""交付件管理中心 API — deliverable-center P0"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session, get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.phase13_models import WordExportDocType, WordExportStatus
from app.models.phase13_schemas import (
    CompletenessResponse,
    DeliverableApprovalRejectRequest,
    DeliverableApprovalResponse,
    DeliverableArchiveRequest,
    DeliverableArchiveResponse,
    DeliverableDTOSchema,
    DeliverableExportRequest,
    DeliverableExportResponse,
    DeliverableListResponse,
    DeliverablePackageRequest,
    DeliverablePackageResponse,
    DeliverableSignRequest,
    DeliverableSignResponse,
    DeliverableUnarchiveRequest,
    DeliverableVersionSchema,
    IntegrityVerifyResponse,
    OnlyOfficeConfigResponse,
    OnlyOfficeHealthResponse,
    ReportBodyLoadTemplateRequest,
    ReportBodyRenderRequest,
    ReportBodyRenderResponse,
    ReportDateComplianceRequest,
    ReportDateComplianceResponse,
    SnapshotStaleResponse,
    VersionCompareRequest,
    VersionCompareResponse,
)
from app.models.report_models import AuditReport, CompanyType, ReportStatus
from app.services.completeness_service import CompletenessService
from app.services.deliverable_permissions import DeliverableAction, can_deliverable
from app.services.deliverable_hash_service import DeliverableHashService
from app.services.deliverable_package_service import DeliverablePackageService
from app.services.deliverable_service import DeliverableService
from app.services.deliverable_snapshot_service import DeliverableSnapshotService
from app.services.onlyoffice_callback_service import OnlyOfficeCallbackService
from app.services.report_body_service import ReportBodyService

router = APIRouter(
    prefix="/api/projects/{project_id}/deliverables",
    tags=["deliverable-center"],
)


def _ensure_task_belongs(task, project_id: UUID) -> None:
    if task.project_id != project_id:
        raise HTTPException(status_code=403, detail="交付物不属于该项目")


async def _is_project_eqcr(db: AsyncSession, user_id: UUID, project_id: UUID) -> bool:
    from app.services.eqcr_workbench_service import EqcrWorkbenchService

    svc = EqcrWorkbenchService(db)
    return await svc._is_user_eqcr_on(user_id, project_id)


async def _notify_deliverable(
    db: AsyncSession,
    *,
    project_id: UUID,
    task_id: UUID,
    doc_type: str,
    notification_type: str,
    recipient_id: UUID | None = None,
    extra: dict | None = None,
) -> None:
    try:
        from app.models.core import Project
        from app.services.notification_service import NotificationService

        project = await db.get(Project, project_id)
        meta = {
            "object_type": "word_export_task",
            "object_id": str(task_id),
            "project_id": str(project_id),
            "project_name": project.name if project else "",
            "doc_type": doc_type,
            **(extra or {}),
        }
        if recipient_id:
            svc = NotificationService(db)
            await svc.send_notification(
                user_id=recipient_id,
                notification_type=notification_type,
                metadata=meta,
            )
    except Exception:
        pass


async def _run_package_job(job_id: UUID) -> None:
    async with async_session() as db:
        try:
            svc = DeliverablePackageService(db)
            await svc.run_package_job(job_id)
            await db.commit()
        except Exception:
            await db.rollback()


async def _guard_action(
    db: AsyncSession,
    user: User,
    project_id: UUID,
    action: DeliverableAction,
    *,
    task_status: str | None = None,
) -> None:
    is_eqcr = await _is_project_eqcr(db, user.id, project_id)
    if not can_deliverable(
        user.role.value,
        action,
        task_status=task_status,
        is_eqcr_assignment=is_eqcr,
    ):
        raise HTTPException(status_code=403, detail="权限不足")


@router.get("/", response_model=DeliverableListResponse)
async def list_deliverables(
    project_id: UUID,
    doc_type: str | None = Query(None),
    status: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    keyword: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _guard_action(db, current_user, project_id, DeliverableAction.list)
    svc = DeliverableService(db)
    dtos = await svc.list_deliverables(
        project_id,
        doc_type=doc_type,
        status=status,
        date_from=date_from,
        date_to=date_to,
        keyword=keyword,
    )
    items = [DeliverableDTOSchema.model_validate(d.__dict__) for d in dtos]
    grouped: dict[str, list[DeliverableDTOSchema]] = {}
    for item in items:
        grouped.setdefault(item.doc_type, []).append(item)
    return DeliverableListResponse(items=items, grouped=grouped)


@router.get("/{task_id}/versions", response_model=list[DeliverableVersionSchema])
async def get_version_chain(
    project_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _guard_action(db, current_user, project_id, DeliverableAction.preview)
    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)
    versions = await svc.get_version_chain(task_id)
    return [DeliverableVersionSchema.model_validate(v) for v in versions]


@router.post("/{task_id}/versions/compare", response_model=VersionCompareResponse)
async def compare_versions(
    project_id: UUID,
    task_id: UUID,
    body: VersionCompareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)
    try:
        result = await svc.compare_versions(task_id, body.version_a, body.version_b)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return VersionCompareResponse(
        version_a=result.version_a,
        version_b=result.version_b,
        exported_at_diff=result.exported_at_diff,
        file_size_diff=result.file_size_diff,
        selected_sections_diff=result.selected_sections_diff,
    )


@router.get("/{task_id}/versions/{version_no}/download")
async def download_version(
    project_id: UUID,
    task_id: UUID,
    version_no: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)
    await _guard_action(
        db, current_user, project_id, DeliverableAction.download, task_status=task.status
    )

    version = await svc.get_version(task_id, version_no)
    if version is None or not version.file_path:
        raise HTTPException(status_code=404, detail="版本文件不存在")

    file_path = Path(version.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在于存储")

    suffix = file_path.suffix.lower()
    media = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if suffix == ".xlsx"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if suffix == ".docx"
        else "application/pdf"
        if suffix == ".pdf"
        else "application/octet-stream"
    )
    return FileResponse(path=str(file_path), filename=file_path.name, media_type=media)


@router.get("/{task_id}/versions/{version_no}/preview-url")
async def preview_version(
    project_id: UUID,
    task_id: UUID,
    version_no: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)

    version = await svc.get_version(task_id, version_no)
    if version is None:
        raise HTTPException(status_code=404, detail="版本不存在")

    if version.html_path and Path(version.html_path).exists():
        return {"preview_type": "html", "url": None, "html_path": version.html_path}

    if version.file_path:
        suffix = Path(version.file_path).suffix.lower()
        if suffix in (".docx", ".pdf"):
            return {
                "preview_type": suffix.lstrip("."),
                "url": f"/api/projects/{project_id}/deliverables/{task_id}/versions/{version_no}/download",
                "html_path": None,
            }

    return {
        "preview_type": "unsupported",
        "url": f"/api/projects/{project_id}/deliverables/{task_id}/versions/{version_no}/download",
        "message": "该格式不支持在线预览，请下载后查看",
    }


@router.post("/report-body/load-template")
async def load_report_body_template(
    project_id: UUID,
    body: ReportBodyLoadTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rbs = ReportBodyService(db)
    template = await rbs.load_body_template(
        body.opinion_type,
        body.company_type,
        include_emphasis=body.include_emphasis
        or body.opinion_type == "unqualified_with_emphasis",
    )
    return {"report_body_json": template}


@router.post("/report-body/render", response_model=ReportBodyRenderResponse)
async def render_report_body(
    project_id: UUID,
    body: ReportBodyRenderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _guard_action(db, current_user, project_id, DeliverableAction.export)
    dsvc = DeliverableService(db)
    rbs = ReportBodyService(db)

    kam_err = None
    template = await rbs.load_body_template(
        body.opinion_type,
        body.company_type,
        include_emphasis=body.include_emphasis
        or body.opinion_type == "unqualified_with_emphasis",
    )
    if body.selected_sections:
        allowed = set(body.selected_sections)
        template["sections"] = [
            s for s in template["sections"] if s.get("section_name") in allowed
        ]

    filled = await rbs.fill_placeholders(template, project_id, body.year)
    if body.prior_period_info:
        filled = rbs.apply_prior_period_section(filled, body.prior_period_info)
    filled["is_pie"] = body.is_pie
    kam_err = rbs.validate_kam(
        filled,
        company_type=body.company_type,
        is_pie=body.is_pie,
        opinion_type=body.opinion_type,
    )

    task, _ = await dsvc.export_or_new_deliverable(
        project_id,
        WordExportDocType.audit_report.value,
        body.company_type,
        current_user.id,
    )
    task.opinion_type = body.opinion_type
    task.company_type = body.company_type
    task.is_pie = body.is_pie
    task.report_body_json = filled
    task.selected_sections = body.selected_sections
    await db.flush()

    html = rbs.render_html(filled)
    out_dir = dsvc._deliverable_dir(project_id, task.id)
    latest = await dsvc._latest_version(task.id)
    next_no = (latest.version_no + 1) if latest else 1
    docx_path = out_dir / f"audit_report_v{next_no}.docx"
    rbs.render_docx(filled, docx_path, watermark=task.status in ("draft", "editing"))

    snapshot_refs = await dsvc.capture_snapshot_refs(
        project_id, body.year, WordExportDocType.audit_report.value
    )

    store = await dsvc.render_and_store(
        task.id,
        docx_path=docx_path,
        html_content=html,
        user_id=current_user.id,
        source_snapshot_refs=snapshot_refs,
        selected_sections=body.selected_sections,
        file_name=docx_path.name,
    )

    # 同步 audit_report.report_body_json
    report = await rbs._audit_svc.get_report(project_id, body.year)
    if report:
        report.report_body_json = filled
        report.is_pie = body.is_pie
    else:
        enum_opinion = rbs._resolve_opinion_enum(body.opinion_type)
        report = AuditReport(
            project_id=project_id,
            year=body.year,
            opinion_type=enum_opinion,
            company_type=CompanyType(body.company_type),
            report_body_json=filled,
            is_pie=body.is_pie,
            status=ReportStatus.draft,
            created_by=current_user.id,
        )
        db.add(report)
    await db.flush()

    await _advance_to_editing(dsvc, task.id)
    await db.commit()

    return ReportBodyRenderResponse(
        task_id=task.id,
        version_no=store.version.version_no,
        download_url=store.download_url,
        html_preview=html,
        platform_persist_failed=store.platform_persist_failed,
        report_body_json=filled,
        validation_warning=kam_err,
    )


async def _advance_to_editing(dsvc: DeliverableService, task_id: UUID) -> None:
    refreshed = await dsvc.get_task(task_id)
    if refreshed and refreshed.status == WordExportStatus.draft.value:
        try:
            await dsvc.update_status(task_id, WordExportStatus.generating.value)
            await dsvc.update_status(task_id, WordExportStatus.generated.value)
            await dsvc.update_status(task_id, WordExportStatus.editing.value)
        except ValueError:
            pass
    elif refreshed and refreshed.status == WordExportStatus.generated.value:
        try:
            await dsvc.update_status(task_id, WordExportStatus.editing.value)
        except ValueError:
            pass


@router.post("/disclosure-notes/render", response_model=DeliverableExportResponse)
async def render_disclosure_notes(
    project_id: UUID,
    body: DeliverableExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """选择性导出附注 Word 并双路径存储"""
    from app.services.note_word_exporter import NoteWordExporter

    await _guard_action(db, current_user, project_id, DeliverableAction.export)
    dsvc = DeliverableService(db)
    task, _ = await dsvc.export_or_new_deliverable(
        project_id,
        WordExportDocType.disclosure_notes.value,
        body.template_type,
        current_user.id,
    )
    task.selected_sections = body.selected_sections
    await db.flush()

    exporter = NoteWordExporter(db)
    buf = await exporter.export(
        project_id,
        body.year,
        template_type=body.template_type,
        sections=body.selected_sections,
    )
    file_name = f"disclosure_notes_{body.year}.docx"
    snapshot_refs = await dsvc.capture_snapshot_refs(
        project_id, body.year, WordExportDocType.disclosure_notes.value
    )
    store = await dsvc.render_and_store(
        task.id,
        docx_bytes=buf.getvalue(),
        user_id=current_user.id,
        source_snapshot_refs=snapshot_refs,
        selected_sections=body.selected_sections,
        file_name=file_name,
    )
    await _advance_to_editing(dsvc, task.id)
    await db.commit()
    return DeliverableExportResponse(
        task_id=task.id,
        version_no=store.version.version_no,
        download_url=store.download_url,
        platform_persist_failed=store.platform_persist_failed,
        file_name=file_name,
    )


@router.post("/financial-reports/render", response_model=DeliverableExportResponse)
async def render_financial_reports(
    project_id: UUID,
    body: DeliverableExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """选择性导出财务报表 Excel 并双路径存储"""
    from app.services.report_excel_exporter import ReportExcelExporter

    await _guard_action(db, current_user, project_id, DeliverableAction.export)
    dsvc = DeliverableService(db)
    task, _ = await dsvc.export_or_new_deliverable(
        project_id,
        WordExportDocType.financial_report.value,
        body.template_type,
        current_user.id,
    )
    task.selected_sections = body.selected_sections
    await db.flush()

    exporter = ReportExcelExporter(db)
    buf = await exporter.export(
        project_id,
        body.year,
        report_types=body.report_types,
    )
    file_name = f"financial_reports_{body.year}.xlsx"
    snapshot_refs = await dsvc.capture_snapshot_refs(
        project_id, body.year, WordExportDocType.financial_report.value
    )
    store = await dsvc.render_and_store(
        task.id,
        docx_bytes=buf.getvalue(),
        user_id=current_user.id,
        source_snapshot_refs=snapshot_refs,
        selected_sections=body.selected_sections or body.report_types,
        file_name=file_name,
    )
    await _advance_to_editing(dsvc, task.id)
    await db.commit()
    return DeliverableExportResponse(
        task_id=task.id,
        version_no=store.version.version_no,
        download_url=store.download_url,
        platform_persist_failed=store.platform_persist_failed,
        file_name=file_name,
    )


@router.get("/completeness", response_model=CompletenessResponse)
async def check_completeness(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _guard_action(db, current_user, project_id, DeliverableAction.list)
    result = await CompletenessService(db).check(project_id, year)
    return CompletenessResponse(
        passed=result.passed,
        missing_doc_types=result.missing_doc_types,
        missing_financial_reports=result.missing_financial_reports,
        has_confirmed=result.has_confirmed,
        trio_consistent=result.trio_consistent,
        trio_message=result.trio_message,
        warnings=result.warnings,
    )


@router.get("/{task_id}/snapshot-stale", response_model=SnapshotStaleResponse)
async def check_snapshot_stale(
    project_id: UUID,
    task_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _guard_action(db, current_user, project_id, DeliverableAction.preview)
    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)

    stale = await DeliverableSnapshotService(db).check_stale(task, year)
    return SnapshotStaleResponse(
        stale=stale.stale,
        bound_tb_hash=stale.bound_tb_hash,
        current_tb_hash=stale.current_tb_hash,
        message=stale.message,
    )


@router.post("/{task_id}/sign", response_model=DeliverableSignResponse)
async def sign_deliverable(
    project_id: UUID,
    task_id: UUID,
    body: DeliverableSignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)
    await _guard_action(
        db, current_user, project_id, DeliverableAction.sign, task_status=task.status
    )
    try:
        signed = await svc.sign(task_id, current_user.id, body.sign_type, body.year)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return DeliverableSignResponse(
        task_id=signed.id,
        status=signed.status,
        signed_by=signed.signed_by,
        signed_at=signed.signed_at,
        sign_type=signed.sign_type,
    )


@router.post("/report-body/report-date-compliance", response_model=ReportDateComplianceResponse)
async def report_date_compliance(
    project_id: UUID,
    body: ReportDateComplianceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _guard_action(db, current_user, project_id, DeliverableAction.list)
    rbs = ReportBodyService(db)
    result = await rbs.check_report_date_compliance(
        project_id, body.year, body.report_date
    )
    return ReportDateComplianceResponse(**result)


@router.post("/{task_id}/submit-approval", response_model=DeliverableApprovalResponse)
async def submit_approval(
    project_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)
    await _guard_action(
        db, current_user, project_id, DeliverableAction.export, task_status=task.status
    )
    try:
        updated = await svc.submit_for_approval(task_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return DeliverableApprovalResponse(
        task_id=updated.id,
        status=updated.status,
        approval_by=updated.approval_by,
        approval_at=updated.approval_at,
        reject_reason=updated.reject_reason,
    )


@router.post("/{task_id}/approve", response_model=DeliverableApprovalResponse)
async def approve_deliverable(
    project_id: UUID,
    task_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)
    await _guard_action(
        db, current_user, project_id, DeliverableAction.approve, task_status=task.status
    )
    try:
        updated = await svc.approve(task_id, current_user.id, year)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await _notify_deliverable(
        db,
        project_id=project_id,
        task_id=task_id,
        doc_type=task.doc_type,
        notification_type="deliverable_approval_done",
        recipient_id=task.created_by,
    )
    await db.commit()
    return DeliverableApprovalResponse(
        task_id=updated.id,
        status=updated.status,
        approval_by=updated.approval_by,
        approval_at=updated.approval_at,
        reject_reason=updated.reject_reason,
    )


@router.post("/{task_id}/reject", response_model=DeliverableApprovalResponse)
async def reject_deliverable(
    project_id: UUID,
    task_id: UUID,
    body: DeliverableApprovalRejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)
    await _guard_action(
        db, current_user, project_id, DeliverableAction.approve, task_status=task.status
    )
    try:
        updated = await svc.reject(task_id, current_user.id, body.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await _notify_deliverable(
        db,
        project_id=project_id,
        task_id=task_id,
        doc_type=task.doc_type,
        notification_type="deliverable_approval_rejected",
        recipient_id=task.created_by,
        extra={"reason": body.reason},
    )
    await db.commit()
    return DeliverableApprovalResponse(
        task_id=updated.id,
        status=updated.status,
        approval_by=updated.approval_by,
        approval_at=updated.approval_at,
        reject_reason=updated.reject_reason,
    )


@router.post("/archive", response_model=DeliverableArchiveResponse)
async def archive_deliverables(
    project_id: UUID,
    body: DeliverableArchiveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _guard_action(db, current_user, project_id, DeliverableAction.archive)
    svc = DeliverableService(db)
    try:
        count = await svc.archive_project_deliverables(
            project_id, current_user.id, body.year, force=body.force
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return DeliverableArchiveResponse(archived_count=count)


@router.post("/{task_id}/unarchive", response_model=DeliverableApprovalResponse)
async def unarchive_deliverable(
    project_id: UUID,
    task_id: UUID,
    body: DeliverableUnarchiveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role.value != "admin":
        raise HTTPException(status_code=403, detail="仅 admin 可解除归档")
    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)
    try:
        updated = await svc.unarchive(task_id, current_user.id, body.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return DeliverableApprovalResponse(
        task_id=updated.id,
        status=updated.status,
        approval_by=updated.approval_by,
        approval_at=updated.approval_at,
        reject_reason=updated.reject_reason,
    )


@router.get("/{task_id}/integrity-verify", response_model=IntegrityVerifyResponse)
async def verify_integrity(
    project_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _guard_action(db, current_user, project_id, DeliverableAction.preview)
    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)

    result = await DeliverableHashService(db).verify_task_integrity(task_id)
    return IntegrityVerifyResponse(
        valid=result.valid,
        tampered_versions=result.tampered_versions,
        checked_count=result.checked_count,
        message=result.message,
    )


@router.post("/package", response_model=DeliverablePackageResponse)
async def create_package(
    project_id: UUID,
    body: DeliverablePackageRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _guard_action(db, current_user, project_id, DeliverableAction.export)
    pkg = DeliverablePackageService(db)
    job_id, warnings = await pkg.create_package_job(
        project_id,
        body.year,
        current_user.id,
        ignore_incomplete=body.ignore_incomplete,
    )
    await db.commit()
    background_tasks.add_task(_run_package_job, job_id)
    return DeliverablePackageResponse(job_id=job_id, warnings=warnings)


@router.get("/package/{job_id}/download")
async def download_package(
    project_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _guard_action(db, current_user, project_id, DeliverableAction.download)
    from app.services.export_job_service import ExportJobService

    job_svc = ExportJobService(db)
    job = await job_svc.get_job(job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="打包任务不存在")
    zip_path = (job.payload or {}).get("zip_path")
    if not zip_path:
        raise HTTPException(status_code=404, detail="打包文件尚未就绪")
    path = Path(zip_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="打包文件不存在")
    return FileResponse(path, filename=path.name, media_type="application/zip")


@router.get(
    "/onlyoffice/config/{task_id}/{version_no}",
    response_model=OnlyOfficeConfigResponse,
)
async def onlyoffice_config(
    project_id: UUID,
    task_id: UUID,
    version_no: int,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)
    await _guard_action(
        db, current_user, project_id, DeliverableAction.edit, task_status=task.status
    )

    version = await svc.get_version(task_id, version_no)
    if version is None or not version.file_path:
        raise HTTPException(status_code=404, detail="版本文件不存在")

    oos = OnlyOfficeCallbackService(db)
    if not oos.enabled:
        raise HTTPException(status_code=503, detail="OnlyOffice 集成未启用")

    base = settings.ONLYOFFICE_CALLBACK_BASE or f"http://localhost:9980"
    download_url = (
        f"{base}/api/projects/{project_id}/deliverables/"
        f"{task_id}/versions/{version_no}/download"
    )
    callback_url = (
        f"{base}/api/projects/{project_id}/deliverables/"
        f"onlyoffice/callback/{task_id}?year={year}"
    )
    try:
        cfg = oos.build_editor_config(
            task,
            version,
            current_user,
            download_url=download_url,
            callback_url=callback_url,
        )
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return OnlyOfficeConfigResponse(**cfg)


@router.get("/onlyoffice/health", response_model=OnlyOfficeHealthResponse)
async def onlyoffice_health(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _guard_action(db, current_user, project_id, DeliverableAction.preview)
    oos = OnlyOfficeCallbackService(db)
    if not oos.enabled:
        return OnlyOfficeHealthResponse(
            available=False,
            enabled=False,
            message="OnlyOffice JWT 未配置，在线编辑已降级为只读预览",
        )
    ok = await oos.health_check()
    return OnlyOfficeHealthResponse(
        available=ok,
        enabled=True,
        message=None if ok else "OnlyOffice 服务不可用，预览/下载仍可使用",
    )


@router.post("/onlyoffice/callback/{task_id}")
async def onlyoffice_callback(
    project_id: UUID,
    task_id: UUID,
    request: Request,
    year: int = Query(...),
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    body = await request.json()
    oos = OnlyOfficeCallbackService(db)
    if not oos.enabled:
        raise HTTPException(status_code=503, detail="OnlyOffice 集成未启用")

    if not oos.verify_callback_jwt(authorization, body):
        raise HTTPException(status_code=401, detail="OnlyOffice callback JWT 校验失败")

    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)

    creator_id = task.created_by
    result = await oos.handle_callback(
        task_id, body, user_id=creator_id, year=year
    )
    await db.commit()
    return result


@router.get("/report-body/preview-html")
async def preview_report_body_html(
    project_id: UUID,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rbs = ReportBodyService(db)
    report = await rbs._audit_svc.get_report(project_id, year)
    if report is None or not report.report_body_json:
        raise HTTPException(status_code=404, detail="报告正文尚未生成")
    html = rbs.render_html(report.report_body_json)
    return HTMLResponse(content=html)
