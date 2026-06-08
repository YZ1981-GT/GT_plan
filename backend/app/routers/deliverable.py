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
import sqlalchemy as sa
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
    OptionalSectionSchema,
    ReportBodyConfirmRequest,
    ReportBodyConfirmResponse,
    ReportBodyLoadTemplateRequest,
    ReportBodyPreviewRequest,
    ReportBodyPreviewResponse,
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
from app.services.report_body_service import ReportBodyService, should_watermark

import logging

logger = logging.getLogger(__name__)

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
        from app.services.notification_types import NOTIFICATION_META

        if not recipient_id:
            return

        project = await db.get(Project, project_id)
        project_name = project.name if project else ""
        meta = {
            "object_type": "word_export_task",
            "object_id": str(task_id),
            "project_id": str(project_id),
            "project_name": project_name,
            "doc_type": doc_type,
            **(extra or {}),
        }

        template = NOTIFICATION_META.get(notification_type, {})
        title = template.get("title_template", "交付物审批通知")
        content_template = template.get("content_template", "")
        fmt_args = {
            "project_name": project_name,
            "doc_type": doc_type,
            "reason": (extra or {}).get("reason", ""),
        }
        try:
            content = content_template.format(**fmt_args) if content_template else ""
        except (KeyError, IndexError):
            content = content_template

        svc = NotificationService(db)
        await svc.send_notification(
            user_id=recipient_id,
            notification_type=notification_type,
            title=title,
            content=content,
            metadata=meta,
        )
    except Exception:
        logger.warning(
            "[DELIVERABLE] notification send failed (non-blocking): type=%s task=%s",
            notification_type,
            task_id,
        )


async def _notify_approvers(
    db: AsyncSession,
    *,
    project_id: UUID,
    task_id: UUID,
    doc_type: str,
    exclude_user_id: UUID | None = None,
) -> None:
    """提交审批时通知项目经理/合伙人（站内消息，需求 7.4）"""
    try:
        from app.models.base import ProjectUserRole
        from app.models.core import ProjectUser

        result = await db.execute(
            sa.select(ProjectUser.user_id).where(
                ProjectUser.project_id == project_id,
                ProjectUser.is_deleted == False,  # noqa: E712
                ProjectUser.role.in_(
                    [ProjectUserRole.manager, ProjectUserRole.partner]
                ),
            )
        )
        approver_ids = [row[0] for row in result.all()]
    except Exception:
        approver_ids = []

    for approver_id in approver_ids:
        if exclude_user_id and approver_id == exclude_user_id:
            continue
        await _notify_deliverable(
            db,
            project_id=project_id,
            task_id=task_id,
            doc_type=doc_type,
            notification_type="deliverable_approval_submitted",
            recipient_id=approver_id,
        )


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


