"""附注正文上传 / 知识库解析与原子批量应用 router。

spec: disclosure-note-doc-upload-and-batch-fill Task 20 / 21 / 25 / 33（第二轮复盘 R-01）

路径：``/api/projects/{project_id}/disclosure-note-text-sections``（readonly）
    ``/api/projects/{project_id}/disclosure-note-import/parse-upload|parse-knowledge``（edit）
    ``/api/projects/{project_id}/disclosure-note-text-batch/preview|apply``（edit）
    ``/api/projects/{project_id}/disclosure-note-text-batch/sources``（readonly，各章最近一次批量写入来源）
注册：``router_registry/report.py``

写入口门禁与附注其余写端点同序：项目 edit（含归档 423）→ 操作 ``note:edit`` → 合并锁 423。
来源可信度裁定在 ``note_text_batch_flow``；本文件只做鉴权、线程池与错误映射。
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_project_access
from app.services.note_edit_gate import require_note_edit_access
from app.models.core import User
from app.models.note_content_template_schemas import BatchApplyRequest, BatchPreviewRequest, ParseKnowledgeRequest
from app.services.disclosure_mutation_coordinator import DisclosureMutationCoordinator, mutation_fingerprint
from app.services.note_document_parser import MAX_UPLOAD_BYTES, ParseError
from app.services.note_text_batch_apply import ApplyError, apply_batch, build_note_saved_events, lock_target_notes
from app.services.note_text_batch_flow import (
    SourceError,
    compute_preview,
    knowledge_source_payload,
    parse_upload_bytes,
    resolve_source,
    upload_source_payload,
)
from app.services.note_text_batch_service import ManualMappingError, load_target_sections
from app.services.note_text_batch_sources import latest_note_sources

router = APIRouter()

MUTATION_ID_HEADER = "X-Mutation-Id"
_APPLY_STATUS = {"NOTE_NOT_FOUND": 404, "NOTE_BATCH_STALE_PREVIEW": 409, "PREVIEW_DIGEST_MISMATCH": 409}
_PARSE_STATUS = {"FILE_TOO_LARGE": 413, "DOCX_ZIP_LIMIT": 413}


def _http_error(err: Exception) -> HTTPException:
    if isinstance(err, ApplyError):
        detail: dict[str, Any] = {"error_code": err.code, "message": err.message}
        if err.stale_notes:
            detail["stale_notes"] = err.stale_notes
        return HTTPException(_APPLY_STATUS.get(err.code, 422), detail)
    if isinstance(err, SourceError):
        return HTTPException(err.status, {"error_code": err.code, "message": err.message})
    if isinstance(err, ParseError):
        return HTTPException(_PARSE_STATUS.get(err.code, 422), {"error_code": err.code, "message": err.reason})
    return HTTPException(422, {"error_code": "MAPPING_INVALID", "message": str(err)})


@router.get(
    "/api/projects/{project_id}/disclosure-note-text-sections",
    summary="当前项目附注章节列表（scope=narrative|all，不下发正文）",
)
async def list_text_sections(
    project_id: UUID,
    year: int = Query(ge=2000, le=2200),
    scope: Literal["narrative", "all"] = "narrative",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    items = await load_target_sections(db, project_id, year, scope=scope, include_content=False)
    return {"items": items, "total": len(items)}


@router.get(
    "/api/projects/{project_id}/disclosure-note-text-batch/sources",
    summary="各章最近一次批量写入的来源（只读，供编辑器来源标记；不进导出正文）",
)
async def list_text_sources(
    project_id: UUID,
    year: int = Query(ge=2000, le=2200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_project_access("readonly")),
):
    return {"items": await latest_note_sources(db, project_id=project_id, year=year)}


@router.post(
    "/api/projects/{project_id}/disclosure-note-import/parse-upload",
    summary="解析上传的 Word / PDF 附注文档（不落库）",
)
async def parse_upload(
    project_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_note_edit_access(consol_lock=True)),
):
    data = await file.read(MAX_UPLOAD_BYTES + 1)  # 有界读取：多读 1 字节即可判超限
    try:
        fmt, result = await asyncio.to_thread(parse_upload_bytes, file.filename, file.content_type, data)
    except ParseError as err:
        raise _http_error(err) from err
    return upload_source_payload(fmt, file.filename, data, result, project_id=project_id, user_id=current_user.id)


@router.post(
    "/api/projects/{project_id}/disclosure-note-import/parse-knowledge",
    summary="逐篇判权后解析知识库文档（不落库）",
)
async def parse_knowledge(
    project_id: UUID,
    body: ParseKnowledgeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_note_edit_access(consol_lock=True)),
):
    try:
        return await knowledge_source_payload(db, project_id=project_id, user=current_user, doc_ids=body.doc_ids)
    except SourceError as err:
        raise _http_error(err) from err


@router.post(
    "/api/projects/{project_id}/disclosure-note-text-batch/preview",
    summary="服务端重算批量写入预览（不落库）",
)
async def preview_text_batch(
    project_id: UUID,
    body: BatchPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_note_edit_access(consol_lock=True)),
):
    try:
        resolved = await resolve_source(db, project_id=project_id, user=current_user, source=body.source)
        return await compute_preview(db, project_id=project_id, year=body.year, resolved=resolved,
                                     manual_mappings=body.manual_mappings,
                                     revoked_replacement_ids=body.revoked_replacement_ids)
    except (SourceError, ManualMappingError) as err:
        raise _http_error(err) from err


@router.post(
    "/api/projects/{project_id}/disclosure-note-text-batch/apply",
    summary="原子批量写入附注正文（X-Mutation-Id 幂等）",
)
async def apply_text_batch(
    project_id: UUID,
    body: BatchApplyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_note_edit_access(consol_lock=True)),
    mutation_id: str | None = Header(default=None, alias=MUTATION_ID_HEADER),
):
    if not mutation_id or not 8 <= len(mutation_id) <= 128:
        raise HTTPException(422, {"error_code": "MUTATION_ID_REQUIRED", "message": "缺少有效的 X-Mutation-Id"})
    fingerprint = mutation_fingerprint("note_text_batch_apply", body.model_dump(mode="json"))
    coordinator = DisclosureMutationCoordinator(db, project_id=project_id, mutation_id=mutation_id,
                                                fingerprint=fingerprint)

    async def _mutate() -> dict[str, Any]:
        resolved = await resolve_source(db, project_id=project_id, user=current_user, source=body.source)
        # 先锁目标再重算：预览里的现状与写入时一致（AC-4.3）
        locked = await lock_target_notes(db, project_id, body.year, [s.target_note_id for s in body.selections])
        preview = await compute_preview(db, project_id=project_id, year=body.year, resolved=resolved,
                                        manual_mappings=body.manual_mappings,
                                        revoked_replacement_ids=body.revoked_replacement_ids)
        return await apply_batch(
            db, project_id=project_id, year=body.year, locked_notes=locked, preview=preview,
            request_digest=body.preview_digest, selections=[s.model_dump() for s in body.selections],
            source_kind=resolved.kind, template_version_id=resolved.template_version_id,
            template_content_hash=resolved.template_content_hash, source_metadata=resolved.audit_metadata,
            mutation_id=mutation_id, request_fingerprint=fingerprint, user_id=current_user.id,
        )

    try:
        return await coordinator.execute(_mutate, lambda resp: build_note_saved_events(project_id, body.year, resp))
    except (ApplyError, SourceError, ManualMappingError) as err:
        raise _http_error(err) from err