@router.post("/report-body/preview", response_model=ReportBodyPreviewResponse)
async def preview_report_body(
    project_id: UUID,
    body: ReportBodyPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """报告正文两阶段生成 — preview 阶段（design §11 / §4）。

    解析模板 → copy → 替换占位符 → 扫描 OPT 段落，写 ``fill_preview_sessions``
    会话行（不落库交付件）。前端据此弹出 OptionalSectionDialog 供用户勾选，
    随后调用 ``/report-body/confirm`` 完成入库。

    铁律：TemplateFillService 仅 flush，router 必须 commit 以持久化 session
    供后续 confirm 请求读取。
    """
    from app.services.template_fill_service import TemplateFillService

    await _guard_action(db, current_user, project_id, DeliverableAction.export)
    svc = TemplateFillService(db)
    try:
        result = await svc.preview_report_body(
            project_id,
            body.year,
            opinion_type=body.opinion_type,
            company_subtype=body.company_subtype,
            template_variant=body.template_variant,
            user_id=current_user.id,
        )
    except ValueError as e:
        # 模板缺失 → 422（请求合法但所需资源不可用）
        raise HTTPException(status_code=422, detail=str(e)) from e
    await db.commit()
    return ReportBodyPreviewResponse(
        preview_session_id=result.preview_session_id,
        optional_sections=[
            OptionalSectionSchema(
                section_id=v.section_id,
                description=v.description,
                preview=v.preview,
                default_keep=v.default_keep,
                group=v.group,
            )
            for v in result.optional_sections
        ],
        missing_fields=result.missing_fields,
        template_version=result.template_version,
        company_subtype_resolved=result.company_subtype_resolved,
    )


@router.post("/report-body/confirm", response_model=ReportBodyConfirmResponse)
async def confirm_report_body(
    project_id: UUID,
    body: ReportBodyConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """报告正文两阶段生成 — confirm 阶段（design §11 / §4）。

    载入 preview 会话（校验未过期 + 归属当前用户）→ 应用 OPT 勾选 →
    保存 guidance 副本 → 剥除 NOTE → DeliverableService 入库（版本递增）→
    更新 ``audit_report.report_body_json`` → 删除会话。

    铁律：TemplateFillService 仅 flush，router 在成功后 commit 保证原子。
    错误映射：会话不存在/过期 → 404；归属不匹配（他人会话）→ 403；
    模板/工作副本缺失 → 422。
    """
    from app.services.template_fill_service import TemplateFillService

    await _guard_action(db, current_user, project_id, DeliverableAction.export)
    svc = TemplateFillService(db)
    try:
        result = await svc.confirm_report_body(
            project_id,
            body.year,
            preview_session_id=body.preview_session_id,
            optional_sections=body.optional_sections,
            user_id=current_user.id,
        )
    except ValueError as e:
        msg = str(e)
        if "不属于当前用户" in msg or "与项目不匹配" in msg:
            raise HTTPException(status_code=403, detail=msg) from e
        if "不存在" in msg or "已过期" in msg or "缺失" in msg:
            raise HTTPException(status_code=404, detail=msg) from e
        raise HTTPException(status_code=422, detail=msg) from e
    await db.commit()
    return ReportBodyConfirmResponse(
        task_id=result.task_id,
        version_no=result.version_no,
        download_url=result.download_url,
        report_body_json=result.report_body_json,
        validation_warning=result.validation_warning,
    )


@router.post("/report-body/render", response_model=ReportBodyRenderResponse)
async def render_report_body(
    project_id: UUID,
    body: ReportBodyRenderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """[DEPRECATED — 旧单阶段路径] 渲染并存储审计报告正文。

    .. deprecated::
        本路由是 ``ReportBodyService`` JSON 段落主源的单阶段（render-once）
        legacy 路径，已被两阶段 ``/report-body/preview`` + ``/report-body/confirm``
        （TemplateFillService Word 模板主源）取代。

        迁移期保留以兼容旧前端；``USE_TEMPLATE_FILL_SERVICE=false`` 时仍为默认
        生成路径。**勿在此基础上新增功能**。移除由 task 17 处理
        （`USE_TEMPLATE_FILL_SERVICE` 默认改 true 后限制/下线本路由）。
    """
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
    rbs.render_docx(filled, docx_path, watermark=should_watermark(task.status))

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

    from app.models.core import Project
    from app.services.note_section_catalog import normalize_report_scope

    proj_row = (
        await db.execute(
            sa.select(Project.report_scope).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()

    exporter = NoteWordExporter(db)
    # 附注导出模式灰度（task 10.4）：
    #   - body.mode 显式指定 "template"/"programmatic" → 直接使用
    #   - 否则跟随 settings.USE_TEMPLATE_FILL_SERVICE（默认 False → programmatic）
    # 生产默认保持 programmatic；切换 template 为默认需人工格式抽检（task 18）。
    from app.core.config import settings

    if body.mode in ("template", "programmatic"):
        export_mode = body.mode
    else:
        export_mode = "template" if settings.USE_TEMPLATE_FILL_SERVICE else "programmatic"

    buf = await exporter.export(
        project_id,
        body.year,
        template_type=body.template_type,
        report_scope=normalize_report_scope(proj_row if isinstance(proj_row, str) else None),
        sections=body.selected_sections,
        mode=export_mode,
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
    await _notify_approvers(
        db,
        project_id=project_id,
        task_id=task_id,
        doc_type=task.doc_type,
        exclude_user_id=current_user.id,
    )
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

    base = settings.ONLYOFFICE_CALLBACK_BASE or "http://host.docker.internal:9980"
    # 生成签名下载 URL（OnlyOffice 不携带 Bearer header，需免认证端点）
    expires = int(__import__('time').time()) + 600  # 10 分钟有效
    sig = _sign_download_url(project_id, task_id, version_no, expires)
    download_url = (
        f"{base}/api/projects/{project_id}/deliverables/"
        f"{task_id}/versions/{version_no}/signed-download"
        f"?expires={expires}&sig={sig}"
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
        # 需求 29.2：伪造回调企图写入安全日志后拒绝
        await oos.write_security_log(
            task_id,
            project_id=project_id,
            reason="callback JWT 校验失败",
        )
        await db.commit()
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


@router.delete("/{task_id}")
async def delete_deliverable(
    project_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除交付物（仅 draft/editing 态且非归档可删）"""
    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)
    await _guard_action(
        db, current_user, project_id, DeliverableAction.export, task_status=task.status
    )
    # 仅 draft/editing/generated 态可删除；confirmed/signed/archived 不允许
    if task.status in ("confirmed", "signed", "archived"):
        raise HTTPException(status_code=400, detail="已确认/已签章/已归档的交付物不可删除")
    try:
        await svc.delete_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return {"message": "交付物已删除"}


# ── OnlyOffice 免认证签名下载（document.url 不支持 Bearer header）────────────
import hashlib
import hmac
import time as _time


def _sign_download_url(project_id: UUID, task_id: UUID, version_no: int, expires: int) -> str:
    """生成 HMAC 签名 token（用于 OnlyOffice document.url 免 auth 下载）"""
    secret = (settings.JWT_SECRET_KEY or "deliverable-download-secret").encode()
    payload = f"{project_id}:{task_id}:{version_no}:{expires}"
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return sig


def _verify_download_sig(project_id: UUID, task_id: UUID, version_no: int, expires: int, sig: str) -> bool:
    """验证签名（防伪造 + 检查过期）"""
    if int(_time.time()) > expires:
        return False
    secret = (settings.JWT_SECRET_KEY or "deliverable-download-secret").encode()
    payload = f"{project_id}:{task_id}:{version_no}:{expires}"
    expected = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()[:32]
    return hmac.compare_digest(sig, expected)


@router.get("/{task_id}/versions/{version_no}/signed-download")
async def signed_download_version(
    project_id: UUID,
    task_id: UUID,
    version_no: int,
    expires: int = Query(...),
    sig: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """OnlyOffice 专用免认证下载（通过 HMAC 签名验证，10 分钟有效）"""
    if not _verify_download_sig(project_id, task_id, version_no, expires, sig):
        raise HTTPException(status_code=403, detail="签名无效或已过期")

    svc = DeliverableService(db)
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="交付物不存在")
    _ensure_task_belongs(task, project_id)

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
